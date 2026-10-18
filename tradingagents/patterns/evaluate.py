"""Evaluate price patterns against the settled decision log (fork-only).

For every log entry the patterns are computed from prices up to and including the
decision date. Per pattern and side the report states how often the sign of the
outcome matched, with honest small-N statistics: independent cases, ties,
Wilson 95 % intervals and an explicit ``insufficient`` status below ``MIN_N``.

Two modes per cell:

* ``engine``: directional ratings (Buy/Overweight/Underweight/Sell) where the
  pattern is active on that side; a hit is ``sign(metric) == rating direction``.
* ``pattern``: every settled entry (Hold included) where the pattern is active
  on that side; a hit is ``sign(metric) == pattern side``.

Both metrics are reported side by side and evaluated independently: alpha (return
minus benchmark) and the raw return. An unreadable value in one metric never
discards the other. Exact zeros (after the log's 0.1 pp rounding) are ties: they
leave the denominator and are counted per metric. The MIN_N gate applies per
metric to its own denominator (``den_alpha`` / ``den_raw``).

Reference groups: ``n_all``, ``ties_*`` and ``mean_alpha`` cover all cases of a cell;
hit rates, intervals and ``den_*`` cover only the independent cases. ``mean_alpha``
is the plain mean alpha, not multiplied by the rating direction (a bearish cell
with negative mean alpha is the "right" direction).

Independence and the entry convention use real trading sessions (taken from the
loaded price index) where available; otherwise they fall back to weekdays and are
marked approximate.

No LLM, no settlement, no reflector: the module only reads the log and prices.
"""

import math
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.memory.log import TradingMemoryLog
from tradingagents.patterns.signals import PATTERNS, compute_patterns

#: Minimum independent cases per cell before a hit rate is reported (assumption:
#: at n=20 and p=0.6 the Wilson interval is still roughly 0.39-0.78).
MIN_N = 20
Z95 = 1.959963984540054  # two-sided 95 %

_DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
_HOLDING_RE = re.compile(r"^\s*(\d+)\s*d\s*$")

ALPHA_BETA_WARNING = (
    "Alpha is a plain difference to the benchmark (no beta adjustment); "
    "high-beta tickers carry market moves in their alpha."
)
SELECTION_WARNING = (
    "The ticker pool is small and fixed; results do not generalize beyond it "
    "(selection effects cannot be ruled out)."
)


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a proportion; ``None`` when ``n == 0``."""
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class PatternCell:
    pattern: str
    side: int
    mode: str  # "engine" | "pattern"
    n_all: int = 0
    n_independent: int = 0
    ties_alpha: int = 0
    ties_raw: int = 0
    den_alpha: int = 0  # independent, non-tie, alpha readable
    den_raw: int = 0  # independent, non-tie, raw readable
    hits_alpha: int = 0
    hits_raw: int = 0
    hit_rate_alpha: float | None = None
    hit_rate_raw: float | None = None
    ci_alpha: tuple[float, float] | None = None
    ci_raw: tuple[float, float] | None = None
    mean_alpha: float | None = None  # plain (undirected) mean over all cases with alpha
    status_alpha: str = "insufficient"  # "ok" once den_alpha >= min_n
    status_raw: str = "insufficient"  # "ok" once den_raw >= min_n
    approximate: bool = False  # independence fell back to weekdays for some case


@dataclass
class PatternReport:
    cells: list[PatternCell] = field(default_factory=list)
    n_entries: int = 0
    n_resolved: int = 0
    n_pending: int = 0
    n_review_excluded: int = 0
    n_unparseable: int = 0
    min_n: int = MIN_N
    holdings: dict[str, int] = field(default_factory=dict)
    conventions: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    flagged_entries: list[str] = field(default_factory=list)
    n_convention_approximate: int = 0
    missing_price_tickers: list[str] = field(default_factory=list)
    entry_states: list[dict] = field(default_factory=list)


def load_log_entries(path: str | Path) -> list[dict]:
    """Parse a memory log with the same parser the engine uses."""
    return TradingMemoryLog({"memory_log_path": str(path)}).load_entries()


def parse_pct(value: str | None) -> float | None:
    """Parse the log's ``+2.0%`` strings into a fraction; ``None`` if unreadable."""
    if not value:
        return None
    text = value.strip()
    if not text.endswith("%"):
        return None
    try:
        return float(text[:-1]) / 100.0
    except ValueError:
        return None


def parse_holding(value: str | None) -> int | None:
    match = _HOLDING_RE.match(value or "")
    return int(match.group(1)) if match else None


def _session_gap(
    sessions: np.ndarray | None, start: str, end: str
) -> tuple[int, bool]:
    """Sessions between two dates; weekdays (approximate) without covering session data."""
    if sessions is not None and len(sessions) and np.datetime64(end) <= sessions[-1]:
        lo = np.searchsorted(sessions, np.datetime64(start), side="right")
        hi = np.searchsorted(sessions, np.datetime64(end), side="right")
        return int(hi - lo), False
    return int(np.busday_count(start, end)), True


def entry_convention(
    entry_date: str,
    resolved: str | None,
    holding: int | None,
    sessions: np.ndarray | None = None,
) -> str:
    """Infer the entry convention from the session gap (weekdays if no sessions given).

    ``decision_close`` (legacy, before fix #1518): the window starts at the
    decision day's close, so exit is ``holding`` sessions later.
    ``next_close``: entry is the first close after the decision, one more session.
    Without session data a holiday can shift the weekday-based inference.
    """
    if not resolved or holding is None:
        return "unknown"
    try:
        gap, _ = _session_gap(sessions, entry_date, resolved)
    except ValueError:
        return "unknown"
    if gap == holding:
        return "decision_close"
    if gap == holding + 1:
        return "next_close"
    return "unknown"


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _independent(cases: list[dict]) -> tuple[list[dict], bool]:
    """Greedy per-ticker selection of non-overlapping windows; flags weekday fallback."""
    kept: list[dict] = []
    last: dict[str, dict] = {}
    approximate = False
    for case in sorted(cases, key=lambda c: (c["ticker"], c["date"])):
        prev = last.get(case["ticker"])
        gap = 0
        if prev is not None:
            gap, approx = _session_gap(prev.get("sessions"), prev["date"], case["date"])
            approximate = approximate or approx
        if prev is None or gap >= prev["holding"]:
            kept.append(case)
            last[case["ticker"]] = case
    return kept, approximate


def _build_cell(pattern: str, side: int, mode: str, cases: list[dict], min_n: int) -> PatternCell:
    cell = PatternCell(pattern=pattern, side=side, mode=mode)
    cell.n_all = len(cases)
    alphas = [c["alpha"] for c in cases if c["alpha"] is not None]
    cell.mean_alpha = sum(alphas) / len(alphas) if alphas else None
    indep, cell.approximate = _independent(cases)
    cell.n_independent = len(indep)
    cell.ties_alpha = sum(1 for c in cases if c["alpha"] == 0.0)
    cell.ties_raw = sum(1 for c in cases if c["raw"] == 0.0)
    target = side if mode == "pattern" else None
    for c in indep:
        want = c["direction"] if target is None else target
        if c["alpha"] is not None and c["alpha"] != 0.0:
            cell.den_alpha += 1
            cell.hits_alpha += int(_sign(c["alpha"]) == want)
        if c["raw"] is not None and c["raw"] != 0.0:
            cell.den_raw += 1
            cell.hits_raw += int(_sign(c["raw"]) == want)
    if cell.den_alpha >= max(min_n, 1):
        cell.status_alpha = "ok"
        cell.hit_rate_alpha = cell.hits_alpha / cell.den_alpha
        cell.ci_alpha = wilson(cell.hits_alpha, cell.den_alpha)
    if cell.den_raw >= max(min_n, 1):
        cell.status_raw = "ok"
        cell.hit_rate_raw = cell.hits_raw / cell.den_raw
        cell.ci_raw = wilson(cell.hits_raw, cell.den_raw)
    return cell


def evaluate(
    entries: list[dict],
    price_loader: Callable[[str, str], pd.DataFrame],
    min_n: int | None = None,
) -> PatternReport:
    """Join log entries with their patterns and score them per pattern and side."""
    min_n = MIN_N if min_n is None else min_n
    report = PatternReport(min_n=min_n, n_entries=len(entries))
    missing: set[str] = set()
    bad_tickers: set[str] = set()
    frames: dict[str, pd.DataFrame | None] = {}
    sessions_by_ticker: dict[str, np.ndarray | None] = {}
    cases: list[dict] = []
    holdings: Counter = Counter()
    conventions: Counter = Counter()

    def frame_for(ticker: str) -> pd.DataFrame | None:
        if ticker in frames:
            return frames[ticker]
        frame = None
        try:
            safe_ticker_component(ticker)
        except ValueError:
            bad_tickers.add(ticker)
        else:
            try:
                frame = price_loader(ticker, _date.today().isoformat())
            except Exception as exc:  # network/vendor errors must be loud, not silent zeros
                report.warnings.append(f"no price data for {ticker}: {exc}")
            if frame is None or len(frame) == 0:
                missing.add(ticker)
                frame = None
        frames[ticker] = frame
        sessions_by_ticker[ticker] = _sessions(frame)
        return frame

    for entry in entries:
        rating = entry.get("rating", "")
        direction = _DIRECTION.get(rating)
        if entry.get("pending"):
            report.n_pending += 1
        else:
            report.n_resolved += 1
        ticker, day = entry.get("ticker", ""), entry.get("date", "")

        patterns: dict[str, int | None] = dict.fromkeys(PATTERNS)
        if direction is not None:
            frame = frame_for(ticker)
            if frame is not None:
                patterns = compute_patterns(frame, day)

        holding = parse_holding(entry.get("holding"))
        convention = None
        if not entry.get("pending"):
            sessions = sessions_by_ticker.get(ticker)
            convention = entry_convention(day, entry.get("resolved"), holding, sessions)
            resolved_day = entry.get("resolved")
            if resolved_day and holding is not None:
                try:
                    if _session_gap(sessions, day, resolved_day)[1]:
                        report.n_convention_approximate += 1
                except ValueError:
                    pass
        report.entry_states.append(
            {
                "date": day,
                "ticker": ticker,
                "rating": rating,
                "pending": bool(entry.get("pending")),
                "convention": convention,
                "patterns": patterns,
            }
        )
        if entry.get("pending"):
            continue
        if direction is None:
            report.n_review_excluded += 1
            continue
        alpha = parse_pct(entry.get("alpha"))
        raw = parse_pct(entry.get("raw"))
        if (alpha is None and raw is None) or holding is None:
            report.n_unparseable += 1
            continue
        holdings[f"{holding}d"] += 1
        conventions[convention] += 1
        if convention == "decision_close":
            report.flagged_entries.append(f"{day} {ticker} ({rating}): legacy entry convention")
        cases.append(
            {
                "ticker": ticker,
                "date": day,
                "direction": direction,
                "holding": holding,
                "sessions": sessions_by_ticker.get(ticker),
                "alpha": alpha,
                "raw": raw,
                "patterns": patterns,
            }
        )

    for pattern in PATTERNS:
        for side in (1, -1):
            active = [c for c in cases if c["patterns"].get(pattern) == side]
            engine = [c for c in active if c["direction"] != 0]
            report.cells.append(_build_cell(pattern, side, "engine", engine, min_n))
            report.cells.append(_build_cell(pattern, side, "pattern", active, min_n))

    report.holdings = dict(holdings)
    report.conventions = dict(conventions)
    report.missing_price_tickers = sorted(missing)
    for ticker in sorted(missing):
        report.warnings.append(f"no price data for {ticker}: patterns are None, not zero")
    for ticker in sorted(bad_tickers):
        report.warnings.append(f"skipped unsafe ticker {ticker!r}")
    if len(holdings) > 1:
        report.warnings.append(f"mixed holding windows: {dict(holdings)}")
    if len([k for k in conventions if k != "unknown"]) > 1:
        report.warnings.append(f"mixed entry conventions: {dict(conventions)}")
    if report.n_convention_approximate:
        report.warnings.append(
            f"{report.n_convention_approximate} entry convention(s) inferred from weekdays "
            "(no covering session data); a holiday can shift them"
        )
    if any(c.approximate for c in report.cells):
        report.warnings.append("some independence checks fell back to weekdays (approximate)")
    report.warnings.extend([ALPHA_BETA_WARNING, SELECTION_WARNING])
    return report


def _sessions(frame: pd.DataFrame | None) -> np.ndarray | None:
    """Sorted unique trading sessions (datetime64[D]) of a loaded price frame."""
    if frame is None or len(frame) == 0:
        return None
    dates = pd.to_datetime(frame["Date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    return np.unique(dates.dt.normalize().to_numpy().astype("datetime64[D]"))


def default_price_loader() -> Callable[[str, str], pd.DataFrame]:
    """Loader that fetches one Yahoo frame per ticker (cached, gaps left unfilled)."""
    from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv

    cache: dict[str, pd.DataFrame] = {}

    def loader(ticker: str, as_of: str) -> pd.DataFrame:
        if ticker not in cache:
            cache[ticker] = load_ohlcv(ticker, as_of, fill_gaps=False)
        return cache[ticker]

    return loader


def log_text_to_entries(text: str) -> list[dict]:
    """Parse log text (e.g. a ``git show`` blob) without touching the real log path."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "decision-log.md"
        path.write_text(text, encoding="utf-8")
        return load_log_entries(path)


def report_to_dict(report: PatternReport) -> dict:
    return asdict(report)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def _fmt_ci(ci: tuple[float, float] | None) -> str:
    return "-" if ci is None else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def render_markdown(report: PatternReport) -> str:
    lines = [
        "# Pattern evaluation",
        "",
        f"Entries {report.n_entries} - settled {report.n_resolved} - pending {report.n_pending} "
        f"- REVIEW excluded {report.n_review_excluded} - unparseable {report.n_unparseable}",
        f"Holdings {report.holdings} - conventions {report.conventions} - MIN_N {report.min_n}",
        "",
        "## Cells (pattern, side, mode)",
        "",
        "Reference groups: n_all, ties and mean alpha cover all cases of the cell; "
        "hit rates, CIs and den_* cover only the independent cases (non-overlapping "
        "windows per ticker, ties excluded). mean alpha is undirected (not multiplied by "
        "the rating direction). `~` marks a weekday fallback for independence.",
        "",
        "| pattern | side | mode | n_all | n_indep | ties a/r | den a/r | hit alpha | CI alpha "
        "| status a | hit raw | CI raw | status r | mean alpha |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in report.cells:
        approx = "~" if c.approximate else ""
        lines.append(
            f"| {c.pattern} | {c.side:+d} | {c.mode} | {c.n_all} | {c.n_independent}{approx} "
            f"| {c.ties_alpha}/{c.ties_raw} | {c.den_alpha}/{c.den_raw} "
            f"| {_fmt(c.hit_rate_alpha)} | {_fmt_ci(c.ci_alpha)} | {c.status_alpha} "
            f"| {_fmt(c.hit_rate_raw)} | {_fmt_ci(c.ci_raw)} | {c.status_raw} "
            f"| {_fmt(c.mean_alpha)} |"
        )
    lines += ["", "## Entry pattern states", "", "| date | ticker | rating | state | convention | "
              + " | ".join(PATTERNS) + " |", "|" + "---|" * (5 + len(PATTERNS))]
    for s in report.entry_states:
        state = "pending" if s["pending"] else "settled"
        vals = " | ".join("-" if s["patterns"][p] is None else f"{s['patterns'][p]:+d}"
                          for p in PATTERNS)
        lines.append(
            f"| {s['date']} | {s['ticker']} | {s['rating']} | {state} "
            f"| {s['convention'] or '-'} | {vals} |"
        )
    if report.flagged_entries:
        lines += ["", "## Flagged entries", ""] + [f"- {f}" for f in report.flagged_entries]
    lines += ["", "## Warnings", ""] + [f"- {w}" for w in report.warnings]
    return "\n".join(lines) + "\n"
