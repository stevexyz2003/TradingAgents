---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 07
subsystem: ci
tags: [portfolio-feed, workflow, fail-open]
requires: [07-03]
provides:
  - load_published_portfolio und --portfolio-from-published (scripts/daily_paper_run.py)
  - summary.json portfolio_feed
affects: []
key-files:
  modified:
    - scripts/daily_paper_run.py
    - tests/test_daily_paper_run.py
    - .github/workflows/daily-paper-run.yml
    - scripts/PAPER_RUN.md
requirements: [REQ-IBKR-52]
completed: 2026-10-20
---

# Phase 7 Plan 07: Portfolio-Rückkanal in die CI-Analyse Summary

Fail-open Lesepfad für das veröffentlichte `portfolio.json` hinter dem Flag `--portfolio-from-published`, Workflow-Eingriff minimal und per Text-Pins gesichert.

## Ergebnis

- BASE (Schritt 0): `ff9a6a25125e03d1d032d314c1c03f3a5115fd20` (Worktree war auf e8f5503 und wurde per Vorgabe darauf zurückgesetzt).
- Task 1 (Commit 9880cc1): Konstanten `PUBLISHED_STATE_REMOTE/BRANCH/PATH`, `load_published_portfolio` (lädt `ibkr_paperlog`/`ibkr_decision` per `spec_from_file_location`, `GitPaperLog(fetch_depth=1)`, Gültigkeit über `second_last_close_utc`), Reasons: branch-unavailable, file-missing, too-large, invalid-json, invalid-schema, as-of-missing, as-of-invalid, as-of-in-future, stale, calendar-unavailable, unexpected-error. Abruf in `main` nach Preflight-Return und Credential-Check; `--portfolio` zusammen mit dem Flag ergibt Exit 1. `portfolio_feed` nur mit Flag im Summary, ohne Beträge; `SUMMARY_SCHEMA_VERSION` bleibt 1.
- Task 2 (Commit f564ab0): Workflow bekommt Schritt „Install the session calendar“ und eine Flag-Zeile im Schritt „Run the analysis“ (nur hinzugefügte Zeilen, `git diff $BASE` zeigt 0 entfernte Zeilen). Klasse `TestWorkflowFeed` pinnt Pip-Spanne gegen `pyproject.toml`, Flag nur im Analyse-Schritt, Restore- und Commit-Schritt als Literal-Kopie, Push/Fetch-Zeilen, kein „IBKR“. `PAPER_RUN.md`: Abschnitt „Published portfolio (CI)“ inkl. Reason-Liste und akzeptierter Folgen (Jev entfällt, Reports öffentlich, D-18).

## Verifikation (ausgeführt)

- `pytest tests/test_daily_paper_run.py`: 78 passed (davon `-k "feed or published"`: 22 passed; `-k workflow`: 7 passed)
- `pytest tests/test_daily_paper_run.py tests/test_paper_summary_contract.py tests/test_ibkr_isolation.py`: 126 passed
- `pytest tests/test_paper_summary_contract.py tests/test_ibkr_decision.py`: 123 passed
- `ruff check scripts tests`: sauber. `ruff format --check` meldet die beiden geänderten Dateien wegen bereits vorhandener Format-Abweichungen (nicht von diesem Plan; nicht angefasst).
- Bestehende Tests nicht editiert (nur Anhänge am Dateiende).
- `grep -c -- "--portfolio-from-published"` im YAML = 1; `grep -ci ibkr` im YAML = 0.

## Abweichungen

Keine funktionalen. Hinweis: Preflight-Test akzeptiert jeden Exit-Code (prüft nur, dass der Leser nicht aufgerufen wird).

## Self-Check: PASSED

Commits 9880cc1 und f564ab0 vorhanden; STATE.md/ROADMAP.md unverändert.
