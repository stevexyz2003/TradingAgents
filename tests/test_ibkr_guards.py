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
