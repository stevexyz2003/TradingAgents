"""Unit tests for the library-free guard blocks (scripts/ibkr_guards.py)."""

import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "ibkr_guards_under_test", _SCRIPTS / "ibkr_guards.py"
)
g = importlib.util.module_from_spec(_spec)
sys.modules["ibkr_guards_under_test"] = (
    g  # dataclasses resolves string annotations through sys.modules
)
_spec.loader.exec_module(g)

ACCOUNT = "DUQ634065"
TODAY = date(2026, 10, 16)


def _write_release(path, body=None, *, raw=None):
    if raw is None:
        body = {"account": ACCOUNT, "valid_until": "2026-10-31"} if body is None else body
        raw = json.dumps(body).encode("utf-8")
    path.write_bytes(raw)
    return path


def _read_release(path, today=TODAY, account=ACCOUNT):
    return g.read_release(path, today_utc=today, expected_account=account)


# --- kill file ---------------------------------------------------------------------------


def test_kill_absent_when_no_file(tmp_path):
    assert g.read_kill(tmp_path).state == g.KILL_ABSENT


def test_kill_active_with_empty_file(tmp_path):
    (tmp_path / "KILL").write_bytes(b"")
    result = g.read_kill(tmp_path)
    assert result.state == g.KILL_ACTIVE
    assert result.active


def test_kill_active_with_directory(tmp_path):
    (tmp_path / "KILL").mkdir()
    assert g.read_kill(tmp_path).state == g.KILL_ACTIVE


def test_kill_unreadable_on_permission_error_fail_closed(tmp_path, monkeypatch):
    def boom(path, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(os, "stat", boom)
    result = g.read_kill(tmp_path)
    assert result.state == g.KILL_UNREADABLE
    assert "PermissionError" in result.detail
    assert not result.active


def test_kill_unreadable_when_state_dir_is_a_file_fail_closed(tmp_path):
    not_a_dir = tmp_path / "file"
    not_a_dir.write_bytes(b"x")
    assert g.read_kill(not_a_dir).state == g.KILL_UNREADABLE


def test_kill_unreadable_on_unexpected_exception_fail_closed(tmp_path, monkeypatch):
    def boom(path, *a, **k):
        raise RuntimeError("weird")

    monkeypatch.setattr(os, "stat", boom)
    assert g.read_kill(tmp_path).state == g.KILL_UNREADABLE


@pytest.mark.parametrize("name", ["KILL.txt", "kill.TXT", "Kill", "KILL.", "kill.stop.now"])
def test_kill_active_for_a_kill_file_with_an_ending_or_another_case(tmp_path, name):
    """WR-03: Explorer hides endings, so "New > Text Document" named KILL is KILL.txt."""
    (tmp_path / name).write_bytes(b"")
    result = g.read_kill(tmp_path)
    assert result.state == g.KILL_ACTIVE
    assert result.active


@pytest.mark.parametrize("name", ["KILLER", "KILL_old", "NOKILL", "kill-switch.txt", "RELEASE"])
def test_kill_absent_for_names_that_only_look_alike(tmp_path, name):
    (tmp_path / name).write_bytes(b"")
    assert g.read_kill(tmp_path).state == g.KILL_ABSENT


def test_kill_unreadable_when_the_folder_cannot_be_listed(tmp_path, monkeypatch):
    def boom(path):
        raise PermissionError("denied")

    monkeypatch.setattr(os, "listdir", boom)
    result = g.read_kill(tmp_path)
    assert result.state == g.KILL_UNREADABLE
    assert "PermissionError" in result.detail
    assert not result.active


def test_kill_absent_when_the_state_folder_does_not_exist(tmp_path):
    assert g.read_kill(tmp_path / "missing").state == g.KILL_ABSENT


def test_negative_control_kill_never_uses_exists(tmp_path, monkeypatch):
    (tmp_path / "KILL").write_bytes(b"")
    monkeypatch.setattr(Path, "exists", lambda self, *a, **k: False)
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    assert g.read_kill(tmp_path).state == g.KILL_ACTIVE


# --- release file ------------------------------------------------------------------------


def test_release_ok(tmp_path):
    result = _read_release(_write_release(tmp_path / "RELEASE"))
    assert result.state == g.RELEASE_OK
    assert result.ok
    assert result.valid_until == date(2026, 10, 31)
    assert result.account == ACCOUNT


def test_release_ok_with_utf8_bom(tmp_path):
    raw = b"\xef\xbb\xbf" + json.dumps({"account": ACCOUNT, "valid_until": "2026-10-31"}).encode()
    assert _read_release(_write_release(tmp_path / "RELEASE", raw=raw)).state == g.RELEASE_OK


def test_release_missing(tmp_path):
    assert _read_release(tmp_path / "RELEASE").state == g.RELEASE_MISSING


def test_release_unreadable_for_directory(tmp_path):
    (tmp_path / "RELEASE").mkdir()
    assert _read_release(tmp_path / "RELEASE").state == g.RELEASE_UNREADABLE


def test_release_unreadable_on_permission_error_fail_closed(tmp_path, monkeypatch):
    path = _write_release(tmp_path / "RELEASE")
    real_open = open

    def deny(file, *a, **k):
        if str(file) == str(path):
            raise PermissionError("denied")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", deny)
    assert _read_release(path).state == g.RELEASE_UNREADABLE


def test_release_invalid_for_utf16_file(tmp_path):
    raw = json.dumps({"account": ACCOUNT, "valid_until": "2026-10-31"}).encode("utf-16")
    result = _read_release(_write_release(tmp_path / "RELEASE", raw=raw))
    assert result.state == g.RELEASE_INVALID
    assert "not UTF-8" in result.detail


def test_release_invalid_for_empty_file(tmp_path):
    assert _read_release(_write_release(tmp_path / "RELEASE", raw=b"")).state == g.RELEASE_INVALID


def test_release_invalid_for_oversize_file(tmp_path):
    raw = b" " * (g.MAX_RELEASE_BYTES + 1)
    assert _read_release(_write_release(tmp_path / "RELEASE", raw=raw)).state == g.RELEASE_INVALID


@pytest.mark.parametrize(
    "body",
    [
        {"account": ACCOUNT, "valid_until": "2026-10-31", "extra": 1},
        {"account": ACCOUNT},
        {"valid_until": "2026-10-31"},
        [ACCOUNT, "2026-10-31"],
        {"account": ACCOUNT, "valid_until": "20261031"},
        {"account": ACCOUNT, "valid_until": "2026-1-5"},
        {"account": ACCOUNT, "valid_until": "2026-02-30"},
        {"account": ACCOUNT, "valid_until": 20261031},
        {"account": 634065, "valid_until": "2026-10-31"},
    ],
)
def test_release_invalid_for_bad_shape(tmp_path, body):
    result = _read_release(_write_release(tmp_path / "RELEASE", body))
    assert result.state == g.RELEASE_INVALID
    assert not result.ok


def test_release_invalid_for_non_json_fail_closed(tmp_path):
    assert (
        _read_release(_write_release(tmp_path / "RELEASE", raw=b"not json")).state
        == g.RELEASE_INVALID
    )


def test_release_valid_until_is_inclusive(tmp_path):
    path = _write_release(tmp_path / "RELEASE", {"account": ACCOUNT, "valid_until": "2026-10-16"})
    assert _read_release(path, today=date(2026, 10, 16)).state == g.RELEASE_OK
    assert _read_release(path, today=date(2026, 10, 17)).state == g.RELEASE_EXPIRED


def test_release_horizon_is_ninety_days(tmp_path):
    ok = _write_release(tmp_path / "RELEASE", {"account": ACCOUNT, "valid_until": "2027-01-14"})
    assert _read_release(ok).state == g.RELEASE_OK  # 2026-10-16 + 90 days
    far = _write_release(tmp_path / "RELEASE2", {"account": ACCOUNT, "valid_until": "2027-01-15"})
    result = _read_release(far)
    assert result.state == g.RELEASE_INVALID
    assert "more than 90 days" in result.detail


def test_release_account_mismatch(tmp_path):
    path = _write_release(
        tmp_path / "RELEASE", {"account": "DUX000000", "valid_until": "2026-10-31"}
    )
    assert _read_release(path).state == g.RELEASE_ACCOUNT_MISMATCH


# --- switches ----------------------------------------------------------------------------


def _switches(release_state, kill_state):
    return g.Switches(g.ReleaseState(release_state), g.KillState(kill_state))


def test_switches_allowed_only_with_release_ok_and_kill_absent():
    s = _switches(g.RELEASE_OK, g.KILL_ABSENT)
    assert s.allowed and not s.cancel and s.blocking_state is None


def test_switches_kill_active_cancels_and_blocks():
    s = _switches(g.RELEASE_OK, g.KILL_ACTIVE)
    assert not s.allowed and s.cancel and s.blocking_state == g.KILL_ACTIVE


def test_switches_kill_unreadable_blocks_without_cancel():
    s = _switches(g.RELEASE_OK, g.KILL_UNREADABLE)
    assert not s.allowed and not s.cancel and s.blocking_state == g.KILL_UNREADABLE


@pytest.mark.parametrize(
    "state",
    [
        g.RELEASE_MISSING,
        g.RELEASE_UNREADABLE,
        g.RELEASE_INVALID,
        g.RELEASE_EXPIRED,
        g.RELEASE_ACCOUNT_MISMATCH,
    ],
)
def test_switches_release_failure_blocks_without_cancel(state):
    s = _switches(state, g.KILL_ABSENT)
    assert not s.allowed and not s.cancel and s.blocking_state == state


def test_switches_as_record_lists_both_states_when_allowed():
    s = g.Switches(
        g.ReleaseState(g.RELEASE_OK, valid_until=date(2026, 10, 31), account=ACCOUNT),
        g.KillState(g.KILL_ABSENT),
    )
    record = s.as_record()
    assert record["release"] == g.RELEASE_OK
    assert record["kill"] == g.KILL_ABSENT
    assert record["valid_until"] == "2026-10-31"
    assert record["release_account"] == ACCOUNT
    assert {"release_detail", "kill_detail"} <= set(record)


def test_check_switches_rereads_every_call_no_cache(tmp_path):
    _write_release(tmp_path / "RELEASE")
    first = g.check_switches(tmp_path, today_utc=TODAY, expected_account=ACCOUNT)
    assert first.allowed
    (tmp_path / "KILL").write_bytes(b"")
    second = g.check_switches(tmp_path, today_utc=TODAY, expected_account=ACCOUNT)
    assert second.kill.state == g.KILL_ACTIVE
    assert not second.allowed


# --- state and exit tables ---------------------------------------------------------------

_BLOCKING = (
    g.RELEASE_MISSING,
    g.RELEASE_UNREADABLE,
    g.RELEASE_INVALID,
    g.RELEASE_EXPIRED,
    g.RELEASE_ACCOUNT_MISMATCH,
    g.KILL_ACTIVE,
    g.KILL_UNREADABLE,
)


@pytest.mark.parametrize("state", _BLOCKING)
def test_release_and_kill_blocking_states_exit_four(state):
    assert g.EXIT_BY_STATE[state] == 4


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (g.RELEASE_OK, 0),
        (g.KILL_ABSENT, 0),
        (g.DRY_COMPLETE, 0),
        (g.SIZE_CAP, 5),
        (g.OUTSIDE_SESSION, 2),
        (g.SOURCE_CONFLICT, 2),
        (g.ALREADY_ATTEMPTED, 2),
        (g.DECISION_CHANGED, 2),
        (g.ACCOUNT_CONFLICT, 8),
        (g.LOCK_HELD, 7),
        (g.LOCK_ERROR, 7),
        (g.LEDGER_CORRUPT, 6),
        (g.RECONCILE_UNRESOLVED, 6),
        (g.STATE_IN_GIT_TREE, 1),
        (g.NOT_DRY, 1),
    ],
)
def test_exit_table_covers_every_state(state, code):
    assert g.EXIT_BY_STATE[state] == code


def test_exit_table_is_read_only():
    with pytest.raises(TypeError):
        g.EXIT_BY_STATE["x"] = 1  # type: ignore[index]


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ([], 0),
        ([0, 2, 5], 5),
        ([5, 1], 1),
        ([2, 4, 5], 4),
        ([6, 2], 6),
        ([7], 7),
        ([8, 5], 8),
        ([6, 7], 7),
        ([7, 4], 4),
    ],
)
def test_worst_run_exit_ranking(codes, expected):
    assert g.worst_run_exit(codes) == expected


# --- size cap ----------------------------------------------------------------------------


def _load_probe(name, filename):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolves string annotations through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("qty", [1, 2])
def test_size_within_cap_is_accepted(qty):
    assert g.check_size(qty) is None


def test_size_above_cap_is_rejected_with_reason():
    assert "exceeds MAX_QTY_PER_ORDER 2" in g.check_size(3)


@pytest.mark.parametrize("qty", [0, -1, 2.0, True, "2", None])
def test_size_not_a_positive_whole_number_is_rejected(qty):
    assert "not a positive whole number" in g.check_size(qty)


def test_size_sentinel_blocks_times_block_qty_fit_the_cap():
    decision = _load_probe("ibkr_decision_guards_probe", "ibkr_decision.py")
    contracts = _load_probe("ibkr_contracts_guards_probe", "ibkr_contracts.py")
    tradable = [
        spec.block_qty
        for spec in contracts.CONTRACT_TABLE.values()
        if spec.sec_type in contracts.ALLOWED_SEC_TYPES
    ]
    assert tradable, "no tradable entry: the sentinel would check nothing"
    largest = max(decision.BLOCKS.values()) * max(tradable)
    assert largest <= g.MAX_QTY_PER_ORDER, (
        f"largest order {largest} exceeds MAX_QTY_PER_ORDER {g.MAX_QTY_PER_ORDER}: "
        "raise MAX_QTY_PER_ORDER deliberately in the same commit"
    )


def test_negative_control_size_cap_rejects_instead_of_trimming():
    assert g.check_size(3) is not None
    assert isinstance(g.check_size(3), str)  # a reason, never a smaller quantity
    trimming = [n for n in dir(g) if n.startswith(("trim", "clamp", "cap_"))]
    assert trimming == []


# --- decision key ------------------------------------------------------------------------


def test_decision_key_joins_date_and_ticker_with_the_separator():
    assert g.DECISION_KEY_SEPARATOR == "|"
    assert g.decision_key("2026-10-09", "AAPL") == "2026-10-09|AAPL"


@pytest.mark.parametrize(
    ("trade_date", "ticker"),
    [
        ("2026-10-9", "AAPL"),
        ("2026-02-30", "AAPL"),
        ("2026-10-09", ""),
        ("2026-10-09", "AA|PL"),
        ("2026-10-09", "aapl"),
    ],
)
def test_decision_key_rejects_bad_parts(trade_date, ticker):
    with pytest.raises(ValueError):
        g.decision_key(trade_date, ticker)


def test_decision_key_has_no_sha():
    import re

    assert not re.search(r"[0-9a-f]{40}", g.decision_key("2026-10-09", "AAPL"))


# --- source conflicts --------------------------------------------------------------------


def test_source_conflict_account_agreeing_sources_are_clean():
    assert (
        g.account_conflict(managed_account=ACCOUNT, release_account=ACCOUNT, echo_account=None)
        is None
    )


def test_source_conflict_account_empty_echo_is_optional():
    assert (
        g.account_conflict(managed_account=ACCOUNT, release_account=ACCOUNT, echo_account="")
        is None
    )


def test_source_conflict_account_echo_mismatch():
    reason = g.account_conflict(
        managed_account=ACCOUNT, release_account=ACCOUNT, echo_account="DUX000000"
    )
    assert reason and "DUX000000" in reason and ACCOUNT in reason


def test_source_conflict_account_release_mismatch():
    reason = g.account_conflict(
        managed_account=ACCOUNT, release_account="DUX000000", echo_account=None
    )
    assert reason and "DUX000000" in reason


@pytest.mark.parametrize("ledger,broker", [(0, 5), (2, 2), (2, 3)])
def test_source_conflict_position_clean(ledger, broker):
    assert g.position_conflict(ledger_filled_qty=ledger, broker_held=broker) is None


def test_source_conflict_position_broker_holds_less_than_ledger_filled():
    reason = g.position_conflict(ledger_filled_qty=2, broker_held=1)
    assert reason and "2" in reason and "1" in reason


def test_source_conflict_executed_broker_has_trace_ledger_does_not():
    reason = g.executed_conflict(ledger_attempted=False, history_has_ref=True)
    assert "broker shows an order with this orderRef, ledger has none" in reason


def test_source_conflict_executed_ledger_attempted_broker_silent():
    reason = g.executed_conflict(ledger_attempted=True, history_has_ref=False)
    assert "ledger says attempted, broker shows no trace" in reason


@pytest.mark.parametrize("value", [True, False])
def test_source_conflict_executed_agreeing_sources_are_clean(value):
    assert g.executed_conflict(ledger_attempted=value, history_has_ref=value) is None
