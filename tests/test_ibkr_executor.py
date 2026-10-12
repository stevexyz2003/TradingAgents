"""The IBKR executor command: exit codes, settings, the log file, the account flow.

Every path comes from ``tmp_path``; nothing here reads the operator's ``.env`` or
reaches the gateway. A real connect of the client library is blocked in this
module, and every call of ``main`` gets ``--env-file``, ``--log-file`` and a
``broker_factory`` of its own.
"""

import importlib.util
import logging
import re
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
        assert values == [0, 1, 2, 3, 4, 5, 6, 7, 8, 20]
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

    @pytest.mark.xfail(strict=True, reason="account flow lands in task 2")
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
