"""Tests for the state maintenance tool (scripts/state_maintenance.py).

Operational tooling with a delete function, working on the track record, so the
behaviours that could lose data are the ones covered here: dry-run by default,
sidecars removed together with their ``.db``, the decision log never touched,
and the integrity check going through ``sqlite3.DatabaseError`` rather than a
return-value comparison — a corrupt image makes ``PRAGMA quick_check`` *raise*,
so a naive ``row[0] != "ok"`` never sees anything.

Every path is passed in explicitly from ``tmp_path``; nothing here reads ``~``
or the operator's own files.
"""

import importlib.util
import json
import os
import sqlite3
import tarfile
import time
from datetime import datetime
from pathlib import Path

from tradingagents.graph.checkpointer import get_checkpointer
from tradingagents.memory.log import TradingMemoryLog

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state_maintenance.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("state_maintenance", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()

_DAY = 86400.0


def _make_checkpoint_db(cache_dir: Path, ticker: str) -> Path:
    """A real checkpoint DB, created by the library itself (tables included)."""
    with get_checkpointer(cache_dir, ticker):
        pass
    return cache_dir / "checkpoints" / f"{ticker}.db"


def _age(path: Path, days: float) -> None:
    when = time.time() - days * _DAY
    os.utime(path, (when, when))


def _entry(date: str, ticker: str, rating: str = "Overweight", fields: int = 4) -> str:
    """One log block in the shape ``store_decision`` writes.

    ``fields=3`` truncates the tag line, which is exactly what ``_parse_entry``
    drops silently (log.py:310-341).
    """
    tag = "[" + " | ".join([date, ticker, rating, "pending"][:fields]) + "]"
    return f"{tag}\n\nDECISION:\nStub decision text."


def _write_log(path: Path, blocks: list[str], trailing_separator: bool = True) -> None:
    text = TradingMemoryLog._SEPARATOR.join(blocks)
    if trailing_separator:
        text += TradingMemoryLog._SEPARATOR
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _verify(cache_dir: Path, memory_log: Path) -> int:
    return tool.main(
        ["verify", "--cache-dir", str(cache_dir), "--memory-log", str(memory_log)]
    )


# --- verify: checkpoint databases ---


def test_verify_accepts_a_healthy_checkpoint_db(tmp_path, capsys):
    cache = tmp_path / "cache"
    _make_checkpoint_db(cache, "AAPL")

    rc = _verify(cache, tmp_path / "no-such-log.md")

    out = capsys.readouterr().out
    assert rc == 0
    assert "AAPL.db" in out
    assert "ok" in out


def test_verify_flags_a_corrupt_checkpoint_db(tmp_path, capsys):
    """The one that fails a naive implementation: the pragma raises here."""
    cache = tmp_path / "cache"
    db = _make_checkpoint_db(cache, "AAPL")
    with open(db, "r+b") as handle:
        handle.seek(4096)
        handle.write(b"GARBAGE!" * 512)

    rc = _verify(cache, tmp_path / "no-such-log.md")

    out = capsys.readouterr().out
    assert rc == 2
    assert "malformed" in out


def test_verify_flags_a_file_that_is_not_a_database(tmp_path, capsys):
    cache = tmp_path / "cache"
    (cache / "checkpoints").mkdir(parents=True)
    (cache / "checkpoints" / "BAD.db").write_bytes(b"not a database, only bytes\n" * 400)

    rc = _verify(cache, tmp_path / "no-such-log.md")

    out = capsys.readouterr().out
    assert rc == 2
    assert "file is not a database" in out


def test_verify_flags_a_db_with_a_missing_table(tmp_path, capsys):
    """"I can query it" is not an integrity check: the same corrupt file

    answered ``select count(*) from checkpoints`` with 1 during research. So the
    schema is checked too.
    """
    cache = tmp_path / "cache"
    db = _make_checkpoint_db(cache, "AAPL")
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP TABLE writes")
        conn.commit()
    finally:
        conn.close()

    rc = _verify(cache, tmp_path / "no-such-log.md")

    out = capsys.readouterr().out
    assert rc == 2
    assert "writes" in out


# --- verify: the decision log, four cases ---


def test_verify_accepts_a_well_formed_decision_log(tmp_path):
    log = tmp_path / "state" / "decision-log.md"
    _write_log(log, [_entry("2026-10-08", "AAPL"), _entry("2026-10-09", "MSFT")])

    assert _verify(tmp_path / "cache", log) == 0


def test_verify_flags_an_entry_the_parser_drops_silently(tmp_path, capsys):
    log = tmp_path / "state" / "decision-log.md"
    _write_log(
        log,
        [_entry("2026-10-08", "AAPL"), _entry("2026-10-09", "MSFT", fields=3)],
    )

    rc = _verify(tmp_path / "cache", log)

    out = capsys.readouterr().out
    assert rc == 2
    assert "1/2" in out


def test_verify_accepts_an_intact_log_without_a_trailing_separator(tmp_path):
    """A hand-edited or ``git checkout``-restored log has no trailing separator.

    Counting separators would call this broken; comparing non-empty blocks does not.
    """
    log = tmp_path / "state" / "decision-log.md"
    _write_log(
        log,
        [_entry("2026-10-08", "AAPL"), _entry("2026-10-09", "MSFT")],
        trailing_separator=False,
    )

    assert _verify(tmp_path / "cache", log) == 0


def test_verify_flags_a_broken_entry_without_a_trailing_separator(tmp_path):
    """And the other direction: a missing separator must not hide a real finding."""
    log = tmp_path / "state" / "decision-log.md"
    _write_log(
        log,
        [_entry("2026-10-08", "AAPL"), _entry("2026-10-09", "MSFT", fields=3)],
        trailing_separator=False,
    )

    assert _verify(tmp_path / "cache", log) == 2


def test_verify_accepts_an_empty_decision_log(tmp_path):
    log = tmp_path / "state" / "decision-log.md"
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")

    assert _verify(tmp_path / "cache", log) == 0


# --- prune ---


def test_prune_without_apply_deletes_nothing(tmp_path, capsys):
    cache = tmp_path / "cache"
    results = tmp_path / "logs"
    db = _make_checkpoint_db(cache, "AAPL")
    _age(db, 10)
    report = results / "reports" / "AAPL_20250101_120000"
    report.mkdir(parents=True)
    (report / "complete_report.md").write_text("old", encoding="utf-8")

    rc = tool.main(["prune", "--cache-dir", str(cache), "--results-dir", str(results)])

    out = capsys.readouterr().out
    assert rc == 0
    assert db.exists()
    assert report.exists()
    assert "AAPL.db" in out
    assert "AAPL_20250101_120000" in out
    assert "--apply" in out


def test_prune_apply_removes_old_checkpoints_with_their_sidecars(tmp_path):
    cache = tmp_path / "cache"
    old = _make_checkpoint_db(cache, "AAPL")
    old_wal = old.with_name(old.name + "-wal")
    old_shm = old.with_name(old.name + "-shm")
    old_wal.write_bytes(b"wal")
    old_shm.write_bytes(b"shm")
    for path in (old, old_wal, old_shm):
        _age(path, 10)

    recent = _make_checkpoint_db(cache, "MSFT")
    recent_wal = recent.with_name(recent.name + "-wal")
    recent_wal.write_bytes(b"wal")
    for path in (recent, recent_wal):
        _age(path, 1)

    rc = tool.main(
        ["prune", "--apply", "--cache-dir", str(cache), "--results-dir", str(tmp_path / "logs")]
    )

    assert rc == 0
    assert not old.exists()
    assert not old_wal.exists()
    assert not old_shm.exists()
    assert recent.exists()
    assert recent_wal.exists()


def test_prune_apply_keeps_the_sidecars_of_a_db_it_decided_to_keep(tmp_path, capsys):
    """A glob metacharacter in a filename must not re-target the sidecar group.

    ``glob(f"{db.name}-*")`` turned the expired ``backup[1].db`` into the
    pattern ``backup[1].db-*``, whose ``[1]`` is a character class — so it
    matched ``backup1.db-wal``, the WAL of the database the same run had just
    decided to *keep*. In WAL mode that sidecar can hold the only copy of
    committed rows, so the surviving checkpoint is silently corrupted while the
    output reads as if nothing happened.
    """
    cache = tmp_path / "cache"
    cp_dir = cache / "checkpoints"
    cp_dir.mkdir(parents=True)
    expired = cp_dir / "backup[1].db"
    expired.write_bytes(b"expired, unrelated to backup1.db")
    _age(expired, 30)
    kept = cp_dir / "backup1.db"
    kept.write_bytes(b"fresh")
    kept_wal = cp_dir / "backup1.db-wal"
    kept_wal.write_bytes(b"committed rows that exist nowhere else")

    rc = tool.main(
        ["prune", "--apply", "--cache-dir", str(cache), "--results-dir", str(tmp_path / "logs")]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert not expired.exists()
    assert kept.exists()
    assert kept_wal.exists(), "the WAL of a kept database was deleted"
    deleted = [line for line in out.splitlines() if "deleted" in line]
    assert len(deleted) == 1
    assert "backup1.db-wal" not in deleted[0], f"the printed group is wrong: {deleted[0]}"


def test_prune_never_touches_the_decision_log(tmp_path, capsys):
    """Operator decision: the decision log has unlimited retention.

    The logs sit where a careless directory sweep would take them: inside the
    pruned results directory, and at the CLI's default memory-log location.
    """
    cache = tmp_path / "cache"
    results = tmp_path / "logs"
    results.mkdir()
    db = _make_checkpoint_db(cache, "AAPL")
    paper_log = results / "decision-log.md"
    _write_log(paper_log, [_entry("2026-10-08", "AAPL")])
    cli_log = tmp_path / "memory" / "trading_memory.md"
    _write_log(cli_log, [_entry("2026-10-09", "MSFT")])
    before_paper = paper_log.read_bytes()
    before_cli = cli_log.read_bytes()

    rc = tool.main(
        [
            "prune",
            "--apply",
            "--checkpoint-days",
            "0",
            "--cache-dir",
            str(cache),
            "--results-dir",
            str(results),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert not db.exists(), "--checkpoint-days 0 should have pruned the database"
    assert paper_log.read_bytes() == before_paper
    assert cli_log.read_bytes() == before_cli
    assert "decision log: kept" in out


def test_prune_apply_removes_old_report_directories_by_stamp(tmp_path, capsys):
    """The stamp in the name decides, not the mtime: both directories are new on disk."""
    results = tmp_path / "logs"
    reports = results / "reports"
    reports.mkdir(parents=True)
    old = reports / "AAPL_20250101_120000"
    old.mkdir()
    (old / "complete_report.md").write_text("old", encoding="utf-8")
    fresh = reports / f"AAPL_{datetime.now():%Y%m%d_%H%M%S}"
    fresh.mkdir()
    foreign = reports / "notareport"
    foreign.mkdir()

    rc = tool.main(
        ["prune", "--apply", "--cache-dir", str(tmp_path / "cache"), "--results-dir", str(results)]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert not old.exists()
    assert fresh.exists()
    assert foreign.exists()
    assert "notareport" in out


# --- prune: the day limit is the only guard rail, so it has a lower bound ---


def _today_report(results: Path) -> Path:
    report = results / "reports" / f"AAPL_{datetime.now():%Y%m%d_%H%M%S}"
    report.mkdir(parents=True)
    (report / "complete_report.md").write_text("today's analysis", encoding="utf-8")
    return report


def test_prune_refuses_negative_day_limits(tmp_path, capsys):
    """A sign typo must not delete today's state.

    A negative limit pushes the cutoff into the *future*, so every candidate is
    "expired": ``--report-days -1`` rmtree'd today's consolidated report tree,
    irreplaceable analysis output under a declared 90-day retention.
    """
    cache = tmp_path / "cache"
    results = tmp_path / "logs"
    db = _make_checkpoint_db(cache, "AAPL")
    report = _today_report(results)

    rc = tool.main(
        [
            "prune",
            "--apply",
            "--checkpoint-days",
            "-1",
            "--report-days",
            "-1",
            "--cache-dir",
            str(cache),
            "--results-dir",
            str(results),
        ]
    )

    out = capsys.readouterr().out
    assert report.exists(), "a negative --report-days deleted today's report tree"
    assert db.exists(), "a negative --checkpoint-days deleted a fresh checkpoint"
    assert rc == 1
    assert "--checkpoint-days" in out


def test_prune_refuses_a_negative_report_day_limit_on_its_own(tmp_path, capsys):
    """Both limits are checked, not just the first one."""
    results = tmp_path / "logs"
    report = _today_report(results)

    rc = tool.main(
        [
            "prune",
            "--apply",
            "--report-days",
            "-90",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--results-dir",
            str(results),
        ]
    )

    out = capsys.readouterr().out
    assert rc == 1
    assert report.exists()
    assert "--report-days" in out


def test_prune_accepts_a_zero_report_day_limit(tmp_path):
    """Zero stays legal: it means "everything is older than the limit"."""
    results = tmp_path / "logs"
    report = _today_report(results)

    rc = tool.main(
        [
            "prune",
            "--apply",
            "--report-days",
            "0",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--results-dir",
            str(results),
        ]
    )

    assert rc == 0
    assert not report.exists()


# --- backup ---


def test_backup_packs_the_allow_list_and_nothing_else(tmp_path, capsys):
    state = tmp_path / "state"
    (state / "runs" / "2026-10-09").mkdir(parents=True)
    _write_log(state / "decision-log.md", [_entry("2026-10-09", "AAPL")])
    (state / "index.md").write_text("# Paper-run index\n", encoding="utf-8")
    (state / "runs" / "2026-10-09" / "summary.json").write_text(
        json.dumps({"schema_version": 1}), encoding="utf-8"
    )
    # Must stay out: a lock sidecar, a temp file, a secret, a checkpoint DB.
    (state / "decision-log.md.lock").write_text("", encoding="utf-8")
    (state / "decision-log.tmp").write_text("half a rewrite", encoding="utf-8")
    (state / "secrets.env").write_text("ANTHROPIC_API_KEY=real\n", encoding="utf-8")
    cache = tmp_path / "cache"
    _make_checkpoint_db(cache, "AAPL")
    cli_log = tmp_path / "memory" / "trading_memory.md"
    _write_log(cli_log, [_entry("2026-10-08", "MSFT")])
    out_dir = tmp_path / "backups"

    rc = tool.main(
        [
            "backup",
            "--out",
            str(out_dir),
            "--state-dir",
            str(state),
            "--memory-log",
            str(cli_log),
        ]
    )

    printed = capsys.readouterr().out
    assert rc == 0
    archives = sorted(out_dir.glob("tex-state-*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as tar:
        members = tar.getnames()
    assert any(m.endswith("decision-log.md") for m in members)
    assert any(m.endswith("index.md") for m in members)
    assert any(m.endswith("runs/2026-10-09/summary.json") for m in members)
    assert not any(m.endswith(".db") for m in members)
    assert not any(m.endswith(".lock") for m in members)
    assert not any(m.endswith(".tmp") for m in members)
    assert not any("secrets.env" in m for m in members)
    # One top-level directory, so unpacking cannot litter the cwd.
    assert len({m.split("/")[0] for m in members}) == 1
    assert str(archives[0].name) in printed


# --- usage errors return 1, not SystemExit ---


def test_unknown_subcommand_returns_one(capsys):
    assert tool.main(["frobnicate"]) == 1
    capsys.readouterr()


def test_no_subcommand_returns_one(capsys):
    assert tool.main([]) == 1
    capsys.readouterr()


def test_backup_without_out_returns_one(tmp_path, capsys):
    rc = tool.main(["backup", "--state-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--out" in captured.out + captured.err


def test_backup_without_state_dir_returns_one(tmp_path, capsys):
    rc = tool.main(["backup", "--out", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "--state-dir" in captured.out + captured.err
