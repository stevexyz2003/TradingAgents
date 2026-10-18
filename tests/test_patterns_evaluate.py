"""Pattern evaluation: Wilson, MIN_N, ties, independence, conventions, import ban."""

import ast
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingagents.patterns import evaluate as ev
from tradingagents.patterns.evaluate import (
    MIN_N,
    entry_convention,
    evaluate,
    load_log_entries,
    log_text_to_entries,
    wilson,
)

ROOT = Path(__file__).resolve().parents[1]
SEP = "\n\n<!-- ENTRY_END -->\n\n"


def _prices(n=300, start="2024-01-01", rising=True):
    dates = pd.bdate_range(start, periods=n)
    closes = np.arange(1, n + 1, dtype=float) if rising else np.arange(n, 0, -1, dtype=float)
    return pd.DataFrame({"Date": dates, "Close": closes + 100})


def _loader(frame=None):
    frame = _prices() if frame is None else frame
    return lambda ticker, as_of: frame


def _entry(date, rating="Overweight", raw="+1.0%", alpha="+1.0%", holding="5d",
           resolved="2025-01-01", ticker="AAPL", pending=False):
    return {
        "date": date, "ticker": ticker, "rating": rating, "pending": pending,
        "raw": None if pending else raw, "alpha": None if pending else alpha,
        "holding": None if pending else holding, "resolved": None if pending else resolved,
        "decision": "", "reflection": "",
    }


def _cell(report, pattern, side, mode):
    return next(c for c in report.cells if (c.pattern, c.side, c.mode) == (pattern, side, mode))


def test_wilson_values():
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 20)
    assert (round(lo, 3), round(hi, 3)) == (0.299, 0.701)
    assert wilson(20, 20)[1] == 1.0


def test_insufficient_below_min_n_reports_n_but_no_rate():
    report = evaluate([_entry("2024-12-02")], _loader())
    cell = _cell(report, "breakout_20", 1, "engine")
    assert cell.n_all == 1 and cell.n_independent == 1
    assert cell.status == "insufficient"
    assert cell.hit_rate_alpha is None and cell.ci_alpha is None


def test_ties_tracked_separately_for_alpha_and_raw():
    entries = [
        _entry("2024-12-02", alpha="+0.0%", raw="+1.0%"),
        _entry("2024-12-16", alpha="-0.0%", raw="+1.0%"),
        _entry("2024-12-23", alpha="+1.0%", raw="-0.0%"),
        _entry("2025-01-06", alpha="-1.0%", raw="+1.0%"),
    ]
    report = evaluate(entries, _loader(), min_n=1)
    cell = _cell(report, "breakout_20", 1, "engine")
    assert (cell.ties_alpha, cell.ties_raw) == (2, 1)
    assert (cell.den_alpha, cell.den_raw) == (2, 3)
    assert (cell.hits_alpha, cell.hits_raw) == (1, 3)
    assert cell.hit_rate_alpha == 0.5 and cell.hit_rate_raw == 1.0
    assert cell.status == "ok"


def test_raw_hit_and_alpha_miss_for_same_entry():
    report = evaluate([_entry("2024-12-02", raw="+1.0%", alpha="-0.5%")], _loader(), min_n=1)
    cell = _cell(report, "breakout_20", 1, "engine")
    assert cell.hit_rate_raw == 1.0 and cell.hit_rate_alpha == 0.0


def test_overlapping_daily_entries_reduce_independent_n():
    days = pd.bdate_range("2024-12-02", periods=10)
    entries = [_entry(str(d.date())) for d in days]
    report = evaluate(entries, _loader(), min_n=1)
    cell = _cell(report, "breakout_20", 1, "engine")
    assert cell.n_all == 10 and cell.n_independent == 2 and cell.n_independent < cell.n_all


def test_convention_flag():
    assert entry_convention("2026-10-09", "2026-10-16", 5) == "decision_close"
    assert entry_convention("2026-10-09", "2026-10-19", 5) == "next_close"
    assert entry_convention("2026-10-12", "2026-10-20", 5) == "next_close"
    assert entry_convention("2026-10-09", "2026-11-30", 5) == "unknown"
    assert entry_convention("2026-10-09", None, 5) == "unknown"
    report = evaluate(
        [_entry("2026-10-09", rating="Hold", resolved="2026-10-16")], _loader(), min_n=1
    )
    assert report.conventions == {"decision_close": 1}
    assert len(report.flagged_entries) == 1 and "2026-10-09" in report.flagged_entries[0]


def test_exclusions_and_counts_and_hold_modes():
    entries = [
        _entry("2024-12-02", rating="REVIEW"),
        _entry("2024-12-02", ticker="MSFT", alpha="n/a"),
        _entry("2024-12-03", pending=True),
        _entry("2024-12-02", rating="Hold", ticker="NVDA", alpha="+2.0%"),
    ]
    report = evaluate(entries, _loader(), min_n=1)
    assert report.n_entries == 4 and report.n_pending == 1
    assert report.n_resolved == 3
    assert report.n_review_excluded == 1 and report.n_unparseable == 1
    assert _cell(report, "breakout_20", 1, "engine").n_all == 0
    pattern_cell = _cell(report, "breakout_20", 1, "pattern")
    assert pattern_cell.n_all == 1 and pattern_cell.hit_rate_alpha == 1.0


def test_missing_prices_are_loud_not_zero():
    def loader(ticker, as_of):
        raise RuntimeError("offline")

    report = evaluate([_entry("2024-12-02")], loader, min_n=1)
    assert report.missing_price_tickers == ["AAPL"]
    assert any("no price data for AAPL" in w for w in report.warnings)
    assert report.entry_states[0]["patterns"]["breakout_20"] is None
    assert _cell(report, "breakout_20", 1, "engine").n_all == 0


def test_unsafe_ticker_is_skipped():
    report = evaluate([_entry("2024-12-02", ticker="../x")], _loader(), min_n=1)
    assert any("unsafe ticker" in w for w in report.warnings)


def _fixture_log() -> str:
    blocks = []
    days = pd.bdate_range("2026-10-09", periods=6)
    n = 0
    for t in ("AAPL", "MSFT", "NVDA"):
        for d in days[: 5 if t != "AAPL" else 6]:
            n += 1
            rating = "Overweight" if n in (3, 9, 15) else "Hold"
            blocks.append(f"[{d.date()} | {t} | {rating} | pending]\n\nDECISION:\ntext {n}")
    assert len(blocks) == 16
    blocks[0] = (
        "[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]\n\n"
        "DECISION:\ntext 1\n\nREFLECTION:\nok"
    )
    return SEP.join(blocks) + SEP


def test_fixture_log_round_trip(tmp_path):
    path = tmp_path / "decision-log.md"
    path.write_text(_fixture_log(), encoding="utf-8")
    entries = load_log_entries(path)
    assert len(entries) == 16
    assert log_text_to_entries(_fixture_log()) == entries
    report = evaluate(entries, _loader(_prices(start="2025-06-01", n=400)), min_n=MIN_N)
    assert report.n_entries == 16 and report.n_pending == 15 and report.n_resolved == 1
    assert report.conventions == {"decision_close": 1}
    assert all(c.status == "insufficient" for c in report.cells)
    assert all(c.hit_rate_alpha is None for c in report.cells)


_BANNED = (
    "tradingagents.graph",
    "tradingagents.memory.settlement",
    "tradingagents.memory.reflection",
    "tradingagents.llm_clients",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_google_genai",
)


def test_import_ban_ast():
    for path in (ROOT / "tradingagents" / "patterns").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not any(name == b or name.startswith(b + ".") for b in _BANNED), (
                    path, name)


def test_import_ban_runtime():
    code = (
        "import sys, tradingagents.patterns.evaluate;"
        "bad=[m for m in ('tradingagents.graph','tradingagents.memory.settlement',"
        "'tradingagents.memory.reflection') if m in sys.modules];"
        "sys.exit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_markdown_mentions_insufficient():
    report = evaluate([_entry("2024-12-02")], _loader())
    assert "insufficient" in ev.render_markdown(report)
    assert ev.report_to_dict(report)["n_entries"] == 1


@pytest.mark.parametrize("value,expected", [("+2.0%", 0.02), ("-0.0%", -0.0), ("x", None)])
def test_parse_pct(value, expected):
    assert ev.parse_pct(value) == expected
