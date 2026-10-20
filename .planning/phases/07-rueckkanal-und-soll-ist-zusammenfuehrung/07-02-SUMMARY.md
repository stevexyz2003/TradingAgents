---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 02
subsystem: state-maintenance
tags: [backup, ibkr, dry-run]
requires: []
provides:
  - "state_maintenance.py backup --dry-run / --ibkr-dir"
  - "IBKR_BACKUP_FILES Allow-Liste, default_ibkr_dir"
affects: [scripts/STATE_OPERATIONS.md]
key-files:
  modified:
    - scripts/state_maintenance.py
    - tests/test_state_maintenance.py
    - scripts/STATE_OPERATIONS.md
requirements: [REQ-IBKR-51]
metrics:
  completed: 2026-10-20
---

# Phase 7 Plan 02: Backup mit IBKR-Dateien und --dry-run Summary

`state_maintenance.py backup` packt jetzt Ledger, Dry-Run-Ledger, Contract-Cache und Contract-Historie unter `ibkr/` (explizite Namensliste) und kennt `--dry-run` und `--ibkr-dir`.

## Umsetzung

- **Task 1 (1496b45):** `IBKR_BACKUP_FILES`, `default_ibkr_dir` (gleiche Regel wie `ibkr_executor._ibkr_base`, per Test gleichgesetzt), `backup(..., ibkr_dir, dry_run)`. Dry-Run listet die Mitglieder, schreibt kein Archiv und legt `--out` nicht an; echter Backup ohne `--out` bleibt Exit 1. Fehlender IBKR-Ordner ergibt eine Hinweiszeile, Exit 0. `RELEASE`, `KILL`, abgeleitete Dateien, Locks, `logs/`, `publish/` sind nie enthalten.
- **Task 2 (docs-Commit):** `STATE_OPERATIONS.md` um Backup-Mitglieder, `--dry-run`, Recovery-Pfad und den Verweis auf `ibkr-log` ("one writer per branch") ergaenzt.

## Verifikation (tatsaechlich ausgefuehrt)

- `pytest tests/test_state_maintenance.py -q`: 35 passed
- `pytest -k "ibkr or dry_run"`: 9 passed
- `ruff check` und `ruff format` auf beiden Python-Dateien: sauber
- Akzeptanz-Greps (Runbook und `"RELEASE"`/`"KILL"` ausserhalb von Kommentaren = 0): erfuellt

## Deviations from Plan

Das Worktree stand beim Start auf einem anderen Basis-Commit (e8f5503); gemaess Startup-Pruefung per `git reset --hard b346a33` korrigiert. Sonst keine Abweichungen.

## Known Stubs

Keine.

## Self-Check: PASSED

Dateien vorhanden, beide Task-Commits (1496b45 und der docs-Commit) im Log, STATE.md/ROADMAP.md unveraendert.
