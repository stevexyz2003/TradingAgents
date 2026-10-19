---
phase: 06-die-erste-echte-order
plan: 04
subsystem: ibkr-guards-executor
tags: [exit-codes, states, freshness, rating_source, WR-05, REQ-45, REQ-65]
requires: [06-01, 06-02, 06-03]
provides:
  - guards.NOT_LIVE, ORDER_FILLED, PLACE_REJECTED, FILL_TIMEOUT, POST_ORDER_MISMATCH, PLACER_STATES
  - executor.EXIT_FILL_TIMEOUT = 9, EXIT_POST_ORDER = 10
  - Frische-Neuprüfung vor dem intent, rating_source im intent
affects: [06-05, 06-06, 06-07, 06-08]
key-files:
  modified:
    - scripts/ibkr_guards.py
    - scripts/ibkr_executor.py
    - scripts/ibkr_decision.py
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_guards.py
    - tests/test_ibkr_isolation.py
    - tests/test_ibkr_execute.py
    - tests/test_ibkr_executor.py
key-decisions:
  - "Rang aufsteigend 0<2<5<1<3<8<9<10<6<7<4: Alarm nach der Order wiegt mehr als jeder Ticker-Abbruch, 6/7/4 mehr als der Alarm"
  - "PLACER_STATES (order-filled, place-rejected) schreiben keine Fallback-Zeile in _ledger_row_finished"
  - "Konstante decision.FRESH eingeführt (es gab keine), vom Executor in beiden Frische-Prüfungen genutzt"
requirements-completed: [REQ-IBKR-45, REQ-IBKR-65]
completed: 2026-10-19
---

# Phase 6 Plan 04: Zustandstabelle, Frische-Neuprüfung und rating_source Summary

Fünf neue Zustände und die Exits 9/10 stehen konsistent in Guards, Executor, Handbuch und Tests; die Frische wird direkt vor dem `intent` mit `ctx.clock()` neu geprüft, und jeder `intent` trägt `rating_source`.

## Ergebnis

- `ibkr_guards.py`: neue States, Exit-Spiegel 9/10, `EXIT_BY_STATE`-Einträge (not-live 1, order-filled 0, place-rejected 5, fill-timeout 9, post-order-mismatch 10), `PLACER_STATES`, neuer Rang.
- `ibkr_executor.py`: `EXIT_FILL_TIMEOUT`, `EXIT_POST_ORDER`, Docstring, `_ledger_row_finished` überspringt Placer-States; `_ROW_KEYS` um `rating_source`; `_execute_ticker` prüft `freshness` nach der Fenster-Neuprüfung und vor `intent_record`; `intent_record(rating_source=...)`.
- `IBKR_EXECUTION.md`: Exit-Tabelle (12 Zeilen), Rangsatz, fünf Zeilen in der State-Tabelle (Überschrift unverändert).
- Tests: `live_states`/`rank` in Guards, Spiegeltest 9/10, Handbuch 12 Codes, `freshness_recheck`, `jev`, `rating_source`-Pin auf `"engine"`.

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` -> 1188 passed
- `-k "freshness_recheck or jev or rating_source"` (execute) -> 3 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests` -> All checks passed

## Deviations from Plan

**1. [Rule 3 - Blocking] Weitere Tests angepasst:** `tests/test_ibkr_executor.py` (`EXIT_NAMES` und feste Werteliste um 9/10 erweitert), sonst rot.

**2. [Rule 3] `decision.FRESH` neu:** Der Plan verlangte eine bestehende Konstante für „fresh“; es gab nur das Literal. Konstante in `ibkr_decision.py` ergänzt.

**3. Test der Neuprüfung:** Statt springender Uhr liefert ein Kalender-Stub nach einem Hook (wie beim WR-05-Fenstertest) eine geschlossene Sitzung; das Fenster bleibt dabei offen, so dass genau die Frische-Neuprüfung greift.

## Commits

- d866a24 feat(06-04): add live states, exits 9/10 and rank consistently
- 603ec04 feat(06-04): recheck freshness before the intent and record rating_source

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche; T-06-17 bis T-06-20 mitigiert und getestet.

## Self-Check: PASSED

Commits d866a24 und 603ec04 vorhanden; geänderte Dateien existieren.
