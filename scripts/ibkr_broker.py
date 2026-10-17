"""IBKR paper adapter: the only module that talks to the IBKR client library.

Operating manual: scripts/IBKR_EXECUTION.md.

Phase 2 reads only. The adapter has no write API at all (no place, preview or
cancel), and it blocks the client's write calls itself before the first byte
reaches the gateway, because the library's ``readonly=True`` only skips the
startup order sync and never stops ``placeOrder`` (ib.py:780-813, 2057-2063 in
2.1.0). The library is imported inside ``_default_ib_factory`` only, so the
command and the tests run without the optional ``ibkr`` extra.

Every request runs under ``asyncio.wait_for``: the library's own
``RequestTimeout`` defaults to 0, which waits forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

#: The one paper account this adapter may talk to (ibkr-konto-befund.md). A code
#: constant, never read from .env: a .env pointed at a live account must not pass.
EXPECTED_ACCOUNT = "DUQ634065"

#: Fixed API client id. Outside 0..9999, where ai_tradex hashes its ids; 0 binds
#: manual TWS orders, 1 is the library default, 98 was the phase-1 probe (Pitfall 8).
EXECUTOR_CLIENT_ID = 20001

#: AAPL on SMART; its contract details are the liveness probe (ibkr-konto-befund.md).
PROBE_CON_ID = 265598

#: Seconds the client library may wait in each of its connect steps (TCP connect,
#: API start, startup positions: client.py:216, :227 and ib.py:2077 in 2.1.0).
CONNECT_TIMEOUT_S = 10.0
#: Seconds on top of ``CONNECT_TIMEOUT_S`` before the adapter's own bound ends the
#: whole connect. The real limit is the sum, and that is what the log names.
CONNECT_GRACE_S = 5.0
#: Seconds any read request may take; the library's own default waits forever.
REQUEST_TIMEOUT_S = 10.0
#: Seconds the liveness probe may take.
PROBE_TIMEOUT_S = 5.0
#: Seconds the loop keeps reading the socket after the last answer of a snapshot,
#: so a 1100 that lands right behind it is seen before the snapshot is trusted.
#: One ``sleep(0)`` tick is not enough on the Windows proactor loop: a socket read
#: needs one iteration for the completion and another for ``data_received``.
SNAPSHOT_SETTLE_S = 0.05

#: Codes that open or close a link outage. Any of them inside a read window voids
#: what was read there: after a 1100 the gateway answers from its local state, and
#: a 1101/1102 inside the window means a loss happened in it.
LINK_CODES = frozenset({1100, 1101, 1102, 1300, 2110})

#: Client calls that would change the account; blocked before connectAsync.
_WRITE_CALLS = ("cancelOrder", "reqGlobalCancel", "exerciseOptions")

#: Outgoing message ids that change the account, blocked on the wire as well:
#: PLACE_ORDER 3, CANCEL_ORDER 4, REPLACE_FA 19, EXERCISE_OPTIONS 21,
#: REQ_GLOBAL_CANCEL 58 (the methods at client.py:472, :714, :805, :843, :980 in
#: 2.1.0). Every
#: request of the library goes through ``Client.send`` and then ``Client.sendMsg``,
#: so a write that bypasses the named calls still meets this check.
#: Id 3 passes only as a whatIf preview of a stock; every real order is refused.
_WRITE_MESSAGE_IDS = frozenset({3, 4, 19, 21, 58})

#: Security types a whatIf preview may name (M2 previews stocks only; any other
#: shape is refused, fail-closed).
_WHATIF_SEC_TYPES = frozenset({"STK"})

#: Indices into the PLACE_ORDER field list (contract = ONE field), read from
#: ib_async==2.1.0 Client.placeOrder for a server version >= 177 and a non-BAG
#: contract. The real-client test turns a layout change on upgrade into a red test.
_PO_DELTA_NEUTRAL_TYPE = 53
_PO_SCALE_PRICE_INCREMENT = 61
_PO_HEDGE_TYPE = 65
_PO_DELTA_NEUTRAL_CONTRACT = 70
_PO_ALGO_STRATEGY = 71
_PO_WHATIF = 73
_PO_MIN_FIELDS = _PO_WHATIF + 1
#: A contract is one field on the field level and 12 on the string level; the
#: string-level secType sits at offset 2 inside them.
_CONTRACT_WIDTH = 12
_UNSET_DOUBLE = 1.7976931348623157e308

#: Order states that are over; mirrors OrderStatus.DoneStates of ib_async 2.1.0
#: (the adapter imports the library only inside ``_default_ib_factory``).
_DONE_ORDER_STATUSES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})

#: Gateway/API code -> named operating state (02-RESEARCH.md Muster 5). 502, 504
#: and 507 never arrive as events from the library; connect() maps the matching
#: exceptions onto them.
STATE_BY_CODE: dict[int, str] = {
    502: "GATEWAY_UNREACHABLE",
    504: "NOT_CONNECTED",
    507: "SOCKET_EOF",
    326: "CLIENT_ID_IN_USE",
    1100: "CONNECTIVITY_LOST",
    1101: "RESTORED_DATA_LOST",
    1102: "RESTORED_DATA_KEPT",
    1300: "PORT_CHANGED",
    2103: "FARM_DOWN",
    2105: "FARM_DOWN",
    2104: "FARM_OK",
    2106: "FARM_OK",
    2158: "FARM_OK",
    2110: "SERVER_LINK_BROKEN",
    # Measured read-only marker of gateway 10.50.1, not 10015 as documented
    # (ibkr-konto-befund.md, Korrektur 1). The library treats it as a warning
    # and does not end the waiting request, so only the timeout ends it.
    321: "READ_ONLY_API",
    10015: "TRADING_NOT_ALLOWED",
    10089: "MARKET_DATA_NOT_SUBSCRIBED",
    10090: "MARKET_DATA_NOT_SUBSCRIBED",
    # Measured on paper gateway 10.50.1 for delayed stock quotes (03-RESEARCH.md).
    10167: "MARKET_DATA_DELAYED",
    # Measured for an unknown symbol (XYZQ): no contract matches.
    200: "CONTRACT_NOT_FOUND",
    2172: "GATEWAY_VERSION_EXPIRING",
    # Official TWS API code list: "Orders cannot be transmitted for a halted
    # security." It cannot be provoked on the paper gateway, so it rests on the
    # official list and a fake test (REQ-IBKR-67 gap, assumption A5).
    154: "HALTED",
    # Measured 2026-10-12, ibkr-marktdaten-befund.md Befund 4: a preview without
    # an explicit tif comes back empty with 10349.
    10349: "TIF_OVERRIDDEN",
}

#: Codes ``preview_order`` evaluates itself; they are no generic request failure.
_PREVIEW_CODES = frozenset({154, 10349})

#: The tif every preview names explicitly (REQ-IBKR-25, REQ-IBKR-69).
PREVIEW_TIF = "DAY"

#: Farm-OK and delayed-market-data notices: expected states, logged at INFO.
INFO_CODES = frozenset({2104, 2106, 2158, 10089, 10090, 10167})
#: System notices (reqId == -1) that may appear inside a read window without voiding
#: it. Any other system code inside a window voids what was read there, a never
#: classified one included (2157, the sec-def farm the contract reads depend on, is
#: such a code): fail-closed by construction instead of a list of known faults.
#: Each entry is measured at the real gateway or a reviewed decision:
#:   INFO_CODES  farm-OK and delayed-market-data notices
#:   2107        HMDS farm inactive, available on demand (measured 2026-10-12)
#:   2103/2105/2108  market-data and HMDS farms: neither the account nor the
#:               sec-def reads use them (phase-3 review, 2b941a0)
#:   321         read-only API, owned by the preview (measured 2026-10-11)
WINDOW_BENIGN_CODES = INFO_CODES | frozenset({2103, 2105, 2107, 2108, 321})

# Named states without a gateway code.
CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
PROBE_TIMEOUT = "PROBE_TIMEOUT"
PROBE_FAILED = "PROBE_FAILED"
SNAPSHOT_INCOMPLETE = "SNAPSHOT_INCOMPLETE"
HEALTHY = "HEALTHY"
UNKNOWN = "UNKNOWN"
REQUEST_FAILED = "REQUEST_FAILED"


def state_for_code(code: int) -> str:
    """The named state for a gateway/API code; ``UNKNOWN`` for any other."""
    return STATE_BY_CODE.get(code, UNKNOWN)


class ReadOnlyViolation(RuntimeError):
    """A write call reached the broker client while the session is read-only."""


class AccountGuardViolation(RuntimeError):
    """The gateway reports accounts other than exactly the paper account."""

    def __init__(self, accounts_seen: list[str]):
        self.accounts_seen = list(accounts_seen)
        super().__init__(
            f"ibkr-state=ACCOUNT_GUARD_VIOLATED accounts_seen={self.accounts_seen} "
            f"expected=[{EXPECTED_ACCOUNT!r}]"
        )


class GatewayUnavailable(RuntimeError):
    """The gateway session is unusable; ``state`` names why."""

    def __init__(self, state: str, code: int | None, detail: str):
        self.state = state
        self.code = code
        self.detail = detail
        super().__init__(state, code, detail)

    def __str__(self) -> str:
        code = "-" if self.code is None else self.code
        return f'ibkr-state={self.state} code={code} detail="{self.detail}"'


@dataclass(frozen=True)
class IbHandles:
    """What the adapter needs from the client library: the client, a contract type, a flag."""

    ib: Any
    contract: Any
    fetch_none: Any
    order: Any = None


@dataclass(frozen=True)
class BrokerPosition:
    """One held position of the paper account, broker-neutral."""

    symbol: str
    sec_type: str
    local_symbol: str
    currency: str
    quantity: float
    avg_cost: float
    con_id: int = 0


@dataclass(frozen=True)
class OpenOrder:
    """One open order of the account, broker-neutral; phase 4 never sends, so each is foreign."""

    con_id: int
    action: str
    quantity: float
    order_type: str
    status: str
    client_id: int
    order_ref: str = ""


@dataclass(frozen=True)
class OrderRecord:
    """One order of the broker's open or completed list, broker-neutral.

    ``source`` is ``"open"`` or ``"completed"``. ``filled`` is ``None`` where the
    gateway left the count unset (every open order, and a completed order that
    never filled).
    """

    source: str
    order_ref: str
    status: str
    action: str
    quantity: float
    filled: float | None
    con_id: int
    perm_id: int
    order_id: int
    client_id: int


@dataclass(frozen=True)
class ExecutionRecord:
    """One execution (fill) of the account, broker-neutral; ``side`` is BUY or SELL."""

    exec_id: str
    order_ref: str
    con_id: int
    perm_id: int
    order_id: int
    client_id: int
    shares: float
    price: float
    side: str
    time: str


@dataclass(frozen=True)
class OrderHistory:
    """The three broker sources of what happened to orders, read in one call (REQ-43)."""

    open: tuple[OrderRecord, ...]
    completed: tuple[OrderRecord, ...]
    executions: tuple[ExecutionRecord, ...]


@dataclass(frozen=True)
class ContractInfo:
    """One contract as the broker reports it, broker-neutral (no library object leaves here).

    The session fields stay empty on a symbol search and are filled by
    ``contract_details``.
    """

    con_id: int
    symbol: str
    sec_type: str
    exchange: str
    primary_exchange: str
    currency: str
    local_symbol: str
    trading_class: str
    long_name: str = ""
    valid_exchanges: str = ""
    order_types: str = ""
    time_zone_id: str = ""
    liquid_hours: str = ""
    trading_hours: str = ""


def _text(obj, name: str) -> str:
    value = getattr(obj, name, "")
    return "" if value is None else str(value)


def _info_from_contract(contract, details=None) -> ContractInfo:
    """A ``ContractInfo`` from a library contract and, optionally, its details row."""
    extra = {}
    if details is not None:
        extra = {
            "long_name": _text(details, "longName"),
            "valid_exchanges": _text(details, "validExchanges"),
            "order_types": _text(details, "orderTypes"),
            "time_zone_id": _text(details, "timeZoneId"),
            "liquid_hours": _text(details, "liquidHours"),
            "trading_hours": _text(details, "tradingHours"),
        }
    return ContractInfo(
        con_id=int(contract.conId),
        symbol=_text(contract, "symbol"),
        sec_type=_text(contract, "secType"),
        exchange=_text(contract, "exchange"),
        primary_exchange=_text(contract, "primaryExchange"),
        currency=_text(contract, "currency"),
        local_symbol=_text(contract, "localSymbol"),
        trading_class=_text(contract, "tradingClass"),
        **extra,
    )


@dataclass(frozen=True)
class AccountSnapshot:
    """Positions and cash of the paper account, read fresh at ``as_of`` (UTC)."""

    account: str
    positions: tuple[BrokerPosition, ...]
    cash: float
    cash_currency: str
    available_funds: float
    available_funds_currency: str
    as_of: datetime


@dataclass(frozen=True)
class PreviewResult:
    """The evaluated answer of one whatIf preview, broker-neutral.

    ``state`` is OK, EMPTY, HALTED, TIF_OVERRIDDEN or READ_ONLY_API. A number the
    gateway left unset (or sent unreadable) is ``None``. The adapter does not judge
    budget or rejection; ``judge_preview`` does.
    """

    state: str
    init_margin_change: float | None
    maint_margin_change: float | None
    commission: float | None
    commission_currency: str
    warning_text: str
    errors: tuple[tuple[int, str], ...]
    effective_tif: str | None
    sent_tif: str
    #: orderRef and account the gateway echoed on the whatIf order; ``None`` = no echo.
    echo_order_ref: str | None = None
    echo_account: str | None = None


def _unset_to_none(value) -> float | None:
    """A readable number, else None: ``None`` and the unset sentinel (>= 1e300) are None."""
    if value is None:
        return None
    number = float(value)
    return None if abs(number) >= 1e300 else number


#: Execution side as the library reports it -> broker-neutral side.
_EXECUTION_SIDES = {"BOT": "BUY", "SLD": "SELL"}


def _order_record(source: str, trade) -> OrderRecord:
    """An ``OrderRecord`` from a library Trade row."""
    order = trade.order
    return OrderRecord(
        source=source,
        order_ref=_text(order, "orderRef"),
        status=_text(trade.orderStatus, "status"),
        action=_text(order, "action"),
        quantity=float(order.totalQuantity),
        filled=_unset_to_none(getattr(order, "filledQuantity", None)),
        con_id=int(trade.contract.conId),
        perm_id=int(getattr(order, "permId", 0) or 0),
        order_id=int(getattr(order, "orderId", 0) or 0),
        client_id=int(getattr(order, "clientId", 0) or 0),
    )


def _money(value) -> float | None:
    """A readable number, else None: text, NaN and the unset sentinel (1.797e308) are None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or abs(number) >= 1e300:
        return None
    return number


@dataclass(frozen=True)
class Health:
    """Liveness verdict: ``ok`` only on a real server answer."""

    ok: bool
    state: str
    detail: str


def _default_ib_factory() -> IbHandles:
    from ib_async import IB, Contract, Order, StartupFetchNONE  # the only import site in the repo

    return IbHandles(IB(), Contract, StartupFetchNONE, Order)


def _message_id(field) -> int | None:
    """The message id of a first protocol field, or None when it is not one."""
    if isinstance(field, bool):
        return None
    try:
        return int(field)
    except (TypeError, ValueError):
        return None


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and value == "")


def _is_unset_number(value) -> bool:
    """True for an unset or non-positive number (the scale increment is not in use)."""
    if _is_empty(value):
        return True
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number <= 0 or number >= _UNSET_DOUBLE


def _whatif_layout(fields) -> bool:
    """True only for a plain order whose whatIf field is set; unknown layout = False.

    ``fields`` has the field-level shape (index 2 stands for the contract). Values
    are typed (field level) or strings (string level); both are understood. Every
    conditional block that would shift the whatIf position (delta neutral, scale,
    hedge, delta-neutral contract, algo) must be in its empty state, otherwise the
    position is not known and the order is refused.
    """
    try:
        if len(fields) < _PO_MIN_FIELDS:
            return False
        if not _is_empty(fields[_PO_DELTA_NEUTRAL_TYPE]):
            return False
        if not _is_unset_number(fields[_PO_SCALE_PRICE_INCREMENT]):
            return False
        if not _is_empty(fields[_PO_HEDGE_TYPE]):
            return False
        dnc = fields[_PO_DELTA_NEUTRAL_CONTRACT]
        if not (dnc is False or (isinstance(dnc, str) and dnc == "0")):
            return False
        if not _is_empty(fields[_PO_ALGO_STRATEGY]):
            return False
        flag = fields[_PO_WHATIF]
        return flag is True or (isinstance(flag, str) and flag == "1")
    except (IndexError, TypeError, ValueError):
        return False


def _whatif_in_fields(fields) -> bool:
    """Field-level check: id 3, a STK contract object and a set whatIf field."""
    try:
        if len(fields) < _PO_MIN_FIELDS or _message_id(fields[0]) != 3:
            return False
        if getattr(fields[2], "secType", None) not in _WHATIF_SEC_TYPES:
            return False
        return _whatif_layout(list(fields))
    except (IndexError, TypeError, ValueError):
        return False


def _whatif_in_message(msg) -> bool:
    """String-level check of a serialized message (contract expanded to 12 fields).

    Layout read from ib_async==2.1.0 Client.placeOrder; the real-client test turns
    a layout change on upgrade into a red test. ``send`` ends every field with a
    NUL, so the last element after the split is empty.
    """
    try:
        if not isinstance(msg, str):
            return False
        parts = msg.split("\0")
        if parts[0] != "3":
            return False
        sec_type = parts[2 + 2]  # id, orderId, then conId, symbol, secType
        if sec_type not in _WHATIF_SEC_TYPES:
            return False
        fields = [*parts[:2], None, *parts[2 + _CONTRACT_WIDTH :]]
        return _whatif_layout(fields)
    except (IndexError, TypeError, ValueError):
        return False


class _CancelPermit:
    """One pass of message 58, opened only by cancel_all after a detected kill switch (D-05).

    ``open`` is True only while ``cancel_all`` runs; ``sent`` counts the passes that
    reached the wire (``sendMsg``), so a second use in one session is visible.
    """

    open: bool = False
    sent: int = 0


def _arm_write_barrier(client, permit: _CancelPermit | None = None) -> None:
    """Refuse every write on this client instance, by call name and on the wire.

    The named write calls are replaced first. ``placeOrder`` and message id 3
    pass only as a whatIf preview of a stock (D-13); every real order is refused.
    Then ``send`` (fields) and ``sendMsg`` (the serialized message, id first) are
    wrapped, so a write message is refused whatever path produced it:
    ``replaceFA``, a raw ``send(3, ...)`` or a write call added by a later library
    version that reuses one of these ids. Reads pass through unchanged.

    ``reqGlobalCancel`` (name, field level and message 58) is the one exception to
    "refused": it passes while ``permit.open`` is True, and the pass is counted on
    the wire level. Without a ``permit`` the exception never opens.
    """
    permit = permit if permit is not None else _CancelPermit()
    original_place = getattr(client, "placeOrder", None)
    original_global_cancel = getattr(client, "reqGlobalCancel", None)

    def guarded_place(*args, **kwargs):
        contract = args[1] if len(args) > 1 else kwargs.get("contract")
        order = args[2] if len(args) > 2 else kwargs.get("order")
        if (
            getattr(order, "whatIf", None) is not True
            or getattr(contract, "secType", None) not in _WHATIF_SEC_TYPES
        ):
            raise ReadOnlyViolation(
                "read-only session: placeOrder without whatIf refused before it reached the gateway"
            )
        if original_place is None:
            raise ReadOnlyViolation("read-only session: no placeOrder to preview with")
        return original_place(*args, **kwargs)

    client.placeOrder = guarded_place

    def guarded_global_cancel(*args, **kwargs):
        if not permit.open or original_global_cancel is None:
            raise ReadOnlyViolation(
                "read-only session: reqGlobalCancel refused before it reached the gateway"
            )
        return original_global_cancel(*args, **kwargs)

    client.reqGlobalCancel = guarded_global_cancel

    for name in _WRITE_CALLS:
        if name == "reqGlobalCancel":
            continue

        def refuse(*_args, _name=name, **_kwargs):
            raise ReadOnlyViolation(
                f"read-only session: {_name} refused before it reached the gateway"
            )

        setattr(client, name, refuse)

    def refuse_message(msg_id: int):
        raise ReadOnlyViolation(
            f"read-only session: message {msg_id} refused before it reached the gateway"
        )

    original_send = client.send
    original_send_msg = client.sendMsg

    def guarded_send(*fields, **kwargs):
        msg_id = _message_id(fields[0]) if fields else None
        if msg_id == 3:
            if not _whatif_in_fields(fields):
                refuse_message(msg_id)
        elif msg_id == 58 and permit.open:
            pass
        elif msg_id in _WRITE_MESSAGE_IDS:
            refuse_message(msg_id)
        return original_send(*fields, **kwargs)

    def guarded_send_msg(msg, *args, **kwargs):
        head = msg.split("\0", 1)[0] if isinstance(msg, str) else None
        msg_id = _message_id(head) if head else None
        if msg_id == 3:
            if not _whatif_in_message(msg):
                refuse_message(msg_id)
        elif msg_id == 58 and permit.open:
            result = original_send_msg(msg, *args, **kwargs)
            permit.open = False
            # Counted as handed to the client; when throttled it may only be queued (IN-02).
            permit.sent += 1
            return result
        elif msg_id in _WRITE_MESSAGE_IDS:
            refuse_message(msg_id)
        return original_send_msg(msg, *args, **kwargs)

    client.send = guarded_send
    client.sendMsg = guarded_send_msg


class IbkrBroker:
    """One read-only session against the paper gateway.

    Public: ``connect``, ``positions``, ``health``, ``search_contract``,
    ``contract_details``, ``open_orders``, ``order_history``, ``preview_order``,
    ``cancel_all``. Use as a context manager; leaving it disconnects.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        client_id: int = EXECUTOR_CLIENT_ID,
        ib_factory=_default_ib_factory,
        loop: asyncio.AbstractEventLoop | None = None,
        logger: logging.Logger | None = None,
        connect_timeout: float = CONNECT_TIMEOUT_S,
        connect_grace: float = CONNECT_GRACE_S,
        request_timeout: float = REQUEST_TIMEOUT_S,
        probe_timeout: float = PROBE_TIMEOUT_S,
        settle: float = SNAPSHOT_SETTLE_S,
    ):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib_factory = ib_factory
        self._loop = loop
        self._owns_loop = False
        self._log = logger or logging.getLogger("ibkr_broker")
        self._connect_timeout = connect_timeout
        self._connect_grace = connect_grace
        self._request_timeout = request_timeout
        self._probe_timeout = probe_timeout
        self._settle = settle
        self._handles: IbHandles | None = None
        self._ib = None
        #: One-shot permit for message 58; shut until cancel_all opens it.
        self._permit = _CancelPermit()
        self.link_lost = False
        self.server_link_broken = False
        self.port_changed = False
        self._seen_codes: list[int] = []
        #: Codes of errors tied to a request id (``reqId >= 0``), in order.
        self._request_errors: list[int] = []
        #: The same errors with their text, for the preview's error report.
        self._request_error_texts: list[tuple[int, str]] = []
        #: Every window-voiding event of the session, in order: a LINK_CODES event or a
        #: system notice outside WINDOW_BENIGN_CODES. Read windows compare its length.
        self._link_codes: list[int] = []

    def __enter__(self) -> IbkrBroker:
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self._disconnect()

    def connect(self) -> None:
        """Connect read-only, block writes, then enforce the paper-account guard.

        Raises ``GatewayUnavailable`` with a named state when the session cannot
        be opened, ``AccountGuardViolation`` when the gateway reports anything
        but exactly ``[EXPECTED_ACCOUNT]``. Either way the session is closed.
        """
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._owns_loop = True
        try:
            handles = self._ib_factory()
        except BaseException:  # e.g. the ibkr extra is missing: close the loop anyway
            self._disconnect()
            raise
        ib = handles.ib
        self._handles, self._ib = handles, ib
        # Subscribed first: a 326 arrives before the handshake completes.
        ib.errorEvent += self._on_error
        # D-01: the barrier stands before a single byte flows.
        _arm_write_barrier(ib.client, self._permit)
        host, port, timeout = self._host, self._port, self._connect_timeout
        bound = timeout + self._connect_grace
        try:
            self._call(
                lambda: ib.connectAsync(
                    host,
                    port,
                    clientId=self._client_id,
                    timeout=timeout,
                    readonly=True,
                    fetchFields=handles.fetch_none,
                ),
                bound,
            )
        except TimeoutError as exc:  # before OSError: TimeoutError is one
            self._disconnect()
            if 326 in self._seen_codes:
                raise GatewayUnavailable(
                    "CLIENT_ID_IN_USE", 326, f"clientId {self._client_id} already in use"
                ) from exc
            raise GatewayUnavailable(
                CONNECT_TIMEOUT,
                None,
                f"no handshake from {host}:{port} within {bound:g}s "
                f"(library steps up to {timeout:g}s each, adapter bound {bound:g}s)",
            ) from exc
        except ConnectionRefusedError as exc:
            self._disconnect()
            raise GatewayUnavailable(
                "GATEWAY_UNREACHABLE",
                502,
                f"Gateway nicht erreichbar: {host}:{port} ({type(exc).__name__})",
            ) from exc
        except (ConnectionResetError, BrokenPipeError, EOFError) as exc:
            self._disconnect()
            raise GatewayUnavailable(
                "SOCKET_EOF", 507, f"peer closed the connection ({type(exc).__name__})"
            ) from exc
        except ConnectionError as exc:
            self._disconnect()
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, f"not connected ({type(exc).__name__}: {exc})"
            ) from exc
        except OSError as exc:
            self._disconnect()
            raise GatewayUnavailable(
                "GATEWAY_UNREACHABLE",
                502,
                f"Gateway nicht erreichbar: {host}:{port} ({type(exc).__name__})",
            ) from exc
        except BaseException:
            self._disconnect()
            raise

        # Paper guard: the first check after the handshake. Exact list, no prefix.
        # __exit__ never runs when connect() raises, so any error here closes the
        # session itself.
        try:
            accounts = list(ib.managedAccounts())
        except BaseException:
            self._disconnect()
            raise
        if accounts != [EXPECTED_ACCOUNT]:
            self._log.error("ibkr-state=ACCOUNT_GUARD_VIOLATED accounts_seen=%s", accounts)
            self._disconnect()
            raise AccountGuardViolation(accounts)
        self._log.info(
            "ibkr-state=CONNECTED account=%s clientId=%s readonly=True "
            "(the handshake requested positions before the guard: a harmless read)",
            EXPECTED_ACCOUNT,
            self._client_id,
        )
        # D-25: delayed data (3), asked for only after the paper guard passed.
        try:
            ib.reqMarketDataType(3)
        except BaseException:
            self._disconnect()
            raise
        self._log.info('ibkr-state=MARKET_DATA_TYPE code=- detail="delayed (3)"')

    def health(self) -> Health:
        """Liveness from a real server answer, not from the socket (REQ-IBKR-09).

        Healthy only when the socket is up, no 1100/2110/1300 is open, and the
        contract-details probe for ``PROBE_CON_ID`` returns exactly that contract
        within ``probe_timeout``. One loop tick runs before the state flags are
        read, so an error event already queued in the loop (a 1100 that arrived
        between two calls) reaches ``_on_error`` first. While a flag is open no
        probe is sent, and a link event that arrives while the probe is in
        flight voids its answer.

        Known limit (assumption A4): should the gateway answer the probe from a
        cache while the server link is down, only the system events reveal
        it; they are checked before and after the probe.
        """
        ib, handles = self._ib, self._handles
        if ib is None or handles is None:
            return self._unhealthy("NOT_CONNECTED", "no session; connect() first")
        self._call(lambda: asyncio.sleep(0), self._probe_timeout)
        if not ib.isConnected():
            return self._unhealthy("NOT_CONNECTED", "socket is down")
        opened = self._open_link()
        if opened is not None:
            return self._unhealthy(*opened)
        mark = len(self._link_codes)
        try:
            details = self._call(
                lambda: ib.reqContractDetailsAsync(handles.contract(conId=PROBE_CON_ID)),
                self._probe_timeout,
            )
        except TimeoutError:
            return self._unhealthy(
                PROBE_TIMEOUT, f"probe conId {PROBE_CON_ID} unanswered in {self._probe_timeout}s"
            )
        except ConnectionError as exc:
            return self._unhealthy("NOT_CONNECTED", f"probe not sent ({type(exc).__name__})")
        event = self._link_event_since(mark)
        if event is not None:
            state, code = event
            return self._unhealthy(state, f"link event {code} while the probe was in flight")
        if len(details) != 1 or details[0].contract.conId != PROBE_CON_ID:
            return self._unhealthy(
                PROBE_FAILED, f"probe conId {PROBE_CON_ID} returned {len(details)} matches"
            )
        return Health(True, HEALTHY, f"probe conId {PROBE_CON_ID} answered")

    def positions(self) -> AccountSnapshot:
        """Positions and cash of the paper account, asked fresh on every call (REQ-IBKR-12).

        Never the library's cached positions, never a file. Rows of other accounts
        and zero-quantity rows are dropped. Cash is the one ``TotalCashValue`` row
        of the paper account (conservative, without margin; assumption A3), not
        the margin-levered buying power. AvailableFunds is the budget yardstick
        for the whatIf preview (D-15, REQ-IBKR-70); compared in account currency,
        no exchange rate.

        Fail-closed over the whole read window: no read starts while a link flag
        is open, the loop settles for ``settle`` seconds after the last answer,
        and any 1100/1101/1102/1300/2110 seen in between discards the snapshot.
        After a 1100 the gateway answers from its local state with well-formed
        rows, so "no error" is no proof of a fresh book.

        Known limit: the library never cancels the account-summary subscription
        it opens, so each call adds one to the session. Phase 2 calls this once
        per session; a later plan that calls it repeatedly must cancel them.
        """
        ib = self._ib
        if ib is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        opened = self._open_link()
        if opened is not None:
            raise GatewayUnavailable(opened[0], None, f"{opened[1]}; no snapshot read")
        mark = len(self._link_codes)
        raw = self._request("reqPositions", ib.reqPositionsAsync)
        # The library asks the gateway only while its summary cache is empty
        # (ib.py:2232-2235 in 2.1.0) and answers every later call from it. Emptied
        # here, every call sends the same request as the measured first run did,
        # and no row of an earlier answer survives into this one.
        ib.wrapper.acctSummary.clear()
        values = self._request("accountSummary", lambda: ib.accountSummaryAsync(EXPECTED_ACCOUNT))
        self._call(lambda: asyncio.sleep(self._settle), self._settle + self._probe_timeout)
        if not ib.isConnected():
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, "socket went down during the snapshot; snapshot discarded"
            )
        event = self._link_event_since(mark)
        if event is not None:
            state, code = event
            raise GatewayUnavailable(
                state,
                code,
                f"link event(s) {self._link_codes[mark:]} during the snapshot; snapshot discarded",
            )

        held = tuple(
            BrokerPosition(
                symbol=p.contract.symbol,
                sec_type=p.contract.secType,
                local_symbol=p.contract.localSymbol,
                currency=p.contract.currency,
                quantity=float(p.position),
                avg_cost=float(p.avgCost),
                con_id=int(p.contract.conId),
            )
            for p in raw
            if p.account == EXPECTED_ACCOUNT and p.position != 0
        )
        mine = [v for v in values if v.account == EXPECTED_ACCOUNT]
        cash_rows = [v for v in mine if v.tag == "TotalCashValue"]
        if len(cash_rows) != 1:
            raise GatewayUnavailable(
                SNAPSHOT_INCOMPLETE,
                None,
                f"expected one TotalCashValue row for {EXPECTED_ACCOUNT}, got {len(cash_rows)}",
            )
        cash = cash_rows[0]
        funds_rows = [v for v in mine if v.tag == "AvailableFunds"]
        if len(funds_rows) != 1:
            raise GatewayUnavailable(
                SNAPSHOT_INCOMPLETE,
                None,
                f"expected one AvailableFunds row for {EXPECTED_ACCOUNT}, got {len(funds_rows)}",
            )
        funds = funds_rows[0]
        self._log.info("ibkr-account AvailableFunds=%s %s", funds.value, funds.currency)
        for v in mine:
            if v.tag == "NetLiquidation":
                self._log.info("ibkr-account %s=%s %s (log only)", v.tag, v.value, v.currency)
        return AccountSnapshot(
            account=EXPECTED_ACCOUNT,
            positions=held,
            cash=float(cash.value),
            cash_currency=cash.currency,
            available_funds=float(funds.value),
            available_funds_currency=funds.currency,
            as_of=datetime.now(UTC),
        )

    def search_contract(self, spec) -> tuple[ContractInfo, ...]:
        """All contracts matching the search keys of ``spec``: 0, 1 or n (REQ-IBKR-29).

        Calls ``qualifyContractsAsync(contract, returnAll=True)``. The library
        mutates the contract it is given (and caches nothing for us), so each
        call builds a fresh one from the spec. Whether exactly one match is
        required is the caller's decision (the resolver), not this method's.
        """

        def ask():
            handles = self._handles
            contract = handles.contract(
                symbol=spec.symbol,
                secType=spec.sec_type,
                exchange=spec.exchange,
                currency=spec.currency,
                primaryExchange=spec.primary_exchange,
            )
            return self._ib.qualifyContractsAsync(contract, returnAll=True)

        slots = self._read("qualifyContracts", ask)
        if not slots or slots[0] is None:
            return ()
        slot = slots[0]
        found = slot if isinstance(slot, list) else [slot]
        if any(c is None for c in found):
            raise GatewayUnavailable(
                REQUEST_FAILED,
                None,
                "qualifyContracts returned an incomplete candidate list",
            )
        return tuple(_info_from_contract(c) for c in found if c is not None)

    def contract_details(self, con_id: int, exchange: str) -> tuple[ContractInfo, ...]:
        """Every details row for ``conId`` on ``exchange`` (REQ-IBKR-30).

        Calls ``reqContractDetailsAsync`` with a fresh contract. Carries the
        valid exchanges, order types, time zone and trading hours.
        """

        def ask():
            contract = self._handles.contract(conId=con_id, exchange=exchange)
            return self._ib.reqContractDetailsAsync(contract)

        rows = self._read("reqContractDetails", ask)
        return tuple(_info_from_contract(d.contract, d) for d in rows)

    def open_orders(self, con_id: int | None = None) -> tuple[OpenOrder, ...]:
        """Every open order of the account, whoever placed it (D-12).

        Reads all open orders of the account, including orders of other clients
        and TWS (``reqAllOpenOrdersAsync``, a read message). Finished orders are
        dropped. With ``con_id`` only that contract's orders are returned; without
        it every open order of the account (kill-switch recheck, reconciliation).
        """
        trades = self._read("reqAllOpenOrders", lambda: self._ib.reqAllOpenOrdersAsync())
        return tuple(
            OpenOrder(
                con_id=int(t.contract.conId),
                action=_text(t.order, "action"),
                quantity=float(t.order.totalQuantity),
                order_type=_text(t.order, "orderType"),
                status=_text(t.orderStatus, "status"),
                client_id=int(t.order.clientId),
                order_ref=_text(t.order, "orderRef"),
            )
            for t in trades
            if (con_id is None or int(t.contract.conId) == con_id)
            and t.orderStatus.status not in _DONE_ORDER_STATUSES
        )

    def order_history(self) -> OrderHistory:
        """Open orders, completed orders and executions of the account (REQ-43).

        Three fail-closed read windows (``reqAllOpenOrders``, ``reqCompletedOrders``,
        ``reqExecutions``); each one is voided by a link event, a timeout or a
        request error. Orders of every client are included. The records carry the
        ``orderRef`` the reconciliation matches on.
        """
        open_trades = self._read("reqAllOpenOrders", lambda: self._ib.reqAllOpenOrdersAsync())
        completed_trades = self._read(
            "reqCompletedOrders", lambda: self._ib.reqCompletedOrdersAsync(apiOnly=False)
        )
        fills = self._read("reqExecutions", lambda: self._ib.reqExecutionsAsync())
        executions = []
        for f in fills:
            execution = f.execution
            side = _EXECUTION_SIDES.get(_text(execution, "side"))
            if side is None:
                raise GatewayUnavailable(
                    REQUEST_FAILED,
                    None,
                    f"reqExecutions: unknown side {_text(execution, 'side')!r}; answer discarded",
                )
            moment = getattr(execution, "time", None)
            executions.append(
                ExecutionRecord(
                    exec_id=_text(execution, "execId"),
                    order_ref=_text(execution, "orderRef"),
                    con_id=int(f.contract.conId),
                    perm_id=int(getattr(execution, "permId", 0) or 0),
                    order_id=int(getattr(execution, "orderId", 0) or 0),
                    client_id=int(getattr(execution, "clientId", 0) or 0),
                    shares=float(execution.shares),
                    price=float(execution.price),
                    side=side,
                    time=(
                        moment.isoformat()
                        if hasattr(moment, "isoformat")
                        else _text(execution, "time")
                    ),
                )
            )
        # Like ``open_orders``, finished orders are not open (WR-06): a just-filled order can
        # still stand in the open answer with ``Filled`` and also in the completed one. The
        # three reads are not atomic, so a finished row that the completed read did not see
        # yet is kept as completed instead of being dropped (its evidence stays).
        completed = [_order_record("completed", t) for t in completed_trades]
        seen = {(record.perm_id, record.quantity) for record in completed if record.perm_id}
        opened = []
        for trade in open_trades:
            record = _order_record("open", trade)
            if record.status not in _DONE_ORDER_STATUSES:
                opened.append(record)
            elif (record.perm_id, record.quantity) not in seen:
                completed.append(record)
        return OrderHistory(
            open=tuple(opened),
            completed=tuple(completed),
            executions=tuple(executions),
        )

    def preview_order(
        self,
        *,
        con_id: int,
        symbol: str,
        sec_type: str,
        currency: str,
        primary_exchange: str,
        action: str,
        quantity: int,
        order_ref: str = "",
    ) -> PreviewResult:
        """The whatIf preview of a market order: margin, commission, errors, tif (D-13).

        Builds the order itself (market, ``tif="DAY"`` explicit, paper account) and
        sends it only through ``whatIfOrderAsync``, which the write barrier lets
        pass as a preview. Never a real order. The echo of the gateway is tapped
        for the tif it actually applied, and for the ``orderRef`` and account it
        carries (``order_ref`` goes onto the order only when set); the tap is
        removed again in ``finally``.

        Fail-closed like every read: no preview while a link is open, a link event
        in the window discards the answer, a timeout without 321 is
        ``REQUEST_TIMEOUT``. 154, 10349 and 321 (on a timeout) are states of the
        result, not exceptions. Budget and rejection are judged elsewhere.
        """
        if action not in ("BUY", "SELL"):
            raise ValueError(f"action must be BUY or SELL, got {action!r}")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError(f"quantity must be a positive whole number, got {quantity!r}")
        ib, handles = self._ib, self._handles
        if ib is None or handles is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        if handles.order is None:
            raise RuntimeError("no order type in IbHandles")
        opened = self._open_link()
        if opened is not None:
            raise GatewayUnavailable(opened[0], None, f"{opened[1]}; no preview sent")
        mark = len(self._link_codes)
        code_mark = len(self._request_error_texts)
        seen_mark = len(self._seen_codes)
        contract = handles.contract(
            conId=con_id,
            symbol=symbol,
            secType=sec_type,
            exchange="SMART",
            currency=currency,
            primaryExchange=primary_exchange,
        )
        order_kwargs = {"orderRef": order_ref} if order_ref else {}
        order = handles.order(
            action=action,
            totalQuantity=quantity,
            orderType="MKT",
            tif=PREVIEW_TIF,
            account=EXPECTED_ACCOUNT,
            **order_kwargs,
        )
        echoed: list[str] = []
        echoed_ref: list[str] = []
        echoed_account: list[str] = []
        original = ib.wrapper.openOrder

        def capture(*args):
            echo_order = args[2] if len(args) > 2 else None
            if getattr(echo_order, "whatIf", False):
                echoed.append(str(getattr(echo_order, "tif", "")))
                echoed_ref.append(_text(echo_order, "orderRef"))
                echoed_account.append(_text(echo_order, "account"))
            return original(*args)

        ib.wrapper.openOrder = capture
        response = None
        timed_out = False
        try:
            response = self._call(lambda: ib.whatIfOrderAsync(contract, order), self._request_timeout)
        except TimeoutError:
            timed_out = True
        except ConnectionError as exc:
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, f"preview not sent ({type(exc).__name__})"
            ) from exc
        finally:
            ib.wrapper.openOrder = original

        event = self._link_event_since(mark)
        if event is not None:
            state, code = event
            raise GatewayUnavailable(
                state, code, f"link event {code} while the preview was in flight; answer discarded"
            )
        errors = tuple(
            (code, text)
            for code, text in self._request_error_texts[code_mark:]
            if code not in INFO_CODES
        )
        codes = {code for code, _ in errors} | set(self._seen_codes[seen_mark:])
        effective_tif = echoed[-1] if echoed else None
        echo_order_ref = echoed_ref[-1] if echoed_ref else None
        echo_account = echoed_account[-1] if echoed_account else None
        if 154 in codes:
            state = "HALTED"
        elif 10349 in codes:
            state = "TIF_OVERRIDDEN"
        elif timed_out:
            if 321 not in codes:
                raise GatewayUnavailable(
                    REQUEST_TIMEOUT,
                    None,
                    f"preview did not answer within {self._request_timeout}s",
                )
            state = "READ_ONLY_API"
        elif getattr(response, "initMarginChange", None) is None:
            state = "EMPTY"
        else:
            state = "OK"
        if state == "OK":
            result = PreviewResult(
                state=state,
                init_margin_change=_money(response.initMarginChange),
                maint_margin_change=_money(getattr(response, "maintMarginChange", None)),
                commission=_money(getattr(response, "commission", None)),
                commission_currency=_text(response, "commissionCurrency"),
                warning_text=_text(response, "warningText"),
                errors=errors,
                effective_tif=effective_tif,
                sent_tif=PREVIEW_TIF,
                echo_order_ref=echo_order_ref,
                echo_account=echo_account,
            )
        else:
            result = PreviewResult(
                state=state,
                init_margin_change=None,
                maint_margin_change=None,
                commission=None,
                commission_currency="",
                warning_text="",
                errors=errors,
                effective_tif=effective_tif,
                sent_tif=PREVIEW_TIF,
                echo_order_ref=echo_order_ref,
                echo_account=echo_account,
            )
        self._log.info(
            'ibkr-state=PREVIEW code=- detail="state=%s init_margin=%s commission=%s '
            'tif sent=%s effective=%s order_ref=%s"',
            result.state,
            result.init_margin_change,
            result.commission,
            result.sent_tif,
            result.effective_tif,
            order_ref or "-",
        )
        return result

    def cancel_all(self, *, kill_evidence) -> None:
        """Cancel every open order of the account once: ``reqGlobalCancel`` (D-05).

        The only write this adapter ever lets through. It needs a positively
        detected kill switch (``kill_evidence.active is True``) and works once per
        session; message 58 is shut again right after. The request is
        fire-and-forget: its effect is proven only by reading the open orders
        again (the executor's job, Pitfall 5). Only the executor's kill path calls
        this (D-05).

        "Sent" means handed to the client library's ``sendMsg`` exactly once. Under
        request throttling the library may only queue the message and put it on the
        socket later, so ``sent=1`` in the ledger is no proof that the gateway got it;
        the re-read of the open orders is (IN-02).
        """
        if self._ib is None or self._handles is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        if getattr(kill_evidence, "active", False) is not True:
            raise ReadOnlyViolation("global cancel needs a positively detected kill switch")
        if self._permit.sent:
            raise ReadOnlyViolation("global cancel already used in this session")
        self._permit.open = True
        try:
            self._ib.reqGlobalCancel()
        except ConnectionError as exc:
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, f"global cancel not sent ({type(exc).__name__})"
            ) from exc
        finally:
            self._permit.open = False
        if self._permit.sent != 1:
            raise GatewayUnavailable(
                REQUEST_FAILED, None, "global cancel did not reach the wire exactly once"
            )
        self._log.warning('ibkr-state=GLOBAL_CANCEL_SENT code=- detail="count=1 reason=kill_switch"')

    def _read(self, name: str, make_awaitable):
        """One fail-closed read: timeout, no open link before, no link event during."""
        if self._ib is None or self._handles is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        opened = self._open_link()
        if opened is not None:
            raise GatewayUnavailable(opened[0], None, f"{opened[1]}; no {name} sent")
        mark = len(self._link_codes)
        code_mark = len(self._request_errors)
        result = self._request(name, make_awaitable)
        event = self._link_event_since(mark)
        if event is not None:
            state, code = event
            raise GatewayUnavailable(
                state, code, f"link event {code} while {name} was in flight; answer discarded"
            )
        request_error = self._request_error_since(code_mark)
        if request_error is not None:
            state, code = request_error
            raise GatewayUnavailable(
                REQUEST_FAILED,
                code,
                f"{name} failed with gateway code {code} ({state}); answer discarded",
            )
        return result

    def _request_error_since(self, mark: int) -> tuple[str, int] | None:
        """First request-scoped error after ``mark``, except code 200 and the preview codes.

        Only errors carrying a request id count: system and farm notices
        (``reqId == -1``, e.g. 2107) are session state, not an answer to this read.
        154 and 10349 are answers of the whatIf preview and evaluated there.
        """
        for code in self._request_errors[mark:]:
            if code not in INFO_CODES and code not in _PREVIEW_CODES and code != 200:
                return state_for_code(code), code
        return None

    def _request(self, name: str, make_awaitable):
        """One read request under the request timeout; a hang becomes a named state."""
        try:
            return self._call(make_awaitable, self._request_timeout)
        except TimeoutError as exc:
            raise GatewayUnavailable(
                REQUEST_TIMEOUT, None, f"{name} did not answer within {self._request_timeout}s"
            ) from exc
        except ConnectionError as exc:
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, f"{name} not sent ({type(exc).__name__})"
            ) from exc

    def _open_link(self) -> tuple[str, str] | None:
        """``(state, detail)`` of an open 1100/2110/1300, or None."""
        if self.link_lost:
            return "CONNECTIVITY_LOST", "1100 open, no 1101/1102 since"
        if self.server_link_broken:
            return "SERVER_LINK_BROKEN", "2110 open, no 1101/1102 since"
        if self.port_changed:
            return "PORT_CHANGED", "1300: the gateway changed its port"
        return None

    def _link_event_since(self, mark: int) -> tuple[str, int] | None:
        """``(state, code)`` of the first window-voiding event after ``mark``, or None.

        The first event names the state: 1100 then 1102 inside one window is
        still a lost link, whatever the flags say afterwards.
        """
        new = self._link_codes[mark:]
        if not new:
            return None
        return state_for_code(new[0]), new[0]

    def _unhealthy(self, state: str, detail: str) -> Health:
        self._log.warning('ibkr-state=%s code=- detail="%s"', state, detail)
        return Health(False, state, detail)

    def _call(self, make_awaitable, timeout: float):
        """Run one request in the adapter's loop, bounded by ``timeout`` seconds."""

        async def runner():
            # Created inside the running loop: the library builds futures eagerly.
            return await asyncio.wait_for(make_awaitable(), timeout)

        return self._loop.run_until_complete(runner())

    def _on_error(self, reqId, errorCode, errorString, contract) -> None:
        state = state_for_code(errorCode)
        level = logging.INFO if errorCode in INFO_CODES else logging.WARNING
        self._log.log(level, 'ibkr-state=%s code=%s detail="%s"', state, errorCode, errorString)
        self._seen_codes.append(errorCode)
        request_scoped = isinstance(reqId, int) and reqId >= 0
        if request_scoped:
            self._request_errors.append(errorCode)
            self._request_error_texts.append((errorCode, str(errorString)))
        # A link code, or any system notice that is not known to be benign, voids the
        # read window it lands in. Request-scoped codes answer their request and are
        # judged by _request_error_since instead.
        if errorCode in LINK_CODES or (
            not request_scoped and errorCode not in WINDOW_BENIGN_CODES
        ):
            self._link_codes.append(errorCode)
        if errorCode == 1100:
            self.link_lost = True
        elif errorCode in (1101, 1102):
            self.link_lost = False
            self.server_link_broken = False
        elif errorCode == 2110:
            self.server_link_broken = True
        elif errorCode == 1300:
            self.port_changed = True

    def _disconnect(self) -> None:
        """Close the session, let its socket close, and drop a loop this adapter owns.

        ``transport.close()`` only schedules ``connection_lost`` with ``call_soon``;
        one loop pass runs it before the loop closes, so the socket handle does
        not stay half open until garbage collection. An own loop is closed and
        unset as the current loop, so later code never finds a closed one there.
        """
        ib, self._ib = self._ib, None
        try:
            if ib is not None:
                with contextlib.suppress(ValueError, AttributeError):
                    ib.errorEvent -= self._on_error
                ib.disconnect()
                loop = self._loop
                if loop is not None and not loop.is_closed() and not loop.is_running():
                    loop.run_until_complete(asyncio.sleep(0))
        finally:
            if self._owns_loop and self._loop is not None:
                self._loop.close()
                asyncio.set_event_loop(None)
                self._loop = None
                self._owns_loop = False
