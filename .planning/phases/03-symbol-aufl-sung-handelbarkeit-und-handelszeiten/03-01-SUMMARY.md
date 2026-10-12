---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 01
subsystem: ibkr-contracts
tags: [ibkr, contract-table, allow-list, liquid-hours, pure-functions]
requires: []
provides:
  - "scripts/ibkr_contracts.py: Tabelle, Allow-List {STK}, Zustände, classify, check_tradable, identity_of/identity_diff, parse_liquid_hours, evaluate_session"
affects: [03-03, 03-04, 03-05]
key-files:
  created:
    - scripts/ibkr_contracts.py
    - tests/test_ibkr_contracts.py
  modified: []
requirements-completed: [REQ-IBKR-27, REQ-IBKR-28, REQ-IBKR-31, REQ-IBKR-37]
duration: ~25min
completed: 2026-10-12
---

# Phase 3 Plan 01: Vertragskern und Sitzungsparser Summary

Bibliotheksfreies Modul `scripts/ibkr_contracts.py` mit Mapping-Tabelle (5 Einträge, nur Suchschlüssel), Allow-List `{STK}`, benannten Zuständen, exakter Klassifikation, Handelbarkeitsprüfung, 4-Felder-Identitätsvergleich und eigenem Liquid-Hours-Parser mit 15-Minuten-Puffer.

## Tasks

| Task | Commits |
|------|---------|
| 1: Tabelle, Allow-List, classify, Handelbarkeit, Identität | RED `test(03-01)` (Task-1-Tests), GREEN `075274e` |
| 2: Sitzungs-Parser, Puffer, session-unknown, Gegentest | RED `14cbe76`, GREEN `54f8960` |

## Ergebnis

- 62 Tests in `tests/test_ibkr_contracts.py` grün (inkl. Gegentest gegen `ib_async.liquidSessions()`, Alt-Format wird von ib_async mit `ValueError` abgelehnt, unser Parser liefert 07:00-18:30).
- `ruff check .` und `ruff format --check` auf beiden Dateien: ohne Befund (selbst ausgeführt, `.venv` des Hauptcheckouts).
- `pytest tests -k ibkr`: 214 passed.
- Greps auf Uhrzeit-Literale und `normalize_symbol|datetime.now|time.time(|date.today` im Modul: leer.
- `XAUUSD+` -> CMDTY/XAUUSD (`not-allowed`), `normalize_symbol('XAUUSD+')` -> `GC=F`: im Test festgenagelt.
- `session-unknown` bei fehlendem Tageseintrag oder Parse-/Zonenfehler; `closed` (Sonntag, Puffer, Halbtag) ist keine Abweisung; `halted` nur im Zustandssatz.

## Deviations from Plan

None - Plan wie geschrieben ausgeführt. Hinweis: Der Worktree-Start lag auf 1394a3f; per Vorgabe auf efdb93f zurückgesetzt (vor jeder Arbeit).

## Known Stubs

Keine.

## Self-Check: PASSED

Dateien `scripts/ibkr_contracts.py`, `tests/test_ibkr_contracts.py` vorhanden; Commits 075274e, 14cbe76, 54f8960 vorhanden.
