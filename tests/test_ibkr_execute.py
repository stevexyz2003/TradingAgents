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
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path)
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
            tmp_path, factory, ["AAPL"], paper_log=_buy_paper(tmp_path)
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
        assert intent["rating_source"] is None
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

    def test_the_dry_placer_checks_the_size_a_second_time(self):
        ctx = SimpleNamespace(mods=SimpleNamespace(guards=guards, ledger=ledger_mod), ledger=None)
        intent = {"decision_key": KEY, "ticker": "AAPL", "quantity": guards.MAX_QTY_PER_ORDER + 1}
        with pytest.raises(ValueError, match="size check failed"):
            executor.DryPlacer().complete(ctx, intent)


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
