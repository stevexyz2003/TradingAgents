---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 08
subsystem: docs-tests
tags: [handbook, isolation, report, backup, portfolio-feed]
requires: [07-02, 07-05, 07-06, 07-07]
key-files:
  modified:
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_isolation.py
requirements: [REQ-IBKR-49, REQ-IBKR-50, REQ-IBKR-51, REQ-IBKR-52]
completed: 2026-10-20
---

# Phase 7 Plan 08: Handbuch und Isolationstests Summary

Das Handbuch dokumentiert jetzt Soll/Ist-Bericht, IBKR-Backup und den CI-Portfolio-Rückkanal (D-17 öffentlich, D-18 Jev entfällt); die Isolationstests nehmen `ibkr_report.py` in die Reinheitsregeln auf und pinnen die Handbuchinhalte.

## Umsetzung

- Task 1 (e089794): Unterabschnitte `### Soll/Ist report`, `### Backup of the IBKR state`, `### Portfolio for the CI run` vor "See also"; Commands-Zeilen für `ibkr_report.py` und `backup --dry-run`; Verweis von der Portfolio-Warnung auf den neuen Abschnitt. Exit-Codes des Berichts (0/1/2) und der Paper-Fill-Hinweis gemäß Quellcode (`PAPER_FILL_NOTICE`). Client-Bibliothek nicht genannt.
- Task 2 (6b89582): `REPORT`-Konstante, beide Reinheitstests auf `(DECISION, PAPERLOG, PUBLISH, REPORT)`; vier neue Tests (Soll/Ist, Backup, CI-Feed, keine Git-Schreib-Strings per AST). `ruff format` auf der Testdatei angewandt (2 Zeilen entfernt, sonst nur Anhänge).

## Verifikation (ausgeführt)

- `pytest tests/test_ibkr_isolation.py`: 40 passed
- `pytest tests/test_ibkr_*.py tests/test_state_maintenance.py tests/test_daily_paper_run.py`: 1466 passed
- `ruff check scripts tests`: sauber
- Volle Suite nicht gelaufen (nur die oben genannten Gruppen).

## Deviations from Plan

Keine. Der Reinheitstest für `ibkr_report.py` war ohne Änderung am Modul grün.

## Known Stubs

Keine.

## Self-Check: PASSED

Beide Commits im Log; STATE.md/ROADMAP.md nicht angefasst.
