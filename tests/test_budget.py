"""Tests for per-run budget enforcement (tradingagents.budget, #582).

Covers:
- SpendTracker token/cost accumulation and check-before-spend aborts
- raise_error=True regression guard (LangChain swallows handler exceptions otherwise)
- defensive extraction (malformed LLMResult must never crash the run)
- build_spend_tracker fail-fast when max_cost_per_run lacks model_cost_rates
- partial save on BudgetExceededError in _run_graph / _save_partial_state
  (unbound-method pattern), with no decision record and no checkpoint clear;
  the save is best-effort and never masks the abort
- per-run reset in create_run_state, before the reflector's LLM calls
- checkpoint kept on abort and resumed, on upstream's real #1249 lifecycle
- the CLI abort path and BudgetConfigError fail-fast
"""

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation, LLMResult

from tradingagents.budget import (
    BudgetConfigError,
    BudgetExceededError,
    SpendTracker,
    build_spend_tracker,
    ensure_rates_configured,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _llm_result(input_tokens, output_tokens, model_name="gpt-5.4"):
    """Build a realistic LLMResult carrying usage metadata."""
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        response_metadata={"model_name": model_name},
    )
    return LLMResult(
        generations=[[ChatGeneration(message=message)]],
        llm_output={"model_name": model_name},
    )


class TestSpendTracker:

    def test_raise_error_is_true_class_attribute(self):
        """LangChain swallows handler exceptions unless raise_error is True."""
        assert SpendTracker.raise_error is True
        assert SpendTracker(max_tokens=1).raise_error is True

    def test_tokens_accumulate_from_usage_metadata(self):
        tracker = SpendTracker(max_tokens=1_000)
        tracker.on_llm_end(_llm_result(60, 30))
        tracker.on_llm_end(_llm_result(10, 5))
        assert tracker.tokens_in == 70
        assert tracker.tokens_out == 35

    def test_token_budget_aborts_before_next_call(self):
        """Check-before-spend: on_llm_end never raises, the next *start does."""
        tracker = SpendTracker(max_tokens=100)
        tracker.on_llm_end(_llm_result(60, 30))  # 90 <= 100
        tracker.on_chat_model_start({}, [])  # under budget: no raise
        tracker.on_llm_end(_llm_result(10, 5))  # 105 > 100, must NOT raise here
        with pytest.raises(BudgetExceededError, match="[Tt]oken"):
            tracker.on_chat_model_start({}, [])
        with pytest.raises(BudgetExceededError):
            tracker.on_llm_start({}, [])

    def test_cost_budget_applies_model_rates(self):
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}
        tracker = SpendTracker(max_cost=0.5, model_cost_rates=rates)
        # 50k in @ $10/1M + 10k out @ $30/1M = 0.5 + 0.3 = 0.8 USD
        tracker.on_llm_end(_llm_result(50_000, 10_000))
        assert tracker.cost == pytest.approx(0.8)
        with pytest.raises(BudgetExceededError, match="[Cc]ost"):
            tracker.on_chat_model_start({}, [])

    def test_unknown_model_billed_at_fallback_rate(self):
        """Missing rate entry warns once and bills at the most expensive
        configured rate — zero-cost counting would silently disable the budget."""
        tracker = SpendTracker(max_cost=5.0, model_cost_rates={"other": {"input": 1, "output": 1}})
        tracker.on_llm_end(_llm_result(1_000, 1_000, model_name="unknown-model"))
        tracker.on_llm_end(_llm_result(1_000, 1_000, model_name="unknown-model"))
        assert tracker.cost == pytest.approx(0.004)  # 2x (1k+1k tokens @ $1/1M each)
        tracker.on_chat_model_start({}, [])  # still under budget

    def test_defensive_extraction_never_crashes(self):
        """With raise_error=True any handler crash aborts the run, so every
        extraction path must tolerate malformed responses."""
        tracker = SpendTracker(max_cost=1.0, max_tokens=100, model_cost_rates={})
        # no generations at all
        tracker.on_llm_end(LLMResult(generations=[], llm_output=None))
        # empty inner generation list
        tracker.on_llm_end(LLMResult(generations=[[]], llm_output=None))
        # plain Generation without a message attribute
        tracker.on_llm_end(LLMResult(generations=[[Generation(text="x")]], llm_output=None))
        # message without usage_metadata, llm_output None (no model name anywhere)
        message = AIMessage(content="ok")
        tracker.on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=message)]], llm_output=None)
        )
        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0
        assert tracker.cost == 0.0


class TestBuildSpendTracker:

    @staticmethod
    def _config(**overrides):
        config = {
            "max_cost_per_run": None,
            "max_tokens_per_run": None,
            "model_cost_rates": {},
            "deep_think_llm": "gpt-5.4",
            "quick_think_llm": "gpt-5.4-mini",
        }
        config.update(overrides)
        return config

    def test_no_limits_returns_none(self):
        assert build_spend_tracker(self._config()) is None

    def test_max_tokens_alone_needs_no_rates(self):
        tracker = build_spend_tracker(self._config(max_tokens_per_run=50_000))
        assert isinstance(tracker, SpendTracker)
        assert tracker.max_tokens == 50_000
        assert tracker.max_cost is None

    def test_max_cost_without_rates_fails_fast(self):
        with pytest.raises(BudgetConfigError, match="gpt-5.4"):
            build_spend_tracker(self._config(max_cost_per_run=5.0))

    def test_max_cost_with_partial_rates_fails_fast(self):
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}  # quick model missing
        with pytest.raises(BudgetConfigError, match="gpt-5.4-mini"):
            build_spend_tracker(
                self._config(max_cost_per_run=5.0, model_cost_rates=rates)
            )

    def test_max_cost_with_full_rates_builds_tracker(self):
        rates = {
            "gpt-5.4": {"input": 10.0, "output": 30.0},
            "gpt-5.4-mini": {"input": 1.0, "output": 3.0},
        }
        tracker = build_spend_tracker(
            self._config(max_cost_per_run=5.0, model_cost_rates=rates)
        )
        assert isinstance(tracker, SpendTracker)
        assert tracker.max_cost == 5.0

    def test_ensure_rates_configured_accepts_complete_rates(self):
        ensure_rates_configured(
            {"m": {"input": 1.0, "output": 2.0}}, ["m"]
        )  # must not raise


def _run_graph_double(tmp_path, stream):
    """A spec'd stand-in for driving the real ``_run_graph`` (unbound call).

    The lifecycle collaborators stay auto-mocked, so a test can assert which
    of them a run reached.
    """
    mock_graph = MagicMock(spec=TradingAgentsGraph)
    mock_graph.debug = False
    mock_graph.config = {"checkpoint_enabled": False, "results_dir": str(tmp_path)}
    mock_graph.create_run_state.return_value = {"messages": []}
    mock_graph.checkpoint_input.side_effect = lambda state: state
    mock_graph.propagator = MagicMock()
    mock_graph.propagator.get_graph_args.return_value = {}
    mock_graph.graph = MagicMock()
    mock_graph.graph.stream = stream
    return mock_graph


def _full_state(decision="Rating: Hold\n\nHold."):
    """A state carrying every field ``_log_state`` reads."""
    return {
        "messages": [],
        "company_of_interest": "AAPL",
        "trade_date": "2026-01-01",
        "market_report": "M",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "", "bear_history": "", "history": "",
            "current_response": "", "judge_decision": "",
        },
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "", "conservative_history": "",
            "neutral_history": "", "history": "", "judge_decision": "",
        },
        "investment_plan": "",
        "final_trade_decision": decision,
    }


class TestRunGraphBudgetAbort:

    def test_abort_saves_partial_state_and_reraises(self, tmp_path):
        """A budget abort mid-stream hands the last chunk to _save_partial_state
        and re-raises; the decision record and the checkpoint clear are skipped."""
        partial_state = {"messages": [], "market_report": "partial market view"}

        def fake_stream(state, **kwargs):
            yield partial_state
            raise BudgetExceededError("cost budget exceeded")

        mock_graph = _run_graph_double(tmp_path, fake_stream)

        with pytest.raises(BudgetExceededError):
            TradingAgentsGraph._run_graph(mock_graph, "AAPL", "2026-01-01")

        mock_graph._save_partial_state.assert_called_once_with("2026-01-01", partial_state)
        mock_graph._log_state.assert_not_called()
        mock_graph.record_decision.assert_not_called()
        mock_graph.clear_checkpoint_on_success.assert_not_called()

    def test_abort_before_the_first_chunk_has_nothing_to_save(self, tmp_path):
        stream = MagicMock(side_effect=BudgetExceededError("over budget"))
        mock_graph = _run_graph_double(tmp_path, stream)

        with pytest.raises(BudgetExceededError):
            TradingAgentsGraph._run_graph(mock_graph, "AAPL", "2026-01-01")

        mock_graph._save_partial_state.assert_called_once_with("2026-01-01", None)
        mock_graph.record_decision.assert_not_called()

    def test_success_merges_chunks_and_persists_in_order(self, tmp_path):
        """Happy path: no partial save; the merged state is logged, recorded,
        then the checkpoint is cleared (upstream's order)."""
        states = [
            {"messages": [], "market_report": "M"},
            {"messages": [], "market_report": "M", "final_trade_decision": "Rating: Buy"},
        ]

        def fake_stream(state, **kwargs):
            yield from states

        mock_graph = _run_graph_double(tmp_path, fake_stream)
        mock_graph.process_signal.return_value = "Buy"

        final_state, signal = TradingAgentsGraph._run_graph(mock_graph, "AAPL", "2026-01-01")

        assert final_state == states[-1]
        assert signal == "Buy"
        mock_graph._save_partial_state.assert_not_called()
        persisted = [
            call[0] for call in mock_graph.mock_calls
            if call[0] in ("_log_state", "record_decision", "clear_checkpoint_on_success")
        ]
        assert persisted == ["_log_state", "record_decision", "clear_checkpoint_on_success"]
        mock_graph.record_decision.assert_called_once_with("AAPL", "2026-01-01", final_state)

    def test_a_failed_persistence_keeps_the_checkpoint(self, tmp_path):
        """The clear comes only after the results are persisted, so a failure
        there leaves the run resumable."""
        def fake_stream(state, **kwargs):
            yield _full_state()

        mock_graph = _run_graph_double(tmp_path, fake_stream)
        mock_graph._log_state.side_effect = OSError("disk full")

        with pytest.raises(OSError):
            TradingAgentsGraph._run_graph(mock_graph, "AAPL", "2026-01-01")

        mock_graph.clear_checkpoint_on_success.assert_not_called()

    def test_budget_abort_survives_a_real_partial_save_failure(self, tmp_path):
        """Through the real _save_partial_state: an early abort whose state
        lacks the final fields must still surface as BudgetExceededError."""
        def fake_stream(state, **kwargs):
            yield {"messages": []}
            raise BudgetExceededError("over budget")

        mock_graph = _run_graph_double(tmp_path, fake_stream)
        mock_graph.ticker = "AAPL"
        mock_graph._save_partial_state.side_effect = (
            lambda *a: TradingAgentsGraph._save_partial_state(mock_graph, *a)
        )
        mock_graph._log_state.side_effect = KeyError("final_trade_decision")

        with pytest.raises(BudgetExceededError):
            TradingAgentsGraph._run_graph(mock_graph, "AAPL", "2026-01-01")

        mock_graph._log_state.assert_called_once()
        mock_graph.clear_checkpoint_on_success.assert_not_called()


class TestSavePartialState:

    def test_writes_last_state_and_sets_curr_state(self):
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.ticker = "AAPL"
        last_state = {"messages": [], "market_report": "partial"}

        TradingAgentsGraph._save_partial_state(mock_graph, "2026-01-01", last_state)

        mock_graph._log_state.assert_called_once_with("2026-01-01", last_state)
        assert mock_graph.curr_state is last_state

    def test_nothing_streamed_writes_nothing(self):
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.ticker = "AAPL"

        TradingAgentsGraph._save_partial_state(mock_graph, "2026-01-01", None)

        mock_graph._log_state.assert_not_called()

    def test_a_failing_save_is_swallowed(self):
        """An early abort lacks final fields; the save failure is logged, not
        raised, so it can never mask the BudgetExceededError."""
        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.ticker = "AAPL"
        mock_graph._log_state.side_effect = KeyError("final_trade_decision")

        TradingAgentsGraph._save_partial_state(mock_graph, "2026-01-01", {"messages": []})

        mock_graph._log_state.assert_called_once()

    def test_an_early_abort_state_is_swallowed_by_the_real_log(self, tmp_path):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"results_dir": str(tmp_path)}
        graph.ticker = "AAPL"
        graph.log_states_dict = {}

        graph._save_partial_state("2026-01-01", {"messages": [], "market_report": "M"})

        assert not (tmp_path / "AAPL").exists()

    def test_lands_in_the_state_log(self, tmp_path):
        """Through the real _log_state: a late abort's state is on disk."""
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"results_dir": str(tmp_path)}
        graph.ticker = "AAPL"
        graph.log_states_dict = {}

        graph._save_partial_state("2026-01-01", _full_state())

        log = tmp_path / "AAPL" / "TradingAgentsStrategy_logs" / "full_states_log_2026-01-01.json"
        assert json.loads(log.read_text(encoding="utf-8"))["market_report"] == "M"


class TestBudgetAbortKeepsCheckpoint:
    """On upstream's real checkpoint lifecycle (#1249), through propagate()."""

    def test_abort_keeps_checkpoint_and_the_resumed_run_clears_it(self, tmp_path):
        from typing import TypedDict

        from langgraph.graph import END, StateGraph

        from tradingagents.graph.checkpointer import checkpoint_step
        from tradingagents.graph.propagation import Propagator

        over_budget = {"now": True}

        class _State(TypedDict, total=False):
            messages: list
            count: int
            final_trade_decision: str

        def analyst(state):
            return {"count": state["count"] + 1}

        def trader(state):
            if over_budget["now"]:
                raise BudgetExceededError("over budget")
            return {"count": state["count"] + 10, "final_trade_decision": "Rating: Hold"}

        workflow = StateGraph(_State)
        workflow.add_node("analyst", analyst)
        workflow.add_node("trader", trader)
        workflow.set_entry_point("analyst")
        workflow.add_edge("analyst", "trader")
        workflow.add_edge("trader", END)

        graph = object.__new__(TradingAgentsGraph)
        graph.config = {
            "checkpoint_enabled": True, "data_cache_dir": str(tmp_path),
            "max_debate_rounds": 1, "max_risk_discuss_rounds": 1,
        }
        graph.selected_analysts = ("market",)
        graph.workflow = workflow
        graph.graph = workflow.compile()
        graph._checkpointer_ctx = None
        graph._resuming = False
        graph.debug = False
        graph.propagator = Propagator()
        graph.create_run_state = lambda *a, **k: {"messages": [], "count": 0}
        saved, recorded = [], []
        graph._log_state = lambda trade_date, state: saved.append(dict(state))
        graph.record_decision = lambda *a: recorded.append(a)
        graph.process_signal = lambda text: "Hold"
        signature = graph._run_signature("stock")

        with pytest.raises(BudgetExceededError):
            graph.propagate("AAPL", "2026-01-02")

        assert saved[-1]["count"] == 1  # the analyst's step was saved
        assert recorded == []
        assert checkpoint_step(str(tmp_path), "AAPL", "2026-01-02", signature) is not None

        over_budget["now"] = False
        final_state, _ = graph.propagate("AAPL", "2026-01-02")

        assert final_state["count"] == 11  # resumed into the trader, not rerun
        assert len(recorded) == 1
        assert checkpoint_step(str(tmp_path), "AAPL", "2026-01-02", signature) is None


class TestRateResolution:
    """Alias/revision model names must not silently disable cost enforcement."""

    def test_exact_match_wins(self):
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}
        tracker = SpendTracker(max_cost=5.0, model_cost_rates=rates)
        assert tracker._resolve_rate("gpt-5.4") == rates["gpt-5.4"]

    def test_revision_name_prefix_matches_configured_rate(self):
        """Providers report revision names like gpt-5.4-2026-01-01."""
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}
        tracker = SpendTracker(max_cost=5.0, model_cost_rates=rates)
        assert tracker._resolve_rate("gpt-5.4-2026-01-01") == rates["gpt-5.4"]

    def test_unknown_model_billed_at_most_expensive_rate(self):
        rates = {
            "cheap": {"input": 1.0, "output": 3.0},
            "expensive": {"input": 10.0, "output": 30.0},
        }
        tracker = SpendTracker(max_cost=5.0, model_cost_rates=rates)
        assert tracker._resolve_rate("totally-unknown") == rates["expensive"]

    def test_unknown_model_cost_accumulates_nonzero(self):
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}
        tracker = SpendTracker(max_cost=5.0, model_cost_rates=rates)
        tracker.on_llm_end(_llm_result(1_000_000, 0, model_name="alias-model"))
        assert tracker.cost == pytest.approx(10.0)

    def test_no_rates_configured_returns_none(self):
        tracker = SpendTracker(max_tokens=100)
        assert tracker._resolve_rate("anything") is None


class TestSpendTrackerReset:

    def test_reset_zeroes_counters(self):
        rates = {"gpt-5.4": {"input": 10.0, "output": 30.0}}
        tracker = SpendTracker(max_cost=5.0, model_cost_rates=rates)
        tracker.on_llm_end(_llm_result(1_000_000, 500_000))
        assert tracker.tokens_in > 0 and tracker.cost > 0
        tracker.reset()
        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0
        assert tracker.cost == 0.0

    def test_create_run_state_resets_tracker_per_run(self):
        """A reused graph instance must not inherit spend from a prior run."""
        tracker = SpendTracker(max_tokens=1_000)
        tracker.on_llm_end(_llm_result(600, 300))  # leftover from "run 1"

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = tracker
        mock_graph.propagator = MagicMock()
        mock_graph.memory_log = MagicMock()

        TradingAgentsGraph.create_run_state(mock_graph, "AAPL", "2026-01-02")

        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0
        assert tracker.cost == 0.0

    def test_reflection_spend_counts_toward_the_new_run(self):
        """The reset comes before pending decisions are settled, so the
        reflector's LLM spend is charged to this run instead of wiped."""
        tracker = SpendTracker(max_tokens=1_000)
        tracker.on_llm_end(_llm_result(600, 300))  # leftover from "run 1"

        def settle(ticker):
            assert tracker.tokens_in == 0  # already reset
            tracker.on_llm_end(_llm_result(40, 10))  # the reflector's call

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = tracker
        mock_graph._resolve_pending_entries.side_effect = settle
        mock_graph.propagator = MagicMock()
        mock_graph.memory_log = MagicMock()

        TradingAgentsGraph.create_run_state(mock_graph, "AAPL", "2026-01-02")

        mock_graph._resolve_pending_entries.assert_called_once_with("AAPL")
        assert (tracker.tokens_in, tracker.tokens_out) == (40, 10)

    def test_on_llm_end_with_none_response_is_ignored(self):
        tracker = SpendTracker(max_tokens=100)
        tracker.on_llm_end(None)  # must not raise despite raise_error=True


# --- the CLI path ----------------------------------------------------------------

class _CliFakeGraph:
    """Records the lifecycle calls run_analysis makes; the stream aborts."""

    def __init__(self):
        self.calls = []
        self.graph = self
        self.propagator = self
        self.ticker = None

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        self.calls.append(("create_run_state", ticker, trade_date))
        return {"messages": [], "company_of_interest": ticker}

    def get_graph_args(self, callbacks=None):
        return {}

    def begin_checkpoint(self, *a, **k):
        return None

    def checkpoint_input(self, state):
        return state

    def stream(self, graph_input, **kwargs):
        yield {"messages": [], "market_report": "M"}
        raise BudgetExceededError("Token budget exceeded")

    def record_decision(self, *a):
        self.calls.append(("record_decision",))

    def clear_checkpoint_on_success(self, *a, **k):
        self.calls.append(("clear_checkpoint",))

    def _save_partial_state(self, trade_date, last_state):
        self.calls.append(("save_partial", self.ticker, trade_date, last_state))

    def end_checkpoint(self):
        self.calls.append(("end_checkpoint",))


class _NullLive:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeBuffer:
    def __init__(self):
        self.messages = []
        self.tool_calls = []
        self.report_sections = {}
        self.agent_status = {}
        self.selected_analysts = []
        self._processed_message_ids = set()

    def init_for_analysis(self, selected_analysts):
        self.selected_analysts = [a.lower() for a in selected_analysts]

    def add_message(self, kind, content):
        self.messages.append((0.0, kind, content))

    def add_tool_call(self, name, args):
        self.tool_calls.append((0.0, name, args))

    def update_report_section(self, *a):
        pass

    def update_agent_status(self, agent, status):
        self.agent_status[agent] = status


def _wire_cli(monkeypatch, tmp_path, graph_factory):
    import cli.main as m
    from cli.models import AnalystType

    monkeypatch.setattr(m, "TradingAgentsGraph", graph_factory)
    monkeypatch.setattr(m, "message_buffer", _FakeBuffer())
    monkeypatch.setattr(m, "create_layout", lambda: None)
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m, "Live", _NullLive)
    monkeypatch.setattr(m, "get_user_selections", lambda: {
        "ticker": "NVDA", "analysis_date": "2026-01-10",
        "analysts": [AnalystType.MARKET], "asset_type": "stock",
    })
    monkeypatch.setattr(m, "_build_run_config", lambda selections, checkpoint: {
        "data_cache_dir": str(tmp_path / "cache"), "results_dir": str(tmp_path / "results"),
    })
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")
    return m


class TestCliBudget:

    def test_cli_abort_saves_partial_state_and_skips_record_and_clear(self, tmp_path, monkeypatch):
        fake = _CliFakeGraph()
        m = _wire_cli(monkeypatch, tmp_path, lambda *a, **k: fake)

        with pytest.raises(m.typer.Exit) as excinfo:
            m.run_analysis()

        assert excinfo.value.exit_code == 1
        assert fake.calls == [
            ("create_run_state", "NVDA", "2026-01-10"),
            ("save_partial", "NVDA", "2026-01-10", {"messages": [], "market_report": "M"}),
            ("end_checkpoint",),
        ]

    def test_cli_budget_config_error_exits_before_the_run(self, tmp_path, monkeypatch):
        def refuse(*a, **k):
            raise BudgetConfigError("max_cost_per_run needs model_cost_rates")

        m = _wire_cli(monkeypatch, tmp_path, refuse)

        with pytest.raises(m.typer.Exit) as excinfo:
            m.run_analysis()

        assert excinfo.value.exit_code == 1
        assert not (tmp_path / "results").exists()
