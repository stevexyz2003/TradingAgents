---
phase: 06-die-erste-echte-order
plan: 01
subsystem: ibkr-ledger
tags: [ledger, execid, reconcile, signed-fills, REQ-47, WR-07]
requires: []
provides:
  - exec_family / correction_rank / effective_executions / fill_records im reinen Ledger-Modul
  - signiertes, korrekturbewusstes Ledger.filled_quantity
  - Ledger-Eintraege alarm, rating-jev -> review, place-rejected
affects: [06-02, 06-05, 06-06]
tech-stack:
  added: []
  patterns: [ein Codepfad fuer Fill-Zeilen (Reconcile und Live-Placer), Schema-Pruefung auch beim Schreiben]
key-files:
  created: []
  modified:
    - scripts/ibkr_ledger.py
    - scripts/ibkr_executor.py
    - tests/test_ibkr_ledger.py
    - tests/test_ibkr_guards.py
    - tests/test_ibkr_execute.py
key-decisions:
  - "Fixture-execIds in der Form <basis>.01.01 / <basis>.01.02; die Familie ist alles vor dem letzten ziffernreinen Suffix (Rohform wird in 06-10 bestaetigt, D-13)"
  - "append() prueft filled/partial/alarm vor dem Schreiben gegen das Schema, damit keine Zeile entsteht, die beim naechsten Oeffnen abgewiesen wuerde"
requirements-completed: [REQ-IBKR-47]
duration: ca. 25 min
completed: 2026-10-19
---

# Phase 6 Plan 01: Ledger-Grundlage fuer echte Fills Summary

execId-Korrekturregel (`.02` ersetzt `.01`), vorzeichenbehaftete Fill-Summe mit Pflichtfeld `side` und ein gemeinsamer Fill-Helfer `fill_records`, den die Reconciliation jetzt nutzt.

## Ergebnis

- `scripts/ibkr_ledger.py` (bleibt rein): `exec_family`, `correction_rank`, `effective_executions`, `fill_records`; `resolve_entry` summiert nur wirksame Executions; `filled_quantity` ist signiert (BUY +, SELL -) und zaehlt je Key nur `exec_id`-Zeilen (hoechste Korrektur je Familie), sonst die Aggregatzeile (Pitfall 5).
- Neues Event `ALARM` (nicht lifecycle), `rating-jev` -> `review`, `place-rejected` in `REJECTED_STATES`; `filled`/`partial` verlangen `side` in `{BUY, SELL}`.
- `scripts/ibkr_executor.py`: `_reconcile` schreibt Fills je wirksamer execId ueber `fill_records` (`source="reconcile"`); ohne Executions eine Aggregatzeile mit `side`; `_fill_quantity` nutzt `effective_executions`.

## Tasks

| Task | Commit | Inhalt |
|------|--------|--------|
| 1 | 2e8ab05 | Reine execId-Funktionen, fill_records, side-Pflicht, neue Tabelleneintraege, Ledger-Tests |
| 2 | 35d654f | Signiertes filled_quantity, Reconcile ueber fill_records, Guards-/Execute-Tests |

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` -> 1124 passed
- `-k signed` (Ledger+Guards) -> 5 passed, darunter Negativ-Kontrolle; `-k correction` (Ledger+Execute) -> 6 passed; `-k "exec_id or correction"` im Ledger -> 10 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests` -> All checks passed

## Deviations from Plan

**1. [Rule 2 - Fehlerschutz] Schema-Pruefung in `append()`**
- Plan verlangte "vom Ledger-Schema abgewiesen"; das Schema lief nur beim Oeffnen. Ohne Pruefung beim Schreiben waere eine `filled`-Zeile ohne `side` geschrieben worden und haette den Ledger beim naechsten Oeffnen unbrauchbar gemacht.
- Fix: `append()` ruft `_schema_problem` fuer `filled`/`partial`/`alarm` vor dem Schreiben. Commit 2e8ab05.

**2. [Hinweis] Commit 2e8ab05 allein laesst `tests/test_ibkr_execute.py` rot**
- Die side-Pflicht wirkt sofort, der Executor schrieb noch ohne `side`; erst Commit 35d654f stellt ihn um. Die Suite ist nach Task 2 vollstaendig gruen.

**3. [Hinweis] execId-Fixtures `.01.01`/`.01.02`**
- Der Plantext spricht von `.01`/`.02`; die Familienregel (letztes ziffernreines Suffix) und das Beispiel `...01.02 -> ...01` verlangen die Rohform mit zwei Suffixen. Tests nutzen sie entsprechend.

**4. Formatierung:** `ruff format` auf den fuenf geaenderten Dateien (waren vorher formatiert).

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsflaeche; T-06-01 bis T-06-05 sind durch Tests abgedeckt.

## Self-Check: PASSED

- scripts/ibkr_ledger.py, scripts/ibkr_executor.py, die drei Testdateien: vorhanden
- Commits 2e8ab05, 35d654f: vorhanden
