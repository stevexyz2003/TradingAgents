"""Library-free guard blocks for the phase-5 ``execute`` chain: no client library, no clock.

Everything here is a pure function or a frozen value, so every guard can be tested
without a gateway. The current UTC date is a parameter, never read here.

* the release file and the kill file, read fail-closed (D-01, D-03, D-17, D-20),
* the combined switch state that ``execute`` checks before every single order,
* the hard size limit that rejects instead of trimming (D-09, REQ-IBKR-32),
* the idempotency key ``decision_key`` (REQ-IBKR-39),
* three of the four source comparisons of REQ-IBKR-63 (account, position, "already
  executed?"). The fourth fact, tradability, is compared by
  ``ibkr_decision.calendar_conflict`` (exchange calendar against the broker's
  trading hours); order status 399 as a further source arrives with the placer of
  phase 6 (D-22),
* named states with their own exit table and a ranking for the run exit.

Every reason to stop is its own named state; ``EXIT_BY_STATE`` is the one table that
maps a state to a process exit code.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType

log = logging.getLogger(__name__)

# --- named states ------------------------------------------------------------------------

RELEASE_OK = "release-ok"
RELEASE_MISSING = "release-missing"
RELEASE_UNREADABLE = "release-unreadable"
RELEASE_INVALID = "release-invalid"
RELEASE_EXPIRED = "release-expired"
RELEASE_ACCOUNT_MISMATCH = "release-account-mismatch"
KILL_ABSENT = "kill-absent"
KILL_ACTIVE = "kill-active"
KILL_UNREADABLE = "kill-unreadable"
SIZE_CAP = "size-cap"
OUTSIDE_SESSION = "outside-session"
SOURCE_CONFLICT = "source-conflict"
ACCOUNT_CONFLICT = "account-conflict"
ALREADY_ATTEMPTED = "already-attempted"
DECISION_CHANGED = "decision-changed"
INVALID_DECISION_KEY = "invalid-decision-key"
DRY_COMPLETE = "dry-complete"
LOCK_HELD = "lock-held"
LOCK_ERROR = "lock-error"
LEDGER_CORRUPT = "ledger-corrupt"
RECONCILE_UNRESOLVED = "reconcile-unresolved"
STATE_IN_GIT_TREE = "state-in-git-tree"
NOT_DRY = "not-dry"

# Values mirror EXIT_OK ... EXIT_ACCOUNT_GUARD from scripts/ibkr_executor.py; the
# equality test lives in tests/test_ibkr_execute.py (plan 05-04).
(
    _EXIT_OK,
    _EXIT_CONFIG,
    _EXIT_PRECONDITION,
    _EXIT_GATEWAY,
    _EXIT_KILL_SWITCH,
    _EXIT_REJECTED,
    _EXIT_RECONCILE,
    _EXIT_LOCKED,
    _EXIT_ACCOUNT_GUARD,
) = (0, 1, 2, 3, 4, 5, 6, 7, 8)

EXIT_BY_STATE: Mapping[str, int] = MappingProxyType(
    {
        **dict.fromkeys((RELEASE_OK, KILL_ABSENT, DRY_COMPLETE), _EXIT_OK),
        **dict.fromkeys(
            (
                RELEASE_MISSING,
                RELEASE_UNREADABLE,
                RELEASE_INVALID,
                RELEASE_EXPIRED,
                RELEASE_ACCOUNT_MISMATCH,
                KILL_ACTIVE,
                KILL_UNREADABLE,
            ),
            _EXIT_KILL_SWITCH,
        ),
        SIZE_CAP: _EXIT_REJECTED,
        **dict.fromkeys(
            (
                OUTSIDE_SESSION,
                SOURCE_CONFLICT,
                ALREADY_ATTEMPTED,
                DECISION_CHANGED,
                INVALID_DECISION_KEY,
            ),
            _EXIT_PRECONDITION,
        ),
        ACCOUNT_CONFLICT: _EXIT_ACCOUNT_GUARD,
        **dict.fromkeys((LOCK_HELD, LOCK_ERROR), _EXIT_LOCKED),
        **dict.fromkeys((LEDGER_CORRUPT, RECONCILE_UNRESOLVED), _EXIT_RECONCILE),
        **dict.fromkeys((STATE_IN_GIT_TREE, NOT_DRY), _EXIT_CONFIG),
    }
)

#: Rank for the run exit, ascending: 0 < 2 < 5 < 1 < 3 < 8 < 6 < 7 < 4.
#: The kill switch always wins; 6 and 7 beat everything else; below that 1 > 5 > 2 > 0.
_RUN_EXIT_RANK = {
    code: rank
    for rank, code in enumerate(
        (
            _EXIT_OK,
            _EXIT_PRECONDITION,
            _EXIT_REJECTED,
            _EXIT_CONFIG,
            _EXIT_GATEWAY,
            _EXIT_ACCOUNT_GUARD,
            _EXIT_RECONCILE,
            _EXIT_LOCKED,
            _EXIT_KILL_SWITCH,
        )
    )
}


def worst_run_exit(codes: Iterable[int]) -> int:
    """Combine exit codes into one run exit; an empty sequence is 0."""
    worst = _EXIT_OK
    for code in codes:
        if _RUN_EXIT_RANK[code] > _RUN_EXIT_RANK[worst]:
            worst = code
    return worst


# --- release and kill files ---------------------------------------------------------------

KILL_FILE_NAME = "KILL"
RELEASE_FILE_NAME = "RELEASE"
RELEASE_KEYS = frozenset({"account", "valid_until"})
MAX_RELEASE_BYTES = 4096
MAX_RELEASE_DAYS = 90

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class KillState:
    state: str
    detail: str = ""

    @property
    def active(self) -> bool:
        return self.state == KILL_ACTIVE


@dataclass(frozen=True)
class ReleaseState:
    state: str
    detail: str = ""
    valid_until: date | None = None
    account: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == RELEASE_OK


def is_kill_name(name: str) -> bool:
    """``KILL`` or ``KILL.<anything>``, in any case (``KILL.txt``, ``kill.TXT``).

    Explorer hides file endings by default: "New > Text Document" named ``KILL`` is
    ``KILL.txt`` on disk, and the stop switch must not fail open on that (WR-03).
    """
    folded = name.casefold()
    kill = KILL_FILE_NAME.casefold()
    return folded == kill or folded.startswith(kill + ".")


def read_kill(state_dir: str | os.PathLike[str]) -> KillState:
    """Three outcomes: present, absent, anything else is unreadable (D-03).

    First ``os.stat`` on ``KILL`` itself, then a listing of the state folder for any
    entry that ``is_kill_name`` (``KILL.txt`` and the like). Only a positive hit (file or
    directory) is ``kill-active``. A permission error, a folder that cannot be listed or
    any other failure is ``kill-unreadable``: trading stops, but nothing is cancelled
    (D-17). Existence helpers swallow such errors into "absent" and would fail open.
    """
    try:
        os.stat(os.path.join(os.fspath(state_dir), KILL_FILE_NAME))
    except FileNotFoundError:
        return _kill_by_listing(state_dir)
    except OSError as exc:
        return KillState(KILL_UNREADABLE, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 - every surprise means "blocked", never "allowed"
        return KillState(KILL_UNREADABLE, type(exc).__name__)
    return KillState(KILL_ACTIVE)


def _kill_by_listing(state_dir: str | os.PathLike[str]) -> KillState:
    """No exact ``KILL``: list the folder. Windows also reports "not found" when the state
    folder is a plain file; listing it fails, which is ``kill-unreadable``."""
    try:
        names = os.listdir(os.fspath(state_dir))
    except FileNotFoundError:
        return KillState(KILL_ABSENT)  # no folder, so no kill file in it
    except Exception as exc:  # noqa: BLE001 - blocked, never allowed
        return KillState(KILL_UNREADABLE, type(exc).__name__)
    hits = sorted(name for name in names if is_kill_name(name))
    if hits:
        return KillState(KILL_ACTIVE, f"{hits[0]} present")
    return KillState(KILL_ABSENT)


def read_release(
    path: str | os.PathLike[str], *, today_utc: date, expected_account: str
) -> ReleaseState:
    """Parse the release file strictly; every defect is its own non-ok state (D-01, D-02, D-20)."""
    try:
        return _read_release(path, today_utc, expected_account)
    except Exception as exc:  # noqa: BLE001 - fail-closed: surprises are "unreadable"
        return ReleaseState(RELEASE_UNREADABLE, type(exc).__name__)


def _read_release(
    path: str | os.PathLike[str], today_utc: date, expected_account: str
) -> ReleaseState:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_RELEASE_BYTES + 1)
    except FileNotFoundError:
        return ReleaseState(RELEASE_MISSING)
    except OSError as exc:
        return ReleaseState(RELEASE_UNREADABLE, type(exc).__name__)
    if len(raw) > MAX_RELEASE_BYTES:
        return ReleaseState(RELEASE_INVALID, "file too large")
    try:
        text = raw.decode("utf-8-sig")
        body = json.loads(text)
    except ValueError:  # UnicodeDecodeError and JSONDecodeError are both ValueErrors
        return ReleaseState(
            RELEASE_INVALID, "not UTF-8 JSON (write it with the handbook one-liner)"
        )
    if not isinstance(body, dict) or set(body) != RELEASE_KEYS:
        return ReleaseState(RELEASE_INVALID, "keys must be exactly account and valid_until")
    account, valid_text = body["account"], body["valid_until"]
    if not isinstance(account, str) or not isinstance(valid_text, str):
        return ReleaseState(RELEASE_INVALID, "account and valid_until must be text")
    if not _DATE_RE.match(valid_text):
        return ReleaseState(RELEASE_INVALID, "valid_until must look like YYYY-MM-DD")
    try:
        valid_until = date.fromisoformat(valid_text)
    except ValueError:
        return ReleaseState(RELEASE_INVALID, "valid_until is not a calendar date")
    if account != expected_account:
        return ReleaseState(
            RELEASE_ACCOUNT_MISMATCH,
            f"release names {account!r}, expected {expected_account!r}",
            valid_until,
            account,
        )
    if today_utc > valid_until:
        return ReleaseState(RELEASE_EXPIRED, f"valid_until {valid_text}", valid_until, account)
    if valid_until > today_utc + timedelta(days=MAX_RELEASE_DAYS):
        return ReleaseState(
            RELEASE_INVALID,
            f"valid_until more than {MAX_RELEASE_DAYS} days ahead",
            valid_until,
            account,
        )
    return ReleaseState(RELEASE_OK, "", valid_until, account)


@dataclass(frozen=True)
class Switches:
    release: ReleaseState
    kill: KillState

    @property
    def allowed(self) -> bool:
        return self.release.ok and self.kill.state == KILL_ABSENT

    @property
    def cancel(self) -> bool:
        """Only a positively present kill file triggers the cancel (D-17)."""
        return self.kill.active

    @property
    def blocking_state(self) -> str | None:
        if self.kill.state != KILL_ABSENT:
            return self.kill.state
        if not self.release.ok:
            return self.release.state
        return None

    def as_record(self) -> dict:
        return {
            "release": self.release.state,
            "release_detail": self.release.detail,
            "valid_until": self.release.valid_until.isoformat()
            if self.release.valid_until
            else None,
            "release_account": self.release.account,
            "kill": self.kill.state,
            "kill_detail": self.kill.detail,
        }


def check_switches(
    state_dir: str | os.PathLike[str], *, today_utc: date, expected_account: str
) -> Switches:
    """Read both files anew on every call; there is no cache (D-04, REQ-IBKR-34)."""
    release = read_release(
        os.path.join(os.fspath(state_dir), RELEASE_FILE_NAME),
        today_utc=today_utc,
        expected_account=expected_account,
    )
    return Switches(release=release, kill=read_kill(state_dir))


# --- size cap ----------------------------------------------------------------------------

#: A code constant: every change is a commit (D-09). It equals the largest order D-10 of
#: phase 4 can produce today (Buy = 2 blocks of 1). Raise it deliberately, never by accident.
MAX_QTY_PER_ORDER = 2


def check_size(quantity: object) -> str | None:
    """Return a reason to reject the order, or None. Never returns a trimmed quantity (REQ-IBKR-32)."""
    if type(quantity) is not int or quantity <= 0:  # excludes bool and float on purpose
        return f"quantity {quantity!r} is not a positive whole number"
    if quantity > MAX_QTY_PER_ORDER:
        return f"quantity {quantity} exceeds MAX_QTY_PER_ORDER {MAX_QTY_PER_ORDER}"
    return None


# --- idempotency key ---------------------------------------------------------------------

#: Unmeasured at the gateway (assumption A3); the operator checkpoint measures it, '_' is the fallback.
DECISION_KEY_SEPARATOR = "|"

_TRADE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


def decision_key(trade_date: str, ticker: str) -> str:
    """``<trade_date><sep><ticker>``, whitelisted parts, no hash (REQ-IBKR-39)."""
    if not isinstance(trade_date, str) or not _TRADE_DATE_RE.match(trade_date):
        raise ValueError(f"invalid trade date: {trade_date!r}")
    try:
        date.fromisoformat(trade_date)
    except ValueError:
        raise ValueError(f"invalid trade date: {trade_date!r}") from None
    if not isinstance(ticker, str) or not _TICKER_RE.match(ticker):
        raise ValueError(f"invalid ticker: {ticker!r}")
    return f"{trade_date}{DECISION_KEY_SEPARATOR}{ticker}"


# --- source comparisons (REQ-IBKR-63: the more cautious value wins) --------------------------


def account_conflict(
    *, managed_account: str, release_account: str | None, echo_account: str | None
) -> str | None:
    """A reason if the account sources disagree. The order echo is optional (D-22)."""
    if release_account and release_account != managed_account:
        return f"release names account {release_account!r}, broker manages {managed_account!r}"
    if echo_account and echo_account != managed_account:
        return f"order echo names account {echo_account!r}, broker manages {managed_account!r}"
    return None


def position_conflict(*, ledger_filled_qty: float, broker_held: float) -> str | None:
    """A reason only if the ledger knows own fills and the broker holds less (D-18, narrow rule).

    Without own fills in the ledger there is no conflict. Phase 6/7 sharpen this for
    sells and foreign holdings once fills are processed.
    """
    if ledger_filled_qty > 0 and broker_held < ledger_filled_qty:
        return f"ledger has {ledger_filled_qty:g} filled, broker holds {broker_held:g}"
    return None


def executed_conflict(*, ledger_attempted: bool, history_has_ref: bool) -> str | None:
    """A reason if ledger and broker history disagree on "already executed?".

    "Ledger yes, broker no" is a matter for the reconciliation (exit 6); "broker yes,
    ledger no" is a ticker conflict (``source-conflict``).
    """
    if history_has_ref and not ledger_attempted:
        return "broker shows an order with this orderRef, ledger has none"
    if ledger_attempted and not history_has_ref:
        return "ledger says attempted, broker shows no trace"
    return None
