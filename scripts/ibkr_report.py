"""Read-only target/actual (Soll/Ist) report: data layer, metrics, markdown, CLI.

REQ-IBKR-49 / REQ-IBKR-50. Exit codes: 0 ok, 1 usage error, 2 a source is not readable.

Takes the raw ``decision-log.md`` text and the raw ``ledger.jsonl`` bytes and returns one
row per decision. The join happens at read time over ``(trade_date, ticker)`` against the
real ledger. This module never writes to any branch, never reads a clock and never
estimates a value the ledger does not hold: target and actual position come from the
``intent`` record only (D-20), the free-text ``detail`` field is never parsed (D-16).
"""

from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

#: Same separator as ``ibkr_guards.DECISION_KEY_SEPARATOR``; a test compares the two.
KEY_SEPARATOR = "|"

#: The decision log joins its entries with this line (see ``TradingMemoryLog._SEPARATOR``).
_ENTRY_SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"

NO_RUN = "no-run"

_FILL_TIMEOUT = "fill-timeout"


def _load(name: str, filename: str):
    """Load a sibling script once under ``name`` (same pattern as the executor)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _ledger():
    return _load("ibkr_ledger", "ibkr_ledger.py")


def _decision():
    return _load("ibkr_decision", "ibkr_decision.py")


def _contracts():
    return _load("ibkr_contracts", "ibkr_contracts.py")


def _paperlog():
    return _load("ibkr_paperlog", "ibkr_paperlog.py")


@dataclass(frozen=True)
class Decision:
    trade_date: str
    ticker: str
    rating: str
    pending: bool
    raw: str | None
    alpha: str | None
    holding: str | None
    resolved: str | None

    @property
    def key(self) -> str:
        return f"{self.trade_date}{KEY_SEPARATOR}{self.ticker}"


@dataclass(frozen=True)
class ReportRow:
    key: str
    trade_date: str
    ticker: str
    log_rating: str
    ledger_rating: str | None
    state: str
    side: str | None
    target: float | None
    held_before: float | None
    held_after: float | None
    order_qty: float | None
    filled_qty: float | None
    avg_price: float | None
    deviation: float | None
    weekend_gap: bool | None
    notes: tuple[str, ...]


# --- reading -------------------------------------------------------------------------------


def parse_decisions(text: str) -> tuple[list[Decision], int, int]:
    """Decisions in file order, the count of unreadable blocks and of dropped duplicates.

    The first version of a ``(trade_date, ticker)`` wins (D-12); later ones are counted.
    """
    from tradingagents.memory.log import TradingMemoryLog

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "decision-log.md"
        copy.write_bytes(text.encode("utf-8"))
        entries = TradingMemoryLog({"memory_log_path": str(copy)}).load_entries()
    blocks = [b for b in (part.strip() for part in text.split(_ENTRY_SEPARATOR)) if b]
    unparsed = max(len(blocks) - len(entries), 0)
    decisions: list[Decision] = []
    seen: set[str] = set()
    duplicates = 0
    for entry in entries:
        decision = Decision(
            trade_date=entry["date"],
            ticker=entry["ticker"],
            rating=entry["rating"],
            pending=bool(entry["pending"]),
            raw=entry.get("raw"),
            alpha=entry.get("alpha"),
            holding=entry.get("holding"),
            resolved=entry.get("resolved"),
        )
        if decision.key in seen:
            duplicates += 1
            continue
        seen.add(decision.key)
        decisions.append(decision)
    return decisions, unparsed, duplicates


def _no_clock():
    raise RuntimeError("the report never appends")


def read_ledger(blob: bytes) -> list[dict]:
    """Records of a live ledger in file order; ``LedgerError`` on anything else (T-07-14)."""
    ledger_mod = _ledger()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.jsonl"
        path.write_bytes(blob)
        ledger = ledger_mod.Ledger.open(
            path, mode=ledger_mod.MODE_LIVE, clock=_no_clock, run_id="report"
        )
        return list(ledger.records)


# --- joining -------------------------------------------------------------------------------


def _fills(rows: list[dict]) -> tuple[float, float | None]:
    """Correction-aware filled quantity and average price over a key's fill rows."""
    ledger_mod = _ledger()
    with_id = [r for r in rows if r.get("exec_id")]
    if with_id:
        counted = ledger_mod.effective_executions(
            [
                SimpleNamespace(
                    exec_id=r["exec_id"],
                    shares=float(r.get("filled_qty") or 0),
                    price=r.get("price"),
                )
                for r in with_id
            ]
        )
        pairs = [(float(c.shares), c.price) for c in counted]
    else:
        pairs = [(float(r.get("filled_qty") or 0), r.get("price")) for r in rows]
    total = sum(qty for qty, _ in pairs)
    priced = [(qty, price) for qty, price in pairs if price is not None]
    priced_qty = sum(qty for qty, _ in priced)
    average = sum(qty * price for qty, price in priced) / priced_qty if priced_qty else None
    return total, average


def _lifecycle_state(last: dict, alarms: list[dict], notes: list[str]) -> str:
    ledger_mod = _ledger()
    event = last["event"]
    if event == ledger_mod.FILLED:
        return "filled"
    if event == ledger_mod.PARTIAL:
        return "partial"
    if event == ledger_mod.REJECTED:
        return last.get("state") or "rejected"
    if event == ledger_mod.RESOLVED:
        return last.get("outcome") or "resolved"
    if event == ledger_mod.PLACED:
        if any(a.get("state") == _FILL_TIMEOUT for a in alarms):
            return _FILL_TIMEOUT
        return "placed"
    if event == ledger_mod.DRY_COMPLETE:
        notes.append("dry event in a live ledger")
        return "dry-complete"
    return "intent-open"


def _build_row(
    decision: Decision,
    records: list[dict],
    block_qty_of: Callable[[str], int | None],
) -> ReportRow:
    ledger_mod = _ledger()
    blocks = _decision().BLOCKS
    notes: list[str] = []
    intent = next((r for r in records if r["event"] == ledger_mod.INTENT), None)
    alarms = [r for r in records if r["event"] == ledger_mod.ALARM]
    lifecycle = [r for r in records if r["event"] in ledger_mod.LIFECYCLE_EVENTS]
    closers = [r for r in records if r["event"] in (ledger_mod.SKIPPED, ledger_mod.REJECTED)]
    last_closer = closers[-1] if closers else None

    if intent is not None:
        state = _lifecycle_state(lifecycle[-1], alarms, notes)
    elif last_closer is not None:
        state = last_closer.get("state") or last_closer.get("reason") or last_closer["event"]
        notes.append("no intent: target/held not recorded (D-20)")
    else:
        state = NO_RUN

    ledger_rating = None
    if intent is not None:
        ledger_rating = intent.get("rating")
    elif last_closer is not None:
        ledger_rating = last_closer.get("rating")
    sha_source = intent or last_closer or {}
    sha = sha_source.get("paper_log_sha")
    if ledger_rating is not None and ledger_rating != decision.rating:
        where = f" (paper-log {str(sha)[:7]})" if sha else ""
        notes.append(f"ledger rating {ledger_rating} != log rating {decision.rating}{where}")

    side = order_qty = target = held_before = held_after = None
    filled_qty = avg_price = deviation = None
    if intent is not None:
        side = intent["side"]
        order_qty = float(intent["quantity"])
        fills = [r for r in records if r["event"] in (ledger_mod.FILLED, ledger_mod.PARTIAL)]
        filled_qty, avg_price = _fills(fills) if fills else (0.0, None)
        block_qty = block_qty_of(decision.ticker)
        multiplier = blocks.get(ledger_rating)
        if block_qty is None:
            notes.append(f"no block size for {decision.ticker}: target not derivable")
        elif multiplier is None:
            notes.append(f"rating {ledger_rating} has no target")
        else:
            target = float(multiplier * block_qty)
            before = target - order_qty if side == "BUY" else target + order_qty
            if before < 0 or not float(before).is_integer():
                notes.append("held before is not a whole non-negative number - block size changed?")
            else:
                held_before = before
                held_after = before + filled_qty if side == "BUY" else before - filled_qty
                deviation = target - held_after

    gap = intent.get("weekend_gap") if intent is not None else None
    if gap is None and last_closer is not None:
        gap = last_closer.get("weekend_gap")

    for alarm in alarms:
        note = f"alarm: {alarm.get('state')}"
        if note not in notes:
            notes.append(note)

    return ReportRow(
        key=decision.key,
        trade_date=decision.trade_date,
        ticker=decision.ticker,
        log_rating=decision.rating,
        ledger_rating=ledger_rating,
        state=state,
        side=side,
        target=target,
        held_before=held_before,
        held_after=held_after,
        order_qty=order_qty,
        filled_qty=filled_qty,
        avg_price=avg_price,
        deviation=deviation,
        weekend_gap=gap,
        notes=tuple(notes),
    )


def build_rows(
    decisions: list[Decision],
    records: list[dict],
    *,
    block_qty_of: Callable[[str], int | None],
) -> tuple[list[ReportRow], list[str]]:
    """One row per decision in log order, plus ledger keys that have no log entry."""
    by_key: dict[str, list[dict]] = {}
    for record in records:
        key = record.get("decision_key")
        if key is not None:
            by_key.setdefault(key, []).append(record)
    rows = [_build_row(d, by_key.get(d.key, []), block_qty_of) for d in decisions]
    known = {d.key for d in decisions}
    return rows, sorted(k for k in by_key if k not in known)


# --- metrics -------------------------------------------------------------------------------

PAPER_FILL_NOTICE = (
    "Paper fills are simulated from the top of the book, and the rest of a partially filled "
    "exchange-directed market order is rejected. Fill ratios from the paper account are "
    "therefore systematically biased upward. This report tests the mechanics; it does not "
    "measure execution quality (REQ-IBKR-50)."
)

SLIPPAGE_HEADER = "Decision price -> fill (incl. gap), bp"

SLIPPAGE_EXPLANATION = (
    "Slippage reference is the close on the trade date, so the overnight gap is included "
    "(D-14). Positive means worse for both BUY and SELL."
)

_ZERO_FILL_STATES = frozenset({_FILL_TIMEOUT, "place-rejected"})


def slippage_bp(side: str | None, avg_fill: float | None, close: float | None) -> float | None:
    """Basis points from the decision price to the fill; positive = worse (D-14)."""
    if side not in ("BUY", "SELL") or avg_fill is None or close is None:
        return None
    if not close > 0:
        return None
    sign = 1 if side == "BUY" else -1
    return sign * (avg_fill - close) / close * 1e4


def _filled_or_zero(row: ReportRow) -> float:
    return 0.0 if row.state in _ZERO_FILL_STATES else (row.filled_qty or 0.0)


def fill_ratio(row: ReportRow) -> float | None:
    if row.order_qty is None or row.order_qty <= 0:
        return None
    return _filled_or_zero(row) / row.order_qty


def total_fill_ratio(rows: list[ReportRow]) -> float | None:
    with_intent = [r for r in rows if r.order_qty is not None]
    ordered = sum(r.order_qty for r in with_intent)
    if not with_intent or ordered <= 0:
        return None
    return sum(_filled_or_zero(r) for r in with_intent) / ordered


class CloseFetcher:
    """Close on a trade date from the settlement price source; fail-soft (D-16)."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[float | None, str | None]] = {}

    def get(self, ticker: str, trade_date: str) -> tuple[float | None, str | None]:
        key = (ticker, trade_date)
        if key not in self._cache:
            self._cache[key] = self._fetch(ticker, trade_date)
        return self._cache[key]

    @staticmethod
    def _fetch(ticker: str, trade_date: str) -> tuple[float | None, str | None]:
        reason = f"no close for {ticker} on {trade_date} from the price source"
        try:
            from tradingagents.memory import settlement

            end = (date.fromisoformat(trade_date) + timedelta(days=1)).isoformat()
            series = settlement.get_closes(ticker, trade_date, end)
            if series is None or len(series) == 0:
                return None, reason
            value = float(series.iloc[-1])
        except Exception as exc:  # noqa: BLE001 - the report never fails on the price source
            return None, f"{reason} ({type(exc).__name__})"
        if math.isnan(value) or value <= 0:
            return None, f"{reason} (unusable value)"
        return value, None


# --- rendering -----------------------------------------------------------------------------


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _num(value: float | None, fmt: str = "g") -> str:
    return "" if value is None else format(value, fmt)


def _table(headers: list[str], body: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in body]
    return lines


EXECUTION_HEADERS = [
    "Trade date",
    "Ticker",
    "Rating",
    "State",
    "Target",
    "Held",
    "Order",
    "Filled",
    "Avg price",
    "Target - held",
    "weekend_gap",
    "Fill ratio",
    SLIPPAGE_HEADER,
]
DECISION_HEADERS = [
    "Trade date",
    "Ticker",
    "Rating",
    "Realized return",
    "Alpha",
    "Holding",
    "Status",
]


def render_markdown(
    rows: list[ReportRow],
    decisions: list[Decision],
    *,
    sources: dict[str, str],
    period: tuple[str | None, str | None],
    prices: CloseFetcher | None,
    unparsed: int,
    duplicates: int,
    ledger_only: list[str],
) -> str:
    footnotes: list[str] = []

    def note(text: str) -> str:
        if text not in footnotes:
            footnotes.append(text)
        return f"[{footnotes.index(text) + 1}]"

    skipped_ref = note("prices skipped (--no-prices)") if prices is None else ""

    body: list[list[str]] = []
    for r in rows:
        refs = "".join(note(n) for n in r.notes)
        held = ""
        if r.held_before is not None and r.held_after is not None:
            held = f"{r.held_before:g} -> {r.held_after:g}"
        slip_cell = ""
        if r.avg_price is not None and r.side is not None:
            if prices is None:
                slip_cell = skipped_ref
            else:
                close, reason = prices.get(r.ticker, r.trade_date)
                if close is None:
                    slip_cell = note(reason or "no close from the price source")
                else:
                    bp = slippage_bp(r.side, r.avg_price, close)
                    slip_cell = "" if bp is None else f"{bp:.1f}"
        ratio = fill_ratio(r)
        body.append(
            [
                r.trade_date,
                r.ticker,
                r.ledger_rating or r.log_rating,
                f"{r.state} {refs}".strip(),
                _num(r.target) if r.target is not None else "—",
                held,
                "" if r.order_qty is None or r.side is None else f"{r.side} {r.order_qty:g}",
                _num(r.filled_qty),
                _num(r.avg_price, ".2f"),
                _num(r.deviation),
                "" if r.weekend_gap is None else str(r.weekend_gap).lower(),
                "" if ratio is None else f"{ratio:.2f}",
                slip_cell,
            ]
        )

    decision_body = [
        [
            d.trade_date,
            d.ticker,
            d.rating,
            d.raw or "",
            d.alpha or "",
            d.holding or "",
            "pending" if d.pending else f"resolved {d.resolved or ''}".strip(),
        ]
        for d in decisions
    ]

    if unparsed:
        note(f"{unparsed} unreadable decision-log block(s) were skipped")
    if duplicates:
        note(f"{duplicates} duplicate decision(s) dropped, first version kept (D-12)")
    if ledger_only:
        note("ledger keys without a decision-log entry: " + ", ".join(ledger_only))

    total = total_fill_ratio(rows)
    since, until = period
    total_text = "n/a" if total is None else f"{total:.2f}"
    out = ["# Target/actual report", ""]
    out += [f"- {name}: {ref}" for name, ref in sources.items()]
    out.append(f"- Period: {since or 'start'} .. {until or 'end'}")
    out.append(f"- Fill ratio (sum filled / sum ordered): {total_text}")
    out += ["", f"> {PAPER_FILL_NOTICE}", "", SLIPPAGE_EXPLANATION, ""]
    out += ["## Execution", ""] + _table(EXECUTION_HEADERS, body) + [""]
    out += ["## Decision", ""] + _table(DECISION_HEADERS, decision_body) + [""]
    out += ["## Notes", ""]
    out += [f"{i}. {n}" for i, n in enumerate(footnotes, 1)] or ["None."]
    return "\n".join(out) + "\n"
