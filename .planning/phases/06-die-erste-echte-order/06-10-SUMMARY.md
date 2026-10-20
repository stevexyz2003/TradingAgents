---
phase: 06-die-erste-echte-order
plan: 10
subsystem: ibkr-execution
tags: [operator-checkpoint, first-live-order, measurement]
requires: [06-09]
provides: [first live order on DUQ634065, ledger chain intent-placed-filled, same-day second run without order]
affects: [07]
key-files:
  created: []
  modified:
    - scripts/IBKR_EXECUTION.md
    - .planning/ibkr-konto-befund.md
    - scripts/ibkr_ledger.py
    - tests/test_ibkr_ledger.py
decisions:
  - "Completed orders from the gateway report quantity 0 (and orderId/clientId 0); the size comes from filled and the executions"
metrics:
  completed: 2026-10-19
---

# Phase 6 Plan 10: Erste echte Order — Summary

Die erste echte Market-Order ist am 2026-10-19 über `execute AAPL --live` auf `DUQ634065` gelaufen: BUY 1 AAPL, gefüllt mit 342.86 USD 0,43 s nach dem Senden. Das Ledger zeigt die vollständige Kette `intent → placed → filled`. Ein zweiter Lauf am selben Tag endete mit `already-attempted` und ohne zweite Order. Der Operator hat Fill, Position und Befund ohne Abweichung abgenommen.

## Ablauf (UTC)

| Zeit | Schritt |
|---|---|
| 15:36:21 | `--history` mit Schalter aus: leer (open/completed/executions 0) |
| 15:37:00 | Commit `698cffe` mit dem Handbuch-Eintrag der Freischaltung, **vor** der Order |
| 15:37:08 | `RELEASE` angelegt |
| 15:37:11.926 | `EXECUTE_INTENT`; 15:37:12.353 `ORDER_SENT` (orderId 18, permId 717633249, Filled) |
| 15:37:12.362 | `POST_ORDER_MISMATCH` „order quantity 0.0, expected 1.0“, Exit 10 (Fehlalarm) |
| 15:37:23 | `RELEASE` entfernt; `--history`: completed order `quantity` 0.0, `filled` 1.0, orderId 0 |
| 15:57–15:58 | Fixes `28ef33a` (Operator, Prüfung nach der Order) und `46c432b` (Reconciliation + 3 Tests); `pytest -k ibkr` 1246 passed |
| 15:59:10 | Zweiter Lauf: Exit 2 `already-attempted`, kein `ORDER_SENT` |
| 15:59:22 | Position AAPL 1.0; Historie open 0 / completed 1 / executions 1 |

Der Handbuch-Commit (15:37:00) liegt vor dem `ORDER_SENT` (15:37:12).

## Erfolgskriterien

- **SC1:** Die Freischaltung ist mit Datum, Grund und Vorher/Nachher im Handbuch notiert, bevor die Order lief. Der 321-Beleg stammt aus 06-09 (Abweichung zu D-15 siehe 06-09).
- **SC3:** `intent → placed → filled` ist vollständig mit `order_id`, `perm_id`, `order_ref == decision_key`, `exec_id`, `filled_qty` und Preis. Danach folgt die Zeile `alarm` aus dem Fehlalarm.
- **SC4:** Der zweite Lauf meldet `already-attempted`. Die Position entspricht dem Ziel der Leiter (Overweight = 1 Block = 1 Aktie).
- **SC5:** Es gab keine Korrektur. Die execId-Form `0000e0d5.6ad60c69.01.01` entspricht dem Fixture, das deshalb nicht geändert wurde (D-13).
- **SC6:** Execution und abgeschlossene Order stehen am selben Tag im Ledger bzw. im Befund.

## Deviations from Plan

- **Pipeline-Test statt Engine-Entscheidung (D-03 gelockert, Operator):** Die Order kam aus dem markierten Eintrag auf `fork/paper-log-pipeline-test` (`8453e76`), siehe 06-09.
- **[Rule 1 - Bug] Fehlalarm nach der Order:** Das Gateway meldet bei abgeschlossenen Orders `quantity` 0. Die Prüfung nach der Order (`scripts/ibkr_executor.py`) und die Reconciliation (`scripts/ibkr_ledger.py`, Twin-Erkennung und Kollisionsprüfung) werten eine 0 jetzt als unbekannt. Eine andere Menge ungleich 0 gilt weiter als Kollision. Der Plan sah keine Codeänderung am Messtag vor; der Operator hat den Fix ausdrücklich freigegeben, damit der zweite Lauf noch am selben Tag laufen konnte. Commits: `28ef33a`, `46c432b`.
- Weil der erste Lauf mit Exit 10 endete, hat er die Fill-Zeilen trotzdem gebucht (`fills_booked: true`). Der Eintrag war damit geschlossen, und der zweite Lauf brauchte keine Reconciliation.

## Lücken für die Verifikation

- Im Ledger steht für die erste Order eine `alarm`-Zeile (`post-order-mismatch`), die nach dem Fix kein echter Befund mehr ist. Sie bleibt als historischer Eintrag stehen.
- Die offenen Punkte aus 06-09 gelten weiter: 321 mit `reqId -1` → Timeout statt `READ_ONLY_API`; `summary.json` wird beim zweiten Paper-Run desselben Datums überschrieben; das Ledger trägt `rating_source: engine` beim Pipeline-Test.

## Self-Check: PASSED

- `grep "## First live order" scripts/IBKR_EXECUTION.md` → 1; Befund enthält „Messung 2: Erste echte Order“, „Messung 3: Historie nach dem Fill“, „Messung 4: Zweiter Lauf“.
- `ledger.jsonl`: für den Key genau eine `intent`- und eine `placed`-Zeile, eine `filled`-Zeile mit `exec_id`, Preis, `order_ref` = Key.
- State-Ordner ohne `RELEASE`/`KILL`; `pytest tests/test_ibkr_ledger.py` grün.
- Operator-Abnahme: „ich erkenne keine Abweichung“ (2026-10-20).
