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

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

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
