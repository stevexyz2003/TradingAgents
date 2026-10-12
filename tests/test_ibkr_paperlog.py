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
    return [(0, b"", b""), (0, (SHA + "\n").encode(), b"")]


def _log(runner):
    return pl.GitPaperLog(Path("."), "fork", "paper-log", run=runner)


def test_fetch_commands_and_env():
    r = FakeRunner(_ok_fetch())
    assert _log(r).fetch() == SHA
    argv0, kw0 = r.calls[0]
    assert argv0 == ["git", "fetch", "--no-tags", "--quiet", "fork", "+refs/heads/paper-log"]
    assert kw0["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kw0["timeout"] == 60.0
    assert "shell" not in kw0
    assert r.calls[1][0] == ["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"]


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
    r = FakeRunner([(0, b"", b""), (0, b"not-a-sha\n", b"")])
    with pytest.raises(pl.PaperLogUnavailable):
        _log(r).fetch()


def test_read_before_fetch():
    with pytest.raises(RuntimeError):
        _log(FakeRunner([])).read("decision-log.md")


def test_read_blob_and_missing():
    r = FakeRunner(_ok_fetch() + [(0, b"a\r\nb", b""), (128, b"", b"fatal")])
    log = _log(r)
    log.fetch()
    assert log.read("decision-log.md") == b"a\r\nb"
    assert r.calls[2][0] == ["git", "cat-file", "blob", f"{SHA}:decision-log.md"]
    with pytest.raises(pl.BlobMissing):
        log.read("runs/2026-01-01/summary.json")


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
    assert r.calls[2][0] == ["git", "ls-tree", "--name-only", SHA, "runs/"]


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
