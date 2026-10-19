---
phase: 06-die-erste-echte-order
plan: 02
subsystem: ibkr-decision
tags: [jev, rating_source, fail-closed, REQ-45]
requires: [06-01]
provides:
  - RunRecord.rating_source, State rating-jev (Exit 2), DecisionVerdict.rating_source
affects: [06-04]
key-files:
  modified:
    - scripts/ibkr_decision.py
    - tests/test_ibkr_decision.py
    - scripts/IBKR_EXECUTION.md
key-decisions:
  - "Fehlendes Feld rating_source = engine (RESEARCH A1); jev und unbekannte Werte -> rating-jev (fail-closed)"
  - "Jev-Zweig steht nach der Hold-Pruefung, vor executable; RUN_FIELDS unveraendert"
requirements-completed: [REQ-IBKR-45]
completed: 2026-10-19
---

# Phase 6 Plan 02: Jev-Fallback-Ratings nicht handeln Summary

`evaluate_decision` liest das optionale Feld `rating_source` aus `summary.json` und beendet Jev- oder unbekannte Quellen fail-closed als `rating-jev` (Exit 2, Ledger-Grund `review`); preview und execute teilen dieselbe Regel.

## Ergebnis

- `scripts/ibkr_decision.py`: `RATING_JEV`, `RATING_SOURCES`, optionales Feld mit Typpruefung (Nicht-String -> `SummaryContractError`), `DecisionVerdict.rating_source` (fehlend = `engine`).
- 11 neue Tests `test_jev_*`/`test_rating_source_*` (inkl. D-06: summary-missing, kaputte Summary).
- `scripts/IBKR_EXECUTION.md`: Zeile `rating-jev` und Absatz zu fehlendem Feld/summary.json.
- `log.py` und `daily_paper_run.py` unveraendert (D-05).

## Verifikation

- `pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py`: 1135 passed
- `ruff check scripts tests`: All checks passed

## Deviations from Plan

None - plan executed exactly as written. Der Kreuztest in test_ibkr_ledger ist gruen, da 06-01 bereits gelandet ist.

## Commits

- c244db0 feat(06-02): exclude Jev fallback ratings via summary rating_source
- 1271da5 docs(06-02): add rating-jev to the phase 4 state table

## Self-Check: PASSED
