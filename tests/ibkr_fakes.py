"""Shared stand-ins for the IBKR adapter tests: a fake client, a loop, a connect block.

Nothing here opens a socket. The real gateway listens on this machine, and the
suite-wide network block does not stop an asyncio loopback connection on
Windows, so the IBKR test modules also block the client library's connect.
"""

import asyncio
import copy
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

_BROKER = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_broker.py"

#: The write calls the adapter must block on the client object.
WRITE_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions")
#: The client's send path, which the adapter guards on the wire (message ids).
WIRE_CALLS = ("send", "sendMsg")


def load_broker():
    """The adapter module, loaded once under one name so its exception classes are shared."""
    if "ibkr_broker" in sys.modules:
        return sys.modules["ibkr_broker"]
    spec = importlib.util.spec_from_file_location("ibkr_broker", _BROKER)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_broker"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_broker", None)
        raise
    return module


class FakeEvent:
    """Minimal event: handlers added with +=, called by emit()."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


@dataclass
class FakeContract:
    conId: int = 0
    symbol: str = ""
    secType: str = "STK"
    localSymbol: str = ""
    currency: str = "USD"
    exchange: str = ""
    primaryExchange: str = ""
    tradingClass: str = ""


def stk_contract(
    symbol,
    con_id,
    primary_exchange="NASDAQ",
    currency="USD",
    local_symbol=None,
    trading_class="NMS",
    exchange="SMART",
    sec_type="STK",
):
    """A contract row as the client library reports a qualified match."""
    return FakeContract(
        conId=con_id,
        symbol=symbol,
        secType=sec_type,
        localSymbol=symbol if local_symbol is None else local_symbol,
        currency=currency,
        exchange=exchange,
        primaryExchange=primary_exchange,
        tradingClass=trading_class,
    )


def contract_detail(
    contract,
    *,
    valid_exchanges="SMART,NASDAQ,ARCA",
    order_types="ACTIVETIM,LMT,MKT,STP",
    time_zone_id="US/Eastern",
    liquid_hours="",
    trading_hours="",
    long_name="",
):
    """A ContractDetails row as the client library reports it."""
    return SimpleNamespace(
        contract=contract,
        longName=long_name,
        validExchanges=valid_exchanges,
        orderTypes=order_types,
        timeZoneId=time_zone_id,
        liquidHours=liquid_hours,
        tradingHours=trading_hours,
    )


def position(account, symbol, quantity, avg_cost=100.0, **contract):
    """A position row as the client library reports it."""
    return SimpleNamespace(
        account=account,
        contract=FakeContract(symbol=symbol, localSymbol=symbol, **contract),
        position=quantity,
        avgCost=avg_cost,
    )


def account_value(tag, value, currency="EUR", account="DUQ634065"):
    """An account summary row as the client library reports it."""
    return SimpleNamespace(account=account, tag=tag, value=value, currency=currency, modelCode="")


async def _forever():
    await asyncio.Event().wait()


class FakeIB:
    """Stand-in for the client library's IB object with a controllable outcome."""

    def __init__(
        self,
        accounts=("DUQ634065",),
        refuse=None,
        emit_on_connect=(),
        positions=None,
        summary=None,
        probe="ok",
        emit_during=None,
        qualify=None,
        details=None,
    ):
        self.accounts = list(accounts)
        self.refuse = refuse
        self.emit_on_connect = list(emit_on_connect)
        #: call name ("positions", "account_summary", "probe") -> error events emitted
        #: while that request is in flight; the answer still comes back well formed.
        self.emit_during = dict(emit_during or {})
        self._positions = [] if positions is None else positions
        self._summary = [account_value("TotalCashValue", "1000.0")] if summary is None else summary
        self.probe = probe
        #: symbol -> matching FakeContracts (or "hang") for qualifyContractsAsync
        self.qualify = dict(qualify) if isinstance(qualify, dict) else (qualify or {})
        #: conId -> ContractDetails rows (or "hang") for reqContractDetailsAsync
        self.details = dict(details) if isinstance(details, dict) else (details or {})
        #: (copy of the contract before mutation, returnAll) per qualify input
        self.qualify_calls: list = []
        self.calls: list[str] = []
        self.connect_kwargs: dict = {}
        self.connected = False
        self.errorEvent = FakeEvent()
        self.wrapper = SimpleNamespace(acctSummary={})
        self._recorders = {name: self._record(name) for name in (*WRITE_CALLS, *WIRE_CALLS)}
        self.client = SimpleNamespace(**self._recorders)

    def _record(self, name):
        def recorder(*_args, **_kwargs):
            self.calls.append(name)

        return recorder

    async def connectAsync(self, host, port, clientId, timeout, readonly, **kw):
        self.connect_kwargs = dict(
            host=host, port=port, clientId=clientId, timeout=timeout, readonly=readonly, **kw
        )
        self.barrier_armed_at_connect = all(
            getattr(self.client, name) is not self._recorders[name]
            for name in (*WRITE_CALLS, *WIRE_CALLS)
        )
        self.calls.append("connect")
        for args in self.emit_on_connect:
            self.errorEvent.emit(*args)
        if self.refuse == "hang":
            # A peer that accepts the socket and never answers; ignores ``timeout``.
            await _forever()
        if self.refuse is not None:
            raise self.refuse
        self.connected = True

    def managedAccounts(self):
        return list(self.accounts)

    def isConnected(self):
        return self.connected

    def disconnect(self):
        self.calls.append("disconnect")
        self.connected = False

    def _emit_during(self, name):
        for args in self.emit_during.get(name, ()):
            self.errorEvent.emit(*args)

    async def reqPositionsAsync(self):
        self.calls.append("positions")
        self._emit_during("positions")
        if self._positions == "hang":
            await _forever()
        return list(self._positions)

    async def accountSummaryAsync(self, account=""):
        # Modelled on the library (ib.py:2232-2242 in 2.1.0): a request goes out
        # only while ``wrapper.acctSummary`` is empty; after that the cache answers.
        if not self.wrapper.acctSummary:
            self.calls.append("account_summary")
            self._emit_during("account_summary")
            if self._summary == "hang":
                await _forever()
            # Keyed by row index, not (account, tag, currency): a duplicate row stays visible.
            self.wrapper.acctSummary.update(enumerate(self._summary))
        rows = list(self.wrapper.acctSummary.values())
        return [v for v in rows if v.account == account] if account else rows

    def reqMarketDataType(self, marketDataType):
        self.calls.append(f"reqMarketDataType({marketDataType})")

    async def qualifyContractsAsync(self, *contracts, returnAll=False):
        # Modelled on the library (2.1.0): one slot per input; None for no match,
        # the (mutated) input for one match, a list for several (returnAll only).
        self.calls.append("qualify")
        for contract in contracts:
            self.qualify_calls.append((copy.copy(contract), returnAll))
        self._emit_during("qualify")
        if self.qualify == "hang":
            await _forever()
        slots = []
        for contract in contracts:
            hits = [
                h
                for h in self.qualify.get(contract.symbol, [])
                if h.secType == contract.secType
            ]
            if not hits:
                slots.append(None)
            elif len(hits) == 1:
                for field, value in vars(hits[0]).items():
                    setattr(contract, field, value)
                slots.append(contract)
            else:
                slots.append(list(hits) if returnAll else None)
        return slots

    async def reqContractDetailsAsync(self, contract):
        if not contract.exchange:
            self.calls.append("probe")
            self._emit_during("probe")
            if self.probe == "hang":
                await _forever()
            if self.probe == "empty":
                return []
            return [SimpleNamespace(contract=FakeContract(conId=contract.conId))]
        self.calls.append("contract_details")
        self.details_calls = [*getattr(self, "details_calls", []), copy.copy(contract)]
        self._emit_during("contract_details")
        if self.details == "hang":
            await _forever()
        return list(self.details.get(contract.conId, []))

    # Phase 3 resolution only reads; it never touches orders, any of these is a bug. Each
    # one is recorded before it raises, so a check over ``calls`` can see it even
    # when the adapter swallows the AssertionError (REQ-IBKR-66).
    def _forbidden(self, name, why=""):
        self.calls.append(name)
        raise AssertionError(f"phase 2 must not call {name}{why}")

    def positions(self):
        self._forbidden("positions()", " (library cache)")

    def reqAllOpenOrders(self, *a, **k):
        self._forbidden("reqAllOpenOrders")

    def reqCompletedOrders(self, *a, **k):
        self._forbidden("reqCompletedOrders")

    def reqExecutions(self, *a, **k):
        self._forbidden("reqExecutions")

    def whatIfOrder(self, *a, **k):
        self._forbidden("whatIfOrder")

    def placeOrder(self, *a, **k):
        self._forbidden("placeOrder")


def make_handles(fake):
    """An ib_factory for IbkrBroker that hands out the given fake."""
    broker = load_broker()

    def factory():
        return broker.IbHandles(ib=fake, contract=FakeContract, fetch_none=0)

    return factory


def session_loop():
    """One event loop for the session, created before the per-test network block."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


def block_real_ib_connect(monkeypatch):
    """Make the client library's connect fail at once, so no test reaches the gateway."""
    try:
        import ib_async
        import ib_async.client
    except ImportError:
        return

    async def refuse(*_args, **_kwargs):
        raise OSError("test tried to reach the IBKR gateway")

    monkeypatch.setattr(ib_async.IB, "connectAsync", refuse)
    monkeypatch.setattr(ib_async.client.Client, "connectAsync", refuse)
