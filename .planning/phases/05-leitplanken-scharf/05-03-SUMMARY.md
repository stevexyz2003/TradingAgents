---
phase: 05-leitplanken-scharf
plan: 03
subsystem: ibkr-adapter
tags: [ibkr, adapter, write-barrier, reconciliation, kill-switch]
requires: []
provides:
  - "IbkrBroker.order_history() (OrderRecord, ExecutionRecord, OrderHistory)"
  - "IbkrBroker.open_orders(con_id=None) mit order_ref"
  - "IbkrBroker.preview_order(order_ref=) mit echo_order_ref/echo_account"
  - "IbkrBroker.cancel_all(kill_evidence=) und _CancelPermit"
affects: [05-04, 05-05, 05-06, 05-07, 05-08]
tech-stack:
  added: []
  patterns: ["Einmal-Permit in der Socket-Sperre", "drei fail-closed Lesefenster ueber _read"]
key-files:
  created: []
  modified:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
    - tests/test_ibkr_isolation.py
key-decisions:
  - "Nachricht 58 bleibt auf Name, Feld- und Drahtebene zu; nur cancel_all oeffnet ein Permit fuer einen Durchgang, gezaehlt auf der Drahtebene"
  - "Adapter hat 9 oeffentliche Methoden (Platz fuer place in Phase 6)"
requirements-completed: [REQ-IBKR-35, REQ-IBKR-41, REQ-IBKR-43, REQ-IBKR-63, REQ-IBKR-66]
duration: ca. 35 min
completed: 2026-10-17
---

# Phase 5 Plan 03: Adapter-Erweiterung Summary

Der Adapter liest jetzt offene Orders, erledigte Orders und Executions in einem Aufruf, traegt `orderRef` samt Konto-Echo durch die whatIf-Vorschau und kennt genau eine kontrollierte Storno-Oeffnung (`cancel_all` mit Kill-Beleg, einmal je Sitzung).

## Ergebnis

- `order_history()`: drei `_read`-Fenster (`reqAllOpenOrders`, `reqCompletedOrders`, `reqExecutions`), broker-neutrale Datensaetze; unbekannte Execution-Seite endet fail-closed mit `REQUEST_FAILED`; `filled` ist `None` fuer den UNSET-Wert; `BOT`/`SLD` werden `BUY`/`SELL`.
- `open_orders(con_id=None)`: ohne Filter alle offenen Orders, `OpenOrder.order_ref` mit Default.
- `preview_order(order_ref=)`: `orderRef` nur bei gesetztem Wert an die Order; Echo-Tap liest `orderRef` und `account` zurueck (`None` ohne Echo).
- `cancel_all(kill_evidence=)`: `_CancelPermit`; ohne Beleg, beim zweiten Aufruf oder ohne Verbindung scheitert er; Erfolg nur wenn Nachricht 58 genau einmal auf dem Draht war. Danach scheitert ein direkter `reqGlobalCancel` wieder mit `ReadOnlyViolation`. Logzeile `ibkr-state=GLOBAL_CANCEL_SENT code=- detail="count=1 reason=kill_switch"`.
- `_WRITE_CALLS` und `_WRITE_MESSAGE_IDS` unveraendert; `WINDOW_BENIGN_CODES`/`INFO_CODES` unberuehrt.
- Fakes nur additiv (Defaults), `tests/test_ibkr_market_data.py` bleibt gruen.

## Commits

- 1b8aff1 test(05-03): fehlschlagende Tests fuer order_history, open_orders, order_ref
- 452b450 feat(05-03): order_history, ungefiltertes open_orders, orderRef-Echo (+ "order_history" in der Methodenmenge)
- 960adbc test(05-03): fehlschlagende Tests fuer Permit und cancel_all
- bfc708e feat(05-03): Einmal-Permit und cancel_all (+ "cancel_all" in der Methodenmenge)

## Verifikation (tatsaechliche Ausgabe)

- `pytest tests -k ibkr -q`: 671 passed, 1475 deselected
- `pytest tests/test_ibkr_broker.py -k "order_history or order_ref or open_orders"`: 22 passed
- `pytest tests/test_ibkr_broker.py -k "cancel_all or global_cancel or negative_control"`: 18 passed
- `ruff check scripts tests`: All checks passed
- `ruff format` wurde nicht auf ganze Dateien angewendet (bestehende Dateien sind nicht durchformatiert); eigene Zeilen sind formatkonform.

## Deviations from Plan

**1. [Rule 3 - Blocking] Bestehende Tests an neue Signaturen angepasst**
- `test_preview_returns_a_fully_read_result`: erwartetes `PreviewResult` um `echo_order_ref=""`, `echo_account="DUQ634065"` ergaenzt (das Fake-Echo traegt beides, die neuen Felder sind nicht mehr `None`).
- `test_forbidden_call_check_sees_a_client_write_without_the_barrier`: monkeypatch-Lambda nimmt jetzt `(client, permit=None)`, weil `connect` das Permit uebergibt.

**2. [Rule 2] `cancel_all` bildet `ConnectionError` auf `GatewayUnavailable(NOT_CONNECTED)` ab**, damit ein Bibliotheksfehler nicht roh durchschlaegt; das Permit schliesst im `finally`.

**3. Worktree-Basis:** HEAD wurde laut Anweisung auf fecb76b zurueckgesetzt (Merge-Base war 1394a3f). Der Plan-Hinweis zum Operator-WIP in `tests/test_ibkr_isolation.py` greift im Worktree nicht: die Datei war sauber, normal gestaged; nur die eine Mengenzeile wurde je Commit geaendert. Beim Zusammenfuehren im Hauptbaum bitte auf WIP-Hunks am Dateiende achten.

## Known Stubs

Keine.

## Threat Flags

Keine neuen Flaechen ausser der im Plan modellierten Oeffnung (T-05-15, T-05-16). Wächter "ibkr_market_data.py nennt weder cancel_all noch reqGlobalCancel" folgt in 05-09.

## Self-Check: PASSED

Dateien und Commits (1b8aff1, 452b450, 960adbc, bfc708e) vorhanden.
