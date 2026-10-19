---
phase: 06-die-erste-echte-order
plan: 03
subsystem: ibkr-broker-adapter
tags: [write-barrier, order-permit, place_order, whitelist, REQ-10]
requires: [06-01, 06-02]
provides:
  - _OrderPermit mit Whitelist (Namens-, Feld-, String-Ebene) in der Socket-Sperre
  - IbkrBroker.place_order, PlaceResult, _build_order/_build_contract
  - FakeIB.placeOrder als modellierte echte Order
affects: [06-05, 06-06]
key-files:
  modified:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
    - tests/test_ibkr_isolation.py
key-decisions:
  - "Order-Permit gilt pro Order: schliesst auf der Leitung (sendMsg) und im finally von place_order"
  - "Whitelist nutzt dieselben Verschiebungsblock-Pruefungen wie das whatIf-Layout (_plain_blocks); unbekanntes Layout = refused"
  - "ValidationError ist Endstatus (_FILL_TERMINAL); Fristablauf storniert nie (D-08), timed_out wird gemeldet"
  - "Fehlercodes in PlaceResult = alle requestbezogenen Fehler seit der Marke ausser INFO_CODES (399 bleibt sichtbar, Bewertung in 06-06)"
requirements-completed: [REQ-IBKR-10]
completed: 2026-10-19
---

# Phase 6 Plan 03: Order-Permit und place_order Summary

Die Socket-Sperre laesst eine echte Order (Nachricht 3 ohne whatIf) nur bei offenem Einmal-Permit und nur als reine STK/MKT/DAY-Order fuer `DUQ634065` mit orderRef und ganzzahliger Menge durch; `IbkrBroker.place_order` sendet genau eine solche Order ueber denselben Bauer wie die Vorschau und wartet bis `timeout_s` ohne Storno.

## Ergebnis

- `scripts/ibkr_broker.py`: `_PM_*`-Indizes (gemessen, ib_async 2.1.0), `_OrderPermit`, `_real_order_ok` / `_real_order_in_fields` / `_real_order_in_message` (fail-closed), `_arm_write_barrier(client, permit, order_permit)`. 4/19/21/58, `cancelOrder`, `reqGlobalCancel` bleiben bei offenem Order-Permit gesperrt.
- `place_order` (10. oeffentliche Methode), `PlaceResult`, `_place_and_wait` (Polling alle 0,1 s), `_build_order`/`_build_contract` gemeinsam mit `preview_order`. Kein `cancelOrder(` im Adapter.
- `tests/ibkr_fakes.py`: `FakeIB.placeOrder` (Name, dann Nachricht 3 im gemessenen Layout) mit `place_outcome`, `place_fill_price`, `place_perm_id`, `place_order_id`, `place_errors`, `place_executions`, `place_completed`, `placed_orders`.
- Tests: 24 `order_permit`-Faelle gegen die echte Client-Klasse (inkl. Layout-Pin, Feld- und Namensebene, Option/LMT/Fremdkonto/GTC/Menge 0/leere Ref, Wiederverwendung) und 19 `place_order`-Faelle (Filled, Timeout ohne Storno, 321 als Endstatus, 399, Link-Ereignis, offener Link, Eingabepruefung, Feldgleichheit mit der Vorschau, Attrappen-Konsistenz).

## Verifikation

- `pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py`: 1173 passed
- `ruff check scripts tests`: All checks passed
- `grep -v '^\s*#' scripts/ibkr_broker.py | grep -c "cancelOrder("`: 0; `_build_order(`: 3 Treffer

## Deviations from Plan

**1. [Rule 3 - Blocking] Bestehende Tests an neue Signatur/Attrappe angepasst**
- `test_forbidden_call_check_sees_a_client_write_without_the_barrier`: Stub von `_arm_write_barrier` nimmt jetzt `order_permit`.
- `test_forbidden_call_check_sees_an_ib_level_write`: Negativkontrolle nutzt `whatIfOrder`/`reqMktData`, da IB-Ebene `placeOrder` nun eine modellierte echte Order ist (die Sperre urteilt, nicht die Attrappe).
- Dateien `ruff format` nicht angewendet: `ibkr_broker.py`, `ibkr_fakes.py`, `test_ibkr_broker.py` waren schon vorher nicht format-sauber.

## Known Stubs

Keine.

## Threat Flags

Keine neuen Flaechen ausser dem im Plan modellierten Order-Permit (T-06-10 bis T-06-15 mitigiert und getestet).

## Self-Check: PASSED

Commits 349db52 (Task 1) und 67ed93d (Task 2) vorhanden; geaenderte Dateien existieren.
