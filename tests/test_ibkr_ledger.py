"""Unit tests for the append-only execution ledger (scripts/ibkr_ledger.py)."""

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


led = _load("ibkr_ledger")
dec = _load("ibkr_decision")

CLOCK = lambda: datetime(2026, 10, 16, 17, 21, tzinfo=UTC)  # noqa: E731


def _open(path, mode="dryrun", run_id="r1"):
    return led.Ledger.open(path, mode=mode, clock=CLOCK, run_id=run_id)


def _intent(key, **over):
    fields = {
        "decision_key": key,
        "ticker": key.split("|")[-1],
        "trade_date": "2026-10-09",
        "rating": "Buy",
        "paper_log_sha": "abc",
        "side": "BUY",
        "quantity": 2,
        "con_id": 265598,
        "order_ref": key,
        "weekend_gap": False,
    }
    fields.update(over)
    return led.intent_record(**fields)


def _lines(path):
    return Path(path).read_bytes().split(b"\n")


# --- append / durability ------------------------------------------------------------------


def test_ledger_append_writes_one_compact_sorted_line(tmp_path):
    path = tmp_path / "ledger-dryrun.jsonl"
    ledger = _open(path)
    assert ledger.records == []
    record = ledger.append("run_start", release="release-ok")
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    text = raw.decode("utf-8")
    assert ", " not in text and ": " not in text
    assert json.loads(text) == record
    assert record["v"] == 1 and record["seq"] == 1
    assert record["ts"] == "2026-10-16T17:21:00+00:00"
    assert record["run_id"] == "r1" and record["mode"] == "dryrun"
    assert record["event"] == "run_start"
    keys = list(json.loads(text))
    assert keys == sorted(keys)


def test_ledger_write_ahead_fsync_once_per_append(tmp_path, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    ledger = _open(tmp_path / "l.jsonl")
    ledger.append("run_start")
    ledger.append("intent", **_intent("2026-10-09|AAPL"))
    assert len(calls) == 2


def test_negative_control_write_ahead_fsync_per_append(tmp_path, monkeypatch):
    ledger = _open(tmp_path / "l.jsonl")

    def boom(fd):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError, match="disk gone"):
        ledger.append("intent", **_intent("2026-10-09|AAPL"))
    assert ledger.records == []
    assert ledger.unresolved() == []


def test_ledger_seq_continues_after_reopen(tmp_path):
    path = tmp_path / "l.jsonl"
    first = _open(path)
    first.append("run_start")
    first.append("run_end")
    second = _open(path, run_id="r2")
    assert len(second.records) == 2
    assert second.append("run_start")["seq"] == 3


def test_ledger_torn_tail_invalid_fragment_is_tolerated(tmp_path):
    path = tmp_path / "l.jsonl"
    good = _open(path)
    good.append("run_start")
    good.append("run_end")
    with open(path, "ab") as fh:
        fh.write(b'{"v":1,"seq":3,"ts":"2026')
    ledger = _open(path)
    assert [r["seq"] for r in ledger.records] == [1, 2]
    appended = ledger.append("run_start")
    assert appended["seq"] == 3
    assert appended[led.SEALS_LINE] == 3
    # The closed fragment sits mid-file now, but its seal follows directly: still readable.
    again = _open(path)
    assert [r["seq"] for r in again.records] == [1, 2, 3]
    assert led.SEALS_LINE not in again.append("run_end")


def test_ledger_broken_middle_line_without_matching_seal_is_ledger_error(tmp_path):
    path = tmp_path / "l.jsonl"
    head = {"v": 1, "seq": 1, "ts": "x", "run_id": "r", "mode": "dryrun", "event": "run_start"}
    tail = {"v": 1, "seq": 2, "ts": "x", "run_id": "r", "mode": "dryrun", "event": "run_end"}
    for seal in (None, 1, 3):
        follow = tail if seal is None else {**tail, led.SEALS_LINE: seal}
        rows = [json.dumps(head).encode(), b'{"v":1,"seq":2', json.dumps(follow).encode()]
        path.write_bytes(b"\n".join(rows) + b"\n")
        with pytest.raises(led.LedgerError, match="line 2"):
            _open(path)


def test_ledger_torn_tail_fragment_gets_closed_before_next_append(tmp_path):
    path = tmp_path / "l.jsonl"
    good = _open(path)
    good.append("run_start")
    with open(path, "ab") as fh:
        fh.write(b'{"v":1,"seq":2')
    ledger = _open(path)
    ledger.append("run_end")
    lines = [ln for ln in _lines(path) if ln]
    assert len(lines) == 3
    assert lines[1] == b'{"v":1,"seq":2'
    assert json.loads(lines[2])["event"] == "run_end"


def test_ledger_valid_last_line_without_newline_counts_and_is_closed(tmp_path):
    path = tmp_path / "l.jsonl"
    good = _open(path)
    good.append("run_start")
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    ledger = _open(path)
    assert len(ledger.records) == 1
    ledger.append("run_end")
    reopened = _open(path)
    assert [r["event"] for r in reopened.records] == ["run_start", "run_end"]
    assert reopened.records[1]["seq"] == 2


def test_ledger_mid_file_garbage_is_ledger_error(tmp_path):
    path = tmp_path / "l.jsonl"
    good = _open(path)
    good.append("run_start")
    with open(path, "ab") as fh:
        fh.write(b"not json\n")
    with open(path, "ab") as fh:
        fh.write(b'{"event":"run_end","mode":"dryrun","run_id":"r","seq":3,"ts":"t","v":1}\n')
    with pytest.raises(led.LedgerError, match="line 2"):
        _open(path)


def test_ledger_blank_line_in_the_middle_is_ledger_error(tmp_path):
    path = tmp_path / "l.jsonl"
    line = b'{"event":"run_start","mode":"dryrun","run_id":"r","seq":1,"ts":"t","v":1}\n'
    path.write_bytes(line + b"\n" + line)
    with pytest.raises(led.LedgerError, match="line 2"):
        _open(path)


@pytest.mark.parametrize(
    "line",
    [
        b'{"event":"run_start","run_id":"r","seq":1,"ts":"t","v":1}\n',
        b'{"event":"bogus","mode":"dryrun","run_id":"r","seq":1,"ts":"t","v":1}\n',
        b'{"event":"run_start","mode":"dryrun","run_id":"r","seq":1,"ts":"t","v":2}\n',
        b"[1,2]\n",
    ],
)
def test_ledger_bad_record_shape_is_ledger_error(tmp_path, line):
    path = tmp_path / "l.jsonl"
    path.write_bytes(line)
    with pytest.raises(led.LedgerError):
        _open(path)


_BASE = {"v": 1, "seq": 1, "ts": "t", "run_id": "r", "mode": "dryrun", "event": "run_start"}
_GOOD_INTENT = {**_BASE, "event": "intent", **_intent("2026-10-09|AAPL")}


@pytest.mark.parametrize(
    "record",
    [
        {**_BASE, "seq": "x"},
        {**_BASE, "seq": None},
        {**_BASE, "seq": 1.5},
        {**_BASE, "seq": True},
        {**_BASE, "seq": 0},
        {k: v for k, v in _BASE.items() if k != "seq"},
        {**_BASE, "ts": None},
        {**_BASE, "run_id": 7},
        {**_BASE, "decision_key": 5},
        {k: v for k, v in _GOOD_INTENT.items() if k != "side"},
        {k: v for k, v in _GOOD_INTENT.items() if k != "quantity"},
        {k: v for k, v in _GOOD_INTENT.items() if k != "con_id"},
        {k: v for k, v in _GOOD_INTENT.items() if k != "decision_key"},
        {k: v for k, v in _GOOD_INTENT.items() if k != "rating"},
        {**_GOOD_INTENT, "side": "HOLD"},
        {**_GOOD_INTENT, "quantity": "2"},
        {**_GOOD_INTENT, "quantity": True},
        {**_GOOD_INTENT, "quantity": -1},
        {**_GOOD_INTENT, "con_id": "265598"},
        {**_GOOD_INTENT, "con_id": 265598.0},
        {**_GOOD_INTENT, "order_ref": 3},
        {**_BASE, "event": "filled", "decision_key": "K", "filled_qty": "2"},
        {**_BASE, "event": "skipped", "decision_key": "K", "reason": "bogus"},
    ],
)
def test_ledger_malformed_record_is_ledger_error(tmp_path, record):
    """CR-01: every malformed record is a LedgerError at open, never a crash later."""
    path = tmp_path / "l.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(led.LedgerError, match="line 1"):
        _open(path)


def test_ledger_well_formed_intent_is_accepted(tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text(json.dumps(_GOOD_INTENT) + "\n", encoding="utf-8")
    assert [e["decision_key"] for e in _open(path).unresolved()] == ["2026-10-09|AAPL"]


def test_dryrun_line_in_live_ledger_is_ledger_error(tmp_path):
    path = tmp_path / "ledger.jsonl"
    _open(path, mode="dryrun").append("run_start")
    with pytest.raises(led.LedgerError, match="dryrun"):
        _open(path, mode="live")


def test_live_line_in_dryrun_ledger_is_ledger_error(tmp_path):
    path = tmp_path / "ledger-dryrun.jsonl"
    _open(path, mode="live").append("run_start")
    with pytest.raises(led.LedgerError, match="live"):
        _open(path, mode="dryrun")


def test_ledger_open_rejects_unknown_mode(tmp_path):
    with pytest.raises(ValueError):
        _open(tmp_path / "l.jsonl", mode="paper")


def test_ledger_append_validates_event_and_reason(tmp_path):
    ledger = _open(tmp_path / "l.jsonl")
    with pytest.raises(ValueError):
        ledger.append("bogus")
    with pytest.raises(ValueError):
        ledger.append("skipped", decision_key="K", reason="foo")
    with pytest.raises(ValueError):
        ledger.append("skipped", decision_key="K")
    assert ledger.records == []


# --- state per decision_key -----------------------------------------------------------------


def test_ledger_state_per_key_skipped_does_not_consume(tmp_path):
    ledger = _open(tmp_path / "l.jsonl")
    ledger.append("intent", **_intent("K1"))
    ledger.append("dry_complete", decision_key="K1")
    ledger.append("intent", **_intent("K2"))
    ledger.append("skipped", decision_key="K3", reason="hold")
    assert ledger.last_event("K1")["event"] == "dry_complete"
    assert ledger.attempt_of("K1")["event"] == "intent"
    assert ledger.attempt_of("K3") is None
    assert ledger.last_event("K3") is None
    assert [e["decision_key"] for e in ledger.unresolved()] == ["K2"]


def test_ledger_reconcile_and_skipped_do_not_close_an_open_intent(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger = _open(path)
    ledger.append("intent", **_intent("K2"))
    ledger.append("reconcile", decision_key="K2", outcome="no_trace")
    ledger.append("skipped", decision_key="K2", reason="already_attempted")
    ledger.append("switch_check", decision_key="K2")
    assert ledger.last_event("K2")["event"] == "intent"
    assert [e["decision_key"] for e in ledger.unresolved()] == ["K2"]
    reopened = _open(path, run_id="r2")
    assert reopened.last_event("K2")["event"] == "intent"
    assert [e["decision_key"] for e in reopened.unresolved()] == ["K2"]
    reopened.append("dry_complete", decision_key="K2")
    assert reopened.unresolved() == []
    assert _open(path, run_id="r3").unresolved() == []


def test_ledger_placed_stays_open_until_filled(tmp_path):
    ledger = _open(tmp_path / "l.jsonl", mode="live")
    ledger.append("intent", **_intent("K1"))
    ledger.append("placed", decision_key="K1")
    assert [e["decision_key"] for e in ledger.unresolved()] == ["K1"]
    ledger.append("filled", decision_key="K1", con_id=265598, filled_qty=2)
    assert ledger.unresolved() == []


def test_ledger_rejected_or_skipped_without_intent_is_not_open(tmp_path):
    ledger = _open(tmp_path / "l.jsonl")
    ledger.append("rejected", decision_key="K4", state="over-budget")
    ledger.append("skipped", decision_key="K5", reason="hold")
    assert ledger.unresolved() == []
    assert ledger.attempt_of("K4") is None
    assert ledger.attempt_of("K5") is None


def test_ledger_filled_quantity_sums_filled_and_partial(tmp_path):
    ledger = _open(tmp_path / "l.jsonl", mode="live")
    assert ledger.filled_quantity(265598) == 0.0
    ledger.append("filled", decision_key="K1", con_id=265598, filled_qty=2)
    ledger.append("partial", decision_key="K2", con_id=265598, filled_qty=1)
    ledger.append("filled", decision_key="K3", con_id=1, filled_qty=5)
    assert ledger.filled_quantity(265598) == 3.0


def test_ledger_intent_record_has_required_fields():
    record = _intent("2026-10-09|AAPL", weekend_gap=True)
    for name in (
        "decision_key",
        "ticker",
        "trade_date",
        "rating",
        "paper_log_sha",
        "side",
        "quantity",
        "con_id",
        "order_ref",
        "weekend_gap",
        "rating_source",
    ):
        assert name in record
    assert record["rating_source"] is None
    assert record["weekend_gap"] is True


# --- reasons --------------------------------------------------------------------------------


def test_ledger_reason_for_state():
    assert led.reason_for_state("skipped-hold") == "hold"
    assert led.reason_for_state("calendar-conflict") == "source_conflict"
    assert led.reason_for_state("release-expired") == "kill_switch"
    with pytest.raises(KeyError):
        led.reason_for_state("bogus")


def test_ledger_every_decision_state_has_a_reason_or_is_a_verdict():
    assert not set(led.REASON_BY_STATE) & led.REJECTED_STATES
    assert "halted" in led.REJECTED_STATES and "halted" not in led.REASON_BY_STATE
    assert set(led.REASON_BY_STATE.values()) <= led.REASONS
    for state in dec.EXIT_BY_STATE:
        if state == "preview-ok":
            continue
        assert state in led.REASON_BY_STATE or state in led.REJECTED_STATES, state
    ticker_end_states = (
        "size-cap",
        "outside-session",
        "source-conflict",
        "already-attempted",
        "decision-changed",
        "kill-active",
        "kill-unreadable",
        "release-missing",
        "release-unreadable",
        "release-invalid",
        "release-expired",
        "release-account-mismatch",
    )
    guards = _load("ibkr_guards")
    for state in ticker_end_states:
        assert state in led.REASON_BY_STATE, state
        assert state in guards.EXIT_BY_STATE, state
    # The other guard states are no ticker end: exit 0 states, or run-level stops
    # (lock, ledger, reconciliation, account conflict per D-11, state in git, not dry).
    for state in guards.EXIT_BY_STATE:
        if state not in ticker_end_states:
            assert state not in led.REASON_BY_STATE, state


def test_ledger_weekend_gap_is_a_field_not_a_reason():
    assert "weekend_gap" not in led.REASONS


# --- state outside git ----------------------------------------------------------------------


def test_git_state_under_a_git_directory_is_refused(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(led.StateInGitTree):
        led.ensure_outside_git(tmp_path / "a" / "b")


def test_git_state_under_a_worktree_git_file_is_refused(tmp_path):
    (tmp_path / ".git").write_text("gitdir: elsewhere\n")
    with pytest.raises(led.StateInGitTree):
        led.ensure_outside_git(tmp_path / "a" / "b")


def test_git_state_without_dot_git_is_accepted(tmp_path):
    led.ensure_outside_git(tmp_path / "a" / "b")


def test_git_state_inside_this_repo_is_refused():
    with pytest.raises(led.StateInGitTree):
        led.ensure_outside_git(Path(__file__).resolve().parents[1] / "x")


def test_git_state_stat_error_fails_closed(tmp_path, monkeypatch):
    def boom(path, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(os, "stat", boom)
    with pytest.raises(led.StateInGitTree, match="denied"):
        led.ensure_outside_git(tmp_path / "a")


# --- reconciliation ---------------------------------------------------------------------------

REF = "2026-10-09|AAPL"
ENTRY = {"decision_key": REF, "order_ref": REF, "con_id": 265598, "side": "BUY", "quantity": 2}


def _order(status="Submitted", filled=None, ref=REF, con_id=265598, action="BUY", qty=2.0):
    return SimpleNamespace(
        order_ref=ref,
        con_id=con_id,
        action=action,
        quantity=qty,
        status=status,
        filled=filled,
        perm_id=1,
        order_id=2,
    )


def _exe(shares, ref=REF, con_id=265598, side="BUY", exec_id="e1"):
    return SimpleNamespace(
        order_ref=ref, con_id=con_id, side=side, shares=shares, exec_id=exec_id, perm_id=1
    )


def _hist(open=(), completed=(), executions=()):
    return SimpleNamespace(open=list(open), completed=list(completed), executions=list(executions))


def test_reconcile_no_trace_is_unresolvable():
    res = led.resolve_entry(ENTRY, _hist())
    assert res.outcome == led.NO_TRACE and res.outcome in led.UNRESOLVABLE
    assert "open=0 completed=0 executions=0" in res.detail
    assert (res.open, res.completed, res.executions) == (0, 0, 0)


def test_reconcile_open_order():
    res = led.resolve_entry(ENTRY, _hist(open=[_order()]))
    assert res.outcome == led.OPEN and res.open == 1


def test_reconcile_executions_full_and_partial():
    assert led.resolve_entry(ENTRY, _hist(executions=[_exe(2)])).outcome == led.FILLED_OUT
    assert led.resolve_entry(ENTRY, _hist(executions=[_exe(1)])).outcome == led.PARTIAL_OUT
    two = _hist(executions=[_exe(1, exec_id="a"), _exe(1, exec_id="b")])
    assert led.resolve_entry(ENTRY, two).outcome == led.FILLED_OUT


def test_reconcile_completed_filled_with_executions():
    hist = _hist(completed=[_order("Filled", filled=2.0)], executions=[_exe(2)])
    assert led.resolve_entry(ENTRY, hist).outcome == led.FILLED_OUT


@pytest.mark.parametrize("status", ["Cancelled", "ApiCancelled", "Inactive"])
def test_reconcile_cancelled_without_executions_is_not_filled(status):
    res = led.resolve_entry(ENTRY, _hist(completed=[_order(status, filled=0.0)]))
    assert res.outcome == led.NOT_FILLED


def test_reconcile_filled_without_executions_and_unset_filled_is_contradiction():
    res = led.resolve_entry(ENTRY, _hist(completed=[_order("Filled", filled=None)]))
    assert res.outcome == led.CONTRADICTION


def test_reconcile_filled_field_without_executions_counts():
    full = led.resolve_entry(ENTRY, _hist(completed=[_order("Filled", filled=2.0)]))
    assert full.outcome == led.FILLED_OUT
    part = led.resolve_entry(ENTRY, _hist(completed=[_order("Filled", filled=1.0)]))
    assert part.outcome == led.PARTIAL_OUT


def test_reconcile_unknown_completed_status_is_contradiction():
    res = led.resolve_entry(ENTRY, _hist(completed=[_order("Weird")]))
    assert res.outcome == led.CONTRADICTION


def test_reconcile_open_and_cancelled_is_contradiction():
    hist = _hist(open=[_order()], completed=[_order("Cancelled", filled=0.0)])
    assert led.resolve_entry(ENTRY, hist).outcome == led.CONTRADICTION


@pytest.mark.parametrize(
    "record",
    [
        _order(con_id=999),
        _order(action="SELL"),
        _order(qty=5.0),
    ],
)
def test_reconcile_collision_on_order_ref(record):
    res = led.resolve_entry(ENTRY, _hist(open=[record]))
    assert res.outcome == led.COLLISION and res.outcome in led.UNRESOLVABLE


def test_reconcile_collision_on_execution_con_id_or_side():
    assert led.resolve_entry(ENTRY, _hist(executions=[_exe(2, con_id=1)])).outcome == led.COLLISION
    assert (
        led.resolve_entry(ENTRY, _hist(executions=[_exe(2, side="SELL")])).outcome == led.COLLISION
    )


def test_reconcile_executions_above_quantity_is_contradiction():
    assert led.resolve_entry(ENTRY, _hist(executions=[_exe(3)])).outcome == led.CONTRADICTION


def test_reconcile_other_order_refs_are_ignored():
    hist = _hist(
        open=[_order(ref="", con_id=1)],
        completed=[_order("Filled", filled=1.0, ref="2026-10-09|MSFT")],
        executions=[_exe(9, ref="")],
    )
    res = led.resolve_entry(ENTRY, hist)
    assert res.outcome == led.NO_TRACE
    assert (res.open, res.completed, res.executions) == (0, 0, 0)


def test_reconcile_falls_back_to_decision_key():
    entry = {k: v for k, v in ENTRY.items() if k != "order_ref"}
    assert led.resolve_entry(entry, _hist(open=[_order()])).outcome == led.OPEN


def test_reconcile_unresolvable_set():
    assert {"no_trace", "collision", "contradiction"} == led.UNRESOLVABLE
