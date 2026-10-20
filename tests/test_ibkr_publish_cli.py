"""The ``publish`` command of the IBKR executor (phase 7, plan 06).

Real git against local bare repositories only; no gateway, no network, no real remote.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradingagents.dataflows import files

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ibkr_executor.py"


def _load_executor():
    spec = importlib.util.spec_from_file_location("ibkr_executor", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = _load_executor()
ledger_mod = executor.load_ledger_module()

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

NOW = datetime(2026, 10, 20, 7, 0, 0, tzinfo=UTC)


def g(cwd, *args, check=True):
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args], cwd=str(cwd), capture_output=True, check=False
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
def world(tmp_path):
    """fork.git and origin.git (with paper-log) and a development repo pointing at both."""
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
    dev = tmp_path / "dev"
    g(tmp_path, "init", "-q", "-b", "main", str(dev))
    g(dev, "remote", "add", "fork", str(fork))
    g(dev, "remote", "add", "origin", str(origin))
    return dev, fork, origin


def _origin_refs(origin) -> str:
    return out(origin, "for-each-ref")


def _write_ledger(lines=2):
    path = executor.default_ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = ledger_mod.Ledger.open(
        path, mode=ledger_mod.MODE_LIVE, clock=lambda: NOW, run_id="seed"
    )
    for index in range(lines):
        ledger.append(
            ledger_mod.SKIPPED,
            reason="hold",
            decision_key=f"2026-10-09|T{index}",
            ticker=f"T{index}",
        )
    return path


def _write_portfolio(as_of="2026-10-20T08:00:00+00:00"):
    path = executor.default_portfolio_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"cash": 1.0}
    if as_of is not None:
        data["as_of"] = as_of
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_contracts():
    path = executor.default_contracts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"AAPL": 1}\n', encoding="utf-8")


def _log_text() -> str:
    return executor.default_log_file().read_text(encoding="utf-8")


def _publish(dev, argv=(), **kw):
    return executor.main(["publish", *argv], clock=lambda: NOW, publish_repo=dev, **kw)


@needs_git
def test_publish_cli_first_publish_then_unchanged(world, capsys):
    dev, fork, origin = world
    _write_ledger()
    _write_portfolio()
    _write_contracts()
    before = _origin_refs(origin)

    assert _publish(dev) == executor.EXIT_OK
    stdout = capsys.readouterr().out
    sha = out(fork, "rev-parse", "refs/heads/ibkr-log")
    assert f"publish: published {sha[:12]} to fork/ibkr-log (first publish)" in stdout
    assert "ibkr-state=PUBLISHED" in _log_text()
    assert _origin_refs(origin) == before
    assert (executor.default_publish_dir() / ".git").exists()
    tree = out(fork, "ls-tree", "--name-only", "ibkr-log").split()
    assert {"ledger.jsonl", "portfolio.json", "contracts.json"} <= set(tree)

    assert _publish(dev) == executor.EXIT_OK
    assert "publish: nothing to publish" in capsys.readouterr().out
    assert "ibkr-state=PUBLISH_UNCHANGED" in _log_text()


@needs_git
def test_publish_cli_lock_held_exits_7_without_git(world):
    dev, fork, _origin = world
    _write_ledger()
    calls = []

    def recorder(*a, **k):
        calls.append(a)
        raise AssertionError("no git call may happen while the lock is held")

    with files.locked(executor.default_ledger_file(), wait=False) as held:
        assert held
        assert _publish(dev, git_run=recorder) == executor.EXIT_LOCKED
    assert calls == []
    assert not executor.default_publish_dir().exists()
    assert "ibkr-state=LOCK_HELD" in _log_text()


@needs_git
def test_publish_cli_corrupt_ledger_exits_6(world):
    dev, fork, _origin = world
    path = _write_ledger(3)
    lines = path.read_bytes().split(b"\n")
    lines[1] = b"this is not json"
    path.write_bytes(b"\n".join(lines))

    assert _publish(dev) == executor.EXIT_RECONCILE
    assert "ibkr-state=LEDGER_CORRUPT" in _log_text()
    assert out(fork, "for-each-ref") == ""


@needs_git
def test_publish_cli_missing_ledger_exits_1(world):
    dev, fork, _origin = world
    assert _publish(dev) == executor.EXIT_CONFIG
    assert "ibkr-state=PUBLISH_NO_LEDGER" in _log_text()


@needs_git
def test_publish_cli_missing_fork_remote_exits_1(world):
    dev, fork, _origin = world
    g(dev, "remote", "remove", "fork")
    _write_ledger()
    assert _publish(dev) == executor.EXIT_CONFIG
    assert "ibkr-state=PUBLISH_REMOTE_MISSING" in _log_text()


@needs_git
def test_publish_cli_fork_equal_origin_exits_1(world):
    dev, fork, _origin = world
    g(dev, "remote", "set-url", "origin", str(fork))
    _write_ledger()
    assert _publish(dev) == executor.EXIT_CONFIG
    assert "ibkr-state=PUBLISH_REMOTE_IS_ORIGIN" in _log_text()
    assert out(fork, "for-each-ref") == ""


@needs_git
def test_publish_cli_rejected_push_exits_11(world, tmp_path, capsys):
    dev, fork, _origin = world
    _write_ledger()
    assert _publish(dev) == executor.EXIT_OK
    capsys.readouterr()
    _write_ledger(1)  # one more line, so the next publish has a diff

    def racing(argv, **kw):
        if "push" in argv:
            rival = tmp_path / "rival"
            g(tmp_path, "clone", "-q", "-b", "ibkr-log", str(fork), str(rival))
            (rival / "other.txt").write_text("second writer\n")
            g(rival, "add", "other.txt")
            g(rival, "commit", "-q", "-m", "rival")
            g(rival, "push", "-q", "origin", "HEAD:refs/heads/ibkr-log")
        return subprocess.run(argv, **kw)

    assert _publish(dev, git_run=racing) == executor.EXIT_PUBLISH
    assert "ibkr-state=PUBLISH_FAILED reason=push-rejected" in _log_text()
    assert "one writer per branch" in capsys.readouterr().err


@needs_git
def test_publish_cli_portfolio_missing_and_stale_are_warnings(world):
    dev, fork, _origin = world
    _write_ledger()
    assert _publish(dev) == executor.EXIT_OK
    assert "ibkr-state=PUBLISH_NO_PORTFOLIO" in _log_text()

    _write_portfolio(as_of="2026-10-19T08:00:00+00:00")  # older than the ledger's NOW
    assert _publish(dev) == executor.EXIT_OK
    assert "ibkr-state=PUBLISH_PORTFOLIO_OLDER_THAN_LEDGER" in _log_text()


@needs_git
def test_publish_cli_undated_portfolio_is_still_copied(world):
    dev, fork, _origin = world
    _write_ledger()
    _write_portfolio(as_of=None)
    assert _publish(dev) == executor.EXIT_OK
    assert "ibkr-state=PUBLISH_PORTFOLIO_UNDATED" in _log_text()
    assert "portfolio.json" in out(fork, "ls-tree", "--name-only", "ibkr-log")


@needs_git
def test_publish_cli_foreign_author_is_logged(world, tmp_path):
    dev, fork, _origin = world
    _write_ledger()
    assert _publish(dev) == executor.EXIT_OK
    rival = tmp_path / "rival"
    g(tmp_path, "clone", "-q", "-b", "ibkr-log", str(fork), str(rival))
    (rival / "other.txt").write_text("x\n")
    g(rival, "add", "other.txt")
    g(rival, "commit", "-q", "-m", "rival")
    g(rival, "push", "-q", "origin", "HEAD:refs/heads/ibkr-log")

    assert _publish(dev) == executor.EXIT_OK
    assert "ibkr-state=PUBLISH_FOREIGN_COMMIT author=tester@example.invalid" in _log_text()


@needs_git
def test_publish_cli_needs_no_gateway_and_no_env_file(world):
    dev, fork, _origin = world
    _write_ledger()
    calls = []

    def factory(*a, **k):
        calls.append(a)
        raise AssertionError("publish must not touch the gateway")

    assert _publish(dev, broker_factory=factory) == executor.EXIT_OK
    assert calls == []


def test_publish_cli_usage_and_no_env_file_option(capsys):
    assert executor.main([]) == executor.EXIT_CONFIG
    assert "account, resolve, preview, execute, publish" in capsys.readouterr().err
    assert executor.main(["publish", "--env-file", "x"]) == executor.EXIT_CONFIG


def test_publish_cli_exit_code_is_eleven():
    assert executor.EXIT_PUBLISH == 11
