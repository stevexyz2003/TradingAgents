"""Archive storage: append-only JSONL per source and UTC day, SQLite dedupe index, atomic
JSON writes and a run lock."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tradingagents.forecast.archive.models import ArchiveRecord

log = logging.getLogger(__name__)


def archive_base(environ=None) -> Path:
    """``LOCALAPPDATA/TradingEngineX/archive``, else ``~/.tradingenginex/archive``."""
    env = os.environ if environ is None else environ
    local = env.get("LOCALAPPDATA")
    if local:
        return Path(local) / "TradingEngineX" / "archive"
    return Path.home() / ".tradingenginex" / "archive"


def atomic_write_json(path, obj, *, retries: int = 5, delay: float = 0.2, sleep=time.sleep):
    """Write ``obj`` as JSON via tmp file + fsync + os.replace in the same folder.

    os.replace can fail with PermissionError on Windows while another process (a virus
    scanner, a reader) has the target open; it is retried ``retries`` times.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == retries - 1:
                tmp.unlink(missing_ok=True)
                raise
            sleep(delay)


def read_json(path) -> dict | None:
    """The JSON object at ``path``; None when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("unreadable JSON file %s: %s", path, exc)
        return None


class LockHeld(Exception):
    """Another run holds the archive lock."""


_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid) -> bool:
    """Whether a process with this PID exists.

    On Windows this uses OpenProcess/GetExitCodeProcess only. ``os.kill(pid, 0)`` must
    never be used there: on Windows os.kill calls TerminateProcess for any signal that is
    not CTRL_C/CTRL_BREAK, so the "probe" would kill the process. Access denied means the
    process exists but belongs to someone else, so it counts as alive.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunLock:
    """Lock file holding ``{"pid", "ts"}``; ``touch()`` renews the timestamp.

    An existing lock counts as held while its PID is alive OR its timestamp is younger
    than ``stale_after``. Regardless of the PID, a lock whose timestamp is older than
    ``takeover_after`` is taken over: that covers PID reuse and hung processes (a live
    run touches the lock per query, window and file).
    """

    def __init__(
        self,
        path,
        *,
        stale_after: timedelta = timedelta(minutes=30),
        takeover_after: timedelta = timedelta(hours=6),
        now: Callable[[], datetime] = _utcnow,
        pid_alive: Callable[[int], bool] = pid_alive,
    ):
        self.path = Path(path)
        self.stale_after = stale_after
        self.takeover_after = takeover_after
        self._now = now
        self._pid_alive = pid_alive
        self._held = False

    def _content(self) -> str:
        return json.dumps({"pid": os.getpid(), "ts": self._now().isoformat()})

    def _is_held(self) -> bool:
        pid = None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            pid = data.get("pid")
            ts = datetime.fromisoformat(data["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        except FileNotFoundError:
            return False
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            try:
                ts = datetime.fromtimestamp(self.path.stat().st_mtime, UTC)
            except FileNotFoundError:
                return False
        age = self._now() - ts
        if age >= self.takeover_after:
            return False
        if age < self.stale_after:
            return True
        return pid is not None and self._pid_alive(pid)

    def acquire(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_held():
                    raise LockHeld(f"archive lock held: {self.path}") from None
                log.warning("taking over stale archive lock %s", self.path)
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self._content())
            self._held = True
            return self
        raise LockHeld(f"could not acquire archive lock: {self.path}")

    def touch(self) -> None:
        if self._held:
            self.path.write_text(self._content(), encoding="utf-8")

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> RunLock:
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


@dataclass
class AppendResult:
    new: int = 0
    duplicate: int = 0


def _day_str(day) -> str:
    return day.isoformat() if isinstance(day, date) else str(day)


class ArchiveStore:
    """JSONL files under ``base/<source>/YYYY/MM/YYYY-MM-DD.jsonl`` plus ``base/index.sqlite``."""

    def __init__(self, base):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.base / "index.sqlite")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS records (record_hash TEXT PRIMARY KEY, source TEXT,"
            " day TEXT, story_key TEXT, first_seen_ts TEXT)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS records_story ON records(story_key)")
        self._db.commit()

    def day_path(self, source: str, day) -> Path:
        text = _day_str(day)
        return self.base / source / text[:4] / text[5:7] / f"{text}.jsonl"

    def append(self, records: Iterable[ArchiveRecord]) -> AppendResult:
        # Order: insert into the index (uncommitted), write + fsync the JSONL lines, then
        # commit. A crash between writing a line and the commit leaves a line without an
        # index row, so a re-run may append the same line again; iter_day therefore
        # dedupes by record_hash when reading. That is deliberate: no line is ever lost.
        result = AppendResult()
        pending: dict[Path, list[str]] = {}
        try:
            for record in records:
                cursor = self._db.execute(
                    "INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?, ?)",
                    (
                        record.record_hash,
                        record.source,
                        record.day,
                        record.story_key,
                        record.first_seen_ts,
                    ),
                )
                if cursor.rowcount == 1:
                    result.new += 1
                    path = self.day_path(record.source, record.day)
                    pending.setdefault(path, []).append(record.to_json())
                else:
                    result.duplicate += 1
            for path, lines in pending.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8", newline="\n") as handle:
                    for line in lines:
                        handle.write(line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise
        return result

    def iter_day(self, source: str, day) -> Iterator[dict]:
        path = self.day_path(source, day)
        if not path.exists():
            return
        seen: set[str] = set()
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue  # truncated last line from an interrupted write
                key = data.get("record_hash")
                if key in seen:
                    continue
                seen.add(key)
                yield data

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> ArchiveStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
