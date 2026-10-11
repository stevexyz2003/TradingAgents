#!/usr/bin/env python3
"""State maintenance for the TradingEngineX strand: prune, backup, verify.

Operational tooling, not part of the ``tradingagents`` library: it works on the
files a run leaves behind — the decision log (the track record), the per-ticker
SQLite checkpoints and the report tree. Pure stdlib plus ``tradingagents``; no
network, no LLM.

Operating manual: ``scripts/STATE_OPERATIONS.md``.

    state_maintenance.py verify [--cache-dir P] [--memory-log P]
    state_maintenance.py prune  [--cache-dir P] [--results-dir P]
                                [--checkpoint-days 7] [--report-days 90] [--apply]
    state_maintenance.py backup --out DIR --state-dir DIR [--memory-log P]

``prune`` is a dry run by default; nothing is deleted without ``--apply``.

There is deliberately **no** ``rotate`` subcommand. The operator's retention
decision is that the decision log is kept unlimited and never trimmed
automatically — it is the track record and the basis of the alpha evaluation.
Rotation stays what it is today: an opt-in in code via ``memory_log_max_entries``
(no ``TRADINGAGENTS_*`` override, never set by the paper run). That is a
decision, not an omission.

Exit codes:
    0   ok
    1   usage/configuration error - nothing was done
    2   verify found something
"""

import argparse
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.memory.log import TradingMemoryLog

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_FINDING = 2

#: Tables a healthy LangGraph SQLite checkpoint carries (checkpointer.py:93).
CHECKPOINT_TABLES = ("checkpoints", "writes")

#: Report directories are ``<TICKER>_<YYYYmmdd>_<HHMMSS>`` (trading_graph.py:307).
#: Anything else is left alone: this tool deletes directories, so the name
#: pattern is the guard rail, not a convenience.
REPORT_DIR_RE = re.compile(r"^[A-Za-z0-9._-]+_(\d{8})_(\d{6})$")

#: Sidecars and scratch files never belong in a backup.
BACKUP_EXCLUDED_SUFFIXES = (".lock", ".tmp", ".db")

DEFAULT_CHECKPOINT_DAYS = 7
DEFAULT_REPORT_DAYS = 90
_DAY = 86400.0


# --- verify -----------------------------------------------------------------


def check_checkpoint_db(db: Path) -> str | None:
    """Return a finding for a checkpoint database, or None when it is healthy.

    The file and its ``-wal``/``-shm`` sidecars are copied to a temporary
    directory and the copy is checked: SQLite needs write access to ``-shm`` to
    read a WAL, so opening a database from a crashed run read-only in place is
    not guaranteed to work.
    """
    with tempfile.TemporaryDirectory(prefix="tex-verify-") as tmp:
        work = Path(tmp) / db.name
        shutil.copy2(db, work)
        for sidecar in sorted(db.parent.glob(f"{db.name}-*")):
            if sidecar.is_file():
                shutil.copy2(sidecar, Path(tmp) / sidecar.name)
        try:
            conn = sqlite3.connect(str(work))
        except sqlite3.DatabaseError as exc:
            return f"cannot open: {exc}"
        try:
            # PRAGMA quick_check *raises* on a corrupt image ("database disk
            # image is malformed") and on a garbage header ("file is not a
            # database"). A naive `row[0] != "ok"` never sees either.
            try:
                rows = conn.execute("PRAGMA quick_check").fetchall()
            except sqlite3.DatabaseError as exc:
                return f"quick_check failed: {exc}"
            result = rows[0][0] if rows else "<no result>"
            if result != "ok":
                return f"quick_check: {result}"
            # "I can query it" is not an integrity check: the same corrupt file
            # answered `select count(*) from checkpoints` with 1 during research.
            try:
                tables = {
                    row[0]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            except sqlite3.DatabaseError as exc:
                return f"cannot read the schema: {exc}"
            missing = [name for name in CHECKPOINT_TABLES if name not in tables]
            if missing:
                return f"missing table(s): {', '.join(missing)}"
        finally:
            conn.close()
    return None


def check_decision_log(path: Path) -> str | None:
    """Return a finding for the decision log, or None when it parses completely.

    The yardstick is the number of non-empty blocks, **not** the number of
    ``<!-- ENTRY_END -->`` separators. Counting separators goes wrong on exactly
    the recovery path the runbook documents: a hand-edited or
    ``git checkout``-restored log has no trailing separator, so the separator
    count is one short and the check would report a problem that is not there —
    and hide a real one in the other direction. A block whose tag line has fewer
    than four fields is dropped *silently* by ``_parse_entry``; comparing blocks
    against parsed entries is the only way to see it.
    """
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return None
    blocks = [block for block in text.split(TradingMemoryLog._SEPARATOR) if block.strip()]
    entries = TradingMemoryLog({"memory_log_path": str(path)}).load_entries()
    if len(entries) != len(blocks):
        return (
            f"only {len(entries)}/{len(blocks)} blocks parsed as entries — "
            "the parser drops a broken entry without a word; check the tag lines"
        )
    return None


def verify(cache_dir: str, memory_log: str) -> int:
    """Check every checkpoint database and the decision log. 2 on any finding."""
    findings = 0
    checked = 0

    cp_dir = Path(cache_dir).expanduser() / "checkpoints"
    if cp_dir.is_dir():
        for db in sorted(cp_dir.glob("*.db")):
            checked += 1
            problem = check_checkpoint_db(db)
            if problem:
                findings += 1
                print(f"FAIL: {db.name}: {problem}")
            else:
                print(f"ok: {db.name}")
    else:
        print(f"checkpoints: no directory at {cp_dir} (nothing to check)")

    log_path = Path(memory_log).expanduser()
    if log_path.is_file():
        checked += 1
        problem = check_decision_log(log_path)
        if problem:
            findings += 1
            print(f"FAIL: {log_path.name}: {problem}")
        else:
            print(f"ok: {log_path.name}")
    else:
        print(f"decision log: no file at {log_path} (nothing to check)")

    print(f"verify: {checked} object(s) checked, {findings} finding(s)")
    return EXIT_FINDING if findings else EXIT_OK


# --- prune ------------------------------------------------------------------


def _checkpoint_dir(cache_dir: str) -> Path | None:
    """Resolve ``<cache>/checkpoints``, or None when it escapes the cache dir.

    Safety belt for a tool that deletes: a symlinked ``checkpoints`` would
    otherwise let a prune reach outside the directory it was pointed at.
    """
    cache = Path(cache_dir).expanduser().resolve()
    cp_dir = (cache / "checkpoints").resolve()
    if cache not in cp_dir.parents:
        return None
    return cp_dir


def _prune_checkpoints(cp_dir: Path, days: int, apply_changes: bool) -> None:
    """Delete checkpoint databases older than ``days``, sidecars included.

    A *successful* run calls ``clear_checkpoint``, which deletes rows, not the
    file — so one ``.db`` per ticker accumulates forever. And ``-wal``/``-shm``
    survive a crash, which is why deleting only the ``.db`` would leave
    committed data on disk. Same glob logic as
    ``checkpointer.clear_all_checkpoints`` (checkpointer.py:80).
    """
    if not cp_dir.is_dir():
        print(f"checkpoints: no directory at {cp_dir}")
        return
    cutoff = time.time() - days * _DAY
    dbs = sorted(cp_dir.glob("*.db"))
    if not dbs:
        print(f"checkpoints: no databases in {cp_dir}")
        return
    for db in dbs:
        if db.is_symlink():
            print(f"  keep {db.name} (symlink, not followed)")
            continue
        mtime = db.stat().st_mtime
        age = (time.time() - mtime) / _DAY
        if mtime > cutoff:
            print(f"  keep {db.name} ({age:.1f} d old, limit {days} d)")
            continue
        group = [db, *(p for p in sorted(cp_dir.glob(f"{db.name}-*")) if not p.is_symlink())]
        names = ", ".join(p.name for p in group)
        if apply_changes:
            for path in group:
                path.unlink(missing_ok=True)
        verb = "deleted" if apply_changes else "would delete"
        print(f"  {verb} {names} ({age:.1f} d old, limit {days} d)")


def _prune_reports(results_dir: str, days: int, apply_changes: bool) -> None:
    """Delete report directories whose name stamp is older than ``days``."""
    reports = Path(results_dir).expanduser().resolve() / "reports"
    if not reports.is_dir():
        print(f"reports: no directory at {reports}")
        return
    cutoff = datetime.now() - timedelta(days=days)
    for entry in sorted(reports.iterdir()):
        if not entry.is_dir():
            continue
        if entry.is_symlink():
            print(f"  keep {entry.name} (symlink, not followed)")
            continue
        match = REPORT_DIR_RE.match(entry.name)
        if not match:
            print(f"  keep {entry.name} (name is not <TICKER>_<YYYYmmdd>_<HHMMSS>)")
            continue
        try:
            stamp = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
            source = "name stamp"
        except ValueError:
            # The name matches the shape but is not a date; fall back to the
            # mtime and say so, so the operator can see which clock decided.
            stamp = datetime.fromtimestamp(entry.stat().st_mtime)
            source = "mtime (the stamp in the name is not a date)"
        if stamp > cutoff:
            print(f"  keep {entry.name} ({source}: {stamp:%Y-%m-%d}, limit {days} d)")
            continue
        if apply_changes:
            shutil.rmtree(entry)
        verb = "deleted" if apply_changes else "would delete"
        print(f"  {verb} {entry.name}/ ({source}: {stamp:%Y-%m-%d}, limit {days} d)")


def prune(
    cache_dir: str,
    results_dir: str,
    checkpoint_days: int,
    report_days: int,
    apply_changes: bool,
) -> int:
    """Prune checkpoints and report directories. Dry run unless ``apply_changes``."""
    mode = "apply" if apply_changes else "dry run"
    print(f"prune ({mode})")
    cp_dir = _checkpoint_dir(cache_dir)
    if cp_dir is None:
        print(
            f"FAIL: {Path(cache_dir).expanduser()}/checkpoints does not resolve inside "
            "the cache directory - refusing to delete anything"
        )
        return EXIT_CONFIG
    _prune_checkpoints(cp_dir, checkpoint_days, apply_changes)
    _prune_reports(results_dir, report_days, apply_changes)
    # Never pruned, by operator decision: the log is the track record and the
    # basis of the alpha evaluation.
    print("decision log: kept (unlimited retention by operator decision)")
    if not apply_changes:
        print("nothing was deleted - pass --apply to carry this out")
    return EXIT_OK


# --- backup -----------------------------------------------------------------


def _backup_included(path: Path) -> bool:
    return path.suffix not in BACKUP_EXCLUDED_SUFFIXES


def backup(out: str | None, state_dir: str | None, memory_log: str) -> int:
    """Pack the track record into ``<out>/tex-state-<stamp>.tar.gz``.

    An explicit allow-list, never a directory sweep: the state directory of a
    real deployment sits next to secrets, and a sweep would pack them.

    ``--state-dir`` is required on purpose. ``DEFAULT_CONFIG`` has no
    ``state_dir`` key — ``daily_paper_run.build_config`` composes
    ``memory_log_path = <state_dir>/decision-log.md`` per run, and in CI the
    state dir is an ephemeral ``$RUNNER_TEMP/paper-state``. There is no default
    that would not be a guess.
    """
    if not out:
        print("backup needs --out <dir>: where the archive is written")
        return EXIT_CONFIG
    if not state_dir:
        print(
            "backup needs --state-dir <dir>: the paper run's state directory "
            "(no config default exists - daily_paper_run.py composes it per run)"
        )
        return EXIT_CONFIG

    state = Path(state_dir).expanduser()
    if not state.is_dir():
        print(f"FAIL: no state directory at {state}")
        return EXIT_CONFIG

    members: list[tuple[Path, str]] = []
    for name in ("decision-log.md", "index.md"):
        path = state / name
        if path.is_file() and _backup_included(path):
            members.append((path, name))
    runs = state / "runs"
    if runs.is_dir():
        for path in sorted(runs.rglob("*")):
            if path.is_file() and _backup_included(path):
                members.append((path, path.relative_to(state).as_posix()))
    cli_log = Path(memory_log).expanduser() if memory_log else None
    if cli_log is not None and cli_log.is_file() and _backup_included(cli_log):
        members.append((cli_log, f"cli/{cli_log.name}"))

    if not members:
        print(f"FAIL: nothing on the allow-list found under {state}")
        return EXIT_CONFIG

    top = f"tex-state-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    out_dir = Path(out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"{top}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for source, arcname in members:
            tar.add(source, arcname=f"{top}/{arcname}")

    print(f"backup: {archive} ({len(members)} member(s) under {top}/)")
    for _, arcname in members:
        print(f"  {arcname}")
    print("checkpoints are not in the backup: they are 7-day resume points, not a record")
    return EXIT_OK


# --- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="state_maintenance.py",
        description="Prune, back up and verify the state a run leaves behind.",
    )
    sub = parser.add_subparsers(dest="command")

    verify_parser = sub.add_parser("verify", help="check the checkpoints and the decision log")
    verify_parser.add_argument("--cache-dir", default=DEFAULT_CONFIG["data_cache_dir"])
    verify_parser.add_argument("--memory-log", default=DEFAULT_CONFIG["memory_log_path"])

    prune_parser = sub.add_parser("prune", help="delete expired checkpoints and reports")
    prune_parser.add_argument("--cache-dir", default=DEFAULT_CONFIG["data_cache_dir"])
    prune_parser.add_argument("--results-dir", default=DEFAULT_CONFIG["results_dir"])
    prune_parser.add_argument("--checkpoint-days", type=int, default=DEFAULT_CHECKPOINT_DAYS)
    prune_parser.add_argument("--report-days", type=int, default=DEFAULT_REPORT_DAYS)
    prune_parser.add_argument(
        "--apply", action="store_true", help="actually delete (default is a dry run)"
    )

    backup_parser = sub.add_parser("backup", help="archive the track record")
    backup_parser.add_argument("--out", default=None, help="directory for the archive (required)")
    backup_parser.add_argument(
        "--state-dir", default=None, help="the paper run's state directory (required)"
    )
    backup_parser.add_argument("--memory-log", default=DEFAULT_CONFIG["memory_log_path"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on a usage error and on --help. Callers (and the tests)
        # want a return code from main(), so translate instead of propagating.
        return EXIT_CONFIG if exc.code else EXIT_OK

    if not args.command:
        parser.print_usage()
        print("state_maintenance.py needs a subcommand: verify, prune or backup")
        return EXIT_CONFIG
    if args.command == "verify":
        return verify(args.cache_dir, args.memory_log)
    if args.command == "prune":
        return prune(
            args.cache_dir,
            args.results_dir,
            args.checkpoint_days,
            args.report_days,
            args.apply,
        )
    if args.command == "backup":
        return backup(args.out, args.state_dir, args.memory_log)
    print(f"unknown subcommand: {args.command}")
    return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
