"""Producer-consumer contract: summary.json from daily_paper_run.py vs ibkr_decision.read_summary."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tradingagents.default_config import DEFAULT_CONFIG

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("daily_paper_run")
dec = _load("ibkr_decision")

_RATES = {
    DEFAULT_CONFIG["deep_think_llm"]: {"input": 5.0, "output": 40.0},
    DEFAULT_CONFIG["quick_think_llm"]: {"input": 1.0, "output": 8.0},
}


class _FakeGraph:
    def __init__(self, signal="Buy"):
        self.signal = signal
        self.spend_tracker = type("T", (), {"tokens_in": 10, "tokens_out": 2, "cost": 0.1})()

    def propagate(self, ticker, trade_date, asset_type="stock", **kwargs):
        return {"final_trade_decision": f"**Rating**: {self.signal}"}, self.signal

    def save_reports(self, final_state, ticker, save_path=None):
        path = Path(save_path)
        path.mkdir(parents=True, exist_ok=True)
        report = path / "complete_report.md"
        report.write_text(f"# {ticker}\n", encoding="utf-8")
        return report


@pytest.fixture
def produced(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.TradingAgentsGraph",
        lambda config=None, **kwargs: _FakeGraph("Buy"),
    )
    rates = tmp_path / "rates.json"
    rates.write_text(json.dumps(_RATES), encoding="utf-8")
    runner.main(
        [
            "--tickers", "AAPL",
            "--date", "2026-08-20",
            "--max-cost", "1.0",
            "--rates", str(rates),
            "--out", str(tmp_path / "out"),
            "--state", str(tmp_path / "state"),
        ]
    )
    return json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))


def test_contract_schema_version_matches_producer():
    assert runner.SUMMARY_SCHEMA_VERSION == dec.SUMMARY_SCHEMA_VERSION


def test_contract_real_summary_is_accepted(produced):
    summary = dec.read_summary(json.dumps(produced))
    assert summary.trade_date == "2026-08-20"
    assert summary.runs[0].ticker == "AAPL"
    assert summary.runs[0].signal == "Buy"


def _drop_status(d):
    del d["status"]


def _rename_signal(d):
    d["runs"][0]["rig"] = d["runs"][0].pop("signal")


def _version_string(d):
    d["schema_version"] = "1"


def _runs_dict(d):
    d["runs"] = {"AAPL": d["runs"][0]}


@pytest.mark.parametrize("mutate", [_drop_status, _rename_signal, _version_string, _runs_dict])
def test_contract_breaking_change_fails(produced, mutate):
    mutate(produced)
    with pytest.raises(dec.SummaryContractError):
        dec.read_summary(json.dumps(produced))


def test_contract_extra_field_stays_green(produced):
    produced["new_top_level"] = 1
    produced["runs"][0]["new_run_field"] = [1]
    assert dec.read_summary(json.dumps(produced)).runs[0].ticker == "AAPL"


def test_contract_decision_log_roundtrip(tmp_path):
    from tradingagents.memory.log import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "log.md")})
    log.store_decision("AAPL", "2026-10-09", "...", rating="Buy")
    latest = dec.latest_entries(log.load_entries())
    assert latest["AAPL"]["date"] == "2026-10-09" and latest["AAPL"]["rating"] == "Buy"
