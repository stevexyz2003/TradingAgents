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


# --- build_rows ----------------------------------------------------------------------------

BLOCKS = {"AAPL": 1, "MSFT": 1, "NVDA": 1}
SHA = "71df89df8a078acdcea92f966c10332086f6cf43"


def _rows(decisions, records):
    ledger = report.read_ledger(_blob(records))
    return report.build_rows(decisions, ledger, block_qty_of=BLOCKS.get)


def _dec(date: str, ticker: str, rating: str) -> report.Decision:
    return report.Decision(date, ticker, rating, True, None, None, None, None)


def _intent(seq: int, key: str, *, rating="Overweight", side="BUY", qty=1, gap=False) -> dict:
    date, ticker = key.split("|")
    return _rec(
        seq,
        "intent",
        decision_key=key,
        ticker=ticker,
        trade_date=date,
        rating=rating,
        paper_log_sha=SHA,
        side=side,
        quantity=qty,
        con_id=265598,
        order_ref="ref",
        weekend_gap=gap,
        rating_source="engine",
    )


def _fill(seq: int, key: str, exec_id: str | None, qty: float, price: float, side="BUY") -> dict:
    fields = {"decision_key": key, "side": side, "filled_qty": qty, "price": price}
    if exec_id:
        fields["exec_id"] = exec_id
    return _rec(seq, "filled", **fields)


def _one(decision, records):
    rows, extra = _rows([decision], records)
    assert extra == []
    return rows[0]


def test_join_first_live_order_real_shape():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Hold"),
        [
            _intent(1, key),
            _rec(2, "placed", decision_key=key),
            _fill(3, key, "0001.01", 1, 270.5),
            _rec(4, "alarm", decision_key=key, state="post-order-mismatch", fills_booked=True),
            _rec(5, "run_end"),
        ],
    )
    assert row.state == "filled"
    assert row.ledger_rating == "Overweight"
    assert (row.target, row.held_before, row.held_after) == (1, 0, 1)
    assert (row.order_qty, row.filled_qty, row.avg_price, row.deviation) == (1, 1, 270.5, 0)
    assert any(
        "ledger rating Overweight != log rating Hold" in n and "71df89d" in n for n in row.notes
    )
    assert "alarm: post-order-mismatch" in row.notes


def test_join_hold_without_order():
    key = "2026-10-09|AAPL"
    row = _one(
        _dec("2026-10-09", "AAPL", "Hold"),
        [
            _rec(
                1,
                "skipped",
                decision_key=key,
                reason="hold",
                state="skipped-hold",
                weekend_gap=True,
            )
        ],
    )
    assert row.state == "skipped-hold"
    assert row.target is None and row.held_before is None and row.held_after is None
    assert row.weekend_gap is True
    assert "no intent: target/held not recorded (D-20)" in row.notes


def test_join_no_run():
    row = _one(_dec("2026-10-09", "MSFT", "Buy"), [])
    assert row.state == report.NO_RUN
    assert row.filled_qty is None and row.order_qty is None and row.target is None


def test_join_fill_timeout():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [
            _intent(1, key),
            _rec(2, "placed", decision_key=key),
            _rec(3, "alarm", decision_key=key, state="fill-timeout"),
        ],
    )
    assert row.state == "fill-timeout"
    assert row.filled_qty == 0


def test_join_place_rejected():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _rec(2, "rejected", decision_key=key, state="place-rejected")],
    )
    assert row.state == "place-rejected"
    assert row.filled_qty == 0


def test_join_resolved():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _rec(2, "resolved", decision_key=key, outcome="never_sent", note="n")],
    )
    assert row.state == "never_sent"


def test_join_correction_highest_wins():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"),
        [_intent(1, key), _fill(2, key, "0001.01", 1, 10), _fill(3, key, "0001.02", 1, 11)],
    )
    assert row.filled_qty == 1
    assert row.avg_price == 11


def test_join_aggregate_row_counts_once():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Overweight"), [_intent(1, key), _fill(2, key, None, 1, 10)]
    )
    assert row.filled_qty == 1
    assert row.avg_price == 10


def test_join_partial_average_price():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Buy"),
        [
            _intent(1, key, rating="Buy", qty=2),
            _fill(2, key, "0001.01", 1, 10),
            _fill(3, key, "0002.01", 1, 12),
        ],
    )
    assert row.filled_qty == 2
    assert row.avg_price == 11
    assert (row.target, row.held_before, row.held_after, row.deviation) == (2, 0, 2, 0)


def test_join_sell_ladder():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Sell"),
        [
            _intent(1, key, rating="Sell", side="SELL", qty=1),
            _fill(2, key, "0001.01", 1, 10, side="SELL"),
        ],
    )
    assert (row.target, row.held_before, row.held_after, row.deviation) == (0, 1, 0, 0)


def test_join_implausible_block_size():
    key = "2026-10-16|AAPL"
    row = _one(
        _dec("2026-10-16", "AAPL", "Underweight"),
        [_intent(1, key, rating="Underweight", side="BUY", qty=1)],
    )
    assert row.held_before is None and row.held_after is None and row.deviation is None
    assert any("block size changed?" in n for n in row.notes)


def test_join_unknown_ticker():
    key = "2026-10-16|ZZZZ"
    row = _one(_dec("2026-10-16", "ZZZZ", "Overweight"), [_intent(1, key)])
    assert row.target is None and row.deviation is None
    assert any("ZZZZ" in n for n in row.notes)


def test_join_last_skip_wins():
    key = "2026-10-09|AAPL"
    row = _one(
        _dec("2026-10-09", "AAPL", "Hold"),
        [
            _rec(1, "skipped", decision_key=key, reason="stale", state="stale-source"),
            _rec(2, "skipped", decision_key=key, reason="hold", state="skipped-hold"),
        ],
    )
    assert row.state == "skipped-hold"


def test_join_ledger_only_keys_are_reported():
    rows, extra = _rows(
        [_dec("2026-10-09", "AAPL", "Hold")],
        [_rec(1, "skipped", decision_key="2026-10-02|NVDA", reason="hold", state="skipped-hold")],
    )
    assert [r.key for r in rows] == ["2026-10-09|AAPL"]
    assert extra == ["2026-10-02|NVDA"]
