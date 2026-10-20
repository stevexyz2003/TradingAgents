"""Publish an executor snapshot to the ``ibkr-log`` branch (single writer).

The executor is the only writer of ``ibkr-log`` on the ``fork`` remote; CI is
the only writer of ``paper-log`` (D-01..D-04). This module is the Git write
path: snapshot bytes in, one-branch clone in the state folder, commit only on
a diff, plain push of ``HEAD:refs/heads/ibkr-log`` to ``fork``. A rejected
push is reported, never forced. The remote and branch are constants without
an environment override, so no code path can reach ``origin`` or
``paper-log``.

Pure by construction: no clock (the caller passes ``now_utc``), no gateway,
no lock, no ledger validation (all of that belongs to the executor wrapper).
Standard library only; the Git runner is injected so tests can record argv.
Contents are published unmasked (D-17) and byte-exact (no line-ending
conversion).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PUBLISH_REMOTE = "fork"
PUBLISH_BRANCH = "ibkr-log"
LEDGER_NAME = "ledger.jsonl"
PORTFOLIO_NAME = "portfolio.json"
CONTRACTS_NAME = "contracts.json"
ATTRIBUTES_NAME = ".gitattributes"
ATTRIBUTES_BYTES = b"* -text\n"
COMMIT_NAME = "TradingEngineX publish"
COMMIT_EMAIL = "publish@tradingenginex.invalid"
GIT_TIMEOUT = 120.0

_PAPERLOG_PATH = Path(__file__).with_name("ibkr_paperlog.py")


def _load_paperlog():
    cached = sys.modules.get("ibkr_paperlog")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("ibkr_paperlog", _PAPERLOG_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_paperlog"] = module
    spec.loader.exec_module(module)
    return module


_validate_ref_name = _load_paperlog().validate_ref_name
_validate_ref_name(PUBLISH_REMOTE, "remote")
_validate_ref_name(PUBLISH_BRANCH, "branch")

_LOCAL_REF = f"refs/remotes/{PUBLISH_REMOTE}/{PUBLISH_BRANCH}"
_FETCH_SPEC = f"+refs/heads/{PUBLISH_BRANCH}:{_LOCAL_REF}"
_PUSH_SPEC = f"HEAD:refs/heads/{PUBLISH_BRANCH}"


class PublishError(Exception):
    """Publishing failed; ``reason`` is a stable identifier."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Snapshot:
    ledger: bytes
    portfolio: bytes | None
    contracts: bytes | None


@dataclass(frozen=True)
class PublishResult:
    outcome: str  # "published" | "unchanged"
    first_publish: bool
    commit: str | None
    foreign_author: str | None


def _text(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _git(run, args: list[str], cwd: Path, timeout: float):
    try:
        return run(
            ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
            cwd=str(cwd),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
            capture_output=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise PublishError("git-unavailable", f"{type(exc).__name__}: {exc}") from exc


def _check(proc, reason: str, what: str):
    if proc.returncode != 0:
        raise PublishError(reason, f"{what}: {_text(proc.stderr).strip()[:300]}")
    return proc


def _norm_url(url: str) -> str:
    url = url.strip().rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def resolve_remote_url(repo: Path, *, run=subprocess.run, timeout: float = GIT_TIMEOUT) -> str:
    """Read the ``fork`` URL of the development repo; refuse ``origin``."""
    fork = _git(run, ["remote", "get-url", PUBLISH_REMOTE], Path(repo), timeout)
    if fork.returncode != 0:
        raise PublishError("remote-missing", f"no '{PUBLISH_REMOTE}' remote in {repo}")
    fork_url = _text(fork.stdout).strip()
    origin = _git(run, ["remote", "get-url", "origin"], Path(repo), timeout)
    if origin.returncode == 0 and _norm_url(_text(origin.stdout)) == _norm_url(fork_url):
        raise PublishError(
            "remote-is-origin", f"'{PUBLISH_REMOTE}' points at origin; refusing to publish"
        )
    return fork_url


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def publish(
    snapshot: Snapshot,
    clone_dir: Path,
    remote_url: str,
    *,
    now_utc: datetime,
    ledger_lines: int,
    last_seq: int | None,
    run=subprocess.run,
    timeout: float = GIT_TIMEOUT,
) -> PublishResult:
    """Write the snapshot into the one-branch clone, commit on a diff, push."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must carry a time zone")
    clone_dir = Path(clone_dir)
    clone_dir.mkdir(parents=True, exist_ok=True)

    def git(*args: str):
        return _git(run, list(args), clone_dir, timeout)

    # (a) clone skeleton
    if not (clone_dir / ".git").exists():
        _check(git("init", "-q", "-b", PUBLISH_BRANCH, "."), "git-failed", "git init")
    have = git("remote", "get-url", PUBLISH_REMOTE)
    if have.returncode == 0:
        _check(git("remote", "set-url", PUBLISH_REMOTE, remote_url), "git-failed", "remote set-url")
    else:
        _check(git("remote", "add", PUBLISH_REMOTE, remote_url), "git-failed", "remote add")
    _check(
        git("config", f"remote.{PUBLISH_REMOTE}.fetch", _FETCH_SPEC), "git-failed", "config fetch"
    )
    _check(
        git("config", f"remote.{PUBLISH_REMOTE}.tagOpt", "--no-tags"), "git-failed", "config tagOpt"
    )

    # (b) first publish vs. update
    foreign_author: str | None = None
    ls = git("ls-remote", "--exit-code", "--heads", PUBLISH_REMOTE, PUBLISH_BRANCH)
    if ls.returncode == 0:
        first_publish = False
        _check(
            git("fetch", "--no-tags", "--quiet", PUBLISH_REMOTE, _FETCH_SPEC),
            "git-failed",
            "git fetch",
        )
        _check(git("reset", "-q", "--hard", _LOCAL_REF), "git-failed", "git reset")
        author = _check(git("log", "-1", "--format=%ae", _LOCAL_REF), "git-failed", "git log")
        email = _text(author.stdout).strip()
        if email and email != COMMIT_EMAIL:
            foreign_author = email
    elif ls.returncode == 2:
        first_publish = True
    else:
        raise PublishError(
            "ls-remote-failed", f"ls-remote rc={ls.returncode}: {_text(ls.stderr).strip()[:300]}"
        )

    # (c) write bytes
    names = [ATTRIBUTES_NAME, LEDGER_NAME]
    _write_bytes_atomic(clone_dir / ATTRIBUTES_NAME, ATTRIBUTES_BYTES)
    _write_bytes_atomic(clone_dir / LEDGER_NAME, snapshot.ledger)
    if snapshot.portfolio is not None:
        _write_bytes_atomic(clone_dir / PORTFOLIO_NAME, snapshot.portfolio)
        names.append(PORTFOLIO_NAME)
    if snapshot.contracts is not None:
        _write_bytes_atomic(clone_dir / CONTRACTS_NAME, snapshot.contracts)
        names.append(CONTRACTS_NAME)

    # (d) explicit staging only
    _check(git("add", "--", *names), "git-failed", "git add")

    # (e) commit only on a diff
    diff = git("diff", "--cached", "--quiet")
    if diff.returncode == 0:
        head = git("rev-parse", "--verify", "-q", "HEAD")
        if not (first_publish and head.returncode == 0):
            return PublishResult("unchanged", first_publish, None, foreign_author)
    elif diff.returncode == 1:
        stamp = now_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        seq = "none" if last_seq is None else str(last_seq)
        message = f"ibkr-publish: {stamp} ({ledger_lines} ledger line(s), last seq {seq})"
        _check(
            git(
                "-c",
                f"user.name={COMMIT_NAME}",
                "-c",
                f"user.email={COMMIT_EMAIL}",
                "commit",
                "-q",
                "-m",
                message,
            ),
            "git-failed",
            "git commit",
        )
    else:
        raise PublishError(
            "git-failed", f"git diff rc={diff.returncode}: {_text(diff.stderr).strip()[:300]}"
        )

    # (f) plain push, never forced
    push = git("push", "--porcelain", PUBLISH_REMOTE, _PUSH_SPEC)
    if push.returncode != 0:
        blob = (_text(push.stderr) + _text(push.stdout)).lower()
        if "rejected" in blob or "non-fast-forward" in blob or "fetch first" in blob:
            raise PublishError(
                "push-rejected",
                f"{PUBLISH_BRANCH} moved; one writer per branch (D-01) - nothing was forced",
            )
        raise PublishError("git-failed", f"git push: {_text(push.stderr).strip()[:300]}")
    rev = _check(git("rev-parse", "HEAD"), "git-failed", "git rev-parse")
    return PublishResult("published", first_publish, _text(rev.stdout).strip(), foreign_author)
