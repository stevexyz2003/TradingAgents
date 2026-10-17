"""The phase-5 operator probe (``scripts/smoke/ibkr_order_probe.py``), against fakes only.

Nothing here reads the operator's ``.env`` or reaches the gateway: a real connect of the
client library is blocked, every path comes from ``tmp_path`` and the gateway is a
``FakeIB``. The probe must read the order history or send one whatIf, and never
transmit or cancel anything.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from tests import ibkr_fakes

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_PROBE = _ROOT / "scripts" / "smoke" / "ibkr_order_probe.py"
_EXECUTOR = _ROOT / "scripts" / "ibkr_executor.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load("ibkr_order_probe", _PROBE)
executor = _load("ibkr_executor_for_probe_tests", _EXECUTOR)
broker = executor.load_broker_module()
contracts_mod = executor.load_contracts_module()

DEFAULT_ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_ACCOUNT_ID": "DUQ634065",
    "IBKR_TRADING_MODE": "paper",
}

#: Calls that would transmit or cancel an order; none may ever appear.
FORBIDDEN_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "global_cancel")


@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)


@pytest.fixture(autouse=True)
def _local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


@pytest.fixture(autouse=True)
def _close_logging():
    yield
    probe.close_logging()


def _env_file(tmp_path):
    path = tmp_path / ".env"
    lines = [f"{key}={value}" for key, value in DEFAULT_ENV.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _fake_factory(fake, loop):
    def factory(host, port, logger):
        return broker.IbkrBroker(
            host,
            port,
            logger=logger,
            ib_factory=ibkr_fakes.make_handles(fake),
            loop=loop,
            connect_timeout=0.05,
            request_timeout=0.05,
            probe_timeout=0.05,
        )

    return factory


def _write_contracts(tmp_path, tickers=("AAPL",)):
    path = tmp_path / "TradingEngineX" / "ibkr" / "contracts.json"
    table = {
        ticker: contracts_mod.StoredContract(
            contracts_mod.Identity(265598, "NASDAQ", "USD", ticker), "2026-10-01T00:00:00+00:00"
        )
        for ticker in tickers
    }
    contracts_mod.commit_contracts(path, table, ())
    return path


def _run(tmp_path, loop, fake, *args):
    argv = [*args, "--env-file", str(_env_file(tmp_path))]
    return probe.main(argv, broker_factory=_fake_factory(fake, loop))


def _assert_nothing_sent(fake):
    for name in FORBIDDEN_CALLS:
        assert name not in fake.calls


def test_no_action_is_exit_1_and_names_the_choices(tmp_path, capsys):
    code = probe.main(["--env-file", str(_env_file(tmp_path))])
    assert code == 1
    assert "--history or --whatif TICKER" in capsys.readouterr().err


def test_history_prints_the_three_sources_as_json(tmp_path, loop, capsys):
    fake = ibkr_fakes.FakeIB(
        open_orders=[ibkr_fakes.open_trade(265598, order_ref="2026-10-09|AAPL")],
        completed_orders=[
            ibkr_fakes.completed_trade(265598, status="Cancelled", order_ref="2026-10-08|AAPL")
        ],
        executions=[ibkr_fakes.fill(265598, "2026-10-07|AAPL", 1, side="BOT")],
    )
    code = _run(tmp_path, loop, fake, "--history")
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"as_of", "open", "completed", "executions"}
    assert out["open"][0]["order_ref"] == "2026-10-09|AAPL"
    assert out["completed"][0]["status"] == "Cancelled"
    assert out["completed"][0]["filled"] is None
    assert out["executions"][0]["side"] == "BUY"
    for name in ("open_orders", "completed_orders", "executions"):
        assert name in fake.calls
    _assert_nothing_sent(fake)


def test_whatif_puts_the_order_ref_on_the_order_and_prints_the_echo(tmp_path, loop, capsys):
    _write_contracts(tmp_path)
    fake = ibkr_fakes.FakeIB(whatif=ibkr_fakes.order_state())
    code = _run(tmp_path, loop, fake, "--whatif", "AAPL", "--order-ref", "2026-10-09|AAPL")
    assert code == 0
    _contract, order = fake.whatif_calls[-1]
    assert order.orderRef == "2026-10-09|AAPL"
    assert order.action == "BUY"
    assert order.totalQuantity == 1
    out = json.loads(capsys.readouterr().out)
    for key in ("state", "errors", "echo_order_ref", "echo_account", "effective_tif"):
        assert key in out
    assert out["echo_order_ref"] == "2026-10-09|AAPL"
    assert out["echo_account"] == "DUQ634065"
    assert "placeOrder" not in fake.calls
    _assert_nothing_sent(fake)


def test_whatif_for_a_ticker_without_a_stored_contract_is_exit_1(tmp_path, loop, capsys):
    _write_contracts(tmp_path, tickers=("MSFT",))
    fake = ibkr_fakes.FakeIB()
    code = _run(tmp_path, loop, fake, "--whatif", "AAPL")
    assert code == 1
    assert "resolve --init" in capsys.readouterr().err
    assert "whatif" not in fake.calls


@pytest.mark.parametrize("quantity", ["0", "3"])
def test_whatif_quantity_is_one_or_two_only(tmp_path, loop, quantity):
    _write_contracts(tmp_path)
    fake = ibkr_fakes.FakeIB()
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, loop, fake, "--whatif", "AAPL", "--quantity", quantity)
    assert exc.value.code != 0
    assert fake.calls == []


def test_an_unreachable_gateway_is_exit_3_with_one_stderr_line(tmp_path, loop, capsys):
    fake = ibkr_fakes.FakeIB(refuse=ConnectionRefusedError("refused"))
    code = _run(tmp_path, loop, fake, "--history")
    assert code == 3
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1


def test_a_foreign_account_is_exit_8(tmp_path, loop, capsys):
    fake = ibkr_fakes.FakeIB(accounts=["U1234567"])
    code = _run(tmp_path, loop, fake, "--history")
    assert code == 8
    assert "ACCOUNT_GUARD_VIOLATED" in capsys.readouterr().err
    _assert_nothing_sent(fake)


def test_the_probe_source_cannot_send_or_cancel():
    source = _PROBE.read_text(encoding="utf-8")
    for needle in ("cancel_all", "reqGlobalCancel", "placeOrder", "reqMktData", "ib_async"):
        assert needle not in source
