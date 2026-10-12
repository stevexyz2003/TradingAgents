"""IBKR contract core: raw ticker -> IBKR search key, allow-list, identity, session.

Library-free: no client library, no tradingagents import. Everything in here is a
pure function or a frozen value, so the decision chain can be tested without a
gateway. The mapping table is a code constant; every table change is a commit plus
a one-off ``resolve <TICKER>`` trial run against the paper gateway (D-08).

The table holds search keys only. The contract id and the local symbol are never
stored here; they are read from the broker at resolve time and compared against
the persisted identity (D-02, D-09). The resolver does not use the vendor symbol
normalizer: that path maps tickers for data vendors and would turn a spot-gold
ticker into a futures symbol (D-07).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

#: Only plain stocks may be traded in this phase (REQ-IBKR-28). Extending this set
#: is a code change and a review, never a configuration switch.
ALLOWED_SEC_TYPES = frozenset({"STK"})

#: Minutes kept free at both ends of a liquid window (D-21). No clock time is
#: hard-coded anywhere; the window itself comes from the broker.
SESSION_BUFFER_MINUTES = 15

SMART = "SMART"
VALUE_EXCHANGE = "VALUE"
REQUIRED_ORDER_TYPES = frozenset({"MKT", "LMT"})

#: Ticker used by the resolver as a sanity anchor (D-13).
ANCHOR_TICKER = "AAPL"

# --- named states ------------------------------------------------------------------------

OK = "ok"
NOT_MAPPED = "not-mapped"
NOT_ALLOWED = "not-allowed"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not-found"
DRIFT = "drift"
NOT_TRADABLE = "not-tradable"
CLOSED = "closed"
SESSION_UNKNOWN = "session-unknown"
#: Never set in phase 3. A later phase sets it after the broker reports a halted
#: instrument at the what-if step. "Unknown" does not mean "not halted" (D-20).
HALTED = "halted"

#: States that stop an order. ``closed`` and ``ok`` are not rejections (D-28, D-29).
REJECTED_STATES = frozenset(
    {NOT_MAPPED, NOT_ALLOWED, AMBIGUOUS, NOT_FOUND, DRIFT, NOT_TRADABLE, SESSION_UNKNOWN, HALTED}
)


# --- mapping table -----------------------------------------------------------------------


@dataclass(frozen=True)
class ContractSpec:
    """Search key for the broker's contract lookup. No contract id, no local symbol."""

    symbol: str
    sec_type: str
    exchange: str
    currency: str
    primary_exchange: str


def _stock(ticker: str) -> ContractSpec:
    return ContractSpec(ticker, "STK", SMART, "USD", "NASDAQ")


#: Source: .planning/ibkr-konto-befund.md section 4. Lookup is exact and
#: case-sensitive; there are no aliases (D-03, D-05).
CONTRACT_TABLE: Mapping[str, ContractSpec] = MappingProxyType(
    {
        "AAPL": _stock("AAPL"),
        "MSFT": _stock("MSFT"),
        "NVDA": _stock("NVDA"),
        # Not tradable here: real secType is kept so the allow-list rejects them (D-04).
        "^GSPC": ContractSpec("SPX", "IND", "CBOE", "USD", ""),
        "XAUUSD+": ContractSpec("XAUUSD", "CMDTY", SMART, "USD", ""),
    }
)


@dataclass(frozen=True)
class LocalVerdict:
    """Outcome of the local, broker-free classification."""

    ticker: str
    state: str
    spec: ContractSpec | None
    detail: str


def classify(raw: str) -> LocalVerdict:
    """Look the raw ticker up exactly as given (no strip, no case folding)."""
    spec = CONTRACT_TABLE.get(raw)
    if spec is None:
        return LocalVerdict(
            raw, NOT_MAPPED, None, f"{raw!r}: no entry in the contract table; nothing tried"
        )
    if spec.sec_type not in ALLOWED_SEC_TYPES:
        return LocalVerdict(
            raw,
            NOT_ALLOWED,
            spec,
            f"{raw!r}: secType {spec.sec_type} is not in the allow-list {{STK}}",
        )
    return LocalVerdict(raw, OK, spec, "mapped; broker lookup required")


# --- tradability -------------------------------------------------------------------------


def _csv_set(text: str) -> set[str]:
    return {part.strip() for part in (text or "").split(",") if part.strip()}


def check_tradable(valid_exchanges: str, order_types: str) -> str | None:
    """Return None when tradable, else the reason. Empty input is never tradable (D-19)."""
    exchanges = _csv_set(valid_exchanges)
    types = _csv_set(order_types)
    if not exchanges:
        return "validExchanges is empty"
    if not types:
        return "orderTypes is empty"
    if exchanges == {VALUE_EXCHANGE}:
        return f"validExchanges lists only {VALUE_EXCHANGE}"
    if SMART not in exchanges:
        return f"{SMART} is missing from validExchanges"
    missing = sorted(REQUIRED_ORDER_TYPES - types)
    if missing:
        return f"orderTypes lacks {', '.join(missing)}"
    return None


# --- identity ----------------------------------------------------------------------------

IDENTITY_FIELDS = ("conId", "primaryExchange", "currency", "localSymbol")


@dataclass(frozen=True)
class Identity:
    """The four fields whose change means the instrument is no longer the same (D-09)."""

    con_id: int
    primary_exchange: str
    currency: str
    local_symbol: str


def identity_of(info) -> Identity:
    """Build an Identity from any object with the four attributes; extras are ignored."""
    return Identity(
        con_id=info.con_id,
        primary_exchange=info.primary_exchange,
        currency=info.currency,
        local_symbol=info.local_symbol,
    )


def identity_diff(expected: Identity, seen: Identity) -> tuple[str, ...]:
    """Names (from IDENTITY_FIELDS) of the fields that differ, in fixed order."""
    pairs = (
        ("conId", expected.con_id, seen.con_id),
        ("primaryExchange", expected.primary_exchange, seen.primary_exchange),
        ("currency", expected.currency, seen.currency),
        ("localSymbol", expected.local_symbol, seen.local_symbol),
    )
    return tuple(name for name, a, b in pairs if a != b)


# --- session -----------------------------------------------------------------------------


class SessionParseError(ValueError):
    """The liquid-hours text or its time zone could not be read; never guessed around."""


@dataclass(frozen=True)
class SessionWindow:
    """One liquid window; both ends are aware datetimes in the contract's zone."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class LiquidHours:
    windows: tuple[SessionWindow, ...]
    closed_dates: frozenset[date]
    time_zone_id: str


@dataclass(frozen=True)
class SessionVerdict:
    state: str
    window: SessionWindow | None
    next_open: datetime | None
    detail: str


_STAMP = "%Y%m%d:%H%M"
_CLOSED_SUFFIX = ":CLOSED"


def _load_zone(time_zone_id: str) -> ZoneInfo:
    try:
        return ZoneInfo(time_zone_id)
    except (ValueError, TypeError, OSError, KeyError) as exc:
        # ZoneInfoNotFoundError is a KeyError subclass.
        raise SessionParseError(f"unusable time zone {time_zone_id!r}: {exc}") from exc


def _parse_window(segment: str, zone: ZoneInfo) -> SessionWindow:
    parts = segment.split("-")
    if len(parts) != 2:
        raise SessionParseError(f"unreadable liquid-hours segment {segment!r}")
    left, right = parts
    try:
        start = datetime.strptime(left, _STAMP).replace(tzinfo=zone)
        if ":" in right:
            end = datetime.strptime(right, _STAMP).replace(tzinfo=zone)
        else:
            # Old format: the end carries only the time and falls on the start date.
            end_time = datetime.strptime(right, "%H%M")
            end = start.replace(hour=end_time.hour, minute=end_time.minute)
    except ValueError as exc:
        raise SessionParseError(f"unreadable liquid-hours segment {segment!r}") from exc
    if end <= start:
        raise SessionParseError(f"window ends before it starts in segment {segment!r}")
    return SessionWindow(start, end)


def parse_liquid_hours(raw: str, time_zone_id: str) -> LiquidHours:
    """Parse the broker's liquid-hours text (new and old format) into aware windows."""
    zone = _load_zone(time_zone_id)
    windows: list[SessionWindow] = []
    closed: set[date] = set()
    for segment in (raw or "").split(";"):
        if not segment:
            continue
        if segment.endswith(_CLOSED_SUFFIX):
            day = segment[: -len(_CLOSED_SUFFIX)]
            try:
                closed.add(datetime.strptime(day, "%Y%m%d").date())
            except ValueError as exc:
                raise SessionParseError(f"unreadable liquid-hours segment {segment!r}") from exc
            continue
        windows.append(_parse_window(segment, zone))
    windows.sort(key=lambda w: w.start)
    return LiquidHours(tuple(windows), frozenset(closed), time_zone_id)


def evaluate_session(
    liquid_hours: str,
    time_zone_id: str,
    now_utc: datetime,
    buffer_minutes: int = SESSION_BUFFER_MINUTES,
) -> SessionVerdict:
    """Decide whether the instrument may be traded at ``now_utc``.

    The caller passes the current time as ``now_utc`` (aware); this function never
    reads a clock, and the hours are never persisted (D-22). ``ok`` needs the
    moment to lie inside a window shrunk by the buffer at both ends. A day with
    neither a window nor a closed entry is ``session-unknown``, not ``closed`` (D-24).
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
    try:
        parsed = parse_liquid_hours(liquid_hours, time_zone_id)
    except SessionParseError as exc:
        return SessionVerdict(SESSION_UNKNOWN, None, None, str(exc))

    buffer = timedelta(minutes=buffer_minutes)
    usable = [w for w in parsed.windows if w.start + buffer <= w.end - buffer]
    for window in usable:
        if window.start + buffer <= now_utc <= window.end - buffer:
            return SessionVerdict(OK, window, None, "inside a liquid window")

    upcoming = [w.start + buffer for w in usable if w.start + buffer > now_utc]
    next_open = min(upcoming) if upcoming else None

    zone = ZoneInfo(time_zone_id)
    today = now_utc.astimezone(zone).date()
    covered = today in parsed.closed_dates or any(
        w.start.date() <= today <= w.end.date() for w in parsed.windows
    )
    if not covered:
        return SessionVerdict(
            SESSION_UNKNOWN, None, next_open, f"no liquid-hours entry for {today.isoformat()}"
        )
    if today in parsed.closed_dates and not any(
        w.start.date() <= today <= w.end.date() for w in parsed.windows
    ):
        detail = "closed today"
    elif any(w.start <= now_utc <= w.end for w in parsed.windows):
        detail = "inside the opening or closing buffer"
    else:
        detail = "outside every liquid window"
    return SessionVerdict(CLOSED, None, next_open, detail)


# --- persistence (D-11, D-12, D-14, D-18, D-22) ------------------------------------------

HISTORY_FILE_NAME = "contracts-history.jsonl"
_ENTRY_KEYS = frozenset({"conId", "primaryExchange", "currency", "localSymbol", "learned_at"})


@dataclass(frozen=True)
class StoredContract:
    """A persisted identity plus the moment it was learned. No session values (D-22)."""

    identity: Identity
    learned_at: str


@dataclass(frozen=True)
class HistoryEvent:
    """One append-only history line: ``init``, ``learn`` or ``rebaseline`` (D-18)."""

    event: str
    ticker: str
    old: Identity | None
    new: Identity
    reason: str
    at: str


class ContractsFileMissing(FileNotFoundError):
    """The contracts file does not exist; it is never recreated silently (D-12)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"{self.path} not found - create it with: resolve --init AAPL ...")


class ContractsFileError(ValueError):
    """The contracts file exists but is unreadable or violates the schema (D-14)."""


def contracts_history_path(path: Path) -> Path:
    return Path(path).with_name(HISTORY_FILE_NAME)


def _identity_json(identity: Identity) -> dict:
    return {
        "conId": identity.con_id,
        "primaryExchange": identity.primary_exchange,
        "currency": identity.currency,
        "localSymbol": identity.local_symbol,
    }


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_contracts(path: Path, data) -> dict[str, StoredContract]:
    def fail(reason: str):
        raise ContractsFileError(f"{path}: {reason}")

    if not isinstance(data, dict):
        fail("top level is not a JSON object")
    if set(data) != {"schema_version", "contracts"}:
        fail(f"top-level keys must be exactly schema_version and contracts, got {sorted(data)}")
    version = data["schema_version"]
    if not _is_int(version) or version != SCHEMA_VERSION:
        fail(f"schema_version must be {SCHEMA_VERSION}, got {version!r}")
    raw = data["contracts"]
    if not isinstance(raw, dict):
        fail("contracts is not a JSON object")
    out: dict[str, StoredContract] = {}
    for ticker, entry in raw.items():
        if not isinstance(entry, dict):
            fail(f"entry {ticker!r} is not a JSON object")
        if set(entry) != _ENTRY_KEYS:
            fail(f"entry {ticker!r} must have exactly {sorted(_ENTRY_KEYS)}, got {sorted(entry)}")
        con_id = entry["conId"]
        if not _is_int(con_id) or con_id <= 0:
            fail(f"entry {ticker!r}: conId must be an integer > 0, got {con_id!r}")
        for key in ("primaryExchange", "currency", "localSymbol", "learned_at"):
            value = entry[key]
            if not isinstance(value, str) or not value:
                fail(f"entry {ticker!r}: {key} must be a non-empty string, got {value!r}")
        out[ticker] = StoredContract(
            Identity(con_id, entry["primaryExchange"], entry["currency"], entry["localSymbol"]),
            entry["learned_at"],
        )
    return out


def load_contracts_file(path: Path) -> dict[str, StoredContract]:
    """Read and strictly validate the contracts file; never fall back to relearning."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContractsFileMissing(path) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractsFileError(f"{path}: unreadable ({type(exc).__name__})") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractsFileError(f"{path}: not valid JSON ({type(exc).__name__})") from exc
    return _parse_contracts(path, data)


def contracts_payload(contracts: Mapping[str, StoredContract]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "contracts": {
            ticker: {**_identity_json(stored.identity), "learned_at": stored.learned_at}
            for ticker, stored in sorted(contracts.items())
        },
    }


def _temp_for(path: Path) -> Path:
    return path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json_atomic(path: Path, payload: dict, check=None) -> None:
    """Write through a uniquely named temp file beside ``path``, then move it into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_for(path)
    try:
        with open(temp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_dump(payload))
            fh.flush()
            os.fsync(fh.fileno())
        if check is not None:
            check(temp)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _history_line(event: HistoryEvent, name: str | None = None, reason: str | None = None) -> str:
    row = {
        "at": event.at,
        "event": name or event.event,
        "ticker": event.ticker,
        "old": None if event.old is None else _identity_json(event.old),
        "new": _identity_json(event.new),
        "reason": event.reason if reason is None else reason,
    }
    return json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"


def _append_history(history: Path, lines: Sequence[str]) -> None:
    with open(history, "a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
        fh.flush()
        os.fsync(fh.fileno())


def _snapshot_bytes(path: Path) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        return None


def _lock_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(f"{path.name}.lock")


class ContractsCommitError(ContractsFileError):
    """A contracts commit could not be completed safely."""


_EXPECTED_UNSET = object()


def commit_contracts(
    path: Path,
    contracts: Mapping[str, StoredContract],
    events: Sequence[HistoryEvent],
    *,
    expected_bytes: bytes | None | object = _EXPECTED_UNSET,
) -> None:
    """Persist the table. History is fsynced BEFORE the replace (D-18).

    If the replace fails, an ``<event>-aborted`` line follows and the error is
    re-raised; nothing is swallowed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    history = contracts_history_path(path)
    lock = _lock_path(path)
    temp = _temp_for(path)
    wrote_history = False
    lock_fd = None
    try:
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ContractsCommitError(f"{lock}: another resolve commit is active") from exc
        if expected_bytes is not _EXPECTED_UNSET:
            actual = _snapshot_bytes(path)
            if actual != expected_bytes:
                raise ContractsCommitError(f"{path}: changed while resolve was running; aborting")
        with open(temp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_dump(contracts_payload(contracts)))
            fh.flush()
            os.fsync(fh.fileno())
        load_contracts_file(temp)
        if events:
            _append_history(history, [_history_line(e) for e in events])
            wrote_history = True
        os.replace(temp, path)
    except BaseException as exc:
        if wrote_history:
            reason = f"replace failed: {type(exc).__name__}"
            try:
                _append_history(
                    history, [_history_line(e, f"{e.event}-aborted", reason) for e in events]
                )
            except Exception:  # best effort; the original error is what matters
                log.exception("could not record the aborted history lines")
        temp.unlink(missing_ok=True)
        raise
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            lock.unlink(missing_ok=True)


# --- resolver ----------------------------------------------------------------------------


class AnchorMismatch(Exception):
    """The anchor ticker did not resolve to the expected contract id (D-13)."""

    def __init__(self, expected: int | None, seen: int | None):
        self.expected = expected
        self.seen = seen
        super().__init__(
            f"anchor {ANCHOR_TICKER}: expected conId={expected}, got "
            f"{'nothing' if seen is None else f'conId={seen}'}; nothing may be written"
        )


@dataclass(frozen=True)
class ResolveResult:
    ticker: str
    state: str
    detail: str
    identity: Identity | None = None
    trading_class: str = ""
    long_name: str = ""
    window: SessionWindow | None = None
    next_open: datetime | None = None

    @property
    def rejected(self) -> bool:
        return self.state in REJECTED_STATES


@dataclass(frozen=True)
class ResolveOutcome:
    results: tuple[ResolveResult, ...]
    contracts: Mapping[str, StoredContract]
    events: tuple[HistoryEvent, ...]

    @property
    def rejected(self) -> bool:
        return any(r.rejected for r in self.results)


MODE_RUN = "run"
MODE_INIT = "init"
MODE_REBASELINE = "rebaseline"


def needs_broker(tickers: Sequence[str]) -> bool:
    """True when at least one ticker survives the local checks and needs the gateway."""
    return any(classify(t).state == OK for t in tickers)


def _fmt(identity: Identity) -> str:
    return (
        f"conId={identity.con_id}/primaryExchange={identity.primary_exchange}"
        f"/currency={identity.currency}/localSymbol={identity.local_symbol}"
    )


def _identity_complete(identity: Identity) -> bool:
    return (
        identity.con_id > 0
        and bool(identity.primary_exchange)
        and bool(identity.currency)
        and bool(identity.local_symbol)
    )


def _candidate_line(cands) -> str:
    return ", ".join(
        f"conId={x.con_id}/primaryExchange={x.primary_exchange}/localSymbol={x.local_symbol}"
        f"/currency={x.currency}/tradingClass={x.trading_class}"
        for x in cands
    )


def _log_state(logger: logging.Logger, level: int, state: str, detail: str) -> None:
    logger.log(level, 'ibkr-state=%s code=- detail="%s"', state, detail)


def _search_key_diff(spec: ContractSpec, cand) -> tuple[str, ...]:
    pairs = [
        ("symbol", spec.symbol, cand.symbol),
        ("secType", spec.sec_type, cand.sec_type),
        ("currency", spec.currency, cand.currency),
    ]
    if spec.primary_exchange:
        pairs.append(("primaryExchange", spec.primary_exchange, cand.primary_exchange))
    return tuple(name for name, want, got in pairs if want != got)


def resolve_all(
    tickers: Sequence[str],
    *,
    contracts: Mapping[str, StoredContract] | None,
    broker,
    now_utc: datetime,
    logger: logging.Logger,
    mode: str = MODE_RUN,
    rebaseline: str | None = None,
    anchor_con_id: int | None = None,
) -> ResolveOutcome:
    """Run the decision chain for every ticker; no file access, no clock, no library.

    Chain per ticker: table mapping, allow-list, identity (learn or check against the
    persisted contract), tradability, session. The caller passes ``now_utc`` and the
    broker (duck-typed: ``search_contract`` and ``contract_details``). Nothing is
    written here; the outcome carries the contracts and history events to persist
    after the gateway session ends. Phase 4 calls this function directly (D-30).

    A drift is reported per ticker and never repaired: the stored identity stays
    untouched unless ``mode == "rebaseline"`` names exactly that ticker (D-16, D-17).
    """
    if mode not in (MODE_RUN, MODE_INIT, MODE_REBASELINE):
        raise ValueError(f"unknown mode {mode!r}")
    if contracts is None and mode != MODE_INIT:
        raise ValueError("contracts may only be None in init mode")
    work: dict[str, StoredContract] = dict(contracts or {})
    results: list[ResolveResult] = []
    events: list[HistoryEvent] = []
    at = now_utc.isoformat()

    for ticker in dict.fromkeys(tickers):
        verdict = classify(ticker)
        if verdict.state != OK:
            _log_state(logger, logging.WARNING, "TICKER_REJECTED", verdict.detail)
            results.append(ResolveResult(ticker, verdict.state, verdict.detail))
            continue
        if broker is None:
            raise ValueError("a broker is required for tickers that pass the local checks")
        spec = verdict.spec
        learn = (
            mode == MODE_INIT
            or ticker not in work
            or (mode == MODE_REBASELINE and ticker == rebaseline)
        )

        def reject(state, detail, level, log_state=None, ticker=ticker):
            _log_state(logger, level, log_state or state.upper().replace("-", "_"), detail)
            results.append(ResolveResult(ticker, state, detail))

        if learn:
            cands = broker.search_contract(spec)
            if not cands:
                reject(NOT_FOUND, f"ticker={ticker} the search returned no contract", logging.ERROR)
                continue
            if len(cands) > 1:
                reject(
                    AMBIGUOUS,
                    f"ticker={ticker} candidates=[{_candidate_line(cands)}]",
                    logging.ERROR,
                    "AMBIGUOUS_CONTRACT",
                )
                continue
            cand = cands[0]
            bad = _search_key_diff(spec, cand)
            if bad:
                reject(
                    DRIFT,
                    f"ticker={ticker} the match differs from the search key in {', '.join(bad)}",
                    logging.ERROR,
                    "CONTRACT_DRIFT",
                )
                continue
            found = broker.contract_details(cand.con_id, spec.exchange)
            if len(found) != 1:
                reject(
                    NOT_FOUND,
                    f"ticker={ticker} conId={cand.con_id} returned {len(found)} detail rows",
                    logging.ERROR,
                )
                continue
            detail_info = found[0]
            diff = identity_diff(identity_of(cand), identity_of(detail_info))
            if diff:
                reject(
                    DRIFT,
                    f"ticker={ticker} search and details disagree in {', '.join(diff)}",
                    logging.ERROR,
                    "CONTRACT_DRIFT",
                )
                continue
            identity = identity_of(detail_info)
            if not _identity_complete(identity):
                reject(
                    NOT_FOUND,
                    f"ticker={ticker} incomplete identity from contract details",
                    logging.ERROR,
                )
                continue
            previous = work.get(ticker)
            if mode == MODE_INIT:
                kind, reason = "init", "resolve --init"
            elif mode == MODE_REBASELINE and ticker == rebaseline:
                kind, reason = "rebaseline", "resolve --rebaseline"
            else:
                kind, reason = "learn", "first run in an existing contracts file"
            old = previous.identity if (kind == "rebaseline" and previous) else None
            work[ticker] = StoredContract(identity, at)
            events.append(HistoryEvent(kind, ticker, old, identity, reason, at))
            if kind == "rebaseline":
                old_text = _fmt(old) if old else "none"
                _log_state(
                    logger,
                    logging.WARNING,
                    "CONTRACT_REBASELINED",
                    f"ticker={ticker} old={old_text} new={_fmt(identity)}",
                )
            else:
                _log_state(
                    logger,
                    logging.INFO,
                    "CONTRACT_LEARNED",
                    f"ticker={ticker} learned conId={identity.con_id} "
                    f"primaryExchange={identity.primary_exchange} currency={identity.currency} "
                    f"localSymbol={identity.local_symbol} tradingClass={detail_info.trading_class} "
                    f"longName={detail_info.long_name}",
                )
        else:
            stored = work[ticker].identity
            found = broker.contract_details(stored.con_id, spec.exchange)
            cands = broker.search_contract(spec)
            drift_detail = None
            if len(found) != 1:
                if not found:
                    drift_detail = (
                        f"ticker={ticker} fields=conId stored={_fmt(stored)} "
                        "seen=none (persisted conId unknown to the gateway)"
                    )
                else:
                    drift_detail = (
                        f"ticker={ticker} fields=conId stored={_fmt(stored)} "
                        f"seen={len(found)} detail rows for one conId"
                    )
            elif not cands:
                reject(NOT_FOUND, f"ticker={ticker} the search returned no contract", logging.ERROR)
                continue
            elif len(cands) > 1:
                reject(
                    AMBIGUOUS,
                    f"ticker={ticker} candidates=[{_candidate_line(cands)}]",
                    logging.ERROR,
                    "AMBIGUOUS_CONTRACT",
                )
                continue
            elif cands[0].con_id != stored.con_id:
                drift_detail = (
                    f"ticker={ticker} fields=conId stored=conId={stored.con_id} "
                    f"seen=conId={cands[0].con_id} (symbol search points elsewhere)"
                )
            else:
                diff = identity_diff(stored, identity_of(found[0]))
                if diff:
                    drift_detail = (
                        f"ticker={ticker} fields={','.join(diff)} stored={_fmt(stored)} "
                        f"seen={_fmt(identity_of(found[0]))}"
                    )
            if drift_detail:
                reject(
                    DRIFT,
                    f"{drift_detail}; check, then resolve --rebaseline {ticker}",
                    logging.ERROR,
                    "CONTRACT_DRIFT",
                )
                continue
            detail_info = found[0]
            identity = stored
            logger.info(
                "ticker=%s tradingClass=%s longName=%s (informational, not compared)",
                ticker,
                detail_info.trading_class,
                detail_info.long_name,
            )

        why = check_tradable(detail_info.valid_exchanges, detail_info.order_types)
        if why:
            reject(NOT_TRADABLE, f"ticker={ticker} {why}", logging.WARNING)
            continue
        session = evaluate_session(detail_info.liquid_hours, detail_info.time_zone_id, now_utc)
        if session.state == SESSION_UNKNOWN:
            reject(SESSION_UNKNOWN, f"ticker={ticker} {session.detail}", logging.WARNING)
            continue
        results.append(
            ResolveResult(
                ticker,
                session.state,
                session.detail,
                identity=identity,
                trading_class=detail_info.trading_class,
                long_name=detail_info.long_name,
                window=session.window,
                next_open=session.next_open,
            )
        )

    if mode == MODE_INIT:
        anchor = work.get(ANCHOR_TICKER)
        if anchor is None or anchor.identity.con_id != anchor_con_id:
            raise AnchorMismatch(anchor_con_id, None if anchor is None else anchor.identity.con_id)
    return ResolveOutcome(tuple(results), MappingProxyType(work), tuple(events))
