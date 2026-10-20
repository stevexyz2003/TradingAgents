---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 05
subsystem: reporting
tags: [ibkr, report, slippage, fill-ratio, cli, git-read-only]

requires:
  - phase: 07-04
    provides: Datenschicht (parse_decisions, read_ledger, build_rows)
provides:
  - "scripts/ibkr_report.py: PAPER_FILL_NOTICE, slippage_bp, fill_ratio, total_fill_ratio, CloseFetcher, render_markdown, main"
affects: [07-06, 07-07]

key-files:
  modified: [scripts/ibkr_report.py, tests/test_ibkr_report.py]

key-decisions:
  - "Slippage-Bezug ist der Schlusskurs am trade_date via `settlement.get_closes` (Modulattribut, patchbar); jede Ausnahme wird zur Fußnote (D-14, D-16)"
  - "argparse-Usage-Fehler (sonst Exit 2) werden auf Exit 1 gemappt, damit Exit 2 eindeutig 'Quelle nicht lesbar' bleibt"

requirements-completed: [REQ-IBKR-49, REQ-IBKR-50]

duration: ~25min
completed: 2026-10-20
---

# Phase 7 Plan 05: Metriken, Darstellung und CLI des Soll-Ist-Berichts Summary

**`scripts/ibkr_report.py` liest `fork/paper-log` und `fork/ibkr-log` ohne Checkout und gibt einen Markdown-Bericht mit getrennten Tabellen Execution und Decision, Paper-Fill-Hinweis, Slippage in bp (fail-soft) und Fill-Quote aus.**

## Umgesetzt

- Task 1 (`16fb44c`): `slippage_bp` (positiv = schlechter für BUY und SELL), `fill_ratio` (Timeout/place-rejected = 0), `total_fill_ratio`, `CloseFetcher` mit Cache und Fail-soft, `render_markdown` mit nummerierten Fußnoten, `PAPER_FILL_NOTICE` vor der ersten Tabelle. Lazy-Lader `_contracts()` und `_paperlog()` ergänzt.
- Task 2 (`3a1f942`): `build_parser`/`main` mit `--repo --remote --paper-log-branch --published-branch --since --until --out --no-prices`; Exit 0/1/2; Referenznamen per `validate_ref_name`; nur `GitPaperLog` (fetch in private Ref, cat-file).

## Verifikation (tatsächlich ausgeführt)

- `pytest tests/test_ibkr_report.py`: 53 passed (`-k "metrics or slippage or footnote"`: 12 passed; `-k "real_git or cli"`: 15 passed).
- `pytest tests/test_ibkr_report.py tests/test_ibkr_paperlog.py tests/test_ibkr_isolation.py`: 129 passed.
- `ruff check scripts tests`: sauber; `ruff format` auf beide angefassten Dateien angewandt.
- `grep -c settlement.get_closes` = 1; keine `"push"/"checkout"/"commit"`-Literale im Modul (0).
- Real-Git-Test: nach dem Lauf `status --porcelain` leer, Arbeitsbaum nur `.git`, keine `refs/tengx`, Branch-Tips im Bare-Repo unverändert.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] argparse-Exit 2 kollidierte mit EXIT_SOURCE**
- **Found during:** Task 2 (`--remote -x` wurde von argparse als Flag gelesen, Exit 2)
- **Fix:** `SystemExit` von `parse_args` wird in `main` auf Exit 1 gemappt.
- **Commit:** 3a1f942

### Sonstiges

- TDD: Tests und Code pro Task im selben Commit, kein separater RED-Commit (wie in 07-04).
- Der Test für `--remote "-x"` nutzt die Form `--remote -x`; beide laufen über den Usage-Pfad (Exit 1).

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche; Mitigationen T-07-18 bis T-07-21 sind durch Tests belegt.

## Self-Check: PASSED

- `scripts/ibkr_report.py`, `tests/test_ibkr_report.py` vorhanden; Commits `16fb44c` und `3a1f942` in `git log`.
- STATE.md und ROADMAP.md nicht angefasst.
