"""Tests for the unattended daily paper run (scripts/daily_paper_run.py).

The runner is operational tooling for the scheduled fork job, so the parts
that decide *what* runs (tickers, trade date, budget, credentials) and *what
is persisted* (summary, index, archive) are covered without any network or
LLM access. The graph itself is stubbed.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingagents.budget import BudgetExceededError

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_paper_run.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("daily_paper_run", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


RATES = {
    "gpt-5.5": {"input": 5.0, "output": 40.0},
    "gpt-5.4-mini": {"input": 1.0, "output": 8.0},
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

    def propagate(self, ticker, trade_date, asset_type="stock"):
        self.calls.append((ticker, trade_date))
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
        from datetime import datetime, timezone

        now = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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


class TestCredentials:
    def test_openai_needs_its_key(self):
        assert runner.missing_credentials("openai", {}) == ["OPENAI_API_KEY"]

    def test_blank_key_counts_as_missing(self):
        assert runner.missing_credentials("openai", {"OPENAI_API_KEY": "  "}) == [
            "OPENAI_API_KEY"
        ]

    def test_present_key_satisfies_the_check(self):
        assert runner.missing_credentials("openai", {"OPENAI_API_KEY": "sk-x"}) == []

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
