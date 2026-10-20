"""Tests for the paper-log reader (phase 4, plan 04)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ibkr_paperlog.py"
if "ibkr_paperlog" in sys.modules:
    pl = sys.modules["ibkr_paperlog"]
else:
    _spec = importlib.util.spec_from_file_location("ibkr_paperlog", _SCRIPT)
    pl = importlib.util.module_from_spec(_spec)
    sys.modules["ibkr_paperlog"] = pl
    _spec.loader.exec_module(pl)

SHA = "a" * 40


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        r = self.responses.pop(0)
        if isinstance(r, BaseException):
            raise r
        rc, out, err = r
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr=err)


def _ok_fetch():
    # fetch into the private ref, resolve it, drop the ref again
    return [(0, b"", b""), (0, (SHA + "\n").encode(), b""), (0, b"", b"")]


def _log(runner):
    return pl.GitPaperLog(Path("."), "fork", "paper-log", run=runner)


def test_fetch_commands_and_env():
    r = FakeRunner(_ok_fetch())
    assert _log(r).fetch() == SHA
    argv0, kw0 = r.calls[0]
    ref = r.calls[1][0][-1][: -len("^{commit}")]
    assert ref.startswith("refs/tengx/paper-log-preview/")
    assert argv0 == [
        "git", "fetch", "--no-tags", "--quiet", "fork", f"+refs/heads/paper-log:{ref}"
    ]
    assert kw0["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kw0["timeout"] == 60.0
    assert "shell" not in kw0
    assert r.calls[1][0] == ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"]
    assert r.calls[2][0] == ["git", "update-ref", "-d", ref]
    assert all("FETCH_HEAD" not in a for argv, _ in r.calls for a in argv)


def test_fetch_resolves_a_private_ref_not_the_shared_fetch_head():
    """WR-02: a concurrent fetch rewriting FETCH_HEAD must not change the pinned sha."""
    r1, r2 = FakeRunner(_ok_fetch()), FakeRunner(_ok_fetch())
    _log(r1).fetch()
    _log(r2).fetch()
    ref1 = r1.calls[0][0][-1].split(":", 1)[1]
    ref2 = r2.calls[0][0][-1].split(":", 1)[1]
    assert ref1 != ref2  # two runs never share a ref either


def test_second_failed_fetch_forgets_the_old_sha():
    log = _log(FakeRunner(_ok_fetch() + [(128, b"", b"fatal: offline")]))
    assert log.fetch() == SHA
    with pytest.raises(pl.PaperLogUnavailable):
        log.fetch()
    assert log.sha is None


def test_fetch_failure_no_fallback():
    r = FakeRunner([(128, b"", b"fatal: unable to access")])
    with pytest.raises(pl.PaperLogUnavailable) as ei:
        _log(r).fetch()
    assert "unable to access" in ei.value.reason
    assert len(r.calls) == 1


@pytest.mark.parametrize(
    "exc", [subprocess.TimeoutExpired("git", 1), FileNotFoundError("git")]
)
def test_fetch_exceptions(exc):
    with pytest.raises(pl.PaperLogUnavailable):
        _log(FakeRunner([exc])).fetch()


def test_fetch_bad_sha():
    r = FakeRunner([(0, b"", b""), (0, b"not-a-sha\n", b""), (0, b"", b"")])
    with pytest.raises(pl.PaperLogUnavailable):
        _log(r).fetch()


def test_read_before_fetch():
    with pytest.raises(RuntimeError):
        _log(FakeRunner([])).read("decision-log.md")


def test_read_blob_and_missing():
    r = FakeRunner(
        _ok_fetch() + [(0, b"a\r\nb", b""), (128, b"", b"fatal: path"), (0, b"", b"")]
    )
    log = _log(r)
    log.fetch()
    assert log.read("decision-log.md") == b"a\r\nb"
    assert r.calls[3][0] == ["git", "cat-file", "blob", f"{SHA}:decision-log.md"]
    with pytest.raises(pl.BlobMissing):
        log.read("runs/2026-01-01/summary.json")
    assert r.calls[-1][0] == ["git", "cat-file", "-e", f"{SHA}^{{commit}}"]


def test_read_failure_with_missing_commit_is_unavailable_not_missing():
    """WR-06: a damaged or shallow repo must not read as 'file missing'."""
    r = FakeRunner(
        _ok_fetch() + [(128, b"", b"fatal: bad object"), (128, b"", b"fatal: Not a valid")]
    )
    log = _log(r)
    log.fetch()
    with pytest.raises(pl.PaperLogUnavailable) as ei:
        log.read("decision-log.md")
    assert "bad object" in ei.value.reason


@pytest.mark.parametrize("bad", ["../x", "-p", "/abs", "", "a//b", "a b"])
def test_read_rejects_bad_path(bad):
    r = FakeRunner(_ok_fetch())
    log = _log(r)
    log.fetch()
    n = len(r.calls)
    with pytest.raises(ValueError):
        log.read(bad)
    assert len(r.calls) == n


def test_list_run_dates():
    out = b"runs/2026-10-09\nruns/2026-09-24\nruns/other\nruns/2026-1-1\n"
    r = FakeRunner(_ok_fetch() + [(0, out, b"")])
    log = _log(r)
    log.fetch()
    assert log.list_run_dates() == ("2026-09-24", "2026-10-09")
    assert r.calls[3][0] == ["git", "ls-tree", "--name-only", SHA, "runs/"]


@pytest.mark.parametrize("bad", ["-upload-pack=x", "a..b", "a b", ""])
def test_validate_ref_name_rejects(bad):
    with pytest.raises(ValueError):
        pl.validate_ref_name(bad, "remote")


@pytest.mark.parametrize("good", ["fork", "paper-log", "feature/x_1.2"])
def test_validate_ref_name_accepts(good):
    assert pl.validate_ref_name(good, "branch") == good


def test_constructor_validates():
    with pytest.raises(ValueError):
        pl.GitPaperLog(Path("."), "-x", "paper-log")


def test_decode_utf8():
    with pytest.raises(pl.PaperLogUnavailable):
        pl.decode_utf8(b"\xff", "decision-log.md")
    assert pl.decode_utf8(b"a\r\nb", "x") == "a\r\nb"


def test_summary_path():
    assert pl.summary_path("2026-10-09") == "runs/2026-10-09/summary.json"
    for bad in ("2026-10-9", "../2026-10-09"):
        with pytest.raises(ValueError):
            pl.summary_path(bad)


def test_real_git_fetch_without_checkout(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")

    def g(cwd, *a):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *a],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    remote, work = tmp_path / "remote", tmp_path / "work"
    remote.mkdir()
    work.mkdir()
    g(remote, "init", "-q", "-b", "paper-log")
    (remote / "decision-log.md").write_bytes(b"hello\r\n")
    g(remote, "add", "decision-log.md")
    g(remote, "commit", "-q", "-m", "x")
    sha = g(remote, "rev-parse", "HEAD").stdout.decode().strip()
    g(work, "init", "-q")
    g(work, "remote", "add", "fixture", str(remote))
    log = pl.GitPaperLog(work, "fixture", "paper-log")
    assert log.fetch() == sha
    assert log.read("decision-log.md") == b"hello\r\n"
    assert [p.name for p in work.iterdir()] == [".git"]


# --- frozen fixture of paper-log commit 71df89d ---------------------------------

import hashlib  # noqa: E402

from tests.paper_log_fixture import (  # noqa: E402
    FROZEN_BLOB_IDS,
    FROZEN_DIR,
    FROZEN_SHA,
    FixturePaperLog,
    write_paper_log,
)


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@pytest.mark.parametrize("rel", sorted(FROZEN_BLOB_IDS))
def test_frozen_bytes_match_blob_ids(rel):
    assert _blob_id((FROZEN_DIR / rel).read_bytes()) == FROZEN_BLOB_IDS[rel]


def test_frozen_fixture_reads():
    src = FixturePaperLog(FROZEN_DIR, FROZEN_SHA)
    assert src.fetch() == FROZEN_SHA
    assert src.read("decision-log.md") == (FROZEN_DIR / "decision-log.md").read_bytes()
    with pytest.raises(pl.BlobMissing):
        src.read("runs/2026-10-08/summary.json")
    assert src.list_run_dates() == ("2026-10-09",)


def test_fixture_unavailable():
    with pytest.raises(pl.PaperLogUnavailable):
        FixturePaperLog.unavailable("offline").fetch()


def test_frozen_log_parses():
    from tradingagents.memory.log import TradingMemoryLog

    entries = TradingMemoryLog(
        {"memory_log_path": str(FROZEN_DIR / "decision-log.md")}
    ).load_entries()
    assert len(entries) == 1
    e = entries[0]
    assert (e["date"], e["ticker"], e["rating"]) == ("2026-10-09", "AAPL", "Hold")


def test_fixture_write_paper_log_roundtrip(tmp_path):
    from tradingagents.memory.log import TradingMemoryLog

    root = write_paper_log(
        tmp_path / "pl",
        entries=[("2026-10-09", "AAPL", "Buy")],
        summaries={"2026-10-09": {"schema_version": 1}},
    )
    src = FixturePaperLog(root, FROZEN_SHA)
    src.fetch()
    assert src.list_run_dates() == ("2026-10-09",)
    assert b"schema_version" in src.read("runs/2026-10-09/summary.json")
    log = TradingMemoryLog({"memory_log_path": str(root / "decision-log.md")})
    assert log.load_entries()[0]["rating"] == "Buy"


# --- fetch_depth (plan 07-03) ------------------------------------------------------


def test_fetch_depth_default_keeps_argv():
    r = FakeRunner(_ok_fetch())
    _log(r).fetch()
    assert not any(a.startswith("--depth") for a in r.calls[0][0])


def test_fetch_depth_adds_depth_flag():
    r = FakeRunner(_ok_fetch())
    pl.GitPaperLog(Path("."), "fork", "paper-log", run=r, fetch_depth=1).fetch()
    argv = r.calls[0][0]
    assert argv[:6] == ["git", "fetch", "--no-tags", "--quiet", "--depth=1", "fork"]


@pytest.mark.parametrize("bad", [0, -1, True, "1", 1.5])
def test_fetch_depth_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        pl.GitPaperLog(Path("."), "fork", "paper-log", fetch_depth=bad)


def test_real_git_shallow_fetch_reads_blob(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")

    def g(cwd, *a):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *a],
            cwd=cwd,
            check=True,
            capture_output=True,
        )

    remote, work = tmp_path / "remote", tmp_path / "work"
    remote.mkdir()
    work.mkdir()
    g(remote, "init", "-q", "-b", "paper-log")
    for i in range(3):
        (remote / "f.txt").write_bytes(f"v{i}\n".encode())
        g(remote, "add", "f.txt")
        g(remote, "commit", "-q", "-m", f"c{i}")
    g(work, "init", "-q")
    g(work, "remote", "add", "fixture", remote.as_uri())
    log = pl.GitPaperLog(work, "fixture", "paper-log", fetch_depth=1)
    log.fetch()
    assert log.read("f.txt") == b"v2\n"
    assert g(work, "rev-list", "--count", log.sha).stdout.decode().strip() == "1"
