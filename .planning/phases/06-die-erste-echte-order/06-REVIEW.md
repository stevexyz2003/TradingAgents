---
phase: 06-die-erste-echte-order
reviewed: 2026-10-19T00:00:00Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - scripts/ibkr_executor.py
  - scripts/ibkr_broker.py
  - scripts/ibkr_ledger.py
  - scripts/ibkr_guards.py
  - scripts/ibkr_decision.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-10-19
**Depth:** deep (diff 1d2e28c..HEAD, production code; ib_async 2.1.0 wrapper/order/client read for cross-checks)
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Priority-1 checks pass. Only one call site sends an order (`LivePlacer.complete` -> `place_order`). The
order permit closes on the wire after exactly one message 3. The `intent` is fsynced before
`place_order`. KILL and RELEASE are re-read right before the whatIf and again right before the
`intent`. A dry placer cannot run with `--live`, and the reverse is refused too. No cancel call
is reachable from the placer path. `cancel_all` is reached only from `_kill_path`, as designed in
D-17. Suite: 1198 passed.

The blocker is in how the outcome is classified after sending. The placer treats the local
`ib_async` status `ValidationError` as a definite rejection, and it does the same with a
`Cancelled` status that `ib_async` sets itself. In both cases the order can still be live at
IBKR. The ledger then closes the key as `rejected` and the run goes on.

## Critical Issues

### CR-01: A live order can be booked as `place-rejected` (`ValidationError` / library-local `Cancelled`)

**File:** `scripts/ibkr_broker.py:418`, `scripts/ibkr_broker.py:1511`, `scripts/ibkr_executor.py:1154`, `scripts/ibkr_executor.py:1262-1263`, `scripts/ibkr_executor.py:1294-1316`
**Issue:** `ib_async` 2.1.0 `wrapper.error` (`.venv/Lib/site-packages/ib_async/wrapper.py:1609-1638`) sets `trade.orderStatus.status = "ValidationError"` for every *warning* tied to the order id. These are 105, 110, 165, 321, 329, 399, 404, 434, 492, 10167 **and every code 2100-2199**. The library's own comment says: "DO NOT delete the trade object because the order is STILL LIVE at the broker". `OrderStatus.ActiveStates` and `WorkingStates` list `ValidationError` ("PreSubmitted -> ValidationError -> Submitted ... order is still live", `order.py:286-302`). For any *non-warning* error code on the order id, `ib_async` sets the local status to `Cancelled` without any broker confirmation. That includes informational codes such as 10349, and its comment admits the order may still be live.

`_FILL_TERMINAL` treats `ValidationError` as an end state, so `_place_and_wait` stops polling at the first warning. `_classify` then puts `ValidationError`, `Cancelled` and `Inactive` with `filled == 0` into `rejected`, and `_rejected` writes a lifecycle `rejected`. That closes the key with no broker read-back, and `complete` returns, so the run goes on to the next ticker. A market order that keeps working then fills unrecorded:
- The ledger shows `rejected` and no fills, and no alarm is raised.
- From the next run on, `filled_quantity(con_id)` (0) disagrees with `broker_held` (2), so every later decision on that ticker ends as `source-conflict`.
- The ledger cannot be repaired in-tool, because `--resolve` only accepts an `intent`-last entry.

The research doc (Pattern 2) made `ValidationError` terminal to avoid a 60 s hang. That hang would only produce the safe `fill-timeout` alarm. Booking a rejection the broker never confirmed is not safe.

**Fix:**
1. Remove `"ValidationError"` from `_FILL_TERMINAL` and from `REJECT_STATUSES`. A warning should keep the wait going; if no fill arrives, the deadline gives `fill-timeout` (exit 9, entry stays open). Keep the 399 -> `parked` check based on `error_codes`, independent of the status.
2. Before `_rejected` writes `rejected`, confirm it from the broker. Do one `order_history()` read and require the order (by permId/orderRef) in `completed` with status in `{Cancelled, ApiCancelled, Inactive}` and no own executions. Otherwise go to `_fill_timeout`:
```python
if kind == "rejected":
    order, mine = self._read_back(ctx, intent, result)   # or a single history read
    if order is None or order.status not in ledger_mod._CANCELLED or mine:
        self._fill_timeout(ctx, intent, result, f"unconfirmed rejection (local status {result.status!r}); {codes}")
    return self._rejected(ctx, intent, result)
```
3. Change `test_ibkr_execute.py:2795` (`ValidationError` + 321 -> `place-rejected`) to the new expectation.

**Fixed (0321845):** `ValidationError` steht nicht mehr in `_FILL_TERMINAL` und `REJECT_STATUSES`; eine Warnung ohne Fill endet am Deadline als `fill-timeout` (Exit 9), 399 bleibt `parked`. Vor `rejected` liest `LivePlacer._unconfirmed_rejection` nach einer `POST_ORDER_RETRY_S`-Pause die Order-Historie: bestaetigt nur ohne offene Order (permId/orderId/orderRef), ohne Execution und mit abgeschlossener Order (falls vorhanden) in `Cancelled`/`ApiCancelled`/`Inactive` ohne Fill. Sonst, oder wenn die Historie nicht lesbar ist, `fill-timeout` mit "rejection not confirmed by the broker". Tests in `test_ibkr_execute.py`/`test_ibkr_broker.py` angepasst und ergaenzt, Handbuch aktualisiert.

## Warnings

### WR-01: Exceptions after the order is on the wire end as exit 3 with no `alarm`

**File:** `scripts/ibkr_executor.py:1173-1174`, `scripts/ibkr_executor.py:1339-1352`, `scripts/ibkr_executor.py:1966-1976`, `scripts/ibkr_executor.py:971-972`, `scripts/ibkr_broker.py:1592-1599`
**Issue:** `_read_back` calls `order_history()`, which goes through `_read` and raises `GatewayUnavailable` in two cases: a link event, or *any* request-scoped error code that arrives during the read (`_request_error_since`). Order-scoped messages (reqId = orderId, for example 2100-range order warnings or a late 202) land in `_request_errors`. Right after a placement is exactly when they are most likely. The exception escapes `LivePlacer.complete` and passes through `_run_locked` (only a `run_end outcome=error`). `_guarded` then maps it to `EXIT_GATEWAY` (3), the same code as "gateway unreachable before anything was sent". The same applies to a `PLACED` append failure, or to `TimeoutError`/`OSError` after the send, which are `UNEXPECTED` and exit 3. No `alarm` line exists, and the console does not say that an order is out. The next run does reconcile it, so this is not a duplicate risk, but the operator gets the wrong signal.
**Fix:** In `LivePlacer.complete`, after `place_order` returns, wrap the rest in `try/except Exception`. Write `ALARM(state=POST_ORDER_MISMATCH or FILL_TIMEOUT, detail="post-send failure: <exc>")` with an inner `try`, then `raise _ExecuteStop(EXIT_POST_ORDER, ...)`. Also make `order_history` used by `_read_back` ignore request errors whose reqId is the own `order_id`.

**Fixed (dbd0d20):** `LivePlacer.complete` kapselt alles nach `place_order` (`_after_send`, `placed` bleibt der erste Schreibvorgang). Eine unerwartete Exception schreibt best-effort ein `alarm` mit `state: fill-timeout` und `detail: post-send failure (<Typ>): ...` und stoppt mit Exit 9; scheitert der Alarm selbst, wird das geloggt und es bleibt Exit 9. Bewusst nicht umgesetzt: das Ausblenden order-bezogener Request-Fehler in `order_history` (Adapter-Aenderung, nicht Teil des Auftrags); ein solcher Fehler endet jetzt als Alarm mit Exit 9 statt als stilles Exit 3.

### WR-02: `post-order-mismatch` closes the entry, so late executions are never booked

**File:** `scripts/ibkr_executor.py:1395-1403`, `scripts/ibkr_ledger.py:74-75`, `scripts/ibkr_ledger.py:460-473`
**Issue:** `_deviation` writes the "trusted" executions as `filled`/`partial`. Both are lifecycle events outside `OPEN_EVENTS`, so `unresolved()` no longer returns the key, and the next run's reconciliation never looks at it again. Example: status `Filled`, but after 5 s of `_read_back` only one of the two executions is visible. The run writes `partial` for 1 share and an alarm, and the entry is closed. The second execution never reaches the ledger, and `filled_quantity` stays 1 against broker 2, so every later run ends as `source-conflict` with no in-tool fix. This contradicts the `ALARM` docstring (`ibkr_ledger.py:45-47`, "the entry stays open for the reconciliation of the next run").
**Fix:** Write no `filled`/`partial` lines in `_deviation` unless the order is confirmed done *and* the effective executions equal the order's reported filled quantity. Otherwise keep the trusted executions only in the alarm's `seen` and let the next reconciliation write the fills from `fill_records(..., known_exec_ids=...)`. The alternative is to add `ALARM` to the open check in `unresolved()`.

**Fixed (e127653):** `_deviation` schreibt Fill-Zeilen nur noch, wenn `_fills_are_final` gilt: Order beim Broker in einem Endstatus (`_DONE`), `filled` gesetzt und gleich der Summe der effektiven vertrauenswuerdigen Executions. Sonst keine Fill-Zeile; die Executions stehen im Alarm unter `seen.trusted`, der Alarm traegt `fills_booked`, der Eintrag bleibt nach `placed` offen (Exit 10, Laufstopp unveraendert). Nachgewiesen: der Folgelauf (gleicher Tag und spaeterer Tag) bucht beide Executions per `fill_records(..., known_exec_ids=...)` genau einmal, ein dritter Lauf bucht nichts mehr, `filled_quantity == 2`, kein `source-conflict`. Die bestaetigte Teilfuellung (Cancelled, filled 1 == 1 Execution) schreibt weiter `partial` und schliesst. `ALARM`-Docstring und Handbuch angepasst.

### WR-03: A `placed` entry with no broker trace the next day is a permanent exit 6, and `--resolve` refuses it

**File:** `scripts/ibkr_executor.py:1571-1578`, `scripts/ibkr_ledger.py:704-706`, `scripts/ibkr_executor.py:2078-2098`
**Issue:** After `fill-timeout`, `placed` is always written. Say the DAY order then expires unfilled and the next run is on a later day. `reqCompletedOrders` and `reqExecutions` (current session/day) then show nothing, `resolve_entry` returns `no_trace`, and the run ends with exit 6. `run_resolve_entry` refuses anything whose last event is not `intent` (`RESOLVE_NOT_INTENT`, exit 2). The only remaining remedy is editing the append-only ledger by hand. The same time window also cuts the other way: a crash between `placeOrder` and the `placed` write, reconciled only a day later, shows `no_trace`, and the documented remedy `--resolve ...=never_sent` would then book an order that actually filled as "never sent".
**Fix:** Tell the operator (console line at FILL_TIMEOUT, plus the manual) to reconcile on the **same** trading day. Either extend `--resolve` with an outcome for `placed` entries (for example `expired_unfilled`, which needs the operator to confirm in TWS), or check `positions()` before `never_sent` is accepted.

**Fixed (4c692d1):** Beides umgesetzt. `--resolve KEY=expired_unfilled` schliesst einen Eintrag mit letztem Lifecycle-Ereignis `placed` (ein `resolved`-Event, keine Zeile geaendert, Key bleibt verbraucht); `never_sent` bleibt fuer `intent`, jede Variante lehnt den Fall der anderen mit Exit 2 ab (`RESOLVE_NOT_INTENT`/`RESOLVE_NOT_PLACED`). Vor dem Schreiben liest `run_resolve_entry` fuer beide Outcomes read-only Historie und `positions()` (keine neue Adapter-Methode) und verweigert ohne Schreiben: Treffer einer offenen/abgeschlossenen Order oder Execution per orderRef/permId/orderId (orderId nur auf der eigenen conId) -> Exit 6; Broker-Position der conId != signierte effektive Ledger-Fills (`filled_quantity`) -> Exit 6 (`RESOLVE_POSITION_MISMATCH`); Broker nicht lesbar -> Exit 3. Kein neuer Exit/Run-State; neuer Ledger-Wert `expired_unfilled` in `RESOLVE_OUTCOMES`, Executor-Tabelle `RESOLVE_LAST_EVENT` per Test an das Ledger gebunden. Konsolenzeile bei `fill-timeout` fordert Abgleich am selben Handelstag; Handbuch dokumentiert Abgleich, `expired_unfilled` und Broker-Guard. Bewusste Grenze: von Hand in TWS gekaufte Aktien derselben conId loesen den Positions-Guard ebenfalls aus (fail-closed, im Handbuch genannt).

## Info

### IN-01: The `orderId` fallback in `_own` cannot match completed orders

**File:** `scripts/ibkr_executor.py:1326-1330`
**Issue:** When `result.perm_id == 0`, orders are matched by `order_id`. Rows from `reqCompletedOrders` usually carry no orderId (0), so the fallback finds nothing, and the result is a false `post-order-mismatch`. That fails closed, but it raises an alarm.
**Fix:** Fall back to `order_ref == intent["order_ref"]` when `perm_id` is 0, or take `perm_id` from `trade.order.permId` as well.

**Fixed (ea352e9):** Beides. `place_order` nimmt die permId aus `trade.order.permId`, wenn der Status keine traegt. `_own` sucht ohne permId per orderId (nur wenn != 0; vorher passte orderId 0 auf jede Order ohne orderId) oder per `orderRef`; abgeschlossene Orders zuerst. `_unconfirmed_rejection` nutzt bereits `_matches` mit orderRef-Fallback. Tests: Broker-Test fuer die permId aus der Order, Executor-Test (permId 0, completed mit orderId 0) -> sauberer Fill ohne Alarm; beide scheitern ohne den Fix.

### IN-02: `rating_source: null` in `summary.json` aborts the whole run

**File:** `scripts/ibkr_decision.py:216-219`
**Issue:** `_check_type(raw["rating_source"], str, ...)` raises `SummarySchemaError`, which becomes a run-level `_RunAbort(summary-schema)` instead of skipping that one ticker. This fails closed. It only matters if the paper run ever writes `null`.
**Fix:** Optionally treat `None` as missing (engine), or as `rating-jev` per ticker.

**Fixed (2761811):** `null` wird als `RunRecord.rating_source_null` gelesen und endet nur fuer diesen Ticker als `rating-jev` (Detail "rating_source is null in summary.json; not traded", Ledger-Grund `review`); andere Ticker laufen weiter. Fehlender Key bleibt `engine`, andere Nicht-String-Typen bleiben `SummaryContractError`. Kein neuer State. Tests in `test_ibkr_decision.py` und ein Lauf-Test mit zwei Tickern; Handbuch ergaenzt.

### IN-03: The kill path can still cancel the order of an earlier ticker in a `--live` run

**File:** `scripts/ibkr_executor.py:1954-1955`
**Issue:** If KILL appears after ticker 1 was placed and is still open (`fill-timeout` stops the run first, so this needs a clean fill or a rejection), `_kill_path` sends `reqGlobalCancel` at the end of the run. This is the designed behaviour of D-17. It is noted here only because the brief says "cancel must never be called from the live path": that holds for the placer, not for a live run that sees KILL.
**Fix:** None required. Mention it in the runbook for the first order.

**Fixed (75684d9):** Kein Code. Handbuch, Abschnitt "RELEASE and KILL": ein `KILL` waehrend eines `--live`-Laufs sendet am Laufende den globalen Cancel (D-17) und kann eine noch offene Order eines frueheren Tickers zuruecknehmen; "nie stornieren" gilt nur fuer den Placer (D-08).

---

_Reviewed: 2026-10-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
