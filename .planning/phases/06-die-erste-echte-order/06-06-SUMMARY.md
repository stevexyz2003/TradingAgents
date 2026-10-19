---
phase: 06-die-erste-echte-order
plan: 06
subsystem: ibkr-executor
tags: [live, LivePlacer, fill-timeout, place-rejected, REQ-48, REQ-65, REQ-10]
requires: [06-05]
provides:
  - "LivePlacer._classify: link / parked / timeout / rejected / partial / filled"
  - "fill-timeout (Exit 9) ohne Storno, place-rejected (Exit 5) schliesst den Key"
  - "Handbuch: After the order is sent, 399-Luecke (D-16), Budget-Akzeptanz (D-17)"
affects: [06-07, 06-08]
key-files:
  modified:
    - scripts/ibkr_executor.py
    - tests/test_ibkr_execute.py
    - scripts/IBKR_EXECUTION.md
key-decisions:
  - "Reihenfolge der Regeln: Link-Ereignis, 399, Timeout, Ablehnung/Teilfuellung, Filled"
  - "fill-timeout beendet den Lauf per _ExecuteStop (kein weiterer Ticker bei unklarem Ausgang); Ablehnung ist nur Ticker-Ende"
  - "Teilfuellung geht ueber den bestehenden Abweichungspfad (persistiert sichere Fills, dann post-order-mismatch)"
requirements-completed: [REQ-IBKR-10, REQ-IBKR-48, REQ-IBKR-65]
completed: 2026-10-19
---

# Phase 6 Plan 06: Ausgaenge des Live-Placers Summary

`LivePlacer.complete` sortiert jeden Ausgang des Sendens: Timeout, Link-Ereignis und geparkte Order (399) lassen die Order offen und stoppen den Lauf mit `fill-timeout` (Exit 9, nie ein Storno); eine definitive Ablehnung schliesst den Key mit `rejected`/`place-rejected` (Exit 5, der Lauf geht weiter); eine Teilfuellung behaelt die Fills und endet in `post-order-mismatch`.

## Ergebnis

- Task 1: `_classify`, `_fill_timeout`, `_rejected`; Konstanten `PARKED_CODES = frozenset({399})` (D-16) und `REJECT_STATUSES`. Der alte Test "status other than filled ends in deviation path" wurde durch die neuen Ausgangstests ersetzt (Timeout ist jetzt Exit 9).
- Reconciliation unveraendert. Folgelauf nach Timeout wie festgelegt: gleicher Tag/gleicher Key -> `already-attempted` (Exit 2); spaeterer Tag/neuer Key mit eigener offener Order -> `foreign-open-order` (Exit 2); Order inzwischen gefuellt -> `filled` mit `source: reconcile`. Beide Faelle als eigene Tests, kein abweichender State, also keine Luecke.
- Task 2: Tests `second_run` (selber Tag: `already-attempted`, `placeOrder` insgesamt einmal) und `second_run_next_day` (`within-tolerance`, kein Exit 6, kein `source-conflict`). Handbuch: Unterabschnitt "After the order is sent", ersetzte 399-Tabellenzeile (D-16), Absatz "Budget per ticker (accepted, D-17)".

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` -> 1216 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests` -> All checks passed
- `-k "fill_timeout or validation_error or parked_399 or place_rejected or partial_then or link_event"` -> 10 passed; laengster Test 1,2 s Setup, alle unter 5 s
- `cancelOrder` ausserhalb von Kommentaren in `scripts/ibkr_executor.py` -> 0 (zusaetzlich als Test gepinnt)

## Deviations from Plan

**1. [Rule 3 - Blocking] Taskaufteilung der Commits:** Die Tests von Task 2 (`second_run`) liegen in derselben Datei wie die von Task 1 und wurden im Task-1-Commit mitgenommen; Task 2 enthaelt nur das Handbuch.

**2. Zusatztest:** `test_live_fill_timeout_source_never_cancels` (Quelltext-Gate gegen `cancelOrder`/`reqGlobalCancel`), damit das Akzeptanzkriterium von mindestens 10 Tests im `-k`-Filter erreicht und T-06-31 testseitig gedeckt ist.

**3. Teilfuellungs-Test:** Der Broker-Verlauf wird erst beim Senden gesetzt (Hook auf `placeOrder`), weil eine vorbelegte Historie sonst als `source-conflict` vor dem Senden endet.

## Commits

- cbfcc9b feat(06-06): classify placer outcomes - fill-timeout without cancel, place-rejected, parked 399
- 1fb51ad docs(06-06): document placer outcomes, the 399 gap and the per-ticker budget

## Known Stubs

Keine. Luecke dokumentiert: 399 ist nur per Fake belegt, nicht am Gateway gemessen (wie `halted`, REQ-67).

## Threat Flags

Keine neue Flaeche; T-06-28 bis T-06-32 mitigiert und getestet, T-06-33 akzeptiert und dokumentiert. Es wurde nie ein echtes Gateway kontaktiert, nur Fakes.

## Self-Check: PASSED

Commits cbfcc9b und 1fb51ad vorhanden; geaenderte Dateien existieren.
