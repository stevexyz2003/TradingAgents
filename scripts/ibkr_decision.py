"""Library-free decision logic for the phase-4 preview: no client library, no tradingagents import, no clock.

Everything here is a pure function or a frozen value, so the decision chain can be
tested without a gateway, without git and without a clock:

* the consumer contract for ``summary.json`` (REQ-IBKR-14, -18),
* the choice of the newest log entry per ticker (REQ-IBKR-13),
* the preconditions including the log-vs-summary divergence (REQ-IBKR-16, -17),
* the target calculation with tolerance band and the long-only invariant
  (REQ-IBKR-21, -23, -24),
* the verdict over a what-if result including the budget check (REQ-IBKR-38, -61, -70).

Every reason to stop is its own named state; ``EXIT_BY_STATE`` is the one table
that maps a state to a process exit code.
"""

from __future__ import annotations

import importlib
import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import Protocol
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# --- named states ------------------------------------------------------------------------

SKIPPED_HOLD = "skipped-hold"
RATING_REVIEW_STATE = "rating-review"
RATING_JEV = "rating-jev"
RUN_NOT_OK = "run-not-ok"
SIGNAL_NULL = "signal-null"
SIGNAL_DIVERGENCE = "signal-divergence"
SUMMARY_MISSING = "summary-missing"
SUMMARY_SCHEMA = "summary-schema"
SUMMARY_CONTRACT = "summary-contract"
NO_DECISION = "no-decision"
LOG_MISSING_ENTRY = "log-missing-entry"
INVALID_TRADE_DATE = "invalid-trade-date"
LOG_FINDING = "log-finding"
PAPER_LOG_UNAVAILABLE = "paper-log-unavailable"
STALE_DECISION = "stale-decision"
FRESH = "fresh"
FUTURE_DECISION = "future-decision"
CALENDAR_CONFLICT = "calendar-conflict"
NOT_RESOLVED_YET = "not-resolved-yet"
FOREIGN_OPEN_ORDER = "foreign-open-order"
FRACTIONAL_POSITION = "fractional-position"
SHORT_POSITION = "short-position"
WITHIN_TOLERANCE = "within-tolerance"
LONG_ONLY_NOOP = "long-only-noop"
PREVIEW_OK = "preview-ok"
PREVIEW_EMPTY = "preview-empty"
PREVIEW_REJECTED = "preview-rejected"
PREVIEW_READ_ONLY = "preview-read-only"
TIF_OVERRIDDEN = "tif-overridden"
TIF_UNCONFIRMED = "tif-unconfirmed"
OVER_BUDGET = "over-budget"
CURRENCY_MISMATCH = "currency-mismatch"
#: Same string as ``ibkr_contracts.HALTED``; not imported, a test checks equality.
HALTED = "halted"
#: Intermediate state, not an end state: preconditions passed.
EXECUTABLE = "executable"
#: Intermediate state of ``plan_order``: an order intent exists.
INTENT = "intent"

ALL_STATES = frozenset(
    {
        SKIPPED_HOLD, RATING_REVIEW_STATE, RATING_JEV, RUN_NOT_OK, SIGNAL_NULL, SIGNAL_DIVERGENCE,
        SUMMARY_MISSING, SUMMARY_SCHEMA, SUMMARY_CONTRACT, NO_DECISION, LOG_MISSING_ENTRY,
        INVALID_TRADE_DATE, LOG_FINDING, PAPER_LOG_UNAVAILABLE, STALE_DECISION,
        FUTURE_DECISION, CALENDAR_CONFLICT, NOT_RESOLVED_YET, FOREIGN_OPEN_ORDER,
        FRACTIONAL_POSITION, SHORT_POSITION, WITHIN_TOLERANCE, LONG_ONLY_NOOP, PREVIEW_OK, PREVIEW_EMPTY,
        PREVIEW_REJECTED, PREVIEW_READ_ONLY, TIF_OVERRIDDEN, TIF_UNCONFIRMED, OVER_BUDGET,
        CURRENCY_MISMATCH, HALTED,
    }
)

# Values mirror EXIT_OK / EXIT_CONFIG / EXIT_PRECONDITION / EXIT_REJECTED from
# scripts/ibkr_executor.py (0 / 1 / 2 / 5); the equality test follows in plan 04-07.
# D-16 puts every precondition, "hold" included, under exit 2. Only within-tolerance,
# long-only-noop and preview-ok are "nothing to do, all fine" (exit 0).
_EXIT_OK, _EXIT_CONFIG, _EXIT_PRECONDITION, _EXIT_REJECTED = 0, 1, 2, 5

EXIT_BY_STATE: Mapping[str, int] = MappingProxyType(
    {
        **dict.fromkeys(
            (
                SKIPPED_HOLD, RATING_REVIEW_STATE, RATING_JEV, RUN_NOT_OK, SIGNAL_NULL,
                SIGNAL_DIVERGENCE, SUMMARY_MISSING, NO_DECISION, LOG_MISSING_ENTRY, INVALID_TRADE_DATE,
                LOG_FINDING, PAPER_LOG_UNAVAILABLE, STALE_DECISION, FUTURE_DECISION,
                CALENDAR_CONFLICT, NOT_RESOLVED_YET, FOREIGN_OPEN_ORDER, FRACTIONAL_POSITION,
                SHORT_POSITION,
            ),
            _EXIT_PRECONDITION,
        ),
        **dict.fromkeys(
            (
                PREVIEW_EMPTY, PREVIEW_REJECTED, PREVIEW_READ_ONLY, TIF_OVERRIDDEN,
                TIF_UNCONFIRMED, OVER_BUDGET, CURRENCY_MISMATCH, HALTED,
            ),
            _EXIT_REJECTED,
        ),
        **dict.fromkeys((SUMMARY_SCHEMA, SUMMARY_CONTRACT), _EXIT_CONFIG),
        **dict.fromkeys((WITHIN_TOLERANCE, LONG_ONLY_NOOP, PREVIEW_OK), _EXIT_OK),
    }
)

#: Rank for combining several tickers into one exit: 1 > 5 > 2 > 0 (5 before 2).
_EXIT_RANK = {_EXIT_CONFIG: 3, _EXIT_REJECTED: 2, _EXIT_PRECONDITION: 1, _EXIT_OK: 0}


def worst_exit(states: Sequence[str]) -> int:
    """Combine states into one exit code with the fixed ranking 1 > 5 > 2 > 0."""
    codes = [EXIT_BY_STATE[s] for s in states]
    if not codes:
        return _EXIT_OK
    return max(codes, key=lambda c: _EXIT_RANK[c])


# --- consumer contract for summary.json --------------------------------------------------

SUMMARY_SCHEMA_VERSION = 1
SUMMARY_FIELDS: Mapping[str, type | tuple] = MappingProxyType(
    {"schema_version": int, "trade_date": str, "status": str, "runs": list}
)
RUN_FIELDS: Mapping[str, type | tuple] = MappingProxyType(
    {"ticker": str, "status": str, "signal": (str, type(None))}
)
RATING_SOURCES = frozenset({"engine", "jev"})
RUN_STATUSES = frozenset({"ok", "failed", "budget_aborted", "skipped"})

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SummaryContractError(ValueError):
    """summary.json does not match the fields this consumer reads."""


class SummarySchemaError(SummaryContractError):
    """summary.json has a schema_version this consumer does not know."""


@dataclass(frozen=True)
class RunRecord:
    ticker: str
    status: str
    signal: str | None
    #: Optional in summary.json: the paper run writes it only when the Jev fallback was active.
    rating_source: str | None = None
    #: ``"rating_source": null`` in summary.json: no proof of an engine rating; only this
    #: ticker fails closed (``rating-jev``), the run goes on (IN-02).
    rating_source_null: bool = False


@dataclass(frozen=True)
class Summary:
    schema_version: int
    trade_date: str
    status: str
    runs: tuple[RunRecord, ...]


def parse_trade_date(text: object) -> date | None:
    """Strict ``YYYY-MM-DD``; anything else is ``None``."""
    if not isinstance(text, str) or not _DATE_RE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _check_type(value: object, expected: type | tuple, where: str) -> None:
    allowed = expected if isinstance(expected, tuple) else (expected,)
    # bool is a subclass of int; a boolean is never an acceptable number here.
    if isinstance(value, bool) and bool not in allowed:
        raise SummaryContractError(f"{where}: unexpected bool")
    if not isinstance(value, allowed):
        raise SummaryContractError(f"{where}: unexpected type {type(value).__name__}")


def read_summary(text: str) -> Summary:
    """Parse summary.json, reading only the fields in ``SUMMARY_FIELDS``/``RUN_FIELDS``."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise SummaryContractError(f"summary is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SummaryContractError("summary is not a JSON object")
    for name, expected in SUMMARY_FIELDS.items():
        if name not in data:
            raise SummaryContractError(f"missing field {name!r}")
        _check_type(data[name], expected, name)
    if data["schema_version"] != SUMMARY_SCHEMA_VERSION:
        raise SummarySchemaError(
            f"schema_version {data['schema_version']} != {SUMMARY_SCHEMA_VERSION}"
        )
    if parse_trade_date(data["trade_date"]) is None:
        raise SummaryContractError(f"trade_date {data['trade_date']!r} is not YYYY-MM-DD")
    runs = []
    for i, raw in enumerate(data["runs"]):
        if not isinstance(raw, dict):
            raise SummaryContractError(f"runs[{i}] is not an object")
        for name, expected in RUN_FIELDS.items():
            if name not in raw:
                raise SummaryContractError(f"runs[{i}]: missing field {name!r}")
            _check_type(raw[name], expected, f"runs[{i}].{name}")
        if raw["status"] not in RUN_STATUSES:
            raise SummaryContractError(f"runs[{i}]: unknown status {raw['status']!r}")
        # REQ-IBKR-18: runs[*].report is never read.
        rating_source = None
        source_null = "rating_source" in raw and raw["rating_source"] is None
        if "rating_source" in raw and not source_null:
            _check_type(raw["rating_source"], str, f"runs[{i}].rating_source")
            rating_source = raw["rating_source"]
        runs.append(
            RunRecord(raw["ticker"], raw["status"], raw["signal"], rating_source, source_null)
        )
    return Summary(data["schema_version"], data["trade_date"], data["status"], tuple(runs))


# --- selection and preconditions ---------------------------------------------------------

RATINGS_5 = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
REVIEW = "REVIEW"


def latest_entries(entries: Sequence[Mapping]) -> dict[str, Mapping]:
    """Newest entry per ticker; the log is append-only, the last hit wins (D-07)."""
    latest: dict[str, Mapping] = {}
    for entry in entries:
        latest[entry["ticker"]] = entry
    return latest


@dataclass(frozen=True)
class DecisionVerdict:
    state: str
    detail: str = ""
    rating: str | None = None
    trade_date: date | None = None
    rating_source: str | None = None


def evaluate_decision(entry: Mapping, summary: Summary | None) -> DecisionVerdict:
    """Check the preconditions for one log entry against the matching summary."""
    ticker = entry.get("ticker")
    rating = entry.get("rating")
    trade_date = parse_trade_date(entry.get("date"))

    source: str | None = None

    def verdict(state: str, detail: str = "") -> DecisionVerdict:
        return DecisionVerdict(state, detail, rating, trade_date, source)

    if trade_date is None:
        return verdict(INVALID_TRADE_DATE, f"entry date {entry.get('date')!r} is not YYYY-MM-DD")
    if summary is None:
        return verdict(SUMMARY_MISSING, "no summary.json for this decision")
    run = next((r for r in summary.runs if r.ticker == ticker), None)
    if run is None:
        return verdict(SUMMARY_MISSING, f"{ticker} is not in the summary")
    # A missing field means engine (RESEARCH A1): the paper run writes rating_source only
    # when the Jev fallback was active.
    # An explicit null is no such proof: no source, the ticker fails closed below (IN-02).
    if not run.rating_source_null:
        source = run.rating_source if run.rating_source is not None else "engine"
    if run.status != "ok":
        return verdict(RUN_NOT_OK, f"run status {run.status}")
    if run.signal is None:
        return verdict(SIGNAL_NULL, "summary run has no signal")
    if rating == REVIEW or rating not in RATINGS_5:
        return verdict(RATING_REVIEW_STATE, f"rating {rating!r} needs a human")
    if rating != run.signal:
        return verdict(
            SIGNAL_DIVERGENCE,
            f"log={rating} summary={run.signal}; log version wins, nothing executed",
        )
    if rating == "Hold":
        return verdict(SKIPPED_HOLD, "skipped: hold")
    # D-05/D-06: positive proof of an engine rating; Jev or an unknown source fails closed.
    if run.rating_source_null:
        return verdict(RATING_JEV, "rating_source is null in summary.json; not traded")
    if source == "jev":
        return verdict(
            RATING_JEV,
            "rating from the Jev fallback (summary.json rating_source=jev); not traded",
        )
    if source not in RATING_SOURCES:
        return verdict(
            RATING_JEV, f"unknown rating_source {source!r} in summary.json; not traded"
        )
    return verdict(EXECUTABLE)


def newer_summary_state(entry_date: date, newer_summary: Summary, ticker: str) -> str | None:
    """Explain a missing newer log entry from a newer summary (pitfall 5)."""
    nd = parse_trade_date(newer_summary.trade_date)
    if nd is None or nd <= entry_date:
        return None
    run = next((r for r in newer_summary.runs if r.ticker == ticker), None)
    if run is None:
        return None
    if run.status != "ok":
        return RUN_NOT_OK
    if run.signal is None:
        return SIGNAL_NULL
    return LOG_MISSING_ENTRY


# --- order plan --------------------------------------------------------------------------

#: Target in blocks per rating. Hold is deliberately absent: it is caught before
#: any calculation.
BLOCKS: Mapping[str, int] = MappingProxyType({"Buy": 2, "Overweight": 1, "Underweight": 0, "Sell": 0})


@dataclass(frozen=True)
class Plan:
    state: str
    side: str | None = None
    quantity: int = 0
    target: int = 0
    held: float = 0.0
    detail: str = ""


def plan_order(rating: str, *, held_qty: float, open_orders: int, block_qty: int) -> Plan:
    """Target = blocks x block_qty; long-only; tolerance band of one block.

    Own open orders are only netted as ``target - held - open`` from phase 6 on.
    """
    if rating == "Hold":
        return Plan(SKIPPED_HOLD, held=held_qty, detail="skipped: hold")
    if block_qty <= 0:
        raise ValueError(f"block_qty must be positive, got {block_qty}")
    if open_orders > 0:
        return Plan(
            FOREIGN_OPEN_ORDER,
            held=held_qty,
            detail="phase 4 never sends, every open order is foreign; nothing planned for this ticker",
        )
    if held_qty < 0:
        # Long-only: a short is somebody else's state. Netting it would turn a
        # Sell signal into a BUY (cover), and a small short into within-tolerance.
        return Plan(SHORT_POSITION, held=held_qty, detail=f"held {held_qty:g} is short; long-only, nothing planned")
    target = BLOCKS[rating] * block_qty
    if held_qty != int(held_qty):
        return Plan(FRACTIONAL_POSITION, target=target, held=held_qty, detail=f"held {held_qty} is fractional")
    if held_qty == 0 and target == 0:
        return Plan(LONG_ONLY_NOOP, held=held_qty, detail="sell/underweight without holding: no short")
    if abs(target - held_qty) < block_qty:
        return Plan(
            WITHIN_TOLERANCE,
            target=target,
            held=held_qty,
            detail=f"target {target} held {held_qty:g} block {block_qty}: within one block",
        )
    diff = target - held_qty
    side = "BUY" if diff > 0 else "SELL"
    quantity = int(abs(diff))
    # held_qty >= 0 and target >= 0 here, so a SELL of target - held never
    # exceeds the holding: the long-only invariant holds by construction.
    return Plan(INTENT, side, quantity, target, held_qty, f"{side} {quantity}: target {target}, held {held_qty:g}")


# --- preview verdict ---------------------------------------------------------------------


@dataclass(frozen=True)
class PreviewVerdict:
    state: str
    detail: str = ""
    reject_reason: str = ""
    reject_source: str = ""


def judge_preview(
    preview, *, available_funds: float, funds_currency: str, account_currency: str
) -> PreviewVerdict:
    """Judge a what-if result, fail-closed on anything missing or unknown."""
    # ib_async 2.1.0 OrderState has no rejectReason field; the reject reason is built
    # from the request's error texts (RESEARCH Pitfall 1). warning_text is logged as
    # a warning, never a rejection (assumption A2).
    errors = tuple(preview.errors or ())
    reason = "; ".join(f"{code}: {text}" for code, text in errors)
    source = "request-errors" if reason else ""

    def verdict(state: str, detail: str = "") -> PreviewVerdict:
        return PreviewVerdict(state, detail, reason, source)

    state = preview.state
    if state == "HALTED":
        return verdict(HALTED, "instrument reported halted")
    if state == "TIF_OVERRIDDEN":
        return verdict(TIF_OVERRIDDEN, "broker overrode the time in force")
    if state == "READ_ONLY_API":
        return verdict(PREVIEW_READ_ONLY, "API is read-only")
    if state == "EMPTY":
        if errors:
            return verdict(PREVIEW_REJECTED, reason)
        return verdict(PREVIEW_EMPTY, "what-if returned no values")
    if state != "OK":
        return verdict(PREVIEW_EMPTY, f"unknown preview state {state!r}")
    if (
        preview.init_margin_change is None
        or preview.maint_margin_change is None
        or preview.commission is None
        or not preview.commission_currency
    ):
        return verdict(PREVIEW_EMPTY, "margin or commission fields missing")
    if errors:
        return verdict(PREVIEW_REJECTED, reason)
    if preview.effective_tif is None:
        return verdict(TIF_UNCONFIRMED, "effective time in force not readable")
    if preview.effective_tif != preview.sent_tif:
        return verdict(
            TIF_OVERRIDDEN, f"sent {preview.sent_tif}, effective {preview.effective_tif}"
        )
    if preview.warning_text:
        log.warning("preview warning: %s", preview.warning_text)
    if funds_currency != account_currency:
        return verdict(
            CURRENCY_MISMATCH, f"funds in {funds_currency}, account in {account_currency}"
        )
    if not math.isfinite(available_funds):
        # An unknown budget is no budget: with nan/inf the comparison below is always
        # False and every preview would pass (review P4 IN-04).
        return verdict(OVER_BUDGET, f"available funds {available_funds!r} is not a finite number")
    if preview.init_margin_change >= available_funds:
        return verdict(
            OVER_BUDGET,
            f"initial margin {preview.init_margin_change:.2f} >= available funds "
            f"{available_funds:.2f} {account_currency}",
        )
    return verdict(PREVIEW_OK, "within budget")


# --- session calendar, freshness in sessions (REQ-IBKR-19, -20; D-05, D-06, D-08) --------


class CalendarRangeError(ValueError):
    """A date lies outside the range the session calendar can answer for."""


class SessionCalendar(Protocol):
    zone_name: str

    def is_session(self, day: date) -> bool: ...

    def sessions_between(self, start: date, end: date) -> tuple[date, ...]:
        """Sessions from ``start`` to ``end``, both inclusive; empty if ``start > end``."""

    def next_session_after(self, day: date) -> date:
        """First session strictly after ``day``."""

    def session_close_utc(self, day: date) -> datetime:
        """Close of the session ``day`` as an aware UTC datetime."""


class XnysSessions:
    """Wraps an ``exchange_calendars`` calendar object behind ``SessionCalendar``.

    ``pandas`` and ``exchange_calendars.errors`` are imported inside the methods so the
    module stays library-free at import time.
    """

    def __init__(self, cal: object) -> None:
        self._cal = cal
        self.zone_name = str(cal.tz)

    @staticmethod
    def _ts(day: date):
        return importlib.import_module("pandas").Timestamp(day.isoformat())

    @staticmethod
    def _errors() -> tuple[type[BaseException], ...]:
        errors = importlib.import_module("exchange_calendars.errors")
        return (
            errors.DateOutOfBounds,
            errors.NotSessionError,
            errors.RequestedSessionOutOfBounds,
        )

    def is_session(self, day: date) -> bool:
        try:
            return bool(self._cal.is_session(self._ts(day)))
        except self._errors() as exc:
            raise CalendarRangeError(f"{day} outside the calendar range: {exc}") from exc

    def sessions_between(self, start: date, end: date) -> tuple[date, ...]:
        if start > end:
            return ()
        try:
            found = self._cal.sessions_in_range(self._ts(start), self._ts(end))
        except self._errors() as exc:
            raise CalendarRangeError(f"{start}..{end} outside the calendar range: {exc}") from exc
        return tuple(ts.date() for ts in found)

    def next_session_after(self, day: date) -> date:
        try:
            ts = self._ts(day)
            if self._cal.is_session(ts):
                nxt = self._cal.next_session(ts)
            else:
                nxt = self._cal.date_to_session(ts, direction="next")
        except self._errors() as exc:
            raise CalendarRangeError(f"{day} outside the calendar range: {exc}") from exc
        return nxt.date()

    def session_close_utc(self, day: date) -> datetime:
        try:
            close = self._cal.session_close(self._ts(day))
        except self._errors() as exc:
            raise CalendarRangeError(f"{day} outside the calendar range: {exc}") from exc
        return close.to_pydatetime().astimezone(UTC)


def load_xnys_calendar() -> SessionCalendar:
    """Load the XNYS calendar; ``ImportError`` is passed through (the executor reports it)."""
    import exchange_calendars

    return XnysSessions(exchange_calendars.get_calendar("XNYS"))


def _calendar_today(now_utc: datetime, calendar: SessionCalendar) -> date:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
    return now_utc.astimezone(ZoneInfo(calendar.zone_name)).date()


def second_last_close_utc(
    now_utc: datetime, calendar: SessionCalendar, *, window_days: int = 14
) -> datetime:
    """Close of the second-to-last regular session that has already closed at ``now_utc``.

    A published portfolio is valid when its as_of is later (D-06). Weekends and holidays
    come from the calendar only; fewer than two closed sessions in the window raise
    ``CalendarRangeError`` rather than yield an estimate.
    """
    today = _calendar_today(now_utc, calendar)
    days = calendar.sessions_between(today - timedelta(days=window_days), today)
    closes: list[datetime] = []
    for day in reversed(days):
        close = calendar.session_close_utc(day)
        if close <= now_utc:
            closes.append(close)
            if len(closes) == 2:
                return closes[1]
    raise CalendarRangeError(f"fewer than two closed sessions in the last {window_days} days")


def execution_session(now_utc: datetime, calendar: SessionCalendar) -> tuple[date, bool]:
    """Return the execution session E and whether it is today's still-open session (D-08).

    E is today if today is a session whose close is not yet reached; otherwise the next
    session (evening, weekend, holiday), with ``in_session_day=False``.
    """
    today = _calendar_today(now_utc, calendar)
    if calendar.is_session(today) and now_utc < calendar.session_close_utc(today):
        return today, True
    return calendar.next_session_after(today), False


@dataclass(frozen=True)
class Freshness:
    state: str  # "fresh" | "stale-decision" | "future-decision"
    execution_day: date | None
    in_session_day: bool | None
    gap_days: int | None
    closed_sessions: tuple[date, ...]
    weekend_gap: bool
    detail: str


def freshness(trade_date: date, now_utc: datetime, calendar: SessionCalendar) -> Freshness:
    """Count closed sessions strictly between ``trade_date`` and the execution session.

    A closed session in between makes the decision ``stale-decision`` (REQ-IBKR-19). Any
    calendar gap of more than one day without a closed session is flagged ``weekend_gap``
    and stays executable (D-06, REQ-IBKR-20).

    ``trade_date`` may itself be a non-session (holiday Monday): the date trap in
    ``daily_paper_run.previous_weekday``, which knows no holidays, is therefore allowed.
    "Saturday decision" in SC4 means the decision of the Saturday run, whose
    ``trade_date`` is the Friday.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
    try:
        exec_day, in_session = execution_session(now_utc, calendar)
        if trade_date >= exec_day:
            return Freshness(
                "future-decision", exec_day, in_session, None, (), False,
                f"trade_date {trade_date} is not before execution session {exec_day}",
            )
        closed = calendar.sessions_between(trade_date + timedelta(days=1), exec_day - timedelta(days=1))
    except CalendarRangeError as exc:
        return Freshness(
            STALE_DECISION, None, None, None, (), False,
            f"trade_date outside the calendar range: {exc}",
        )
    if closed:
        listed = ", ".join(d.isoformat() for d in closed)
        return Freshness(
            STALE_DECISION, exec_day, in_session, None, closed, False,
            f"session(s) {listed} closed between trade_date {trade_date} and execution "
            f"session {exec_day}; nothing executed (REQ-IBKR-19)",
        )
    gap = (exec_day - trade_date).days
    return Freshness(
        FRESH, exec_day, in_session, gap, (), gap > 1,
        f"trade_date {trade_date}, execution session {exec_day}, {gap} calendar day(s)",
    )


def calendar_conflict(
    now_utc: datetime, calendar: SessionCalendar, session_day: bool | None
) -> bool:
    """D-05: liquidHours of the resolved contract decides today; the exchange calendar
    decides the past. If they disagree about today, the run stops with calendar-conflict.
    """
    today = _calendar_today(now_utc, calendar)
    if session_day is None:
        return False
    try:
        return calendar.is_session(today) != session_day
    except CalendarRangeError:
        return True
