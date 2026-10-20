---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 06
subsystem: ibkr-executor
tags: [publish, ibkr-log, exit-11, handbook]
requires: [07-01]
provides:
  - "ibkr_executor.py publish (EXIT_PUBLISH = 11)"
  - "Handbuchabschnitt: Ein-Schreiber-Invariante, Betriebsablauf"
affects: [07-07]
key-files:
  created:
    - tests/test_ibkr_publish_cli.py
  modified:
    - scripts/ibkr_executor.py
    - tests/test_ibkr_executor.py
    - tests/test_ibkr_isolation.py
    - scripts/IBKR_EXECUTION.md
requirements: [REQ-IBKR-52]
decisions:
  - "publish hat bewusst kein --env-file und ruft nie eine Broker-Factory auf"
  - "Der Ledger-Lock wird nur für das Lesen der drei Dateien gehalten und vor jedem Git-Aufruf freigegeben"
metrics:
  completed: 2026-10-20
  tasks: 2
  files: 5
---

# Phase 7 Plan 06: publish-Unterbefehl Summary

`ibkr_executor.py publish` ist ein dünner Wrapper um `scripts/ibkr_publish.py`: Snapshot unter Lock lesen, Ledger validieren, Remote prüfen, auf `fork/ibkr-log` veröffentlichen. Exit 11 (`EXIT_PUBLISH`) ist neu; `execute` bleibt unverändert.

## Ergebnis

- Task 1 (Commit 81fa460): `EXIT_PUBLISH`, `default_publish_dir`, `default_portfolio_file`, `load_publish_module`, `run_publish`, Parser und `main` (`publish_repo`, `git_run`). Basis-SHA für Diff-Vergleiche: ff9a6a25125e03d1d032d314c1c03f3a5115fd20 (nach Worktree-Reset von e8f5503).
- Task 2 (Commit d6ce33d): Handbuch (Exit-Zeile 11, Abschnitt „Publishing to ibkr-log“, Commands-Eintrag) und Isolationstests (Exit-Tabelle 13, `PUBLISH` in den Reinheitstests, Invarianten-Text-Pin, Test auf Force-/paper-log-Freiheit des Moduls).
- Exit-Pfade durch Tests belegt: 0 (erst/unverändert), 1 (kein Ledger, kein `fork`, `fork == origin`), 6 (kaputter Ledger), 7 (Lock gehalten, kein Git-Aufruf, kein Klon), 11 (Push-Rennen).
- Warnungen: `PUBLISH_NO_PORTFOLIO`, `PUBLISH_PORTFOLIO_UNDATED`, `PUBLISH_PORTFOLIO_OLDER_THAN_LEDGER`, `PUBLISH_FOREIGN_COMMIT`. Im Log steht nur der Remote-Name, nie die URL.

## Verifikation (tatsächlich ausgeführt)

- `pytest tests/test_ibkr_publish_cli.py`: 13 passed.
- `pytest tests/test_ibkr_publish.py tests/test_ibkr_execute.py tests/test_ibkr_preview.py tests/test_ibkr_executor.py`: 325 passed.
- `pytest tests/test_ibkr_isolation.py`: 36 passed.
- `pytest tests/test_ibkr_*.py`: 1313 passed.
- `ruff check scripts tests`: sauber; `ruff format` auf allen berührten Dateien angewandt.

## Deviations from Plan

- Worktree-Basis wich ab (e8f5503); gemäß Vorgabe per `git reset --hard ff9a6a2` korrigiert.
- Einmaliger, nicht reproduzierbarer Git-Fehler „Out of memory“ in der Test-Fixture beim ersten Lauf; der Wiederholungslauf war grün. Kein Codefehler.
- Sonst keine: Plan wie geschrieben umgesetzt.

## Known Stubs

Keine.

## Self-Check: PASSED

- Commits 81fa460 und d6ce33d vorhanden; tests/test_ibkr_publish_cli.py vorhanden; alle oben genannten Testläufe wurden ausgeführt.
