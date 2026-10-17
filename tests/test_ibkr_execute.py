"""The ``execute`` command of the IBKR executor: forced dry, against fakes only.

Every path comes from ``tmp_path`` (``LOCALAPPDATA`` is pinned there, so the state folder
with the release file, the kill file and the ledgers is a temp folder); nothing here reads the
operator's ``.env`` or reaches the gateway. The paper-log is a directory, the session
calendar a weekday stub, the gateway a ``FakeIB``. Phase 5 sends no order: every test that
reaches the gateway also checks that nothing but a whatIf preview reached the client.
"""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import ibkr_fakes, paper_log_fixture
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
paperlog = paper_log_fixture._pl
guards = executor.load_guards_module()
ledger_mod = executor.load_ledger_module()

DEFAULT_ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_ACCOUNT_ID": "DUQ634065",
    "IBKR_TRADING_MODE": "paper",
}

#: A Monday, 13:20 US/Eastern: inside the regular session (Columbus Day, NYSE open).
OPEN_NOW = datetime(2026, 10, 12, 17, 20, tzinfo=UTC)
OPEN_HOURS = "20261012:0930-20261012:1600"

CON_IDS = {"AAPL": 265598, "MSFT": 272093, "NVDA": 4815747}
SHA = "a" * 40
KEY = "2026-10-09|AAPL"


@pytest.fixture(scope="session")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _pin_modules(monkeypatch):
    """Hand the executor this file's module instances, whatever ``sys.modules`` holds."""
    monkeypatch.setattr(executor, "load_decision_module", lambda: decision)
    monkeypatch.setattr(executor, "load_paperlog_module", lambda: paperlog)
    monkeypatch.setattr(executor, "load_guards_module", lambda: guards)
    monkeypatch.setattr(executor, "load_ledger_module", lambda: ledger_mod)


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


def _log_file(tmp_path):
    return tmp_path / "logs" / "executor.log"


def _log_text(tmp_path):
    return _log_file(tmp_path).read_text(encoding="utf-8")


def _read_records(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _run_execute(
    tmp_path,
    factory,
    tickers,
    *,
    paper_log,
    placer=None,
    clock=OPEN_NOW,
    calendar=None,
    release=True,
    kill=False,
    contracts=None,
    extra=(),
):
    """Run ``main(["execute", ...])``; returns (exit code, dry-run ledger records).

    The release file is dated relative to the injected clock, never to the real date, so a
    fixed clock never meets ``release-expired``.
    """
    env_file = _env_file(tmp_path)
    contracts = tmp_path / "ibkr" / "contracts.json" if contracts is None else contracts
    if release:
        path = executor.default_release_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        until = (clock.date() + timedelta(days=30)).isoformat()
        path.write_text(json.dumps({"account": "DUQ634065", "valid_until": until}), "utf-8")
    if kill:
        path = executor.default_kill_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stop", encoding="utf-8")
    argv = [
        "execute",
        *tickers,
        "--contracts",
        str(contracts),
        "--env-file",
        str(env_file),
        "--log-file",
        str(_log_file(tmp_path)),
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
        placer=placer,
    )
    executor.close_logging()
    return code, _read_records(executor.default_dryrun_ledger_file())


def _assert_nothing_sent(fake, previews=None):
    """Only whatIf previews reached the client: no real order, no cancel, no market data."""
    for name in ("placeOrder", "cancelOrder", "whatIfOrder", "reqGlobalCancel", "reqMktData"):
        assert name not in fake.calls
    if previews is not None:
        assert fake.calls.count("placeOrder(whatIf)") == previews


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


def _events(records, name):
    return [r for r in records if r["event"] == name]


# --- wiring: arguments, paths, forced dry, state folder (D-07, D-08, REQ-46) ----------------


class TestWiring:
    def test_usage_lists_execute(self, capsys):
        assert executor.main([], broker_factory=_RecordingFactory()) == executor.EXIT_CONFIG
        assert "account, resolve, preview, execute" in capsys.readouterr().err

    def test_execute_needs_a_ticker(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path, factory, [], paper_log=FixturePaperLog.unavailable("x")
        )
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert records == []
        assert "execute needs at least one TICKER (no default list)" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--live", "--wet", "--real", "--force"])
    def test_there_is_no_option_that_lifts_the_dry_run(self, tmp_path, flag):
        factory = _PaperLogFactory(FixturePaperLog.unavailable("x"))
        code, records = _run_execute(
            tmp_path, _RecordingFactory(), ["AAPL"], paper_log=factory, extra=[flag]
        )
        assert code == executor.EXIT_CONFIG
        assert factory.calls == []
        assert records == []

    def test_default_state_paths(self):
        env = {"LOCALAPPDATA": "X"}
        base = Path("X/TradingEngineX/ibkr")
        assert executor.default_dryrun_ledger_file(env) == base / "ledger-dryrun.jsonl"
        assert executor.default_ledger_file(env) == base / "ledger.jsonl"
        assert executor.default_release_file(env) == base / "RELEASE"
        assert executor.default_kill_file(env) == base / "KILL"

    def test_the_loaders_register_their_modules(self):
        import sys

        assert sys.modules["ibkr_guards"] is guards
        assert sys.modules["ibkr_ledger"] is ledger_mod

    def test_forced_dry_refuses_a_live_placer(self, tmp_path):
        """Negative control: a placer that is not dry ends the run before any file is touched."""
        completed = []
        placer = SimpleNamespace(dry=False, complete=lambda ctx, intent: completed.append(intent))
        factory = _RecordingFactory()
        pl_factory = _PaperLogFactory(_buy_paper(tmp_path))
        code, records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=pl_factory, placer=placer
        )
        assert code == executor.EXIT_CONFIG
        assert "ibkr-state=NOT_DRY" in _log_text(tmp_path)
        assert records == []
        assert not executor.default_dryrun_ledger_file().exists()
        assert not executor.default_ledger_file().exists()
        assert factory.calls == []
        assert pl_factory.calls == []
        assert completed == []

    def test_a_placer_without_the_dry_flag_is_refused(self, tmp_path):
        placer = SimpleNamespace(complete=lambda ctx, intent: "dry-complete")
        code, _records = _run_execute(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            placer=placer,
        )
        assert code == executor.EXIT_CONFIG
        assert "ibkr-state=NOT_DRY" in _log_text(tmp_path)

    def test_state_in_git_tree_negative_control(self, tmp_path, monkeypatch):
        work = tmp_path / "work"
        (work / ".git").mkdir(parents=True)
        monkeypatch.setenv("LOCALAPPDATA", str(work / "appdata"))
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path), release=False
        )
        assert code == executor.EXIT_CONFIG
        assert "ibkr-state=STATE_IN_GIT_TREE" in _log_text(tmp_path)
        assert records == []
        assert not (work / "appdata").exists()
        assert factory.calls == []

    def test_guards_exit_literals_match_executor_constants(self):
        names = (
            "EXIT_OK",
            "EXIT_CONFIG",
            "EXIT_PRECONDITION",
            "EXIT_GATEWAY",
            "EXIT_KILL_SWITCH",
            "EXIT_REJECTED",
            "EXIT_RECONCILE",
            "EXIT_LOCKED",
            "EXIT_ACCOUNT_GUARD",
        )
        constants = {getattr(executor, name) for name in names}
        assert set(guards.EXIT_BY_STATE.values()) <= constants
        assert guards._EXIT_OK == executor.EXIT_OK
        assert guards._EXIT_CONFIG == executor.EXIT_CONFIG
        assert guards._EXIT_PRECONDITION == executor.EXIT_PRECONDITION
        assert guards._EXIT_GATEWAY == executor.EXIT_GATEWAY
        assert guards._EXIT_KILL_SWITCH == executor.EXIT_KILL_SWITCH
        assert guards._EXIT_REJECTED == executor.EXIT_REJECTED
        assert guards._EXIT_RECONCILE == executor.EXIT_RECONCILE
        assert guards._EXIT_LOCKED == executor.EXIT_LOCKED
        assert guards._EXIT_ACCOUNT_GUARD == executor.EXIT_ACCOUNT_GUARD


# --- the dry-run ledger and the local chain ---------------------------------------------------


class TestDryrunLedger:
    def test_dryrun_ledger_only(self, tmp_path, capsys):
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path, rating="Hold")
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert not executor.default_ledger_file().exists()
        start = _events(records, "run_start")[0]
        assert start["mode"] == "dryrun"
        assert start["command"] == "execute"
        assert start["tickers"] == ["AAPL"]
        assert start["run_id"]
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "hold"
        assert skipped["state"] == "skipped-hold"
        assert skipped["decision_key"] == KEY
        assert skipped["paper_log_sha"] == SHA
        assert skipped["ticker"] == "AAPL"
        end = _events(records, "run_end")[-1]
        assert end["exit"] == 2
        assert records[-1] is end
        assert {r["run_id"] for r in records} == {start["run_id"]}
        assert "execute: AAPL skipped-hold" in capsys.readouterr().out
        assert "ibkr-state=EXECUTE ticker=AAPL state=skipped-hold" in _log_text(tmp_path)

    def test_a_second_run_appends_to_the_same_dryrun_ledger(self, tmp_path):
        paper = _buy_paper(tmp_path, rating="Hold")
        _run_execute(tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper)
        _code, records = _run_execute(tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper)
        assert len(_events(records, "run_start")) == 2
        assert len({r["run_id"] for r in records}) == 2

    def test_ledger_corrupt_is_exit_six(self, tmp_path):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        good = {"v": 1, "seq": 1, "mode": "dryrun", "event": "run_start"}
        path.write_text(
            json.dumps(good) + "\nthis is not json\n" + json.dumps({**good, "seq": 3}) + "\n",
            encoding="utf-8",
        )
        factory = _RecordingFactory()
        code, _records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path), release=False
        )
        assert code == executor.EXIT_RECONCILE
        assert "ibkr-state=LEDGER_CORRUPT" in _log_text(tmp_path)
        assert factory.calls == []

    def test_a_live_mode_line_in_the_dryrun_ledger_is_exit_six(self, tmp_path):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        line = {"v": 1, "seq": 1, "mode": "live", "event": "run_start"}
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        factory = _RecordingFactory()
        code, _records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path), release=False
        )
        assert code == executor.EXIT_RECONCILE
        assert "ibkr-state=LEDGER_CORRUPT" in _log_text(tmp_path)
        assert factory.calls == []

    def test_a_run_abort_closes_the_ledger_with_its_state(self, tmp_path):
        paper = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"), schema=2)},
        )
        code, records = _run_execute(tmp_path, _RecordingFactory(), ["AAPL"], paper_log=paper)
        assert code == executor.EXIT_CONFIG
        end = _events(records, "run_end")[-1]
        assert end["state"] == "summary-schema"
        assert end["exit"] == executor.EXIT_CONFIG
        assert not executor.default_preview_file().exists()

    def test_a_paper_log_outage_closes_the_ledger_with_its_state(self, tmp_path):
        code, records = _run_execute(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=FixturePaperLog.unavailable("offline"),
        )
        assert code == executor.EXIT_PRECONDITION
        assert _events(records, "run_end")[-1]["state"] == "paper-log-unavailable"
        assert not executor.default_preview_file().exists()

    def test_an_unexpected_error_after_run_start_is_recorded(self, tmp_path, monkeypatch):
        def boom(ctx, source, tickers):
            raise RuntimeError("boom")

        monkeypatch.setattr(executor, "_local_chain", boom)
        code, records = _run_execute(
            tmp_path, _RecordingFactory(), ["AAPL"], paper_log=_buy_paper(tmp_path)
        )
        assert code != executor.EXIT_OK
        end = _events(records, "run_end")[-1]
        assert end["outcome"] == "error"
        assert end["error"] == "RuntimeError"
        assert "ibkr-state=UNEXPECTED RuntimeError" in _log_text(tmp_path)


class TestReasonFallback:
    def _ctx(self, tmp_path):
        mods = SimpleNamespace(
            decision=decision, guards=guards, ledger=ledger_mod, contracts=contracts_mod
        )
        import logging

        ledger = ledger_mod.Ledger.open(
            tmp_path / "ledger-dryrun.jsonl",
            mode=ledger_mod.MODE_DRYRUN,
            clock=lambda: OPEN_NOW,
            run_id="r1",
        )
        return SimpleNamespace(
            mods=mods,
            logger=logging.getLogger("test-fallback"),
            sha=SHA,
            ledger=ledger,
            label="execute",
            on_row_finished=executor._ledger_row_finished,
        )

    def test_ledger_reason_fallback_for_unmapped_state_records_and_continues(
        self, tmp_path, caplog
    ):
        ctx = self._ctx(tmp_path)
        row = executor._new_row("AAPL")
        row["trade_date"] = "2026-10-09"
        with caplog.at_level("WARNING", logger="test-fallback"):
            executor._finish_row(ctx, row, "totally-new-state", "a state nobody mapped")
        (record,) = _events(ctx.ledger.records, "skipped")
        assert record["reason"] == "review"
        assert record["unmapped_state"] is True
        assert record["state"] == "totally-new-state"
        assert record["decision_key"] == KEY
        assert "ibkr-state=LEDGER_REASON_UNMAPPED state=totally-new-state" in caplog.text
        assert row["exit"] == executor.EXIT_PRECONDITION

    def test_a_verdict_state_becomes_a_rejected_event(self, tmp_path):
        ctx = self._ctx(tmp_path)
        row = executor._new_row("AAPL")
        row["trade_date"] = "2026-10-09"
        executor._finish_row(ctx, row, "over-budget", "no funds")
        (record,) = _events(ctx.ledger.records, "rejected")
        assert record["state"] == "over-budget"
        assert record["decision_key"] == KEY
        assert row["exit"] == executor.EXIT_REJECTED

    def test_a_row_without_a_trade_date_has_no_decision_key(self, tmp_path):
        ctx = self._ctx(tmp_path)
        row = executor._new_row("AAPL")
        executor._finish_row(ctx, row, "no-decision", "no entry")
        (record,) = _events(ctx.ledger.records, "skipped")
        assert record["reason"] == "review"
        assert "decision_key" not in record
        assert "unmapped_state" not in record
