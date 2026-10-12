"""Unit tests for the library-free decision logic (scripts/ibkr_decision.py)."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_decision.py"
_spec = importlib.util.spec_from_file_location("ibkr_decision", _SCRIPT)
dec = importlib.util.module_from_spec(_spec)
sys.modules["ibkr_decision"] = dec
_spec.loader.exec_module(dec)


def _summary_text(runs=None, **over):
    body = {
        "schema_version": 1,
        "trade_date": "2026-10-09",
        "status": "ok",
        "runs": runs
        if runs is not None
        else [{"ticker": "AAPL", "status": "ok", "signal": "Buy", "report": "x"}],
    }
    body.update(over)
    return json.dumps(body)


def _entry(ticker="AAPL", date="2026-10-09", rating="Buy"):
    return {"date": date, "ticker": ticker, "rating": rating, "pending": True}


def _summary(ticker="AAPL", status="ok", signal="Buy"):
    runs = [{"ticker": ticker, "status": status, "signal": signal}]
    return dec.read_summary(_summary_text(runs=runs))


# --- schema ---------------------------------------------------------------------------


def test_schema_version_other_than_one_raises_schema_error():
    with pytest.raises(dec.SummarySchemaError):
        dec.read_summary(_summary_text(schema_version=2))


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps({"schema_version": 1, "trade_date": "2026-10-09", "status": "ok"}),
        _summary_text(runs=[{"ticker": "AAPL", "status": 5, "signal": "Buy"}]),
        json.dumps({"schema_version": 1, "status": "ok", "runs": []}),
        _summary_text(schema_version=True),
        _summary_text(trade_date="09.10.2026"),
        _summary_text(runs=[{"ticker": "AAPL", "status": "weird", "signal": None}]),
    ],
)
def test_schema_contract_violations_raise(text):
    with pytest.raises(dec.SummaryContractError):
        dec.read_summary(text)


def test_schema_extra_fields_are_tolerated_and_report_is_not_exposed():
    text = _summary_text(extra=1, runs=[{"ticker": "AAPL", "status": "ok", "signal": "Buy", "x": 1, "report": "r"}])
    summary = dec.read_summary(text)
    assert summary.runs[0].ticker == "AAPL"
    assert not hasattr(summary.runs[0], "report")


# --- log entries ----------------------------------------------------------------------


def test_log_entries_latest_per_ticker_wins():
    a1, m, a2 = _entry(date="2026-10-08"), _entry("MSFT", "2026-10-08"), _entry(date="2026-10-09")
    assert dec.latest_entries([a1, m, a2]) == {"AAPL": a2, "MSFT": m}


def test_log_entries_roundtrip_with_memory_log(tmp_path):
    from tradingagents.memory.log import TradingMemoryLog

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "log.md")})
    log.store_decision("AAPL", "2026-10-09", "text", rating="Buy")
    latest = dec.latest_entries(log.load_entries())
    assert latest["AAPL"]["date"] == "2026-10-09"
    assert latest["AAPL"]["rating"] == "Buy"


def test_log_entries_ratings_mirror_rating_module():
    from tradingagents.agents import rating

    assert tuple(rating.RATINGS_5_TIER) == dec.RATINGS_5
    assert dec.REVIEW == rating.RATING_REVIEW


# --- preconditions --------------------------------------------------------------------


def test_preconditions_hold_is_skipped():
    v = dec.evaluate_decision(_entry(rating="Hold"), _summary(signal="Hold"))
    assert v.state == "skipped-hold"
    assert v.detail == "skipped: hold"


def test_preconditions_review():
    v = dec.evaluate_decision(_entry(rating="REVIEW"), _summary(signal="REVIEW"))
    assert v.state == "rating-review"


def test_preconditions_run_not_ok():
    v = dec.evaluate_decision(_entry(), _summary(status="failed", signal=None))
    assert v.state == "run-not-ok"


def test_preconditions_signal_null():
    v = dec.evaluate_decision(_entry(), _summary(signal=None))
    assert v.state == "signal-null"


def test_preconditions_summary_missing():
    assert dec.evaluate_decision(_entry(), None).state == "summary-missing"
    assert dec.evaluate_decision(_entry(), _summary(ticker="MSFT")).state == "summary-missing"


def test_preconditions_invalid_trade_date():
    assert dec.evaluate_decision(_entry(date="10/09/2026"), _summary()).state == "invalid-trade-date"


def test_preconditions_executable():
    v = dec.evaluate_decision(_entry(), _summary())
    assert v.state == dec.EXECUTABLE
    assert str(v.trade_date) == "2026-10-09"


def test_divergence_log_version_wins():
    v = dec.evaluate_decision(_entry(rating="Buy"), _summary(signal="Sell"))
    assert v.state == "signal-divergence"
    assert v.rating == "Buy"
    assert "log=Buy summary=Sell" in v.detail


def test_preconditions_newer_summary_state():
    newer = dec.read_summary(
        _summary_text(trade_date="2026-10-10", runs=[{"ticker": "AAPL", "status": "failed", "signal": None}])
    )
    assert dec.newer_summary_state(dec.parse_trade_date("2026-10-09"), newer, "AAPL") == "run-not-ok"
    assert dec.newer_summary_state(dec.parse_trade_date("2026-10-09"), newer, "MSFT") is None


# --- exit table -----------------------------------------------------------------------


def test_exit_table_values_and_coverage():
    t = dec.EXIT_BY_STATE
    assert t["skipped-hold"] == 2 and t["preview-empty"] == 5
    assert t["summary-schema"] == 1 and t["within-tolerance"] == 0
    assert set(t) == set(dec.ALL_STATES)
    assert dec.worst_exit(["within-tolerance", "skipped-hold", "halted"]) == 5
    assert dec.worst_exit(["summary-schema", "halted"]) == 1


def test_no_forbidden_literals_in_module():
    src = _SCRIPT.read_text(encoding="utf-8")
    assert '"report"' not in src
    assert not re.search(r"13:30|14:30|09:30|16:00|datetime\.now|date\.today|time\.time\(", src)
    assert not re.search(r"reqMktData|reqTickers|lmtPrice|marketPrice", src)


# --- order plan -----------------------------------------------------------------------


def _plan(rating, held=0, open_orders=0, block=1):
    return dec.plan_order(rating, held_qty=held, open_orders=open_orders, block_qty=block)


def test_plan_hold_never_orders():
    assert _plan("Hold", held=3).state == "skipped-hold"


def test_plan_buy_from_flat():
    p = _plan("Buy")
    assert (p.state, p.side, p.quantity, p.target) == ("intent", "BUY", 2, 2)


def test_tolerance_band():
    assert _plan("Overweight", held=1).state == "within-tolerance"
    assert _plan("Buy", held=2).state == "within-tolerance"
    assert _plan("Buy", held=3, block=2).state == "within-tolerance"
    p = _plan("Buy", held=2, block=2)
    assert (p.side, p.quantity) == ("BUY", 2)
    p = _plan("Buy", held=1, block=2)
    assert (p.side, p.quantity) == ("BUY", 3)


def test_long_only_noop_and_sells():
    assert _plan("Sell").state == "long-only-noop"
    assert _plan("Underweight").state == "long-only-noop"
    p = _plan("Sell", held=2)
    assert (p.side, p.quantity) == ("SELL", 2)
    p = _plan("Overweight", held=3)
    assert (p.side, p.quantity) == ("SELL", 2)


def test_open_order_is_foreign():
    assert _plan("Buy", open_orders=1).state == "foreign-open-order"


def test_plan_fractional_position():
    assert _plan("Buy", held=1.5).state == "fractional-position"


def test_plan_bad_block_qty():
    with pytest.raises(ValueError):
        _plan("Buy", block=0)


def test_long_only_property_never_oversell():
    for rating in dec.RATINGS_5:
        for held in range(6):
            for block in (1, 2, 3):
                p = _plan(rating, held=held, block=block)
                assert p.target >= 0
                if p.side == "SELL":
                    assert p.quantity <= held


# --- preview verdict ------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402


@dataclass
class _Preview:
    state: str = "OK"
    init_margin_change: float | None = 500.0
    maint_margin_change: float | None = 400.0
    commission: float | None = 1.0
    commission_currency: str = "USD"
    warning_text: str = ""
    errors: tuple = ()
    effective_tif: str | None = "DAY"
    sent_tif: str = "DAY"


def _judge(p, funds=1000.0, fc="EUR", ac="EUR"):
    return dec.judge_preview(p, available_funds=funds, funds_currency=fc, account_currency=ac)


def test_halted_and_special_states():
    assert _judge(_Preview(state="HALTED")).state == "halted"
    assert _judge(_Preview(state="TIF_OVERRIDDEN")).state == "tif-overridden"
    assert _judge(_Preview(state="READ_ONLY_API")).state == "preview-read-only"
    assert _judge(_Preview(state="WHATEVER")).state == "preview-empty"


def test_preview_empty_states():
    assert _judge(_Preview(state="EMPTY")).state == "preview-empty"
    assert _judge(_Preview(init_margin_change=None)).state == "preview-empty"
    assert _judge(_Preview(commission=None)).state == "preview-empty"
    assert _judge(_Preview(commission_currency="")).state == "preview-empty"
    assert _judge(_Preview(maint_margin_change=None)).state == "preview-empty"


def test_preview_rejected_reason_from_errors():
    v = _judge(_Preview(state="EMPTY", errors=((201, "Order rejected - reason: x"),)))
    assert v.state == "preview-rejected"
    assert "201: Order rejected - reason: x" in v.reject_reason
    assert v.reject_source == "request-errors"
    assert _judge(_Preview(errors=((1, "e"),))).state == "preview-rejected"


def test_preview_tif_checks():
    assert _judge(_Preview(effective_tif=None)).state == "tif-unconfirmed"
    assert _judge(_Preview(effective_tif="GTC")).state == "tif-overridden"


def test_budget_and_currency():
    assert _judge(_Preview(), fc="USD").state == "currency-mismatch"
    assert _judge(_Preview(init_margin_change=997.14), funds=997.14).state == "over-budget"
    v = _judge(_Preview(), funds=1000.0)
    assert v.state == "preview-ok" and v.reject_reason == ""
    assert _judge(_Preview(warning_text="careful")).state == "preview-ok"


# --- freshness / calendar_conflict (plan 04-06) -----------------------------------------

from datetime import date, datetime, timezone  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calendar_stub import WeekdayCalendar  # noqa: E402


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


@pytest.fixture(params=["xnys", "stub"])
def cal(request):
    if request.param == "xnys":
        pytest.importorskip("exchange_calendars")
        return dec.load_xnys_calendar()
    return WeekdayCalendar(holidays={date(2026, 9, 7)})


_FRESHNESS_CASES = [
    # name, trade_date, now, state, execution_day, in_session_day, gap_days, weekend_gap, closed
    ("tue_run_mon_decision", date(2026, 10, 5), _utc(2026, 10, 6, 15), "fresh",
     date(2026, 10, 6), True, 1, False, ()),
    ("sat_run_decision_on_monday", date(2026, 10, 9), _utc(2026, 10, 12, 15), "fresh",
     date(2026, 10, 12), True, 3, True, ()),
    ("wed_missed_thu_catchup", date(2026, 10, 6), _utc(2026, 10, 8, 15), "stale-decision",
     date(2026, 10, 8), True, None, None, (date(2026, 10, 7),)),
    ("labor_day_monday_tuesday_run", date(2026, 9, 7), _utc(2026, 9, 8, 15), "fresh",
     date(2026, 9, 8), True, 1, False, ()),
    ("weekend_run", date(2026, 10, 9), _utc(2026, 10, 10, 10), "fresh",
     date(2026, 10, 12), False, 3, True, ()),
    ("evening_after_close", date(2026, 10, 9), _utc(2026, 10, 12, 23), "stale-decision",
     date(2026, 10, 13), False, None, None, (date(2026, 10, 12),)),
    ("same_day_is_future", date(2026, 10, 12), _utc(2026, 10, 12, 15), "future-decision",
     date(2026, 10, 12), True, None, None, ()),
]


@pytest.mark.parametrize("case", _FRESHNESS_CASES, ids=[c[0] for c in _FRESHNESS_CASES])
def test_freshness_cases(cal, case):
    _, trade_date, now, state, exec_day, in_day, gap, weekend, closed = case
    result = dec.freshness(trade_date, now, cal)
    assert result.state == state
    assert result.execution_day == exec_day
    assert result.in_session_day is in_day
    assert result.closed_sessions == closed
    if gap is not None:
        assert result.gap_days == gap
        assert result.weekend_gap is weekend


def test_freshness_stale_detail_names_the_closed_session(cal):
    result = dec.freshness(date(2026, 10, 6), _utc(2026, 10, 8, 15), cal)
    assert "2026-10-07" in result.detail


def test_freshness_outside_calendar_range_is_stale_not_a_crash(cal):
    result = dec.freshness(date(1990, 1, 2), _utc(2026, 10, 12, 15), cal)
    assert result.state == "stale-decision"
    assert "outside the calendar range" in result.detail


def test_freshness_naive_now_raises(cal):
    with pytest.raises(ValueError):
        dec.freshness(date(2026, 10, 9), datetime(2026, 10, 12, 15), cal)


_CONFLICT_CASES = [
    (_utc(2026, 10, 12, 15), True, False),
    (_utc(2026, 10, 12, 15), False, True),
    (_utc(2026, 9, 7, 15), True, True),
    (_utc(2026, 10, 10, 15), False, False),
    (_utc(2026, 10, 12, 15), None, False),
    # 02:00 UTC on the 13th is still Oct 12 in New York
    (_utc(2026, 10, 13, 2), True, False),
    (_utc(2026, 10, 13, 2), False, True),
]


@pytest.mark.parametrize(("now", "session_day", "expected"), _CONFLICT_CASES)
def test_calendar_conflict_cases(cal, now, session_day, expected):
    assert dec.calendar_conflict(now, cal, session_day) is expected


def test_calendar_conflict_naive_now_raises(cal):
    with pytest.raises(ValueError):
        dec.calendar_conflict(datetime(2026, 10, 12, 15), cal, True)
