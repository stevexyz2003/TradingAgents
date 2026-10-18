#!/usr/bin/env python3
"""Evaluate price patterns against the decision log (fork-only, no LLM).

Operational tooling: reads a memory log, computes six look-ahead-free patterns
per entry from Yahoo prices and reports per pattern how often the engine's
rating (or the pattern alone) matched the settled outcome, with small-N
statistics. Needs network only for prices.

    pattern_eval.py --log PATH [--format md|json] [--out FILE]
    pattern_eval.py --git-ref fork/paper-log [--format md|json] [--out FILE]

``--git-ref`` reads ``decision-log.md`` from that ref via ``git show`` without a
checkout. The script does not fetch: run ``git fetch fork paper-log`` first.
Yahoo needs the CA-bundle variables from the local ``.env`` behind TLS
interception (see ``scripts/PAPER_RUN.md``); ``.env`` is loaded at startup.

Exit codes:
    0   ok
    1   usage/configuration error (bad ref, git show failed, unreadable log)
    3   price data missing for at least one ticker
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from tradingagents.patterns.evaluate import (
    default_price_loader,
    evaluate,
    load_log_entries,
    render_markdown,
    report_to_dict,
)

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_NO_PRICES = 3

#: Conservative allowlist for a git ref: no leading '-', no shell/option characters.
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9/._-]*$")


def _price_loader():
    """Module-level seam so tests can inject a stub loader."""
    return default_price_loader()


def _entries_from_ref(ref: str) -> list[dict] | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:decision-log.md"], capture_output=True, check=False
    )
    if result.returncode != 0:
        print(
            f"git show {ref}:decision-log.md failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}",
            file=sys.stderr,
        )
        return None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "decision-log.md"
        path.write_bytes(result.stdout)
        return load_log_entries(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--log", help="path to a decision-log.md")
    source.add_argument("--git-ref", help="git ref holding decision-log.md, e.g. fork/paper-log")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--out", help="write to FILE instead of stdout")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_CONFIG if exc.code else EXIT_OK

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if args.git_ref is not None:
        if not _REF_RE.match(args.git_ref):
            print(f"rejected git ref {args.git_ref!r}", file=sys.stderr)
            return EXIT_CONFIG
        entries = _entries_from_ref(args.git_ref)
    else:
        path = Path(args.log)
        if not path.is_file():
            print(f"log not found: {path}", file=sys.stderr)
            return EXIT_CONFIG
        try:
            entries = load_log_entries(path)
        except OSError as exc:
            print(f"cannot read log: {exc}", file=sys.stderr)
            return EXIT_CONFIG
    if entries is None:
        return EXIT_CONFIG

    report = evaluate(entries, _price_loader())
    if args.format == "json":
        text = json.dumps(report_to_dict(report), indent=2, default=str)
    else:
        text = render_markdown(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if report.missing_price_tickers:
        print(
            "WARNING: no price data for " + ", ".join(report.missing_price_tickers)
            + " - patterns are missing, results are NOT meaningful",
            file=sys.stderr,
        )
        return EXIT_NO_PRICES
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
