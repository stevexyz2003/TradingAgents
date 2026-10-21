"""Quality status per source and UTC day, archive start, heartbeat and gap report.

Layout under the archive base: ``status/<source>/YYYY-MM-DD.json``, ``meta.json``
(archive_start) and ``heartbeat.json``; every file is written atomically. A day without a
status file is ``missing`` - a gap is never mistaken for "no news".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tradingagents.forecast.archive.store import atomic_write_json, read_json

PARTIAL_FAILURE_RATIO = 0.10
MAX_ATTEMPTS = 3


@dataclass
class DayStatus:
    source: str
    day: str
    status: str = "missing"  # ok | partial | missing
    attempts: int = 0
    last_attempt_date: str | None = None  # UTC date of the last counted attempt
    queries: int = 0
    failed: int = 0
    rejected: int = 0
    truncated: int = 0
    canary_hits: int = 0
    files: int = 0
    records_new: int = 0
    records_duplicate: int = 0
    errors: list[str] = field(default_factory=list)
    run_id: str | None = None
    finished_at: str | None = None


def _day_str(day) -> str:
    return day.isoformat() if isinstance(day, date) else str(day)


def _status_path(base, source: str, day) -> Path:
    return Path(base) / "status" / source / f"{_day_str(day)}.json"


def read_day_status(base, source: str, day) -> DayStatus:
    data = read_json(_status_path(base, source, day))
    if data is None:
        return DayStatus(source=source, day=_day_str(day), errors=["no status file"])
    known = {f.name for f in fields(DayStatus)}
    return DayStatus(**{k: v for k, v in data.items() if k in known})


def write_day_status(
    base, st: DayStatus, *, count_attempt: bool = True, now: datetime | None = None
) -> DayStatus:
    """Write ``st``; the attempt counter is taken from the existing file.

    ``attempts`` grows at most once per UTC calendar day: a re-run on the same day retries
    without using up another attempt. ``count_attempt=False`` (e.g. a run cut short by
    --max-runtime) never counts.
    """
    previous = read_day_status(base, st.source, st.day)
    attempts = previous.attempts
    last = previous.last_attempt_date
    if count_attempt:
        today = (now or datetime.now(UTC)).astimezone(UTC).date().isoformat()
        if last != today:
            attempts += 1
            last = today
    st.attempts = attempts
    st.last_attempt_date = last
    atomic_write_json(_status_path(base, st.source, st.day), asdict(st))
    return st


def classify_gdelt_day(queries: int, failed: int, rejected: int, canary_hits: int) -> str:
    if queries <= 0 or failed >= queries:
        return "missing"
    if (failed + rejected) / queries > PARTIAL_FAILURE_RATIO:
        return "partial"
    if canary_hits == 0:
        return "partial"
    return "ok"


def _meta_path(base) -> Path:
    return Path(base) / "meta.json"


def archive_start(base) -> date | None:
    data = read_json(_meta_path(base)) or {}
    value = data.get("archive_start")
    return date.fromisoformat(value) if value else None


def ensure_archive_start(base, start: date) -> date:
    """Set archive_start once; an existing value is never moved."""
    existing = archive_start(base)
    if existing is not None:
        return existing
    data = read_json(_meta_path(base)) or {}
    data["archive_start"] = start.isoformat()
    atomic_write_json(_meta_path(base), data)
    return start


def _heartbeat_path(base) -> Path:
    return Path(base) / "heartbeat.json"


def read_heartbeat(base) -> dict | None:
    return read_json(_heartbeat_path(base))


def write_heartbeat(base, hb: dict) -> dict:
    """Write the heartbeat. A "started" write keeps ``last_finished_at`` of the predecessor."""
    hb = dict(hb)
    for key in ("started_at", "finished_at", "last_finished_at", "run_id", "exit_code"):
        hb.setdefault(key, None)
    hb.setdefault("counts", {})
    if hb.get("finished_at"):
        hb["last_finished_at"] = hb["finished_at"]
    elif not hb.get("last_finished_at"):
        previous = read_heartbeat(base) or {}
        hb["last_finished_at"] = previous.get("last_finished_at") or previous.get("finished_at")
    atomic_write_json(_heartbeat_path(base), hb)
    return hb


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def heartbeat_age(base, now: datetime) -> timedelta | None:
    """Age since the last finished run; None when no run ever finished.

    Measured from ``last_finished_at``/``finished_at``, so a run that started but hangs
    does not mask a gap.
    """
    hb = read_heartbeat(base)
    if not hb:
        return None
    stamps = [
        t for t in (_parse_ts(hb.get("last_finished_at")), _parse_ts(hb.get("finished_at"))) if t
    ]
    if not stamps:
        return None
    return now - max(stamps)


def is_given_up(st: DayStatus, max_attempts: int = MAX_ATTEMPTS) -> bool:
    return st.status != "ok" and st.attempts >= max_attempts


def days_needing_work(
    base,
    source: str,
    today: date,
    *,
    window_days: int = 89,
    max_days: int = 3,
    reserve_newest: int = 2,
    max_attempts: int = MAX_ATTEMPTS,
) -> list[date]:
    """Days before ``today`` that still need a (re)try, oldest first.

    The reservation keeps a long backlog from crowding out the current day; the attempt
    limit stops endless loops on a permanently broken day. Deleting a day's status file
    makes the day eligible again.
    """
    start = archive_start(base)
    if start is None:
        return []
    lo = max(start, today - timedelta(days=window_days))
    candidates: list[date] = []
    day = lo
    while day < today:
        st = read_day_status(base, source, day)
        if st.status != "ok" and st.attempts < max_attempts:
            candidates.append(day)
        day += timedelta(days=1)
    if len(candidates) <= max_days:
        return candidates
    reserve = min(reserve_newest, max_days)
    newest = candidates[len(candidates) - reserve :] if reserve else []
    oldest = candidates[: max_days - reserve]
    return sorted(set(oldest) | set(newest))


def gap_report(base, sources, *, days: int, today: date) -> list[DayStatus]:
    """Status of the last ``days`` days before ``today`` (not before archive_start)."""
    start = archive_start(base)
    if start is None:
        return []
    report = []
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        if day < start:
            continue
        for source in sources:
            report.append(read_day_status(base, source, day))
    return report


def given_up_days(base, sources, *, max_attempts: int = MAX_ATTEMPTS) -> list[DayStatus]:
    """Every day that is not ok and has used up its attempts (catch-up no longer tries it)."""
    result = []
    for source in sources:
        folder = Path(base) / "status" / source
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            st = read_day_status(base, source, path.stem)
            if is_given_up(st, max_attempts):
                result.append(st)
    return result


def status_file(base, source: str, day) -> Path:
    """Path of a day's status file (delete it to reset the attempt counter)."""
    return _status_path(base, source, day)
