"""Archive core: models, store with dedupe, status/heartbeat/gaps, HTTP helpers."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime, timedelta

import pytest
import requests

from tradingagents.forecast.archive import http as ahttp, status as astatus, store as astore
from tradingagents.forecast.archive.models import (
    ArchiveRecord,
    canonical_url,
    record_hash,
    story_key,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, status_code=200, headers=None, text="", content=b"", json_data=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.content = content or text.encode()
        self._json = json_data

    def json(self):
        return self._json


def _rec(i, *, source="gdelt", day="2026-10-19", url=None, key=""):
    return ArchiveRecord(
        source=source,
        url=url or f"https://example.com/a{i}",
        title=f"Synthetic title {i}",
        day=day,
        dedupe_key=key,
    )


# --- models ---------------------------------------------------------------------------


def test_canonical_url_normalizes_and_strips_tracking():
    url = "HTTPS://Example.COM/a?utm_source=x&b=2&a=1&fbclid=z#frag"
    assert canonical_url(url) == "https://example.com/a?a=1&b=2"
    assert canonical_url("dila-amf:x.tar.gz/m.xml") == "dila-amf:x.tar.gz/m.xml"


def test_record_hash_depends_on_source_and_dedupe_key():
    assert record_hash("gdelt", "k") == record_hash("gdelt", "k")
    assert record_hash("gdelt", "k") != record_hash("amf", "k")
    a = _rec(1, key="https://example.com/a1|DE0007164600")
    b = _rec(1, key="https://example.com/a1|FR0000120271")
    assert a.record_hash != b.record_hash
    assert _rec(1).dedupe_key == "https://example.com/a1"


def test_story_key_ignores_case_punctuation_and_spacing():
    assert story_key("Siemens  beats, estimates!") == story_key("siemens beats estimates")


def test_to_json_is_one_line_with_hashes():
    line = _rec(1).to_json()
    assert "\n" not in line
    data = json.loads(line)
    assert data["record_hash"] == _rec(1).record_hash
    assert data["story_key"] == _rec(1).story_key


# --- store ----------------------------------------------------------------------------


def test_append_dedupes_across_store_instances(tmp_path):
    records = [_rec(i) for i in range(3)]
    with astore.ArchiveStore(tmp_path) as store:
        assert store.append(records) == astore.AppendResult(new=3, duplicate=0)
    with astore.ArchiveStore(tmp_path) as store:
        assert store.append(records) == astore.AppendResult(new=0, duplicate=3)
        path = store.day_path("gdelt", "2026-10-19")
    assert path == tmp_path / "gdelt" / "2026" / "10" / "2026-10-19.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_iter_day_skips_truncated_line_and_dedupes(tmp_path):
    with astore.ArchiveStore(tmp_path) as store:
        store.append([_rec(1), _rec(2)])
        path = store.day_path("gdelt", "2026-10-19")
        first = path.read_text(encoding="utf-8").splitlines()[0]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(first + "\n")
            handle.write('{"source": "gd')
        rows = list(store.iter_day("gdelt", "2026-10-19"))
    assert len(rows) == 2


def test_archive_base_uses_localappdata(tmp_path):
    assert astore.archive_base({"LOCALAPPDATA": str(tmp_path)}) == (
        tmp_path / "TradingEngineX" / "archive"
    )
    assert astore.archive_base({}).parts[-2:] == (".tradingenginex", "archive")


# --- atomic_write_json ----------------------------------------------------------------


def test_atomic_write_json_leaves_no_tmp(tmp_path):
    path = tmp_path / "sub" / "x.json"
    astore.atomic_write_json(path, {"a": 1})
    assert astore.read_json(path) == {"a": 1}
    assert not list(path.parent.glob("*.tmp"))


def test_atomic_write_json_retries_permission_error(tmp_path, monkeypatch):
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("locked")
        return real(src, dst)

    monkeypatch.setattr(astore.os, "replace", flaky)
    sleeps = []
    astore.atomic_write_json(tmp_path / "x.json", {"a": 2}, sleep=sleeps.append)
    assert calls["n"] == 3 and len(sleeps) == 2
    assert astore.read_json(tmp_path / "x.json") == {"a": 2}


def test_atomic_write_json_gives_up_after_retries(tmp_path, monkeypatch):
    def always(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(astore.os, "replace", always)
    with pytest.raises(PermissionError):
        astore.atomic_write_json(tmp_path / "x.json", {"a": 3}, sleep=lambda _s: None)
    assert not list(tmp_path.glob("*.tmp"))


def test_read_json_missing_is_none(tmp_path):
    assert astore.read_json(tmp_path / "nope.json") is None


# --- RunLock --------------------------------------------------------------------------


def _write_lock(path, pid, ts):
    path.write_text(json.dumps({"pid": pid, "ts": ts.isoformat()}), encoding="utf-8")


def test_second_lock_raises(tmp_path):
    path = tmp_path / "run.lock"
    second = astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: True)
    with (
        astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: True),
        pytest.raises(astore.LockHeld),
    ):
        second.acquire()
    assert not path.exists()


def test_dead_pid_and_old_timestamp_is_taken_over(tmp_path):
    path = tmp_path / "run.lock"
    _write_lock(path, 999999, NOW - timedelta(hours=1))
    with astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: False):
        assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_live_pid_and_old_timestamp_is_held(tmp_path):
    path = tmp_path / "run.lock"
    _write_lock(path, 4242, NOW - timedelta(hours=1))
    with pytest.raises(astore.LockHeld):
        astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: True).acquire()


def test_dead_pid_and_fresh_timestamp_is_held(tmp_path):
    path = tmp_path / "run.lock"
    _write_lock(path, 4242, NOW - timedelta(minutes=5))
    with pytest.raises(astore.LockHeld):
        astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: False).acquire()


def test_live_pid_with_timestamp_older_than_six_hours_is_taken_over(tmp_path):
    path = tmp_path / "run.lock"
    _write_lock(path, 4242, NOW - timedelta(hours=6, minutes=1))
    with astore.RunLock(path, now=lambda: NOW, pid_alive=lambda _p: True):
        assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_touch_renews_timestamp(tmp_path):
    path = tmp_path / "run.lock"
    clock = {"t": NOW}
    with astore.RunLock(path, now=lambda: clock["t"], pid_alive=lambda _p: False) as lock:
        clock["t"] = NOW + timedelta(minutes=20)
        lock.touch()
        ts = json.loads(path.read_text(encoding="utf-8"))["ts"]
    assert datetime.fromisoformat(ts) == NOW + timedelta(minutes=20)


def test_pid_alive_rejects_nonsense():
    assert astore.pid_alive(0) is False
    assert astore.pid_alive("x") is False
    assert astore.pid_alive(os.getpid()) is True


# --- status ---------------------------------------------------------------------------


def test_missing_status_file_is_missing(tmp_path):
    st = astatus.read_day_status(tmp_path, "gdelt", date(2026, 10, 19))
    assert st.status == "missing" and st.attempts == 0 and st.errors == ["no status file"]


def test_attempts_count_once_per_utc_day(tmp_path):
    st = astatus.DayStatus(source="gdelt", day="2026-10-19", status="missing")
    astatus.write_day_status(tmp_path, st, now=NOW)
    astatus.write_day_status(tmp_path, st, now=NOW + timedelta(hours=3))
    assert astatus.read_day_status(tmp_path, "gdelt", "2026-10-19").attempts == 1
    astatus.write_day_status(tmp_path, st, now=NOW + timedelta(days=1))
    again = astatus.read_day_status(tmp_path, "gdelt", "2026-10-19")
    assert again.attempts == 2 and again.last_attempt_date == "2026-10-21"
    astatus.write_day_status(tmp_path, st, count_attempt=False, now=NOW + timedelta(days=2))
    assert astatus.read_day_status(tmp_path, "gdelt", "2026-10-19").attempts == 2


def test_two_failed_runs_on_the_same_day_are_one_attempt(tmp_path):
    for hour in (6, 18):
        st = astatus.DayStatus(source="gdelt", day="2026-10-18", status="missing")
        astatus.write_day_status(tmp_path, st, now=NOW.replace(hour=hour))
    assert astatus.read_day_status(tmp_path, "gdelt", "2026-10-18").attempts == 1


def test_classify_gdelt_day():
    assert astatus.classify_gdelt_day(10, 10, 0, 5) == "missing"
    assert astatus.classify_gdelt_day(10, 1, 1, 5) == "partial"
    assert astatus.classify_gdelt_day(10, 0, 0, 0) == "partial"
    assert astatus.classify_gdelt_day(10, 1, 0, 5) == "ok"


def _set_status(base, day, status, attempts=1):
    st = astatus.DayStatus(source="gdelt", day=day.isoformat(), status=status)
    astatus.atomic_write_json(
        astatus.status_file(base, "gdelt", day), {**st.__dict__, "attempts": attempts}
    )


def test_days_needing_work_basic(tmp_path):
    today = date(2026, 10, 20)
    assert astatus.days_needing_work(tmp_path, "gdelt", today) == []
    astatus.ensure_archive_start(tmp_path, today - timedelta(days=5))
    _set_status(tmp_path, today - timedelta(days=3), "ok")
    days = astatus.days_needing_work(tmp_path, "gdelt", today, max_days=10)
    assert days == [today - timedelta(days=d) for d in (5, 4, 2, 1)]


def test_days_needing_work_window_attempts_and_reservation(tmp_path):
    today = date(2026, 10, 20)
    astatus.ensure_archive_start(tmp_path, today - timedelta(days=200))
    days = astatus.days_needing_work(tmp_path, "gdelt", today, max_days=500)
    assert min(days) == today - timedelta(days=89)
    _set_status(tmp_path, today - timedelta(days=89), "missing", attempts=3)
    days = astatus.days_needing_work(tmp_path, "gdelt", today, max_days=500)
    assert today - timedelta(days=89) not in days

    tmp2 = tmp_path / "b"
    astatus.ensure_archive_start(tmp2, today - timedelta(days=10))
    days = astatus.days_needing_work(tmp2, "gdelt", today, max_days=3)
    assert days == [
        today - timedelta(days=10),
        today - timedelta(days=2),
        today - timedelta(days=1),
    ]


def test_gap_report_shows_missing_day_and_skips_before_start(tmp_path):
    today = date(2026, 10, 20)
    astatus.ensure_archive_start(tmp_path, today - timedelta(days=10))
    for offset in range(1, 11):
        if offset != 4:
            _set_status(tmp_path, today - timedelta(days=offset), "ok")
    report = astatus.gap_report(tmp_path, ["gdelt"], days=14, today=today)
    assert len(report) == 10
    bad = [st for st in report if st.status != "ok"]
    assert [st.day for st in bad] == [(today - timedelta(days=4)).isoformat()]
    assert bad[0].status == "missing"


def test_given_up_days_lists_exhausted_days(tmp_path):
    today = date(2026, 10, 20)
    _set_status(tmp_path, today - timedelta(days=2), "partial", attempts=3)
    _set_status(tmp_path, today - timedelta(days=1), "partial", attempts=1)
    gave_up = astatus.given_up_days(tmp_path, ["gdelt", "amf"])
    assert [st.day for st in gave_up] == [(today - timedelta(days=2)).isoformat()]


def test_ensure_archive_start_is_set_once(tmp_path):
    assert astatus.ensure_archive_start(tmp_path, date(2026, 10, 1)) == date(2026, 10, 1)
    assert astatus.ensure_archive_start(tmp_path, date(2026, 9, 1)) == date(2026, 10, 1)
    assert astatus.archive_start(tmp_path) == date(2026, 10, 1)


def test_heartbeat_age(tmp_path):
    assert astatus.heartbeat_age(tmp_path, NOW) is None
    astatus.write_heartbeat(tmp_path, {"started_at": "x", "finished_at": None})
    assert astatus.heartbeat_age(tmp_path, NOW) is None

    finished = NOW - timedelta(hours=40)
    astatus.write_heartbeat(
        tmp_path, {"started_at": finished.isoformat(), "finished_at": finished.isoformat()}
    )
    assert astatus.heartbeat_age(tmp_path, NOW) > timedelta(hours=36)

    astatus.write_heartbeat(
        tmp_path, {"started_at": (NOW - timedelta(hours=1)).isoformat(), "finished_at": None}
    )
    hb = astatus.read_heartbeat(tmp_path)
    assert hb["last_finished_at"] == finished.isoformat()
    assert astatus.heartbeat_age(tmp_path, NOW) > timedelta(hours=36)


# --- http -----------------------------------------------------------------------------


def test_resolve_ca_bundle(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert ahttp.resolve_ca_bundle({}) is True
    assert "certifi" in caplog.text
    bundle = tmp_path / "ca.pem"
    bundle.write_text("x", encoding="ascii")
    assert ahttp.resolve_ca_bundle({"REQUESTS_CA_BUNDLE": str(bundle)}) == str(bundle)
    with pytest.raises(ahttp.CaBundleMissing, match="nope.pem"):
        ahttp.resolve_ca_bundle({"REQUESTS_CA_BUNDLE": str(tmp_path / "nope.pem")})


def test_make_session_sets_verify_and_agent():
    session = ahttp.make_session("/x.pem")
    assert session.verify == "/x.pem"
    assert session.headers["User-Agent"] == ahttp.USER_AGENT


def _seq_get(responses):
    calls = []

    def get(url, params=None, timeout=None):
        calls.append(url)
        item = responses[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    return get, calls


def test_get_with_retry_recovers_from_429():
    get, calls = _seq_get([FakeResponse(429), FakeResponse(429), FakeResponse(200)])
    sleeps = []
    resp = ahttp.get_with_retry(get, "u", sleep=sleeps.append, rate_limit_backoff=1.0)
    assert resp.status_code == 200 and len(calls) == 3 and sleeps == [1.0, 2.0]


def test_get_with_retry_pauses_long_after_429_by_default():
    get, _calls = _seq_get([FakeResponse(429), FakeResponse(200)])
    sleeps = []
    ahttp.get_with_retry(get, "u", sleep=sleeps.append)
    assert sleeps == [60.0]


def test_get_with_retry_honours_numeric_retry_after():
    get, _calls = _seq_get([FakeResponse(429, headers={"Retry-After": "120"}), FakeResponse(200)])
    sleeps = []
    ahttp.get_with_retry(get, "u", sleep=sleeps.append, rate_limit_backoff=1.0)
    assert sleeps == [120.0]


def test_get_with_retry_ignores_an_http_date_retry_after():
    stamp = "Wed, 21 Oct 2026 07:28:00 GMT"
    get, _calls = _seq_get([FakeResponse(429, headers={"Retry-After": stamp}), FakeResponse(200)])
    sleeps = []
    ahttp.get_with_retry(get, "u", sleep=sleeps.append, rate_limit_backoff=1.0)
    assert sleeps == [1.0]


def test_get_with_retry_keeps_the_short_backoff_for_server_errors():
    get, _calls = _seq_get([FakeResponse(503), FakeResponse(200)])
    sleeps = []
    ahttp.get_with_retry(get, "u", sleep=sleeps.append, backoff=1.0)
    assert sleeps == [1.0]


def test_get_with_retry_server_error_after_three():
    get, calls = _seq_get([FakeResponse(503)] * 3)
    with pytest.raises(ahttp.FetchError) as exc:
        ahttp.get_with_retry(get, "u", sleep=lambda _s: None)
    assert exc.value.kind == "server" and len(calls) == 3


def test_get_with_retry_timeout_kind():
    get, _calls = _seq_get([requests.Timeout("slow")] * 3)
    with pytest.raises(ahttp.FetchError) as exc:
        ahttp.get_with_retry(get, "u", sleep=lambda _s: None)
    assert exc.value.kind == "timeout"


def test_get_with_retry_client_error_no_retry():
    get, calls = _seq_get([FakeResponse(404)])
    with pytest.raises(ahttp.FetchError) as exc:
        ahttp.get_with_retry(get, "u", sleep=lambda _s: None)
    assert exc.value.kind == "client" and len(calls) == 1


def test_rate_limiter_sleeps_the_difference():
    clock = {"t": 100.0}
    sleeps = []
    limiter = ahttp.RateLimiter(6.0, clock=lambda: clock["t"], sleep=sleeps.append)
    limiter.wait()
    clock["t"] = 102.0
    limiter.wait()
    assert sleeps == [4.0]
