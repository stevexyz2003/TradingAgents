"""Tests for per-run budget enforcement (tradingagents.budget, #582).

Covers:
- SpendTracker token/cost accumulation and check-before-spend aborts
- raise_error=True regression guard (LangChain swallows handler exceptions otherwise)
- defensive extraction (malformed LLMResult must never crash the run)
- build_spend_tracker fail-fast when max_cost_per_run lacks model_cost_rates
- stream_run partial save on BudgetExceededError (unbound-method pattern)
"""

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


class TestStreamRunBudgetAbort:

    def test_stream_run_saves_partial_state_and_reraises(self, tmp_path):
        """Budget abort mid-stream saves the last chunk via _log_state and re-raises."""
        partial_state = {"messages": [], "market_report": "partial market view"}

        def fake_stream(state, **kwargs):
            yield partial_state
            raise BudgetExceededError("cost budget exceeded")

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = None
        mock_graph.config = {"checkpoint_enabled": False, "results_dir": str(tmp_path)}
        mock_graph.graph = MagicMock()
        mock_graph.graph.stream = fake_stream
        mock_graph.propagator = MagicMock()
        mock_graph.propagator.create_initial_state.return_value = {"messages": []}
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.memory_log = MagicMock()
        mock_graph.memory_log.get_past_context.return_value = ""

        chunks = []
        with pytest.raises(BudgetExceededError):
            for chunk in TradingAgentsGraph.stream_run(
                mock_graph, "AAPL", "2026-01-01"
            ):
                chunks.append(chunk)

        assert chunks == [partial_state]
        mock_graph._log_state.assert_called_once_with("2026-01-01", partial_state)
        assert mock_graph.curr_state is partial_state

    def test_stream_run_yields_all_chunks_on_success(self, tmp_path):
        """Happy path: chunks pass through, no partial save happens."""
        states = [{"messages": [], "step": 1}, {"messages": [], "step": 2}]

        def fake_stream(state, **kwargs):
            yield from states

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = None
        mock_graph.config = {"checkpoint_enabled": False, "results_dir": str(tmp_path)}
        mock_graph.graph = MagicMock()
        mock_graph.graph.stream = fake_stream
        mock_graph.propagator = MagicMock()
        mock_graph.propagator.create_initial_state.return_value = {"messages": []}
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.memory_log = MagicMock()
        mock_graph.memory_log.get_past_context.return_value = ""

        chunks = list(
            TradingAgentsGraph.stream_run(mock_graph, "AAPL", "2026-01-01")
        )

        assert chunks == states
        mock_graph._log_state.assert_not_called()


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

    def test_stream_run_resets_tracker_per_run(self, tmp_path):
        """A reused graph instance must not inherit spend from a prior run."""
        tracker = SpendTracker(max_tokens=1_000)
        tracker.on_llm_end(_llm_result(600, 300))  # leftover from "run 1"

        def fake_stream(state, **kwargs):
            yield {"messages": [], "step": 1}

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = tracker
        mock_graph.config = {"checkpoint_enabled": False, "results_dir": str(tmp_path)}
        mock_graph.graph = MagicMock()
        mock_graph.graph.stream = fake_stream
        mock_graph.propagator = MagicMock()
        mock_graph.propagator.create_initial_state.return_value = {"messages": []}
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.memory_log = MagicMock()
        mock_graph.memory_log.get_past_context.return_value = ""

        list(TradingAgentsGraph.stream_run(mock_graph, "AAPL", "2026-01-02"))

        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0
        assert tracker.cost == 0.0

    def test_on_llm_end_with_none_response_is_ignored(self):
        tracker = SpendTracker(max_tokens=100)
        tracker.on_llm_end(None)  # must not raise despite raise_error=True


class TestStreamRunCheckpointClear:

    def test_stream_run_clears_checkpoint_on_success(self, tmp_path, monkeypatch):
        """Success-clear lives in stream_run so the CLI path gets it too."""
        import tradingagents.graph.trading_graph as tg

        cleared = []
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock())
        ctx.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(tg, "get_checkpointer", lambda *a, **k: ctx)
        monkeypatch.setattr(tg, "checkpoint_step", lambda *a, **k: None)
        monkeypatch.setattr(tg, "thread_id", lambda *a, **k: "tid")
        monkeypatch.setattr(
            tg, "clear_checkpoint", lambda *a, **k: cleared.append(a)
        )

        def fake_stream(state, **kwargs):
            yield {"messages": [], "step": 1}

        compiled = MagicMock()
        compiled.stream = fake_stream

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = None
        mock_graph.config = {
            "checkpoint_enabled": True,
            "data_cache_dir": str(tmp_path),
            "results_dir": str(tmp_path),
        }
        mock_graph.workflow = MagicMock()
        mock_graph.workflow.compile.return_value = compiled
        mock_graph.propagator = MagicMock()
        mock_graph.propagator.create_initial_state.return_value = {"messages": []}
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.memory_log = MagicMock()
        mock_graph.memory_log.get_past_context.return_value = ""

        list(TradingAgentsGraph.stream_run(mock_graph, "AAPL", "2026-01-01"))

        assert cleared == [(str(tmp_path), "AAPL", "2026-01-01")]

    def test_stream_run_keeps_checkpoint_on_budget_abort(self, tmp_path, monkeypatch):
        """Abort must stay resumable: no clear on BudgetExceededError."""
        import tradingagents.graph.trading_graph as tg

        cleared = []
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock())
        ctx.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(tg, "get_checkpointer", lambda *a, **k: ctx)
        monkeypatch.setattr(tg, "checkpoint_step", lambda *a, **k: None)
        monkeypatch.setattr(tg, "thread_id", lambda *a, **k: "tid")
        monkeypatch.setattr(
            tg, "clear_checkpoint", lambda *a, **k: cleared.append(a)
        )

        def fake_stream(state, **kwargs):
            yield {"messages": [], "step": 1}
            raise BudgetExceededError("over budget")

        compiled = MagicMock()
        compiled.stream = fake_stream

        mock_graph = MagicMock(spec=TradingAgentsGraph)
        mock_graph.spend_tracker = None
        mock_graph.config = {
            "checkpoint_enabled": True,
            "data_cache_dir": str(tmp_path),
            "results_dir": str(tmp_path),
        }
        mock_graph.workflow = MagicMock()
        mock_graph.workflow.compile.return_value = compiled
        mock_graph.propagator = MagicMock()
        mock_graph.propagator.create_initial_state.return_value = {"messages": []}
        mock_graph.propagator.get_graph_args.return_value = {}
        mock_graph.memory_log = MagicMock()
        mock_graph.memory_log.get_past_context.return_value = ""

        with pytest.raises(BudgetExceededError):
            list(TradingAgentsGraph.stream_run(mock_graph, "AAPL", "2026-01-01"))

        assert cleared == []
