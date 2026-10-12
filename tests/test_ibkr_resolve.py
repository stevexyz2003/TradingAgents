"""The ``resolve`` command of the IBKR executor, against fakes only.

Every path comes from ``tmp_path``; nothing here reads the operator's ``.env`` or
reaches the gateway. A real connect of the client library is blocked in this
module, and every call of ``main`` gets its own ``--env-file``, ``--log-file``,
``broker_factory`` and ``clock``.
"""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests import ibkr_fakes

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_executor.py"


def _load_executor():
    spec = importlib.util.spec_from_file_location("ibkr_executor", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = _load_executor()
broker = executor.load_broker_module()
contracts_mod = executor.load_contracts_module()

DEFAULT_ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_ACCOUNT_ID": "DUQ634065",
    "IBKR_TRADING_MODE": "paper",
}

#: A Monday, 13:20 US/Eastern: inside the regular session.
OPEN_NOW = datetime(2026, 10, 12, 17, 20, tzinfo=UTC)
OPEN_HOURS = "20261012:0930-20261012:1600"
#: A Saturday; the listing carries a CLOSED entry and the next Monday window.
CLOSED_NOW = datetime(2026, 10, 10, 17, 20, tzinfo=UTC)
CLOSED_HOURS = "20261010:CLOSED;20261012:0930-20261012:1600"

CON_IDS = {"AAPL": 265598, "MSFT": 272093, "NVDA": 4815747}


@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)


@pytest.fixture(autouse=True)
def _close_logging():
    yield
    executor.close_logging()


def _env_file(tmp_path, **values):
    merged = {**DEFAULT_ENV, **values}
    lines = [f"{key}={value}" for key, value in merged.items() if value is not None]
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class _RecordingFactory:
    """A broker factory that must never be called."""

    def __init__(self):
        self.calls = []

    def __call__(self, host, port, logger):
        self.calls.append((host, port))
        raise AssertionError("the broker factory must not be called")


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


def _fixed(moment):
    return lambda: moment


def _run(tmp_path, factory, tickers, *, extra=(), env_file=None, contracts=None, clock=OPEN_NOW):
    env_file = _env_file(tmp_path) if env_file is None else env_file
    contracts = tmp_path / "ibkr" / "contracts.json" if contracts is None else contracts
    log = tmp_path / "logs" / "executor.log"
    argv = [
        "resolve",
        *tickers,
        "--contracts",
        str(contracts),
        "--env-file",
        str(env_file),
        "--log-file",
        str(log),
        *extra,
    ]
    code = executor.main(argv, broker_factory=factory, clock=_fixed(clock))
    executor.close_logging()
    return code, contracts, log


def _log_text(log):
    return log.read_text(encoding="utf-8")


def _identity(ticker, con_id=None, exchange="NASDAQ"):
    return contracts_mod.Identity(
        CON_IDS[ticker] if con_id is None else con_id, exchange, "USD", ticker
    )


def _contracts_file(tmp_path, entries):
    """A valid contracts file; ``entries`` maps ticker to an Identity."""
    path = tmp_path / "ibkr" / "contracts.json"
    table = {
        t: contracts_mod.StoredContract(i, "2026-10-01T00:00:00+00:00") for t, i in entries.items()
    }
    contracts_mod.commit_contracts(path, table, ())
    return path


def _fake_for(tickers=("AAPL",), *, liquid_hours=OPEN_HOURS, **detail_kwargs):
    contracts = {t: ibkr_fakes.stk_contract(t, CON_IDS[t]) for t in tickers}
    return ibkr_fakes.FakeIB(
        qualify={t: [c] for t, c in contracts.items()},
        details={
            CON_IDS[t]: [ibkr_fakes.contract_detail(c, liquid_hours=liquid_hours, **detail_kwargs)]
            for t, c in contracts.items()
        },
    )


# --- argument checks and the contracts file (D-12, D-14, D-26, D-27) -----------------


class TestScaffold:
    def test_contracts_module_is_shared(self):
        assert executor.load_contracts_module() is sys.modules["ibkr_contracts"]

    def test_exit_table_names_exit_2_without_reserved(self):
        for line in executor.__doc__.splitlines():
            if line.startswith("    2 "):
                assert "reserved" not in line
                break
        else:
            pytest.fail("no exit-2 line in the docstring")

    def test_no_tickers_is_a_usage_error(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, _contracts, _log = _run(tmp_path, factory, [])
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "resolve needs at least one TICKER" in capsys.readouterr().err

    def test_init_and_rebaseline_exclude_each_other(self, tmp_path):
        code, _c, _l = _run(
            tmp_path, _RecordingFactory(), ["AAPL"], extra=["--init", "--rebaseline", "AAPL"]
        )
        assert code == executor.EXIT_CONFIG

    def test_rebaseline_target_must_be_among_the_tickers(self, tmp_path, capsys):
        code, _c, _l = _run(tmp_path, _RecordingFactory(), ["AAPL"], extra=["--rebaseline", "MSFT"])
        assert code == executor.EXIT_CONFIG

    def test_init_needs_the_anchor(self, tmp_path, capsys):
        code, _c, _l = _run(tmp_path, _RecordingFactory(), ["MSFT"], extra=["--init"])
        assert code == executor.EXIT_CONFIG
        assert "AAPL" in capsys.readouterr().err

    def test_locally_rejected_tickers_need_no_env_and_no_gateway(self, tmp_path, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        factory = _RecordingFactory()
        code, _c, log = _run(
            tmp_path,
            factory,
            ["XYZQ", "^GSPC", "XAUUSD+"],
            contracts=path,
            env_file=tmp_path / "missing.env",
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("resolve: ")]
        assert len(lines) == 3
        assert "not-mapped" in lines[0]
        assert "not-allowed" in lines[1]
        assert "not-allowed" in lines[2]
        assert "STK" in lines[2]

    def test_missing_contracts_file_is_exit_2(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, path, log = _run(tmp_path, factory, ["AAPL"])
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert "resolve --init" in capsys.readouterr().err
        text = _log_text(log)
        assert "CONTRACTS_MISSING" in text
        assert "resolve --init" in text
        assert not path.exists()

    @pytest.mark.parametrize(
        "content",
        ["not json at all", '{"schema_version": 2, "contracts": {}}'],
        ids=["broken", "wrong-version"],
    )
    def test_invalid_contracts_file_is_exit_1(self, tmp_path, content):
        path = tmp_path / "ibkr" / "contracts.json"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        factory = _RecordingFactory()
        code, _c, log = _run(tmp_path, factory, ["AAPL"], contracts=path)
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "CONTRACTS_INVALID" in _log_text(log)
        assert path.read_text(encoding="utf-8") == content

    def test_init_refuses_an_existing_file(self, tmp_path, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        before = path.read_bytes()
        factory = _RecordingFactory()
        code, _c, log = _run(tmp_path, factory, ["AAPL"], contracts=path, extra=["--init"])
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert "CONTRACTS_EXIST" in _log_text(log)
        assert "--rebaseline" in capsys.readouterr().err
        assert path.read_bytes() == before

    def test_rebaseline_without_an_entry_is_exit_2(self, tmp_path):
        path = _contracts_file(tmp_path, {"MSFT": _identity("MSFT")})
        factory = _RecordingFactory()
        code, _c, _l = _run(
            tmp_path, factory, ["AAPL"], contracts=path, extra=["--rebaseline", "AAPL"]
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []

    def test_mapped_ticker_without_env_file_is_exit_20(self, tmp_path, loop):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        factory = _RecordingFactory()
        code, _c, log = _run(
            tmp_path, factory, ["AAPL"], contracts=path, env_file=tmp_path / "missing.env"
        )
        assert code == executor.EXIT_NO_CREDENTIALS
        assert factory.calls == []

    def test_live_trading_mode_is_exit_1(self, tmp_path):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        env = _env_file(tmp_path, IBKR_TRADING_MODE="live")
        factory = _RecordingFactory()
        code, _c, _l = _run(tmp_path, factory, ["AAPL"], contracts=path, env_file=env)
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
