---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 05
subsystem: ibkr-adapter
tags: [whatif, preview, open-orders, available-funds, ib_async]
requires: [04-02]
provides:
  - "BrokerPosition.con_id, AccountSnapshot.available_funds(+_currency)"
  - "IbkrBroker.open_orders(con_id) und OpenOrder"
  - "IbkrBroker.preview_order(...) und PreviewResult"
  - "STATE_BY_CODE 154 HALTED, 10349 TIF_OVERRIDDEN"
affects: [04-07, 04-08]
tech-stack:
  added: []
  patterns: ["zeitweiliger Abgriff von wrapper.openOrder im Aufruffenster (finally-Reset)", "Unset-Sentinel (>= 1e300, NaN, Text) wird None"]
key-files:
  created: []
  modified:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
    - tests/test_ibkr_executor.py
    - tests/test_ibkr_isolation.py
key-decisions:
  - "Auswertungsreihenfolge in preview_order: Link-Ereignis (Ausnahme) > 154 > 10349 > Timeout (321 = READ_ONLY_API, sonst REQUEST_TIMEOUT) > leer > OK"
  - "Bei nicht-OK-Zuständen sind alle Zahlenfelder None; effective_tif und errors bleiben gefüllt"
requirements-completed: [REQ-IBKR-38, REQ-IBKR-61, REQ-IBKR-25, REQ-IBKR-23, REQ-IBKR-68, REQ-IBKR-69, REQ-IBKR-70, REQ-IBKR-37]
duration: 30min
completed: 2026-10-12
---

# Phase 4 Plan 05: Lesewege und whatIf-Vorschau im Adapter Summary

Der Adapter liefert jetzt conId je Position, AvailableFunds im Kontobericht, offene Orders aller Clients je conId und `preview_order` (Markt-Order, `tif="DAY"` explizit, nur über `whatIfOrderAsync`) mit ausgewerteter Margin, Kommission, Fehlercodes 154/10349/321 und zurückgelesenem tif.

## Umgesetzt

- Task 1: `con_id` an `BrokerPosition`; `available_funds`/`available_funds_currency` (genau eine `AvailableFunds`-Zeile, sonst `SNAPSHOT_INCOMPLETE`); `open_orders` über `reqAllOpenOrdersAsync` mit Filter auf conId und nicht abgeschlossene Status (`_DONE_ORDER_STATUSES`); Fakes um `reqAllOpenOrdersAsync`, `open_trade`, verbotene `reqMktData`/`reqTickers`.
- Task 2: `PreviewResult`, `_money`, `PREVIEW_TIF`, `preview_order`; `_request_error_texts` für Fehlertexte; 154/10349 in `STATE_BY_CODE` und aus `_request_error_since` herausgehalten; `IbHandles.order` (Order-Klasse aus der einzigen Importstelle); Fakes `FakeWrapper.openOrder`, `order_state`, `whatIfOrderAsync` mit Echo.
- Methodenmenge des Adapters: sieben Namen (Isolationstest angepasst).

## Deviations from Plan

**1. [Rule 3] Bestehende Tests an Pflichtfelder angepasst.** `tests/test_ibkr_executor.py` (`_snapshot`, Summary-Fixture) und `test_positions_fresh_each_call` brauchten `AvailableFunds` bzw. die neuen `AccountSnapshot`-Felder.
**2. [Rule 1] Obsoleter Test ersetzt.** `test_halt_code_is_not_mapped_before_measurement` widersprach dem Plan (154 wird jetzt gemappt) und wurde zu `test_halt_code_is_mapped_for_the_preview`.

## Hinweise

- REQ-IBKR-67 (154 am Paper-Gateway provozieren) bleibt Lücke: 154 stützt sich auf die offizielle Codeliste und einen Fake-Test (Annahme A5).
- Echo-Abgriff setzt voraus, dass der Decoder `self.wrapper.openOrder` zur Aufrufzeit nachschlägt (decoder.py:1147, Wrapper ohne `__slots__`); gegen ein echtes Gateway nicht gemessen.

## Verifikation

- Gesamtsuite (ohne die bekannte `test_yfinance_keeps_its_cache_out_of_the_users_home`): 1924 grün, 4 übersprungen; `ruff check scripts tests` ohne Befund.
- `grep -cE "orderId=|\.orderId =|\.whatIfOrder\(|reqMktData|reqTickers" scripts/ibkr_broker.py` == 0.

## Commits

- 74d282b: test(04-05): failing tests für conId, AvailableFunds, offene Orders
- 12f61a6: feat(04-05): conId, AvailableFunds, open_orders
- f0edbb0: test(04-05): failing tests für die whatIf-Vorschau
- fbd06e0: feat(04-05): preview_order

## Known Stubs

Keine.

## Self-Check: PASSED
