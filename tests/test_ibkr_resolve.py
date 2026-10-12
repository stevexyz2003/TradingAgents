"""The ``resolve`` command of the IBKR executor, against fakes only.

Every path comes from ``tmp_path``; nothing here reads the operator's ``.env`` or
reaches the gateway. A real connect of the client library is blocked in this
module, and every call of ``main`` gets its own ``--env-file``, ``--log-file``,
``broker_factory`` and ``clock``.
"""

import importlib.util
import json
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

    def test_missing_contracts_file_with_history_does_not_suggest_init(self, tmp_path, capsys):
        path = tmp_path / "ibkr" / "contracts.json"
        path.parent.mkdir(parents=True)
        contracts_mod.contracts_history_path(path).write_text('{"event":"init"}\n', encoding="utf-8")
        factory = _RecordingFactory()
        code, _path, log = _run(tmp_path, factory, ["AAPL"], contracts=path)
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        err = capsys.readouterr().err
        assert "restore contracts.json manually" in err
        assert "resolve --init" not in err
        assert "CONTRACTS_MISSING" in _log_text(log)

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

    def test_init_refuses_history_without_contracts_file(self, tmp_path, capsys):
        path = tmp_path / "ibkr" / "contracts.json"
        path.parent.mkdir(parents=True)
        history = contracts_mod.contracts_history_path(path)
        history.write_text('{"event":"init"}\n', encoding="utf-8")
        factory = _RecordingFactory()
        code, _c, log = _run(tmp_path, factory, ["AAPL"], contracts=path, extra=["--init"])
        assert code == executor.EXIT_PRECONDITION
        assert factory.calls == []
        assert "CONTRACTS_HISTORY_EXISTS" in _log_text(log)
        assert "restore contracts.json manually" in capsys.readouterr().err

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


# --- resolve against FakeIB (D-10 .. D-18, D-22, D-26 .. D-31) -----------------------


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _history(contracts_path):
    history = contracts_mod.contracts_history_path(contracts_path)
    if not history.exists():
        return []
    return [json.loads(x) for x in history.read_text(encoding="utf-8").splitlines()]


def _lines(capsys):
    return [x for x in capsys.readouterr().out.splitlines() if x.startswith("resolve: ")]


class TestInit:
    def test_init_creates_the_file_and_history(self, tmp_path, loop, capsys):
        fake = _fake_for(("AAPL", "MSFT", "NVDA"))
        code, path, log = _run(
            tmp_path, _fake_factory(fake, loop), ["AAPL", "MSFT", "NVDA"], extra=["--init"]
        )
        assert code == executor.EXIT_OK
        data = _json(path)
        assert data["schema_version"] == 1
        assert {t: e["conId"] for t, e in data["contracts"].items()} == CON_IDS
        assert [h["event"] for h in _history(path)] == ["init"] * 3
        assert "reqMarketDataType(3)" in fake.calls
        lines = _lines(capsys)
        assert len(lines) == 3
        assert lines[0].startswith("resolve: AAPL ok conId=265598 NASDAQ/USD/AAPL")

    def test_anchor_mismatch_writes_nothing(self, tmp_path, loop, capsys):
        wrong = ibkr_fakes.stk_contract("AAPL", 111)
        fake = ibkr_fakes.FakeIB(
            qualify={"AAPL": [wrong]},
            details={111: [ibkr_fakes.contract_detail(wrong, liquid_hours=OPEN_HOURS)]},
        )
        code, path, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], extra=["--init"])
        assert code == executor.EXIT_PRECONDITION
        text = _log_text(log)
        assert "ANCHOR_MISMATCH" in text
        assert "265598" in text
        assert "111" in text
        assert not path.exists()
        assert _history(path) == []


class TestRuns:
    def test_unknown_ticker_is_learned(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        fake = _fake_for(("AAPL", "MSFT"))
        code, _c, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL", "MSFT"], contracts=path)
        assert code == executor.EXIT_OK
        assert "learned conId=272093" in _log_text(log)
        assert [h["event"] for h in _history(path)] == ["learn"]
        assert _json(path)["contracts"]["MSFT"]["conId"] == 272093

    def test_second_run_reads_by_con_id_and_changes_nothing(self, tmp_path, loop):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        before = path.read_bytes()
        fake = _fake_for(("AAPL",))
        code, _c, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_OK
        assert "contract_details" in fake.calls
        assert "qualify" in fake.calls
        assert _history(path) == []
        assert path.read_bytes() == before

    def test_drift_is_reported_and_the_file_stays(self, tmp_path, loop, capsys):
        path = _contracts_file(
            tmp_path, {"AAPL": _identity("AAPL", 999999), "MSFT": _identity("MSFT")}
        )
        before = path.read_bytes()
        fake = _fake_for(("AAPL", "MSFT"))
        code, _c, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL", "MSFT"], contracts=path)
        assert code == executor.EXIT_PRECONDITION
        lines = _lines(capsys)
        assert lines[0].startswith("resolve: AAPL drift")
        assert lines[1].startswith("resolve: MSFT ok")
        text = _log_text(log)
        assert "CONTRACT_DRIFT" in text
        assert "999999" in text
        assert path.read_bytes() == before

    def test_ambiguous_candidates_all_land_in_the_log(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"MSFT": _identity("MSFT")})
        cands = [ibkr_fakes.stk_contract("AAPL", n) for n in (111, 222, 333)]
        fake = ibkr_fakes.FakeIB(qualify={"AAPL": cands})
        code, _c, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_PRECONDITION
        assert _lines(capsys)[0].startswith("resolve: AAPL ambiguous")
        row = next(x for x in _log_text(log).splitlines() if "AMBIGUOUS_CONTRACT" in x)
        for con_id in (111, 222, 333):
            assert f"conId={con_id}" in row

    def test_rebaseline_shows_old_and_new(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL", 999999)})
        fake = _fake_for(("AAPL",))
        code, _c, _l = _run(
            tmp_path,
            _fake_factory(fake, loop),
            ["AAPL"],
            contracts=path,
            extra=["--rebaseline", "AAPL"],
        )
        assert code == executor.EXIT_OK
        out = capsys.readouterr().out
        assert "999999" in out
        assert "265598" in out
        assert _json(path)["contracts"]["AAPL"]["conId"] == 265598
        rows = _history(path)
        assert [h["event"] for h in rows] == ["rebaseline"]
        assert rows[0]["old"]["conId"] == 999999

    def test_value_only_listing_is_not_tradable(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        fake = _fake_for(("AAPL",), valid_exchanges="VALUE")
        code, _c, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_PRECONDITION
        assert _lines(capsys)[0].startswith("resolve: AAPL not-tradable")

    def test_closed_with_a_next_window_is_exit_0(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        fake = _fake_for(("AAPL",), liquid_hours=CLOSED_HOURS)
        code, _c, _l = _run(
            tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path, clock=CLOSED_NOW
        )
        assert code == executor.EXIT_OK
        line = _lines(capsys)[0]
        assert "closed" in line
        assert "next window 2026-10-12T" in line

    def test_empty_hours_are_session_unknown(self, tmp_path, loop, capsys):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        fake = _fake_for(("AAPL",), liquid_hours="")
        code, _c, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_PRECONDITION
        assert _lines(capsys)[0].startswith("resolve: AAPL session-unknown")


class TestOutputAndPersistence:
    def test_out_file_schema_and_no_session_values(self, tmp_path, loop):
        out = tmp_path / "res" / "resolve.json"
        out.parent.mkdir(parents=True)
        out.write_text("stale", encoding="utf-8")
        fake = _fake_for(("AAPL",), liquid_hours=OPEN_HOURS)
        code, path, _log = _run(
            tmp_path, _fake_factory(fake, loop), ["AAPL"], extra=["--init", "--out", str(out)]
        )
        assert code == executor.EXIT_OK
        data = _json(out)
        assert data["schema_version"] == 1
        assert data["as_of"] == OPEN_NOW.isoformat()
        (row,) = data["results"]
        assert set(row) == {
            "ticker",
            "state",
            "detail",
            "conId",
            "primaryExchange",
            "currency",
            "localSymbol",
            "window_start",
            "window_end",
            "next_open",
        }
        assert row["conId"] == 265598
        assert list(out.parent.glob("*.tmp")) == []
        for file in (path, contracts_mod.contracts_history_path(path), out):
            text = file.read_text(encoding="utf-8")
            # The verdict text may say "a liquid window"; the broker's hours must not appear.
            assert "liquidhours" not in text.lower()
            assert "tradinghours" not in text.lower()
            assert OPEN_HOURS not in text
            assert "0930" not in text

    def test_previous_out_file_is_removed_on_failure(self, tmp_path):
        out = tmp_path / "resolve.json"
        out.write_text("stale", encoding="utf-8")
        code, _p, _l = _run(tmp_path, _RecordingFactory(), ["AAPL"], extra=["--out", str(out)])
        assert code == executor.EXIT_PRECONDITION  # contracts file missing
        assert not out.exists()

    def test_contracts_are_written_after_the_session_closed(self, tmp_path, loop, monkeypatch):
        fake = _fake_for(("AAPL",))
        seen = []
        original = contracts_mod.commit_contracts

        def spy(*args, **kwargs):
            seen.append(list(fake.calls))
            return original(*args, **kwargs)

        monkeypatch.setattr(contracts_mod, "commit_contracts", spy)
        code, _p, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], extra=["--init"])
        assert code == executor.EXIT_OK
        assert seen and "disconnect" in seen[0]

    def test_commit_failure_is_exit_1_without_traceback(self, tmp_path, loop, monkeypatch, capsys):
        fake = _fake_for(("AAPL",))

        def boom(*_a, **_k):
            raise PermissionError("denied")

        monkeypatch.setattr(contracts_mod, "commit_contracts", boom)
        code, _p, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], extra=["--init"])
        assert code == executor.EXIT_CONFIG
        assert "OUTPUT_INVALID" in _log_text(log)
        assert "Traceback" not in capsys.readouterr().err

    def test_commit_validation_failure_is_exit_1_without_traceback(
        self, tmp_path, loop, monkeypatch, capsys
    ):
        fake = _fake_for(("AAPL",))

        def boom(*_a, **_k):
            raise contracts_mod.ContractsFileError("bad contracts")

        monkeypatch.setattr(contracts_mod, "commit_contracts", boom)
        code, _p, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], extra=["--init"])
        assert code == executor.EXIT_CONFIG
        assert "OUTPUT_INVALID" in _log_text(log)
        assert "unexpected" not in capsys.readouterr().err


class TestGatewayFailures:
    def _existing(self, tmp_path):
        path = _contracts_file(tmp_path, {"AAPL": _identity("AAPL")})
        return path, path.read_bytes()

    def test_unreachable_gateway_is_exit_3(self, tmp_path, loop):
        path, before = self._existing(tmp_path)
        fake = ibkr_fakes.FakeIB(refuse=ConnectionRefusedError())
        code, _c, log = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_GATEWAY
        assert "GATEWAY_UNREACHABLE" in _log_text(log)
        assert path.read_bytes() == before

    def test_guard_violation_is_exit_8_before_any_request(self, tmp_path, loop):
        path, before = self._existing(tmp_path)
        fake = ibkr_fakes.FakeIB(accounts=("U1234567",))
        code, _c, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_ACCOUNT_GUARD
        assert "reqMarketDataType(3)" not in fake.calls
        assert path.read_bytes() == before

    def test_unhealthy_probe_is_exit_3(self, tmp_path, loop):
        path, before = self._existing(tmp_path)
        fake = ibkr_fakes.FakeIB(probe="empty")
        code, _c, _l = _run(tmp_path, _fake_factory(fake, loop), ["AAPL"], contracts=path)
        assert code == executor.EXIT_GATEWAY
        assert path.read_bytes() == before
