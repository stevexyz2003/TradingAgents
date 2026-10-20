"""Tests for the ibkr-log publisher (phase 7, plan 01). Real git, local bare repos only."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ibkr_publish.py"
if "ibkr_publish" in sys.modules:
    pub = sys.modules["ibkr_publish"]
else:
    _spec = importlib.util.spec_from_file_location("ibkr_publish", _SCRIPT)
    pub = importlib.util.module_from_spec(_spec)
    sys.modules["ibkr_publish"] = pub
    _spec.loader.exec_module(pub)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

NOW = datetime(2026, 10, 20, 7, 0, 0, tzinfo=UTC)
LEDGER = b'{"a":1}\r\n{"b":2}\n'
PORTFOLIO = '{"cash": "Straße"}'.encode()
CONTRACTS = b'{"AAPL": 1}\n'


def g(cwd, *args, check=True):
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=str(cwd),
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr!r}")
    return proc


def out(cwd, *args) -> str:
    return g(cwd, *args).stdout.decode().strip()


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch, tmp_path):
    cfg = tmp_path / "gitconfig-global"
    cfg.write_text("[user]\n\tname = Tester\n\temail = tester@example.invalid\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def remotes(tmp_path):
    fork = tmp_path / "fork.git"
    origin = tmp_path / "origin.git"
    for repo in (fork, origin):
        g(tmp_path, "init", "-q", "--bare", "-b", "main", str(repo))
    seed = tmp_path / "seed"
    g(tmp_path, "init", "-q", "-b", "paper-log", str(seed))
    (seed / "decision-log.md").write_text("x\n")
    g(seed, "add", "decision-log.md")
    g(seed, "commit", "-q", "-m", "seed")
    g(seed, "push", "-q", str(origin), "HEAD:refs/heads/paper-log")
    return fork, origin


def snap(ledger=LEDGER, portfolio=PORTFOLIO, contracts=CONTRACTS):
    return pub.Snapshot(ledger=ledger, portfolio=portfolio, contracts=contracts)


def do_publish(snapshot, clone, fork, **kw):
    return pub.publish(
        snapshot,
        clone,
        str(fork),
        now_utc=NOW,
        ledger_lines=2,
        last_seq=7,
        **kw,
    )


def tip(fork) -> str:
    return out(fork, "rev-parse", "refs/heads/ibkr-log")


class Recorder:
    def __init__(self, inner=subprocess.run, before_push=None):
        self.inner = inner
        self.calls = []
        self.before_push = before_push

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        if self.before_push is not None and "push" in argv:
            hook, self.before_push = self.before_push, None
            hook()
        return self.inner(argv, **kw)


@needs_git
def test_publish_first_creates_the_branch(tmp_path, remotes):
    fork, origin = remotes
    origin_before = out(origin, "rev-parse", "refs/heads/paper-log")
    result = do_publish(snap(), tmp_path / "clone", fork)
    assert result.outcome == "published"
    assert result.first_publish is True
    assert result.commit == tip(fork)
    names = out(fork, "ls-tree", "-r", "--name-only", "ibkr-log").splitlines()
    assert sorted(names) == [".gitattributes", "contracts.json", "ledger.jsonl", "portfolio.json"]
    assert out(origin, "rev-parse", "refs/heads/paper-log") == origin_before
    assert (
        g(origin, "rev-parse", "--verify", "-q", "refs/heads/ibkr-log", check=False).returncode != 0
    )


@needs_git
def test_publish_bytes_survive_autocrlf(tmp_path, monkeypatch, remotes):
    fork, _ = remotes
    cfg = tmp_path / "autocrlf-global"
    cfg.write_text("[core]\n\tautocrlf = true\n[user]\n\tname = T\n\temail = t@example.invalid\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    do_publish(snap(), tmp_path / "clone", fork)
    for name, data in (("ledger.jsonl", LEDGER), ("portfolio.json", PORTFOLIO)):
        blob = g(fork, "cat-file", "blob", f"ibkr-log:{name}").stdout
        assert blob == data


@needs_git
def test_publish_updates_on_change(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    do_publish(snap(), clone, fork)
    first = tip(fork)
    result = do_publish(snap(ledger=LEDGER + b'{"c":3}\n'), clone, fork)
    assert result.outcome == "published"
    assert result.first_publish is False
    assert out(fork, "rev-parse", "ibkr-log^") == first
    assert result.commit == tip(fork)


@needs_git
def test_publish_empty_diff_makes_no_commit(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    do_publish(snap(), clone, fork)
    before = tip(fork)
    result = do_publish(snap(), clone, fork)
    assert result.outcome == "unchanged"
    assert result.commit is None
    assert tip(fork) == before


@needs_git
def test_publish_keeps_portfolio_when_absent(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    do_publish(snap(), clone, fork)
    do_publish(snap(ledger=b"{}\n", portfolio=None, contracts=None), clone, fork)
    assert g(fork, "cat-file", "blob", "ibkr-log:portfolio.json").stdout == PORTFOLIO
    assert g(fork, "cat-file", "blob", "ibkr-log:contracts.json").stdout == CONTRACTS
    assert g(fork, "cat-file", "blob", "ibkr-log:ledger.jsonl").stdout == b"{}\n"


@needs_git
def test_publish_retries_an_unpushed_first_commit(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"

    def failing(argv, **kw):
        if "push" in argv:
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.run(argv, **kw)

    with pytest.raises(pub.PublishError) as err:
        do_publish(snap(), clone, fork, run=failing)
    assert err.value.reason == "git-unavailable"
    assert (
        g(fork, "rev-parse", "--verify", "-q", "refs/heads/ibkr-log", check=False).returncode != 0
    )
    result = do_publish(snap(), clone, fork)
    assert result.outcome == "published"
    assert result.first_publish is True
    assert result.commit == tip(fork)


@needs_git
def test_publish_non_fast_forward_is_rejected_not_forced(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    do_publish(snap(), clone, fork)
    other = tmp_path / "other"
    g(tmp_path, "clone", "-q", "-b", "ibkr-log", str(fork), str(other))

    def foreign_push():
        (other / "foreign.txt").write_text("hi\n")
        g(other, "add", "foreign.txt")
        g(other, "-c", "user.email=other@example.invalid", "commit", "-q", "-m", "foreign")
        g(other, "push", "-q", "origin", "HEAD:refs/heads/ibkr-log")

    recorder = Recorder(before_push=foreign_push)
    with pytest.raises(pub.PublishError) as err:
        do_publish(snap(ledger=b"{}\n"), clone, fork, run=recorder)
    assert err.value.reason == "push-rejected"
    assert tip(fork) == out(other, "rev-parse", "HEAD")


@needs_git
def test_publish_flags_a_foreign_author(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    do_publish(snap(), clone, fork)
    other = tmp_path / "other"
    g(tmp_path, "clone", "-q", "-b", "ibkr-log", str(fork), str(other))
    (other / "foreign.txt").write_text("hi\n")
    g(other, "add", "foreign.txt")
    g(other, "-c", "user.email=other@example.invalid", "commit", "-q", "-m", "foreign")
    g(other, "push", "-q", "origin", "HEAD:refs/heads/ibkr-log")
    result = do_publish(snap(ledger=b"{}\n"), clone, fork)
    assert result.foreign_author == "other@example.invalid"
    assert result.outcome == "published"


@needs_git
def test_publish_argv_never_names_origin_or_paper_log_or_force(tmp_path, remotes):
    fork, _ = remotes
    clone = tmp_path / "clone"
    recorder = Recorder()
    do_publish(snap(), clone, fork, run=recorder)
    do_publish(snap(ledger=b"{}\n"), clone, fork, run=recorder)
    assert recorder.calls
    forbidden = {"origin", "paper-log", "--force", "--force-with-lease", "-f"}
    for argv, kw in recorder.calls:
        assert not forbidden & set(argv), argv
        assert "timeout" in kw
        if "push" in argv:
            spec = argv[-1]
            assert spec == "HEAD:refs/heads/ibkr-log"
            assert not spec.startswith("+")
            assert argv[-2] == "fork"


@needs_git
def test_publish_env_blocks_prompts(tmp_path, remotes):
    fork, _ = remotes
    recorder = Recorder()
    do_publish(snap(), tmp_path / "clone", fork, run=recorder)
    for _argv, kw in recorder.calls:
        assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kw["env"]["GCM_INTERACTIVE"] == "never"


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired(["git"], 1), OSError("no git")])
def test_publish_git_unavailable(tmp_path, exc):
    def boom(argv, **kw):
        raise exc

    with pytest.raises(pub.PublishError) as err:
        do_publish(snap(), tmp_path / "clone", tmp_path / "x.git", run=boom)
    assert err.value.reason == "git-unavailable"


def test_publish_ls_remote_failure(tmp_path):
    def runner(argv, **kw):
        rc = 128 if "ls-remote" in argv else 0
        return subprocess.CompletedProcess(argv, rc, stdout=b"", stderr=b"fatal")

    with pytest.raises(pub.PublishError) as err:
        do_publish(snap(), tmp_path / "clone", tmp_path / "x.git", run=runner)
    assert err.value.reason == "ls-remote-failed"


def test_publish_requires_aware_time(tmp_path):
    with pytest.raises(ValueError):
        pub.publish(
            snap(),
            tmp_path / "c",
            "x",
            now_utc=datetime(2026, 1, 1),
            ledger_lines=0,
            last_seq=None,
        )


@needs_git
def test_resolve_remote_url_missing_fork(tmp_path):
    repo = tmp_path / "dev"
    g(tmp_path, "init", "-q", str(repo))
    g(repo, "remote", "add", "origin", "https://example.invalid/a/b.git")
    with pytest.raises(pub.PublishError) as err:
        pub.resolve_remote_url(repo)
    assert err.value.reason == "remote-missing"


@needs_git
def test_resolve_remote_url_fork_is_origin(tmp_path):
    repo = tmp_path / "dev"
    g(tmp_path, "init", "-q", str(repo))
    g(repo, "remote", "add", "origin", "https://example.invalid/a/b.git")
    g(repo, "remote", "add", "fork", "https://example.invalid/a/b/")
    with pytest.raises(pub.PublishError) as err:
        pub.resolve_remote_url(repo)
    assert err.value.reason == "remote-is-origin"


@needs_git
def test_resolve_remote_url_returns_fork(tmp_path):
    repo = tmp_path / "dev"
    g(tmp_path, "init", "-q", str(repo))
    g(repo, "remote", "add", "origin", "https://example.invalid/a/b.git")
    g(repo, "remote", "add", "fork", "https://example.invalid/c/d.git")
    assert pub.resolve_remote_url(repo) == "https://example.invalid/c/d.git"
