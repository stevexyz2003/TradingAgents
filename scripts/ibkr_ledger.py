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
    }
)
#: Only these events move the state of a decision key; reconcile, switch_check, skipped
#: and the run events never do, so an unresolvable intent stays open in every later run.
LIFECYCLE_EVENTS = frozenset({INTENT, PLACED, FILLED, PARTIAL, REJECTED, DRY_COMPLETE})
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
    }
)


def reason_for_state(state: str) -> str:
    """Reason for a skipped ticker; an unknown state raises ``KeyError`` (no default)."""
    return REASON_BY_STATE[state]


class LedgerError(ValueError):
    """The ledger file cannot be trusted (broken middle line, foreign mode, bad record)."""


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
    ) -> None:
        self.path = path
        self.mode = mode
        self.run_id = run_id
        self.records = records
        self._clock = clock
        self._needs_newline = needs_newline
        self._seq = max((int(r.get("seq", 0)) for r in records), default=0)

    @classmethod
    def open(
        cls, path: Path | str, *, mode: str, clock: Callable[[], datetime], run_id: str
    ) -> Ledger:
        if mode not in MODES:
            raise ValueError(f"unknown ledger mode: {mode!r}")
        path = Path(path)
        records: list[dict] = []
        needs_newline = False
        if path.exists():
            raw = path.read_bytes()
            if raw:
                ends_with_newline = raw.endswith(b"\n")
                needs_newline = not ends_with_newline
                parts = raw.split(b"\n")
                if ends_with_newline:
                    parts = parts[:-1]
                last = len(parts) - 1
                for index, part in enumerate(parts):
                    number = index + 1
                    torn = needs_newline and index == last
                    try:
                        record = json.loads(part.decode("utf-8"))
                    except ValueError:
                        if torn:
                            log.warning(
                                "ibkr-state=LEDGER_TORN_TAIL path=%s line=%d detail=%r",
                                path,
                                number,
                                "last line is cut off and is ignored",
                            )
                            continue
                        raise LedgerError(f"{path}: line {number} is not a ledger record") from None
                    records.append(cls._check(path, number, record, mode))
        return cls(path, mode, clock, run_id, records, needs_newline)

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
        return record

    def append(self, event: str, **fields: object) -> dict:
        """Write one line durably (single write, flush, fsync); raise on any failure."""
        if event not in EVENTS:
            raise ValueError(f"unknown ledger event: {event!r}")
        if event == SKIPPED and fields.get("reason") not in REASONS:
            raise ValueError(f"skipped needs a reason from REASONS, got {fields.get('reason')!r}")
        record = {
            "v": LEDGER_VERSION,
            "seq": self._seq + 1,
            "ts": self._clock().isoformat(),
            "run_id": self.run_id,
            "mode": self.mode,
            "event": event,
            **fields,
        }
        line = (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        with open(self.path, "ab") as fh:
            if self._needs_newline:
                fh.write(b"\n")
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._seq += 1
        self._needs_newline = False
        self.records.append(record)
        return record

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
        return float(
            sum(
                float(r.get("filled_qty") or 0)
                for r in self.records
                if r["event"] in (FILLED, PARTIAL) and r.get("con_id") == con_id
            )
        )


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
    """Fields for ``append(INTENT, **...)``; ``rating_source`` stays ``None`` (D-23)."""
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
COLLISION = "collision"
CONTRADICTION = "contradiction"
UNRESOLVABLE = frozenset({NO_TRACE, COLLISION, CONTRADICTION})

_CANCELLED = frozenset({"Cancelled", "ApiCancelled", "Inactive"})


@dataclass(frozen=True)
class Resolution:
    outcome: str
    detail: str
    open: int
    completed: int
    executions: int


def resolve_entry(entry: dict, history: object) -> Resolution:
    """Classify an open ledger entry against open orders, completed orders and executions.

    Matching is by exact ``orderRef`` on the client side. Unclear cases are unresolvable
    instead of guessed: "never sent" and "sent outside the query window" look the same.
    """
    key = entry.get("order_ref") or entry["decision_key"]
    side = entry["side"]
    quantity = float(entry["quantity"])
    con_id = entry["con_id"]
    opened = [o for o in history.open if o.order_ref == key]
    completed = [o for o in history.completed if o.order_ref == key]
    executions = [e for e in history.executions if e.order_ref == key]
    counts = f"open={len(opened)} completed={len(completed)} executions={len(executions)}"

    def result(outcome: str, why: str) -> Resolution:
        return Resolution(
            outcome, f"{key}: {why} ({counts})", len(opened), len(completed), len(executions)
        )

    for order in (*opened, *completed):
        if order.con_id != con_id or order.action != side or float(order.quantity) != quantity:
            return result(COLLISION, "orderRef is not unique at IBKR")
    for execution in executions:
        if execution.con_id != con_id or execution.side != side:
            return result(COLLISION, "orderRef is not unique at IBKR")
    if opened and completed:
        return result(CONTRADICTION, "order is both open and completed")
    if opened:
        return result(OPEN, "order is still open")
    shares = sum(float(e.shares) for e in executions)
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
        return result(NOT_FILLED, "order was cancelled without a fill")
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
