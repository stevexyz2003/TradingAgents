"""The ``preview`` command of the IBKR executor, against fakes only.

Every path comes from ``tmp_path``; nothing here reads the operator's ``.env`` or
reaches the gateway. The paper-log is a directory (``FixturePaperLog``), the session
calendar a weekday stub or the real XNYS calendar, the gateway a ``FakeIB``. A real
connect of the client library is blocked in this module, and every call of ``main``
gets its own ``--env-file``, ``--log-file``, ``--out``, ``--contracts``, clock and
injected collaborators.
"""

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests import ibkr_fakes
from tests.calendar_stub import WeekdayCalendar
from tests.paper_log_fixture import FixturePaperLog, write_paper_log

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
decision = executor.load_decision_module()
paperlog = executor.load_paperlog_module()

DEFAULT_ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_ACCOUNT_ID": "DUQ634065",
    "IBKR_TRADING_MODE": "paper",
}

#: A Monday, 13:20 US/Eastern: inside the regular session (Columbus Day, NYSE open).
OPEN_NOW = datetime(2026, 10, 12, 17, 20, tzinfo=UTC)
OPEN_HOURS = "20261012:0930-20261012:1600"
#: A Saturday; the listing carries a CLOSED entry and the next Monday window.
CLOSED_NOW = datetime(2026, 10, 10, 17, 20, tzinfo=UTC)
CLOSED_HOURS = "20261010:CLOSED;20261012:0930-20261012:1600"
#: The clock of the frozen-branch case: Monday 11:00 US/Eastern.
FROZEN_NOW = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)

CON_IDS = {"AAPL": 265598, "MSFT": 272093, "NVDA": 4815747}
SHA = "a" * 40


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


@pytest.fixture(autouse=True)
def _local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


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


def _stub_calendar(**kwargs):
    return WeekdayCalendar(range_error=decision.CalendarRangeError, **kwargs)


def _fixed(moment):
    return lambda: moment


class _PaperLogFactory:
    """The injected ``paper_log_factory``; records what the executor handed it."""

    def __init__(self, source):
        self.source = source
        self.calls = []

    def __call__(self, repo, remote, branch):
        self.calls.append((repo, remote, branch))
        return self.source


def _run_preview(
    tmp_path,
    factory,
    tickers,
    *,
    paper_log,
    calendar=None,
    clock=OPEN_NOW,
    contracts=None,
    extra=(),
    env_file=None,
    out=None,
):
    """Run ``main(["preview", ...])``; returns (exit code, out path, log path, contracts path)."""
    env_file = _env_file(tmp_path) if env_file is None else env_file
    contracts = tmp_path / "ibkr" / "contracts.json" if contracts is None else contracts
    out = tmp_path / "out" / "preview.json" if out is None else out
    log = tmp_path / "logs" / "executor.log"
    argv = [
        "preview",
        *tickers,
        "--contracts",
        str(contracts),
        "--out",
        str(out),
        "--env-file",
        str(env_file),
        "--log-file",
        str(log),
        *extra,
    ]
    paper_log_factory = (
        paper_log if isinstance(paper_log, _PaperLogFactory) else _PaperLogFactory(paper_log)
    )
    code = executor.main(
        argv,
        broker_factory=factory,
        clock=_fixed(clock),
        paper_log_factory=paper_log_factory,
        calendar=_stub_calendar() if calendar is None else calendar,
    )
    executor.close_logging()
    return code, out, log, contracts


def _log_text(log):
    return log.read_text(encoding="utf-8")


def _payload(out):
    return json.loads(Path(out).read_text(encoding="utf-8"))


def _rows(out):
    return {row["ticker"]: row for row in _payload(out)["rows"]}


# --- fixtures for the paper-log -------------------------------------------------------


def _summary(trade_date, *runs, status="ok", schema=1):
    """A summary.json; ``runs`` are (ticker, status, signal) triples."""
    return {
        "schema_version": schema,
        "trade_date": trade_date,
        "status": status,
        "runs": [{"ticker": t, "status": s, "signal": sig} for t, s, sig in runs],
    }


def _paper(tmp_path, entries, summaries):
    root = write_paper_log(tmp_path / "pl", entries, summaries)
    return FixturePaperLog(root, SHA)


def _buy_paper(tmp_path, rating="Buy", ticker="AAPL"):
    """A paper-log with one decision dated Friday 2026-10-09 and its matching summary."""
    return _paper(
        tmp_path,
        [("2026-10-09", ticker, rating)],
        {"2026-10-09": _summary("2026-10-09", (ticker, "ok", rating))},
    )


# --- wiring: arguments, settings, paths, exit table (D-03, D-07, D-16) ----------------


class TestWiring:
    def test_usage_lists_preview(self, capsys):
        assert executor.main([], broker_factory=_RecordingFactory()) == executor.EXIT_CONFIG
        assert "account, resolve, preview" in capsys.readouterr().err

    def test_no_tickers_is_a_usage_error(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, _out, _log, _c = _run_preview(
            tmp_path, factory, [], paper_log=FixturePaperLog.unavailable("x")
        )
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert "preview needs at least one TICKER (no default list)" in capsys.readouterr().err

    def test_there_is_no_date_option(self, tmp_path):
        source = FixturePaperLog.unavailable("x")
        paper_log_factory = _PaperLogFactory(source)
        code, _out, _log, _c = _run_preview(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=paper_log_factory,
            extra=["--trade" + "-date", "2026-10-09"],
        )
        assert code == executor.EXIT_CONFIG
        assert paper_log_factory.calls == []

    def test_remote_and_branch_default_to_fork_and_paper_log(self, tmp_path):
        paper_log_factory = _PaperLogFactory(FixturePaperLog.unavailable("offline"))
        _run_preview(tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper_log_factory)
        assert paper_log_factory.calls == [(executor.REPO_ROOT, "fork", "paper-log")]

    def test_remote_and_branch_come_from_the_env_file(self, tmp_path):
        paper_log_factory = _PaperLogFactory(FixturePaperLog.unavailable("offline"))
        env = _env_file(tmp_path, IBKR_PAPER_LOG_REMOTE="upstream", IBKR_PAPER_LOG_BRANCH="logs/x")
        _run_preview(
            tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper_log_factory, env_file=env
        )
        assert paper_log_factory.calls == [(executor.REPO_ROOT, "upstream", "logs/x")]

    @pytest.mark.parametrize(
        "key", ["IBKR_PAPER_LOG_REMOTE", "IBKR_PAPER_LOG_BRANCH"], ids=["remote", "branch"]
    )
    def test_option_injection_in_the_settings_is_exit_1(self, tmp_path, key):
        paper_log_factory = _PaperLogFactory(FixturePaperLog.unavailable("offline"))
        env = _env_file(tmp_path, **{key: "-upload-pack=x"})
        code, _out, log, _c = _run_preview(
            tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper_log_factory, env_file=env
        )
        assert code == executor.EXIT_CONFIG
        assert paper_log_factory.calls == []
        assert "ibkr-state=CONFIG_INVALID" in _log_text(log)

    def test_exit_table_matches_the_executor_constants(self):
        allowed = {
            executor.EXIT_OK,
            executor.EXIT_CONFIG,
            executor.EXIT_PRECONDITION,
            executor.EXIT_REJECTED,
        }
        assert set(decision.EXIT_BY_STATE.values()) <= allowed
        assert decision.EXIT_BY_STATE["skipped-hold"] == executor.EXIT_PRECONDITION
        assert decision.EXIT_BY_STATE["over-budget"] == executor.EXIT_REJECTED
        assert decision.EXIT_BY_STATE["summary-schema"] == executor.EXIT_CONFIG
        assert decision.EXIT_BY_STATE["preview-ok"] == executor.EXIT_OK

    def test_default_paths(self):
        env = {"LOCALAPPDATA": "X"}
        assert executor.default_preview_file(env) == Path("X/TradingEngineX/ibkr/preview.json")
        copy = executor.default_paper_log_copy(env)
        assert copy == Path("X/TradingEngineX/ibkr/paper-log/decision-log.md")

    def test_missing_calendar_library_is_exit_1(self, tmp_path, monkeypatch, capsys):
        def missing():
            raise ImportError("exchange_calendars")

        monkeypatch.setattr(decision, "load_xnys_calendar", missing)
        paper_log_factory = _PaperLogFactory(FixturePaperLog.unavailable("offline"))
        code = executor.main(
            [
                "preview",
                "AAPL",
                "--env-file",
                str(_env_file(tmp_path)),
                "--log-file",
                str(tmp_path / "logs" / "e.log"),
                "--out",
                str(tmp_path / "out.json"),
            ],
            broker_factory=_RecordingFactory(),
            clock=_fixed(OPEN_NOW),
            paper_log_factory=paper_log_factory,
            calendar=None,
        )
        assert code == executor.EXIT_CONFIG
        assert 'pip install -e ".[ibkr]"' in capsys.readouterr().err
        assert paper_log_factory.calls == []

    def test_earlier_output_is_removed_and_the_new_one_has_the_record_shape(self, tmp_path):
        out = tmp_path / "out" / "preview.json"
        out.parent.mkdir(parents=True)
        out.write_text("stale", encoding="utf-8")
        code, _out, log, _c = _run_preview(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=FixturePaperLog.unavailable("offline"),
            out=out,
        )
        assert code == executor.EXIT_PRECONDITION
        data = _payload(out)
        assert data["schema_version"] == 1
        assert data["sent"] is False
        assert data["as_of"] == OPEN_NOW.isoformat()
        assert data["paper_log"] == {"remote": "fork", "branch": "paper-log", "sha": None}
        assert "rows" in data
        assert "decision_key" not in data
        assert "previous output removed" in _log_text(log)

    def test_module_loaders_share_sys_modules(self):
        assert executor.load_decision_module() is sys.modules["ibkr_decision"]
        assert executor.load_paperlog_module() is sys.modules["ibkr_paperlog"]
        assert executor.load_state_maintenance_module() is sys.modules["state_maintenance"]

    def test_settings_do_not_demand_the_optional_keys(self, tmp_path):
        env = _env_file(tmp_path)
        settings = executor.read_settings(env)
        assert "IBKR_PAPER_LOG_REMOTE" not in settings
        assert executor.OPTIONAL_ENV_DEFAULTS == {
            "IBKR_PAPER_LOG_REMOTE": "fork",
            "IBKR_PAPER_LOG_BRANCH": "paper-log",
        }

