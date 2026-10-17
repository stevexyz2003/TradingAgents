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
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tests import ibkr_fakes, paper_log_fixture
from tests.calendar_stub import WeekdayCalendar
from tests.paper_log_fixture import FROZEN_DIR, FROZEN_SHA, FixturePaperLog, write_paper_log

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
paperlog = paper_log_fixture._pl

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
def _pin_modules(monkeypatch):
    """Hand the executor this file's module instances, whatever ``sys.modules`` holds.

    Other test files load ``ibkr_decision`` and ``ibkr_paperlog`` under the same name;
    the exception classes the fakes raise must be the ones the executor catches.
    """
    monkeypatch.setattr(executor, "load_decision_module", lambda: decision)
    monkeypatch.setattr(executor, "load_paperlog_module", lambda: paperlog)


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
        assert "account, resolve, preview, execute" in capsys.readouterr().err

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

    def test_the_state_tool_loader_registers_its_module(self):
        assert executor.load_state_maintenance_module() is sys.modules["state_maintenance"]

    def test_settings_do_not_demand_the_optional_keys(self, tmp_path):
        env = _env_file(tmp_path)
        settings = executor.read_settings(env)
        assert "IBKR_PAPER_LOG_REMOTE" not in settings
        assert executor.OPTIONAL_ENV_DEFAULTS == {
            "IBKR_PAPER_LOG_REMOTE": "fork",
            "IBKR_PAPER_LOG_BRANCH": "paper-log",
        }



# --- the local chain: no gateway is contacted (D-01, D-02, D-04, D-07, D-16) ----------


class _RecordingLog(FixturePaperLog):
    """A fixture source that remembers every path it was asked for (REQ-IBKR-18)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paths: list[str] = []

    def read(self, path):
        self.paths.append(path)
        return super().read(path)


def _raw_paper(tmp_path, log_text, summaries=None):
    """A paper-log directory with a hand-written ``decision-log.md``."""
    root = tmp_path / "pl"
    root.mkdir(parents=True, exist_ok=True)
    (root / "decision-log.md").write_bytes(log_text)
    for trade_date, summary in (summaries or {}).items():
        target = root / "runs" / trade_date / "summary.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary), encoding="utf-8")
    return FixturePaperLog(root, SHA)


_ENTRY_END = "\n\n<!-- ENTRY_END -->\n\n"


def _local(tmp_path, source, tickers=("AAPL",), clock=FROZEN_NOW, calendar=None):
    """Run ``preview`` with a gateway factory that must stay unused."""
    factory = _RecordingFactory()
    code, out, log, _c = _run_preview(
        tmp_path, factory, list(tickers), paper_log=source, clock=clock, calendar=calendar
    )
    assert factory.calls == [], "the gateway was contacted"
    return code, out, log


class TestRealBranchHold:
    """SC1 against the frozen copy of the branch: a Hold never reaches the gateway."""

    def _check(self, tmp_path, capsys, calendar):
        source = FixturePaperLog(FROZEN_DIR, FROZEN_SHA)
        code, out, log = _local(tmp_path, source, calendar=calendar)
        assert code == executor.EXIT_PRECONDITION
        assert "preview: AAPL skipped-hold" in capsys.readouterr().out
        data = _payload(out)
        row = _rows(out)["AAPL"]
        assert row["state"] == "skipped-hold"
        assert row["detail"] == "skipped: hold"
        assert row["exit"] == executor.EXIT_PRECONDITION
        assert data["paper_log"]["sha"] == FROZEN_SHA
        assert data["run_state"] is None
        assert data["sent"] is False
        assert f"sha={FROZEN_SHA}" in _log_text(log)

    def test_real_branch_hold_with_the_stub_calendar(self, tmp_path, capsys):
        self._check(tmp_path, capsys, None)

    def test_real_branch_hold_with_the_xnys_calendar(self, tmp_path, capsys):
        pytest.importorskip("exchange_calendars")
        self._check(tmp_path, capsys, decision.load_xnys_calendar())


class TestPaperLogUnavailable:
    def test_a_failed_fetch_ends_the_run_without_fallback(self, tmp_path, capsys):
        source = FixturePaperLog.unavailable("offline")
        code, out, log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        assert "preview: paper-log-unavailable" in capsys.readouterr().out
        data = _payload(out)
        assert data["run_state"] == "paper-log-unavailable"
        assert data["paper_log"]["sha"] is None
        assert data["rows"] == []
        assert source.fetch_calls == 1
        assert "PAPER_LOG_UNAVAILABLE" in _log_text(log)


class TestVerify:
    def test_a_broken_tag_line_is_a_log_finding(self, tmp_path):
        text = (
            "[2026-10-09 | AAPL | Buy | pending]\n\nDECISION:\nok"
            + _ENTRY_END
            + "[2026-10-10 | AAPL | Buy]\n\nDECISION:\nbroken"
            + _ENTRY_END
        )
        source = _raw_paper(tmp_path, text.encode("utf-8"))
        code, out, log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        assert _payload(out)["run_state"] == "log-finding"
        assert "FAIL" in _log_text(log)

    def test_an_empty_log_is_a_log_finding(self, tmp_path):
        source = _raw_paper(tmp_path, b"")
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        assert _payload(out)["run_state"] == "log-finding"

    def test_a_missing_log_is_a_log_finding(self, tmp_path):
        (tmp_path / "pl").mkdir()
        code, out, _log = _local(tmp_path, FixturePaperLog(tmp_path / "pl", SHA))
        assert code == executor.EXIT_PRECONDITION
        assert _payload(out)["run_state"] == "log-finding"

    def test_invalid_utf8_is_a_log_finding(self, tmp_path):
        source = _raw_paper(tmp_path, b"[2026-10-09 | AAPL | Buy | pending]\n\n\xff\xfe")
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        assert _payload(out)["run_state"] == "log-finding"

    def test_the_copy_is_byte_equal_with_the_blob(self, tmp_path):
        source = FixturePaperLog(FROZEN_DIR, FROZEN_SHA)
        _local(tmp_path, source)
        copy = tmp_path / "TradingEngineX" / "ibkr" / "paper-log" / "decision-log.md"
        assert copy.read_bytes() == (FROZEN_DIR / "decision-log.md").read_bytes()


class TestSchema:
    def test_an_unknown_schema_version_is_exit_1(self, tmp_path):
        source = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"), schema=2)},
        )
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_CONFIG
        assert _payload(out)["run_state"] == "summary-schema"

    def test_a_malformed_summary_is_exit_1(self, tmp_path):
        source = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": {"schema_version": 1, "trade_date": "2026-10-09"}},
        )
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_CONFIG
        assert _payload(out)["run_state"] == "summary-contract"


    def test_a_summary_dated_differently_from_its_path_is_exit_1(self, tmp_path):
        """WR-05: a copied summary must not stand in for another day's run."""
        source = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-08", ("AAPL", "ok", "Buy"))},
        )
        code, out, log = _local(tmp_path, source)
        assert code == executor.EXIT_CONFIG
        assert _payload(out)["run_state"] == "summary-contract"
        assert "does not match the path date" in _log_text(log)


class TestDivergence:
    def test_log_and_summary_disagree(self, tmp_path):
        source = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Sell"))},
        )
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        row = _rows(out)["AAPL"]
        assert row["state"] == "signal-divergence"
        assert row["rating"] == "Buy"
        assert "Buy" in row["detail"]
        assert "Sell" in row["detail"]


def _pre(tmp_path, entries, summaries, ticker="AAPL"):
    source = _RecordingLog(write_paper_log(tmp_path / "pl", entries, summaries), SHA)
    code, out, _log = _local(tmp_path, source, tickers=(ticker,))
    return code, _rows(out).get(ticker), source


class TestPreconditions:
    def test_review_rating(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-09", "AAPL", "REVIEW")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"))},
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "rating-review")

    def test_run_failed_for_the_log_date(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "failed", None), status="failed")},
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "run-not-ok")

    def test_newer_summary_with_a_failed_run(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-08", "AAPL", "Buy")],
            {
                "2026-10-08": _summary("2026-10-08", ("AAPL", "ok", "Buy")),
                "2026-10-09": _summary("2026-10-09", ("AAPL", "failed", None), status="failed"),
            },
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "run-not-ok")

    def test_newer_summary_with_a_null_signal(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-08", "AAPL", "Buy")],
            {
                "2026-10-08": _summary("2026-10-08", ("AAPL", "ok", "Buy")),
                "2026-10-09": _summary("2026-10-09", ("AAPL", "ok", None)),
            },
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "signal-null")

    def test_newer_summary_without_a_newer_log_entry(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-08", "AAPL", "Buy")],
            {
                "2026-10-08": _summary("2026-10-08", ("AAPL", "ok", "Buy")),
                "2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy")),
            },
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "log-missing-entry")

    def test_summary_file_is_missing(self, tmp_path):
        code, row, _s = _pre(tmp_path, [("2026-10-09", "AAPL", "Buy")], {})
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "summary-missing")

    def test_ticker_without_a_log_entry(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"))},
            ticker="MSFT",
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "no-decision")

    def test_the_newest_entry_per_ticker_wins(self, tmp_path):
        code, row, _s = _pre(
            tmp_path,
            [("2026-10-08", "AAPL", "Buy"), ("2026-10-09", "AAPL", "Hold")],
            {
                "2026-10-08": _summary("2026-10-08", ("AAPL", "ok", "Buy")),
                "2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Hold")),
            },
        )
        assert (code, row["state"]) == (executor.EXIT_PRECONDITION, "skipped-hold")
        assert row["trade_date"] == "2026-10-09"

    def test_only_log_and_summary_paths_are_read(self, tmp_path):
        _code, _row, source = _pre(
            tmp_path,
            [("2026-10-08", "AAPL", "Buy")],
            {
                "2026-10-08": _summary("2026-10-08", ("AAPL", "ok", "Buy")),
                "2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy")),
            },
        )
        assert source.paths
        for path in source.paths:
            assert path == "decision-log.md" or (
                path.startswith("runs/") and path.endswith("/summary.json")
            )


class TestFreshness:
    def test_a_decision_with_a_closed_session_in_between_is_stale(self, tmp_path):
        source = _paper(
            tmp_path,
            [("2026-10-06", "AAPL", "Buy")],
            {"2026-10-06": _summary("2026-10-06", ("AAPL", "ok", "Buy"))},
        )
        clock = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)
        code, out, _log = _local(tmp_path, source, clock=clock)
        assert code == executor.EXIT_PRECONDITION
        assert _rows(out)["AAPL"]["state"] == "stale-decision"

    def test_a_decision_of_today_is_a_future_decision(self, tmp_path):
        source = _paper(
            tmp_path,
            [("2026-10-12", "AAPL", "Buy")],
            {"2026-10-12": _summary("2026-10-12", ("AAPL", "ok", "Buy"))},
        )
        code, out, _log = _local(tmp_path, source)
        assert code == executor.EXIT_PRECONDITION
        assert _rows(out)["AAPL"]["state"] == "future-decision"

    def test_two_tickers_are_both_reported(self, tmp_path, capsys):
        source = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Hold"), ("2026-10-09", "MSFT", "Buy")],
            {
                "2026-10-09": _summary(
                    "2026-10-09", ("AAPL", "ok", "Hold"), ("MSFT", "ok", "Sell")
                )
            },
        )
        code, out, _log = _local(tmp_path, source, tickers=("AAPL", "MSFT"))
        assert code == executor.EXIT_PRECONDITION
        lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("preview: ")]
        assert len(lines) == 2
        rows = _rows(out)
        assert rows["AAPL"]["state"] == "skipped-hold"
        assert rows["MSFT"]["state"] == "signal-divergence"


# --- the gateway chain: resolution, position, open orders, target, whatIf, verdict ----

BUY_TEXT_HALT = "Order rejected - instrument is halted"


def _identity(ticker, con_id=None):
    return contracts_mod.Identity(
        CON_IDS[ticker] if con_id is None else con_id, "NASDAQ", "USD", ticker
    )


def _contracts_file(tmp_path, entries):
    """A valid contracts file; ``entries`` maps ticker to an Identity."""
    path = tmp_path / "ibkr" / "contracts.json"
    table = {
        t: contracts_mod.StoredContract(i, "2026-10-01T00:00:00+00:00") for t, i in entries.items()
    }
    contracts_mod.commit_contracts(path, table, ())
    return path


def _funds(available="100000", funds_currency="EUR", cash_currency="EUR"):
    return [
        ibkr_fakes.account_value("TotalCashValue", "100000", currency=cash_currency),
        ibkr_fakes.account_value("AvailableFunds", available, currency=funds_currency),
    ]


def _fake_for(tickers=("AAPL",), *, liquid_hours=OPEN_HOURS, funds=None, **kwargs):
    contracts = {t: ibkr_fakes.stk_contract(t, CON_IDS[t]) for t in tickers}
    kwargs.setdefault("whatif", ibkr_fakes.order_state(init="997.14"))
    return ibkr_fakes.FakeIB(
        qualify={t: [c] for t, c in contracts.items()},
        details={
            CON_IDS[t]: [ibkr_fakes.contract_detail(c, liquid_hours=liquid_hours)]
            for t, c in contracts.items()
        },
        summary=_funds() if funds is None else funds,
        **kwargs,
    )


def _aapl_position(quantity, con_id=None):
    return ibkr_fakes.position(
        "DUQ634065", "AAPL", quantity, conId=CON_IDS["AAPL"] if con_id is None else con_id
    )


def _gateway_run(
    tmp_path,
    loop,
    fake,
    *,
    rating="Buy",
    tickers=("AAPL",),
    paper=None,
    clock=OPEN_NOW,
    calendar=None,
    entries=None,
    factory=None,
):
    """Run ``preview`` against a fake gateway with a stored contract for each ticker."""
    paper = _buy_paper(tmp_path, rating) if paper is None else paper
    contracts = _contracts_file(
        tmp_path, {t: _identity(t) for t in tickers} if entries is None else entries
    )
    code, out, log, _c = _run_preview(
        tmp_path,
        _fake_factory(fake, loop) if factory is None else factory,
        list(tickers),
        paper_log=paper,
        clock=clock,
        calendar=calendar,
        contracts=contracts,
    )
    return code, out, log, contracts


def _assert_nothing_sent(fake, previews):
    """G2: only whatIf previews reached the client; no real order, no cancel, no market data."""
    for name in ("placeOrder", "cancelOrder", "whatIfOrder", "reqMktData", "reqTickers"):
        assert name not in fake.calls
    assert fake.calls.count("placeOrder(whatIf)") == previews


class TestBuyFlat:
    def test_buy_flat_previews_two_blocks(self, tmp_path, loop, capsys):
        fake = _fake_for()
        code, out, log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert "preview: AAPL preview-ok BUY 2" in capsys.readouterr().out
        data = _payload(out)
        assert data["sent"] is False
        row = _rows(out)["AAPL"]
        assert row["state"] == "preview-ok"
        assert row["intent"] == {"side": "BUY", "quantity": 2, "order_type": "MKT", "tif_sent": "DAY"}
        preview = row["preview"]
        assert preview["init_margin_change"] == 997.14
        assert preview["commission"] == 1.00003
        assert preview["commission_currency"] == "USD"
        assert preview["reject_reason"] == ""
        assert preview["effective_tif"] == "DAY"
        assert preview["tif_sent"] == "DAY"
        assert row["budget"] == {"available_funds": 100000.0, "currency": "EUR"}
        assert row["position"]["held"] == 0
        order = fake.whatif_calls[0][1]
        assert (order.action, order.totalQuantity, order.orderType, order.tif) == (
            "BUY",
            2,
            "MKT",
            "DAY",
        )
        assert f"sha={SHA}" in _log_text(log)
        _assert_nothing_sent(fake, 1)

    def test_the_contracts_file_stays_byte_equal(self, tmp_path, loop):
        fake = _fake_for()
        paper = _buy_paper(tmp_path)
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        before = path.read_bytes()
        code, _out, _log, _c = _run_preview(
            tmp_path,
            _fake_factory(fake, loop),
            ["AAPL"],
            paper_log=paper,
            contracts=path,
        )
        assert code == executor.EXIT_OK
        assert path.read_bytes() == before
        assert not contracts_mod.contracts_history_path(path).exists()


def _case_buy_flat():
    return "Buy", {}, 1


def _case_within_tolerance():
    return "Overweight", {"positions": [_aapl_position(1)]}, 0


def _case_foreign_open_order():
    return "Buy", {"open_orders": [ibkr_fakes.open_trade(CON_IDS["AAPL"])]}, 0


def _case_over_budget():
    return "Buy", {"funds": _funds(available="500")}, 1


def _case_halted():
    text = BUY_TEXT_HALT
    return "Buy", {"whatif": [], "emit_during": {"whatif": [(17, 154, text, None)]}}, 1


def _case_preview_empty():
    return "Buy", {"whatif": []}, 1


class TestNothingIsSent:
    @pytest.mark.parametrize(
        "case",
        [
            _case_buy_flat,
            _case_within_tolerance,
            _case_foreign_open_order,
            _case_over_budget,
            _case_halted,
            _case_preview_empty,
        ],
        ids=lambda f: f.__name__.removeprefix("_case_"),
    )
    def test_nothing_sent(self, tmp_path, loop, case):
        rating, kwargs, previews = case()
        fake = _fake_for(**kwargs)
        _gateway_run(tmp_path, loop, fake, rating=rating)
        _assert_nothing_sent(fake, previews)
        assert "reqMktData" not in fake.calls


class TestTargetCalculation:
    def test_within_tolerance_needs_no_preview(self, tmp_path, loop, capsys):
        fake = _fake_for(positions=[_aapl_position(1)])
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake, rating="Overweight")
        assert code == executor.EXIT_OK
        assert _rows(out)["AAPL"]["state"] == "within-tolerance"
        assert "whatif" not in fake.calls

    def test_a_foreign_open_order_stops_the_ticker(self, tmp_path, loop):
        fake = _fake_for(open_orders=[ibkr_fakes.open_trade(CON_IDS["AAPL"])])
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        row = _rows(out)["AAPL"]
        assert row["state"] == "foreign-open-order"
        assert len(row["open_orders"]) == 1
        assert "whatif" not in fake.calls

    def test_long_only_noop_for_a_sell_without_holding(self, tmp_path, loop):
        fake = _fake_for()
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake, rating="Sell")
        assert code == executor.EXIT_OK
        assert _rows(out)["AAPL"]["state"] == "long-only-noop"
        assert "whatif" not in fake.calls

    def test_a_sell_with_holding_previews_a_sale(self, tmp_path, loop, capsys):
        fake = _fake_for(positions=[_aapl_position(2)])
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake, rating="Sell")
        assert code == executor.EXIT_OK
        assert "preview: AAPL preview-ok SELL 2" in capsys.readouterr().out
        order = fake.whatif_calls[0][1]
        assert (order.action, order.totalQuantity) == ("SELL", 2)
        assert _rows(out)["AAPL"]["intent"]["side"] == "SELL"

    def test_a_fractional_position_is_its_own_state(self, tmp_path, loop):
        fake = _fake_for(positions=[_aapl_position(1.5)])
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        assert _rows(out)["AAPL"]["state"] == "fractional-position"

    def test_a_position_on_another_conid_is_reported_not_netted(self, tmp_path, loop):
        fake = _fake_for(positions=[_aapl_position(5, con_id=999)])
        code, out, log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        row = _rows(out)["AAPL"]
        assert row["intent"]["quantity"] == 2
        assert row["position"]["held"] == 0
        assert row["position"]["other_conid"] == [{"con_id": 999, "quantity": 5.0}]
        assert "ibkr-state=POSITION_OTHER_CONID" in _log_text(log)


class TestBudgetAndVerdict:
    def test_over_budget_is_exit_5(self, tmp_path, loop):
        fake = _fake_for(funds=_funds(available="500"))
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "over-budget"

    def test_funds_in_another_currency_are_a_mismatch(self, tmp_path, loop):
        fake = _fake_for(funds=_funds(funds_currency="USD", cash_currency="EUR"))
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "currency-mismatch"

    def test_an_empty_preview_is_exit_5(self, tmp_path, loop):
        fake = _fake_for(whatif=[])
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "preview-empty"

    def test_code_154_is_halted(self, tmp_path, loop):
        fake = _fake_for(whatif=[], emit_during={"whatif": [(17, 154, BUY_TEXT_HALT, None)]})
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "halted"

    def test_code_10349_is_tif_overridden(self, tmp_path, loop):
        fake = _fake_for(whatif=[], emit_during={"whatif": [(17, 10349, "TIF set to DAY", None)]})
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "tif-overridden"

    def test_a_missing_tif_echo_is_unconfirmed(self, tmp_path, loop):
        fake = _fake_for(whatif_echo_tif=None)
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert _rows(out)["AAPL"]["state"] == "tif-unconfirmed"

    def test_a_request_error_is_a_rejection_with_its_text(self, tmp_path, loop):
        text = "Order rejected - reason: insufficient permissions"
        fake = _fake_for(whatif=[], emit_during={"whatif": [(17, 201, text, None)]})
        code, out, log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        row = _rows(out)["AAPL"]
        assert row["state"] == "preview-rejected"
        assert text in row["preview"]["reject_reason"]
        assert f"rejectReason={text!r}" in _log_text(log) or text in _log_text(log)


class TestSessionAndCalendar:
    def test_a_closed_market_still_previews(self, tmp_path, loop, capsys):
        fake = _fake_for(liquid_hours=CLOSED_HOURS)
        clock = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake, clock=clock)
        assert code == executor.EXIT_OK
        row = _rows(out)["AAPL"]
        assert row["session"]["closed"] is True
        assert row["state"] == "preview-ok"
        assert "market closed" in capsys.readouterr().out
        assert fake.calls.count("placeOrder(whatIf)") == 1

    def test_an_open_market_is_not_marked_closed(self, tmp_path, loop):
        fake = _fake_for()
        _code, out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert _rows(out)["AAPL"]["session"]["closed"] is False

    def test_calendar_and_liquid_hours_disagree(self, tmp_path, loop):
        fake = _fake_for()
        calendar = _stub_calendar(holidays={date(2026, 10, 12)})
        code, out, _log, _c = _gateway_run(tmp_path, loop, fake, calendar=calendar)
        assert code == executor.EXIT_PRECONDITION
        assert _rows(out)["AAPL"]["state"] == "calendar-conflict"
        assert "whatif" not in fake.calls


class TestContracts:
    def test_a_broken_contract_table_is_exit_1_before_any_contact(self, tmp_path, monkeypatch):
        """WR-03: table_problems runs up front, not as a mid-window ValueError (exit 3)."""
        monkeypatch.setattr(executor, "load_contracts_module", lambda: contracts_mod)
        monkeypatch.setattr(
            contracts_mod, "table_problems", lambda *a: ("'AAPL': block_qty must be positive",)
        )
        paper = _buy_paper(tmp_path)
        factory = _RecordingFactory()
        code, out, log, _c = _run_preview(
            tmp_path, factory, ["AAPL"], paper_log=paper, contracts=_contracts_file(
                tmp_path, {"AAPL": _identity("AAPL")}
            )
        )
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert not Path(out).exists()
        assert "contract table" in _log_text(log)

    def test_a_ticker_without_a_stored_contract_is_not_resolved_yet(self, tmp_path):
        paper = _buy_paper(tmp_path, ticker="MSFT")
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        before = path.read_bytes()
        factory = _RecordingFactory()
        code, out, _log, _c = _run_preview(
            tmp_path, factory, ["MSFT"], paper_log=paper, contracts=path
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert _rows(out)["MSFT"]["state"] == "not-resolved-yet"
        assert path.read_bytes() == before
        assert not contracts_mod.contracts_history_path(path).exists()

    def test_a_missing_contracts_file_is_a_run_state(self, tmp_path):
        paper = _buy_paper(tmp_path)
        factory = _RecordingFactory()
        code, out, log, contracts = _run_preview(tmp_path, factory, ["AAPL"], paper_log=paper)
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert _payload(out)["run_state"] == "CONTRACTS_MISSING"
        assert "ibkr-state=CONTRACTS_MISSING" in _log_text(log)
        assert "resolve --init" in _log_text(log)
        assert not contracts.exists()

    def test_an_invalid_contracts_file_is_exit_1(self, tmp_path):
        paper = _buy_paper(tmp_path)
        path = tmp_path / "ibkr" / "contracts.json"
        path.parent.mkdir(parents=True)
        path.write_text("not json at all", encoding="utf-8")
        factory = _RecordingFactory()
        code, _out, log, _c = _run_preview(
            tmp_path, factory, ["AAPL"], paper_log=paper, contracts=path
        )
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert path.read_text(encoding="utf-8") == "not json at all"
        assert "CONFIG_INVALID" in _log_text(log)

    def test_a_resolve_rejection_keeps_its_phase_3_state(self, tmp_path, loop):
        fake = _fake_for()
        wrong = _identity("AAPL", con_id=111)
        code, out, _log, contracts = _gateway_run(
            tmp_path, loop, fake, entries={"AAPL": wrong}
        )
        before = contracts.read_bytes()
        assert code == executor.EXIT_PRECONDITION
        row = _rows(out)["AAPL"]
        assert row["state"] == "drift"
        assert row["exit"] == executor.EXIT_PRECONDITION
        assert "whatif" not in fake.calls
        assert contracts.read_bytes() == before


class TestSeveralTickers:
    def test_the_heaviest_exit_wins(self, tmp_path, loop):
        paper = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy"), ("2026-10-09", "MSFT", "Hold")],
            {
                "2026-10-09": _summary(
                    "2026-10-09", ("AAPL", "ok", "Buy"), ("MSFT", "ok", "Hold")
                )
            },
        )
        fake = _fake_for(funds=_funds(available="500"))
        code, out, _log, _c = _gateway_run(
            tmp_path,
            loop,
            fake,
            tickers=("AAPL", "MSFT"),
            paper=paper,
            entries={"AAPL": _identity("AAPL"), "MSFT": _identity("MSFT")},
        )
        assert code == executor.EXIT_REJECTED
        rows = _rows(out)
        assert rows["AAPL"]["state"] == "over-budget"
        assert rows["MSFT"]["state"] == "skipped-hold"
        _assert_nothing_sent(fake, 1)

    def test_every_ticker_is_processed(self, tmp_path, loop):
        paper = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy"), ("2026-10-09", "MSFT", "Buy")],
            {
                "2026-10-09": _summary(
                    "2026-10-09", ("AAPL", "ok", "Buy"), ("MSFT", "ok", "Buy")
                )
            },
        )
        fake = _fake_for(tickers=("AAPL", "MSFT"))
        code, out, _log, _c = _gateway_run(
            tmp_path, loop, fake, tickers=("AAPL", "MSFT"), paper=paper
        )
        assert code == executor.EXIT_OK
        assert {r["state"] for r in _payload(out)["rows"]} == {"preview-ok"}
        assert fake.calls.count("placeOrder(whatIf)") == 2
        assert fake.calls.count("connect") == 1


class TestBarrierAndGateway:
    def test_a_read_only_violation_is_never_swallowed(self, tmp_path, loop):
        fake = _fake_for()

        def factory(host, port, logger):
            adapter = _fake_factory(fake, loop)(host, port, logger)

            def refuse(**_kwargs):
                raise broker.ReadOnlyViolation("order refused by the barrier")

            adapter.preview_order = refuse
            return adapter

        code, _out, log, _c = _gateway_run(tmp_path, loop, fake, factory=factory)
        assert code == executor.EXIT_GATEWAY
        assert "WRITE_REFUSED" in _log_text(log)

    def test_an_unreachable_gateway_is_exit_3(self, tmp_path, loop):
        fake = _fake_for()
        fake.refuse = ConnectionRefusedError("refused")
        code, _out, _log, _c = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_GATEWAY
        assert "whatif" not in fake.calls

    def test_the_executor_knows_no_write_call(self):
        source = _SCRIPT.read_text(encoding="utf-8")
        for name in ("placeOrder", "cancelOrder", "reqMktData", "reqTickers"):
            assert name not in source
        assert source.count("commit_contracts") == 1
