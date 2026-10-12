"""The IBKR adapter: write barrier, paper guard, named states, liveness, fresh reads.

Every test runs against FakeIB. A real connect is blocked in this module, because
the suite-wide network block does not stop asyncio loopback on Windows and the
real paper gateway listens on this machine.
"""

import logging

import pytest

from tests import ibkr_fakes
from tests.ibkr_fakes import FakeIB, make_handles

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
