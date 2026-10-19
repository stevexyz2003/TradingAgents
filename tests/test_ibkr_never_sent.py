# ruff: noqa: F811 - fixtures imported from test_ibkr_execute are re-used as arguments
"""``execute --resolve KEY=never_sent --note TEXT`` (phase 6, D-14, T-06-34..38).

Only fakes: no test connects to a real gateway, and conftest points LOCALAPPDATA at tmp_path.
"""

from __future__ import annotations

import pytest

from tests import ibkr_fakes
from tests.test_ibkr_execute import (  # noqa: F401 - fixtures used by name
    CON_IDS,
    KEY,
    OPEN_NOW,
    SHA,
    _aapl_position,
    _block_real_connect,
    _close_logging,
    _env_file,
    _fake_factory,
    _fake_for,
    _fixed,
    _live_run,
    _local_app_data,
    _log_file,
    _log_text,
    _pin_modules,
    _read_records,
    _RecordingFactory,
    executor,
    ledger_mod,
    loop,
)

pytestmark = pytest.mark.unit

NOTE = "crash before send"
_CON = CON_IDS["AAPL"]


def _live_ledger(*, placed: bool = False, closed: bool = False, ids: bool = False, fills=()):
    """Write the live ledger a crashed run would have left: an intent for KEY.

    ``ids`` puts the broker's ids on the ``placed`` line (as the live placer writes it);
    ``fills`` are BUY quantities of an earlier, filled key of the same conId.
    """
    path = executor.default_ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    led = ledger_mod.Ledger.open(
        path, mode=ledger_mod.MODE_LIVE, clock=_fixed(OPEN_NOW), run_id="crashed"
    )
    fields = ledger_mod.intent_record(
        decision_key=KEY,
        ticker="AAPL",
        trade_date="2026-10-09",
        rating="Buy",
        paper_log_sha=SHA,
        side="BUY",
        quantity=2,
        con_id=_CON,
        order_ref=KEY,
        weekend_gap=False,
    )
    for number, quantity in enumerate(fills):
        led.append(
            ledger_mod.FILLED,
            decision_key="2026-10-08|AAPL",
            ticker="AAPL",
            con_id=_CON,
            side="BUY",
            exec_id=f"0000e0d5.0000000{number}.01.01",
            filled_qty=float(quantity),
        )
    led.append(ledger_mod.INTENT, **fields)
    follow = {"decision_key": KEY, "ticker": "AAPL"}
    if placed:
        extra = {"order_id": 5, "perm_id": 777} if ids else {}
        led.append(ledger_mod.PLACED, **follow, **extra)
    if closed:
        led.append(ledger_mod.REJECTED, **follow)
    return path


def _resolve(tmp_path, loop, fake=None, *, arg=f"{KEY}=never_sent", note=NOTE, extra=()):
    argv = ["execute", "--resolve", arg]
    if note is not None:
        argv += ["--note", note]
    argv += [
        "--env-file",
        str(_env_file(tmp_path)),
        "--log-file",
        str(_log_file(tmp_path)),
        *extra,
    ]
    factory = _fake_factory(fake, loop) if fake is not None else _RecordingFactory()
    code = executor.main(argv, broker_factory=factory, clock=_fixed(OPEN_NOW))
    executor.close_logging()
    return code


def _events(path, name):
    return [r for r in _read_records(path) if r["event"] == name]


def test_resolve_closes_an_intent_without_trace_and_appends_one_line(tmp_path, loop, capsys):
    path = _live_ledger()
    before = path.read_bytes()
    fake = _fake_for()
    assert _resolve(tmp_path, loop, fake) == executor.EXIT_OK
    after = path.read_bytes()
    assert after.startswith(before)
    assert after[len(before) :].count(b"\n") == 1
    (resolved,) = _events(path, "resolved")
    assert resolved["decision_key"] == KEY
    assert resolved["outcome"] == "never_sent"
    assert resolved["note"] == NOTE
    assert resolved["source"] == "operator"
    assert f"ibkr-state=RESOLVED_BY_OPERATOR key={KEY}" in _log_text(tmp_path)
    assert f"execute: resolved {KEY} as never_sent" in capsys.readouterr().out
    assert "placeOrder" not in fake.calls


def test_after_resolve_the_next_run_is_not_blocked_and_sends_nothing(tmp_path, loop):
    _live_ledger()
    assert _resolve(tmp_path, loop, _fake_for()) == executor.EXIT_OK
    fake = _fake_for()
    code, records = _live_run(tmp_path, loop, fake)
    assert code != executor.EXIT_RECONCILE
    assert [r["event"] for r in records].count("intent") == 1
    assert any(r.get("reason") == "already_attempted" for r in records if r["event"] == "skipped")
    assert "placeOrder" not in fake.calls


def test_resolve_unknown_key_is_exit_two(tmp_path, loop):
    _live_ledger()
    code = _resolve(tmp_path, loop, _fake_for(), arg="2026-10-10|AAPL=never_sent")
    assert code == executor.EXIT_PRECONDITION
    assert not _events(executor.default_ledger_file(), "resolved")
    assert "RESOLVE_NOT_OPEN" in _log_text(tmp_path)


def test_resolve_after_placed_is_exit_two(tmp_path, loop):
    _live_ledger(placed=True)
    code = _resolve(tmp_path, loop, _fake_for())
    assert code == executor.EXIT_PRECONDITION
    assert "RESOLVE_NOT_INTENT" in _log_text(tmp_path)
    assert not _events(executor.default_ledger_file(), "resolved")


def test_resolve_closed_key_is_exit_two(tmp_path, loop):
    _live_ledger(closed=True)
    code = _resolve(tmp_path, loop, _fake_for())
    assert code == executor.EXIT_PRECONDITION
    assert "RESOLVE_NOT_OPEN" in _log_text(tmp_path)


@pytest.mark.parametrize(
    "broker",
    [
        {"open_orders": [ibkr_fakes.open_trade(_CON, order_ref=KEY, quantity=2)]},
        {
            "completed_orders": [
                ibkr_fakes.completed_trade(_CON, "Cancelled", order_ref=KEY, quantity=2)
            ]
        },
        {"executions": [ibkr_fakes.fill(_CON, KEY, 2)]},
    ],
    ids=["open", "completed", "execution"],
)
def test_resolve_with_a_trace_at_the_broker_is_exit_six(tmp_path, loop, capsys, broker):
    path = _live_ledger()
    before = path.read_bytes()
    code = _resolve(tmp_path, loop, _fake_for(**broker))
    assert code == executor.EXIT_RECONCILE
    assert path.read_bytes() == before
    assert "RESOLVE_HAS_TRACE" in _log_text(tmp_path)
    assert "normal reconciliation" in capsys.readouterr().err


def test_resolve_other_outcome_is_exit_one(tmp_path, loop):
    path = _live_ledger()
    before = path.read_bytes()
    assert _resolve(tmp_path, loop, arg=f"{KEY}=filled") == executor.EXIT_CONFIG
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "note",
    [None, "", "   ", "x" * 501, "bad\nnote", "tab\there"],
    ids=["missing", "empty", "blank", "too-long", "newline", "tab"],
)
def test_resolve_bad_note_is_exit_one(tmp_path, loop, note):
    path = _live_ledger()
    before = path.read_bytes()
    assert _resolve(tmp_path, loop, note=note) == executor.EXIT_CONFIG
    assert path.read_bytes() == before


def test_resolve_note_of_500_characters_is_accepted(tmp_path, loop):
    _live_ledger()
    assert _resolve(tmp_path, loop, _fake_for(), note="x" * 500) == executor.EXIT_OK


@pytest.mark.parametrize("extra", [("AAPL",), ("--live",)], ids=["ticker", "live"])
def test_resolve_with_ticker_or_live_is_exit_one(tmp_path, loop, extra):
    _live_ledger()
    assert _resolve(tmp_path, loop, extra=extra) == executor.EXIT_CONFIG


@pytest.mark.parametrize(
    "arg",
    ["AAPL=never_sent", "2026-10-09|aapl=never_sent", "2026-13-09|AAPL=never_sent", "=never_sent"],
    ids=["no-date", "lowercase-ticker", "bad-date", "empty"],
)
def test_resolve_key_outside_the_whitelist_is_exit_one(tmp_path, loop, arg):
    _live_ledger()
    assert _resolve(tmp_path, loop, arg=arg) == executor.EXIT_CONFIG


def test_resolve_with_the_lock_held_is_exit_seven(tmp_path, loop):
    from tradingagents.dataflows import files

    path = _live_ledger()
    before = path.read_bytes()
    with files.locked(path, wait=False) as held:
        assert held
        code = _resolve(tmp_path, loop)
    assert code == executor.EXIT_LOCKED
    assert path.read_bytes() == before


def test_note_without_resolve_is_exit_one(tmp_path):
    argv = ["execute", "AAPL", "--note", "x", "--log-file", str(_log_file(tmp_path))]
    assert executor.main(argv) == executor.EXIT_CONFIG
    executor.close_logging()


# --- expired_unfilled and the broker guard (WR-03) ---------------------------------------

EXPIRED = f"{KEY}=expired_unfilled"


def test_expired_unfilled_closes_a_placed_entry_and_the_next_run_is_not_blocked(
    tmp_path, loop, capsys
):
    path = _live_ledger(placed=True, ids=True)
    before = path.read_bytes()
    fake = _fake_for()
    assert _resolve(tmp_path, loop, fake, arg=EXPIRED) == executor.EXIT_OK
    after = path.read_bytes()
    assert after.startswith(before)
    assert after[len(before) :].count(b"\n") == 1
    (resolved,) = _events(path, "resolved")
    assert resolved["outcome"] == "expired_unfilled"
    assert resolved["note"] == NOTE
    assert resolved["source"] == "operator"
    assert f"execute: resolved {KEY} as expired_unfilled" in capsys.readouterr().out
    assert "positions" in fake.calls
    assert "placeOrder" not in fake.calls
    again = _fake_for()
    code, records = _live_run(tmp_path, loop, again)
    assert code != executor.EXIT_RECONCILE
    assert any(r.get("reason") == "already_attempted" for r in records if r["event"] == "skipped")
    assert "placeOrder" not in again.calls


def test_expired_unfilled_on_an_intent_entry_is_exit_two(tmp_path, loop):
    path = _live_ledger()
    before = path.read_bytes()
    assert _resolve(tmp_path, loop, _fake_for(), arg=EXPIRED) == executor.EXIT_PRECONDITION
    assert path.read_bytes() == before
    assert "RESOLVE_NOT_PLACED" in _log_text(tmp_path)


@pytest.mark.parametrize(
    "broker",
    [
        {"open_orders": [ibkr_fakes.open_trade(_CON, order_ref=KEY, quantity=2)]},
        {"open_orders": [ibkr_fakes.open_trade(_CON, order_ref="", quantity=2, perm_id=777)]},
        {"open_orders": [ibkr_fakes.open_trade(_CON, order_ref="", quantity=2, order_id=5)]},
        {"executions": [ibkr_fakes.fill(_CON, KEY, 2)]},
        {"executions": [ibkr_fakes.fill(_CON, "", 2, perm_id=777)]},
    ],
    ids=["open-by-ref", "open-by-perm-id", "open-by-order-id", "exec-by-ref", "exec-by-perm-id"],
)
def test_expired_unfilled_with_a_matching_order_or_execution_is_refused(tmp_path, loop, broker):
    path = _live_ledger(placed=True, ids=True)
    before = path.read_bytes()
    code = _resolve(tmp_path, loop, _fake_for(**broker), arg=EXPIRED)
    assert code == executor.EXIT_RECONCILE
    assert path.read_bytes() == before
    assert "RESOLVE_HAS_TRACE" in _log_text(tmp_path)


@pytest.mark.parametrize("arg", [EXPIRED, f"{KEY}=never_sent"], ids=["expired", "never-sent"])
def test_resolve_with_unaccounted_shares_at_the_broker_is_refused(tmp_path, loop, capsys, arg):
    path = _live_ledger(placed=arg == EXPIRED, ids=True)
    before = path.read_bytes()
    code = _resolve(tmp_path, loop, _fake_for(positions=[_aapl_position(2)]), arg=arg)
    assert code == executor.EXIT_RECONCILE
    assert path.read_bytes() == before
    assert "RESOLVE_POSITION_MISMATCH" in _log_text(tmp_path)
    assert "unaccounted shares" in capsys.readouterr().err


@pytest.mark.parametrize("arg", [EXPIRED, f"{KEY}=never_sent"], ids=["expired", "never-sent"])
def test_resolve_with_the_position_matching_the_ledger_fills_is_accepted(tmp_path, loop, arg):
    _live_ledger(placed=arg == EXPIRED, ids=True, fills=(1, 1))
    fake = _fake_for(positions=[_aapl_position(2)])
    assert _resolve(tmp_path, loop, fake, arg=arg) == executor.EXIT_OK


@pytest.mark.parametrize("arg", [EXPIRED, f"{KEY}=never_sent"], ids=["expired", "never-sent"])
@pytest.mark.parametrize("hang", ["positions", "open_orders"])
def test_resolve_with_an_unreadable_broker_is_refused(tmp_path, loop, arg, hang):
    path = _live_ledger(placed=arg == EXPIRED, ids=True)
    before = path.read_bytes()
    code = _resolve(tmp_path, loop, _fake_for(**{hang: "hang"}), arg=arg)
    assert code == executor.EXIT_GATEWAY
    assert path.read_bytes() == before
    assert not _events(path, "resolved")


def test_resolve_last_event_table_matches_the_ledger_module():
    assert set(executor.RESOLVE_LAST_EVENT) == ledger_mod.RESOLVE_OUTCOMES
    assert executor.RESOLVE_LAST_EVENT[ledger_mod.NEVER_SENT] == ledger_mod.INTENT
    assert executor.RESOLVE_LAST_EVENT[ledger_mod.EXPIRED_UNFILLED] == ledger_mod.PLACED
