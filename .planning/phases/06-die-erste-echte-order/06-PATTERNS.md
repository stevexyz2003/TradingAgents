# Phase 6: Die erste echte Order - Pattern Map

**Mapped:** 2026-10-18
**Files analyzed:** 14 (neu/geändert)
**Analogs found:** 13 / 14 (kein Analog nur für den Fill-Warte-Loop; Vorlage steht in RESEARCH Pattern 2)

Alle Zeilenangaben beziehen sich auf den Stand von `main` @ 454f883. Bash/Tests laufen mit `.venv/Scripts/python.exe -m pytest|ruff` (nicht `uv run`).

## File Classification

| Neue/geänderte Datei | Rolle | Data Flow | Nächstes Analog | Match |
|---|---|---|---|---|
| `scripts/ibkr_broker.py` (`_OrderPermit`, `_arm_write_barrier`, `place_order`, `_build_order`) | adapter / middleware (Socket-Sperre) | request-response + Polling | `_CancelPermit` + `cancel_all` (selbe Datei) | exact (Permit), role-match (Fill-Warten) |
| `scripts/ibkr_executor.py` (`LivePlacer`, `--live`, Ledger-Wahl, Frische-Neuprüfung, `--resolve`) | service / CLI | request-response | `DryPlacer` (Z. 1051-1064), `_run_locked` (Z. 1391-1397), `_reconcile` (Z. 1494-1567) | exact |
| `scripts/ibkr_ledger.py` (`exec_family`, `effective_executions`, signiertes `filled_quantity`, `resolved`, `alarm`, `rating_source`) | model (rein) | CRUD / transform | `Ledger.filled_quantity`, `resolve_entry`, `intent_record` (selbe Datei) | exact |
| `scripts/ibkr_guards.py` (neue States, Exit-Codes, Rang) | config / Zustandstabelle | transform | `EXIT_BY_STATE` + `_RUN_EXIT_RANK` (Z. 74-138) | exact |
| `scripts/ibkr_decision.py` (`RunRecord.rating_source`, State `rating-jev`) | model + validation | transform | `RUN_FIELDS`/`read_summary`/`evaluate_decision` (Z. 132-266) | exact |
| `scripts/IBKR_EXECUTION.md` (Zustands-, Exit-, Ledger-Tabellen, `--live`, Read-Only, `--resolve`) | doc (von Test geprüft) | n/a | Abschnitte "States (phase 5)", "Exit codes", "Ledger and reconciliation" | exact |
| `tests/ibkr_fakes.py` (`FakeIB.placeOrder` echt modellieren, Trade-Attrappe) | test-fake | event-driven | `FakeIB.reqGlobalCancel` (Z. 476-482) + `whatIfOrderAsync` (Z. 431-453) | exact |
| `tests/test_ibkr_broker.py` (Order-Permit-Negativkontrollen) | test | request-response | `test_negative_control_global_cancel_refused_without_permit` u. a. (Z. 1606-1758), `_wire_client` (Z. 987) | exact |
| `tests/test_ibkr_ledger.py` (exec_id, signed, resolved) | test | transform | bestehende `filled_qty`-Tests (5 Stellen) | role-match |
| `tests/test_ibkr_execute.py` (`_live_run`, Reihenfolge, Timeout, Mismatch, zweiter Lauf, AST-Aufrufstelle) | test | request-response | `_gateway_run` (Z. 578), `DiskPlacer` (Z. 1072), `_KillingPlacer` (Z. 1311), `test_g3_kill_between_two_orders` (Z. 1425) | exact |
| `tests/test_ibkr_isolation.py` (Methodenmenge, `len(codes)`, Handbuch-Tabellen) | test | n/a | Z. 118-138, 181-192, 406-414 | exact |
| `tests/test_ibkr_guards.py`, `tests/test_ibkr_decision.py` (neue States, `NOT_DRY`-Pin Z. 319) | test | transform | bestehende Tabellen-Tests | role-match |
| `.planning/ibkr-konto-befund.md` (neuer Abschnitt Phase 6) | doc / Messung | n/a | Befund-Abschnitt aus 05-10 | exact |
| `.planning/phases/06-.../06-NN-PLAN.md` (Operator-Checkpoint) | plan (`autonomous: false`) | n/a | `.planning/phases/05-leitplanken-scharf/05-10-PLAN.md` | exact |

## Pattern Assignments

### `scripts/ibkr_broker.py` - `_OrderPermit` + Barrier (adapter, request-response)

**Analog:** `_CancelPermit` / `_arm_write_barrier` / `cancel_all` (selbe Datei).

**Permit-Klasse** (Z. 534-542), zu spiegeln als `_OrderPermit`:
```python
class _CancelPermit:
    """One pass of message 58, opened only by cancel_all after a detected kill switch (D-05)."""
    open: bool = False
    sent: int = 0
```

**Barrier-Signatur und benannte Aufrufe** (Z. 545-586). Heute wirft `guarded_place` bei jedem `placeOrder` ohne `whatIf is True` und STK; hier kommt der Zweig "Permit offen und reine STK-MKT-Order" hinzu, sonst bleibt die `ReadOnlyViolation`:
```python
def _arm_write_barrier(client, permit: _CancelPermit | None = None) -> None:
    permit = permit if permit is not None else _CancelPermit()
    original_place = getattr(client, "placeOrder", None)
    ...
    def guarded_place(*args, **kwargs):
        contract = args[1] if len(args) > 1 else kwargs.get("contract")
        order = args[2] if len(args) > 2 else kwargs.get("order")
        if (
            getattr(order, "whatIf", None) is not True
            or getattr(contract, "secType", None) not in _WHATIF_SEC_TYPES
        ):
            raise ReadOnlyViolation(
                "read-only session: placeOrder without whatIf refused before it reached the gateway"
            )
```

**Feld- und String-Ebene** (Z. 604-635). Das Cancel-Muster `elif msg_id == 58 and permit.open:` ist die Vorlage für `elif msg_id == 3 and order_permit.open and _real_order_in_message(msg)`. Wichtig: Id 3 hängt heute an `_whatif_in_fields`/`_whatif_in_message`; der neue Zweig muss VOR dem `refuse_message(3)` stehen und den whatIf-Fall unberührt lassen:
```python
def guarded_send_msg(msg, *args, **kwargs):
    head = msg.split("\0", 1)[0] if isinstance(msg, str) else None
    msg_id = _message_id(head) if head else None
    if msg_id == 3:
        if not _whatif_in_message(msg):
            refuse_message(msg_id)
    elif msg_id == 58 and permit.open:
        result = original_send_msg(msg, *args, **kwargs)
        permit.open = False
        # Counted as handed to the client; when throttled it may only be queued (IN-02).
        permit.sent += 1
        return result
```
Abweichung vom Vorbild (RESEARCH Pattern 2): das Order-Permit gilt **pro Order**, nicht pro Session (`cancel_all` sperrt mit `if self._permit.sent:`). Es schließt auf der Leitung nach genau einem Durchgang. Zusätzlich Whitelist-Prüfung (STK, MKT, BUY/SELL, `whatIf` nicht True, Konto = `EXPECTED_ACCOUNT`, `orderRef` nicht leer, `tif == "DAY"`, ganzzahlige Menge > 0). String-Indizes (ib_async 2.1.0, gemessen in RESEARCH): `[0]=="3"`, secType `[4]`, action `[16]`, Menge `[17]`, orderType `[18]`, tif `[21]`, account `[23]`, orderRef `[26]`, whatIf `[84]`. Als Konstanten wie `_PO_*` (Z. 77-83) im Adapter ablegen.

**Aufrufer-Muster `cancel_all`** (Z. 1224-1258): Evidenz-/Vorbedingungsprüfung, `permit.open = True`, Aufruf in `try`, `finally: open = False`, danach `sent`-Prüfung und Log `ibkr-state=...`:
```python
        if self._ib is None or self._handles is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        if getattr(kill_evidence, "active", False) is not True:
            raise ReadOnlyViolation("global cancel needs a positively detected kill switch")
        ...
        self._permit.open = True
        try:
            self._ib.reqGlobalCancel()
        except ConnectionError as exc:
            raise GatewayUnavailable(
                "NOT_CONNECTED", 504, f"global cancel not sent ({type(exc).__name__})"
            ) from exc
        finally:
            self._permit.open = False
        if self._permit.sent != 1:
            raise GatewayUnavailable(
                REQUEST_FAILED, None, "global cancel did not reach the wire exactly once"
            )
```

**`_build_order` herausziehen** aus `preview_order` (Z. 1117-1125), damit whatIf und echte Order identisch gebaut werden:
```python
order_kwargs = {"orderRef": order_ref} if order_ref else {}
order = handles.order(
    action=action, totalQuantity=quantity, orderType="MKT",
    tif=PREVIEW_TIF, account=EXPECTED_ACCOUNT, **order_kwargs,
)
```

**Pre-Checks / Fail-Closed beim Senden** aus `preview_order` (Z. 1094-1108, 1153-1158): `ValueError` für `action`/`quantity`, `GatewayUnavailable("NOT_CONNECTED")`, `_open_link()` vor dem Senden, `mark = len(self._link_codes)` und `_link_event_since(mark)` nach dem Warten (Antwort bei Link-Ereignis verwerfen).

**Fill-Warten (kein Analog):** Vorlage in RESEARCH "Pattern 2" (`_place_and_wait`, Polling alle 0,1 s, `_TERMINAL` inkl. `ValidationError`; Frist gibt den `Trade` zurück statt `TimeoutError`; kein `cancelOrder`). `ib.placeOrder` muss innerhalb der laufenden Coroutine in `self._call(...)` laufen, wie `whatIfOrderAsync` in `preview_order` Z. 1143.

**Öffentliche Methode Nr. 10:** `place_order` (Name frei). Das Warten bleibt privat darin; `test_adapter_has_at_most_ten_public_methods` (isolation Z. 118-138) wird auf die neue Menge aktualisiert, das Limit 10 bleibt.

---

### `scripts/ibkr_executor.py` - `LivePlacer`, `--live`, Ledger-Wahl (service, request-response)

**Analog:** `DryPlacer` (Z. 1051-1064).
```python
class DryPlacer:
    """The phase-5 placer: completes an intent on paper and never contacts the broker."""
    dry = True

    def complete(self, ctx, intent: dict) -> str:
        ctx.ledger.append(
            ctx.mods.ledger.DRY_COMPLETE,
            decision_key=intent["decision_key"],
            ticker=intent["ticker"],
        )
        return ctx.mods.guards.DRY_COMPLETE
```
`LivePlacer.dry = False`; Signatur `complete(self, ctx, intent) -> str` NICHT ändern (Test-Placer `ReadingPlacer`, `DiskPlacer`, `_KillingPlacer` überschreiben sie). Symbol/secType/currency/primary_exchange per `ctx.placing` unmittelbar vor `ctx.placer.complete(...)` (Z. 2275) setzen. Rückgabe ist ein State-Name; `_finish_row(ctx, row, state, ...)` folgt in Z. 2276.

**Argparse** (Z. 790-796): Kommentar "No live, release or date option (D-07)" aktualisieren und ergänzen:
```python
execute = sub.add_parser("execute", help=help_execute)
execute.add_argument("tickers", nargs="*", metavar="TICKER")
execute.add_argument("--contracts", type=Path, default=None, help="contracts.json path")
```
Neu: `--live` (`action="store_true"`), für `--resolve KEY=never_sent` (D-14) ein Flag `--resolve` plus `--note` (Muster `--rebaseline TICKER` in `resolve`, Z. 776, und Validierung Z. 842).

**Placer-Wahl** (Z. 1094): `placer = DryPlacer() if placer is None else placer` -> `LivePlacer() if args.live else DryPlacer()`.

**Modus-Abgleich** (Z. 1161-1168), die zu ersetzende Stelle, bleibt vor jeder Dateiberührung:
```python
    if EXECUTE_FORCED_DRY and getattr(placer, "dry", None) is not True:
        return _fail(
            logger,
            EXIT_CONFIG,
            "ibkr-state=NOT_DRY the placer is not dry",
            "phase 5: execute is forced dry",
        )
```
Neu in beide Richtungen: ohne `--live` muss `placer.dry is True` (State `not-dry`, besteht), mit `--live` muss `placer.dry is False` (neuer State `not-live`, Exit 1). `EXECUTE_FORCED_DRY` (Z. 129-131) entfällt; Docstring-Kopf (Z. 31) anpassen.

**Ledger-Ziel je Modus** (Z. 1391-1397), Lock bleibt immer `ledger.jsonl.lock`:
```python
        ctx.ledger = ledger_mod.Ledger.open(
            default_dryrun_ledger_file(),
            mode=ledger_mod.MODE_DRYRUN,
            clock=clock,
            run_id=uuid.uuid4().hex,
        )
```
`default_ledger_file()` / `MODE_LIVE` bei `args.live` (Funktionen liegen bei Z. 275 bzw. daneben).

**Frühausstieg für Erfolgs-/Placer-States** (Z. 1124-1125) in `_ledger_row_finished`; jeder neue State, den der Placer selbst im Ledger vermerkt (`order-filled`, `fill-timeout`, `post-order-mismatch`, `place-rejected`), muss hier wie `DRY_COMPLETE` früh zurückkehren, sonst entsteht eine falsche `skipped/review`-Zeile (Fallback Z. 1148-1150, `LEDGER_REASON_UNMAPPED`):
```python
    if state == guards.DRY_COMPLETE:
        return  # the placer wrote ``dry_complete`` already
```

**Lauf-Stopp** (Muster Z. 2181 und Fangstelle Z. 1450-1451):
```python
        raise _ExecuteStop(EXIT_ACCOUNT_GUARD, guards.ACCOUNT_CONFLICT, reason)
...
        except _ExecuteStop as stop:
            abort_code, stop_state = stop.code, stop.state
```
`fill-timeout` und `post-order-mismatch` beenden den Lauf genauso (D-08/D-09); vorher `alarm`-Ledgerzeile (neues nicht-lifecycle Event), `intent`/`placed` bleiben offen.

**Frische-Neuprüfung vor dem `intent`** (WR-05-Rest). Direkt neben der bestehenden Fenster-Neuprüfung (Z. 2231-2240), vor `intent_record`:
```python
    now = ctx.clock()
    if result.window is None or not contracts_mod.window_open(result.window, now):
        detail = (...)
        _finish_row(ctx, row, guards.OUTSIDE_SESSION, detail)
        return
```
Ergänzen: `ctx.mods.decision.freshness(ctx.mods.decision.parse_trade_date(row["trade_date"]), now, ctx.calendar)`; `fresh.state != "fresh"` -> `_finish_row(ctx, row, fresh.state, fresh.detail)`; `return`. Aufruf-Muster von `freshness` siehe `_local_chain` Z. 1857-1868.

**`intent_record` mit `rating_source`** (Z. 2241-2252): `rating_source=row["rating_source"]` ergänzen; `"rating_source"` in `_ROW_KEYS` (Z. 1661-1671) aufnehmen und in `_local_chain` (Z. 1843-1845) setzen. Bestehender Test pinnt `assert intent["rating_source"] is None` (test_ibkr_execute.py Z. 660) und muss auf `"engine"` angepasst werden.

**Reconciliation / Fill-Menge** (Z. 1483-1491, 1494-1567): `_fill_quantity` summiert heute `float(e.shares)` unkorrigiert und unsigniert; auf `effective_executions` umstellen. Der Folgelauf nach `fill-timeout` läuft über dieselbe `_reconcile`-Schleife; kein zweiter Codepfad:
```python
def _fill_quantity(entry: dict, history) -> float:
    key = entry.get("order_ref") or entry["decision_key"]
    shares = sum(float(e.shares) for e in history.executions if e.order_ref == key)
    if shares:
        return shares
    return sum(float(o.filled) for o in history.completed if o.order_ref == key and o.filled is not None)
```

**`--resolve KEY=never_sent` (D-14)** hängt als neues Event `resolved` an die Reconcile-Struktur (Z. 1541-1546, `NEVER_SENT`-Zweig schreibt `REJECTED, state="never-sent"`). Das Handbuch verspricht es an Z. 662; `test_handbook_documents_resolve` (isolation Z. 196-208) ist die Vorlage für einen neuen Handbuch-Test.

---

### `scripts/ibkr_ledger.py` (model, transform)

**Event-Tabellen** (Z. 33-65): neues Event `RESOLVED` (lifecycle, schließt einen offenen Eintrag wie `REJECTED`) und `ALARM` (nicht-lifecycle) in `EVENTS` und ggf. `LIFECYCLE_EVENTS` eintragen:
```python
LIFECYCLE_EVENTS = frozenset({INTENT, PLACED, FILLED, PARTIAL, REJECTED, DRY_COMPLETE})
OPEN_EVENTS = frozenset({INTENT, PLACED})
```
`unresolved()` (Z. 425-438) prüft `tail[-1]["event"] in OPEN_EVENTS`; ein `resolved` als letztes Lifecycle-Event schließt den Eintrag ohne weitere Änderung.

**Grund-Tabellen** (Z. 87-160): `rating-jev` -> `"review"` in `REASON_BY_STATE` (neben `rating-review`); Placer-eigene Ablehnung `place-rejected` in `REJECTED_STATES` (disjunkt halten). `REASONS` (Z. 69-84) braucht keinen neuen Grund (D-06: `review`).

**Schema** (Z. 228-233): `side` für `filled`/`partial` verlangen (WR-07), `exec_id`/`price` optional prüfen:
```python
    if event in (FILLED, PARTIAL):
        filled = record.get("filled_qty")
        if filled is not None and (not _is_number(filled) or filled < 0):
            return f"has filled_qty {filled!r}"
        if "con_id" in record and not _is_int(record["con_id"]):
```

**`filled_quantity` ersetzen** (Z. 440-447), heute unsigniert und ohne Korrektur:
```python
    def filled_quantity(self, con_id: int) -> float:
        return float(sum(float(r.get("filled_qty") or 0) for r in self.records
                         if r["event"] in (FILLED, PARTIAL) and r.get("con_id") == con_id))
```
Neu: je `decision_key` `exec_id`-Zeilen nach `exec_family` gruppieren, höchste Korrektur je Familie, `+` BUY / `-` SELL; Aggregatzeilen ohne `exec_id` nur, wenn der Key keine `exec_id`-Zeilen hat (Pitfall 5).

**Reine Funktionen** `exec_family`, `correction_rank`, `effective_executions`: Code steht in RESEARCH Pattern 3. Modul bleibt frei von Client-Bibliothek und Uhr (`test_new_modules_are_pure`, isolation Z. 417-441). `resolve_entry` Z. 554 (`shares = sum(float(e.shares) for e in executions)`) auf `effective_executions` umstellen; die Kollisionsprüfung Z. 543-545 (`con_id`/`side`) bleibt, sie fängt Familien mit abweichender Seite ab.

**`intent_record`** (Z. 450-477): Docstring "``rating_source`` stays ``None`` (D-23)" aktualisieren; Feld wird mit `engine`/`jev` befüllt.

---

### `scripts/ibkr_guards.py` (config, Zustandstabelle)

**Muster** (Z. 52-58, 62-72, 74-105): State-Konstante, Exit-Code-Spiegel, Eintrag in `EXIT_BY_STATE`, Rang:
```python
NOT_DRY = "not-dry"
(_EXIT_OK, _EXIT_CONFIG, _EXIT_PRECONDITION, _EXIT_GATEWAY, _EXIT_KILL_SWITCH,
 _EXIT_REJECTED, _EXIT_RECONCILE, _EXIT_LOCKED, _EXIT_ACCOUNT_GUARD) = (0, 1, 2, 3, 4, 5, 6, 7, 8)
...
        **dict.fromkeys((STATE_IN_GIT_TREE, NOT_DRY), _EXIT_CONFIG),
```
Neue States (Vorschlag RESEARCH, Ermessen): `ORDER_FILLED="order-filled"` (0), `NOT_LIVE="not-live"` (1), `PLACE_REJECTED="place-rejected"` (5), `FILL_TIMEOUT="fill-timeout"` (neuer Exit 9), `POST_ORDER_MISMATCH="post-order-mismatch"` (neuer Exit 10). Jeder neue Exit-Code muss in `_RUN_EXIT_RANK` (Z. 114-129; sonst `KeyError` in `worst_run_exit`, Z. 132-138), im Docstring-Kopf des Executors (`EXIT_*`-Konstanten), in der Handbuch-Exit-Tabelle und im Rangsatz des Handbuchs stehen. Der Kommentar Z. 107 (Rangreihe) wird mitgepflegt.

---

### `scripts/ibkr_decision.py` (Jev-Abgleich, D-05/06/07)

**Analog:** `RUN_FIELDS`, `RunRecord`, `read_summary`, `evaluate_decision`.

`RUN_FIELDS` (Z. 132-134) und `RunRecord` (Z. 148-152) kennen nur `ticker/status/signal`; `rating_source` fehlt in `summary.json`, wenn Jev nicht aktiv war (RESEARCH Pattern 5, A1). Daher **optionales** Feld, nicht in `RUN_FIELDS` (sonst `missing field` für jeden Lauf):
```python
RUN_FIELDS = MappingProxyType({"ticker": str, "status": str, "signal": (str, type(None))})
...
        for name, expected in RUN_FIELDS.items():
            if name not in raw:
                raise SummaryContractError(f"runs[{i}]: missing field {name!r}")
            _check_type(raw[name], expected, f"runs[{i}].{name}")
```
`_check_type` (Z. 173-179) für den optionalen Wert wiederverwenden; fehlendes Feld => `engine`; unbekannter Wert (weder `engine` noch `jev`) => fail-closed.

`evaluate_decision` (Z. 237-266): neuer Zweig nach der Hold-Prüfung und vor `return verdict(EXECUTABLE)`:
```python
    if rating == "Hold":
        return verdict(SKIPPED_HOLD, "skipped: hold")
    return verdict(EXECUTABLE)
```
Neuer State `RATING_JEV = "rating-jev"` (Exit 2) wird an drei Stellen geführt: `EXIT_BY_STATE` (Z. 90-117, Muster `RATING_REVIEW_STATE` Z. 36 und 74/94), `REASON_BY_STATE` im Ledger, Handbuch-Phase-4-Tabelle (`test_handbook_state_table_matches_decision_module`, isolation Z. 510). D-06 (fehlende/kaputte `summary.json`) ist durch `summary-missing`/`summary-schema`/`summary-contract` schon erfüllt: nur testen.

---

### `tests/ibkr_fakes.py` - `FakeIB.placeOrder` (test-fake, event-driven)

**Analog:** `FakeIB.reqGlobalCancel` (Name, dann Leitung) und `whatIfOrderAsync` (Z. 431-453), `_record` (Z. 323-332).

```python
    def reqGlobalCancel(self):
        # Models the library: the named call first, then message 58 on the wire.
        self.client.reqGlobalCancel()
        self.client.sendMsg("58\0" + "1\0")
        self._emit_during("global_cancel")
        if self.global_cancel_clears:
            self.open_orders = []
```
Heute steht `FakeIB.placeOrder` bei Z. 507-508 als `_forbidden("placeOrder")` (wirft `AssertionError` und zeichnet `"placeOrder"` auf). Neu: echten Aufruf modellieren (Name über `self.client.placeOrder(...)` aufzeichnen, dann `client.sendMsg("3\0...")`), `Trade`-artigen Rückgabewert (`SimpleNamespace` wie `open_trade` Z. 138-162 mit veränderlichem `orderStatus.status/filled/avgFillPrice/permId`, `order`, `fills`) liefern; Steuerparameter im Konstruktor (Filled / bleibt Submitted / `ValidationError`), Fills in `self.executions` einspeisbar. `_record` unterscheidet whatIf (`"placeOrder(whatIf)"`) von echter Order (`"placeOrder"`): so bleibt "`"placeOrder" not in fake.calls`" der exakte Beweis. `fill(...)` (Z. 193-219) hat `exec_id`-Parameter für das `.01`->`.02`-Fixture. Ein Selbstkonsistenz-Test für die Attrappe gehört dazu (Wave 0 in RESEARCH).

---

### `tests/test_ibkr_broker.py` - Order-Permit-Negativkontrollen (test, request-response)

**Analog:** Z. 1606-1672 (Cancel-Permit gegen die echte Client-Klasse) und `_wire_client`/`_stock_and_order` (Z. 987-1008).

```python
def test_negative_control_global_cancel_refused_without_permit():
    ib_async = pytest.importorskip("ib_async")
    client = ib_async.IB().client
    permit = broker._CancelPermit()
    broker._arm_write_barrier(client, permit)
    with pytest.raises(broker.ReadOnlyViolation, match="reqGlobalCancel"):
        client.reqGlobalCancel()
    with pytest.raises(broker.ReadOnlyViolation, match="message 58"):
        client.send(58, 1)
    ...
    assert permit.sent == 0
```
```python
@pytest.mark.parametrize("msg_id", (4, 19, 21))
def test_global_cancel_open_permit_keeps_the_other_write_messages_shut(msg_id): ...
def test_global_cancel_counts_only_on_the_wire(): ...   # sent=0 nach send(), 1 nach sendMsg()
```
Für `_OrderPermit` spiegeln: geschlossen -> `ReadOnlyViolation`; offen -> genau eine STK-MKT geht auf die Leitung (`sent` 1, `open False`); Limit/Nicht-STK/falsches Konto/leere `orderRef`/`whatIf=False` mit LMT -> refused; zweite Order ohne neues Öffnen -> refused; Id 4/19/21/58 bleiben bei offenem Order-Permit zu. Layout-Pin gegen die echte Client-Klasse mit `_wire_client`:
```python
    assert parts[0] == "3"
    assert parts[4] == "STK"
    assert parts[16] == "BUY" and parts[21] == "DAY"
    assert parts[84] == "1"  # whatIf, after the 12-field contract expansion
```
(Z. 1026-1030; bei echter Order `parts[84] == "0"`, dazu Indizes 17/18/23/26.) Die Adapter-Tests `test_cancel_all_*` (Z. 1677-1741) sind die Vorlage für `place_order`-Tests mit `_connected(fake, loop)`; `test_global_cancel_in_the_fake_model_is_name_then_wire` (Z. 1751) für die Attrappen-Konsistenz.

---

### `tests/test_ibkr_execute.py` (test, request-response)

**Analog:** `_gateway_run` (Z. 578-606), `_fake_for` (Z. 558), `DiskPlacer` (Z. 1072-1078), `ReadingPlacer` (Z. 684-687), `_KillingPlacer` (Z. 1311), `test_g3_kill_between_two_orders` (Z. 1425).

`_gateway_run(tmp_path, loop, fake, *, rating, tickers, paper, clock, calendar, placer, release, kill)` reicht an `_run_execute(...)` durch. Neue Hilfsfunktion `_live_run(...)` daneben: gleiche Signatur plus `live=True` (Flag `--live` in argv), `release=True`, injizierbare Uhr/`sleep` für den 60-s-Timeout. Beweis "intent vor placeOrder auf Platte": in der Attrappe beim echten `placeOrder` die Ledger-Datei lesen (Muster `ReadingPlacer`):
```python
        class ReadingPlacer(executor.DryPlacer):
            def complete(self, ctx, intent):
                seen.append(_read_records(executor.default_dryrun_ledger_file()))
                return super().complete(ctx, intent)
```
Ereignisfolge-Assertion nach dem Muster von `test_the_run_is_framed_by_run_start_and_run_end` (Z. 670-679): `["run_start","switch_check","intent","placed","filled","run_end"]` im Live-Ledger. Bestehende Tests, die `intent["rating_source"] is None`, `not executor.default_ledger_file().exists()` (Z. 667) oder `NOT_DRY` (Z. 312/330) pinnen, sind betroffen (Pitfall 11).

Negativkontrollen: whatIf-Reject im `--live`-Pfad per `FakeIB(whatif=..., emit_during={"whatif": [(reqId, code, text, None)]})` (kein `rejectReason`, Pitfall 6) -> Exit 5, `"placeOrder" not in fake.calls`. AST-Test "`place_order` nur in `LivePlacer.complete`" nach dem Muster der AST-Tests in `test_ibkr_isolation.py` (Z. 95-115, 118-138).

---

### `tests/test_ibkr_isolation.py` (test)

**Methodenmenge** (Z. 118-138): `public == {...}` um `place_order` erweitern, `<= 10` bleibt.
**Exit-Konstanten** (Z. 181-192): `assert len(codes) == 10` auf die neue Zahl (bei zwei neuen Codes 12) anheben; jede Zeile `| N | `EXIT_X` |` im Handbuch:
```python
    assert len(codes) == 10
    for name, value in codes.items():
        assert re.search(rf"^\| {value} \| `{name}` \|", text, re.M), f"{name}={value} not in table"
```
**State-Tabelle** (Z. 406-414): jeder State in `guards.EXIT_BY_STATE` braucht `| `state` | code |` im Handbuch:
```python
    for state, code in guards.EXIT_BY_STATE.items():
        assert re.search(rf"^\| `{re.escape(state)}` \| {code} \|", text, re.M)
```
`test_handbook_documents_execute` (Z. 379-403) prüft Schlüsselwörter: `--live`, `--resolve` und neue States ergänzen. Die Guards/Ledger-Module bleiben rein (Z. 417-441).

---

### `scripts/IBKR_EXECUTION.md` (doc)

Zu ändern, weil Tests sie lesen: Exit-Tabelle (Z. 128-143, neue Zeilen im Format `| 9 | `EXIT_FILL_TIMEOUT` | ... |`), "States (phase 5)" (Z. 664-693; Zeile `not-dry` Z. 671 "phase 5 refuses to run" umformulieren, neue Zeilen `not-live`, `order-filled`, `fill-timeout`, `post-order-mismatch`, `place-rejected`), Phase-4-Tabelle (`rating-jev`), Ledger-Abschnitt (Z. 599-662: Events-Liste um `resolved`, `alarm`; Satz Z. 662 "A `--resolve` flag ... comes with phase 6" ersetzen; Z. 601-603 "from phase 6"), Rangsatz, Abschnitt "Gateway Read-Only switch" (Z. 38: Einträge des Messtags ein/aus mit Datum und Grund, D-04/D-11/D-15), neuer Abschnitt "First live order". Z. 596 "the order status 399 joins in phase 6" -> D-16 (nur Fake-Test, Lücke wie `halted`). Der Handbuchtext darf den Namen der Client-Bibliothek nicht enthalten (`test_handbook_does_not_name_the_client_library`, Z. 176-178).

---

### Operator-Checkpoint-Plan (`06-NN-PLAN.md`, `autonomous: false`)

**Analog:** `05-10-PLAN.md`. Übernehmen:

- Frontmatter: `phase`, `plan`, `type: execute`, `wave` (letzte), `depends_on`, `files_modified: [.planning/ibkr-konto-befund.md]` (plus Handbuch), `autonomous: false`, `requirements: [...]`, `must_haves.truths/artifacts/key_links`.
- Task-Abfolge: Task 1 `checkpoint:human-action` (`gate="blocking"`; Agent fährt vorher Suite `.venv/Scripts/python.exe -m pytest -q`, `ruff check .` SELBST, prüft State-Ordner auf `KILL`/`RELEASE`, fragt den Operator statt zu löschen), Task 2 `type="auto"` (Messungen und Befundabschnitt, "Rohausgabe in Codeblöcken, UTC-Uhrzeit", Haltepunkt bei unerwarteten offenen Orders), Task 3 `checkpoint:human-verify` (Operator-Abnahme mit `resume-signal`).
- `<how-to-verify>` nummeriert; `<acceptance_criteria>` mit grep-prüfbaren Aussagen (z. B. `grep -c "## ...(Phase 6" .planning/ibkr-konto-befund.md` == 1) und "im State-Ordner liegen danach weder `KILL` noch `RELEASE`".
- Regel "Weicht eine Messung ab: keinen Code ändern, Abweichung als Lücke benennen" (Threat T-05-57).
- `<threat_model>` mit STRIDE-Tabelle; `<output>` = SUMMARY.
- Befehle: `.venv/Scripts/python.exe scripts/ibkr_executor.py execute AAPL --live`, `.venv/Scripts/python.exe scripts/smoke/ibkr_order_probe.py --history`; `RELEASE`-Einzeiler wörtlich aus dem Handbuch (§ "RELEASE and KILL"; UTF-8 ohne BOM, sonst `release-invalid`); Log `%LOCALAPPDATA%\TradingEngineX\ibkr\logs\ibkr_executor.log`, Ledger `...\ledger.jsonl`.
- Phase-6-spezifisch (CONTEXT Specifics, D-11/D-15): Read-Only AN -> `execute <T> --live` endet als `preview-read-only`, Exit 5, kein `intent` (321-Beleg am whatIf); Read-Only AUS und Handbucheintrag; echte Order; `--history` sichern (Rohform `execId`, `orderRef`, `permId`; Fixture-Material D-13); zweiter Lauf -> `already-attempted`; Timeout ist gültiges Ergebnis (D-08), kein Storno durch den Agenten.
- Befund-Muster: Abschnitt "Messung 1/2/3 ... Folgen ... Abnahme" in `.planning/ibkr-konto-befund.md`; der Commit enthält nur die Befund- und Handbuchdatei.

---

## Shared Patterns

### Neue Zustände an drei Stellen führen
**Quelle:** `scripts/ibkr_guards.py` Z. 74-105, `scripts/ibkr_ledger.py` Z. 87-160, `scripts/IBKR_EXECUTION.md` Z. 664-693.
**Gilt für:** jeden neuen State (`order-filled`, `not-live`, `place-rejected`, `fill-timeout`, `post-order-mismatch`, `rating-jev`).
Gate-Tests: `test_handbook_state_table_matches_guards_module` / `..._decision_module`, `test_handbook_exit_table_matches_executor`, Fallback `LEDGER_REASON_UNMAPPED` im Executor (Z. 1148-1150).

### Einmal-Permit (Schreiböffnung)
**Quelle:** `scripts/ibkr_broker.py` Z. 534-635, 1224-1258.
**Gilt für:** `_OrderPermit` und `place_order`. Immer: `open` nur im `try`, `finally: open = False`, Zählung auf der Leitung (`sendMsg`), Prüfung `sent` nach dem Aufruf, Negativkontrolle gegen `ib_async.IB().client` und `_wire_client`, AST-Test pinnt Aufrufstellen.

### Write-ahead Ledger
**Quelle:** `scripts/ibkr_executor.py` Z. 2265-2276.
`ctx.ledger.append(ledger_mod.INTENT, **intent)` (fsync) vor `ctx.placer.complete(ctx, intent)`; danach nichts mehr, das die Order verweigern darf (zweiter Größencheck Z. 2253-2264 steht davor).

### Fail-closed Lauf-Ende mit eigenem Exit
**Quelle:** `_ExecuteStop` (Z. 1041-1048), Fangstelle Z. 1450-1451, `worst_run_exit` (guards Z. 132-138), `RUN_END` mit `state` (Z. 1469-1472).

### Tests
**Quelle:** `tests/conftest.py` setzt `LOCALAPPDATA` je Test auf tmp; Fakes in `tests/ibkr_fakes.py`; Marker `unit`. Lauf: `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q`, Lint: `.venv/Scripts/python.exe -m ruff check scripts tests`. Bekannt rot vorab: `test_yfinance_keeps_its_cache_out_of_the_users_home`.

## No Analog Found

| Datei / Teil | Rolle | Data Flow | Grund |
|---|---|---|---|
| Fill-Warte-Loop in `IbkrBroker.place_order` (Polling auf `Trade.orderStatus`, 60 s, `ValidationError` terminal) | adapter | polling | Bisher nur synchrone Einzel-Requests (`_read`/`_request`/`_call`); Vorlage ist RESEARCH Pattern 2. Struktur von `_call(make_awaitable, timeout)` (Z. 1336) und `_link_event_since` wiederverwenden. |

## Metadata

**Analog-Suchbereich:** `scripts/` (broker, executor, ledger, guards, decision, Handbuch), `tests/` (fakes, broker, execute, isolation), `.planning/phases/05-leitplanken-scharf/05-10-PLAN.md`
**Gelesene Dateien:** 12 (teils gezielt per Zeilenbereich)
**Extraktionsdatum:** 2026-10-18
