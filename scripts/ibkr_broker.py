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
}

#: Farm-OK and delayed-market-data notices: expected states, logged at INFO.
#: The halt code 154 stays unmapped here; it is measured at the whatIf preview
#: in phase 4 (REQ-IBKR-67).
INFO_CODES = frozenset({2104, 2106, 2158, 10089, 10090, 10167})

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


@dataclass(frozen=True)
class BrokerPosition:
    """One held position of the paper account, broker-neutral."""

    symbol: str
    sec_type: str
    local_symbol: str
    currency: str
    quantity: float
    avg_cost: float


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
    as_of: datetime


@dataclass(frozen=True)
class Health:
    """Liveness verdict: ``ok`` only on a real server answer."""

    ok: bool
    state: str
    detail: str


def _default_ib_factory() -> IbHandles:
    from ib_async import IB, Contract, StartupFetchNONE  # the only import site in the repo

    return IbHandles(IB(), Contract, StartupFetchNONE)


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


def _arm_write_barrier(client) -> None:
    """Refuse every write on this client instance, by call name and on the wire.

    The named write calls are replaced first. ``placeOrder`` and message id 3
    pass only as a whatIf preview of a stock (D-13); every real order is refused.
    Then ``send`` (fields) and ``sendMsg`` (the serialized message, id first) are
    wrapped, so a write message is refused whatever path produced it:
    ``replaceFA``, a raw ``send(3, ...)`` or a write call added by a later library
    version that reuses one of these ids. Reads pass through unchanged.
    """
    original_place = getattr(client, "placeOrder", None)

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

    for name in _WRITE_CALLS:

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
        elif msg_id in _WRITE_MESSAGE_IDS:
            refuse_message(msg_id)
        return original_send(*fields, **kwargs)

    def guarded_send_msg(msg, *args, **kwargs):
        head = msg.split("\0", 1)[0] if isinstance(msg, str) else None
        msg_id = _message_id(head) if head else None
        if msg_id == 3:
            if not _whatif_in_message(msg):
                refuse_message(msg_id)
        elif msg_id in _WRITE_MESSAGE_IDS:
            refuse_message(msg_id)
        return original_send_msg(msg, *args, **kwargs)

    client.send = guarded_send
    client.sendMsg = guarded_send_msg


class IbkrBroker:
    """One read-only session against the paper gateway.

    Public: ``connect``, ``positions``, ``health``, ``search_contract``,
    ``contract_details``. Use as a context
    manager; leaving it disconnects.
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
        self.link_lost = False
        self.server_link_broken = False
        self.port_changed = False
        self._seen_codes: list[int] = []
        #: Codes of errors tied to a request id (``reqId >= 0``), in order.
        self._request_errors: list[int] = []
        #: Every LINK_CODES event of the session, in order; read windows compare its length.
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
        _arm_write_barrier(ib.client)
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
        cache while the server link is down, only the 1100/2110 events reveal
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
        the margin-levered buying power.

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
        for v in mine:
            if v.tag in ("AvailableFunds", "NetLiquidation"):
                self._log.info("ibkr-account %s=%s %s (log only)", v.tag, v.value, v.currency)
        return AccountSnapshot(
            account=EXPECTED_ACCOUNT,
            positions=held,
            cash=float(cash.value),
            cash_currency=cash.currency,
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
        """First request-scoped error after ``mark``, except code 200.

        Only errors carrying a request id count: system and farm notices
        (``reqId == -1``, e.g. 2107) are session state, not an answer to this read.
        """
        for code in self._request_errors[mark:]:
            if code not in INFO_CODES and code != 200:
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
        """``(state, code)`` of the first link event after ``mark``, or None.

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
        if isinstance(reqId, int) and reqId >= 0:
            self._request_errors.append(errorCode)
        if errorCode in LINK_CODES:
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
