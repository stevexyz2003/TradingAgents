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

#: Seconds the handshake may take before the session counts as unreachable.
CONNECT_TIMEOUT_S = 10.0
#: Seconds any read request may take; the library's own default waits forever.
REQUEST_TIMEOUT_S = 10.0
#: Seconds the liveness probe may take.
PROBE_TIMEOUT_S = 5.0

#: Client calls that would change the account; blocked before connectAsync.
_WRITE_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions")

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
    2172: "GATEWAY_VERSION_EXPIRING",
}

#: Farm-OK notices: logged at INFO, never as a warning.
INFO_CODES = frozenset({2104, 2106, 2158})

# Named states without a gateway code.
CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
PROBE_TIMEOUT = "PROBE_TIMEOUT"
PROBE_FAILED = "PROBE_FAILED"
SNAPSHOT_INCOMPLETE = "SNAPSHOT_INCOMPLETE"
HEALTHY = "HEALTHY"
UNKNOWN = "UNKNOWN"


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


def _arm_write_barrier(client) -> None:
    """Replace the client's write calls with one that refuses, on this instance."""
    for name in _WRITE_CALLS:

        def refuse(*_args, _name=name, **_kwargs):
            raise ReadOnlyViolation(
                f"read-only session: {_name} refused before it reached the gateway"
            )

        setattr(client, name, refuse)


class IbkrBroker:
    """One read-only session against the paper gateway.

    Public in phase 2: ``connect``, ``positions``, ``health``. Use as a context
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
        request_timeout: float = REQUEST_TIMEOUT_S,
        probe_timeout: float = PROBE_TIMEOUT_S,
    ):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib_factory = ib_factory
        self._loop = loop
        self._owns_loop = False
        self._log = logger or logging.getLogger("ibkr_broker")
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout
        self._probe_timeout = probe_timeout
        self._handles: IbHandles | None = None
        self._ib = None
        self.link_lost = False
        self.server_link_broken = False
        self.port_changed = False
        self._seen_codes: list[int] = []

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
        handles = self._ib_factory()
        ib = handles.ib
        self._handles, self._ib = handles, ib
        # Subscribed first: a 326 arrives before the handshake completes.
        ib.errorEvent += self._on_error
        # D-01: the barrier stands before a single byte flows.
        _arm_write_barrier(ib.client)
        host, port, timeout = self._host, self._port, self._connect_timeout
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
                timeout + 5,
            )
        except TimeoutError as exc:  # before OSError: TimeoutError is one
            self._disconnect()
            if 326 in self._seen_codes:
                raise GatewayUnavailable(
                    "CLIENT_ID_IN_USE", 326, f"clientId {self._client_id} already in use"
                ) from exc
            raise GatewayUnavailable(
                CONNECT_TIMEOUT, None, f"no handshake from {host}:{port} within {timeout}s"
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
        accounts = list(ib.managedAccounts())
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

    def health(self) -> Health:
        """Liveness from a real server answer, not from the socket (REQ-IBKR-09).

        Healthy only when the socket is up, no 1100/2110/1300 is open, and the
        contract-details probe for ``PROBE_CON_ID`` returns exactly that contract
        within ``probe_timeout``. One loop tick runs before the state flags are
        read, so an error event already queued in the loop (a 1100 that arrived
        between two calls) reaches ``_on_error`` first. While a flag is open no
        probe is sent.

        Known limit (assumption A4): should the gateway answer the probe from a
        cache while the server link is down, only the 1100/2110 flags reveal it.
        """
        ib, handles = self._ib, self._handles
        if ib is None or handles is None:
            return self._unhealthy("NOT_CONNECTED", "no session; connect() first")
        self._call(lambda: asyncio.sleep(0), self._probe_timeout)
        if not ib.isConnected():
            return self._unhealthy("NOT_CONNECTED", "socket is down")
        if self.link_lost:
            return self._unhealthy("CONNECTIVITY_LOST", "1100 open, no 1101/1102 since")
        if self.server_link_broken:
            return self._unhealthy("SERVER_LINK_BROKEN", "2110 open, no 1101/1102 since")
        if self.port_changed:
            return self._unhealthy("PORT_CHANGED", "1300: the gateway changed its port")
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
        """
        ib = self._ib
        if ib is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        raw = self._request("reqPositions", ib.reqPositionsAsync)
        values = self._request("accountSummary", lambda: ib.accountSummaryAsync(EXPECTED_ACCOUNT))

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
        ib, self._ib = self._ib, None
        if ib is not None:
            with contextlib.suppress(ValueError, AttributeError):
                ib.errorEvent -= self._on_error
            ib.disconnect()
        if self._owns_loop and self._loop is not None:
            self._loop.close()
            self._loop = None
            self._owns_loop = False
