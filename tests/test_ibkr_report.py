"""Soll/Ist report data layer: decision-log parsing, ledger reading, the per-decision join."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_LOG = ROOT / "tests" / "fixtures" / "paper_log_71df89d" / "decision-log.md"
SEP = "\n\n<!-- ENTRY_END -->\n\n"

_spec = importlib.util.spec_from_file_location("ibkr_report", ROOT / "scripts" / "ibkr_report.py")
report = importlib.util.module_from_spec(_spec)
sys.modules["ibkr_report"] = report
_spec.loader.exec_module(report)


def _entry(date: str, ticker: str, rating: str, tag: str = "pending") -> str:
    return f"[{date} | {ticker} | {rating} | {tag}]\n\nDECISION:\n**Rating**: {rating}"


def _log(*entries: str) -> str:
    return SEP.join(entries) + SEP


# --- parse_decisions -----------------------------------------------------------------------


def test_dedup_first_version_wins():
    """SC5: the triple 2026-10-09 | AAPL (written raw) yields one decision, the first version."""
    text = _log(
        _entry("2026-10-09", "AAPL", "Hold"),
        _entry("2026-10-09", "MSFT", "Buy"),
        _entry("2026-10-09", "AAPL", "Buy"),
        _entry("2026-10-09", "AAPL", "Sell"),
    )
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert [d.key for d in decisions] == ["2026-10-09|AAPL", "2026-10-09|MSFT"]
    assert decisions[0].rating == "Hold"
    assert duplicates == 2
    assert unparsed == 0


def test_parse_real_fixture_smoke():
    """Smoke only: the real bytes parse; this fixture holds each key once, so no dedup proof."""
    text = FIXTURE_LOG.read_bytes().decode("utf-8")
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert decisions
    keys = [d.key for d in decisions]
    assert len(keys) == len(set(keys))
    assert unparsed == 0
    assert duplicates == 0


def test_parse_counts_unparsable_blocks():
    text = _log(_entry("2026-10-09", "AAPL", "Hold"), "[2026-10-09 | MSFT | Buy]\n\nDECISION:\nx")
    decisions, unparsed, duplicates = report.parse_decisions(text)
    assert len(decisions) == 1
    assert unparsed == 1
    assert duplicates == 0


def test_parse_reads_settled_tag():
    text = _log(
        "[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]\n\nDECISION:\nx"
    )
    (decision,), _, _ = report.parse_decisions(text)
    assert decision.pending is False
    assert decision.raw == "+2.0%"
    assert decision.alpha == "+4.0%"
    assert decision.holding == "5d"
    assert decision.resolved == "2026-10-16"


def test_key_separator_matches_guards():
    guards = report._load("ibkr_guards", "ibkr_guards.py")
    assert report.KEY_SEPARATOR == guards.DECISION_KEY_SEPARATOR


# --- read_ledger ---------------------------------------------------------------------------


def _rec(seq: int, event: str, mode: str = "live", **fields) -> dict:
    return {
        "v": 1,
        "seq": seq,
        "ts": "2026-10-16T14:00:00+00:00",
        "run_id": "r1",
        "mode": mode,
        "event": event,
        **fields,
    }


def _blob(records: list[dict]) -> bytes:
    return b"".join((json.dumps(r) + "\n").encode("utf-8") for r in records)


def test_read_ledger_in_file_order():
    blob = _blob([_rec(1, "run_start"), _rec(2, "run_end")])
    assert [r["seq"] for r in report.read_ledger(blob)] == [1, 2]


def test_read_ledger_tolerates_torn_tail():
    blob = _blob([_rec(1, "run_start")]) + b'{"v":1,"seq":2,"ev'
    assert [r["seq"] for r in report.read_ledger(blob)] == [1]


def test_read_ledger_broken_middle_raises():
    good = _blob([_rec(1, "run_start")])
    blob = good + b"not json\n" + _blob([_rec(3, "run_end")])
    with pytest.raises(report._ledger().LedgerError):
        report.read_ledger(blob)


def test_read_ledger_rejects_dryrun_ledger():
    with pytest.raises(report._ledger().LedgerError):
        report.read_ledger(_blob([_rec(1, "run_start", mode="dryrun")]))
