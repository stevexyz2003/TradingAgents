"""The market-data stream session: its own clientId, read-only, fail-closed, always cleaned up.

Nothing here opens a socket: the session runs on ``FakeStreamIB``, and the client
library's connect is blocked as in the adapter tests.
"""

import importlib.util
import logging
import math
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import ibkr_fakes
from tests.ibkr_fakes import FakeContract, FakeEvent, FakeIB, make_handles

pytestmark = pytest.mark.unit

broker = ibkr_fakes.load_broker()

_MODULE = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_market_data.py"


def _load_market_data():
    if "ibkr_market_data" in sys.modules:
        return sys.modules["ibkr_market_data"]
    spec = importlib.util.spec_from_file_location("ibkr_market_data", _MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_market_data"] = module
    spec.loader.exec_module(module)
    return module


md = _load_market_data()

FAST = {"connect_timeout": 0.05, "request_timeout": 0.05, "probe_timeout": 0.05}
POLL = 0.01
AAPL, MSFT = 265598, 272093


class FakeStreamIB(FakeIB):
    """FakeIB that allows the stream calls; every other market-data call stays forbidden.

    ``ticks`` maps a conId to the tickers the loop delivers once it is
    subscribed; ``link_events`` are error events emitted shortly after the
    first subscription.
    """

    def __init__(self, *, ticks=None, rows=None, link_events=(), drop_socket=False, **kw):
        super().__init__(**kw)
        self.pendingTickersEvent = FakeEvent()
        self.ticks = dict(ticks or {})
        #: conId -> number of contract-details rows to answer with (default 1)
        self.rows = dict(rows or {})
        self.link_events = list(link_events)
        self.drop_socket = drop_socket
        self.subscribed: list[int] = []
        self.cancelled: list[int] = []
        #: The session's event loop; ticks and events are scheduled on it.
        self.loop = None

    async def reqContractDetailsAsync(self, contract):
        self.calls.append("stream_details")
        count = self.rows.get(contract.conId, 1)
        symbol = {AAPL: "AAPL", MSFT: "MSFT"}.get(contract.conId, "")
        return [
            SimpleNamespace(contract=FakeContract(conId=contract.conId, symbol=symbol))
            for _ in range(count)
        ]

    def reqMktData(self, contract, genericTickList="", snapshot=False, regulatory=False):
        self.calls.append("reqMktData")
        self.subscribed.append(contract.conId)
        loop = self.loop  # the session's loop; set by _session
        tickers = [
            SimpleNamespace(contract=contract, **t) for t in self.ticks.get(contract.conId, ())
        ]
        if tickers:
            loop.call_soon(self.pendingTickersEvent.emit, tickers)
        if len(self.subscribed) == 1:
            for args in self.link_events:
                loop.call_soon(self.errorEvent.emit, *args)
            if self.drop_socket:
                loop.call_soon(setattr, self, "connected", False)
        return SimpleNamespace(contract=contract)

    def cancelMktData(self, contract):
        self.calls.append("cancelMktData")
        self.cancelled.append(contract.conId)
        return True


@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)


def _session(fake, loop):
    fake.loop = loop
    session = md.IbkrMarketData(
        "127.0.0.1", 7497, ib_factory=make_handles(fake), loop=loop, poll=POLL, **FAST
    )
    session.connect()
    return session


def _tick(bid=1.0, ask=2.0, last=1.5, **kw):
    base = {"bid": bid, "ask": ask, "last": last, "bidSize": 10, "askSize": 20, "lastSize": 5}
    return {**base, "volume": 1000, "time": None, **kw}


def _no_writes(fake):
    return not any(call in fake.calls for call in (*ibkr_fakes.WRITE_CALLS, "whatIfOrder"))


# --- the session --------------------------------------------------------------------------


def test_connects_with_its_own_client_id_read_only_and_delayed(loop):
    fake = FakeStreamIB()
    _session(fake, loop)
    assert fake.connect_kwargs["clientId"] == 20002 == md.MARKET_DATA_CLIENT_ID
    assert md.MARKET_DATA_CLIENT_ID != broker.EXECUTOR_CLIENT_ID
    assert fake.connect_kwargs["readonly"] is True
    assert fake.barrier_armed_at_connect is True
    assert "reqMarketDataType(3)" in fake.calls


def test_account_guard_applies_to_the_stream_session(loop):
    fake = FakeStreamIB(accounts=("U1234567",))
    with pytest.raises(broker.AccountGuardViolation):
        _session(fake, loop)
    assert "reqMktData" not in fake.calls


def test_shares_the_adapter_exception_class():
    assert md.GatewayUnavailable is broker.GatewayUnavailable


# --- streaming ----------------------------------------------------------------------------


def test_stream_delivers_broker_neutral_ticks_and_cleans_up(loop):
    fake = FakeStreamIB(
        ticks={AAPL: [_tick()], MSFT: [_tick(bid=math.nan, ask=1.7976931348623157e308)]}
    )
    session = _session(fake, loop)
    got = []
    session.stream([AAPL, MSFT], got.append, duration=0.05)

    assert all(isinstance(t, md.MarketTick) for t in got)
    by_id = {t.con_id: t for t in got}
    assert by_id[AAPL] == md.MarketTick(AAPL, "AAPL", 1.0, 2.0, 1.5, 10.0, 20.0, 5.0, 1000.0, None)
    assert (by_id[MSFT].bid, by_id[MSFT].ask) == (None, None)
    assert fake.subscribed == fake.cancelled == [AAPL, MSFT]
    assert fake.pendingTickersEvent.handlers == []
    assert _no_writes(fake)


def test_stop_flag_ends_the_stream(loop):
    fake = FakeStreamIB()
    session = _session(fake, loop)
    stop = threading.Event()
    stop.set()
    session.stream([AAPL], lambda _t: None, stop=stop)
    assert fake.cancelled == [AAPL]


def test_callback_error_is_logged_and_the_stream_goes_on(loop, caplog):
    fake = FakeStreamIB(ticks={AAPL: [_tick(), _tick(last=1.6)]})
    session = _session(fake, loop)
    seen = []

    def on_tick(tick):
        seen.append(tick.last)
        raise ValueError("callback bug")

    with caplog.at_level(logging.ERROR, logger="ibkr_market_data"):
        session.stream([AAPL], on_tick, duration=0.03)
    assert seen == [1.5, 1.6]
    assert "STREAM_CALLBACK_ERROR" in caplog.text
    assert fake.cancelled == [AAPL]


def test_empty_con_ids_subscribe_nothing(loop):
    fake = FakeStreamIB()
    _session(fake, loop).stream([], lambda _t: None, duration=0.01)
    assert "reqMktData" not in fake.calls


# --- fail-closed --------------------------------------------------------------------------


def test_link_loss_during_the_stream_ends_it_and_cancels(loop):
    fake = FakeStreamIB(link_events=[(-1, 1100, "Connectivity lost", None)])
    session = _session(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as exc:
        session.stream([AAPL], lambda _t: None, duration=5)
    assert (exc.value.state, exc.value.code) == ("CONNECTIVITY_LOST", 1100)
    assert fake.cancelled == [AAPL]
    assert fake.pendingTickersEvent.handlers == []


def test_socket_drop_during_the_stream_ends_it(loop):
    fake = FakeStreamIB(drop_socket=True)
    session = _session(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as exc:
        session.stream([AAPL], lambda _t: None, duration=5)
    assert exc.value.state == "NOT_CONNECTED"
    assert fake.cancelled == [AAPL]


def test_open_link_blocks_the_start(loop):
    fake = FakeStreamIB()
    session = _session(fake, loop)
    fake.errorEvent.emit(-1, 1100, "Connectivity lost", None)
    with pytest.raises(broker.GatewayUnavailable) as exc:
        session.stream([AAPL], lambda _t: None, duration=0.01)
    assert exc.value.state == "CONNECTIVITY_LOST"
    assert "stream_details" not in fake.calls
    assert "reqMktData" not in fake.calls


@pytest.mark.parametrize("rows", [0, 2])
def test_a_conid_that_does_not_resolve_to_one_contract_is_refused(loop, rows):
    fake = FakeStreamIB(rows={MSFT: rows})
    session = _session(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as exc:
        session.stream([AAPL, MSFT], lambda _t: None, duration=0.01)
    assert exc.value.state == broker.REQUEST_FAILED
    assert "reqMktData" not in fake.calls


def test_stream_before_connect_is_refused(loop):
    session = md.IbkrMarketData(
        "127.0.0.1", 7497, ib_factory=make_handles(FakeStreamIB()), loop=loop, **FAST
    )
    with pytest.raises(broker.GatewayUnavailable) as exc:
        session.stream([AAPL], lambda _t: None)
    assert exc.value.state == "NOT_CONNECTED"


def test_context_manager_disconnects(loop):
    fake = FakeStreamIB()
    with md.IbkrMarketData("127.0.0.1", 7497, ib_factory=make_handles(fake), loop=loop, **FAST):
        pass
    assert fake.calls[-1] == "disconnect"
