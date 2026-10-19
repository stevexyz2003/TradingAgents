---
phase: 06-die-erste-echte-order
plan: 07
subsystem: ibkr-executor
tags: [live, ledger, resolved, never_sent, REQ-IBKR-48, D-14]
requires: [06-06]
provides:
  - "Ledger-Ereignis resolved (Lifecycle, nicht OPEN) mit Schema outcome=never_sent, note"
  - "execute --resolve KEY=never_sent --note TEXT (run_resolve_entry unter dem Ledger-Lock)"
  - "Handbuch: Ablauf zum Schliessen eines Live-intent ohne Broker-Spur"
affects: [06-08]
key-files:
  modified:
    - scripts/ibkr_ledger.py
    - scripts/ibkr_executor.py
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_ledger.py
    - tests/test_ibkr_isolation.py
  created:
    - tests/test_ibkr_never_sent.py
key-decisions:
  - "resolved ist Lifecycle-Ereignis: schliesst den Eintrag, attempt_of liefert weiter den intent, der Key bleibt verbraucht"
  - "Kein run_start/run_end-Rahmen um --resolve: das Akzeptanzkriterium verlangt genau eine neue Zeile; der Lauf steht im Log"
  - "Alle Ablehnungen vor dem Schreiben: Exit 1 (Argumente), 2 (nicht offen / nicht intent), 6 (Spur am Broker), 7 (Lock)"
requirements-completed: [REQ-IBKR-48]
completed: 2026-10-19
---

# Phase 6 Plan 07: Notausgang --resolve never_sent Summary

`execute --resolve "KEY=never_sent" --note TEXT` haengt ein `resolved`-Ereignis an das Live-Ledger und schliesst damit einen `intent` ohne Broker-Spur, ohne eine bestehende Zeile zu aendern; der Key bleibt verbraucht, der Folgelauf endet nicht mehr mit Exit 6.

## Ergebnis

- `scripts/ibkr_ledger.py`: `RESOLVED`, `NEVER_SENT`, `RESOLVE_OUTCOMES`; `RESOLVED` in `EVENTS` und `LIFECYCLE_EVENTS`, nicht in `OPEN_EVENTS`; Schema (decision_key, outcome, nicht leere note) wird in `_schema_problem` und schon beim `append` geprueft.
- `scripts/ibkr_executor.py`: Flags `--resolve`/`--note`; `_resolve_args_problem` (kein TICKER/`--live`, Outcome nur `never_sent`, Note 1-500 druckbare Zeichen, KEY ueber `guards.decision_key` reproduziert); `run_resolve_entry` mit Lock (`wait=False`), frischer Broker-Historie und `resolve_entry`; nur bei `NO_TRACE` wird `resolved` (`source: operator`) geschrieben, Log `ibkr-state=RESOLVED_BY_OPERATOR`.
- Handbuch: Punkt 4 unter „Resolving exit 6“ ersetzt, Ereignisliste und „Commands“ ergaenzt; „comes with phase 6“ ist entfernt.
- Tests: 6 neue Ledger-Tests, 24 in `tests/test_ibkr_never_sent.py` (Positivfall byte-gleiche Praefix-Pruefung + genau eine Zeile mehr, Folgelauf `already-attempted` ohne `placeOrder`, alle Negativfaelle), 1 Handbuch-Test.

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q`: 1246 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests`: All checks passed

## Abweichungen vom Plan

- Kein `run_start`/`run_end` um den `--resolve`-Lauf (Plan-Aktion nennt den Rahmen, das Akzeptanzkriterium verlangt genau eine neue Zeile; letzteres gewaehlt, Log-Zeilen dokumentieren den Lauf).
- `tests/test_ibkr_never_sent.py` traegt `# ruff: noqa: F811`, weil die aus `test_ibkr_execute` importierten Fixtures (`loop`) als Argumente wiederverwendet werden.

## Commits

- 0c4b58a feat(06-07): add resolved ledger event and execute --resolve KEY=never_sent
- 624d139 docs(06-07): document execute --resolve never_sent in the handbook

## Known Stubs

Keine.

## Self-Check: PASSED
