#!/usr/bin/env python3
"""Unattended daily paper run for the TradingEngineX strand.

Operational tooling, not part of the ``tradingagents`` library: analyzes a
short ticker list with a hard per-run cost budget, writes a machine-readable
summary plus the markdown report tree, and keeps the decision log in a
persistent state directory so consecutive days accumulate a real track record
(realized return and alpha are filled in by the pipeline's own reflection pass
on the next run of the same ticker).

Operating manual: ``scripts/PAPER_RUN.md``.

Exit codes:
    0   all tickers analyzed, or --preflight passed
    1   configuration/usage error - nothing was run
    3   at least one ticker failed with a runtime error
    4   the cost budget aborted or skipped at least one ticker
    20  --preflight only: the provider's credentials are not configured
"""

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tradingagents.budget import BudgetConfigError, BudgetExceededError, ensure_rates_configured
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_RUN_FAILED = 3
EXIT_BUDGET = 4
EXIT_NO_CREDENTIALS = 20

#: Bumped when the shape of summary.json changes in a non-additive way.
SUMMARY_SCHEMA_VERSION = 1

#: Azure needs all four; the key alone is not enough to reach a deployment.
AZURE_REQUIRED_ENV = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "OPENAI_API_VERSION",
)

_INDEX_HEADER = (
    "# Paper-run index\n\n"
    "One row per ticker run. Written by `scripts/daily_paper_run.py`.\n\n"
    "| trade date | ticker | signal | status | cost (USD) | tokens in/out | run |\n"
    "|---|---|---|---|---|---|---|\n"
)


class ConfigError(Exception):
    """Invalid input or configuration - nothing is run."""


# --------------------------------------------------------------------------
# pure helpers (unit-tested without network or LLM access)
# --------------------------------------------------------------------------


def parse_tickers(raw: str, *, max_tickers: int = 10) -> list[str]:
    """Split a comma/whitespace separated ticker list into validated symbols.

    Symbols are upper-cased and de-duplicated while preserving order, and each
    one is validated with the same path guard the pipeline uses (#618), so a
    malformed repository variable cannot write outside the output directory.
    """
    tokens = [part for chunk in raw.split(",") for part in chunk.split()]
    tickers: list[str] = []
    for token in tokens:
        symbol = token.strip().upper()
        if not symbol:
            continue
        try:
            safe_ticker_component(symbol)
        except ValueError as exc:
            raise ConfigError(f"Invalid ticker {symbol!r}: {exc}") from exc
        if symbol not in tickers:
            tickers.append(symbol)
    if not tickers:
        raise ConfigError("No tickers given - pass --tickers 'AAPL,MSFT'.")
    if len(tickers) > max_tickers:
        raise ConfigError(
            f"{len(tickers)} tickers requested but the cap is {max_tickers}. "
            "A scheduled paper run is a heartbeat, not a batch job - raise "
            "--max-tickers deliberately if you really mean it."
        )
    return tickers


def previous_weekday(today: datetime) -> str:
    """Most recent weekday strictly before ``today``, as YYYY-MM-DD.

    The scheduled run happens the morning after a session closes, so the
    default trade date is yesterday - stepping back over a weekend. Exchange
    holidays are not modelled: on a holiday the pipeline analyzes the last
    session's data, which is visible in the report but is not an error.
    """
    day = today - timedelta(days=1)
    while day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def resolve_trade_date(value: str | None, *, now: datetime | None = None) -> str:
    """Validate an explicit ``YYYY-MM-DD`` date, or derive the default one."""
    if not value or value == "auto":
        return previous_weekday(now or datetime.now(timezone.utc))
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ConfigError(f"--date must be YYYY-MM-DD or 'auto', got {value!r}") from exc
    return value


def load_rates(path: Path) -> dict[str, dict[str, float]]:
    """Load the operator-maintained ``{model: {input, output}}`` rate table.

    Rates are USD per 1M tokens. The library deliberately ships no built-in
    price table, so an unattended run has to carry its own - and a malformed
    file must fail loudly rather than silently disable the budget.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Rate file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Rate file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Rate file {path} must contain a JSON object.")

    rates: dict[str, dict[str, float]] = {}
    for model, entry in raw.items():
        if model.startswith("_"):
            continue  # "_comment"-style keys are documentation, not models
        if not isinstance(entry, dict) or "input" not in entry or "output" not in entry:
            raise ConfigError(
                f"Rate entry for {model!r} in {path} needs both 'input' and 'output' "
                "(USD per 1M tokens)."
            )
        try:
            rates[model] = {"input": float(entry["input"]), "output": float(entry["output"])}
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Non-numeric rate for {model!r} in {path}: {exc}") from exc
    if not rates:
        raise ConfigError(f"Rate file {path} contains no model entries.")
    return rates


def _key_optional(provider_lower: str) -> bool:
    """Whether the provider authenticates without a key env var."""
    if provider_lower == "bedrock":
        return True  # AWS credential chain, not a single key variable
    try:
        from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
    except ImportError:  # pragma: no cover - SDK missing
        return False
    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider_lower)
    return bool(spec is not None and spec.key_optional)


def missing_credentials(provider: str, environ: dict | None = None) -> list[str]:
    """Names of the env vars this provider needs that are absent or empty."""
    env = os.environ if environ is None else environ
    provider_lower = provider.lower()
    if provider_lower == "azure":
        required: tuple[str, ...] = AZURE_REQUIRED_ENV
    elif _key_optional(provider_lower):
        required = ()
    else:
        key_env = get_api_key_env(provider_lower)
        required = (key_env,) if key_env else ()
    return [name for name in required if not str(env.get(name, "")).strip()]


def build_config(
    *,
    rates: dict[str, dict[str, float]],
    max_cost: float,
    out_dir: Path,
    state_dir: Path,
    base_config: dict | None = None,
) -> dict:
    """Assemble the run config: hard budget, run-local results, shared log."""
    config = dict(base_config if base_config is not None else DEFAULT_CONFIG)
    config["max_cost_per_run"] = max_cost
    config["model_cost_rates"] = rates
    config["results_dir"] = str(out_dir / "logs")
    config["memory_log_path"] = str(state_dir / "decision-log.md")
    # An unattended run must not resume yesterday's half-finished graph: each
    # day is a fresh analysis of a new trade date.
    config["checkpoint_enabled"] = False
    return config


def render_summary_markdown(summary: dict) -> str:
    """Render the run summary as markdown (job summary + artifact)."""
    totals = summary["totals"]
    lines = [
        f"## Paper run {summary['trade_date']} - {summary['status'].upper()}",
        "",
        f"Provider `{summary['provider']}` | deep `{summary['deep_think_llm']}` | "
        f"quick `{summary['quick_think_llm']}`",
        f"Budget: ${summary['max_cost_per_run_usd']:.2f} per ticker, "
        f"${summary['max_total_cost_usd']:.2f} total.",
        "",
        "| ticker | status | signal | cost (USD) | tokens in/out | duration |",
        "|---|---|---|---|---|---|",
    ]
    for run in summary["runs"]:
        lines.append(
            f"| {run['ticker']} | {run['status']} | {run['signal'] or '-'} | "
            f"{run['cost_usd']:.4f} | {run['tokens_in']}/{run['tokens_out']} | "
            f"{run['duration_s']:.0f}s |"
        )
    lines += [
        "",
        f"**Total:** ${totals['cost_usd']:.4f} | "
        f"{totals['tokens_in']}/{totals['tokens_out']} tokens | "
        f"{totals['ok']} ok, {totals['failed']} failed, "
        f"{totals['budget_aborted']} budget-aborted, {totals['skipped']} skipped.",
    ]
    errors = [run for run in summary["runs"] if run.get("error")]
    if errors:
        lines += ["", "### Errors", ""]
        lines += [f"- **{run['ticker']}**: {run['error']}" for run in errors]
    return "\n".join(lines) + "\n"


def append_index_rows(index_path: Path, summary: dict) -> None:
    """Append one row per ticker to the cumulative index on the state branch."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text(_INDEX_HEADER, encoding="utf-8")
    rows = [
        f"| {summary['trade_date']} | {run['ticker']} | {run['signal'] or '-'} | "
        f"{run['status']} | {run['cost_usd']:.4f} | {run['tokens_in']}/{run['tokens_out']} | "
        f"runs/{summary['trade_date']}/summary.json |"
        for run in summary["runs"]
    ]
    with open(index_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")


# --------------------------------------------------------------------------
# run path
# --------------------------------------------------------------------------


def _spend(graph) -> tuple[int, int, float]:
    """Read the per-run counters off the graph's spend tracker."""
    tracker = getattr(graph, "spend_tracker", None)
    if tracker is None:
        return 0, 0, 0.0
    return tracker.tokens_in, tracker.tokens_out, tracker.cost


def run_ticker(graph, ticker: str, trade_date: str, out_dir: Path) -> dict:
    """Analyze one ticker; never raises - the outcome is in the returned record."""
    record = {
        "ticker": ticker,
        "status": "ok",
        "signal": None,
        "cost_usd": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_s": 0.0,
        "report": None,
        "error": None,
    }
    started = time.monotonic()
    try:
        final_state, signal = graph.propagate(ticker, trade_date)
        record["signal"] = signal
        record["report"] = str(graph.save_reports(final_state, ticker, out_dir / "reports" / ticker))
    except BudgetExceededError as exc:
        record["status"] = "budget_aborted"
        record["error"] = str(exc)
    except Exception as exc:  # one bad ticker must not kill the whole day
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        record["duration_s"] = time.monotonic() - started
        record["tokens_in"], record["tokens_out"], record["cost_usd"] = _spend(graph)
    return record


def _archive(state_dir: Path, summary: dict, summary_path: Path) -> None:
    """Copy the day's summary and complete reports onto the state branch."""
    run_dir = state_dir / "runs" / summary["trade_date"]
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(summary_path, run_dir / "summary.json")
    for run in summary["runs"]:
        report = run.get("report")
        if report and Path(report).is_file():
            shutil.copyfile(report, run_dir / f"{run['ticker']}.md")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unattended daily paper run.")
    parser.add_argument(
        "--tickers", required=True, help="Comma/space separated symbols, e.g. 'AAPL,MSFT,NVDA'."
    )
    parser.add_argument(
        "--date", default="auto", help="Trade date YYYY-MM-DD, or 'auto' (previous weekday)."
    )
    parser.add_argument(
        "--max-cost", type=float, required=True, help="Hard USD budget per ticker run."
    )
    parser.add_argument(
        "--max-total-cost",
        type=float,
        default=None,
        help="Hard USD budget for the whole day (default: --max-cost x number of tickers).",
    )
    parser.add_argument(
        "--rates",
        type=Path,
        default=Path(__file__).with_name("paper_run_rates.json"),
        help="JSON rate table {model: {input, output}} in USD per 1M tokens.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Per-run output directory.")
    parser.add_argument(
        "--state", type=Path, required=True, help="Persistent directory (decision log, index)."
    )
    parser.add_argument("--max-tickers", type=int, default=10, help="Safety cap on the list size.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate config and credentials, then exit without any LLM call.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        tickers = parse_tickers(args.tickers, max_tickers=args.max_tickers)
        trade_date = resolve_trade_date(args.date)
        rates = load_rates(args.rates)
        if args.max_cost <= 0:
            raise ConfigError("--max-cost must be greater than 0.")
        max_total = args.max_total_cost
        if max_total is None:
            max_total = args.max_cost * len(tickers)

        out_dir = args.out.resolve()
        state_dir = args.state.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        config = build_config(
            rates=rates, max_cost=args.max_cost, out_dir=out_dir, state_dir=state_dir
        )
        # The same validation the graph performs at construction time, but
        # reached before anything expensive happens (and without credentials).
        ensure_rates_configured(rates, [config["deep_think_llm"], config["quick_think_llm"]])
    except (ConfigError, BudgetConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    provider = config["llm_provider"]
    absent = missing_credentials(provider)
    print(
        f"paper-run: {len(tickers)} ticker(s) {', '.join(tickers)} on {trade_date} | "
        f"provider={provider} deep={config['deep_think_llm']} quick={config['quick_think_llm']} | "
        f"budget ${args.max_cost:.2f}/ticker, ${max_total:.2f} total"
    )
    if args.preflight:
        if absent:
            print(
                f"preflight: credentials missing for provider '{provider}': {', '.join(absent)}",
                file=sys.stderr,
            )
            return EXIT_NO_CREDENTIALS
        print("preflight: OK - config valid, credentials present, no LLM call made.")
        return EXIT_OK
    if absent:
        print(
            f"error: missing credentials for provider '{provider}': {', '.join(absent)}",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    started_at = datetime.now(timezone.utc)
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "trade_date": trade_date,
        "provider": provider,
        "deep_think_llm": config["deep_think_llm"],
        "quick_think_llm": config["quick_think_llm"],
        "max_cost_per_run_usd": args.max_cost,
        "max_total_cost_usd": max_total,
        "commit": os.environ.get("GITHUB_SHA"),
        "status": "ok",
        "totals": {},
        "runs": [],
    }

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(config=config)
    except Exception as exc:  # surfaced as a config failure, nothing ran
        print(f"error: could not build the graph: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return EXIT_CONFIG

    spent = 0.0
    for ticker in tickers:
        if spent >= max_total:
            summary["runs"].append({
                "ticker": ticker,
                "status": "skipped",
                "signal": None,
                "cost_usd": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "duration_s": 0.0,
                "report": None,
                "error": f"day budget ${max_total:.2f} already spent (${spent:.4f})",
            })
            continue
        print(f"--- {ticker} {trade_date} ---", flush=True)
        record = run_ticker(graph, ticker, trade_date, out_dir)
        spent += record["cost_usd"]
        summary["runs"].append(record)
        print(
            f"--- {ticker}: {record['status']} signal={record['signal']} "
            f"cost=${record['cost_usd']:.4f} ---",
            flush=True,
        )

    counts = {"ok": 0, "failed": 0, "budget_aborted": 0, "skipped": 0}
    for run in summary["runs"]:
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    summary["totals"] = {
        "tickers": len(summary["runs"]),
        "cost_usd": round(sum(r["cost_usd"] for r in summary["runs"]), 6),
        "tokens_in": sum(r["tokens_in"] for r in summary["runs"]),
        "tokens_out": sum(r["tokens_out"] for r in summary["runs"]),
        **counts,
    }
    if counts["failed"]:
        summary["status"] = "failed"
    elif counts["budget_aborted"] or counts["skipped"]:
        summary["status"] = "partial"
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    markdown = render_summary_markdown(summary)
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8")
    append_index_rows(state_dir / "index.md", summary)
    _archive(state_dir, summary, summary_path)
    print(markdown)

    if counts["failed"]:
        return EXIT_RUN_FAILED
    if counts["budget_aborted"] or counts["skipped"]:
        return EXIT_BUDGET
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
