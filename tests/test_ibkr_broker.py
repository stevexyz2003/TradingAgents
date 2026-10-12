"""The IBKR adapter: write barrier, paper guard, named states, liveness, fresh reads.

Every test runs against FakeIB. A real connect is blocked in this module, because
the suite-wide network block does not stop asyncio loopback on Windows and the
real paper gateway listens on this machine.
"""

import asyncio
import logging
import time

import pytest

from tests import ibkr_fakes
from tests.ibkr_fakes import FakeIB, account_value, make_handles, position

pytestmark = pytest.mark.unit

broker = ibkr_fakes.load_broker()

FAST = {"connect_timeout": 0.05, "request_timeout": 0.05, "probe_timeout": 0.05}
FORBIDDEN_CALLS = (*ibkr_fakes.WRITE_CALLS, "whatIfOrder")


@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)


def _broker(fake, loop, host="127.0.0.1", port=7497):
    return broker.IbkrBroker(host, port, ib_factory=make_handles(fake), loop=loop, **FAST)


def _connected(fake, loop):
    adapter = _broker(fake, loop)
    adapter.connect()
    return adapter


# --- connect: read-only flag, fixed client id, no startup fetch -------------------------


def test_connect_uses_readonly_fixed_client_id_and_no_startup_fetch(loop):
    fake = FakeIB()
    _broker(fake, loop, host="10.0.0.5", port=4002).connect()
    kw = fake.connect_kwargs
    assert kw["readonly"] is True
    assert kw["clientId"] == 20001 == broker.EXECUTOR_CLIENT_ID
    assert kw["fetchFields"] == 0
    assert (kw["host"], kw["port"]) == ("10.0.0.5", 4002)


def test_write_barrier_is_armed_before_connect(loop):
    fake = FakeIB()
    _connected(fake, loop)
    assert fake.barrier_armed_at_connect is True
    for name in ibkr_fakes.WRITE_CALLS:
        with pytest.raises(broker.ReadOnlyViolation):
            getattr(fake.client, name)()
    assert not any(call in fake.calls for call in FORBIDDEN_CALLS)


def test_write_barrier_on_the_real_client_object():
    ib_async = pytest.importorskip("ib_async")
    ib = ib_async.IB()
    broker._arm_write_barrier(ib.client)
    order = ib_async.Order(orderId=1, action="BUY", totalQuantity=1, orderType="MKT")
    with pytest.raises(broker.ReadOnlyViolation):
        ib.placeOrder(ib_async.Contract(conId=265598), order)
    with pytest.raises(broker.ReadOnlyViolation):
        ib.reqGlobalCancel()


# Outgoing write messages of the pinned library (client.py, 2.1.0): PLACE_ORDER,
# CANCEL_ORDER, REPLACE_FA, EXERCISE_OPTIONS, REQ_GLOBAL_CANCEL.
WRITE_MESSAGE_IDS = (3, 4, 19, 21, 58)


@pytest.mark.parametrize("msg_id", WRITE_MESSAGE_IDS)
def test_write_barrier_refuses_write_messages_on_the_wire(msg_id):
    # WR-01 negative control: the raw send path bypasses every named write call.
    # Unguarded, the unconnected client raises ConnectionError, not the refusal.
    ib_async = pytest.importorskip("ib_async")
    client = ib_async.IB().client
    broker._arm_write_barrier(client)
    with pytest.raises(broker.ReadOnlyViolation, match=f"message {msg_id}"):
        client.send(msg_id, 1, 42)
    with pytest.raises(broker.ReadOnlyViolation, match=f"message {msg_id}"):
        client.sendMsg(f"{msg_id}\0" + "1\0")


def test_write_barrier_covers_replace_fa_which_has_no_named_block():
    ib_async = pytest.importorskip("ib_async")
    ib = ib_async.IB()
    broker._arm_write_barrier(ib.client)
    # IB.replaceFA first asks the unconnected client for a request id, so the
    # client call is the one to test; it sends message 19 through send().
    with pytest.raises(broker.ReadOnlyViolation, match="message 19"):
        ib.client.replaceFA(1, 1, "<xml/>")


def test_write_barrier_lets_read_messages_through():
    ib_async = pytest.importorskip("ib_async")
    client = ib_async.IB().client
    broker._arm_write_barrier(client)
    # reqPositions (61) reaches the library's own send, which refuses: not connected.
    with pytest.raises(ConnectionError, match="Not connected"):
        client.send(61, 1)
    with pytest.raises(ConnectionError, match="Not connected"):
        client.reqPositions()


# --- paper guard -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "accounts",
    [
        ["DU0000001"],  # foreign account
        ["DUQ634065", "DU0000001"],  # superset: not exactly the paper account
        [],  # empty
    ],
    ids=["foreign", "superset", "empty"],
)
def test_guard_rejects_anything_but_the_paper_account(loop, accounts):
    fake = FakeIB(accounts=accounts)
    with pytest.raises(broker.AccountGuardViolation) as info:
        _broker(fake, loop).connect()
    assert info.value.accounts_seen == accounts
    assert "disconnect" in fake.calls
    assert not any(call in fake.calls for call in FORBIDDEN_CALLS)


def test_guard_accepts_exact_account(loop):
    fake = FakeIB(accounts=["DUQ634065"])
    _connected(fake, loop)
    assert "disconnect" not in fake.calls


def test_guard_target_is_a_code_constant():
    assert broker.EXPECTED_ACCOUNT == "DUQ634065"


# --- connect failures map to named states ----------------------------------------------


def test_unreachable_maps_to_502(loop):
    fake = FakeIB(refuse=ConnectionRefusedError())
    with pytest.raises(broker.GatewayUnavailable) as info:
        _broker(fake, loop).connect()
    exc = info.value
    assert (exc.state, exc.code) == ("GATEWAY_UNREACHABLE", 502)
    assert "Gateway nicht erreichbar" in exc.detail
    assert str(exc).startswith("ibkr-state=GATEWAY_UNREACHABLE code=502 detail=")


def test_timeout_after_326_maps_to_client_id_in_use(loop):
    fake = FakeIB(
        emit_on_connect=[(-1, 326, "client id is already in use", None)], refuse=TimeoutError()
    )
    with pytest.raises(broker.GatewayUnavailable) as info:
        _broker(fake, loop).connect()
    assert (info.value.state, info.value.code) == ("CLIENT_ID_IN_USE", 326)


def test_timeout_without_326_maps_to_connect_timeout(loop):
    fake = FakeIB(refuse=TimeoutError())
    with pytest.raises(broker.GatewayUnavailable) as info:
        _broker(fake, loop).connect()
    assert (info.value.state, info.value.code) == ("CONNECT_TIMEOUT", None)
    assert str(info.value).startswith("ibkr-state=CONNECT_TIMEOUT code=- ")


@pytest.mark.parametrize(
    ("refuse", "state", "code"),
    [
        (ConnectionResetError(), "SOCKET_EOF", 507),
        (EOFError(), "SOCKET_EOF", 507),
        (ConnectionError("Not connected"), "NOT_CONNECTED", 504),
        (OSError("unreachable"), "GATEWAY_UNREACHABLE", 502),
    ],
)
def test_other_connect_failures_map_to_named_states(loop, refuse, state, code):
    with pytest.raises(broker.GatewayUnavailable) as info:
        _broker(FakeIB(refuse=refuse), loop).connect()
    assert (info.value.state, info.value.code) == (state, code)


# --- error code table ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (502, "GATEWAY_UNREACHABLE"),
        (504, "NOT_CONNECTED"),
        (507, "SOCKET_EOF"),
        (326, "CLIENT_ID_IN_USE"),
        (1100, "CONNECTIVITY_LOST"),
        (1101, "RESTORED_DATA_LOST"),
        (1102, "RESTORED_DATA_KEPT"),
        (1300, "PORT_CHANGED"),
        (2103, "FARM_DOWN"),
        (2105, "FARM_DOWN"),
        (2104, "FARM_OK"),
        (2106, "FARM_OK"),
        (2158, "FARM_OK"),
        (2110, "SERVER_LINK_BROKEN"),
        (321, "READ_ONLY_API"),  # measured read-only marker (ibkr-konto-befund.md)
        (10015, "TRADING_NOT_ALLOWED"),
        (10089, "MARKET_DATA_NOT_SUBSCRIBED"),
        (10090, "MARKET_DATA_NOT_SUBSCRIBED"),
        (2172, "GATEWAY_VERSION_EXPIRING"),
        (99999, "UNKNOWN"),
    ],
)
def test_state_map(code, state):
    assert broker.state_for_code(code) == state


@pytest.mark.parametrize("code", [2104, 2106, 2158])
def test_farm_ok_codes_log_at_info(loop, caplog, code):
    adapter = _broker(FakeIB(), loop)
    with caplog.at_level(logging.INFO, logger="ibkr_broker"):
        adapter._on_error(-1, code, "data farm connection is OK", None)
    assert code in broker.INFO_CODES
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert f"ibkr-state=FARM_OK code={code}" in record.getMessage()


def test_other_codes_log_at_warning(loop, caplog):
    adapter = _broker(FakeIB(), loop)
    with caplog.at_level(logging.INFO, logger="ibkr_broker"):
        adapter._on_error(-1, 321, "read-only", None)
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert 'ibkr-state=READ_ONLY_API code=321 detail="read-only"' in record.getMessage()


# --- the real connect is blocked here --------------------------------------------------


def test_real_connect_is_blocked_in_this_module(loop):
    ib_async = pytest.importorskip("ib_async")
    # Port 1, never 7497: should the block fail, this still cannot reach the gateway.
    with pytest.raises(OSError, match="IBKR gateway"):
        loop.run_until_complete(
            ib_async.IB().connectAsync("127.0.0.1", 1, clientId=20001, timeout=1)
        )


# --- health: liveness rests on a real probe answer --------------------------------------


def test_health_ok_with_one_probe_answer(loop):
    fake = FakeIB(probe="ok")
    health = _connected(fake, loop).health()
    assert (health.ok, health.state) == (True, "HEALTHY")
    assert "probe" in fake.calls


def test_health_socket_up_session_dead(loop):
    fake = FakeIB(probe="hang")
    adapter = _connected(fake, loop)
    started = time.monotonic()
    health = adapter.health()
    assert time.monotonic() - started < 1.0
    assert fake.isConnected() is True
    assert (health.ok, health.state) == (False, "PROBE_TIMEOUT")


def test_health_empty_probe_is_unhealthy(loop):
    health = _connected(FakeIB(probe="empty"), loop).health()
    assert (health.ok, health.state) == (False, "PROBE_FAILED")


def test_health_after_1100_then_1102(loop):
    fake = FakeIB()
    adapter = _connected(fake, loop)
    fake.errorEvent.emit(-1, 1100, "Connectivity between IB and TWS has been lost", None)
    health = adapter.health()
    assert (health.ok, health.state) == (False, "CONNECTIVITY_LOST")
    assert "probe" not in fake.calls
    fake.errorEvent.emit(-1, 1102, "Connectivity restored, data maintained", None)
    assert adapter.health().ok is True


def test_health_sees_1100_queued_before_the_call(loop):
    fake = FakeIB()
    adapter = _connected(fake, loop)
    loop.call_soon(
        fake.errorEvent.emit, -1, 1100, "Connectivity between IB and TWS has been lost", None
    )
    health = adapter.health()
    assert health.state == "CONNECTIVITY_LOST"
    assert "probe" not in fake.calls


@pytest.mark.parametrize(("code", "state"), [(2110, "SERVER_LINK_BROKEN"), (1300, "PORT_CHANGED")])
def test_health_after_open_link_codes(loop, code, state):
    fake = FakeIB()
    adapter = _connected(fake, loop)
    fake.errorEvent.emit(-1, code, "link event", None)
    health = adapter.health()
    assert (health.ok, health.state) == (False, state)
    assert "probe" not in fake.calls


def test_health_sees_1100_during_the_probe(loop):
    # The probe still answers well formed; only the 1100 inside its window shows the loss.
    fake = FakeIB(emit_during={"probe": [(-1, 1100, "Connectivity lost", None)]})
    health = _connected(fake, loop).health()
    assert (health.ok, health.state) == (False, "CONNECTIVITY_LOST")
    assert "probe" in fake.calls


def test_health_sees_a_lost_and_restored_link_during_the_probe(loop):
    events = [(-1, 1100, "Connectivity lost", None), (-1, 1101, "restored, data lost", None)]
    fake = FakeIB(emit_during={"probe": events})
    health = _connected(fake, loop).health()
    assert (health.ok, health.state) == (False, "CONNECTIVITY_LOST")


def test_health_when_not_connected(loop):
    fake = FakeIB()
    adapter = _connected(fake, loop)
    fake.connected = False
    assert adapter.health().state == "NOT_CONNECTED"
    assert broker.IbkrBroker("127.0.0.1", 7497, loop=loop).health().state == "NOT_CONNECTED"


# --- positions: fresh every call, filtered, cash is TotalCashValue -------------------


def _summary(*extra):
    return [
        account_value("TotalCashValue", "1005459.44"),
        account_value("BuyingPower", "6705922.13"),
        account_value("AvailableFunds", "1004000.00"),
        *extra,
    ]


def test_positions_fresh_each_call(loop):
    # WR-02: the fake caches the summary like the library does, so a second
    # call only asks the gateway again if the adapter makes it do so.
    fake = FakeIB(positions=[position("DUQ634065", "AAPL", 3)], summary=_summary())
    adapter = _connected(fake, loop)
    first = adapter.positions()
    fake._summary = [account_value("TotalCashValue", "4242.0")]
    second = adapter.positions()
    assert fake.calls.count("positions") == 2
    assert fake.calls.count("account_summary") == 2
    assert (first.cash, second.cash) == (1005459.44, 4242.0)


def test_the_library_answers_the_summary_from_its_cache(loop):
    # The behaviour WR-02 rests on, pinned on the real IB object: a request goes
    # out only while wrapper.acctSummary is empty. Should a library update change
    # that, the fake above no longer models it and this test says so.
    ib_async = pytest.importorskip("ib_async")
    ib = ib_async.IB()
    sent = []

    async def no_request():
        sent.append("reqAccountSummary")

    ib.reqAccountSummaryAsync = no_request
    ib.wrapper.acctSummary[("DUQ634065", "TotalCashValue", "EUR")] = account_value(
        "TotalCashValue", "1.0"
    )
    loop.run_until_complete(ib.accountSummaryAsync("DUQ634065"))
    assert sent == []
    ib.wrapper.acctSummary.clear()
    loop.run_until_complete(ib.accountSummaryAsync("DUQ634065"))
    assert sent == ["reqAccountSummary"]


def test_positions_drops_summary_rows_of_an_earlier_call(loop):
    fake = FakeIB(summary=_summary())
    adapter = _connected(fake, loop)
    adapter.positions()
    # The second answer has no cash row; an old cached one must not stand in for it.
    fake._summary = [account_value("BuyingPower", "1.0")]
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.positions()
    assert info.value.state == "SNAPSHOT_INCOMPLETE"


def test_positions_filters_account_and_zero(loop):
    fake = FakeIB(
        positions=[
            position("DUQ634065", "AAPL", 3, avg_cost=187.5),
            position("DUQ634065", "MSFT", 0),
            position("DU0000001", "NVDA", 5),
        ],
        summary=_summary(),
    )
    snapshot = _connected(fake, loop).positions()
    assert snapshot.account == "DUQ634065"
    assert [(p.symbol, p.quantity, p.avg_cost) for p in snapshot.positions] == [
        ("AAPL", 3.0, 187.5)
    ]
    assert snapshot.positions[0].sec_type == "STK"
    assert snapshot.as_of.tzinfo is not None


def test_positions_cash_is_total_cash_value(loop):
    snapshot = _connected(FakeIB(summary=_summary()), loop).positions()
    assert snapshot.cash == 1005459.44
    assert snapshot.cash_currency == "EUR"


@pytest.mark.parametrize(
    "summary",
    [
        [account_value("BuyingPower", "6705922.13")],  # TotalCashValue missing
        _summary(account_value("TotalCashValue", "1.0")),  # TotalCashValue twice
        [account_value("TotalCashValue", "5.0", account="DU0000001")],  # foreign account only
    ],
    ids=["missing", "duplicate", "foreign"],
)
def test_positions_incomplete_summary_is_named(loop, summary):
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(FakeIB(summary=summary), loop).positions()
    assert info.value.state == "SNAPSHOT_INCOMPLETE"


def test_positions_request_timeout(loop):
    fake = FakeIB(positions="hang")
    adapter = _connected(fake, loop)
    started = time.monotonic()
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.positions()
    assert time.monotonic() - started < 1.0
    assert info.value.state == "REQUEST_TIMEOUT"


@pytest.mark.parametrize("where", ["positions", "account_summary"])
@pytest.mark.parametrize(
    ("codes", "state"),
    [
        ((1100,), "CONNECTIVITY_LOST"),
        ((1100, 1102), "CONNECTIVITY_LOST"),  # lost and restored inside the window
        ((2110,), "SERVER_LINK_BROKEN"),
        ((1300,), "PORT_CHANGED"),
    ],
    ids=["1100", "1100-1102", "2110", "1300"],
)
def test_positions_discards_a_snapshot_with_a_link_event_inside(loop, where, codes, state):
    # Fail-closed (CR-01): the answers are well formed, so only the link event
    # inside the read window can tell that they came from the gateway's local state.
    events = [(-1, code, "link event", None) for code in codes]
    fake = FakeIB(
        positions=[position("DUQ634065", "AAPL", 3)],
        summary=_summary(),
        emit_during={where: events},
    )
    adapter = _connected(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.positions()
    assert info.value.state == state
    assert info.value.code == codes[0]
    assert "snapshot discarded" in info.value.detail


def test_positions_refuses_to_read_while_a_link_is_open(loop):
    fake = FakeIB(summary=_summary())
    adapter = _connected(fake, loop)
    fake.errorEvent.emit(-1, 1100, "Connectivity lost", None)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.positions()
    assert info.value.state == "CONNECTIVITY_LOST"
    assert "positions" not in fake.calls


class _LateLinkLoss(FakeIB):
    """Answers the summary, and the gateway's 1100 lands on the socket just after."""

    async def accountSummaryAsync(self, account=""):
        rows = await super().accountSummaryAsync(account)
        asyncio.get_running_loop().call_later(
            0.01, self.errorEvent.emit, -1, 1100, "Connectivity lost", None
        )
        return rows


def test_positions_settles_the_socket_before_it_trusts_the_snapshot(loop):
    fake = _LateLinkLoss(summary=_summary())
    adapter = _connected(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.positions()
    assert info.value.state == "CONNECTIVITY_LOST"


def test_positions_when_not_connected(loop):
    with pytest.raises(broker.GatewayUnavailable) as info:
        broker.IbkrBroker("127.0.0.1", 7497, loop=loop).positions()
    assert (info.value.state, info.value.code) == ("NOT_CONNECTED", 504)


def test_context_manager_disconnects(loop):
    fake = FakeIB()
    with _broker(fake, loop) as adapter:
        assert isinstance(adapter, broker.IbkrBroker)
    assert "disconnect" in fake.calls
    assert not loop.is_closed()
