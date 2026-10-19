"""The ``execute`` command of the IBKR executor: forced dry, against fakes only.

Every path comes from ``tmp_path`` (``LOCALAPPDATA`` is pinned there, so the state folder
with the release file, the kill file and the ledgers is a temp folder); nothing here reads the
operator's ``.env`` or reaches the gateway. The paper-log is a directory, the session
calendar a weekday stub, the gateway a ``FakeIB``. Phase 5 sends no order: every test that
reaches the gateway also checks that nothing but a whatIf preview reached the client.
"""

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

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
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue  # a deliberately broken line of a corruption test
    return records


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
    # ``clock`` is a moment (fixed clock) or a callable (a clock that moves during the run).
    clock_fn = clock if callable(clock) else _fixed(clock)
    if release:
        path = executor.default_release_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        until = (clock_fn().date() + timedelta(days=30)).isoformat()
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
        clock=clock_fn,
        paper_log_factory=paper_log_factory,
        calendar=_stub_calendar() if calendar is None else calendar,
        placer=placer,
    )
    executor.close_logging()
    ledger_file = (
        executor.default_ledger_file()
        if "--live" in extra
        else executor.default_dryrun_ledger_file()
    )
    return code, _read_records(ledger_file)


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

    @pytest.mark.parametrize("flag", ["--wet", "--real", "--force"])
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
        # Other test files may have registered their own instance under the same name.
        assert Path(guards.__file__).name == "ibkr_guards.py"
        assert Path(ledger_mod.__file__).name == "ibkr_ledger.py"
        assert executor._GUARDS_PATH.name == "ibkr_guards.py"
        assert executor._LEDGER_PATH.name == "ibkr_ledger.py"

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
            "EXIT_FILL_TIMEOUT",
            "EXIT_POST_ORDER",
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
        assert guards._EXIT_FILL_TIMEOUT == executor.EXIT_FILL_TIMEOUT == 9
        assert guards._EXIT_POST_ORDER == executor.EXIT_POST_ORDER == 10


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
        code, _records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path))
        assert code == executor.EXIT_RECONCILE
        assert "ibkr-state=LEDGER_CORRUPT" in _log_text(tmp_path)
        assert factory.calls == []

    def test_a_live_mode_line_in_the_dryrun_ledger_is_exit_six(self, tmp_path):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        line = {"v": 1, "seq": 1, "mode": "live", "event": "run_start"}
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        factory = _RecordingFactory()
        code, _records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path))
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


# --- the gateway chain: resolution, position, target, whatIf with orderRef, intent -------------

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
    placer=None,
    release=True,
    kill=False,
):
    """Run ``execute`` against a fake gateway with a stored contract for each ticker."""
    paper = _buy_paper(tmp_path, rating) if paper is None else paper
    contracts = _contracts_file(tmp_path, {t: _identity(t) for t in tickers})
    return _run_execute(
        tmp_path,
        _fake_factory(fake, loop),
        list(tickers),
        paper_log=paper,
        clock=clock,
        calendar=calendar,
        contracts=contracts,
        placer=placer,
        release=release,
        kill=kill,
    )


def _live_run(
    tmp_path,
    loop,
    fake,
    *,
    rating="Buy",
    tickers=("AAPL",),
    paper=None,
    clock=OPEN_NOW,
    calendar=None,
    placer=None,
    release=True,
    kill=False,
    extra_argv=(),
):
    """Like ``_gateway_run`` with ``--live``; returns (exit code, ``ledger.jsonl`` records)."""
    paper = _buy_paper(tmp_path, rating) if paper is None else paper
    contracts = _contracts_file(tmp_path, {t: _identity(t) for t in tickers})
    return _run_execute(
        tmp_path,
        _fake_factory(fake, loop),
        list(tickers),
        paper_log=paper,
        clock=clock,
        calendar=calendar,
        contracts=contracts,
        placer=placer,
        release=release,
        kill=kill,
        extra=("--live", *extra_argv),
    )


def _half_writing_open(fails):
    """An ``open`` for the ledger: a write for which ``fails(data)`` holds lands only halfway
    and raises a full-disk error, like a write cut off on a full or network drive."""
    import builtins

    def ledger_open(path, mode):
        real = builtins.open(path, mode)  # noqa: SIM115 - closed by the handle's __exit__

        class Handle:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                real.close()
                return False

            def write(self, data):
                if fails(data):
                    real.write(data[: len(data) // 2])
                    real.flush()
                    raise OSError(28, "No space left on device")
                return real.write(data)

            def flush(self):
                real.flush()

            def fileno(self):
                return real.fileno()

        return Handle()

    return ledger_open


class TestOrderRefAndIntent:
    def test_order_ref_is_decision_key(self, tmp_path, loop, capsys):
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        order = fake.whatif_calls[-1][1]
        assert order.orderRef == KEY
        (intent,) = _events(records, "intent")
        assert intent["decision_key"] == KEY
        assert intent["order_ref"] == KEY
        assert intent["paper_log_sha"] == SHA
        assert intent["side"] == "BUY"
        assert intent["quantity"] == 2
        assert intent["con_id"] == CON_IDS["AAPL"]
        assert intent["rating"] == "Buy"
        assert intent["trade_date"] == "2026-10-09"
        assert isinstance(intent["weekend_gap"], bool)
        assert intent["rating_source"] == "engine"
        (done,) = _events(records, "dry_complete")
        assert done["decision_key"] == KEY
        assert done["seq"] > intent["seq"]
        assert "execute: AAPL dry-complete BUY 2" in capsys.readouterr().out
        text = _log_text(tmp_path)
        assert f"ibkr-state=EXECUTE_INTENT ticker=AAPL key={KEY} sha={SHA}" in text
        assert not executor.default_ledger_file().exists()
        _assert_nothing_sent(fake, 1)

    def test_the_run_is_framed_by_run_start_and_run_end(self, tmp_path, loop):
        _code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert [r["event"] for r in records] == [
            "run_start",
            "switch_check",
            "intent",
            "dry_complete",
            "run_end",
        ]
        assert records[-1]["exit"] == executor.EXIT_OK

    def test_write_ahead_intent_before_placer_complete(self, tmp_path, loop):
        seen = []

        class ReadingPlacer(executor.DryPlacer):
            def complete(self, ctx, intent):
                seen.append(_read_records(executor.default_dryrun_ledger_file()))
                return super().complete(ctx, intent)

        code, _records = _gateway_run(tmp_path, loop, _fake_for(), placer=ReadingPlacer())
        assert code == executor.EXIT_OK
        (on_disk,) = seen
        assert [r["event"] for r in on_disk] == ["run_start", "switch_check", "intent"]
        assert on_disk[-1]["decision_key"] == KEY

    def test_write_ahead_negative_control_a_failing_placer_leaves_the_intent_open(
        self, tmp_path, loop
    ):
        class FailingPlacer:
            dry = True

            def complete(self, ctx, intent):
                raise RuntimeError("placer failed")

        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake, placer=FailingPlacer())
        assert code != executor.EXIT_OK
        assert len(_events(records, "intent")) == 1
        assert _events(records, "dry_complete") == []
        end = _events(records, "run_end")[-1]
        assert end["outcome"] == "error"
        assert end["error"] == "RuntimeError"
        _assert_nothing_sent(fake, 1)

    def test_a_half_written_intent_does_not_corrupt_the_ledger(self, tmp_path, loop, monkeypatch):
        """WR-01: the error path's run_end seals the cut-off intent line; the next run reads it."""
        armed = [True]

        def fails(data):
            if armed[0] and b'"event":"intent"' in data:
                armed[0] = False
                return True
            return False

        monkeypatch.setattr(ledger_mod, "open", _half_writing_open(fails), raising=False)
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code != executor.EXIT_OK
        end = _events(records, "run_end")[-1]
        assert end["outcome"] == "error"
        assert end["error"] == "OSError"
        lines = executor.default_dryrun_ledger_file().read_bytes().split(b"\n")
        cut = lines[end[ledger_mod.SEALS_LINE] - 1]
        assert b'"event":"intent"' in cut  # the seal names the cut-off intent line
        with pytest.raises(ValueError):
            json.loads(cut)
        assert _events(records, "intent") == []
        assert _events(records, "dry_complete") == []
        # The next run (the failing write is used up) reads the ledger and goes through.
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        assert "ibkr-state=LEDGER_CORRUPT" not in _log_text(tmp_path)
        assert len(_events(records, "intent")) == 1

    def test_a_run_end_that_cannot_be_written_is_refused_cleanly(self, tmp_path, loop, monkeypatch):
        """WR-01: the disk stays full; the error path logs the failed run_end, keeps the cause."""

        def fails(data):
            return b'"event":"intent"' in data or b'"event":"run_end"' in data

        monkeypatch.setattr(ledger_mod, "open", _half_writing_open(fails), raising=False)
        code, _records = _gateway_run(tmp_path, loop, _fake_for())
        assert code != executor.EXIT_OK
        text = _log_text(tmp_path)
        assert "ibkr-state=LEDGER_APPEND_FAILED event=run_end" in text
        assert "ibkr-state=UNEXPECTED OSError" in text

    def test_the_second_size_check_runs_before_the_intent_line(self, tmp_path, loop, monkeypatch):
        """WR-02: the last size check comes before the write-ahead line, never after it."""
        seen = []
        real = guards.check_size

        def recording(quantity):
            on_disk = _read_records(executor.default_dryrun_ledger_file())
            seen.append([r["event"] for r in on_disk])
            return real(quantity)

        monkeypatch.setattr(guards, "check_size", recording)
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        assert len(seen) == 2
        assert "intent" not in seen[-1]
        assert seen[-1][-1] == "switch_check"
        assert len(_events(records, "intent")) == 1


def _case_buy_flat():
    return "Buy", {}, 1


def _case_within_tolerance():
    return "Overweight", {"positions": [_aapl_position(1)]}, 0


def _case_foreign_open_order():
    return "Buy", {"open_orders": [ibkr_fakes.open_trade(CON_IDS["AAPL"])]}, 0


def _case_over_budget():
    return "Buy", {"funds": _funds(available="500")}, 1


def _case_halted():
    return "Buy", {"whatif": [], "emit_during": {"whatif": [(17, 154, BUY_TEXT_HALT, None)]}}, 1


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
    def test_nothing_sent_forced_dry(self, tmp_path, loop, case):
        rating, kwargs, previews = case()
        fake = _fake_for(**kwargs)
        _gateway_run(tmp_path, loop, fake, rating=rating)
        _assert_nothing_sent(fake, previews)
        assert not executor.default_ledger_file().exists()
        assert executor.default_dryrun_ledger_file().exists()


class TestTickerEnds:
    def test_over_budget_is_rejected_with_exit_5(self, tmp_path, loop):
        fake = _fake_for(funds=_funds(available="500"))
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        (rejected,) = _events(records, "rejected")
        assert rejected["state"] == "over-budget"
        assert rejected["decision_key"] == KEY
        assert _events(records, "intent") == []
        assert _events(records, "run_end")[-1]["exit"] == executor.EXIT_REJECTED

    def test_halted_is_rejected_not_skipped(self, tmp_path, loop):
        fake = _fake_for(whatif=[], emit_during={"whatif": [(17, 154, BUY_TEXT_HALT, None)]})
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        assert [r["state"] for r in _events(records, "rejected")] == ["halted"]
        assert _events(records, "skipped") == []

    def test_within_tolerance_is_skipped_with_exit_0(self, tmp_path, loop):
        fake = _fake_for(positions=[_aapl_position(1)])
        code, records = _gateway_run(tmp_path, loop, fake, rating="Overweight")
        assert code == executor.EXIT_OK
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "tolerance"
        assert skipped["state"] == "within-tolerance"
        assert "whatif" not in fake.calls
        assert _events(records, "intent") == []

    def test_a_foreign_open_order_is_skipped_with_exit_2(self, tmp_path, loop):
        fake = _fake_for(open_orders=[ibkr_fakes.open_trade(CON_IDS["AAPL"])])
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "foreign_open_order"
        assert "whatif" not in fake.calls

    def test_calendar_conflict_is_a_source_conflict(self, tmp_path, loop):
        fake = _fake_for()
        calendar = _stub_calendar(holidays={date(2026, 10, 12)})
        code, records = _gateway_run(tmp_path, loop, fake, calendar=calendar)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "source_conflict"
        assert skipped["state"] == "calendar-conflict"
        assert "whatif" not in fake.calls

    def test_a_ticker_without_a_stored_contract_is_skipped_not_tradable(self, tmp_path):
        paper = _buy_paper(tmp_path, ticker="MSFT")
        contracts = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path, factory, ["MSFT"], paper_log=paper, contracts=contracts
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "not_tradable"
        assert skipped["state"] == "not-resolved-yet"

    @pytest.mark.parametrize("symbol", ["^GSPC", "XAUUSD+"])
    def test_a_ticker_without_a_valid_decision_key_stops_only_itself(
        self, tmp_path, loop, capsys, symbol
    ):
        """CR-02: a contract-table symbol outside the key whitelist must not crash the run."""
        paper = _paper(
            tmp_path,
            [("2026-10-09", symbol, "Buy"), ("2026-10-09", "AAPL", "Buy")],
            {"2026-10-09": _summary("2026-10-09", (symbol, "ok", "Buy"), ("AAPL", "ok", "Buy"))},
        )
        contracts = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        fake = _fake_for()
        code, records = _run_execute(
            tmp_path,
            _fake_factory(fake, loop),
            [symbol, "AAPL"],
            paper_log=paper,
            contracts=contracts,
        )
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["ticker"] == symbol
        assert skipped["state"] == guards.INVALID_DECISION_KEY
        assert skipped["reason"] == "not_tradable"
        assert "decision_key" not in skipped
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL"]
        assert len(_events(records, "dry_complete")) == 1
        end = _events(records, "run_end")[-1]
        assert end["exit"] == executor.EXIT_PRECONDITION
        assert "outcome" not in end
        assert f"execute: {symbol} invalid-decision-key" in capsys.readouterr().out
        assert "UNEXPECTED" not in _log_text(tmp_path)

    def test_a_missing_contracts_file_closes_the_run_with_its_state(self, tmp_path):
        factory = _RecordingFactory()
        code, records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path))
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert _events(records, "run_end")[-1]["state"] == "CONTRACTS_MISSING"


class TestSessions:
    def test_two_tickers_share_one_broker_session(self, tmp_path, loop):
        paper = _paper(
            tmp_path,
            [("2026-10-09", "AAPL", "Buy"), ("2026-10-09", "MSFT", "Hold")],
            {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"), ("MSFT", "ok", "Hold"))},
        )
        fake = _fake_for(tickers=("AAPL", "MSFT"))
        code, records = _gateway_run(tmp_path, loop, fake, tickers=("AAPL", "MSFT"), paper=paper)
        assert code == executor.EXIT_PRECONDITION
        assert fake.calls.count("connect") == 1
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL"]
        assert [r["ticker"] for r in _events(records, "skipped")] == ["MSFT"]
        _assert_nothing_sent(fake, 1)

    def test_an_unreachable_gateway_is_exit_3_and_the_ledger_records_the_error(
        self, tmp_path, loop
    ):
        fake = _fake_for()
        fake.refuse = ConnectionRefusedError("refused")
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_GATEWAY
        assert _events(records, "run_end")[-1]["outcome"] == "error"
        assert _events(records, "intent") == []
        assert "whatif" not in fake.calls

    def test_a_hold_only_run_opens_no_session(self, tmp_path):
        factory = _RecordingFactory()
        code, _records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path, rating="Hold")
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []

    def test_the_executor_source_knows_no_write_call(self):
        source = _SCRIPT.read_text(encoding="utf-8")
        for name in ("placeOrder", "cancelOrder", "whatIfOrder", "reqMktData", "reqTickers"):
            assert name not in source


# --- the run lock, the release and kill files, fail closed (05-05, Task 1) -----------------------


def _write_release(clock=OPEN_NOW, *, account="DUQ634065", days=30, raw=None):
    path = executor.default_release_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_bytes(raw)
        return
    until = (clock.date() + timedelta(days=days)).isoformat()
    path.write_text(json.dumps({"account": account, "valid_until": until}), "utf-8")


def _kill_stat_fails(monkeypatch):
    """``os.stat`` raises for the KILL path only; every other path goes to the original."""
    import os

    real = os.stat

    def stat(path, *args, **kwargs):
        if isinstance(path, str | os.PathLike) and os.fspath(path).endswith("KILL"):
            raise PermissionError("denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat)


def _setup_release_missing(monkeypatch):
    return "release-missing"


def _setup_release_unreadable(monkeypatch):
    executor.default_release_file().mkdir(parents=True)
    return "release-unreadable"


def _setup_release_utf16(monkeypatch):
    text = json.dumps({"account": "DUQ634065", "valid_until": "2026-11-01"})
    _write_release(raw=text.encode("utf-16"))
    return "release-invalid"


def _setup_release_expired(monkeypatch):
    _write_release(days=-1)
    return "release-expired"


def _setup_release_too_long(monkeypatch):
    _write_release(days=91)
    return "release-invalid"


def _setup_release_wrong_account(monkeypatch):
    _write_release(account="DUX000000")
    return "release-account-mismatch"


def _setup_kill_unreadable(monkeypatch):
    _write_release()
    _kill_stat_fails(monkeypatch)
    return "kill-unreadable"


_BLOCKED_SETUPS = [
    _setup_release_missing,
    _setup_release_unreadable,
    _setup_release_utf16,
    _setup_release_expired,
    _setup_release_too_long,
    _setup_release_wrong_account,
    _setup_kill_unreadable,
]


class TestRunLock:
    def test_lock_held_second_run_exit_seven(self, tmp_path):
        from tradingagents.dataflows import files

        path = executor.default_ledger_file()
        path.parent.mkdir(parents=True)
        factory = _RecordingFactory()
        pl_factory = _PaperLogFactory(_buy_paper(tmp_path))
        with files.locked(path, wait=False) as held:
            assert held
            code, records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=pl_factory)
        assert code == executor.EXIT_LOCKED
        assert "ibkr-state=LOCK_HELD" in _log_text(tmp_path)
        assert records == []
        assert not executor.default_dryrun_ledger_file().exists()
        assert factory.calls == []
        assert pl_factory.calls == []

    def test_lock_oserror_is_exit_seven_without_traceback(self, tmp_path, monkeypatch, capsys):
        import contextlib

        @contextlib.contextmanager
        def broken(path, wait=True):
            raise PermissionError("denied")
            yield  # pragma: no cover

        monkeypatch.setattr(executor, "locked", broken)
        factory = _RecordingFactory()
        code, records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path))
        assert code == executor.EXIT_LOCKED
        assert "ibkr-state=LOCK_ERROR" in _log_text(tmp_path)
        assert "Traceback" not in capsys.readouterr().err
        assert records == []
        assert factory.calls == []

    def test_lock_oserror_inside_the_run_is_not_exit_seven(self, tmp_path, loop):
        class DiskPlacer:
            dry = True

            def complete(self, ctx, intent):
                raise OSError("disk full")

        code, records = _gateway_run(tmp_path, loop, _fake_for(), placer=DiskPlacer())
        assert code != executor.EXIT_LOCKED
        assert code != executor.EXIT_OK
        end = _events(records, "run_end")[-1]
        assert end["outcome"] == "error"
        assert end["error"] == "OSError"

    def test_lock_sidecar_lives_in_the_state_dir(self, tmp_path):
        _run_execute(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=_buy_paper(tmp_path, rating="Hold"),
        )
        state_dir = tmp_path / "TradingEngineX" / "ibkr"
        assert (state_dir / "ledger.jsonl.lock").exists()
        assert not (state_dir / "ledger.jsonl").exists()
        assert list(executor.REPO_ROOT.glob("ledger*.lock")) == []


class TestFailClosed:
    @pytest.mark.parametrize(
        "setup", _BLOCKED_SETUPS, ids=lambda f: f.__name__.removeprefix("_setup_")
    )
    def test_fail_closed_matrix(self, tmp_path, monkeypatch, capsys, setup):
        state = setup(monkeypatch)
        factory = _RecordingFactory()
        pl_factory = _PaperLogFactory(_buy_paper(tmp_path))
        code, records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=pl_factory, release=False
        )
        assert code == executor.EXIT_KILL_SWITCH
        assert factory.calls == []
        assert pl_factory.calls == []
        assert _events(records, "intent") == []
        start = _events(records, "run_start")[0]
        assert "release" in start
        assert "kill" in start
        end = _events(records, "run_end")[-1]
        assert end["exit"] == 4
        assert end["state"] == state
        assert f"execute: {state} (" in capsys.readouterr().out
        assert f"ibkr-state={state.upper().replace('-', '_')}" in _log_text(tmp_path)

    def test_switch_state_logged_on_every_run(self, tmp_path, loop):
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        start = _events(records, "run_start")[0]
        assert start["release"] == "release-ok"
        assert start["kill"] == "kill-absent"
        assert start["valid_until"] == (OPEN_NOW.date() + timedelta(days=30)).isoformat()
        (check,) = _events(records, "switch_check")
        assert check["release"] == "release-ok"
        assert check["kill"] == "kill-absent"
        assert check["decision_key"] == KEY
        assert check["seq"] < _events(records, "intent")[0]["seq"]

    def test_preflight_switch_state_is_logged_when_blocked(self, tmp_path):
        code, records = _run_execute(
            tmp_path,
            _RecordingFactory(),
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            release=False,
        )
        assert code == executor.EXIT_KILL_SWITCH
        start = _events(records, "run_start")[0]
        assert start["release"] == "release-missing"
        assert start["kill"] == "kill-absent"

    def test_switch_checked_before_whatif(self, tmp_path, loop):
        fake = _fake_for()
        original = fake.reqPositionsAsync

        async def kill_then_read():
            executor.default_kill_file().write_text("stop", encoding="utf-8")
            return await original()

        fake.reqPositionsAsync = kill_then_read
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_KILL_SWITCH
        assert "placeOrder(whatIf)" not in fake.calls
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "kill_switch"
        assert _events(records, "intent") == []

    def test_fail_closed_blocked_switches_beat_corrupt_ledger(self, tmp_path):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        good = {"v": 1, "seq": 1, "mode": "dryrun", "event": "run_start"}
        path.write_text(
            json.dumps(good) + "\nnot json\n" + json.dumps({**good, "seq": 3}) + "\n",
            encoding="utf-8",
        )
        before = path.read_bytes()
        factory = _RecordingFactory()
        code, _records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path), release=False
        )
        assert code == executor.EXIT_KILL_SWITCH
        text = _log_text(tmp_path)
        assert "ibkr-state=LEDGER_CORRUPT" in text
        assert "ibkr-state=RELEASE_MISSING" in text
        assert factory.calls == []
        assert path.read_bytes() == before

    def test_blocked_by_kill_with_a_corrupt_ledger_still_cancels_once(self, tmp_path, loop):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        good = {"v": 1, "seq": 1, "mode": "dryrun", "event": "run_start"}
        path.write_text(
            json.dumps(good) + "\nnot json\n" + json.dumps({**good, "seq": 3}) + "\n",
            encoding="utf-8",
        )
        before = path.read_bytes()
        fake = _fake_for()
        code, _records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        assert path.read_bytes() == before

    def test_a_kill_txt_from_explorer_stops_and_cancels(self, tmp_path, loop):
        """WR-03: KILL.txt (hidden ending in Explorer) is a present kill switch."""
        kill_txt = executor.default_kill_file().with_name("KILL.txt")
        kill_txt.parent.mkdir(parents=True, exist_ok=True)
        kill_txt.write_text("stop", encoding="utf-8")
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        assert _events(records, "intent") == []
        assert _events(records, "run_start")[0]["kill"] == "kill-active"

    @pytest.mark.parametrize("seq", ['"x"', "null", "1.5", "true", "0"])
    def test_kill_with_a_malformed_seq_still_cancels_with_exit_4(self, tmp_path, loop, seq):
        """CR-01: a record that is valid JSON but not a ledger record never bypasses the kill."""
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        line = f'{{"v":1,"seq":{seq},"ts":"t","run_id":"r","mode":"dryrun","event":"run_start"}}\n'
        path.write_text(line, encoding="utf-8")
        fake = _fake_for()
        code, _records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        text = _log_text(tmp_path)
        assert "ibkr-state=LEDGER_CORRUPT" in text
        assert "UNEXPECTED" not in text

    def test_kill_with_an_intent_missing_its_order_fields_still_cancels(self, tmp_path, loop):
        """CR-01: an intent without side/quantity/con_id is a ledger error, not a KeyError later."""
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        intent = {
            "v": 1,
            "seq": 1,
            "ts": "t",
            "run_id": "r",
            "mode": "dryrun",
            "event": "intent",
            "decision_key": KEY,
        }
        path.write_text(json.dumps(intent) + "\n", encoding="utf-8")
        fake = _fake_for()
        code, _records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1

    @staticmethod
    def _ledger_read_denied(monkeypatch):
        real = Path.read_bytes

        def read_bytes(self):
            if self.name == "ledger-dryrun.jsonl":
                raise PermissionError("held open by another program")
            return real(self)

        monkeypatch.setattr(Path, "read_bytes", read_bytes)

    def test_kill_with_an_unreadable_ledger_still_cancels_with_exit_4(
        self, tmp_path, loop, monkeypatch
    ):
        """CR-01: a ledger another program holds open (Windows) ends like a corrupt one."""
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")  # present, so the read is attempted
        self._ledger_read_denied(monkeypatch)
        fake = _fake_for()
        code, _records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        assert 'ibkr-state=LEDGER_CORRUPT detail="PermissionError' in _log_text(tmp_path)

    def test_an_unreadable_ledger_without_kill_is_exit_6(self, tmp_path, monkeypatch):
        path = executor.default_dryrun_ledger_file()
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")
        self._ledger_read_denied(monkeypatch)
        factory = _RecordingFactory()
        code, _records = _run_execute(tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path))
        assert code == executor.EXIT_RECONCILE
        assert factory.calls == []
        assert "ibkr-state=LEDGER_CORRUPT" in _log_text(tmp_path)

    def test_negative_control_switches_bypassed_would_reach_intent(
        self, tmp_path, loop, monkeypatch
    ):
        def always_open(state_dir, *, today_utc, expected_account):
            return guards.Switches(
                release=guards.ReleaseState(guards.RELEASE_OK, "", today_utc, expected_account),
                kill=guards.KillState(guards.KILL_ABSENT),
            )

        # The real chain: KILL present, no intent.
        _code, real = _gateway_run(tmp_path, loop, _fake_for(), kill=True)
        assert _events(real, "intent") == []
        # The bypassed chain: the same run reaches the intent.
        monkeypatch.setattr(guards, "check_switches", always_open)
        code, records = _gateway_run(tmp_path, loop, _fake_for(), kill=True)
        assert code == executor.EXIT_OK
        assert len(_events(records, "intent")) == 1


# --- the kill path: one global cancel, a re-read, exit 4 (05-05, Task 2) ------------------------


def _two_buys(tmp_path):
    return _paper(
        tmp_path,
        [("2026-10-09", "AAPL", "Buy"), ("2026-10-09", "MSFT", "Buy")],
        {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", "Buy"), ("MSFT", "ok", "Buy"))},
    )


class _KillingPlacer(executor.DryPlacer):
    """Lays the KILL file in the first ``complete()``, then completes like the dry placer."""

    def __init__(self):
        self.fired = False

    def complete(self, ctx, intent):
        if not self.fired:
            self.fired = True
            executor.default_kill_file().write_text("stop", encoding="utf-8")
        return super().complete(ctx, intent)


class TestKillPath:
    def test_kill_preflight_cancel_all_once(self, tmp_path, loop):
        fake = _fake_for(open_orders=[ibkr_fakes.open_trade(CON_IDS["AAPL"], order_ref="")])
        pl_factory = _PaperLogFactory(_buy_paper(tmp_path))
        code, records = _gateway_run(tmp_path, loop, fake, paper=pl_factory, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        assert "open_orders" in fake.calls[fake.calls.index("reqGlobalCancel") :]
        assert "placeOrder(whatIf)" not in fake.calls
        assert pl_factory.calls == []
        assert [r["event"] for r in records] == ["run_start", "kill_cancel", "run_end"]
        assert records[0]["kill"] == "kill-active"
        cancel = records[1]
        assert cancel["outcome"] == "sent"
        assert cancel["sent"] == 1
        assert cancel["remaining"] == 0
        assert records[2]["exit"] == 4
        text = _log_text(tmp_path)
        assert "GLOBAL_CANCEL_SENT" in text
        assert "ibkr-state=KILL_CANCEL remaining=0" in text

    def test_kill_cancel_without_effect_reports_remaining(
        self, tmp_path, loop, monkeypatch, caplog
    ):
        monkeypatch.setattr(executor, "KILL_RECHECK_SECONDS", 0.05)
        monkeypatch.setattr(executor, "_sleep", lambda seconds: None)
        fake = _fake_for(
            open_orders=[ibkr_fakes.open_trade(CON_IDS["AAPL"])], global_cancel_clears=False
        )
        code, records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        (cancel,) = _events(records, "kill_cancel")
        assert cancel["remaining"] == 1
        assert cancel["outcome"] == "sent"
        assert cancel["rechecks"] >= 1
        assert "ibkr-state=KILL_CANCEL remaining=1" in _log_text(tmp_path)

    def test_kill_cancel_gateway_unavailable_still_exit_four(self, tmp_path, loop):
        fake = _fake_for()
        fake.refuse = ConnectionRefusedError()
        code, records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        (cancel,) = _events(records, "kill_cancel")
        assert cancel["outcome"] == "gateway_unavailable"
        assert "reqGlobalCancel" not in fake.calls
        assert "ibkr-state=KILL_CANCEL_FAILED" in _log_text(tmp_path)

    def test_kill_cancel_unhealthy_session_still_exit_four(self, tmp_path):
        class SickBroker:
            cancelled = False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def health(self):
                return SimpleNamespace(ok=False, state="NOT_CONNECTED", detail="down")

            def cancel_all(self, **kwargs):
                SickBroker.cancelled = True

        code, records = _run_execute(
            tmp_path,
            lambda host, port, logger: SickBroker(),
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            kill=True,
        )
        assert code == executor.EXIT_KILL_SWITCH
        assert SickBroker.cancelled is False
        (cancel,) = _events(records, "kill_cancel")
        assert cancel["outcome"] == "gateway_unavailable"

    def test_kill_cancel_wrong_account_never_cancels(self, tmp_path, loop):
        fake = _fake_for(accounts=("DUX000000",))
        code, _records = _gateway_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_ACCOUNT_GUARD
        assert "reqGlobalCancel" not in fake.calls

    @pytest.mark.parametrize(
        "setup", _BLOCKED_SETUPS, ids=lambda f: f.__name__.removeprefix("_setup_")
    )
    def test_no_global_cancel_without_kill_file(self, tmp_path, loop, monkeypatch, setup):
        """Negative control to D-17: every block that is not a present KILL file cancels nothing."""
        setup(monkeypatch)
        fake = _fake_for()
        contracts = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        code, _records = _run_execute(
            tmp_path,
            _fake_factory(fake, loop),
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            release=False,
            contracts=contracts,
        )
        assert code == executor.EXIT_KILL_SWITCH
        assert "reqGlobalCancel" not in fake.calls
        assert "connect" not in fake.calls

    def test_g3_kill_between_two_orders(self, tmp_path, loop):
        """SC2 / G3: KILL appears after the first order; the second gets no intent."""
        fake = _fake_for(tickers=("AAPL", "MSFT"))
        code, records = _gateway_run(
            tmp_path,
            loop,
            fake,
            tickers=("AAPL", "MSFT"),
            paper=_two_buys(tmp_path),
            placer=_KillingPlacer(),
        )
        assert code == executor.EXIT_KILL_SWITCH
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL"]
        assert [r["ticker"] for r in _events(records, "dry_complete")] == ["AAPL"]
        (skipped,) = _events(records, "skipped")
        assert skipped["ticker"] == "MSFT"
        assert skipped["reason"] == "kill_switch"
        assert skipped["state"] == "kill-active"
        assert fake.calls.count("reqGlobalCancel") == 1
        assert fake.calls.count("placeOrder(whatIf)") == 1
        assert "placeOrder" not in fake.calls
        assert len(_events(records, "kill_cancel")) == 1
        assert _events(records, "run_end")[-1]["exit"] == 4

    def test_negative_control_kill_between_checked_once_per_run(self, tmp_path, loop, monkeypatch):
        real = guards.check_switches
        cache = []

        def checked_once(*args, **kwargs):
            if not cache:
                cache.append(real(*args, **kwargs))
            return cache[0]

        monkeypatch.setattr(guards, "check_switches", checked_once)
        fake = _fake_for(tickers=("AAPL", "MSFT"))
        _code, records = _gateway_run(
            tmp_path,
            loop,
            fake,
            tickers=("AAPL", "MSFT"),
            paper=_two_buys(tmp_path),
            placer=_KillingPlacer(),
        )
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL", "MSFT"]

    def test_cancel_all_called_at_one_site(self):
        import ast

        tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
        sites = []

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "cancel_all":
                    sites.append(self.stack[-1] if self.stack else None)
                self.generic_visit(node)

        Finder().visit(tree)
        assert sites == ["_kill_path"]


# --- size cap and session window (05-06, Task 1) --------------------------------------------------

_EASTERN = ZoneInfo("US/Eastern")


def _hours(day: date, start: str, end: str) -> str:
    stamp = day.strftime("%Y%m%d")
    return f"{stamp}:{start}-{stamp}:{end}"


def _window_clock(window_start_et: datetime, minutes: int) -> datetime:
    return (window_start_et + timedelta(minutes=minutes)).astimezone(UTC)


def _force_quantity(monkeypatch, quantity, side="BUY"):
    """Simulate a calculation error: the plan asks for ``quantity``."""
    monkeypatch.setattr(
        decision,
        "plan_order",
        lambda rating, **kwargs: decision.Plan(
            decision.INTENT, side, quantity, quantity, 0.0, f"{side} {quantity}"
        ),
    )


class TestSizeCap:
    def test_g3_size_cap_rejects_instead_of_trimming(self, tmp_path, loop, monkeypatch, capsys):
        _force_quantity(monkeypatch, 3)
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_REJECTED
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "size_cap"
        assert skipped["state"] == "size-cap"
        assert "exceeds MAX_QTY_PER_ORDER 2" in skipped["detail"]
        assert _events(records, "intent") == []
        assert "placeOrder(whatIf)" not in fake.calls
        _assert_nothing_sent(fake, None)
        assert "execute: AAPL size-cap" in capsys.readouterr().out
        assert _events(records, "run_end")[-1]["exit"] == executor.EXIT_REJECTED

    def test_size_cap_sell_above_cap_is_rejected_not_trimmed(self, tmp_path, loop):
        fake = _fake_for(positions=[_aapl_position(5)])
        code, records = _gateway_run(tmp_path, loop, fake, rating="Sell")
        assert code == executor.EXIT_REJECTED
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "size_cap"
        assert "quantity 5" in skipped["detail"]
        assert _events(records, "intent") == []
        assert "placeOrder(whatIf)" not in fake.calls

    def test_size_two_passes(self, tmp_path, loop):
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        (intent,) = _events(records, "intent")
        assert intent["quantity"] == 2

    def test_negative_control_size_cap_removed_would_send_three(self, tmp_path, loop, monkeypatch):
        _force_quantity(monkeypatch, 3)
        monkeypatch.setattr(guards, "check_size", lambda quantity: None)
        monkeypatch.setattr(
            executor.DryPlacer,
            "complete",
            lambda self, ctx, intent: ctx.mods.guards.DRY_COMPLETE,
        )
        _code, records = _gateway_run(tmp_path, loop, _fake_for())
        (intent,) = _events(records, "intent")
        assert intent["quantity"] == 3

    def test_negative_control_only_chain_check_removed_placer_still_refuses(
        self, tmp_path, loop, monkeypatch
    ):
        _force_quantity(monkeypatch, 3)
        real = guards.check_size
        calls = []

        def chain_blind(quantity):
            calls.append(quantity)
            return None if len(calls) == 1 else real(quantity)

        monkeypatch.setattr(guards, "check_size", chain_blind)
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        # WR-02: the second check sits before the intent line, so it refuses cleanly
        # (size-cap, exit 5) and leaves no open intent behind.
        assert code == executor.EXIT_REJECTED
        assert len(calls) == 2
        assert _events(records, "intent") == []
        assert _events(records, "dry_complete") == []
        (skipped,) = _events(records, "skipped")
        assert skipped["state"] == "size-cap"
        assert "size check before intent" in skipped["detail"]
        end = _events(records, "run_end")[-1]
        assert "outcome" not in end
        assert end["exit"] == executor.EXIT_REJECTED

    def test_size_checked_before_session(self, tmp_path, loop, monkeypatch):
        _force_quantity(monkeypatch, 3)
        day = date(2026, 10, 12)
        start = datetime(2026, 10, 12, 9, 30, tzinfo=_EASTERN)
        fake = _fake_for(liquid_hours=_hours(day, "0930", "1600"))
        code, records = _gateway_run(tmp_path, loop, fake, clock=_window_clock(start, 5))
        assert code == executor.EXIT_REJECTED
        (skipped,) = _events(records, "skipped")
        assert skipped["state"] == "size-cap"


_DAY = date(2026, 10, 12)
_START = datetime(2026, 10, 12, 9, 30, tzinfo=_EASTERN)
_FULL = _hours(_DAY, "0930", "1600")
_HALF = _hours(_DAY, "0930", "1300")

#: (liquid hours, minutes after 09:30 ET, expected state)
_SESSION_CASES = [
    pytest.param(_FULL, 200, "intent", id="mid_window"),
    pytest.param(_FULL, 5, "outside-session", id="opening_buffer"),
    pytest.param(_FULL, 6 * 60 + 30 - 5, "outside-session", id="closing_buffer"),
    pytest.param(_HALF, 3 * 60 + 30 - 5, "outside-session", id="half_day_closing_buffer"),
    pytest.param(_HALF, 90, "intent", id="half_day_mid_window"),
]


class TestSessionWindow:
    @pytest.mark.parametrize(("hours", "minutes", "expected"), _SESSION_CASES)
    def test_g3_session_window(self, tmp_path, loop, hours, minutes, expected):
        fake = _fake_for(liquid_hours=hours)
        code, records = _gateway_run(tmp_path, loop, fake, clock=_window_clock(_START, minutes))
        if expected == "intent":
            assert code == executor.EXIT_OK
            assert len(_events(records, "intent")) == 1
            return
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "outside_session"
        assert skipped["state"] == "outside-session"
        assert "placeOrder(whatIf)" not in fake.calls
        assert _events(records, "intent") == []

    def test_g3_session_window_saturday(self, tmp_path, loop):
        saturday = datetime(2026, 10, 10, 17, 20, tzinfo=UTC)
        fake = _fake_for(liquid_hours=f"20261010:CLOSED;{_FULL}")
        code, records = _gateway_run(tmp_path, loop, fake, clock=saturday)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "outside_session"
        assert "placeOrder(whatIf)" not in fake.calls
        assert _events(records, "intent") == []

    def test_the_window_closing_during_the_run_stops_before_the_intent(self, tmp_path, loop):
        """WR-05: the window is judged again with a fresh clock right before the intent."""
        moment = {"now": _window_clock(_START, 370)}  # 15:40 ET: inside the buffered window
        fake = _fake_for(liquid_hours=_FULL)
        original = fake.reqPositionsAsync

        async def time_passes_then_read():
            moment["now"] = _window_clock(_START, 380)  # 15:50 ET: inside the closing buffer
            return await original()

        fake.reqPositionsAsync = time_passes_then_read
        code, records = _gateway_run(tmp_path, loop, fake, clock=lambda: moment["now"])
        assert code == executor.EXIT_PRECONDITION
        assert fake.calls.count("placeOrder(whatIf)") == 1
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "outside_session"
        assert skipped["state"] == "outside-session"
        assert "closed during the run" in skipped["detail"]
        assert _events(records, "intent") == []
        assert len(_events(records, "switch_check")) == 1

    def test_freshness_recheck_with_a_fresh_clock_stops_before_the_intent(self, tmp_path, loop):
        """WR-05 rest: freshness is judged again right before the intent, not only at start."""
        state = {"late": False}

        class LateClosedSessionCalendar(WeekdayCalendar):
            def sessions_between(self, start, end):
                if state["late"]:
                    return (date(2026, 10, 10),)  # a session closed since the run started
                return super().sessions_between(start, end)

        fake = _fake_for(liquid_hours=_FULL)
        original = fake.reqPositionsAsync

        async def time_passes_then_read():
            state["late"] = True
            return await original()

        fake.reqPositionsAsync = time_passes_then_read
        code, records = _gateway_run(
            tmp_path,
            loop,
            fake,
            clock=_window_clock(_START, 370),
            calendar=LateClosedSessionCalendar(),
        )
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["state"] == "stale-decision"
        assert skipped["reason"] == ledger_mod.REASON_BY_STATE["stale-decision"]
        assert _events(records, "intent") == []

    def test_jev_rating_source_ends_as_review_without_an_intent(self, tmp_path, loop):
        summary = _summary("2026-10-09", ("AAPL", "ok", "Buy"))
        summary["runs"][0]["rating_source"] = "jev"
        paper = _paper(tmp_path, [("2026-10-09", "AAPL", "Buy")], {"2026-10-09": summary})
        code, records = _gateway_run(tmp_path, loop, _fake_for(), paper=paper)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "review"
        assert skipped["state"] == "rating-jev"
        assert _events(records, "intent") == []

    def test_rating_source_jev_in_the_summary_is_what_the_intent_would_carry(self):
        # the intent takes the source from the verdict: an engine rating is "engine"
        assert "rating_source" in executor._ROW_KEYS

    def test_negative_control_a_fixed_clock_inside_the_window_reaches_the_intent(
        self, tmp_path, loop
    ):
        fake = _fake_for(liquid_hours=_FULL)
        code, records = _gateway_run(tmp_path, loop, fake, clock=_window_clock(_START, 370))
        assert code == executor.EXIT_OK
        assert len(_events(records, "intent")) == 1

    def test_session_unknown_stays_not_tradable(self, tmp_path, loop):
        fake = _fake_for(liquid_hours=_hours(date(2026, 10, 13), "0930", "1600"))
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["state"] == "session-unknown"
        assert skipped["reason"] == "not_tradable"
        assert "placeOrder(whatIf)" not in fake.calls


# --- one attempt per decision_key (05-06, Task 2) -------------------------------------------------

SHA_B = "b" * 40


def _second_paper(tmp_path, rating):
    """A second paper-log state: same entry date and ticker, another rating and SHA."""
    root = write_paper_log(
        tmp_path / "pl2",
        [("2026-10-09", "AAPL", rating)],
        {"2026-10-09": _summary("2026-10-09", ("AAPL", "ok", rating))},
    )
    return FixturePaperLog(root, SHA_B)


class TestOneAttemptPerKey:
    def test_already_attempted_second_run_same_key(self, tmp_path, loop):
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        (first,) = _events(records, "intent")
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path,
            factory,
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            contracts=tmp_path / "ibkr" / "contracts.json",
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "already_attempted"
        assert skipped["state"] == "already-attempted"
        assert KEY in skipped["detail"]
        assert first["run_id"] in skipped["detail"]
        assert first["ts"] in skipped["detail"]
        assert len(_events(records, "intent")) == 1

    def test_already_attempted_sends_no_second_whatif(self, tmp_path, loop):
        _gateway_run(tmp_path, loop, _fake_for())
        fake = _fake_for()
        code, _records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        assert "placeOrder(whatIf)" not in fake.calls
        assert "connect" not in fake.calls

    def test_decision_changed_second_version_is_logged_not_executed(self, tmp_path, loop):
        _gateway_run(tmp_path, loop, _fake_for())
        fake = _fake_for()
        paper = _second_paper(tmp_path, "Overweight")
        code, records = _gateway_run(tmp_path, loop, fake, paper=paper)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["reason"] == "decision_changed"
        assert skipped["state"] == "decision-changed"
        assert skipped["first_rating"] == "Buy"
        assert skipped["paper_log_sha"] == SHA_B
        assert skipped["first_paper_log_sha"] == SHA
        assert "Overweight" in skipped["detail"]
        assert len(_events(records, "intent")) == 1
        assert "placeOrder(whatIf)" not in fake.calls

    def test_already_attempted_skipped_does_not_consume(self, tmp_path, loop):
        code, records = _gateway_run(
            tmp_path, loop, _fake_for(liquid_hours=_FULL), clock=_window_clock(_START, 5)
        )
        assert code == executor.EXIT_PRECONDITION
        assert _events(records, "skipped")[0]["reason"] == "outside_session"
        code, records = _gateway_run(
            tmp_path, loop, _fake_for(liquid_hours=_FULL), clock=_window_clock(_START, 200)
        )
        assert code == executor.EXIT_OK
        assert len(_events(records, "intent")) == 1

    def test_already_attempted_after_crash_is_not_a_second_intent(self, tmp_path, loop):
        class CrashingPlacer:
            dry = True

            def complete(self, ctx, intent):
                raise RuntimeError("crash after the write-ahead line")

        _gateway_run(tmp_path, loop, _fake_for(), placer=CrashingPlacer())
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        # The reconciliation meets the open dry intent first and closes it as never sent
        # (WR-02); the key stays used up, so the key check stops a second intent.
        assert code == executor.EXIT_PRECONDITION
        assert len(_events(records, "intent")) == 1
        assert [r["outcome"] for r in _events(records, "reconcile")] == ["never_sent"]
        (skipped,) = _events(records, "skipped")
        assert skipped["state"] == "already-attempted"
        assert "placeOrder(whatIf)" not in fake.calls

    def test_negative_control_key_check_removed_allows_second_intent(
        self, tmp_path, loop, monkeypatch
    ):
        _gateway_run(tmp_path, loop, _fake_for())
        monkeypatch.setattr(ledger_mod.Ledger, "attempt_of", lambda self, key: None)
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        assert len(_events(records, "intent")) == 2


# --- startup reconciliation (05-07, Task 1) -------------------------------------------------------

PREV_KEY = "2026-10-08|AAPL"
RECONCILE_MANUAL = "see IBKR_EXECUTION.md, Ledger and reconciliation"


def _prepare_ledger(*events):
    """Write lines into the dry-run ledger the way a former run would have (not by hand)."""
    path = executor.default_dryrun_ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    led = ledger_mod.Ledger.open(
        path, mode=ledger_mod.MODE_DRYRUN, clock=_fixed(OPEN_NOW), run_id="prepared"
    )
    for event, fields in events:
        led.append(event, **fields)
    return led


def _prepared_intent():
    fields = ledger_mod.intent_record(
        decision_key=PREV_KEY,
        ticker="AAPL",
        trade_date="2026-10-08",
        rating="Buy",
        paper_log_sha=SHA,
        side="BUY",
        quantity=2,
        con_id=CON_IDS["AAPL"],
        order_ref=PREV_KEY,
        weekend_gap=False,
    )
    return ledger_mod.INTENT, fields


def _unresolved_keys():
    led = ledger_mod.Ledger.open(
        executor.default_dryrun_ledger_file(),
        mode=ledger_mod.MODE_DRYRUN,
        clock=_fixed(OPEN_NOW),
        run_id="reader",
    )
    return [entry["decision_key"] for entry in led.unresolved()]


class _CrashAfterIntent:
    dry = True

    def complete(self, ctx, intent):
        raise RuntimeError("crash after the write-ahead line")


def _msft_run(tmp_path, loop, fake, **kwargs):
    """MSFT is the new Buy ticker next to a prepared AAPL entry of the day before."""
    return _gateway_run(
        tmp_path,
        loop,
        fake,
        tickers=("MSFT",),
        paper=_buy_paper(tmp_path, ticker="MSFT"),
        **kwargs,
    )


_CON = CON_IDS["AAPL"]
#: Broker history that contradicts itself for PREV_KEY: unresolvable in either ledger.
_CONTRADICTION = {
    "open_orders": [ibkr_fakes.open_trade(_CON, order_ref=PREV_KEY, quantity=2)],
    "completed_orders": [
        ibkr_fakes.completed_trade(_CON, "Cancelled", order_ref=PREV_KEY, quantity=2)
    ],
}
_RECONCILE_CASES = [
    pytest.param(
        {"open_orders": [ibkr_fakes.open_trade(_CON, order_ref=PREV_KEY, quantity=2)]},
        "open",
        "placed",
        None,
        id="open-order",
    ),
    pytest.param(
        {
            "completed_orders": [
                ibkr_fakes.completed_trade(_CON, "Cancelled", order_ref=PREV_KEY, quantity=2)
            ]
        },
        "not_filled",
        "rejected",
        None,
        id="cancelled-order",
    ),
    pytest.param(
        {"executions": [ibkr_fakes.fill(_CON, PREV_KEY, 2)]},
        "filled",
        "filled",
        2.0,
        id="executions",
    ),
    pytest.param(
        {
            "completed_orders": [
                ibkr_fakes.completed_trade(
                    _CON, "Filled", order_ref=PREV_KEY, quantity=2, filled=2.0
                )
            ]
        },
        "filled",
        "filled",
        2.0,
        id="completed-filled",
    ),
    # CR-03: partly filled, then cancelled, no executions (the next day): the fill counts.
    pytest.param(
        {
            "completed_orders": [
                ibkr_fakes.completed_trade(
                    _CON, "Cancelled", order_ref=PREV_KEY, quantity=2, filled=1.0
                )
            ]
        },
        "partial",
        "partial",
        1.0,
        id="cancelled-after-partial-fill",
    ),
]


def _live_reconcile_ctx(tmp_path, history, caplog_name="test-live-reconcile"):
    """A ``_reconcile`` context on a live ledger with one open intent (phase 6 mode)."""
    import logging

    path = tmp_path / "live" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    led = ledger_mod.Ledger.open(
        path, mode=ledger_mod.MODE_LIVE, clock=_fixed(OPEN_NOW), run_id="live"
    )
    if not led.records:
        kind, fields = _prepared_intent()
        led.append(kind, **fields)
    return SimpleNamespace(
        ledger=led,
        mods=SimpleNamespace(guards=guards, ledger=ledger_mod),
        history=history,
        logger=logging.getLogger(caplog_name),
    )


_NO_TRACE = SimpleNamespace(open=[], completed=[], executions=[])


class TestReconcile:
    def test_g3_reconcile_unresolved_intent_aborts_with_exit_six(self, tmp_path, caplog, capsys):
        """SC6 / G3: in the live ledger an intent without a trace blocks the run (exit 6),
        and it stays open in every later run (REQ-43). The dry ledger resolves it instead
        (``test_g3_reconcile_dry_intent_without_trace_is_never_sent``)."""
        for expected_lines in (1, 2):
            ctx = _live_reconcile_ctx(tmp_path, _NO_TRACE)
            with (
                caplog.at_level("WARNING", logger="test-live-reconcile"),
                pytest.raises(executor._ExecuteStop) as stop,
            ):
                executor._reconcile(ctx)
            assert stop.value.code == executor.EXIT_RECONCILE == 6
            assert stop.value.state == "reconcile-unresolved"
            reconciles = _events(ctx.ledger.records, "reconcile")
            assert len(reconciles) == expected_lines
            assert reconciles[-1]["decision_key"] == PREV_KEY
            assert reconciles[-1]["outcome"] == "no_trace"
            assert [e["decision_key"] for e in ctx.ledger.unresolved()] == [PREV_KEY]
        assert (
            f"ibkr-state=RECONCILE_UNRESOLVED key={PREV_KEY} outcome=no_trace "
            "open=0 completed=0 executions=0"
        ) in caplog.text
        assert RECONCILE_MANUAL in capsys.readouterr().out

    def test_g3_reconcile_dry_intent_without_trace_is_never_sent(self, tmp_path, loop, capsys):
        """WR-02 / D-08: a dry run that broke off after the intent does not block every later
        run with exit 6: the dry intent was never sent, it is closed as such and logged."""
        code, records = _gateway_run(tmp_path, loop, _fake_for(), placer=_CrashAfterIntent())
        assert code != executor.EXIT_OK
        assert len(_events(records, "intent")) == 1
        capsys.readouterr()
        fake = _fake_for(("AAPL", "MSFT"))
        pl_factory = _PaperLogFactory(_two_buys(tmp_path))
        code, records = _gateway_run(
            tmp_path, loop, fake, tickers=("AAPL", "MSFT"), paper=pl_factory
        )
        # AAPL's key is used up (already-attempted, exit 2); MSFT goes through.
        assert code == executor.EXIT_PRECONDITION
        for name in ("open_orders", "completed_orders", "executions"):
            assert name in fake.calls
        (reconcile,) = _events(records, "reconcile")
        assert reconcile["decision_key"] == KEY
        assert reconcile["outcome"] == "never_sent"
        assert (reconcile["open"], reconcile["completed"], reconcile["executions"]) == (0, 0, 0)
        (closed,) = [r for r in _events(records, "rejected") if r.get("source") == "reconcile"]
        assert closed["decision_key"] == KEY
        assert closed["state"] == "never-sent"
        assert closed["seq"] > reconcile["seq"]
        assert _unresolved_keys() == []
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL", "MSFT"]
        end = _events(records, "run_end")[-1]
        assert end["exit"] == executor.EXIT_PRECONDITION
        assert "state" not in end
        assert f"ibkr-state=RECONCILE_NEVER_SENT key={KEY}" in _log_text(tmp_path)
        assert "RECONCILE_UNRESOLVED" not in _log_text(tmp_path)
        assert RECONCILE_MANUAL not in capsys.readouterr().out

    @pytest.mark.parametrize(("history", "outcome", "follow", "filled"), _RECONCILE_CASES)
    def test_g3_reconcile_resolves_before_any_new_order(
        self, tmp_path, loop, history, outcome, follow, filled
    ):
        _prepare_ledger(_prepared_intent())
        fake = _fake_for(("MSFT",), **history)
        code, records = _msft_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        (reconcile,) = _events(records, "reconcile")
        assert reconcile["decision_key"] == PREV_KEY
        assert reconcile["outcome"] == outcome
        (resolved,) = [
            r for r in records if r["event"] == follow and r.get("source") == "reconcile"
        ]
        assert resolved["decision_key"] == PREV_KEY
        if filled is not None:
            assert resolved["filled_qty"] == filled
            assert resolved["con_id"] == _CON
        if follow == "rejected":
            assert resolved["state"] == "not-filled"
        new_intents = [r for r in _events(records, "intent") if r["decision_key"] != PREV_KEY]
        assert [r["ticker"] for r in new_intents] == ["MSFT"]
        assert reconcile["seq"] < new_intents[0]["seq"]
        assert resolved["seq"] < new_intents[0]["seq"]
        assert not executor.default_ledger_file().exists()

    def test_reconcile_correction_writes_one_fill_row_for_the_corrected_execution(
        self, tmp_path, loop
    ):
        """REQ-47: execId .01.01 then its correction .01.02 (2 pieces each) is one fill of 2."""
        _prepare_ledger(_prepared_intent())
        fake = _fake_for(
            ("MSFT",),
            executions=[
                ibkr_fakes.fill(_CON, PREV_KEY, 2, exec_id="0000e0d5.6710a3c5.01.01"),
                ibkr_fakes.fill(_CON, PREV_KEY, 2, exec_id="0000e0d5.6710a3c5.01.02"),
            ],
        )
        code, records = _msft_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        (filled,) = [
            r for r in records if r["event"] == "filled" and r.get("source") == "reconcile"
        ]
        assert filled["exec_id"] == "0000e0d5.6710a3c5.01.02"
        assert filled["side"] == "BUY" and filled["filled_qty"] == 2.0
        assert not [r for r in records if r["event"] == "partial"]

    def test_reconcile_correction_aggregate_row_carries_the_side(self, tmp_path, loop):
        """Only a completed order, no executions: one aggregate fill row with ``side``."""
        _prepare_ledger(_prepared_intent())
        fake = _fake_for(
            ("MSFT",),
            completed_orders=[
                ibkr_fakes.completed_trade(
                    _CON, "Filled", order_ref=PREV_KEY, quantity=2, filled=2.0
                )
            ],
        )
        code, records = _msft_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        (filled,) = [
            r for r in records if r["event"] == "filled" and r.get("source") == "reconcile"
        ]
        assert "exec_id" not in filled
        assert filled["side"] == "BUY" and filled["filled_qty"] == 2.0

    def test_g3_reconcile_unresolved_stays_unresolved_on_the_next_run(self, tmp_path, loop):
        """Blocker REQ-43: a reconcile line does not close an entry; every run stops again."""
        _prepare_ledger(_prepared_intent())
        for expected_lines in (1, 2):
            fake = _fake_for(("MSFT",), **_CONTRADICTION)
            pl_factory = _PaperLogFactory(_buy_paper(tmp_path, ticker="MSFT"))
            code, records = _gateway_run(tmp_path, loop, fake, tickers=("MSFT",), paper=pl_factory)
            assert code == executor.EXIT_RECONCILE
            reconciles = _events(records, "reconcile")
            assert len(reconciles) == expected_lines
            assert {r["decision_key"] for r in reconciles} == {PREV_KEY}
            assert reconciles[-1]["outcome"] == "contradiction"
            assert "placeOrder(whatIf)" not in fake.calls
            assert pl_factory.calls == []
            assert len(_events(records, "intent")) == 1
            assert _unresolved_keys() == [PREV_KEY]
            end = _events(records, "run_end")[-1]
            assert end["exit"] == 6
            assert end["state"] == "reconcile-unresolved"

    def test_reconcile_collision_is_exit_six(self, tmp_path, loop):
        _prepare_ledger(_prepared_intent())
        stranger = ibkr_fakes.open_trade(999, order_ref=PREV_KEY, quantity=2)
        fake = _fake_for(("MSFT",), open_orders=[stranger])
        code, records = _msft_run(tmp_path, loop, fake)
        assert code == executor.EXIT_RECONCILE
        (reconcile,) = _events(records, "reconcile")
        assert reconcile["outcome"] == "collision"
        assert len(_events(records, "intent")) == 1
        assert "placeOrder(whatIf)" not in fake.calls

    def test_reconcile_contradiction_is_exit_six(self, tmp_path, loop):
        _prepare_ledger(_prepared_intent())
        fake = _fake_for(
            ("MSFT",),
            open_orders=[ibkr_fakes.open_trade(_CON, order_ref=PREV_KEY, quantity=2)],
            completed_orders=[
                ibkr_fakes.completed_trade(_CON, "Cancelled", order_ref=PREV_KEY, quantity=2)
            ],
        )
        code, records = _msft_run(tmp_path, loop, fake)
        assert code == executor.EXIT_RECONCILE
        (reconcile,) = _events(records, "reconcile")
        assert reconcile["outcome"] == "contradiction"
        assert "placeOrder(whatIf)" not in fake.calls

    def test_reconcile_skipped_without_open_entries(self, tmp_path):
        done = {"decision_key": PREV_KEY, "ticker": "AAPL"}
        _prepare_ledger(_prepared_intent(), (ledger_mod.DRY_COMPLETE, done))
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path, rating="Hold")
        )
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert _events(records, "reconcile") == []

    def test_write_ahead_torn_tail_tolerated_at_cli(self, tmp_path, loop):
        _prepare_ledger((ledger_mod.RUN_START, {"command": "execute"}))
        path = executor.default_dryrun_ledger_file()
        with open(path, "ab") as fh:
            fh.write(b'{"v":1,"seq":2,"ts')
        code, records = _gateway_run(tmp_path, loop, _fake_for())
        assert code == executor.EXIT_OK
        lines = path.read_bytes().split(b"\n")
        assert lines[1] == b'{"v":1,"seq":2,"ts'
        assert json.loads(lines[2])["seals_torn_line"] == 2
        assert len(_events(records, "intent")) == 1

    def test_reconcile_kill_wins_over_exit_six(self, tmp_path, loop):
        """D-21: an active KILL ends the run with 4 and cancels; nothing is reconciled first."""
        _prepare_ledger(_prepared_intent())
        fake = _fake_for(("MSFT",))
        code, records = _msft_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert fake.calls.count("reqGlobalCancel") == 1
        assert _events(records, "reconcile") == []

    def test_negative_control_reconcile_removed_would_create_new_intent(
        self, tmp_path, loop, monkeypatch
    ):
        _prepare_ledger(_prepared_intent())
        # The real chain: the unresolvable entry stops the run before MSFT.
        code, records = _msft_run(tmp_path, loop, _fake_for(("MSFT",), **_CONTRADICTION))
        assert code == executor.EXIT_RECONCILE
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL"]
        monkeypatch.setattr(executor, "_reconcile", lambda ctx: None)
        _code, records = _msft_run(tmp_path, loop, _fake_for(("MSFT",), **_CONTRADICTION))
        # AAPL from the prepared entry, MSFT is the new order the real chain never lets through.
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL", "MSFT"]


# --- two sources per fact (05-07, Task 2) ---------------------------------------------------------


def _two_ticker_run(tmp_path, loop, fake, **kwargs):
    return _gateway_run(
        tmp_path, loop, fake, tickers=("AAPL", "MSFT"), paper=_two_buys(tmp_path), **kwargs
    )


def _intent_tickers(records):
    return [r["ticker"] for r in _events(records, "intent")]


class TestSourceConflict:
    def test_source_conflict_account_echo_stops_the_whole_run(self, tmp_path, loop, capsys):
        fake = _fake_for(("AAPL", "MSFT"), whatif_echo_account="DUX000000")
        code, records = _two_ticker_run(tmp_path, loop, fake)
        assert code == executor.EXIT_ACCOUNT_GUARD
        end = _events(records, "run_end")[-1]
        assert end["exit"] == 8
        assert end["state"] == "account-conflict"
        assert _events(records, "intent") == []
        assert fake.calls.count("placeOrder(whatIf)") == 1
        text = _log_text(tmp_path)
        assert "ibkr-state=ACCOUNT_CONFLICT" in text
        assert "DUX000000" in text
        assert "DUQ634065" in text
        assert "account-conflict" in capsys.readouterr().out

    @pytest.mark.parametrize("echo", [None, "", "DUQ634065"], ids=["none", "empty", "same"])
    def test_source_conflict_account_echo_missing_is_not_a_conflict(self, tmp_path, loop, echo):
        fake = _fake_for(whatif_echo_account=echo)
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert _intent_tickers(records) == ["AAPL"]

    def test_source_conflict_order_ref_echo_stops_only_that_ticker(self, tmp_path, loop):
        """WR-04: a gateway that changes the orderRef would hide the order from reconciliation."""
        fake = _fake_for(("AAPL", "MSFT"), whatif_echo_order_ref="2026-10-09_AAPL")
        code, records = _two_ticker_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        assert _events(records, "intent") == []
        skipped = _events(records, "skipped")
        assert [r["ticker"] for r in skipped] == ["AAPL", "MSFT"]
        assert {r["state"] for r in skipped} == {"source-conflict"}
        assert {r["reason"] for r in skipped} == {"source_conflict"}
        assert "orderRef echo '2026-10-09_AAPL' differs" in skipped[0]["detail"]
        assert "ibkr-state=ORDER_REF_CONFLICT ticker=AAPL" in _log_text(tmp_path)

    @pytest.mark.parametrize("echo", [None, ""], ids=["same", "empty"])
    def test_source_conflict_order_ref_echo_same_or_empty_is_not_a_conflict(
        self, tmp_path, loop, echo
    ):
        fake = _fake_for(whatif_echo_order_ref=echo)
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert _intent_tickers(records) == ["AAPL"]

    def test_source_conflict_position_only_that_ticker(self, tmp_path, loop):
        """D-18: the ledger holds own fills the broker does not show."""
        filled = {
            "decision_key": PREV_KEY,
            "ticker": "AAPL",
            "con_id": _CON,
            "side": "BUY",
            "filled_qty": 2,
        }
        _prepare_ledger((ledger_mod.FILLED, filled))
        fake = _fake_for(("AAPL", "MSFT"), positions=[_aapl_position(1)])
        code, records = _two_ticker_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["ticker"] == "AAPL"
        assert skipped["reason"] == "source_conflict"
        assert skipped["state"] == "source-conflict"
        assert "ledger has 2 filled, broker holds 1" in skipped["detail"]
        assert _intent_tickers(records) == ["MSFT"]

    def test_source_conflict_position_without_fills_is_no_conflict(self, tmp_path, loop):
        fake = _fake_for(positions=[_aapl_position(5)])
        _code, records = _gateway_run(tmp_path, loop, fake)
        assert [r for r in _events(records, "skipped") if r["reason"] == "source_conflict"] == []

    def test_source_conflict_already_executed_broker_knows_order_ref(self, tmp_path, loop):
        known = ibkr_fakes.completed_trade(_CON, "Filled", order_ref=KEY, quantity=2, filled=2.0)
        fake = _fake_for(("AAPL", "MSFT"), completed_orders=[known])
        code, records = _two_ticker_run(tmp_path, loop, fake)
        assert code == executor.EXIT_PRECONDITION
        (skipped,) = _events(records, "skipped")
        assert skipped["ticker"] == "AAPL"
        assert skipped["reason"] == "source_conflict"
        assert "executed:" in skipped["detail"]
        assert fake.calls.count("placeOrder(whatIf)") == 1
        assert _intent_tickers(records) == ["MSFT"]

    def test_source_conflict_tradability_calendar_vs_liquid_hours_only_that_ticker(
        self, tmp_path, loop
    ):
        aapl = ibkr_fakes.stk_contract("AAPL", CON_IDS["AAPL"])
        msft = ibkr_fakes.stk_contract("MSFT", CON_IDS["MSFT"])
        fake = ibkr_fakes.FakeIB(
            qualify={"AAPL": [aapl], "MSFT": [msft]},
            details={
                CON_IDS["AAPL"]: [ibkr_fakes.contract_detail(aapl, liquid_hours=OPEN_HOURS)],
                # MSFT agrees with the calendar that today is no session day.
                CON_IDS["MSFT"]: [
                    ibkr_fakes.contract_detail(
                        msft, liquid_hours="20261012:CLOSED;20261013:0930-20261013:1600"
                    )
                ],
            },
            summary=_funds(),
            whatif=ibkr_fakes.order_state(),
        )
        calendar = _stub_calendar(holidays={date(2026, 10, 12)})
        code, records = _two_ticker_run(tmp_path, loop, fake, calendar=calendar)
        assert code == executor.EXIT_PRECONDITION
        by_ticker = {r["ticker"]: r for r in _events(records, "skipped")}
        assert by_ticker["AAPL"]["state"] == "calendar-conflict"
        assert by_ticker["AAPL"]["reason"] == "source_conflict"
        # MSFT was processed on its own: its end is its own state, not a conflict.
        assert by_ticker["MSFT"]["reason"] == "outside_session"
        assert _events(records, "intent") == []
        assert "placeOrder(whatIf)" not in fake.calls

    def test_source_conflict_never_leaves_an_intent_for_the_ticker(self, tmp_path, loop):
        known = ibkr_fakes.open_trade(_CON, order_ref=KEY, quantity=2)
        fake = _fake_for(("AAPL", "MSFT"), open_orders=[known])
        _code, records = _two_ticker_run(tmp_path, loop, fake)
        assert _intent_tickers(records) == ["MSFT"]
        assert [r["ticker"] for r in _events(records, "skipped")] == ["AAPL"]

    def test_source_conflict_negative_control_position_check_removed(
        self, tmp_path, loop, monkeypatch
    ):
        filled = {
            "decision_key": PREV_KEY,
            "ticker": "AAPL",
            "con_id": _CON,
            "side": "BUY",
            "filled_qty": 2,
        }
        _prepare_ledger((ledger_mod.FILLED, filled))
        monkeypatch.setattr(guards, "position_conflict", lambda **kwargs: None)
        fake = _fake_for(("AAPL", "MSFT"), positions=[_aapl_position(1)])
        _code, records = _two_ticker_run(tmp_path, loop, fake)
        assert "AAPL" in _intent_tickers(records)

    def test_source_conflict_negative_control_executed_check_removed(
        self, tmp_path, loop, monkeypatch
    ):
        monkeypatch.setattr(guards, "executed_conflict", lambda **kwargs: None)
        known = ibkr_fakes.completed_trade(_CON, "Filled", order_ref=KEY, quantity=2, filled=2.0)
        fake = _fake_for(("AAPL", "MSFT"), completed_orders=[known])
        _code, records = _two_ticker_run(tmp_path, loop, fake)
        assert "AAPL" in _intent_tickers(records)

    def test_source_conflict_negative_control_account_check_removed(
        self, tmp_path, loop, monkeypatch
    ):
        monkeypatch.setattr(guards, "account_conflict", lambda **kwargs: None)
        fake = _fake_for(("AAPL", "MSFT"), whatif_echo_account="DUX000000")
        code, records = _two_ticker_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert _intent_tickers(records) == ["AAPL", "MSFT"]


class TestLiveSwitch:
    """``--live`` switches per run (D-01); placer and mode must agree before any file."""

    def test_not_live_refuses_a_dry_placer_before_any_file(self, tmp_path):
        factory = _RecordingFactory()
        code, records = _run_execute(
            tmp_path,
            factory,
            ["AAPL"],
            paper_log=_buy_paper(tmp_path),
            placer=executor.DryPlacer(),
            extra=("--live",),
        )
        assert code == executor.EXIT_CONFIG
        assert "ibkr-state=NOT_LIVE" in _log_text(tmp_path)
        assert records == []
        assert not executor.default_ledger_file().exists()
        assert not executor.default_dryrun_ledger_file().exists()
        assert factory.calls == []

    def test_without_live_the_default_placer_is_dry_and_writes_only_the_dryrun_ledger(
        self, tmp_path, loop
    ):
        fake = _fake_for()
        code, records = _gateway_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert [r["event"] for r in records][-2:] == ["dry_complete", "run_end"]
        assert not executor.default_ledger_file().exists()
        _assert_nothing_sent(fake, 1)

    def test_live_without_release_exits_4_and_sends_nothing(self, tmp_path, loop):
        fake = _fake_for()
        code, records = _live_run(tmp_path, loop, fake, release=False)
        assert code == executor.EXIT_KILL_SWITCH
        assert "placeOrder" not in fake.calls
        assert fake.placed_orders == []
        assert records[0]["event"] == "run_start"
        assert records[0]["mode"] == "live"
        assert not executor.default_dryrun_ledger_file().exists()

    def test_live_kill_wins_even_with_a_release(self, tmp_path, loop):
        fake = _fake_for()
        code, records = _live_run(tmp_path, loop, fake, kill=True)
        assert code == executor.EXIT_KILL_SWITCH
        assert "placeOrder" not in fake.calls
        assert fake.placed_orders == []
        assert records[-1]["event"] == "run_end"

    def test_live_ledger_mode_and_lock_path(self, tmp_path, loop):
        fake = _fake_for()
        seen = []

        class SpyPlacer(executor.LivePlacer):
            def complete(self, ctx, intent):
                seen.append(
                    (
                        ctx.ledger.path,
                        ctx.ledger.mode,
                        executor.default_ledger_file().with_name("ledger.jsonl.lock").exists(),
                    )
                )
                return ctx.mods.guards.ORDER_FILLED

        code, _records = _live_run(tmp_path, loop, fake, placer=SpyPlacer())
        assert code == executor.EXIT_OK
        ((path, mode, _lock),) = seen
        assert path == executor.default_ledger_file()
        assert mode == "live"


EXEC_ID = "0000e0d5.6710a3c5.01.01"


def _own_fill(**overrides):
    """The execution a clean fill of the AAPL intent produces."""
    args = {
        "con_id": CON_IDS["AAPL"],
        "order_ref": KEY,
        "shares": 2,
        "side": "BOT",
        "exec_id": EXEC_ID,
        "price": 250.1,
        "perm_id": 777,
        "order_id": 5,
    }
    args.update(overrides)
    con_id = args.pop("con_id")
    order_ref = args.pop("order_ref")
    shares = args.pop("shares")
    return ibkr_fakes.fill(con_id, order_ref, shares, **args)


def _own_completed(**overrides):
    args = {
        "status": "Filled",
        "order_ref": KEY,
        "action": "BUY",
        "quantity": 2,
        "filled": 2,
        "perm_id": 777,
        "order_id": 5,
    }
    args.update(overrides)
    return ibkr_fakes.completed_trade(CON_IDS["AAPL"], **args)


def _filling_fake(tickers=("AAPL",), *, executions=None, completed=None, **kwargs):
    return _fake_for(
        tickers,
        place_executions=[_own_fill()] if executions is None else executions,
        place_completed=_own_completed() if completed is None else completed,
        **kwargs,
    )


class TestLivePlacer:
    """The live placer: send, ``placed``, read back, compare, persist (D-09, D-10, REQ-65)."""

    @pytest.fixture(autouse=True)
    def _no_wait(self, monkeypatch):
        monkeypatch.setattr(executor, "POST_ORDER_RETRY_S", 0)

    def test_live_chain_intent_placed_filled(self, tmp_path, loop, capsys):
        fake = _filling_fake()
        code, records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        chain = [
            r for r in records if r.get("decision_key") == KEY and r["event"] != "switch_check"
        ]
        assert [r["event"] for r in chain] == ["intent", "placed", "filled"]
        intent, placed, filled = chain
        assert placed["order_id"] == 5
        assert placed["perm_id"] == 777
        assert filled["exec_id"] == EXEC_ID
        assert filled["filled_qty"] == 2
        assert filled["side"] == "BUY"
        assert filled["order_ref"] == KEY
        assert filled["avg_price"] == 250.1
        assert filled["perm_id"] == 777
        assert filled["order_id"] == 5
        assert filled["completed_status"] == "Filled"
        assert intent["seq"] < placed["seq"] < filled["seq"]
        assert _events(records, "skipped") == []
        assert records[-1]["event"] == "run_end"
        assert records[-1]["exit"] == 0
        assert "execute: AAPL order-filled" in capsys.readouterr().out
        assert "ibkr-state=ORDER_FILLED" in _log_text(tmp_path)
        assert not executor.default_dryrun_ledger_file().exists()

    def test_intent_before_place(self, tmp_path, loop):
        fake = _filling_fake()
        seen = []
        real = fake.placeOrder

        def hook(contract, order):
            if not getattr(order, "whatIf", False):
                seen.append(_read_records(executor.default_ledger_file()))
            return real(contract, order)

        fake.placeOrder = hook
        code, _records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        (on_disk,) = seen
        assert [r["event"] for r in on_disk][-1] == "intent"
        assert on_disk[-1]["decision_key"] == KEY

    def test_the_sent_order_equals_the_preview_order_except_what_if(self, tmp_path, loop):
        fake = _filling_fake()
        code, _records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        (sent,) = fake.placed_orders
        previewed = fake.whatif_calls[-1][1]
        a, b = dict(vars(sent)), dict(vars(previewed))
        assert a.pop("whatIf") is False
        assert b.pop("whatIf") is True
        a.pop("orderId", None)
        b.pop("orderId", None)
        assert a == b

    @pytest.mark.parametrize(
        "case",
        ["short-fill", "wrong-side", "other-ref", "other-con-id", "empty-ref", "order-short"],
    )
    def test_post_order_mismatch_stops_the_whole_run(self, tmp_path, loop, case):
        executions = [_own_fill()]
        completed = _own_completed()
        if case == "short-fill":
            executions = [_own_fill(shares=1)]
        elif case == "wrong-side":
            executions = [_own_fill(side="SLD")]
        elif case == "other-ref":
            executions = [_own_fill(order_ref="2026-10-09|XXXX")]
        elif case == "other-con-id":
            executions = [_own_fill(con_id=999)]
        elif case == "empty-ref":
            executions = [_own_fill(order_ref="")]
        elif case == "order-short":
            completed = _own_completed(filled=1)
        fake = _filling_fake(("AAPL", "MSFT"), executions=executions, completed=completed)
        code, records = _live_run(
            tmp_path,
            loop,
            fake,
            tickers=("AAPL", "MSFT"),
            paper=_two_buys(tmp_path),
        )
        assert code == executor.EXIT_POST_ORDER
        (alarm,) = _events(records, "alarm")
        assert alarm["state"] == "post-order-mismatch"
        assert alarm["decision_key"] == KEY
        assert alarm["expected"]["side"] == "BUY"
        assert alarm["expected"]["quantity"] == 2
        assert alarm["expected"]["order_ref"] == KEY
        assert alarm["expected"]["con_id"] == CON_IDS["AAPL"]
        assert "executions" in alarm["seen"]
        assert records[-1]["event"] == "run_end"
        assert records[-1]["state"] == "post-order-mismatch"
        assert records[-1]["exit"] == executor.EXIT_POST_ORDER
        # MSFT is never sent and never gets an intent.
        assert len(fake.placed_orders) == 1
        assert [r["ticker"] for r in _events(records, "intent")] == ["AAPL"]

    def test_a_status_other_than_filled_ends_in_the_deviation_path(
        self, tmp_path, loop, monkeypatch
    ):
        monkeypatch.setattr(executor, "FILL_TIMEOUT_S", 0.3)
        fake = _fake_for(place_outcome="Submitted")
        code, records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_POST_ORDER
        assert [r["event"] for r in records if r.get("decision_key") == KEY][-2:] == [
            "placed",
            "alarm",
        ]

    def test_executions_that_appear_on_the_second_read_raise_no_alarm(self, tmp_path, loop):
        fake = _filling_fake(executions=[])
        real = fake.reqExecutionsAsync
        reads = []

        async def delayed(execFilter=None):
            if fake.placed_orders:
                reads.append(1)
                if len(reads) >= 2:
                    fake.executions = [_own_fill()]
            return await real(execFilter)

        fake.reqExecutionsAsync = delayed
        code, records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        assert len(reads) >= 2
        assert _events(records, "alarm") == []
        assert [r["exec_id"] for r in _events(records, "filled")] == [EXEC_ID]

    def test_fills_are_persisted_in_the_same_run_for_the_next_day(self, tmp_path, loop):
        fake = _filling_fake()
        code, _records = _live_run(tmp_path, loop, fake)
        assert code == executor.EXIT_OK
        # Next run: the broker's history is empty, the position is held; the ledger alone
        # knows the fills.
        again = _fake_for(positions=[_aapl_position(2)])
        code, records = _live_run(tmp_path, loop, again)
        assert code != executor.EXIT_RECONCILE
        assert again.placed_orders == []
        assert not any(r.get("state") == "source-conflict" for r in records)
        ledger = ledger_mod.Ledger.open(
            executor.default_ledger_file(),
            mode=ledger_mod.MODE_LIVE,
            clock=lambda: OPEN_NOW,
            run_id="check",
        )
        assert ledger.filled_quantity(CON_IDS["AAPL"]) == 2

    def test_place_order_called_at_one_site(self):
        import ast

        tree = ast.parse(Path(executor.__file__).read_text(encoding="utf-8"))
        sites = []

        def walk(node, owner):
            for child in ast.iter_child_nodes(node):
                scope = owner
                if isinstance(child, ast.ClassDef):
                    scope = (child.name, owner[1])
                elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    scope = (owner[0], child.name)
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "place_order"
                ):
                    sites.append(scope)
                walk(child, scope)

        walk(tree, (None, None))
        assert sites == [("LivePlacer", "complete")]
