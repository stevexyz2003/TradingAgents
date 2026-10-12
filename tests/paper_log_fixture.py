"""Test source for the paper-log reader contract (not a test module).

``FixturePaperLog`` satisfies the same read contract as ``GitPaperLog``
(``fetch``, ``read``, ``list_run_dates``) but reads a plain directory.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ibkr_paperlog.py"
if "ibkr_paperlog" in sys.modules:
    _pl = sys.modules["ibkr_paperlog"]
else:
    _spec = importlib.util.spec_from_file_location("ibkr_paperlog", _SCRIPT)
    _pl = importlib.util.module_from_spec(_spec)
    sys.modules["ibkr_paperlog"] = _pl
    _spec.loader.exec_module(_pl)

PaperLogUnavailable = _pl.PaperLogUnavailable
BlobMissing = _pl.BlobMissing

FROZEN_SHA = "71df89df8a078acdcea92f966c10332086f6cf43"
FROZEN_DIR = Path(__file__).parent / "fixtures" / "paper_log_71df89d"
FROZEN_BLOB_IDS = {
    "decision-log.md": "12a2c0bf8326e880b758a5e98d242aef3c643a05",
    "runs/2026-10-09/summary.json": "5ff4e4ba2db3cd532b178933faa904397a7275ba",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FixturePaperLog:
    def __init__(self, root: Path, sha: str, *, unavailable_reason: str | None = None):
        self._root = Path(root)
        self.sha: str | None = None
        self._sha = sha
        self._unavailable = unavailable_reason
        self.fetch_calls = 0
        self.read_calls = 0

    @classmethod
    def unavailable(cls, reason: str) -> FixturePaperLog:
        return cls(Path("."), FROZEN_SHA, unavailable_reason=reason)

    def fetch(self) -> str:
        self.fetch_calls += 1
        if self._unavailable is not None:
            raise PaperLogUnavailable(self._unavailable)
        self.sha = self._sha
        return self._sha

    def read(self, path: str) -> bytes:
        _pl.validate_blob_path(path)
        if self.sha is None:
            raise RuntimeError("fetch() must run before reading")
        self.read_calls += 1
        target = self._root / path
        if not target.is_file():
            raise BlobMissing(path)
        return target.read_bytes()

    def list_run_dates(self) -> tuple[str, ...]:
        if self.sha is None:
            raise RuntimeError("fetch() must run before reading")
        runs = self._root / "runs"
        if not runs.is_dir():
            return ()
        return tuple(
            sorted(p.name for p in runs.iterdir() if p.is_dir() and _DATE_RE.match(p.name))
        )


def write_paper_log(root: Path, entries, summaries) -> Path:
    """Build a paper-log directory; the log is written by the real producer."""
    from tradingagents.memory.log import TradingMemoryLog

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    log = TradingMemoryLog({"memory_log_path": str(root / "decision-log.md")})
    for trade_date, ticker, rating in entries:
        log.store_decision(ticker, trade_date, "fixture decision", rating=rating)
    for trade_date, summary in summaries.items():
        target = root / "runs" / trade_date / "summary.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps(summary, indent=2).encode("utf-8"))
    return root
