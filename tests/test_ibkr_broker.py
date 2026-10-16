"""The IBKR adapter: write barrier, paper guard, named states, liveness, fresh reads.

Every test runs against FakeIB. A real connect is blocked in this module, because
the suite-wide network block does not stop asyncio loopback on Windows and the
real paper gateway listens on this machine.
"""

import asyncio
import inspect
import logging
import re
import time
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from tests import ibkr_fakes
from tests.ibkr_fakes import (
    FakeIB,
    account_value,
    contract_detail,
    make_handles,
    position,
    stk_contract,
)

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


def test_forbidden_call_check_sees_an_ib_level_write():
    # Negative control for the FORBIDDEN_CALLS assertions (WR-05): a write on the
    # IB object lands in ``calls`` even though the fake raises.
    fake = FakeIB()
    for name in ("whatIfOrder", "placeOrder"):
        with pytest.raises(AssertionError):
            getattr(fake, name)()
    assert [call for call in fake.calls if call in FORBIDDEN_CALLS] == [
        "whatIfOrder",
        "placeOrder",
    ]


class _WritesDuringConnect(FakeIB):
    async def connectAsync(self, *args, **kwargs):
        await super().connectAsync(*args, **kwargs)
        self.client.placeOrder(1, None, None)


def test_forbidden_call_check_sees_a_client_write_without_the_barrier(loop, monkeypatch):
    # Without the barrier the client recorder runs, and the check over ``calls``
    # trips: proof that the assertion in the guard tests can fail.
    monkeypatch.setattr(broker, "_arm_write_barrier", lambda client: None)
    fake = _WritesDuringConnect()
    _connected(fake, loop)
    assert any(call in fake.calls for call in FORBIDDEN_CALLS)


def test_client_write_during_connect_is_refused_with_the_barrier(loop):
    fake = _WritesDuringConnect()
    with pytest.raises(broker.ReadOnlyViolation):
        _broker(fake, loop).connect()
    assert not any(call in fake.calls for call in FORBIDDEN_CALLS)
    assert "disconnect" in fake.calls


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
WRITE_MESSAGE_IDS = (4, 19, 21, 58)


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


def test_place_order_refused_without_whatif_on_the_wire():
    ib_async = pytest.importorskip("ib_async")
    client = ib_async.IB().client
    broker._arm_write_barrier(client)
    with pytest.raises(broker.ReadOnlyViolation, match="message 3"):
        client.send(3, 1, 42)
    with pytest.raises(broker.ReadOnlyViolation, match="message 3"):
        client.sendMsg("3\0" + "1\0")
    with pytest.raises(broker.ReadOnlyViolation, match="message 3"):
        client.send(3)


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


def test_write_barrier_lets_contract_details_and_market_data_type_through():
    # A1: the head ids of reqContractDetails (9) and reqMarketDataType (59) pass.
    sent = []
    client = SimpleNamespace(send=lambda *f, **k: sent.append(f), sendMsg=lambda *a, **k: None)
    broker._arm_write_barrier(client)
    client.send(9, 8, 0)
    client.send(59, 1, 3)
    assert [f[0] for f in sent] == [9, 59]


def test_contract_details_and_market_data_type_heads_match_the_installed_library():
    ib_async = pytest.importorskip("ib_async")
    for name, head in (("reqContractDetails", 9), ("reqMarketDataType", 59)):
        source = inspect.getsource(getattr(ib_async.client.Client, name))
        assert re.search(rf"(?:send\(|\[)\s*{head}", source), name
        assert head not in broker._WRITE_MESSAGE_IDS
    assert frozenset({3, 4, 19, 21, 58}) == broker._WRITE_MESSAGE_IDS


# --- delayed market data type ---------------------------------------------------------


def test_market_data_type_is_set_once_after_the_guard(loop):
    fake = FakeIB()
    _connected(fake, loop)
    assert fake.calls.count("reqMarketDataType(3)") == 1
    assert fake.calls.index("reqMarketDataType(3)") > fake.calls.index("connect")


def test_market_data_type_is_not_sent_on_a_guard_violation(loop):
    fake = FakeIB(accounts=("DU999",))
    with pytest.raises(broker.AccountGuardViolation):
        _broker(fake, loop).connect()
    assert not any(c.startswith("reqMarketDataType") for c in fake.calls)


# --- paper guard -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "accounts",
    [
        ["DU0000001"],  # foreign account
        ["DUQ634065", "DU0000001"],  # superset: not exactly the paper account
        [],  # empty
        # Pin the exact list comparison (WR-05): a set comparison, a case fold,
        # a strip or a prefix match would each let one of these through.
        ["DUQ634065", "DUQ634065"],
        ["duq634065"],
        [" DUQ634065"],
        ["DUQ634065 "],
        ["DUQ6340650"],
        ["DUQ63406"],
    ],
    ids=[
        "foreign",
        "superset",
        "empty",
        "duplicate",
        "lower",
        "lead-space",
        "trail-space",
        "longer",
        "prefix",
    ],
)
def test_guard_rejects_anything_but_the_paper_account(loop, accounts):
    fake = FakeIB(accounts=accounts)
    with pytest.raises(broker.AccountGuardViolation) as info:
        _broker(fake, loop).connect()
    assert info.value.accounts_seen == accounts
    assert "disconnect" in fake.calls
    assert not any(call in fake.calls for call in FORBIDDEN_CALLS)


def test_error_while_reading_the_accounts_closes_the_session(loop):
    class Boom(FakeIB):
        def managedAccounts(self):
            raise ValueError("unparseable managedAccounts")

    fake = Boom()
    with pytest.raises(ValueError):
        _broker(fake, loop).connect()
    assert "disconnect" in fake.calls


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


def test_hanging_connect_ends_at_the_outer_bound(loop):
    # WR-04 / REQ-IBKR-62: a peer that never answers, and a library that ignores
    # its own timeout, still end in the named state, bounded by timeout + grace.
    fake = FakeIB(refuse="hang")
    adapter = broker.IbkrBroker(
        "127.0.0.1", 7497, ib_factory=make_handles(fake), loop=loop, connect_grace=0.05, **FAST
    )
    started = time.monotonic()
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.connect()
    assert time.monotonic() - started < 1.0
    assert (info.value.state, info.value.code) == ("CONNECT_TIMEOUT", None)
    assert "within 0.1s" in info.value.detail
    assert "disconnect" in fake.calls


def test_connect_grace_is_a_named_constant():
    assert broker.CONNECT_GRACE_S == 5.0
    assert broker.CONNECT_TIMEOUT_S + broker.CONNECT_GRACE_S == 15.0


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
        (10167, "MARKET_DATA_DELAYED"),
        (200, "CONTRACT_NOT_FOUND"),
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


@pytest.mark.parametrize(
    ("code", "label"),
    [
        (10089, "MARKET_DATA_NOT_SUBSCRIBED"),
        (10090, "MARKET_DATA_NOT_SUBSCRIBED"),
        (10167, "MARKET_DATA_DELAYED"),
    ],
)
def test_market_data_codes_log_at_info(loop, caplog, code, label):
    adapter = _broker(FakeIB(), loop)
    with caplog.at_level(logging.INFO, logger="ibkr_broker"):
        adapter._on_error(-1, code, "delayed market data", None)
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert f"ibkr-state={label} code={code}" in record.getMessage()
    assert not adapter.link_lost
    assert not adapter.server_link_broken
    assert not adapter.port_changed


def test_halt_code_is_mapped_for_the_preview():
    assert broker.STATE_BY_CODE[154] == "HALTED"


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
    fake._summary = [
        account_value("TotalCashValue", "4242.0"),
        account_value("AvailableFunds", "4000.0"),
    ]
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


# --- contract resolution: search_contract and contract_details ------------------------


@dataclass(frozen=True)
class Spec:
    symbol: str = "AAPL"
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: str = ""


def test_search_contract_one_match(loop):
    fake = FakeIB(qualify={"AAPL": [stk_contract("AAPL", 265598)]})
    (info,) = _connected(fake, loop).search_contract(Spec())
    assert isinstance(info, broker.ContractInfo)
    assert (info.con_id, info.symbol, info.sec_type) == (265598, "AAPL", "STK")
    assert (info.primary_exchange, info.currency) == ("NASDAQ", "USD")
    assert (info.local_symbol, info.trading_class) == ("AAPL", "NMS")
    assert info.valid_exchanges == info.order_types == info.time_zone_id == ""
    assert info.liquid_hours == info.trading_hours == ""


def test_search_contract_no_match(loop):
    assert _connected(FakeIB(), loop).search_contract(Spec("ZZZZ")) == ()


def test_search_contract_many_matches(loop):
    hits = [stk_contract("ES", 1000 + i) for i in range(21)]
    result = _connected(FakeIB(qualify={"ES": hits}), loop).search_contract(Spec("ES"))
    assert len(result) == 21
    assert {r.con_id for r in result} == {1000 + i for i in range(21)}


class _QualifyWithNone(FakeIB):
    async def qualifyContractsAsync(self, *contracts, returnAll=False):
        self.calls.append("qualify")
        return [[stk_contract("AAPL", 265598), None]]


def test_search_contract_refuses_incomplete_candidate_list(loop):
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(_QualifyWithNone(), loop).search_contract(Spec())
    assert info.value.state == "REQUEST_FAILED"


def test_search_contract_builds_a_fresh_contract_per_call(loop):
    fake = FakeIB(qualify={"AAPL": [stk_contract("AAPL", 265598)]})
    adapter = _connected(fake, loop)
    spec = Spec(primary_exchange="NASDAQ")
    adapter.search_contract(spec)
    adapter.search_contract(spec)
    assert spec == Spec(primary_exchange="NASDAQ")
    assert len(fake.qualify_calls) == 2
    for sent, return_all in fake.qualify_calls:
        assert return_all is True
        assert sent.conId == 0
        assert (sent.symbol, sent.secType, sent.exchange) == ("AAPL", "STK", "SMART")
        assert (sent.currency, sent.primaryExchange) == ("USD", "NASDAQ")


def test_contract_details_maps_session_fields(loop):
    contract = stk_contract("AAPL", 265598)
    detail = contract_detail(contract, liquid_hours="20261012:0930-1600", long_name="APPLE INC")
    fake = FakeIB(details={265598: [detail]})
    (info,) = _connected(fake, loop).contract_details(265598, "SMART")
    assert info.con_id == 265598
    assert info.valid_exchanges == "SMART,NASDAQ,ARCA"
    assert info.order_types == "ACTIVETIM,LMT,MKT,STP"
    assert info.time_zone_id == "US/Eastern"
    assert info.liquid_hours == "20261012:0930-1600"
    assert info.long_name == "APPLE INC"
    (sent,) = fake.details_calls
    assert (sent.conId, sent.exchange) == (265598, "SMART")


def test_contract_details_unknown_con_id(loop):
    assert _connected(FakeIB(), loop).contract_details(1, "SMART") == ()


def test_resolution_request_error_code_is_not_reported_as_empty_result(loop):
    detail = contract_detail(stk_contract("AAPL", 265598), liquid_hours="20261012:0930-1600")
    fake = FakeIB(
        details={265598: [detail]},
        emit_during={"contract_details": [(17, 162, "pacing violation", None)]},
    )
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(fake, loop).contract_details(265598, "SMART")
    assert (info.value.state, info.value.code) == ("REQUEST_FAILED", 162)


@pytest.mark.parametrize("code", [2103, 2105, 2107, 2108])
def test_system_notice_without_request_id_does_not_fail_the_read(loop, code):
    # Farm notices arrive with reqId -1 at any time; they are not this read's answer.
    detail = contract_detail(stk_contract("AAPL", 265598), liquid_hours="20261012:0930-1600")
    fake = FakeIB(
        details={265598: [detail]},
        emit_during={"contract_details": [(-1, code, "farm notice", None)]},
    )
    result = _connected(fake, loop).contract_details(265598, "SMART")
    assert [r.con_id for r in result] == [265598]


def test_contract_not_found_code_200_stays_an_empty_result(loop):
    fake = FakeIB(emit_during={"contract_details": [(17, 200, "No security definition", None)]})
    assert _connected(fake, loop).contract_details(265598, "SMART") == ()


@pytest.mark.parametrize(
    ("kwargs", "call"),
    [
        ({"qualify": "hang"}, lambda a: a.search_contract(Spec())),
        ({"details": "hang"}, lambda a: a.contract_details(265598, "SMART")),
    ],
    ids=["search", "details"],
)
def test_resolution_request_timeout(loop, kwargs, call):
    adapter = _connected(FakeIB(**kwargs), loop)
    started = time.monotonic()
    with pytest.raises(broker.GatewayUnavailable) as info:
        call(adapter)
    assert time.monotonic() - started < 1.0
    assert info.value.state == "REQUEST_TIMEOUT"


_READS = [
    ("qualify", lambda a: a.search_contract(Spec())),
    ("contract_details", lambda a: a.contract_details(265598, "SMART")),
]


@pytest.mark.parametrize(("where", "call"), _READS, ids=["search", "details"])
def test_resolution_refuses_to_read_while_a_link_is_open(loop, where, call):
    fake = FakeIB()
    adapter = _connected(fake, loop)
    adapter._on_error(-1, 1100, "lost", None)
    with pytest.raises(broker.GatewayUnavailable) as info:
        call(adapter)
    assert info.value.state == "CONNECTIVITY_LOST"
    assert where not in fake.calls


@pytest.mark.parametrize(("where", "call"), _READS, ids=["search", "details"])
def test_resolution_discards_an_answer_with_a_link_event_inside(loop, where, call):
    fake = FakeIB(
        qualify={"AAPL": [stk_contract("AAPL", 265598)]},
        details={265598: [contract_detail(stk_contract("AAPL", 265598))]},
        emit_during={where: [(-1, 1100, "lost", None)]},
    )
    adapter = _connected(fake, loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        call(adapter)
    assert (info.value.state, info.value.code) == ("CONNECTIVITY_LOST", 1100)


@pytest.mark.parametrize(("where", "call"), _READS, ids=["search", "details"])
def test_resolution_when_not_connected(loop, where, call):
    adapter = broker.IbkrBroker("127.0.0.1", 7497, loop=loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        call(adapter)
    assert (info.value.state, info.value.code) == ("NOT_CONNECTED", 504)


def test_context_manager_disconnects(loop):
    fake = FakeIB()
    with _broker(fake, loop) as adapter:
        assert isinstance(adapter, broker.IbkrBroker)
    assert "disconnect" in fake.calls
    assert not loop.is_closed()


# --- own event loop: closed, unset, and drained (WR-06) -------------------------------


class _OwnLoop:
    """A loop the adapter believes it created; runs on the session loop.

    A real new loop opens a loopback socket pair on Windows, which the
    suite-wide network block refuses inside a test.
    """

    def __init__(self, inner):
        self._inner = inner
        self.closed = False

    def run_until_complete(self, awaitable):
        assert not self.closed, "run on a closed loop"
        return self._inner.run_until_complete(awaitable)

    def call_soon(self, *args):
        return self._inner.call_soon(*args)

    def is_running(self):
        return self._inner.is_running()

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class _LoopRecorder:
    """Records the loops the adapter creates and sets, without touching the real policy."""

    def __init__(self, monkeypatch, inner):
        self.created = []
        self.set_calls = []

        def new_event_loop():
            created = _OwnLoop(inner)
            self.created.append(created)
            return created

        monkeypatch.setattr(broker.asyncio, "new_event_loop", new_event_loop)
        monkeypatch.setattr(broker.asyncio, "set_event_loop", self.set_calls.append)


class _ClosesLikeATransport(FakeIB):
    """disconnect() schedules connection_lost via call_soon, as transport.close() does."""

    adapter_loop = None

    def disconnect(self):
        super().disconnect()
        self.adapter_loop.call_soon(self.calls.append, "connection_lost")


def test_own_loop_is_closed_and_unset_after_the_session(monkeypatch, loop):
    loops = _LoopRecorder(monkeypatch, loop)
    fake = FakeIB()
    adapter = broker.IbkrBroker("127.0.0.1", 7497, ib_factory=make_handles(fake), **FAST)
    with adapter:
        pass
    (own,) = loops.created
    assert own.is_closed()
    assert loops.set_calls == [own, None]


def test_own_loop_is_closed_when_the_library_is_missing(monkeypatch, loop):
    loops = _LoopRecorder(monkeypatch, loop)

    def no_library():
        raise ModuleNotFoundError("No module named the IBKR client library")

    adapter = broker.IbkrBroker("127.0.0.1", 7497, ib_factory=no_library, **FAST)
    with pytest.raises(ModuleNotFoundError):
        adapter.connect()
    (own,) = loops.created
    assert own.is_closed()
    assert loops.set_calls == [own, None]


def test_disconnect_lets_connection_lost_run_before_the_loop_closes(monkeypatch, loop):
    loops = _LoopRecorder(monkeypatch, loop)
    fake = _ClosesLikeATransport()
    adapter = broker.IbkrBroker("127.0.0.1", 7497, ib_factory=make_handles(fake), **FAST)
    adapter.connect()
    fake.adapter_loop = loops.created[0]
    adapter.__exit__(None, None, None)
    assert fake.calls[-2:] == ["disconnect", "connection_lost"]
    assert loops.created[0].is_closed()


# --- whatIf passes the barrier, a real order does not (D-13) ----------------------------


def _fake_client_barrier(loop):
    fake = FakeIB()
    _connected(fake, loop)
    return fake


def test_whatif_barrier_place_order_refused_without_whatif(loop):
    fake = _fake_client_barrier(loop)
    contract = ibkr_fakes.FakeContract(conId=265598, secType="STK")
    with pytest.raises(broker.ReadOnlyViolation):
        fake.client.placeOrder(7, contract, ibkr_fakes.FakeOrder(whatIf=False))
    assert "placeOrder" not in fake.calls
    assert "placeOrder(whatIf)" not in fake.calls


def test_whatif_barrier_place_order_passes_a_stock_preview(loop):
    fake = _fake_client_barrier(loop)
    contract = ibkr_fakes.FakeContract(conId=265598, secType="STK")
    fake.client.placeOrder(7, contract, ibkr_fakes.FakeOrder(whatIf=True))
    assert fake.calls.count("placeOrder(whatIf)") == 1
    assert "placeOrder" not in fake.calls


def test_whatif_barrier_place_order_refused_for_a_non_stock_preview(loop):
    fake = _fake_client_barrier(loop)
    contract = ibkr_fakes.FakeContract(conId=1, secType="OPT")
    with pytest.raises(broker.ReadOnlyViolation):
        fake.client.placeOrder(7, contract, ibkr_fakes.FakeOrder(whatIf=True))
    assert "placeOrder(whatIf)" not in fake.calls


@pytest.mark.parametrize("name", ("cancelOrder", "reqGlobalCancel", "exerciseOptions"))
def test_whatif_barrier_other_write_calls_stay_refused(loop, name):
    fake = _fake_client_barrier(loop)
    with pytest.raises(broker.ReadOnlyViolation):
        getattr(fake.client, name)()


def _wire_client(loop, monkeypatch):
    """The real Client class with a stub connection that records the bytes sent.

    ``sendMsg`` asks the library for its event loop, which would open a socketpair
    and trip the network block; the session loop is handed in instead.
    """
    ib_async = pytest.importorskip("ib_async")
    monkeypatch.setattr("ib_async.client.getLoop", lambda: loop)
    client = ib_async.client.Client(ib_async.IB().wrapper)
    sent = []
    client.conn = SimpleNamespace(sendMsg=sent.append)
    client.connState = client.CONNECTED
    client._serverVersion = 178
    return ib_async, client, sent


def _stock_and_order(ib_async, what_if):
    contract = ib_async.Contract(
        conId=265598, symbol="AAPL", secType="STK", exchange="SMART", currency="USD"
    )
    order = ib_async.Order(action="BUY", totalQuantity=2, orderType="MKT", tif="DAY", whatIf=what_if)
    return contract, order


def _recorded_message(loop, monkeypatch, what_if=True):
    """The serialized message of the real client for a market order, barrier off."""
    ib_async, client, sent = _wire_client(loop, monkeypatch)
    contract, order = _stock_and_order(ib_async, what_if)
    client.placeOrder(1, contract, order)
    assert len(sent) == 1
    return sent[0][4:].decode()  # the library prefixes a 4-byte length


def test_whatif_barrier_real_client_passes_whatif(loop, monkeypatch):
    ib_async, client, sent = _wire_client(loop, monkeypatch)
    broker._arm_write_barrier(client)
    contract, order = _stock_and_order(ib_async, True)
    client.placeOrder(1, contract, order)
    assert len(sent) == 1
    parts = sent[0][4:].decode().split("\0")
    assert parts[0] == "3"
    assert parts[4] == "STK"
    assert parts[16] == "BUY" and parts[21] == "DAY"
    assert parts[84] == "1"  # whatIf, after the 12-field contract expansion


def test_whatif_barrier_real_client_refuses_real_order(loop, monkeypatch):
    ib_async, client, sent = _wire_client(loop, monkeypatch)
    broker._arm_write_barrier(client)
    contract, order = _stock_and_order(ib_async, False)
    with pytest.raises(broker.ReadOnlyViolation):
        client.placeOrder(1, contract, order)
    assert sent == []


def test_whatif_barrier_real_client_refuses_real_order_on_the_field_level(loop, monkeypatch):
    # Bypass the named call: the field-level wrapper alone must stop it.
    ib_async, client, sent = _wire_client(loop, monkeypatch)
    broker._arm_write_barrier(client)
    contract, order = _stock_and_order(ib_async, False)
    del client.placeOrder  # back to the class method, which calls the guarded send
    with pytest.raises(broker.ReadOnlyViolation):
        client.placeOrder(1, contract, order)
    assert sent == []


def _message_client(sent):
    client = SimpleNamespace(send=lambda *f, **k: None, sendMsg=lambda m, *a, **k: sent.append(m))
    broker._arm_write_barrier(client)
    return client


def test_whatif_barrier_message_level_passes_the_recorded_whatif_string(loop, monkeypatch):
    msg = _recorded_message(loop, monkeypatch, True)
    sent = []
    _message_client(sent).sendMsg(msg)
    assert sent == [msg]


def test_whatif_barrier_message_level_refuses_whatif_zero_and_other_sec_types(loop, monkeypatch):
    parts = _recorded_message(loop, monkeypatch, True).split("\0")
    assert parts[84] == "1"
    sent = []
    client = _message_client(sent)
    off = list(parts)
    off[84] = "0"
    with pytest.raises(broker.ReadOnlyViolation):
        client.sendMsg("\0".join(off))
    opt = list(parts)
    opt[4] = "OPT"
    with pytest.raises(broker.ReadOnlyViolation):
        client.sendMsg("\0".join(opt))
    assert sent == []


def test_whatif_barrier_message_level_refuses_a_shifted_layout_and_a_truncated_string(loop, monkeypatch):
    parts = _recorded_message(loop, monkeypatch, True).split("\0")
    sent = []
    client = _message_client(sent)
    algo = list(parts)
    algo[82] = "Twap"  # an algo order moves the whatIf field
    with pytest.raises(broker.ReadOnlyViolation):
        client.sendMsg("\0".join(algo))
    with pytest.raises(broker.ReadOnlyViolation):
        client.sendMsg("3\0" + "1\0")
    assert sent == []


# --- phase 4: conId, AvailableFunds, open orders of every client ------------------------


def test_positions_carry_the_con_id(loop):
    fake = FakeIB(positions=[position("DUQ634065", "AAPL", 2, conId=265598)])
    (held,) = _connected(fake, loop).positions().positions
    assert held.con_id == 265598


def test_positions_available_funds_comes_from_one_summary_row(loop):
    summary = [
        account_value("TotalCashValue", "1005459.44"),
        account_value("AvailableFunds", "1000.0"),
    ]
    snapshot = _connected(FakeIB(summary=summary), loop).positions()
    assert snapshot.available_funds == 1000.0
    assert snapshot.available_funds_currency == "EUR"


@pytest.mark.parametrize(
    "summary",
    [
        [account_value("TotalCashValue", "1.0")],
        [
            account_value("TotalCashValue", "1.0"),
            account_value("AvailableFunds", "1.0"),
            account_value("AvailableFunds", "2.0"),
        ],
    ],
    ids=["missing", "duplicate"],
)
def test_positions_available_funds_row_must_be_unique(loop, summary):
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(FakeIB(summary=summary), loop).positions()
    assert info.value.state == "SNAPSHOT_INCOMPLETE"
    assert "AvailableFunds" in info.value.detail


def test_open_orders_reads_every_client_and_filters_con_id_and_status(loop):
    trades = [
        ibkr_fakes.open_trade(265598, status="Submitted", client_id=0),
        ibkr_fakes.open_trade(265598, status="Filled"),
        ibkr_fakes.open_trade(272093, status="PreSubmitted"),
    ]
    fake = FakeIB(open_orders=trades)
    result = _connected(fake, loop).open_orders(265598)
    assert result == (
        broker.OpenOrder(
            con_id=265598,
            action="BUY",
            quantity=1.0,
            order_type="LMT",
            status="Submitted",
            client_id=0,
        ),
    )
    assert "open_orders" in fake.calls
    assert "placeOrder" not in fake.calls
    assert not any(call in fake.calls for call in FORBIDDEN_CALLS)


def test_open_orders_request_timeout(loop):
    adapter = _connected(FakeIB(open_orders="hang"), loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.open_orders(265598)
    assert info.value.state == "REQUEST_TIMEOUT"


def test_open_orders_discards_an_answer_with_a_link_event_inside(loop):
    fake = FakeIB(
        open_orders=[ibkr_fakes.open_trade(265598)],
        emit_during={"open_orders": [(-1, 1100, "lost", None)]},
    )
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(fake, loop).open_orders(265598)
    assert info.value.state == "CONNECTIVITY_LOST"


def test_open_orders_when_not_connected(loop):
    adapter = broker.IbkrBroker("127.0.0.1", 7497, loop=loop)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.open_orders(265598)
    assert info.value.state == "NOT_CONNECTED"


PREVIEW_ARGS = {
    "con_id": 265598,
    "symbol": "AAPL",
    "sec_type": "STK",
    "currency": "USD",
    "primary_exchange": "NASDAQ",
    "action": "BUY",
    "quantity": 2,
}


def _preview(fake, loop, **overrides):
    return _connected(fake, loop).preview_order(**{**PREVIEW_ARGS, **overrides})


def _state(init="997.14"):
    return ibkr_fakes.order_state(init=init, maint="997.14")


def test_preview_returns_a_fully_read_result(loop):
    fake = FakeIB(whatif=_state())
    result = _preview(fake, loop)
    assert result == broker.PreviewResult(
        state="OK",
        init_margin_change=997.14,
        maint_margin_change=997.14,
        commission=1.00003,
        commission_currency="USD",
        warning_text="",
        errors=(),
        effective_tif="DAY",
        sent_tif="DAY",
    )


def test_preview_sends_one_whatif_market_order_with_explicit_tif_and_account(loop):
    fake = FakeIB(whatif=_state())
    _preview(fake, loop)
    ((contract, order),) = fake.whatif_calls
    assert (order.orderType, order.tif, order.account) == ("MKT", "DAY", "DUQ634065")
    assert (order.action, order.totalQuantity, order.whatIf) == ("BUY", 2, True)
    assert contract.conId == 265598
    assert (contract.exchange, contract.secType, contract.currency) == ("SMART", "STK", "USD")
    assert contract.primaryExchange == "NASDAQ"
    assert fake.calls.count("placeOrder(whatIf)") == 1
    assert "placeOrder" not in fake.calls
    assert not any(c in fake.calls for c in ("whatIfOrder", "placeOrder", "reqMktData"))


def test_preview_empty_answer_has_no_numbers(loop):
    result = _preview(FakeIB(whatif=[]), loop)
    assert result.state == "EMPTY"
    assert (result.init_margin_change, result.maint_margin_change, result.commission) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "state",
    [
        ibkr_fakes.order_state(init="1.7976931348623157E308"),
        ibkr_fakes.order_state(init="abc"),
        ibkr_fakes.order_state(init=float("nan")),
    ],
    ids=["unset", "text", "nan"],
)
def test_preview_unset_margin_is_none(loop, state):
    result = _preview(FakeIB(whatif=state), loop)
    assert result.init_margin_change is None


def test_preview_unset_commission_is_none(loop):
    state = ibkr_fakes.order_state(commission=float("nan"))
    assert _preview(FakeIB(whatif=state), loop).commission is None


def test_preview_halted_code_154_is_its_own_state(loop):
    text = "Orders cannot be transmitted for a halted security."
    fake = FakeIB(whatif=[], emit_during={"whatif": [(17, 154, text, None)]})
    result = _preview(fake, loop)
    assert result.state == "HALTED"
    assert (154, text) in result.errors


def test_preview_tif_overridden_code_10349_is_its_own_state(loop):
    fake = FakeIB(whatif=[], emit_during={"whatif": [(17, 10349, "TIF set to DAY", None)]})
    assert _preview(fake, loop).state == "TIF_OVERRIDDEN"


@pytest.mark.parametrize("req_id", [-1, 17])
def test_preview_read_only_api_321_on_timeout(loop, req_id):
    fake = FakeIB(whatif="hang", emit_during={"whatif": [(req_id, 321, "read-only", None)]})
    assert _preview(fake, loop).state == "READ_ONLY_API"


def test_preview_timeout_without_321_is_unavailable(loop):
    with pytest.raises(broker.GatewayUnavailable) as info:
        _preview(FakeIB(whatif="hang"), loop)
    assert info.value.state == "REQUEST_TIMEOUT"


def test_preview_request_error_text_is_kept(loop):
    text = "Order rejected - reason: x"
    fake = FakeIB(whatif=[], emit_during={"whatif": [(17, 201, text, None)]})
    result = _preview(fake, loop)
    assert result.state == "EMPTY"
    assert result.errors == ((201, text),)


def test_preview_discards_an_answer_with_a_link_event_inside(loop):
    fake = FakeIB(whatif=_state(), emit_during={"whatif": [(-1, 1100, "lost", None)]})
    with pytest.raises(broker.GatewayUnavailable) as info:
        _preview(fake, loop)
    assert info.value.state == "CONNECTIVITY_LOST"


def test_preview_sends_nothing_while_a_link_is_open(loop):
    fake = FakeIB(whatif=_state())
    adapter = _connected(fake, loop)
    adapter._on_error(-1, 1100, "lost", None)
    with pytest.raises(broker.GatewayUnavailable) as info:
        adapter.preview_order(**PREVIEW_ARGS)
    assert info.value.state == "CONNECTIVITY_LOST"
    assert fake.whatif_calls == []


def test_preview_effective_tif_comes_from_the_echo(loop):
    assert _preview(FakeIB(whatif=_state(), whatif_echo_tif="GTC"), loop).effective_tif == "GTC"
    assert _preview(FakeIB(whatif=_state(), whatif_echo_tif=None), loop).effective_tif is None


@pytest.mark.parametrize("hang", [False, True])
def test_preview_restores_the_wrapper_open_order(loop, hang):
    fake = FakeIB(whatif="hang" if hang else _state())
    original = fake.wrapper.openOrder
    adapter = _connected(fake, loop)
    if hang:
        with pytest.raises(broker.GatewayUnavailable):
            adapter.preview_order(**PREVIEW_ARGS)
    else:
        adapter.preview_order(**PREVIEW_ARGS)
    assert fake.wrapper.openOrder == original


@pytest.mark.parametrize(
    "overrides",
    [{"action": "SHORT"}, {"quantity": 0}, {"quantity": 1.5}, {"quantity": True}],
    ids=["action", "zero", "fraction", "bool"],
)
def test_preview_refuses_a_bad_request_before_the_gateway(loop, overrides):
    fake = FakeIB(whatif=_state())
    with pytest.raises(ValueError):
        _preview(fake, loop, **overrides)
    assert fake.whatif_calls == []


def test_preview_codes_are_mapped_and_not_generic_errors():
    assert broker.STATE_BY_CODE[154] == "HALTED"
    assert broker.STATE_BY_CODE[10349] == "TIF_OVERRIDDEN"
    adapter = broker.IbkrBroker("127.0.0.1", 7497)
    adapter._on_error(17, 154, "halted", None)
    adapter._on_error(17, 10349, "tif", None)
    assert adapter._request_error_since(0) is None


def test_the_fake_forbids_market_data():
    fake = FakeIB()
    for name in ("reqMktData", "reqTickers"):
        with pytest.raises(AssertionError):
            getattr(fake, name)()
        assert name in fake.calls


# --- fail-closed for system events: an unexpected reqId=-1 code voids a read window ----

#: Real IBKR system notices that report a broken state but are no link codes. Before
#: this fix the window only knew LINK_CODES, so these passed silently (fail-open).
_BROKEN_SYSTEM_EVENTS = [
    (2103, "FARM_DOWN", "Market data farm connection is broken"),
    (2105, "FARM_DOWN", "HMDS data farm connection is broken"),
    (507, "SOCKET_EOF", "Bad message length"),
]
_BROKEN_IDS = [str(code) for code, _, _ in _BROKEN_SYSTEM_EVENTS]


@pytest.mark.parametrize(("code", "state", "text"), _BROKEN_SYSTEM_EVENTS, ids=_BROKEN_IDS)
def test_health_voids_a_probe_with_an_unexpected_system_event(loop, code, state, text):
    # The probe answers well formed (assumption A4): only the event in its window shows it.
    fake = FakeIB(emit_during={"probe": [(-1, code, text, None)]})
    health = _connected(fake, loop).health()
    assert (health.ok, health.state) == (False, state)


@pytest.mark.parametrize(("code", "state", "text"), _BROKEN_SYSTEM_EVENTS, ids=_BROKEN_IDS)
def test_positions_discards_a_snapshot_with_an_unexpected_system_event(loop, code, state, text):
    fake = FakeIB(
        positions=[position("DUQ634065", "AAPL", 3)],
        summary=_summary(),
        emit_during={"account_summary": [(-1, code, text, None)]},
    )
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(fake, loop).positions()
    assert (info.value.state, info.value.code) == (state, code)


def test_resolution_read_is_voided_by_an_unexpected_system_event(loop):
    # The resolution path persists what it reads (contracts.json), so a read taken
    # while the farm is down must not be learned.
    detail = contract_detail(stk_contract("AAPL", 265598), liquid_hours="20261012:0930-1600")
    fake = FakeIB(
        details={265598: [detail]},
        emit_during={"contract_details": [(-1, 2103, "Market data farm connection is broken", None)]},
    )
    with pytest.raises(broker.GatewayUnavailable) as info:
        _connected(fake, loop).contract_details(265598, "SMART")
    assert (info.value.state, info.value.code) == ("FARM_DOWN", 2103)


def test_a_never_measured_system_code_voids_the_window(loop):
    # Not in STATE_BY_CODE: fail-closed by construction, no measurement needed (REQ-IBKR-67).
    fake = FakeIB(emit_during={"probe": [(-1, 2999, "something nobody has seen", None)]})
    health = _connected(fake, loop).health()
    assert (health.ok, health.state) == (False, "UNKNOWN")


def test_window_benign_codes_are_exactly_the_measured_notices():
    # Pinned: a code enters only after it was seen at the real gateway. 2107 was
    # measured 2026-10-12 in the real account run; it is session state, not a fault.
    assert broker.WINDOW_BENIGN_CODES == frozenset(
        {2104, 2106, 2158, 2107, 10089, 10090, 10167}
    )


@pytest.mark.parametrize("code", [2104, 2106, 2158, 2107, 10089, 10090, 10167])
def test_benign_system_notices_do_not_void_a_window(loop, code):
    fake = FakeIB(emit_during={"probe": [(-1, code, "notice", None)]})
    assert _connected(fake, loop).health().ok is True


def test_2107_inside_a_snapshot_keeps_the_snapshot(loop):
    fake = FakeIB(
        positions=[],
        summary=_summary(),
        emit_during={"account_summary": [(-1, 2107, "HMDS data farm connection is inactive", None)]},
    )
    snapshot = _connected(fake, loop).positions()
    assert float(snapshot.cash) == pytest.approx(1005459.44)


def test_request_scoped_codes_are_not_system_events(loop):
    # A 200 answering the search itself carries a request id: the request logic owns
    # it (empty result), it must not turn into a voided window.
    fake = FakeIB(emit_during={"qualify": [(5, 200, "No security definition", None)]})
    assert _connected(fake, loop).search_contract(Spec("ZZZZ")) == ()
