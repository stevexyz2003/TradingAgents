---
phase: 06-die-erste-echte-order
plan: 05
subsystem: ibkr-executor
tags: [live, LivePlacer, post-order-check, REQ-10, REQ-47, REQ-48, REQ-65]
requires: [06-01, 06-03, 06-04]
provides:
  - "execute --live (pro Lauf, D-01), Placer-/Modus-Abgleich not-dry / not-live"
  - "Ledger je Modus: ledger.jsonl (live) / ledger-dryrun.jsonl (trocken)"
  - "LivePlacer: place_order, placed, Post-Order-Kontrolle, Fills im selben Lauf, alarm + Exit 10"
affects: [06-06, 06-07, 06-08]
key-files:
  modified:
    - scripts/ibkr_executor.py
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_execute.py
    - tests/test_ibkr_isolation.py
key-decisions:
  - "EXECUTE_FORCED_DRY entfernt; Placer und Modus werden vor jeder Dateiberuehrung in beide Richtungen abgeglichen"
  - "Eigene Order/Executions per permId (orderId bei permId 0) bzw. orderRef; leerer oder fremder orderRef einer eigenen Execution ist eine Abweichung"
  - "Bei Abweichung werden nur Fills persistiert, die Seite, conId und orderRef der Absicht tragen; der Rest steht im alarm (seen.executions)"
  - "Ein Status ausser Filled, Timeout oder Link-Ereignis geht in diesem Plan fail-closed in den Abweichungspfad (06-06 trennt das auf)"
requirements-completed: [REQ-IBKR-10, REQ-IBKR-47, REQ-IBKR-48, REQ-IBKR-65]
completed: 2026-10-19
---

# Phase 6 Plan 05: --live und LivePlacer Summary

`execute --live` waehlt `LivePlacer` und `ledger.jsonl`; der Placer sendet genau eine Markt-Order ueber `place_order`, schreibt `placed`, liest den Zustand bei IBKR zurueck, vergleicht ihn mit dem `intent` und persistiert die Fills im selben Lauf; jede Abweichung stoppt den ganzen Lauf mit Exit 10.

## Ergebnis

- Task 1: `--live`-Flag, `EXECUTE_FORCED_DRY` entfernt, `not-dry`/`not-live` (Exit 1) vor jeder Dateiberuehrung, Ledger-Ziel und Modus nach `--live`, Lock bleibt `ledger.jsonl.lock`. Hilfsfunktion `_live_run` fuer 06-06/06-08; `_run_execute` liest bei `--live` das Live-Ledger.
- Task 2: `LivePlacer` mit `FILL_TIMEOUT_S = 60.0`, `POST_ORDER_READS = 5`, `POST_ORDER_RETRY_S = 1.0`; `ctx.placing` wird in `_execute_ticker` mit denselben Werten wie die Vorschau belegt. Kette `intent -> placed -> filled` mit `order_id`, `perm_id`, `order_ref`, `exec_id`, `filled_qty`, `avg_price`, `completed_status`. `place_order` hat genau eine Aufrufstelle (AST-Test).
- Task 3: Handbuch (execute, Ledger-Ereignisse inkl. `alarm`, Fill-Zeilen, Read-Only nach der Freischaltung D-04, Command-Zeile), Isolationstest um `--live`, `post-order-mismatch`, `alarm` erweitert.

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` -> 1205 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests` -> All checks passed
- `grep -c "\.place_order(" scripts/ibkr_executor.py` -> 1; `cancelOrder|reqGlobalCancel` ausserhalb von Kommentaren -> 0

## Deviations from Plan

**1. [Rule 3 - Blocking] Bestehenden Test angepasst:** `test_there_is_no_option_that_lifts_the_dry_run` parametrisierte `--live` als unbekannte Option (Exit 1); `--live` ist jetzt gueltig und wurde aus der Liste genommen (`--wet`, `--real`, `--force` bleiben).

**2. Zusatzpruefungen im Vergleich:** Zusaetzlich zum Plan werden `filled` der abgeschlossenen Order und eine abweichende `permId` einer Execution gegen die Absicht geprueft; Tests: sechs Abweichungsfaelle (Fill zu klein, Seite, fremder orderRef, fremde conId, leerer orderRef, Order-Fuellung zu klein).

**3. Test Folgetag:** Der Folgelauf endet ueber den Schluessel-Check mit `already-attempted` (Exit 2) ohne Broker-Kontakt, keine `source-conflict`; das Ledger liefert `filled_quantity == 2`.

## Commits

- 78f1248 feat(06-05): add --live flag, placer/mode check and ledger per mode
- 5042a3a feat(06-05): add live placer with post-order check and same-run fills
- 3cbdf24 docs(06-05): document --live, ledger per mode and the post-order check

## Known Stubs

Keine. Timeout und definitive Ablehnung laufen bewusst noch fail-closed in den Abweichungspfad; 06-06 trennt sie ab.

## Threat Flags

Keine neue Flaeche; T-06-21 bis T-06-27 mitigiert und getestet. Es wurde nie ein echtes Gateway kontaktiert, nur Fakes.

## Self-Check: PASSED

Commits 78f1248, 5042a3a und 3cbdf24 vorhanden; geaenderte Dateien existieren.
