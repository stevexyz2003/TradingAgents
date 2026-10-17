---
phase: 05-leitplanken-scharf
plan: 01
subsystem: ibkr-guards
tags: [ibkr, guards, fail-closed, tdd]
requires: []
provides:
  - scripts/ibkr_guards.py (Schalter-Parser, Switches, Größengrenze, decision_key, drei Quellenvergleiche, EXIT_BY_STATE, worst_run_exit)
affects: [05-04, 05-05, 05-06, 05-07]
tech-stack:
  added: []
  patterns: [bibliotheksfreies Modul, Uhr als Parameter, benannte Zustände mit eigener Exit-Tabelle]
key-files:
  created: [scripts/ibkr_guards.py, tests/test_ibkr_guards.py]
  modified: []
key-decisions:
  - "read_kill nutzt os.stat mit drei Ausgängen; unter Windows meldet stat auf KILL in einer Datei als Statedir FileNotFoundError, daher wird bei FileNotFoundError das Verzeichnis nachgeprüft (Datei statt Ordner -> kill-unreadable)"
requirements-completed: [REQ-IBKR-32, REQ-IBKR-33, REQ-IBKR-34, REQ-IBKR-39, REQ-IBKR-63, REQ-IBKR-64, REQ-IBKR-66]
duration: ~25 min
completed: 2026-10-17
---

# Phase 5 Plan 01: Leitplanken-Bausteine (ibkr_guards) Summary

Neues bibliotheksfreies Modul `scripts/ibkr_guards.py` mit fail-closed gelesener Freigabe- und Kill-Datei, Größengrenze (ablehnen statt kürzen), SHA-freiem `decision_key`, drei Quellenvergleichen und eigener Exit-Tabelle samt `worst_run_exit`.

## Ergebnis

- 4 Commits (RED/GREEN je Task): 20acba0, f5ea84d, d1d8f64, 4d67309.
- `tests/test_ibkr_guards.py`: 100 Tests, alle grün. Zusammen mit `test_ibkr_decision`, `test_ibkr_contracts`, `test_ibkr_isolation`: 342 passed.
- `ruff check scripts tests/test_ibkr_guards.py`: All checks passed. `ruff format` angewandt.
- Wächter-Greps (`.exists(`, `datetime.now`, `time.time(`, `date.today`, `ibkr_market_data`, `ib_async`, `tradingagents`, Uhrzeit-Literale): je 0 Treffer.
- Negativ-Kontrollen: `test_negative_control_kill_never_uses_exists`, `test_negative_control_size_cap_rejects_instead_of_trimming`.
- Sentinel `test_size_sentinel_blocks_times_block_qty_fit_the_cap` koppelt `BLOCKS` x `block_qty` (nur Einträge mit `sec_type in ALLOWED_SEC_TYPES`) an `MAX_QTY_PER_ORDER`.

## Deviations from Plan

**1. [Rule 1 - Bug] Windows-Verhalten von os.stat bei Statedir = Datei**
- **Found during:** Task 1 (GREEN)
- **Issue:** `os.stat("<datei>/KILL")` wirft unter Windows `FileNotFoundError` statt `NotADirectoryError`; der Test `kill-unreadable` für "state_dir ist eine Datei" schlug fehl (fail-open-Risiko).
- **Fix:** Hilfsfunktion `_kill_absent_or_blocked`: bei `FileNotFoundError` wird das Verzeichnis geprüft; existiert es als Ordner oder gar nicht -> `kill-absent`, existiert es als Nicht-Ordner -> `kill-unreadable`.
- **Files modified:** scripts/ibkr_guards.py
- **Commit:** f5ea84d

Sonst: Plan wie geschrieben ausgeführt. STATE.md und ROADMAP.md wurden nicht angefasst.

## Hinweise für Folgepläne

- Fehlender State-Ordner gilt als `kill-absent` (der Executor legt ihn vor dem Lock an, 05-04).
- `_EXIT_*`-Literale müssen in 05-04 per `test_guards_exit_literals_match_executor_constants` gegen die Executor-Konstanten geprüft werden.

## Known Stubs

Keine.

## Self-Check: PASSED

- scripts/ibkr_guards.py, tests/test_ibkr_guards.py vorhanden; Commits 20acba0, f5ea84d, d1d8f64, 4d67309 im Log.
