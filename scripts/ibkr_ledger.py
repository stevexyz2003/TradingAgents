"""Append-only execution ledger for the IBKR executor (library-free, no clock).

One JSON object per line, one line per event. The state of a ``decision_key`` is its last
lifecycle event; nothing is ever rewritten or deleted. Two files share this code, one per
mode (``dryrun`` / ``live``, D-08); every line carries its mode, so a line of the wrong
mode is a ledger error instead of a silent mix-up.

The time comes in as a callable, the broker history comes in as duck-typed records: this
module imports neither the broker adapter nor any client library.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

log = logging.getLogger(__name__)

LEDGER_VERSION = 1

MODE_DRYRUN = "dryrun"
MODE_LIVE = "live"
MODES = frozenset({MODE_DRYRUN, MODE_LIVE})

# --- events --------------------------------------------------------------------------------

RUN_START = "run_start"
SWITCH_CHECK = "switch_check"
RECONCILE = "reconcile"
INTENT = "intent"
DRY_COMPLETE = "dry_complete"
PLACED = "placed"
FILLED = "filled"
PARTIAL = "partial"
REJECTED = "rejected"
SKIPPED = "skipped"
KILL_CANCEL = "kill_cancel"
RUN_END = "run_end"
#: Run alarm after the order (D-08 fill timeout, D-09 mismatch): no lifecycle event, so the
#: entry stays open (last lifecycle event ``placed``) and the next run's reconciliation books
#: its fills from the broker. Only exception: a mismatch whose fills the broker confirms as
#: final (order done, effective executions == its filled quantity) books them in the same
#: run (``fills_booked: true``), which closes the entry (WR-02).
ALARM = "alarm"
#: Closes an open live entry by hand (D-14, phase-5 D-19); never changes a line; the key
#: stays used up (``attempt_of`` still finds the intent). ``never_sent`` closes an entry
#: whose last lifecycle event is ``intent``; ``expired_unfilled`` one whose last is
#: ``placed`` (the operator confirmed in TWS that the DAY order expired unfilled, WR-03).
RESOLVED = "resolved"
NEVER_SENT = "never_sent"
EXPIRED_UNFILLED = "expired_unfilled"
RESOLVE_OUTCOMES = frozenset({NEVER_SENT, EXPIRED_UNFILLED})

EVENTS = frozenset(
    {
        RUN_START,
        SWITCH_CHECK,
        RECONCILE,
        INTENT,
        DRY_COMPLETE,
        PLACED,
        FILLED,
        PARTIAL,
        REJECTED,
        SKIPPED,
        KILL_CANCEL,
        RUN_END,
        ALARM,
        RESOLVED,
    }
)
#: Only these events move the state of a decision key; reconcile, switch_check, skipped
#: and the run events never do, so an unresolvable intent stays open in every later run.
LIFECYCLE_EVENTS = frozenset({INTENT, PLACED, FILLED, PARTIAL, REJECTED, DRY_COMPLETE, RESOLVED})
OPEN_EVENTS = frozenset({INTENT, PLACED})

# --- reasons for a skipped ticker (REQ-42) ---------------------------------------------------

REASONS = frozenset(
    {
        "hold",
        "review",
        "tolerance",
        "stale",
        "not_tradable",
        "outside_session",
        "size_cap",
        "kill_switch",
        "source_conflict",
        "already_attempted",
        "decision_changed",
        "foreign_open_order",
    }
)

# State names are literals on purpose: no import of the decision or guards modules.
REASON_BY_STATE: Mapping[str, str] = MappingProxyType(
    {
        "skipped-hold": "hold",
        **dict.fromkeys(
            (
                "rating-review",
                # Jev-sourced rating (D-05/D-06): skipped, never an order; state lives in 06-02.
                "rating-jev",
                "run-not-ok",
                "signal-null",
                "signal-divergence",
                "summary-missing",
                "no-decision",
                "log-missing-entry",
                "invalid-trade-date",
                "fractional-position",
                "short-position",
                "summary-schema",
                "summary-contract",
                "log-finding",
                "paper-log-unavailable",
            ),
            "review",
        ),
        **dict.fromkeys(("within-tolerance", "long-only-noop"), "tolerance"),
        **dict.fromkeys(("stale-decision", "future-decision"), "stale"),
        **dict.fromkeys(
            (
                "not-mapped",
                "not-allowed",
                "ambiguous",
                "not-found",
                "drift",
                "not-tradable",
                "session-unknown",
                "not-resolved-yet",
                # No idempotency key can be built (e.g. ^GSPC): never an order (CR-02).
                "invalid-decision-key",
            ),
            "not_tradable",
        ),
        "foreign-open-order": "foreign_open_order",
        "outside-session": "outside_session",
        "size-cap": "size_cap",
        **dict.fromkeys(
            (
                "kill-active",
                "kill-unreadable",
                "release-missing",
                "release-unreadable",
                "release-invalid",
                "release-expired",
                "release-account-mismatch",
            ),
            "kill_switch",
        ),
        **dict.fromkeys(("source-conflict", "calendar-conflict"), "source_conflict"),
        "already-attempted": "already_attempted",
        "decision-changed": "decision_changed",
    }
)

#: whatIf verdicts other than OK: ledger event ``rejected`` (exit 5). Disjoint from
#: ``REASON_BY_STATE``; ``halted`` is a verdict and lives only here.
REJECTED_STATES = frozenset(
    {
        "preview-rejected",
        "preview-empty",
        "preview-read-only",
        "over-budget",
        "halted",
        "tif-overridden",
        "tif-unconfirmed",
        "currency-mismatch",
        # Definitive IBKR rejection after sending (06-06).
        "place-rejected",
    }
)


def reason_for_state(state: str) -> str:
    """Reason for a skipped ticker; an unknown state raises ``KeyError`` (no default)."""
    return REASON_BY_STATE[state]


#: Field on the first record after a torn tail: the number of the cut-off line it closes.
#: Only a broken line followed directly by its seal is tolerated in the middle of the file.
SEALS_LINE = "seals_torn_line"
_BROKEN = object()


class LedgerError(ValueError):
    """The ledger file cannot be trusted (broken middle line, foreign mode, bad record)."""


SIDES = frozenset({"BUY", "SELL"})


def _is_int(value: object) -> bool:
    return type(value) is int  # excludes bool on purpose


def _is_number(value: object) -> bool:
    return type(value) in (int, float)  # excludes bool on purpose


def _is_text(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _schema_problem(record: dict) -> str | None:
    """Why ``record`` is not a ledger record the executor can use, or None.

    ``v``, ``event`` and ``mode`` are checked by the caller; this covers the fields that are
    read later (``seq``, ``ts``, ``run_id``, the decision key, the intent's order fields,
    the filled quantity and the skip reason).
    """
    seq = record.get("seq")
    if not _is_int(seq) or seq <= 0:
        return f"has seq {seq!r}, expected a positive whole number"
    for name in ("ts", "run_id"):
        if not _is_text(record.get(name)):
            return f"has {name} {record.get(name)!r}, expected text"
    event = record["event"]
    if "decision_key" in record and not _is_text(record["decision_key"]):
        return f"has decision_key {record['decision_key']!r}, expected text"
    if event == INTENT:
        if "decision_key" not in record:
            return "is an intent without a decision_key"
        if not _is_text(record.get("ticker")):
            return f"is an intent with ticker {record.get('ticker')!r}"
        if not _is_text(record.get("rating")):
            return f"is an intent with rating {record.get('rating')!r}"
        if not _is_text(record.get("paper_log_sha")):
            return f"is an intent with paper_log_sha {record.get('paper_log_sha')!r}"
        if record.get("side") not in SIDES:
            return f"is an intent with side {record.get('side')!r}"
        quantity = record.get("quantity")
        if not _is_number(quantity) or quantity <= 0:
            return f"is an intent with quantity {quantity!r}"
        if not _is_int(record.get("con_id")):
            return f"is an intent with con_id {record.get('con_id')!r}"
        order_ref = record.get("order_ref")
        if order_ref is not None and not _is_text(order_ref):
            return f"is an intent with order_ref {order_ref!r}"
    if event == ALARM and not _is_text(record.get("state")):
        return f"is an alarm with state {record.get('state')!r}"
    if event == RESOLVED:
        if not _is_text(record.get("decision_key")):
            return "is a resolved without a decision_key"
        if record.get("outcome") not in RESOLVE_OUTCOMES:
            return f"is a resolved with outcome {record.get('outcome')!r}"
        if not _is_text(record.get("note")):
            return f"is a resolved with note {record.get('note')!r}, expected text"
    if event in (FILLED, PARTIAL):
        if record.get("side") not in SIDES:
            return f"has side {record.get('side')!r}, expected BUY or SELL"
        if "exec_id" in record and not _is_text(record["exec_id"]):
            return f"has exec_id {record['exec_id']!r}, expected text"
        price = record.get("price")
        if price is not None and (not _is_number(price) or price < 0):
            return f"has price {price!r}"
        filled = record.get("filled_qty")
        if filled is not None and (not _is_number(filled) or filled < 0):
            return f"has filled_qty {filled!r}"
        if "con_id" in record and not _is_int(record["con_id"]):
            return f"has con_id {record['con_id']!r}"
    if event == SKIPPED and record.get("reason") not in REASONS:
        return f"is skipped with reason {record.get('reason')!r}"
    return None


class StateInGitTree(ValueError):
    """A state path lies inside a git work tree."""


# --- the ledger ----------------------------------------------------------------------------


class Ledger:
    """Append-only JSONL file with the state per ``decision_key`` held in memory."""

    def __init__(
        self,
        path: Path,
        mode: str,
        clock: Callable[[], datetime],
        run_id: str,
        records: list[dict],
        needs_newline: bool,
        torn_line: int | None = None,
    ) -> None:
        self.path = path
        self.mode = mode
        self.run_id = run_id
        self.records = records
        self._clock = clock
        self._needs_newline = needs_newline
        self._torn_line = torn_line
        # Set when an append failed midway: part of its line may be on disk without a newline.
        self._tail_unknown = False
        # ``_check`` guarantees every ``seq`` is a positive int.
        self._seq = max((r["seq"] for r in records), default=0)

    @classmethod
    def open(
        cls, path: Path | str, *, mode: str, clock: Callable[[], datetime], run_id: str
    ) -> Ledger:
        if mode not in MODES:
            raise ValueError(f"unknown ledger mode: {mode!r}")
        path = Path(path)
        records: list[dict] = []
        needs_newline = False
        torn_line = None
        if path.exists():
            raw = path.read_bytes()
            if raw:
                ends_with_newline = raw.endswith(b"\n")
                needs_newline = not ends_with_newline
                parts = raw.split(b"\n")
                if ends_with_newline:
                    parts = parts[:-1]
                parsed: list[object] = []
                for part in parts:
                    try:
                        parsed.append(json.loads(part.decode("utf-8")))
                    except ValueError:
                        parsed.append(_BROKEN)
                last = len(parsed) - 1
                for index, record in enumerate(parsed):
                    number = index + 1
                    if record is _BROKEN:
                        if needs_newline and index == last:
                            torn_line = number
                            log.warning(
                                "ibkr-state=LEDGER_TORN_TAIL path=%s line=%d detail=%r",
                                path,
                                number,
                                "last line is cut off and is ignored",
                            )
                            continue
                        following = parsed[index + 1] if index < last else None
                        if isinstance(following, dict) and following.get(SEALS_LINE) == number:
                            # A torn tail from an earlier run, closed by the next append.
                            continue
                        raise LedgerError(f"{path}: line {number} is not a ledger record")
                    records.append(cls._check(path, number, record, mode))
        return cls(path, mode, clock, run_id, records, needs_newline, torn_line)

    @staticmethod
    def _check(path: Path, number: int, record: object, mode: str) -> dict:
        if not isinstance(record, dict):
            raise LedgerError(f"{path}: line {number} is not a ledger record")
        if record.get("v") != LEDGER_VERSION:
            raise LedgerError(f"{path}: line {number} has ledger version {record.get('v')!r}")
        if record.get("event") not in EVENTS:
            raise LedgerError(f"{path}: line {number} has unknown event {record.get('event')!r}")
        found = record.get("mode")
        if found != mode:
            raise LedgerError(f"{path}: line {number} has mode {found!r}, this ledger is {mode!r}")
        # Every field the executor reads later is checked here, so a malformed line is a
        # ``LedgerError`` at open and never a ``KeyError``/``ValueError`` deep in the run.
        problem = _schema_problem(record)
        if problem:
            raise LedgerError(f"{path}: line {number} {problem}")
        return record

    def append(self, event: str, **fields: object) -> dict:
        """Write one line durably (single write, flush, fsync); raise on any failure."""
        if event not in EVENTS:
            raise ValueError(f"unknown ledger event: {event!r}")
        if event == SKIPPED and fields.get("reason") not in REASONS:
            raise ValueError(f"skipped needs a reason from REASONS, got {fields.get('reason')!r}")
        if self._tail_unknown:
            self._inspect_tail()
        record = {
            "v": LEDGER_VERSION,
            "seq": self._seq + 1,
            "ts": self._clock().isoformat(),
            "run_id": self.run_id,
            "mode": self.mode,
            "event": event,
            **fields,
        }
        if event in (FILLED, PARTIAL, ALARM, RESOLVED):
            # Refuse a fill or alarm line the next open would reject, before it is written.
            problem = _schema_problem(record)
            if problem:
                raise LedgerError(f"{event} record {problem}")
        if self._torn_line is not None:
            record[SEALS_LINE] = self._torn_line
        line = (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        try:
            with open(self.path, "ab") as fh:
                if self._needs_newline:
                    fh.write(b"\n")
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            # A full disk or a network drive can leave part of the line on disk without its
            # newline. The next append looks at the tail first, so it never lands behind a
            # cut-off line unsealed (WR-01). The seq is used up: the line may be on disk.
            self._seq += 1
            self._tail_unknown = True
            raise
        self._seq += 1
        self._needs_newline = False
        self._torn_line = None
        self.records.append(record)
        return record

    def _inspect_tail(self) -> None:
        """After a failed append: find out what reached the disk and how to go on safely.

        * The file ends with a newline: either the failed line landed in full (it is taken
          into ``records``), or only the newline that closed an earlier torn tail did (that
          line still needs its seal, so ``_torn_line`` stays).
        * The file ends without one: the last line is cut off; the next append starts a new
          line and seals that line's number, like a torn tail found at open.
        """
        raw = self.path.read_bytes() if self.path.exists() else b""
        lines = raw.split(b"\n")
        ends_with_newline = raw.endswith(b"\n")
        last = lines[-2] if ends_with_newline and len(lines) > 1 else lines[-1]
        try:
            landed = json.loads(last.decode("utf-8"))
        except ValueError:
            landed = None
        if (
            isinstance(landed, dict)
            and landed.get("seq") == self._seq
            and landed.get("run_id") == self.run_id
            and not any(r.get("seq") == self._seq for r in self.records)
        ):
            # The failed line is on disk in full; it sealed the earlier torn tail, if any.
            self.records.append(landed)
            self._torn_line = None
        if ends_with_newline or not raw:
            self._needs_newline = False
        else:
            self._needs_newline = True
            if not isinstance(landed, dict):
                self._torn_line = len(lines)
        self._tail_unknown = False

    def _lifecycle(self, key: str) -> list[dict]:
        return [
            r
            for r in self.records
            if r.get("decision_key") == key and r["event"] in LIFECYCLE_EVENTS
        ]

    def last_event(self, key: str) -> dict | None:
        events = self._lifecycle(key)
        return events[-1] if events else None

    def attempt_of(self, key: str) -> dict | None:
        intents = [r for r in self._lifecycle(key) if r["event"] == INTENT]
        return intents[-1] if intents else None

    def unresolved(self) -> list[dict]:
        keys: list[str] = []
        for record in self.records:
            key = record.get("decision_key")
            if record["event"] == INTENT and key is not None and key not in keys:
                keys.append(key)
        open_intents: list[dict] = []
        for key in keys:
            events = self._lifecycle(key)
            index = max(i for i, r in enumerate(events) if r["event"] == INTENT)
            tail = events[index:]
            if tail[-1]["event"] in OPEN_EVENTS:
                open_intents.append(tail[0])
        return open_intents

    def filled_quantity(self, con_id: int) -> float:
        """Signed, correction-aware filled pieces for ``con_id`` (WR-07, REQ-47).

        BUY counts plus, SELL minus. Per decision key only the rows with an ``exec_id``
        count, one per execId family (the highest correction wins); a key with aggregate
        rows only (no ``exec_id``) counts those (Pitfall 5).
        """
        by_key: dict[str, list[dict]] = {}
        for r in self.records:
            if r["event"] in (FILLED, PARTIAL) and r.get("con_id") == con_id:
                by_key.setdefault(r.get("decision_key"), []).append(r)
        total = 0.0
        for rows in by_key.values():
            with_id = [r for r in rows if r.get("exec_id")]
            if with_id:
                best: dict[str, dict] = {}
                for r in with_id:
                    fam = exec_family(r["exec_id"])
                    kept = best.get(fam)
                    if kept is None or correction_rank(r["exec_id"]) >= correction_rank(
                        kept["exec_id"]
                    ):
                        best[fam] = r
                counted = list(best.values())
            else:
                counted = rows
            for r in counted:
                qty = float(r.get("filled_qty") or 0)
                total += qty if r.get("side") == "BUY" else -qty
        return total


def intent_record(
    *,
    decision_key: str,
    ticker: str,
    trade_date: str,
    rating: str,
    paper_log_sha: str,
    side: str,
    quantity: int | float,
    con_id: int,
    order_ref: str,
    weekend_gap: bool,
    rating_source: str | None = None,
) -> dict:
    """Fields for ``append(INTENT, **...)``; ``rating_source`` is ``engine`` or ``jev`` from summary.json (D-07)."""
    return {
        "decision_key": decision_key,
        "ticker": ticker,
        "trade_date": trade_date,
        "rating": rating,
        "paper_log_sha": paper_log_sha,
        "side": side,
        "quantity": quantity,
        "con_id": con_id,
        "order_ref": order_ref,
        "weekend_gap": weekend_gap,
        "rating_source": rating_source,
    }


# --- reconciliation (pure) ------------------------------------------------------------------

OPEN = "open"
FILLED_OUT = "filled"
PARTIAL_OUT = "partial"
NOT_FILLED = "not_filled"
NO_TRACE = "no_trace"
#: A dry-run intent without any trace at the broker: it was never sent (D-08). Resolved,
#: not unresolvable; only the dry-run ledger knows it.
NEVER_SENT = "never_sent"
COLLISION = "collision"
CONTRADICTION = "contradiction"
UNRESOLVABLE = frozenset({NO_TRACE, COLLISION, CONTRADICTION})

_CANCELLED = frozenset({"Cancelled", "ApiCancelled", "Inactive"})
_DONE = frozenset({"Filled", *_CANCELLED})


def exec_family(exec_id: str) -> str:
    """The execId without a trailing all-digit correction suffix (``...01.02`` -> ``...01``)."""
    head, dot, tail = exec_id.rpartition(".")
    if dot and head and tail.isdigit():
        return head
    return exec_id


def correction_rank(exec_id: str) -> int:
    """The numeric correction suffix of an execId; 0 without one."""
    _, dot, tail = exec_id.rpartition(".")
    return int(tail) if dot and tail.isdigit() else 0


def effective_executions(executions) -> list:
    """One execution per execId family: the highest correction, the later one on a tie.

    A correction (``.02`` after ``.01``) replaces the earlier one and is not added (REQ-47).
    The result keeps the order in which each family first appeared.
    """
    chosen: dict[str, object] = {}
    for execution in executions:
        family = exec_family(execution.exec_id)
        kept = chosen.get(family)
        if kept is None or correction_rank(execution.exec_id) >= correction_rank(kept.exec_id):
            chosen[family] = execution
    return list(chosen.values())


def fill_records(
    entry: dict, executions, *, known_exec_ids: frozenset | set = frozenset()
) -> list[tuple[str, dict]]:
    """Ledger ``(event, fields)`` pairs, one per effective execution (D-10, one code path).

    ``filled`` once the cumulative pieces reach the intent quantity, else ``partial``.
    Executions whose execId is in ``known_exec_ids`` are not written again. The caller
    adds ``source`` and any detail.
    """
    quantity = float(entry["quantity"])
    cumulative = 0.0
    records: list[tuple[str, dict]] = []
    for execution in effective_executions(executions):
        cumulative += float(execution.shares)
        if execution.exec_id in known_exec_ids:
            continue
        event = FILLED if cumulative >= quantity else PARTIAL
        records.append(
            (
                event,
                {
                    "decision_key": entry["decision_key"],
                    "ticker": entry.get("ticker"),
                    "con_id": entry["con_id"],
                    "side": entry["side"],
                    "order_ref": getattr(execution, "order_ref", None) or entry.get("order_ref"),
                    "exec_id": execution.exec_id,
                    "filled_qty": float(execution.shares),
                    "price": getattr(execution, "price", None),
                    "perm_id": getattr(execution, "perm_id", None),
                    "order_id": getattr(execution, "order_id", None),
                    "exec_time": getattr(execution, "time", None),
                },
            )
        )
    return records


@dataclass(frozen=True)
class Resolution:
    outcome: str
    detail: str
    open: int
    completed: int
    executions: int


def resolve_entry(entry: dict, history: object, *, dry: bool = False) -> Resolution:
    """Classify an open ledger entry against open orders, completed orders and executions.

    Matching is by exact ``orderRef`` on the client side. Unclear cases are unresolvable
    instead of guessed: "never sent" and "sent outside the query window" look the same.
    Only for an entry of the dry-run ledger (``dry=True``) is "no trace" certain: a dry
    intent is never sent, so it resolves as ``never_sent`` (WR-02, D-08).
    """
    key = entry.get("order_ref") or entry["decision_key"]
    side = entry["side"]
    quantity = float(entry["quantity"])
    con_id = entry["con_id"]
    completed = [o for o in history.completed if o.order_ref == key]
    # A finished order in the open answer is not open (WR-06): the same permId in the
    # completed answer is the same order, not a contradiction (the quantity is checked for
    # every record below); without that twin it counts as completed.
    # The gateway reports totalQuantity 0 on completed orders (first live order,
    # 2026-10-19, ibkr-konto-befund.md): a zero quantity says nothing about the size,
    # so it neither breaks the twin match nor counts as a different order.
    finished = {o.perm_id: float(o.quantity) for o in completed if getattr(o, "perm_id", 0)}
    opened = []
    for order in history.open:
        if order.order_ref != key:
            continue
        if order.status not in _DONE:
            opened.append(order)
        elif finished.get(getattr(order, "perm_id", 0)) not in (0.0, float(order.quantity)):
            completed.append(order)
    executions = [e for e in history.executions if e.order_ref == key]
    counts = f"open={len(opened)} completed={len(completed)} executions={len(executions)}"

    def result(outcome: str, why: str) -> Resolution:
        return Resolution(
            outcome, f"{key}: {why} ({counts})", len(opened), len(completed), len(executions)
        )

    for order in (*opened, *completed):
        size_differs = bool(order.quantity) and float(order.quantity) != quantity
        if order.con_id != con_id or order.action != side or size_differs:
            return result(COLLISION, "orderRef is not unique at IBKR")
    for execution in executions:
        if execution.con_id != con_id or execution.side != side:
            return result(COLLISION, "orderRef is not unique at IBKR")
    # Two different orders (permIds) under one orderRef: which one is ours is unclear.
    perm_ids = {getattr(o, "perm_id", 0) for o in (*opened, *completed)} - {0}
    if len(perm_ids) > 1:
        return result(COLLISION, "orderRef names more than one order at IBKR")
    if opened and completed:
        return result(CONTRADICTION, "order is both open and completed")
    if opened:
        return result(OPEN, "order is still open")
    shares = sum(float(e.shares) for e in effective_executions(executions))
    if shares > quantity:
        return result(CONTRADICTION, "executions exceed the ordered quantity")
    if executions:
        if shares == quantity:
            return result(FILLED_OUT, "executions cover the full quantity")
        return result(PARTIAL_OUT, f"executions cover {shares:g} of {quantity:g}")
    if completed:
        for order in completed:
            if order.status == "Filled":
                filled = order.filled
                if filled is not None and float(filled) == quantity:
                    return result(FILLED_OUT, "completed order reports a full fill")
                if filled is not None and 0 < float(filled) < quantity:
                    return result(PARTIAL_OUT, f"completed order reports {float(filled):g} filled")
                return result(CONTRADICTION, "order is Filled but nothing shows a fill")
            if order.status not in _CANCELLED:
                return result(CONTRADICTION, f"unexpected completed status {order.status!r}")
            # Partly filled, then cancelled (a market-order rest at the close, a kill cancel):
            # the next day the completed order is often the only trace of the fill.
            filled = order.filled
            if filled is not None and float(filled) > 0:
                if float(filled) >= quantity:
                    return result(CONTRADICTION, f"{order.status} order reports a full fill")
                return result(PARTIAL_OUT, f"{order.status} after {float(filled):g} filled")
        return result(NOT_FILLED, "order was cancelled without a fill")
    if dry:
        return result(NEVER_SENT, "dry-run intent, no trace at the broker: never sent")
    return result(NO_TRACE, "no trace at the broker")


# --- state outside git ----------------------------------------------------------------------


def ensure_outside_git(path: Path | str) -> None:
    """Refuse a state path with a ``.git`` (directory or file) in it or above it."""
    start = Path(path).resolve()
    for folder in (start, *start.parents):
        try:
            os.stat(folder / ".git")
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise StateInGitTree(
                f"{path}: cannot rule out a git work tree at {folder} ({exc})"
            ) from None
        raise StateInGitTree(f"{path} lies inside the git work tree {folder}")
