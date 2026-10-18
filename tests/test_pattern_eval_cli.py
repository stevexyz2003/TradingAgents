"""CLI scripts/pattern_eval.py: exit codes, ref validation, subprocess argument form."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SEP = "\n\n<!-- ENTRY_END -->\n\n"
LOG = SEP.join(
    [
        "[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]\n\n"
        "DECISION:\nx\n\nREFLECTION:\ny",
        "[2026-10-12 | AAPL | Overweight | pending]\n\nDECISION:\nz",
    ]
) + SEP


@pytest.fixture
def cli(monkeypatch):
    spec = importlib.util.spec_from_file_location("pattern_eval", ROOT / "scripts" / "pattern_eval.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pattern_eval"] = module
    spec.loader.exec_module(module)
    frame = pd.DataFrame(
        {"Date": pd.bdate_range("2025-06-01", periods=400), "Close": np.arange(400) + 100.0}
    )
    monkeypatch.setattr(module, "_price_loader", lambda: (lambda t, a: frame))
    return module


def test_log_run_reports_insufficient(cli, tmp_path, capsys):
    log = tmp_path / "decision-log.md"
    log.write_text(LOG, encoding="utf-8")
    assert cli.main(["--log", str(log)]) == 0
    assert "insufficient" in capsys.readouterr().out


def test_json_to_file(cli, tmp_path):
    log = tmp_path / "decision-log.md"
    log.write_text(LOG, encoding="utf-8")
    out = tmp_path / "r.json"
    assert cli.main(["--log", str(log), "--format", "json", "--out", str(out)]) == 0
    assert '"n_entries": 2' in out.read_text(encoding="utf-8")


def test_missing_prices_exit_3(cli, tmp_path, monkeypatch, capsys):
    log = tmp_path / "decision-log.md"
    log.write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(cli, "_price_loader", lambda: (lambda t, a: pd.DataFrame()))
    assert cli.main(["--log", str(log)]) == 3
    assert "WARNING" in capsys.readouterr().err


@pytest.mark.parametrize("ref", ["--evil", "a;b", "$(x)", "a b"])
def test_bad_ref_rejected_before_subprocess(cli, monkeypatch, ref):
    def boom(*a, **k):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(subprocess, "run", boom)
    assert cli.main(["--git-ref", ref]) == 1


def test_git_ref_uses_argument_list(cli, monkeypatch, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=LOG.encode(), stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli.main(["--git-ref", "fork/paper-log"]) == 0
    cmd, kwargs = calls[0]
    assert cmd == ["git", "show", "fork/paper-log:decision-log.md"]
    assert not kwargs.get("shell")
    assert "insufficient" in capsys.readouterr().out


def test_git_show_failure_is_config_error(cli, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 128, stdout=b"", stderr=b"bad ref"),
    )
    assert cli.main(["--git-ref", "nope/ref"]) == 1


def test_missing_log_file(cli, tmp_path):
    assert cli.main(["--log", str(tmp_path / "none.md")]) == 1
