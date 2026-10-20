"""The IBKR executor command: exit codes, settings, the log file, the account flow.

Every path comes from ``tmp_path``; nothing here reads the operator's ``.env`` or
reaches the gateway. A real connect of the client library is blocked in this
module, and every call of ``main`` gets ``--env-file``, ``--log-file`` and a
``broker_factory`` of its own.
"""

import importlib.util
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests import ibkr_fakes
from tradingagents.portfolio import load_portfolio

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_executor.py"


def _load_executor():
    spec = importlib.util.spec_from_file_location("ibkr_executor", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = _load_executor()
broker = executor.load_broker_module()

EXIT_NAMES = (
    "EXIT_OK",
    "EXIT_CONFIG",
    "EXIT_PRECONDITION",
    "EXIT_GATEWAY",
    "EXIT_KILL_SWITCH",
    "EXIT_REJECTED",
    "EXIT_RECONCILE",
    "EXIT_LOCKED",
    "EXIT_ACCOUNT_GUARD",
    "EXIT_FILL_TIMEOUT",
    "EXIT_POST_ORDER",
    "EXIT_PUBLISH",
    "EXIT_NO_CREDENTIALS",
)

DEFAULT_ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_ACCOUNT_ID": "DUQ634065",
    "IBKR_TRADING_MODE": "paper",
}


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
    """A .env in tmp_path; a value of None leaves the key out."""
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
    """The real adapter against a FakeIB, with short timeouts."""

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


def _run(tmp_path, factory, *, env_file=None, out=None, extra=()):
    env_file = _env_file(tmp_path) if env_file is None else env_file
    out = tmp_path / "out" / "portfolio.json" if out is None else out
    log = tmp_path / "logs" / "executor.log"
    argv = [
        "account",
        "--out",
        str(out),
        "--env-file",
        str(env_file),
        "--log-file",
        str(log),
        *extra,
    ]
    code = executor.main(argv, broker_factory=factory)
    executor.close_logging()
    return code, out, log


def _log_text(log):
    return log.read_text(encoding="utf-8")


def _own_file_handlers():
    """File handlers on the root logger, minus the one pytest's logging plugin adds."""
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.FileHandler) and type(h).__module__ != "_pytest.logging"
    ]


# --- exit codes ---------------------------------------------------------------------


class TestExitCodes:
    def test_exit_codes_are_disjoint_and_complete(self):
        values = [getattr(executor, name) for name in EXIT_NAMES]
        assert values == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 20]
        assert len(set(values)) == len(values)

    def test_exit_codes_match_the_docstring_table(self):
        documented = {int(m) for m in re.findall(r"^\s{4}(\d+)\s{2,}", executor.__doc__, re.M)}
        assert documented == {getattr(executor, name) for name in EXIT_NAMES}

    def test_executor_and_fakes_share_the_broker_module(self):
        assert executor.load_broker_module() is ibkr_fakes.load_broker()

    def test_usage_error_without_subcommand(self, capsys):
        assert executor.main([], broker_factory=_RecordingFactory()) == executor.EXIT_CONFIG

    def test_usage_error_unknown_subcommand(self, capsys):
        assert executor.main(["trade"], broker_factory=_RecordingFactory()) == executor.EXIT_CONFIG

    def test_usage_error_account_without_out(self, tmp_path, capsys):
        factory = _RecordingFactory()
        argv = [
            "account",
            "--env-file",
            str(_env_file(tmp_path)),
            "--log-file",
            str(tmp_path / "x.log"),
        ]
        assert executor.main(argv, broker_factory=factory) == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "--out" in capsys.readouterr().err


# --- settings -----------------------------------------------------------------------


class TestSettings:
    @pytest.mark.parametrize(
        ("values", "missing"),
        [
            ({"IBKR_HOST": None}, "IBKR_HOST"),
            ({"IBKR_PORT": None}, "IBKR_PORT"),
            ({"IBKR_ACCOUNT_ID": None}, "IBKR_ACCOUNT_ID"),
            ({"IBKR_PORT": "   "}, "IBKR_PORT"),
        ],
        ids=["no-host", "no-port", "no-account", "blank-port"],
    )
    def test_missing_credentials_exit_20(self, tmp_path, capsys, values, missing):
        factory = _RecordingFactory()
        env = _env_file(tmp_path, IBKR_PASSWORD="hidden-value", **values)
        code, out, log = _run(tmp_path, factory, env_file=env)
        assert code == executor.EXIT_NO_CREDENTIALS
        assert factory.calls == []
        text = _log_text(log)
        assert "SETTINGS_MISSING" in text
        assert missing in text
        assert "hidden-value" not in text
        assert not out.exists()
        err = capsys.readouterr().err
        assert missing in err

    def test_missing_env_file_exit_20(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, _out, log = _run(tmp_path, factory, env_file=tmp_path / "nope" / ".env")
        assert code == executor.EXIT_NO_CREDENTIALS
        assert factory.calls == []
        assert "SETTINGS_MISSING" in _log_text(log)

    @pytest.mark.parametrize(
        "values",
        [
            {"IBKR_PORT": "abc"},
            {"IBKR_PORT": "70000"},
            {"IBKR_ACCOUNT_ID": "U1234567"},
            {"IBKR_TRADING_MODE": "live"},
        ],
        ids=["port-not-int", "port-out-of-range", "live-account", "live-mode"],
    )
    def test_config_errors_exit_1(self, tmp_path, capsys, values):
        factory = _RecordingFactory()
        code, out, log = _run(tmp_path, factory, env_file=_env_file(tmp_path, **values))
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "CONFIG_INVALID" in _log_text(log)
        assert not out.exists()
        assert "Traceback" not in capsys.readouterr().err

    def test_account_id_must_match_the_code_constant(self, tmp_path):
        raw = {**DEFAULT_ENV, "IBKR_ACCOUNT_ID": "DU0000001"}
        with pytest.raises(executor.ConfigError, match="DUQ634065"):
            executor.validate_settings(raw, broker.EXPECTED_ACCOUNT)

    def test_password_is_never_read_or_logged(self, tmp_path, capsys, loop):
        env = _env_file(tmp_path, IBKR_PASSWORD="s3cr3t-Ü", IBKR_USERNAME="someone")
        settings = executor.read_settings(env)
        assert "IBKR_PASSWORD" not in settings
        assert "IBKR_USERNAME" not in settings
        fake = ibkr_fakes.FakeIB()
        code, out, log = _run(tmp_path, _fake_factory(fake, loop), env_file=env)
        assert code == executor.EXIT_OK
        assert out.exists()
        captured = capsys.readouterr()
        for text in (_log_text(log), captured.out, captured.err):
            assert "s3cr3t" not in text
            assert "someone" not in text


# --- the log file -------------------------------------------------------------------


class TestLogFile:
    def test_log_file_is_utf8_absolute_and_names_itself(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        logger = executor.setup_logging(Path("rel") / "run.log")
        logger.info("Gateway nicht erreichbar – schreibgeschützt")
        executor.close_logging()
        path = (tmp_path / "rel" / "run.log").resolve()
        assert path.is_file()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert str(path) in lines[0]
        assert Path(lines[0].split("log file: ", 1)[1]).is_absolute()
        assert any("Gateway nicht erreichbar – schreibgeschützt" in line for line in lines)

    def test_library_loggers_land_in_the_log_file(self, tmp_path, capsys):
        path = tmp_path / "x.log"
        executor.setup_logging(path)
        logging.getLogger("thirdparty.client").error("Fehler Ü-123")
        file_handlers = _own_file_handlers()
        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename) == path.resolve()
        executor.close_logging()
        assert "Fehler Ü-123" in path.read_text(encoding="utf-8")
        assert capsys.readouterr().err == ""
        assert _own_file_handlers() == []
        path.unlink()  # no Windows file lock left behind
        assert not path.exists()

    def test_repeated_setup_keeps_one_file_handler(self, tmp_path):
        executor.setup_logging(tmp_path / "a.log")
        executor.setup_logging(tmp_path / "b.log")
        file_handlers = _own_file_handlers()
        assert [Path(h.baseFilename).name for h in file_handlers] == ["b.log"]

    def test_default_log_file_is_outside_the_repo(self, tmp_path):
        assert executor.default_log_file({"LOCALAPPDATA": str(tmp_path)}) == (
            tmp_path / "TradingEngineX" / "ibkr" / "logs" / "ibkr_executor.log"
        )
        fallback = executor.default_log_file({})
        assert fallback == (Path.home() / ".tradingenginex" / "ibkr" / "logs" / "ibkr_executor.log")

    def test_default_env_file_is_the_repo_root(self):
        assert _SCRIPT.parents[1] / ".env" == executor.DEFAULT_ENV_FILE


# --- the account flow, real adapter against FakeIB ------------------------------------

ACCOUNT = "DUQ634065"
FORBIDDEN_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions", "whatIfOrder")


def _book():
    return {
        "positions": [
            ibkr_fakes.position(ACCOUNT, "AAPL", 3, 250.5),
            ibkr_fakes.position(ACCOUNT, "MSFT", 0, 10.0),
        ],
        "summary": [
            ibkr_fakes.account_value("TotalCashValue", "1005459.44", "EUR"),
            ibkr_fakes.account_value("AvailableFunds", "1004000.00", "EUR"),
        ],
    }


def _snapshot(*positions):
    return broker.AccountSnapshot(
        account=ACCOUNT,
        positions=positions,
        cash=1000.0,
        cash_currency="EUR",
        available_funds=1000.0,
        available_funds_currency="EUR",
        as_of=datetime.now(UTC),
    )


class _PositionsBoom(ibkr_fakes.FakeIB):
    async def reqPositionsAsync(self):
        self.calls.append("positions")
        raise RuntimeError("boom")


class _HandshakeBoom(ibkr_fakes.FakeIB):
    """The handshake stood, then the library failed while it parsed the accounts."""

    def managedAccounts(self):
        raise ValueError("unparseable managedAccounts")


class _WritesDuringConnect(ibkr_fakes.FakeIB):
    """Something inside the connect tries to place an order."""

    async def connectAsync(self, *args, **kwargs):
        await super().connectAsync(*args, **kwargs)
        self.client.placeOrder(1, None, None)


class _WritesOnTheWire(ibkr_fakes.FakeIB):
    """A read that sends a write message (id 3) through the raw send path."""

    async def reqContractDetailsAsync(self, contract):
        self.client.send(3, 1, 42)


class TestAccount:
    def test_account_writes_portfolio_that_load_portfolio_accepts(self, tmp_path, capsys, loop):
        fake = ibkr_fakes.FakeIB(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_OK
        ctx = load_portfolio(out)
        assert ctx.cash == 1005459.44
        assert ctx.currency == "EUR"
        assert [p.ticker for p in ctx.positions] == ["AAPL"]
        assert ctx.positions[0].quantity == 3
        assert ctx.positions[0].average_price is None
        assert list(out.parent.glob("*.tmp")) == []
        assert "disconnect" in fake.calls
        captured = capsys.readouterr()
        assert captured.out.strip().splitlines() == [
            f"account: 1 position(s), cash 1005459.44 EUR -> {out.resolve()}"
        ]
        assert captured.err == ""
        text = _log_text(log)
        assert "portfolio written" in text
        assert ACCOUNT in text

    def test_foreign_currency_average_price_is_dropped(self, tmp_path):
        logger = executor.setup_logging(tmp_path / "x.log")
        snapshot = _snapshot(
            broker.BrokerPosition("AAPL", "STK", "AAPL", "USD", 3.0, 250.5),
            broker.BrokerPosition("SAP", "STK", "SAP", "EUR", 2.0, 120.0),
        )
        ctx = executor.snapshot_to_portfolio(snapshot, logger)
        executor.close_logging()
        by_ticker = {p.ticker: p for p in ctx.positions}
        assert by_ticker["AAPL"].average_price is None
        assert by_ticker["SAP"].average_price == 120.0
        warnings = [
            line
            for line in (tmp_path / "x.log").read_text(encoding="utf-8").splitlines()
            if " WARNING " in line
        ]
        assert any("AAPL" in w and "USD" in w and "EUR" in w for w in warnings)
        assert not any("SAP" in w for w in warnings)

    def test_non_stock_position_keeps_no_price(self, tmp_path):
        logger = executor.setup_logging(tmp_path / "x.log")
        snapshot = _snapshot(broker.BrokerPosition("ES", "FUT", "ESZ6", "EUR", 1.0, 250000.0))
        ctx = executor.snapshot_to_portfolio(snapshot, logger)
        executor.close_logging()
        assert ctx.positions[0].ticker == "ESZ6"
        assert ctx.positions[0].average_price is None
        assert "FUT" in (tmp_path / "x.log").read_text(encoding="utf-8")

    def test_account_json_contains_schema_fields_and_as_of(self, tmp_path, loop):
        fake = ibkr_fakes.FakeIB(**_book())
        before = datetime.now(UTC)
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_OK
        data = json.loads(out.read_text(encoding="utf-8"))
        assert set(data) == {"cash", "currency", "positions", "as_of"}
        as_of = datetime.fromisoformat(data["as_of"])
        assert as_of.tzinfo is not None
        assert before <= as_of <= datetime.now(UTC)
        assert f"as_of={data['as_of']}" in _log_text(log)

    def test_written_file_passes_the_paper_runs_freshness_check(self, tmp_path, loop):
        spec = importlib.util.spec_from_file_location(
            "daily_paper_run", _SCRIPT.with_name("daily_paper_run.py")
        )
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        assert executor.AS_OF_KEY == runner.PORTFOLIO_AS_OF_KEY
        code, out, _log = _run(tmp_path, _fake_factory(ibkr_fakes.FakeIB(**_book()), loop))
        assert code == executor.EXIT_OK
        ctx = runner.load_fresh_portfolio(out, max_age=runner.DEFAULT_PORTFOLIO_MAX_AGE)
        assert ctx == load_portfolio(out)
        assert ctx.cash == 1005459.44

    @pytest.mark.parametrize(
        "accounts",
        [["DU0000001"], ["DUQ634065", "DU0000001"]],
        ids=["foreign", "superset"],
    )
    def test_guard_violation_exits_8_without_writes(self, tmp_path, capsys, loop, accounts):
        fake = ibkr_fakes.FakeIB(accounts=accounts, **_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_ACCOUNT_GUARD
        assert "disconnect" in fake.calls
        assert not any(name in fake.calls for name in FORBIDDEN_CALLS)
        assert not out.exists()
        text = _log_text(log)
        assert "ACCOUNT_GUARD_VIOLATED" in text
        assert "DU0000001" in text
        err = capsys.readouterr().err
        assert len(err.strip().splitlines()) == 1
        assert "Traceback" not in err

    def test_unreachable_gateway_exits_3_with_named_state(self, tmp_path, capsys, loop):
        fake = ibkr_fakes.FakeIB(refuse=ConnectionRefusedError())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        text = _log_text(log)
        assert "GATEWAY_UNREACHABLE" in text
        assert "502" in text
        assert "Gateway nicht erreichbar" in text
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out + captured.err
        assert len(captured.err.strip().splitlines()) == 1
        assert not out.exists()

    def test_client_id_in_use_exits_3(self, tmp_path, loop):
        fake = ibkr_fakes.FakeIB(
            emit_on_connect=[(-1, 326, "client id is already in use", None)],
            refuse=TimeoutError(),
        )
        code, _out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        assert "CLIENT_ID_IN_USE" in _log_text(log)

    def test_unhealthy_session_exits_3(self, tmp_path, capsys, loop):
        fake = ibkr_fakes.FakeIB(probe="hang", **_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        assert "PROBE_TIMEOUT" in _log_text(log)
        assert not out.exists()
        assert "disconnect" in fake.calls
        assert len(capsys.readouterr().err.strip().splitlines()) == 1

    def test_link_loss_during_the_snapshot_exits_3_without_a_file(self, tmp_path, capsys, loop):
        # CR-01 negative control: the gateway answers from its local state after a
        # 1100, the answer is well formed, and the run must still not write a file.
        fake = ibkr_fakes.FakeIB(
            emit_during={"positions": [(-1, 1100, "Connectivity lost", None)]}, **_book()
        )
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        assert not out.exists()
        text = _log_text(log)
        assert "ibkr-state=CONNECTIVITY_LOST code=1100" in text
        assert "snapshot discarded" in text
        assert "disconnect" in fake.calls
        assert len(capsys.readouterr().err.strip().splitlines()) == 1

    def test_read_only_warning_survives_in_the_log(self, tmp_path, loop):
        fake = ibkr_fakes.FakeIB(
            emit_on_connect=[(-1, 321, "Die API befindet sich im schreibgeschützten Modus", None)],
            **_book(),
        )
        code, _out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_OK
        text = _log_text(log)
        assert "READ_ONLY_API" in text
        assert "schreibgeschützten" in text

    def test_missing_extra_exits_1_with_hint(self, tmp_path, capsys, loop):
        def no_library():
            raise ModuleNotFoundError("No module named the IBKR client library")

        def factory(host, port, logger):
            return broker.IbkrBroker(host, port, logger=logger, ib_factory=no_library, loop=loop)

        code, out, _log = _run(tmp_path, factory)
        assert code == executor.EXIT_CONFIG
        err = capsys.readouterr().err
        assert 'pip install -e ".[ibkr]"' in err
        assert "Traceback" not in err
        assert not out.exists()

    def test_unexpected_error_has_no_console_traceback(self, tmp_path, capsys, loop):
        fake = _PositionsBoom(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        captured = capsys.readouterr()
        assert len(captured.err.strip().splitlines()) == 1
        assert "Traceback" not in captured.out + captured.err
        assert "boom" in captured.err
        assert "Traceback" in _log_text(log)
        assert "disconnect" in fake.calls
        assert not out.exists()

    def test_unexpected_error_inside_connect_exits_3_not_1(self, tmp_path, capsys, loop):
        # WR-03: a socket and a handshake stood, so "nothing was done" (exit 1) is wrong.
        fake = _HandshakeBoom(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        assert "connect" in fake.calls
        assert "disconnect" in fake.calls
        assert "ibkr-state=UNEXPECTED ValueError" in _log_text(log)
        assert not out.exists()
        assert "Traceback" not in capsys.readouterr().err

    def test_error_before_the_connect_starts_stays_exit_1(self, tmp_path):
        def factory(host, port, logger):
            raise RuntimeError("broken factory")

        code, _out, log = _run(tmp_path, factory)
        assert code == executor.EXIT_CONFIG
        assert "ibkr-state=UNEXPECTED RuntimeError" in _log_text(log)

    @pytest.mark.parametrize("fake_cls", [_WritesDuringConnect, _WritesOnTheWire])
    def test_refused_write_has_its_own_state_and_exits_3(self, tmp_path, capsys, loop, fake_cls):
        fake = fake_cls(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_GATEWAY
        text = _log_text(log)
        assert "ibkr-state=WRITE_REFUSED" in text
        assert "UNEXPECTED" not in text
        assert "disconnect" in fake.calls
        assert not out.exists()
        err = capsys.readouterr().err
        assert err.startswith("error: ibkr-state=WRITE_REFUSED")
        assert len(err.strip().splitlines()) == 1

    @pytest.mark.parametrize(
        ("fake_kwargs", "env_values", "expected"),
        [
            ({"accounts": ["DU0000001"]}, {}, "EXIT_ACCOUNT_GUARD"),
            ({"refuse": ConnectionRefusedError()}, {}, "EXIT_GATEWAY"),
            ({"probe": "hang"}, {}, "EXIT_GATEWAY"),
            ({}, {"IBKR_PORT": None}, "EXIT_NO_CREDENTIALS"),
            ({}, {"IBKR_TRADING_MODE": "live"}, "EXIT_CONFIG"),
        ],
        ids=["guard", "unreachable", "unhealthy", "no-settings", "bad-config"],
    )
    def test_a_failed_run_leaves_no_portfolio_file(
        self, tmp_path, loop, fake_kwargs, env_values, expected
    ):
        # CR-02: a stale book from an earlier run must not survive a failed one,
        # or the paper run would analyze against it without noticing.
        out = tmp_path / "out" / "portfolio.json"
        out.parent.mkdir(parents=True)
        out.write_text('{"cash": 1.0, "currency": "EUR", "positions": []}', encoding="utf-8")
        fake = ibkr_fakes.FakeIB(**{**_book(), **fake_kwargs})
        env = _env_file(tmp_path, **env_values)
        code, _out, log = _run(tmp_path, _fake_factory(fake, loop), env_file=env, out=out)
        assert code == getattr(executor, expected)
        assert not out.exists()
        assert "previous output removed" in _log_text(log)

    def test_unremovable_previous_file_exits_1_before_connecting(self, tmp_path):
        out = tmp_path / "out" / "portfolio.json"
        out.mkdir(parents=True)  # a directory cannot be unlinked as a file
        factory = _RecordingFactory()
        code, _out, log = _run(tmp_path, factory, out=out)
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "OUTPUT_INVALID" in _log_text(log)

    def test_failed_cross_check_exits_1(self, tmp_path, capsys, loop, monkeypatch):
        def refuse(path):
            raise ValueError(f"portfolio file {path} is not usable: forced")

        monkeypatch.setattr(executor, "load_portfolio", refuse)
        fake = ibkr_fakes.FakeIB(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_CONFIG
        assert "OUTPUT_INVALID" in _log_text(log)
        assert not out.exists()  # checked as a temp file, never moved into place
        assert list(out.parent.glob("*.tmp")) == []
        err = capsys.readouterr().err
        assert len(err.strip().splitlines()) == 1
        assert "Traceback" not in err

    def test_unwritable_out_exits_1_and_leaves_no_temp(self, tmp_path, loop, monkeypatch):
        def locked(src, dst):
            raise PermissionError("in use")

        monkeypatch.setattr(executor.os, "replace", locked)
        fake = ibkr_fakes.FakeIB(**_book())
        code, out, log = _run(tmp_path, _fake_factory(fake, loop))
        assert code == executor.EXIT_CONFIG
        assert not out.exists()
        assert list(out.parent.glob("*.tmp")) == []
        assert "OUTPUT_INVALID" in _log_text(log)
