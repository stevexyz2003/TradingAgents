"""Tests for the unattended daily paper run (scripts/daily_paper_run.py).

The runner is operational tooling for the scheduled fork job, so the parts
that decide *what* runs (tickers, trade date, budget, credentials) and *what
is persisted* (summary, index, archive) are covered without any network or
LLM access. The graph itself is stubbed.
"""

import importlib.util
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingagents.budget import BudgetExceededError
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import PortfolioContext, Position

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_paper_run.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("daily_paper_run", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


# Priced for whatever models the config defaults to, so the fixture follows
# upstream's default-model changes instead of pinning today's names.
RATES = {
    DEFAULT_CONFIG["deep_think_llm"]: {"input": 5.0, "output": 40.0},
    DEFAULT_CONFIG["quick_think_llm"]: {"input": 1.0, "output": 8.0},
}


def _rate_file(tmp_path: Path, payload=None) -> Path:
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(RATES if payload is None else payload), encoding="utf-8")
    return path


class _FakeGraph:
    """Stand-in for TradingAgentsGraph with a controllable outcome."""

    def __init__(self, *, signal="Buy", error=None, cost=0.25):
        self.signal = signal
        self.error = error
        self.spend_tracker = SimpleNamespace(tokens_in=1000, tokens_out=200, cost=cost)
        self.calls = []
        self.portfolios = []

    def propagate(self, ticker, trade_date, asset_type="stock", **kwargs):
        self.calls.append((ticker, trade_date))
        # Sentinel when the kwarg is absent: proves the unchanged CI call shape.
        self.portfolios.append(kwargs.get("portfolio", "<absent>"))
        if self.error is not None:
            raise self.error
        return {"final_trade_decision": f"**Rating**: {self.signal}"}, self.signal

    def save_reports(self, final_state, ticker, save_path=None):
        path = Path(save_path)
        path.mkdir(parents=True, exist_ok=True)
        report = path / "complete_report.md"
        report.write_text(f"# {ticker}\n", encoding="utf-8")
        return report


class TestParseTickers:
    def test_splits_uppercases_and_dedupes_preserving_order(self):
        assert runner.parse_tickers("msft, aapl nvda,AAPL") == ["MSFT", "AAPL", "NVDA"]

    def test_rejects_path_traversal(self):
        with pytest.raises(runner.ConfigError, match="Invalid ticker"):
            runner.parse_tickers("../../etc/passwd")

    def test_rejects_empty_list(self):
        with pytest.raises(runner.ConfigError, match="No tickers"):
            runner.parse_tickers("  , ")

    def test_enforces_the_cap(self):
        with pytest.raises(runner.ConfigError, match="cap is 2"):
            runner.parse_tickers("A,B,C", max_tickers=2)


class TestTradeDate:
    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            ("2026-08-19", "2026-08-18"),  # Wednesday -> Tuesday
            ("2026-08-17", "2026-08-14"),  # Monday -> Friday
            ("2026-08-16", "2026-08-14"),  # Sunday -> Friday
        ],
    )
    def test_previous_weekday(self, today, expected):
        from datetime import datetime

        now = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=UTC)
        assert runner.previous_weekday(now) == expected

    def test_explicit_date_passes_through(self):
        assert runner.resolve_trade_date("2026-01-02") == "2026-01-02"

    def test_malformed_date_is_a_config_error(self):
        with pytest.raises(runner.ConfigError, match="YYYY-MM-DD"):
            runner.resolve_trade_date("02.01.2026")


class TestLoadRates:
    def test_loads_and_skips_documentation_keys(self, tmp_path):
        path = _rate_file(tmp_path, {"_note": "docs", "m": {"input": 1, "output": 2}})
        assert runner.load_rates(path) == {"m": {"input": 1.0, "output": 2.0}}

    def test_missing_file(self, tmp_path):
        with pytest.raises(runner.ConfigError, match="not found"):
            runner.load_rates(tmp_path / "nope.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "rates.json"
        path.write_text("{oops", encoding="utf-8")
        with pytest.raises(runner.ConfigError, match="not valid JSON"):
            runner.load_rates(path)

    def test_entry_without_output_rate(self, tmp_path):
        path = _rate_file(tmp_path, {"m": {"input": 1}})
        with pytest.raises(runner.ConfigError, match="needs both"):
            runner.load_rates(path)

    def test_documentation_only_file_is_rejected(self, tmp_path):
        # A file with nothing but comments would leave the budget unenforced.
        path = _rate_file(tmp_path, {"_note": "docs"})
        with pytest.raises(runner.ConfigError, match="no model entries"):
            runner.load_rates(path)

    @pytest.mark.skipif(
        any(os.environ.get(v) for v in ("TRADINGAGENTS_DEEP_THINK_LLM",
                                        "TRADINGAGENTS_QUICK_THINK_LLM")),
        reason="models overridden by the environment",
    )
    def test_the_committed_table_prices_the_default_models(self):
        # A configured model without a rate fails the run with exit 1, so a
        # change of the framework's default models needs entries here too.
        rates = runner.load_rates(_SCRIPT.with_name("paper_run_rates.json"))
        for key in ("deep_think_llm", "quick_think_llm"):
            assert DEFAULT_CONFIG[key] in rates, DEFAULT_CONFIG[key]

    def test_the_committed_table_prices_the_models_the_workflow_pins(self):
        # The scheduled run pins its own models in the workflow (upstream
        # re-points its defaults every release), so those are the names that
        # actually get billed - an unpriced one exits 1 before any analysis.
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "daily-paper-run.yml"
        ).read_text(encoding="utf-8")
        pinned = re.findall(
            r"TRADINGAGENTS_(?:DEEP|QUICK)_THINK_LLM:.*\|\|\s*'([^']+)'", workflow
        )
        assert len(pinned) == 2, f"expected both tiers pinned, found {pinned}"
        rates = runner.load_rates(_SCRIPT.with_name("paper_run_rates.json"))
        for model in pinned:
            assert model in rates, model


class TestCredentials:
    def test_openai_needs_its_key(self):
        assert runner.missing_credentials("openai", {}) == ["OPENAI_API_KEY"]

    def test_blank_key_counts_as_missing(self):
        assert runner.missing_credentials("openai", {"OPENAI_API_KEY": "  "}) == [
            "OPENAI_API_KEY"
        ]

    def test_present_key_satisfies_the_check(self):
        assert runner.missing_credentials("openai", {"OPENAI_API_KEY": "sk-x"}) == []

    def test_a_tiers_own_provider_is_checked_too(self):
        # #1440 lets a tier name its own provider. Checking llm_provider alone
        # would pass preflight and then exit 1 mid-run on the missing key.
        config = {
            "llm_provider": "anthropic",
            "quick_think_provider": "openai",
            "deep_think_provider": None,
        }
        assert runner.providers_in_use(config) == ["anthropic", "openai"]
        assert runner.missing_credentials_for_config(
            config, {"ANTHROPIC_API_KEY": "sk-ant-x"}
        ) == ["OPENAI_API_KEY"]

    def test_both_tiers_on_the_configured_provider_need_one_key(self):
        config = {
            "llm_provider": "anthropic",
            "quick_think_provider": None,
            "deep_think_provider": None,
        }
        assert runner.providers_in_use(config) == ["anthropic"]
        assert runner.missing_credentials_for_config(config, {}) == ["ANTHROPIC_API_KEY"]
        assert (
            runner.missing_credentials_for_config(config, {"ANTHROPIC_API_KEY": "sk-ant-x"})
            == []
        )

    def test_local_runtime_needs_nothing(self):
        assert runner.missing_credentials("ollama", {}) == []

    def test_azure_needs_all_four(self):
        assert runner.missing_credentials("azure", {}) == list(runner.AZURE_REQUIRED_ENV)


class TestBuildConfig:
    def test_budget_and_paths(self, tmp_path):
        config = runner.build_config(
            rates=RATES, max_cost=1.5, out_dir=tmp_path / "out", state_dir=tmp_path / "state"
        )
        assert config["max_cost_per_run"] == 1.5
        assert config["model_cost_rates"] == RATES
        assert config["results_dir"] == str(tmp_path / "out" / "logs")
        assert config["memory_log_path"] == str(tmp_path / "state" / "decision-log.md")

    def test_checkpoint_resume_is_off(self, tmp_path):
        # Resuming yesterday's graph into today's trade date would silently
        # analyze the wrong session.
        config = runner.build_config(
            rates=RATES,
            max_cost=1.0,
            out_dir=tmp_path,
            state_dir=tmp_path,
            base_config={"checkpoint_enabled": True},
        )
        assert config["checkpoint_enabled"] is False

    def test_does_not_mutate_the_shared_default_config(self, tmp_path):
        from tradingagents.default_config import DEFAULT_CONFIG

        runner.build_config(rates=RATES, max_cost=1.0, out_dir=tmp_path, state_dir=tmp_path)
        assert DEFAULT_CONFIG["max_cost_per_run"] is None


class TestRunTicker:
    def test_success_records_signal_cost_and_report(self, tmp_path):
        graph = _FakeGraph(signal="Overweight", cost=0.42)
        record = runner.run_ticker(graph, "AAPL", "2026-08-20", tmp_path)
        assert record["status"] == "ok"
        assert record["signal"] == "Overweight"
        assert record["cost_usd"] == 0.42
        assert record["tokens_in"] == 1000
        assert Path(record["report"]).is_file()

    def test_budget_abort_is_its_own_status(self, tmp_path):
        graph = _FakeGraph(error=BudgetExceededError("cap reached", cost=1.5))
        record = runner.run_ticker(graph, "AAPL", "2026-08-20", tmp_path)
        assert record["status"] == "budget_aborted"
        assert "cap reached" in record["error"]

    def test_runtime_error_is_captured_not_raised(self, tmp_path):
        graph = _FakeGraph(error=RuntimeError("vendor down"))
        record = runner.run_ticker(graph, "AAPL", "2026-08-20", tmp_path)
        assert record["status"] == "failed"
        assert record["error"] == "RuntimeError: vendor down"

    def test_a_jev_review_is_carried_into_the_record(self, tmp_path):
        jev = {"model": "jev-1.13.0", "questions": {"final_rating": {"applied": True}}}

        class _JevGraph(_FakeGraph):
            def propagate(self, ticker, trade_date, asset_type="stock", **kwargs):
                state, signal = super().propagate(ticker, trade_date, asset_type, **kwargs)
                return {**state, "jev": jev, "final_rating_source": "jev"}, signal

        record = runner.run_ticker(_JevGraph(), "AAPL", "2026-08-20", tmp_path)
        assert record["jev"] == jev
        assert record["rating_source"] == "jev"

    def test_without_jev_the_record_has_no_jev_fields(self, tmp_path):
        record = runner.run_ticker(_FakeGraph(), "AAPL", "2026-08-20", tmp_path)
        assert "jev" not in record and "rating_source" not in record


class TestIndex:
    def test_header_written_once_and_rows_appended(self, tmp_path):
        index = tmp_path / "index.md"
        summary = {
            "trade_date": "2026-08-20",
            "runs": [
                {
                    "ticker": "AAPL", "signal": "Buy", "status": "ok",
                    "cost_usd": 0.5, "tokens_in": 10, "tokens_out": 2,
                }
            ],
        }
        runner.append_index_rows(index, summary)
        runner.append_index_rows(index, summary)
        text = index.read_text(encoding="utf-8")
        assert text.count("# Paper-run index") == 1
        assert text.count("| 2026-08-20 | AAPL |") == 2


def _run_main(monkeypatch, tmp_path, graph, extra_args=()):
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        lambda config=None, **kwargs: graph,
    )
    argv = [
        "--tickers", "AAPL",
        "--date", "2026-08-20",
        "--max-cost", "1.0",
        "--rates", str(_rate_file(tmp_path)),
        "--out", str(tmp_path / "out"),
        "--state", str(tmp_path / "state"),
        *extra_args,
    ]
    return runner.main(argv)


class TestMain:
    def test_successful_day_writes_summary_index_and_archive(self, monkeypatch, tmp_path):
        graph = _FakeGraph(cost=0.3)
        assert _run_main(monkeypatch, tmp_path, graph) == runner.EXIT_OK

        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "ok"
        assert summary["trade_date"] == "2026-08-20"
        assert summary["totals"] == {
            "tickers": 1, "cost_usd": 0.3, "tokens_in": 1000, "tokens_out": 200,
            "ok": 1, "failed": 0, "budget_aborted": 0, "skipped": 0,
        }
        assert (tmp_path / "out" / "summary.md").is_file()
        assert (tmp_path / "state" / "index.md").is_file()
        # Archived on the state branch so the record outlives artifact retention.
        assert (tmp_path / "state" / "runs" / "2026-08-20" / "summary.json").is_file()
        assert (tmp_path / "state" / "runs" / "2026-08-20" / "AAPL.md").is_file()

    def test_failed_ticker_exits_three(self, monkeypatch, tmp_path):
        graph = _FakeGraph(error=RuntimeError("boom"))
        assert _run_main(monkeypatch, tmp_path, graph) == runner.EXIT_RUN_FAILED
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "failed"

    def test_budget_abort_exits_four_and_still_persists(self, monkeypatch, tmp_path):
        graph = _FakeGraph(error=BudgetExceededError("over"))
        assert _run_main(monkeypatch, tmp_path, graph) == runner.EXIT_BUDGET
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "partial"
        assert (tmp_path / "state" / "index.md").is_file()

    def test_two_tickers_second_skipped_when_day_budget_is_spent(self, monkeypatch, tmp_path):
        graph = _FakeGraph(cost=0.9)
        monkeypatch.setattr(
            "tradingagents.graph.trading_graph.TradingAgentsGraph",
            lambda config=None, **kwargs: graph,
        )
        exit_code = runner.main([
            "--tickers", "AAPL,MSFT",
            "--date", "2026-08-20",
            "--max-cost", "1.0",
            "--max-total-cost", "0.5",
            "--rates", str(_rate_file(tmp_path)),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
        ])
        assert exit_code == runner.EXIT_BUDGET
        assert graph.calls == [("AAPL", "2026-08-20")]
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        statuses = {run["ticker"]: run["status"] for run in summary["runs"]}
        assert statuses == {"AAPL": "ok", "MSFT": "skipped"}

    def test_bad_rate_file_exits_one_without_building_a_graph(self, tmp_path):
        exit_code = runner.main([
            "--tickers", "AAPL",
            "--max-cost", "1.0",
            "--rates", str(tmp_path / "missing.json"),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
        ])
        assert exit_code == runner.EXIT_CONFIG

    def test_rates_missing_the_configured_model_exit_one(self, tmp_path):
        # build_spend_tracker would raise this at graph construction; the
        # runner reaches it in preflight, before any credential is needed.
        path = _rate_file(tmp_path, {"some-other-model": {"input": 1, "output": 2}})
        exit_code = runner.main([
            "--tickers", "AAPL",
            "--max-cost", "1.0",
            "--rates", str(path),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
            "--preflight",
        ])
        assert exit_code == runner.EXIT_CONFIG

    def test_preflight_passes_without_touching_the_graph(self, tmp_path):
        exit_code = runner.main([
            "--tickers", "AAPL",
            "--max-cost", "1.0",
            "--rates", str(_rate_file(tmp_path)),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
            "--preflight",
        ])
        assert exit_code == runner.EXIT_OK
        assert not (tmp_path / "out" / "summary.json").exists()

    def test_preflight_reports_missing_credentials_distinctly(self, monkeypatch, tmp_path):
        # Exit 20 is what lets the workflow skip green instead of going red
        # every morning until the operator adds the secret.
        monkeypatch.setenv("OPENAI_API_KEY", "")
        exit_code = runner.main([
            "--tickers", "AAPL",
            "--max-cost", "1.0",
            "--rates", str(_rate_file(tmp_path)),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
            "--preflight",
        ])
        assert exit_code == runner.EXIT_NO_CREDENTIALS


def _portfolio_file(tmp_path: Path, payload) -> Path:
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _as_of(age: timedelta = timedelta(0)) -> str:
    return (datetime.now(UTC) - age).isoformat()


def _book(**extra):
    return {"cash": 1000.0, "currency": "EUR", "positions": [], "as_of": _as_of(), **extra}


@pytest.mark.unit
class TestPortfolio:
    def test_portfolio_is_passed_to_propagate(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, {
            "cash": 1000.0,
            "currency": "EUR",
            "positions": [{"ticker": "AAPL", "quantity": 10, "average_price": 150.0}],
            "as_of": _as_of(timedelta(minutes=2)),
        })
        graph = _FakeGraph()
        exit_code = _run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(path)))
        assert exit_code == runner.EXIT_OK
        assert graph.portfolios == [
            PortfolioContext(
                cash=1000.0,
                currency="EUR",
                positions=[Position(ticker="AAPL", quantity=10, average_price=150.0)],
            )
        ]
        assert graph.portfolios[0].positions[0].ticker == "AAPL"

    def test_without_portfolio_propagate_gets_no_portfolio_kwarg(self, monkeypatch, tmp_path):
        graph = _FakeGraph()
        assert _run_main(monkeypatch, tmp_path, graph) == runner.EXIT_OK
        assert graph.portfolios == ["<absent>"]

    def test_missing_portfolio_file_is_a_config_error(self, monkeypatch, tmp_path, capsys):
        graph = _FakeGraph()
        missing = tmp_path / "no-such-portfolio.json"
        exit_code = _run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(missing)))
        assert exit_code == runner.EXIT_CONFIG
        assert graph.calls == []
        assert "portfolio" in capsys.readouterr().err

    def test_invalid_portfolio_file_is_a_config_error(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, {"positions": [{"quantity": "x"}]})
        graph = _FakeGraph()
        exit_code = _run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(path)))
        assert exit_code == runner.EXIT_CONFIG
        assert graph.calls == []

    def test_invalid_portfolio_fails_preflight_too(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, {"positions": [{"quantity": "x"}]})
        graph = _FakeGraph()
        exit_code = _run_main(
            monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(path), "--preflight")
        )
        assert exit_code == runner.EXIT_CONFIG

    # --- CR-02: a portfolio needs a positive proof that it is fresh ---------------------

    @pytest.mark.parametrize(
        ("payload", "reason"),
        [
            ({"cash": 1000.0, "currency": "EUR", "positions": []}, "no as_of"),
            (_book(as_of=None), "no as_of"),
            (_book(as_of="yesterday"), "not an ISO timestamp"),
            (_book(as_of="2026-10-12T08:00:00"), "no time zone"),
            (_book(as_of=_as_of(timedelta(hours=26))), "older than"),
            (_book(as_of=_as_of(timedelta(minutes=61))), "older than"),
            (_book(as_of=_as_of(-timedelta(hours=1))), "in the future"),
        ],
        ids=["missing", "null", "garbage", "naive", "yesterday", "just-stale", "future"],
    )
    def test_portfolio_without_fresh_as_of_is_refused(
        self, monkeypatch, tmp_path, capsys, payload, reason
    ):
        path = _portfolio_file(tmp_path, payload)
        graph = _FakeGraph()
        exit_code = _run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(path)))
        assert exit_code == runner.EXIT_CONFIG
        assert graph.calls == []
        err = capsys.readouterr().err
        assert reason in err
        assert str(path.resolve()) in err

    def test_stale_portfolio_fails_preflight_too(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, _book(as_of=_as_of(timedelta(days=7))))
        exit_code = _run_main(
            monkeypatch,
            tmp_path,
            _FakeGraph(),
            extra_args=("--portfolio", str(path), "--preflight"),
        )
        assert exit_code == runner.EXIT_CONFIG

    def test_max_age_flag_widens_the_window(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, _book(as_of=_as_of(timedelta(hours=3))))
        graph = _FakeGraph()
        args = ("--portfolio", str(path), "--portfolio-max-age-minutes", "240")
        assert _run_main(monkeypatch, tmp_path, graph, extra_args=args) == runner.EXIT_OK
        assert graph.portfolios[0].cash == 1000.0

    def test_max_age_must_be_positive(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, _book())
        args = ("--portfolio", str(path), "--portfolio-max-age-minutes", "0")
        assert _run_main(monkeypatch, tmp_path, _FakeGraph(), extra_args=args) == runner.EXIT_CONFIG

    def test_fresh_portfolio_is_accepted_and_its_age_printed(self, monkeypatch, tmp_path, capsys):
        path = _portfolio_file(tmp_path, _book(as_of=_as_of(timedelta(minutes=5))))
        graph = _FakeGraph()
        exit_code = _run_main(monkeypatch, tmp_path, graph, extra_args=("--portfolio", str(path)))
        assert exit_code == runner.EXIT_OK
        assert "as_of" in capsys.readouterr().out


# --------------------------------------------------------------------------
# --portfolio-from-published (phase 7): fail-open reader of the published book
# --------------------------------------------------------------------------

from tests.calendar_stub import WeekdayCalendar  # noqa: E402

_FEED_NOW = datetime(2026, 10, 20, 6, 30, tzinfo=UTC)  # Tuesday morning
_FEED_FRESH = "2026-10-19T21:00:00+00:00"  # Monday evening, after the Friday close
_FEED_SHA = "a" * 40


class _FakeReader:
    def __init__(self, blob=None, *, fetch_error=None, read_error=None):
        self.blob = blob
        self.fetch_error = fetch_error
        self.read_error = read_error
        self.reads = []

    def fetch(self):
        if self.fetch_error:
            raise self.fetch_error
        return _FEED_SHA

    def read(self, path):
        self.reads.append(path)
        if self.read_error:
            raise self.read_error
        return self.blob


def _feed_blob(**overrides) -> bytes:
    book = {"cash": 1000.0, "currency": "EUR", "positions": [], "as_of": _FEED_FRESH}
    book.update(overrides)
    return json.dumps({k: v for k, v in book.items() if v is not None}).encode("utf-8")


def _feed(blob=None, *, calendar_loader=None, **reader_kwargs):
    reader = _FakeReader(blob, **reader_kwargs)
    decision = runner._load_sibling("ibkr_decision")
    loader = calendar_loader or (lambda: WeekdayCalendar(range_error=decision.CalendarRangeError))
    result = runner.load_published_portfolio(
        Path("."),
        _FEED_NOW,
        reader_factory=lambda repo, remote, branch: reader,
        calendar_loader=loader,
    )
    return result, reader


@pytest.mark.unit
class TestPublishedFeed:
    def test_published_valid_snapshot_is_used(self):
        position = {"ticker": "AAPL", "quantity": 1, "average_price": 100.0}
        (portfolio, note), reader = _feed(_feed_blob(positions=[position]))
        assert isinstance(portfolio, PortfolioContext)
        assert note == {
            "status": "used",
            "as_of": _FEED_FRESH,
            "cutoff": "2026-10-16T20:00:00+00:00",
            "sha": _FEED_SHA,
            "positions": 1,
        }
        assert reader.reads == ["portfolio.json"]

    def test_published_note_carries_no_amounts(self):
        (_, note), _ = _feed(_feed_blob(cash=12345.67))
        assert "12345" not in json.dumps(note)

    @pytest.mark.parametrize(
        ("kwargs", "reason"),
        [
            pytest.param({"fetch_error": "unavailable"}, "branch-unavailable", id="branch"),
            pytest.param({"read_error": "missing"}, "file-missing", id="missing"),
            pytest.param({"blob": b"x" * 1_000_001}, "too-large", id="large"),
            pytest.param({"blob": b"{not json"}, "invalid-json", id="json"),
            pytest.param({"blob": b"\xff\xfe"}, "invalid-json", id="utf8"),
            pytest.param({"blob": b'{"cash": "many"}'}, "invalid-schema", id="schema"),
            pytest.param({"blob": _feed_blob(as_of=None)}, "as-of-missing", id="no-as-of"),
            pytest.param({"blob": _feed_blob(as_of="yesterday")}, "as-of-invalid", id="bad-as-of"),
            pytest.param(
                {"blob": _feed_blob(as_of="2026-10-19T21:00:00")}, "as-of-invalid", id="naive"
            ),
            pytest.param(
                {"blob": _feed_blob(as_of="2026-10-20T07:00:00+00:00")},
                "as-of-in-future",
                id="future",
            ),
            pytest.param(
                {"blob": _feed_blob(as_of="2026-10-15T21:00:00+00:00")}, "stale", id="stale"
            ),
            pytest.param(
                {"blob": _feed_blob(as_of="2026-10-16T20:00:00+00:00")}, "stale", id="at-cutoff"
            ),
        ],
    )
    def test_published_problem_skips_with_reason(self, kwargs, reason):
        paperlog = runner._load_sibling("ibkr_paperlog")
        kwargs = dict(kwargs)
        if kwargs.get("fetch_error") == "unavailable":
            kwargs["fetch_error"] = paperlog.PaperLogUnavailable("no branch")
        if kwargs.get("read_error") == "missing":
            kwargs["read_error"] = paperlog.BlobMissing("portfolio.json")
        (portfolio, note), _ = _feed(**kwargs)
        assert portfolio is None
        assert note["status"] == "skipped"
        assert note["reason"] == reason

    def test_published_missing_calendar_package_skips(self):
        def loader():
            raise ImportError("exchange_calendars")

        (portfolio, note), _ = _feed(_feed_blob(), calendar_loader=loader)
        assert portfolio is None
        assert note["reason"] == "calendar-unavailable"

    def test_published_calendar_range_error_skips(self):
        decision = runner._load_sibling("ibkr_decision")

        def loader():
            raise decision.CalendarRangeError("out of range")

        (_, note), _ = _feed(_feed_blob(), calendar_loader=loader)
        assert note["reason"] == "calendar-unavailable"

    def test_published_unexpected_error_skips(self):
        (portfolio, note), _ = _feed(read_error=RuntimeError("boom"))
        assert portfolio is None
        assert note["reason"] == "unexpected-error"
        assert "RuntimeError" in note["detail"]


def _feed_main(monkeypatch, tmp_path, graph, result, extra_args=()):
    calls = []

    def fake(repo, now, **kwargs):
        calls.append(repo)
        return result

    monkeypatch.setattr(runner, "load_published_portfolio", fake)
    args = ("--portfolio-from-published", *extra_args)
    return _run_main(monkeypatch, tmp_path, graph, extra_args=args), calls


@pytest.mark.unit
class TestPublishedFeedMain:
    def test_published_feed_used_reaches_propagate_and_summary(self, monkeypatch, tmp_path):
        book = PortfolioContext(cash=5.0, currency="EUR", positions=[])
        note = {"status": "used", "as_of": _FEED_FRESH, "cutoff": "c", "sha": "s", "positions": 0}
        graph = _FakeGraph()
        code, calls = _feed_main(monkeypatch, tmp_path, graph, (book, note))
        assert code == runner.EXIT_OK
        assert len(calls) == 1
        assert graph.portfolios == [book]
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["portfolio_feed"] == note
        assert summary["schema_version"] == 1

    def test_published_feed_skipped_runs_like_today(self, monkeypatch, tmp_path):
        note = {"status": "skipped", "reason": "stale", "detail": ""}
        graph = _FakeGraph()
        code, _ = _feed_main(monkeypatch, tmp_path, graph, (None, note))
        assert code == runner.EXIT_OK
        assert graph.portfolios == ["<absent>"]
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["portfolio_feed"]["reason"] == "stale"

    def test_published_without_flag_has_no_feed_key_and_no_read(self, monkeypatch, tmp_path):
        def boom(*args, **kwargs):
            raise AssertionError("must not be called")

        monkeypatch.setattr(runner, "load_published_portfolio", boom)
        graph = _FakeGraph()
        assert _run_main(monkeypatch, tmp_path, graph) == runner.EXIT_OK
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert "portfolio_feed" not in summary

    def test_published_conflicts_with_local_portfolio(self, monkeypatch, tmp_path):
        path = _portfolio_file(tmp_path, _book())
        graph = _FakeGraph()
        code, calls = _feed_main(
            monkeypatch, tmp_path, graph, (None, {}), extra_args=("--portfolio", str(path))
        )
        assert code == runner.EXIT_CONFIG
        assert calls == []
        assert graph.calls == []

    def test_published_preflight_makes_no_read(self, monkeypatch, tmp_path):
        graph = _FakeGraph()
        _, calls = _feed_main(monkeypatch, tmp_path, graph, (None, {}), extra_args=("--preflight",))
        assert calls == []
