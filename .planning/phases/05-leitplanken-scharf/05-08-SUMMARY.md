---
phase: 05-leitplanken-scharf
plan: 08
subsystem: ibkr-operator-probe
tags: [ibkr, smoke, read-only, operator-checkpoint]
requires: [05-03]
provides:
  - "scripts/smoke/ibkr_order_probe.py (--history, --whatif TICKER --order-ref)"
affects: [05-10]
key-files:
  created:
    - scripts/smoke/ibkr_order_probe.py
    - tests/test_ibkr_order_probe.py
  modified: []
key-decisions:
  - "Die Sonde nutzt ausschliesslich order_history() und preview_order(order_ref=...) des Adapters; kein cancel_all, keine Marktdaten, kein Import der Client-Bibliothek"
requirements-completed: [REQ-IBKR-41, REQ-IBKR-43]
completed: 2026-10-17
---

# Phase 5 Plan 08: Read-only-Sonde Summary

Eine nur lesende Sonde fuer die Operator-Messungen A2, A3 und A5: `--history` gibt offene Orders, erledigte Orders und Executions als JSON aus, `--whatif TICKER --order-ref ...` setzt genau einen whatIf ab und zeigt Zustand, Fehlercodes, `echo_order_ref`, `echo_account` und TIF.

## Ergebnis

- Laedt `scripts/ibkr_executor.py` per Pfad und nutzt dessen Lader, `read_settings`, `validate_settings`, Logging und `default_contracts_file`.
- `--quantity` nur 1 oder 2 (argparse `choices`); genau eine der Aktionen ist Pflicht (Exit 1, Hinweis "--history or --whatif TICKER").
- Exit-Codes: 0 ok, 1 Konfiguration/fehlender Vertrag (Hinweis `resolve --init`), 3 Gateway/ReadOnlyViolation/ungesund, 8 Account-Guard.
- 9 Tests (inkl. 2 parametrisiert) gegen FakeIB: JSON-Form, `orderRef` an der whatIf-Order, nichts gesendet (`placeOrder`/`cancelOrder`/`reqGlobalCancel` nie in `fake.calls`), Quelltext-Wächter.

## Commits

- dcc1d62 test(05-08): failing tests for the read-only order probe
- 3f96da2 feat(05-08): read-only order probe

## Verifikation (tatsaechliche Ausgabe)

- `pytest tests/test_ibkr_order_probe.py tests/test_ibkr_isolation.py -q`: 35 passed
- `ruff check scripts tests`: All checks passed; `ruff format` auf beiden Dateien: unveraendert
- `grep -cE "cancel_all|reqGlobalCancel|placeOrder|reqMktData|ib_async"` == 0; `order_ref=` == 1; `order_history()` == 1

## Deviations from Plan

Keine. Worktree-Basis wurde laut Anweisung auf c3f1aac zurueckgesetzt (Merge-Base war 1394a3f).

## Offene Operator-Aktion

Der Lauf gegen das echte Paper-Gateway (`--history` nach einem Storno, `--whatif AAPL --order-ref "2026-10-09|AAPL"`) wurde NICHT ausgefuehrt; er gehoert zum Operator-Checkpoint 05-10.

## Known Stubs

Keine.

## Threat Flags

Keine neuen Flaechen (T-05-44 bis T-05-46 wie geplant mitigiert).

## Self-Check: PASSED
