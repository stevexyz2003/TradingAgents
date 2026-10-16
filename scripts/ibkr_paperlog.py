"""Read-only access to the paper-log branch for the phase-4 preview.

``git fetch`` plus ``git cat-file``: no working tree (D-01).
Library-free; the runner is injected so tests need neither git nor network.

The reader knows exactly two path shapes: ``decision-log.md`` and
``runs/<YYYY-MM-DD>/summary.json``. It never reads a run report (REQ-IBKR-18).
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RUN_DIR_RE = re.compile(r"^runs/(\d{4}-\d{2}-\d{2})$")

DECISION_LOG_PATH = "decision-log.md"


class PaperLogUnavailable(Exception):
    """The paper-log branch could not be fetched or decoded."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BlobMissing(Exception):
    """The requested path does not exist in the fetched commit."""

    def __init__(self, path: str):
        super().__init__(path)
        self.path = path


def validate_ref_name(value: str, what: str) -> str:
    """Whitelist a remote or branch name before it goes into a command line."""
    if (
        not value
        or value.startswith("-")
        or ".." in value
        or not _REF_RE.match(value)
    ):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def validate_blob_path(path: str) -> str:
    """Whitelist a repository-relative blob path."""
    if (
        not path
        or path.startswith(("-", "/"))
        or not _REF_RE.match(path)
        or any(seg in ("", "..") for seg in path.split("/"))
    ):
        raise ValueError(f"invalid path: {path!r}")
    return path


def summary_path(trade_date: str) -> str:
    if not _DATE_RE.match(trade_date):
        raise ValueError(f"invalid trade date: {trade_date!r}")
    return f"runs/{trade_date}/summary.json"


def decode_utf8(blob: bytes, path: str) -> str:
    """Strict UTF-8; bytes are never passed through a text-mode conversion."""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PaperLogUnavailable(f"{path} is not valid UTF-8: {exc}") from exc


class GitPaperLog:
    def __init__(
        self,
        repo: Path,
        remote: str,
        branch: str,
        *,
        run=subprocess.run,
        fetch_timeout: float = 60.0,
        read_timeout: float = 30.0,
    ):
        self._repo = Path(repo)
        self._remote = validate_ref_name(remote, "remote")
        self._branch = validate_ref_name(branch, "branch")
        self._run = run
        self._fetch_timeout = fetch_timeout
        self._read_timeout = read_timeout
        self.sha: str | None = None

    def _git(self, args: list[str], timeout: float):
        return self._run(
            ["git", *args],
            cwd=str(self._repo),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            capture_output=True,
            timeout=timeout,
        )

    @staticmethod
    def _err(proc) -> str:
        return (proc.stderr or b"").decode("utf-8", errors="replace").strip()

    def fetch(self) -> str:
        # Forget a previous sha first: a failed re-fetch must not leave the
        # reader on a stale view (D-02).
        self.sha = None
        # Fetch into a ref of this run's own and resolve that: FETCH_HEAD is
        # repo-wide and any other fetch (IDE background fetch, a second run)
        # would overwrite it between the fetch and the rev-parse.
        ref = f"refs/tengx/paper-log-preview/{uuid.uuid4().hex}"
        try:
            proc = self._git(
                [
                    "fetch",
                    "--no-tags",
                    "--quiet",
                    self._remote,
                    f"+refs/heads/{self._branch}:{ref}",
                ],
                self._fetch_timeout,
            )
            if proc.returncode != 0:
                raise PaperLogUnavailable(f"git fetch failed: {self._err(proc)}")
            rev = self._git(["rev-parse", "--verify", f"{ref}^{{commit}}"], self._read_timeout)
            # The sha is resolved; the ref only served to pin it. Best effort.
            self._git(["update-ref", "-d", ref], self._read_timeout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise PaperLogUnavailable(f"git unavailable: {exc}") from exc
        if rev.returncode != 0:
            raise PaperLogUnavailable(f"rev-parse failed: {self._err(rev)}")
        sha = (rev.stdout or b"").decode("utf-8", errors="replace").strip()
        if not _SHA_RE.match(sha):
            raise PaperLogUnavailable(f"not a commit sha: {sha!r}")
        # No fallback to a locally known ref: a stale view would hide the
        # divergence case of REQ-IBKR-17 (D-02).
        self.sha = sha
        return sha

    def _require_sha(self) -> str:
        if self.sha is None:
            raise RuntimeError("fetch() must run before reading")
        return self.sha

    def read(self, path: str) -> bytes:
        validate_blob_path(path)
        sha = self._require_sha()
        try:
            proc = self._git(["cat-file", "blob", f"{sha}:{path}"], self._read_timeout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise PaperLogUnavailable(f"git unavailable: {exc}") from exc
        if proc.returncode != 0:
            raise BlobMissing(path)
        return proc.stdout

    def list_run_dates(self) -> tuple[str, ...]:
        sha = self._require_sha()
        try:
            proc = self._git(["ls-tree", "--name-only", sha, "runs/"], self._read_timeout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise PaperLogUnavailable(f"git unavailable: {exc}") from exc
        if proc.returncode != 0:
            raise PaperLogUnavailable(f"ls-tree failed: {self._err(proc)}")
        dates = []
        for line in (proc.stdout or b"").decode("utf-8", errors="replace").splitlines():
            m = _RUN_DIR_RE.match(line.strip())
            if m:
                dates.append(m.group(1))
        return tuple(sorted(dates))
