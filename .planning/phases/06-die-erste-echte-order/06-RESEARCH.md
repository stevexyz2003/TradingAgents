# Phase 6: Die erste echte Order - Research

**Researched:** 2026-10-18
**Domain:** IBKR-Paper-Ausführung (brownfield Python): `execute --live`, echter Placer, Fill-Warten, `execId`-Korrektur, Ledger, Socket-Sperre
**Confidence:** HIGH für alles, was aus dem Code und dem installierten `ib_async 2.1.0` gelesen wurde; MEDIUM für das Verhalten des Gateways bei echten Fills (noch nie gemessen)

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Scharf wird `execute` über ein **Flag `--live` pro Lauf**. Ohne das Flag bleibt jeder Lauf trocken und schreibt nur nach `ledger-dryrun.jsonl`. Mit `--live` schreibt er nach `ledger.jsonl` und platziert. Eine gültige `RELEASE` ist weiterhin Pflicht, und `KILL` gewinnt weiterhin. Die Konstante `EXECUTE_FORCED_DRY` wird zum Default „trocken, solange `--live` fehlt"; ein globales Umschalten im Code gibt es nicht.
- **D-02:** Die allererste echte Order löst Claude **von Hand** aus (`execute --live`), während der Operator TWS bzw. Gateway beobachtet. Das passiert an einem Handelstag im Sitzungsfenster, als Checkpoint-Plan nach dem Muster von 05-10. Der Operator nimmt den Fill direkt ab.
- **D-03:** Die erste Order kommt aus dem, was der Paper-Log am Tag hergibt: die jüngste frische Entscheidung, die eine BUY-Order ergibt. Ein Ticker genügt. Gibt es am Tag keine solche Entscheidung, wird nicht künstlich eine erzeugt.
- **D-04:** „Read-Only API" bleibt nach der Freischaltung **aus**. Geschützt wird über `RELEASE` und `KILL`. Wer den Schalter wieder einschaltet, tut das bewusst und notiert es im Betriebshandbuch.
- **D-05:** Der Executor gleicht jede Entscheidung mit `runs/<date>/summary.json` → `record.rating_source` ab (Weg b aus dem Todo). Steht dort `jev`, endet der Ticker als `skipped` und wird nicht gehandelt. Das Log-Format von `decision-log.md` (`tradingagents/memory/log.py`, eine Upstream-Datei) bleibt unverändert.
- **D-06:** Fehlt `summary.json` oder ist sie nicht lesbar, gilt **fail-closed**: der Ticker wird `skipped` mit Grund `review`. Es gibt keinen Nachweis für ein Engine-Rating, also wird nicht gehandelt (Prinzip „positiver Nachweis").
- **D-07:** Das in Phase 5 vorgesehene Ledger-Feld `rating_source` wird **befüllt** (`engine` bzw. `jev`), damit der Ledger nachweist, woher eine Entscheidung kam.
- **D-08:** Nach dem Platzieren wartet der Lauf **bis zu 60 s** auf den Fill. Bleibt die Order länger offen, endet der Lauf mit eigenem Zustand und eigenem Exit (ein Alarm). Die Order bleibt bestehen und wird **nicht** storniert. Der nächste Lauf gleicht sie per Reconciliation ab. Eine zweite Schreiböffnung (`cancelOrder`) gibt es nicht.
- **D-09:** Weicht die Kontrolle nach der Order (Status, Stückzahl, `orderRef`, REQ-65) von der Absicht ab, endet der **ganze Lauf** mit eigenem Zustand (etwa `post-order-mismatch`) und Ledger-Eintrag. Weitere Ticker desselben Laufs werden nicht mehr platziert.
- **D-10:** Executions und abgeschlossene Orders werden **im selben `execute`-Lauf** direkt nach der Fill-Bestätigung persistiert: `filled`/`partial` je `execId` ins Ledger, mit Dedup und Korrekturregel (REQ-47). Ein eigenes Subkommando `sync` gibt es in dieser Phase nicht.
- **D-11:** Fehler 321 wird **am Tag der ersten Order frisch gemessen**. Der Operator schaltet Read-Only ein, `execute --live` scheitert beim Platzieren mit 321, dann schaltet der Operator Read-Only aus. Datum, Grund und Vorher/Nachher kommen ins Betriebshandbuch, und erst danach folgt die echte Order. Die whatIf-Messung aus Phase 4 (D-14) allein reicht nicht.
- **D-12:** **Klarstellung zu Roadmap-SC7:** Der whatIf-Reject im scharfen Pfad wird per **Fixture und Stub-Broker** nachgewiesen. Der Stub liefert einen whatIf mit `rejectReason`, der Lauf endet mit Exit 5 und ruft `placeOrder` nicht auf. Ein echter IBKR-Reject am Konto wird nicht provoziert (eigene Leitplanke `MAX_QTY_PER_ORDER = 2` stoppt schon vor dem whatIf). Bewusste Abweichung vom Roadmap-Wortlaut; die Verifikation soll sie nicht als Lücke werten.
- **D-13:** Die `execId`-Korrektur (SC5) wird gegen echte Daten belegt, falls eine Korrektur auftritt. Sonst dient ein Fixture aus der gemessenen Rohform von Executions und abgeschlossenen Orders (Befund 2026-10-17 plus erster echter Fill) mit einer künstlichen Korrektur `.01` → `.02`.

### Claude's Discretion

- Namen und Exit-Codes der neuen Zustände (Fill-Timeout, Abweichung nach der Order), solange sie in `EXIT_BY_STATE`, der Ledger-Grund-Tabelle und dem Handbuch konsistent sind (der Isolationstest prüft das).
- Wie die Schreiböffnung für `placeOrder` in der Socket-Sperre gebaut wird. Sie folgt dem Muster des Einmal-Permits von `cancel_all` aus 05-03: genau eine Stelle, nur im `--live`-Pfad, mit Negativ-Kontrollen gegen die echte Client-Klasse.

### Deferred Ideas (OUT OF SCOPE)

- Gezieltes Stornieren einer nicht gefüllten Order (`cancelOrder` als zweite Schreiböffnung) wurde verworfen (D-08). Falls nötig, später als eigene Phase oder in Phase 7.
- Subkommando `sync` als Nachholpfad für die Tageshistorie (D-10). Kandidat für Phase 7 (Rückkanal).
- Kill-Grenze aus Phase 5: Erscheint `KILL` erst nach einem Halt wegen ungültiger Freigabe, storniert erst der Folgelauf. Wird bewusst nicht in Phase 6 geändert.

Nicht in dieser Phase (aus Domain/Roadmap): kein Scheduler, kein Push, kein Heartbeat, kein Soll-Ist-Bericht, keine Limit-Order, kein zweiter Ticker als Pflicht, keine Ausweitung der Leiter oder der Blockgröße (`MAX_QTY_PER_ORDER = 2` bleibt).

### Folded Todos

- WR-07 (vorzeichenbehaftete Fills) plus WR-05-Rest (Frische-Prüfung mit `ctx.clock()` direkt vor dem `intent`): Pflicht vor der ersten echten Order.
- Jev-Fallback-Ratings: wird mit D-05 bis D-07 umgesetzt.

## Project Constraints (from CLAUDE.md)

- Graphify und Serena sind nur Navigations-Werkzeuge, kein Build- oder Merge-Gate.
- Tests/Lint auf dieser Maschine: `.venv/Scripts/python.exe -m pytest` und `.venv/Scripts/python.exe -m ruff` (`uv run` scheitert an der TLS-Interception; MEMORY.md).
- Antworten im Chat auf Deutsch; Code, Commits und CHANGELOG englisch; `.planning/` deutsch.
- Publish nur über Remote `fork`, `origin` ist pull-only (MEMORY.md).
- Agent-Selbstangaben („lint PASSED") gegenprüfen: `ruff check` selbst erneut laufen lassen (MEMORY.md).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-IBKR-10 | Schreibrecht als dokumentierte Einmalhandlung; vorher 321 | `--live`-Flag; frische 321-Messung (Pitfall 1: 321 zeigt sich in der Kette am whatIf, nicht am `placeOrder`); Handbuch-Tabelle „Gateway Read-Only switch" |
| REQ-IBKR-45 | Prüfkette an einer Stelle, in Reihenfolge, getestet | `_run_locked` → `_execute_ticker`; Reihenfolgetest gegen `FakeIB.calls` mit vier dokumentierten Abweichungen; Section „Order-Sequenz-Test" |
| REQ-IBKR-47 | Fills je `execId` mit Dedup und Korrekturregel | `exec_family()`/`effective_executions()` im Ledger-Modul; `filled`/`partial` je `execId`; `resolve_entry` und `_fill_quantity` korrigieren |
| REQ-IBKR-48 | Executions und abgeschlossene Orders am selben Tag persistiert | Persistenz im selben Lauf direkt nach der Fill-Bestätigung (D-10) aus einer frischen `order_history()`-Lesung |
| REQ-IBKR-65 | Zustand nach jeder Order lesen und gegen Absicht vergleichen | Post-Order-Kontrolle aus `order_history()` (Status, Menge, `orderRef`, Seite, `conId`); Abweichung → `post-order-mismatch`, ganzer Lauf endet |
</phase_requirements>

## Summary

Die Phase ist klein, weil fast alles schon steht: die komplette Prüfkette läuft heute bis zum `intent` und übergibt dann an `ctx.placer.complete(ctx, intent)` (`scripts/ibkr_executor.py:2275`). Phase 6 ersetzt dort `DryPlacer` durch einen `LivePlacer`, wenn `--live` gesetzt ist. Vier Dinge sind dafür neu zu bauen und alle haben eine klare Vorlage im Code: (1) ein zweites Einmal-Permit in der Socket-Sperre (`_arm_write_barrier`) für genau eine echte Markt-Order auf Nachrichten-Id 3, (2) ein Adapter-Methode `place_order` mit Fill-Warten (60 s, kein Storno), (3) Ledger-Umbau für vorzeichenbehaftete Fills und die `execId`-Korrekturregel, (4) die Jev-Abgleichung über `summary.json`.

Drei Befunde aus dem Code ändern die Planung gegenüber dem CONTEXT-Wortlaut und gehören vorn in die Pläne. **Erstens:** Mit eingeschaltetem „Read-Only API" scheitert der `whatIf` (321, 10 s Timeout, Zustand `preview-read-only`, Exit 5) — also *vor* dem `placeOrder`. Die D-11-Messung „`execute --live` scheitert beim Platzieren mit 321" kann in der Kette nie den `placeOrder` erreichen; der frisch gemessene 321-Beleg ist der Zustand `preview-read-only` am whatIf (das ist der Weg, den Phase 4 D-14 auch schon gemessen hat, jetzt am Tag und im scharfen Pfad). **Zweitens:** `rating_source` steht in `summary.json` **nur**, wenn Jev aktiv war (`daily_paper_run.py:370-372`); ohne Jev fehlt das Feld. „Fehlendes Feld" muss also als `engine` gelesen werden, sonst wäre jeder Ticker fail-closed. **Drittens:** Das Handbuch und Phase-5-D-19 versprechen `execute --resolve KEY=never_sent` „mit Phase 6", CONTEXT und Roadmap erwähnen es nicht. Ohne diese Funktion ist ein Live-`intent` ohne Spur (Absturz zwischen `intent` und `placed`) ein dauerhafter Exit 6. Das ist eine offene Frage für den Nutzer (Open Question 1).

**Primary recommendation:** `LivePlacer` in einem einzigen Plan zusammen mit dem Adapter-Permit bauen (`IbkrBroker.place_order` als 10. und letzte öffentliche Methode), vorher Ledger (signierte Fills, `execId`-Familien) und Jev-Abgleich als unabhängige Pläne in Welle 1, den Reihenfolgetest und die States/Handbuch in Welle 3, den Operator-Checkpoint zuletzt.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `--live`-Flag, Placer-Wahl, Ledger-Ziel je Modus | Executor (`ibkr_executor.py`) | — | Einzige Stelle, die Lock/Schalter/Ledger/Kette kennt |
| Echte Order senden, Fill-Warten, Nachricht-3-Permit | Broker-Adapter (`ibkr_broker.py`) | — | Einziges Modul, das `ib_async` importiert (Isolationstest) |
| Post-Order-Kontrolle (Status/Menge/orderRef) | Executor (`LivePlacer`) | Adapter (liefert `order_history()`) | Vergleich Absicht↔Ist ist Policy; Lesen ist Adapter |
| Fills je `execId`, Korrekturregel, vorzeichenbehaftete Summe | Ledger-Modul (`ibkr_ledger.py`, rein) | Executor (schreibt Zeilen) | Reine Funktion, ohne Client-Bibliothek testbar |
| Zustände/Exit-Tabelle | Guards-Modul (`ibkr_guards.py`) | Ledger-Grund-Tabelle, Handbuch | `EXIT_BY_STATE` ist die eine Tabelle |
| Jev-Abgleich | Decision-Modul (`ibkr_decision.py`, `read_summary`/`evaluate_decision`) | Executor (`_summary_reader`) | `summary.json` wird dort schon gelesen und geprüft |
| 321-Messung, Fill-Abnahme | Operator (Checkpoint) | Sonde `scripts/smoke/ibkr_order_probe.py` | Echtes Konto, nur Mensch sieht TWS |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ib_async` | 2.1.0 (exakt gepinnt, installiert und per `ib_async.__version__` bestätigt) | IBKR-API-Client; nur im Adapter importiert | Bereits Projektentscheidung; Pin in `pyproject.toml` Extra `ibkr` [VERIFIED: pyproject.toml + .venv] |
| Python stdlib (`asyncio`, `json`, `dataclasses`) | 3.11+ | Warteschleife, Ledger | Keine neue Abhängigkeit |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | im Dev-Extra | Tests (`unit`-Marker, `-m "not integration"` Default) | Alle Phase-6-Tests [VERIFIED: pyproject.toml] |
| `ruff` | im Dev-Extra | Lint, line-length 100, py311 | Vor jedem Commit |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polling der `Trade`-Status im Adapter (alle 0,1-0,25 s) | `trade.filledEvent` awaiten | Polling ist mit `FakeIB` trivial zu testen und braucht keine Event-Attrappen; Events wären nur marginal schneller. Empfehlung: Polling. |
| Neuer Event `alarm` im Ledger für Timeout/Mismatch | Bestehendes `reconcile`-Event mit `outcome` wiederverwenden | `reconcile` ist semantisch „Abgleich"; `alarm` (nicht-lifecycle) ist ehrlicher. Beide lassen den `intent`/`placed` offen, damit der Folgelauf abgleicht. Empfehlung: `alarm`. |

**Installation:** Keine neuen Pakete. `ib_async==2.1.0` ist schon im Extra `ibkr`.

**Version verification:** `.venv/Scripts/python.exe -c "import ib_async;print(ib_async.__version__)"` → `2.1.0` [VERIFIED: ausgeführt 2026-10-18].

## Package Legitimacy Audit

Diese Phase installiert **keine** neuen externen Pakete. `ib_async==2.1.0` ist seit Phase 2 gepinnt und im Repo etabliert; slopcheck war nicht nötig.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| ib_async (bestehend) | PyPI | bestehende Projektabhängigkeit | — | github.com/ib-api-reloaded/ib_async | nicht geprüft (nicht neu) | Approved (unverändert, Phase 2) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
execute TICKER... [--live]
      │
      ▼
 argparse ──(--live fehlt)──► DryPlacer, ledger-dryrun.jsonl (MODE_DRYRUN)
      │ --live
      ▼                                 (Placer-/Modus-Abgleich: sonst Exit 1 not-dry / not-live)
 Lock ledger.jsonl.lock ──held──► Exit 7
      ▼
 Schalter-Preflight (RELEASE/KILL) ──block──► Exit 4 (+ cancel_all bei KILL)
      ▼
 Ledger.open(ledger.jsonl, MODE_LIVE)
      ▼
 Reconciliation offener Einträge (order_history: open+completed+executions)
      │  unlösbar ──► Exit 6          offen ──► weiter (already-attempted für diesen Key)
      ▼
 Paper-Log fetch ► lokale Kette (Log, summary.json, Jev-Abgleich NEU, Frische)
      ▼
 Schlüsselprüfung (already-attempted / decision-changed)
      ▼
 Gateway-Kette je Ticker: Auflösung ► Position+Quellen ► Plan ► Größe ► Sitzung
      ▼
 Schalter ► whatIf(orderRef) ► Konto-/orderRef-Echo ► judge_preview ──reject──► Exit 5
      ▼
 Schalter ► SWITCH_CHECK ► Fenster neu ► Frische neu (NEU, WR-05) ► Größe 2 ► INTENT (fsync)
      ▼
 LivePlacer.complete(ctx, intent)
      │  adapter.place_order(...)  ◄── Einmal-Permit Nachricht 3, genau eine Order
      │  ledger: PLACED (order_id)
      │  warten ≤ 60 s (Polling Trade.orderStatus)
      ├─ Timeout ► ledger: alarm(fill-timeout), Order bleibt ► _ExecuteStop(Exit fill-timeout)
      ├─ ValidationError/Cancelled/Inactive ohne Fill ► ledger: REJECTED(place-rejected)
      ▼  Filled
 order_history() frisch lesen (REQ-65 + D-10)
      ├─ Abweichung ► ledger: alarm(post-order-mismatch) ► _ExecuteStop (ganzer Lauf endet)
      ▼  ok
 ledger: FILLED/PARTIAL je execId (Korrekturregel), + Abgeschlossene-Order-Daten
      ▼
 State "order-filled" (Exit 0) ► nächster Ticker ► RUN_END
```

### Recommended Project Structure

```
scripts/
├── ibkr_executor.py      # --live, LivePlacer, Ledger-Wahl je Modus, Frische-Neuprüfung
├── ibkr_broker.py        # _OrderPermit, place_order(), geteilter _build_order()
├── ibkr_ledger.py        # exec_family, effective_executions, signed filled_quantity, alarm-Event
├── ibkr_guards.py        # neue States + Exit-Codes + Rangtabelle
├── ibkr_decision.py      # RunRecord.rating_source, State rating-jev
├── IBKR_EXECUTION.md     # Zustands-/Exit-/Ledger-Tabellen, --live, Read-Only-Eintrag
└── smoke/ibkr_order_probe.py   # unverändert nutzbar (--history)
tests/
├── ibkr_fakes.py         # FakeIB.placeOrder modellieren (heute "forbidden")
├── test_ibkr_broker.py   # Permit-Negativkontrollen gegen echte Client-Klasse
├── test_ibkr_ledger.py   # Signierte Summe, execId-Korrektur
├── test_ibkr_execute.py  # --live-Läufe, Reihenfolge, Timeout, Mismatch, zweiter Lauf
└── test_ibkr_isolation.py# öffentliche Methoden, AST-Aufrufstellen, Handbuch-Tabellen
```

### Pattern 1: Placer-Naht und Modus-Wahl

**What:** `main()` bekommt bereits `placer=None` zur Injektion. `_execute` setzt `placer = DryPlacer() if placer is None`. Neu: `placer = LivePlacer() if args.live else DryPlacer()`. `run_execute` ersetzt die `EXECUTE_FORCED_DRY`-Prüfung (Z. 1161) durch einen Abgleich in beide Richtungen: ohne `--live` muss `placer.dry is True` sein (State `not-dry`, Exit 1, existiert), mit `--live` muss `placer.dry is False` sein (neuer State `not-live`, Exit 1). Die Prüfung steht weiter **vor** jeder Dateiberührung.

**Ledger-Ziel:** `_run_locked` öffnet heute hart `default_dryrun_ledger_file()` mit `MODE_DRYRUN` (Z. ~1387). Das wird `default_ledger_file()`/`MODE_LIVE` bei `--live`. Der Lock bleibt immer `ledger.jsonl.lock` (schon so). `_reconcile` leitet `dry` bereits aus `ctx.ledger.mode` ab, also ist `no_trace` im Live-Ledger richtig Exit 6.

**Placer-Daten:** `complete(ctx, intent)` kennt `symbol`, `sec_type`, `currency`, `primary_exchange` nicht (der `intent` trägt nur `con_id`). Signatur nicht ändern (Test-Placer `_KillingPlacer`, `ReadingPlacer`, `FailingPlacer`, `DiskPlacer` überschreiben `complete(self, ctx, intent)`); stattdessen unmittelbar vor `ctx.placer.complete` ein `ctx.placing = SimpleNamespace(symbol=..., sec_type=..., currency=identity.currency, primary_exchange=identity.primary_exchange)` setzen. [VERIFIED: ibkr_executor.py:1051-1064, 2275; tests/test_ibkr_execute.py:1311]

**Erfolgszustand:** Neuer State `order-filled` (Exit 0) muss in `_ledger_row_finished` wie `DRY_COMPLETE` früh zurückkehren (Z. 1124), sonst schreibt der Fallback eine falsche `skipped/review`-Zeile (`LEDGER_REASON_UNMAPPED`). Gleiches gilt für jeden neuen Zustand, den der Placer selbst im Ledger vermerkt.

### Pattern 2: Einmal-Permit für `placeOrder` (Vorlage `_CancelPermit`)

**What:** Heute lässt `guarded_place` (Name), `guarded_send` (Feldebene) und `guarded_send_msg` (String-Ebene) Id 3 nur als STK-whatIf durch (`_whatif_in_fields`/`_whatif_in_message`). Neu kommt ein `_OrderPermit(open=False, sent=0)` daneben.

Wichtige Unterschiede zum Cancel-Permit:

- **Pro Order, nicht pro Session.** `cancel_all` sperrt nach einem Durchgang die ganze Session (`if self._permit.sent: raise`). Ein Lauf mit mehreren Tickern braucht aber mehrere Orders in einer Session. Das Permit öffnet deshalb vor *jeder* Order und schließt auf der Leitung nach genau einem Durchgang (`sent += 1`, `open = False` in `guarded_send_msg`). Eine Obergrenze je Session ist nicht nötig, weil D-09 den Lauf beendet; der AST-Test pinnt die Aufrufstellen.
- **Whitelist statt Blankoöffnung.** Auch bei offenem Permit darf nur eine *reine Aktien-Markt-Order* durch: `secType == "STK"`, `orderType == "MKT"`, `action in {BUY, SELL}`, `whatIf` nicht `True`, `account == EXPECTED_ACCOUNT`, `orderRef` nicht leer, `tif == "DAY"`, ganzzahlige positive Menge. Auf der String-Ebene gelten die gemessenen Indizes (Ib_async 2.1.0, Server ≥ 177, STK): Id `[0]=="3"`, secType `[4]`, action `[16]`, Menge `[17]`, orderType `[18]`, tif `[21]`, account `[23]`, orderRef `[26]`, whatIf `[84]` (`"0"` bei echter Order). Diese Indizes gehören — wie `_PO_*` heute — als Konstanten in den Adapter, abgesichert durch einen Test gegen die echte Client-Klasse, der bei einem Layout-Wechsel rot wird.
- **Der whatIf bleibt unberührt.** Ein whatIf auf Id 3 verbraucht das Permit nicht und braucht es nicht.

**Adapter-API:** Eine neue öffentliche Methode `place_order(...)` (Name frei). Der Isolationstest `test_adapter_has_at_most_ten_public_methods` erlaubt ≤ 10 und pinnt die Menge (heute 9: `connect, positions, health, search_contract, contract_details, open_orders, preview_order, order_history, cancel_all`). `place_order` macht die 10. Eine zweite öffentliche Methode (z. B. `await_fill`) würde das Limit sprengen. Das Fill-Warten gehört deshalb **in** `place_order` (privat zerlegt). Der Test wird auf die neue Menge aktualisiert, nicht das Limit angehoben.

**Gleiche Order wie die Vorschau:** `preview_order` baut die Order inline (`orderType="MKT"`, `tif="DAY"`, `account=EXPECTED_ACCOUNT`, `orderRef`). Diesen Bau in `_build_order(...)` herausziehen und von beiden Methoden nutzen lassen; ein Test vergleicht Feld für Feld die Vorschau-Order (`fake.whatif_calls[0][1]`) mit der gesendeten Order.

```python
# Quelle: Muster aus scripts/ibkr_broker.py (_CancelPermit, cancel_all) + ib_async 2.1.0 ib.py:780-813
class _OrderPermit:
    """One pass of a plain stock market order on message 3, opened per order by place_order."""
    open: bool = False
    sent: int = 0

# in guarded_send_msg, nach dem whatIf-Zweig:
elif msg_id == 3 and permit.open and _real_order_in_message(msg):
    result = original_send_msg(msg, *args, **kwargs)
    permit.open = False
    permit.sent += 1          # gezählt wie bei Cancel: "an den Client übergeben" (IN-02)
    return result
```

**Wo die Order im Loop läuft:** Der Adapter treibt den Loop nur während eines `run_until_complete`. Ereignisse (orderStatus, execDetails) werden nur in dieser Zeit verarbeitet. `ib.placeOrder` ist synchron, muss aber *innerhalb* der laufenden Coroutine aufgerufen werden (wie `whatIfOrderAsync` heute in `runner()`), und das Warten läuft in derselben Coroutine:

```python
# Quelle: ib_async 2.1.0 ib.py:780 (placeOrder gibt Trade zurück), order.py:269 (DoneStates)
_TERMINAL = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive", "ValidationError"})

async def _place_and_wait(self, contract, order, timeout_s):
    trade = self._ib.placeOrder(contract, order)          # innerhalb des Loops
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while trade.orderStatus.status not in _TERMINAL and loop.time() < deadline:
        await asyncio.sleep(0.1)
    return trade   # Aufrufer unterscheidet Filled / Timeout / abgelehnt am Status
```

`ValidationError` **muss** terminal sein: `ib_async` setzt bei den Warncodes `{105,110,165,321,329,399,404,434,492,10167}` den Status auf `ValidationError`, löscht den `Trade` nicht und `OrderStatus.DoneStates` enthält ihn nicht (wrapper.py:1609-1630, order.py:269). Ein Warten auf `isDone()` würde bei einer 321-Ablehnung volle 60 s hängen. [VERIFIED: gelesener Code]

**Kein Storno beim Timeout:** `asyncio.wait_for` bricht nur die lokale Coroutine ab; es gibt keinen `cancelOrder`-Aufruf, die Order bleibt am Broker (D-08). Die Warteschleife hat ihre Frist selbst und gibt den `Trade` zurück, statt `TimeoutError` zu werfen, damit der letzte bekannte Status ins Ledger kommt.

### Pattern 3: `execId`-Familien (REQ-47)

IBKR liefert eine Korrektur als zusätzlichen `execDetails`-Callback mit allen Parametern gleich außer der `execId`, bei der sich nur die Ziffern nach dem letzten Punkt ändern (`.02` korrigiert `.01`) [CITED: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/exec-id-behavior, über Suchergebnis; Seite selbst lieferte 403]. Die `execId` hat meist vier Segmente [CITED: ebenda].

**Wichtig für die Planung:** `ib_async` dedupliziert nur nach *voller* `execId` (`wrapper.py:821-827`: `if execId not in self.fills`). Eine Korrektur erscheint dort also als **neuer** `Fill` im `trade.fills`, und `Trade.filled()` summiert beide. `trade.filled()` und `trade.fills` dürfen darum nie Quelle der Wahrheit für die Menge sein. Quelle ist ein eigenes, korrekturbewusstes Zusammenfassen der `execId`-Zeilen.

```python
# Reine Funktionen in scripts/ibkr_ledger.py (keine Client-Bibliothek, keine Uhr)
def exec_family(exec_id: str) -> str:
    """execId ohne die Ziffern nach dem letzten Punkt; ohne Punkt/Ziffern die ganze execId."""
    head, dot, tail = exec_id.rpartition(".")
    return head if dot and tail.isdigit() else exec_id

def correction_rank(exec_id: str) -> int:
    tail = exec_id.rpartition(".")[2]
    return int(tail) if tail.isdigit() else 0

def effective_executions(executions):
    """Je Familie die Ausführung mit der höchsten Korrekturnummer (bei Gleichstand die letzte)."""
    best = {}
    for e in executions:
        fam = exec_family(e.exec_id)
        if fam not in best or correction_rank(e.exec_id) >= correction_rank(best[fam].exec_id):
            best[fam] = e
    return list(best.values())
```

Genutzt von: `resolve_entry` (heute `shares = sum(float(e.shares) for e in executions)`, `scripts/ibkr_ledger.py` Reconciliation), `_fill_quantity` im Executor (Z. 1483), der Post-Order-Kontrolle und `Ledger.filled_quantity`. Eine Familie, deren Mitglieder in der Seite, `conId` oder `orderRef` abweichen, ist kein Korrekturfall, sondern `collision` (die bestehende Prüfung in `resolve_entry` fängt unterschiedliche `con_id`/`side` schon ab).

### Pattern 4: Ledger-Zeilen für Fills (D-10, WR-07)

- Je Execution (genauer: je *wirksame* Execution) eine Zeile `partial` oder `filled`, mit `exec_id`, `side`, `filled_qty` (= Stückzahl dieser Execution), `price`, `con_id`, `order_ref`/`decision_key`, `perm_id`, `order_id`. Das letzte Ereignis des Keys bestimmt den Zustand (`LIFECYCLE_EVENTS`); `unresolved()` prüft `tail[-1] in OPEN_EVENTS`, also schließen `partial`/`filled` den Eintrag (wie heute). Die Zeile, die die Absichtsmenge erreicht, heißt `filled`, vorige heißen `partial`.
- `Ledger.filled_quantity(con_id)` wird: je `decision_key` die `exec_id`-Zeilen nach `exec_family` gruppieren, je Familie die höchste Korrektur nehmen, `+` für BUY, `−` für SELL summieren. Zeilen *ohne* `exec_id` (Aggregat aus dem Completed-Order-Pfad, siehe `_fill_quantity`-Fallback) zählen nur, wenn der Key keine `exec_id`-Zeilen hat; sonst Doppelzählung (Pitfall 5).
- `_schema_problem` verlangt `side in SIDES` für `filled`/`partial` (WR-07). Der echte Ledger ist leer (`%LOCALAPPDATA%\TradingEngineX\ibkr\` enthält nur `ledger-dryrun.jsonl`, keine `ledger.jsonl`) [VERIFIED: ls 2026-10-18], daher braucht es keine Regel für Altzeilen; die Dry-Run-Datei enthält nie `filled`.
- Den Abgleich schreibt auch `_reconcile` (Folgelauf nach Timeout) über **dieselbe** Hilfsfunktion, nicht über einen zweiten Codepfad.
- Betroffene bestehende Tests: `filled_qty` kommt in `test_ibkr_ledger.py` (5), `test_ibkr_execute.py` (3), `test_ibkr_guards.py` (2) vor; sie brauchen `side`.
- `rating_source` im `intent_record` wird mit `"engine"`/`"jev"` befüllt (D-07); `row["rating_source"]` dafür in `_ROW_KEYS` und `_local_chain` ergänzen.

### Pattern 5: Jev-Abgleich (D-05/06/07)

`RunRecord` hat nur `ticker, status, signal`; `read_summary` liest ausdrücklich nur die Felder aus `RUN_FIELDS`. Ergänzen: optionales Feld `rating_source` (`str | None`) in `RunRecord`, gelesen mit eigener Typprüfung. `evaluate_decision` bekommt nach der Hold-Prüfung (Hold bleibt `skipped-hold`) und vor `EXECUTABLE` einen Zweig `rating_source == "jev"` → neuer State `rating-jev` (Exit 2, Ledger-Grund `review`, Handbuch-Tabelle Phase 4 — `test_handbook_state_table_matches_decision_module` erzwingt die Zeile). Die Prüfung steht in `evaluate_decision`, damit `preview` und `execute` dieselbe Regel haben.

`rating_source` wird von `daily_paper_run.run_ticker` nur geschrieben, wenn `"jev" in final_state`; dann `final_state.get("final_rating_source", "engine")`. Ohne Jev fehlt das Feld (`tests/test_daily_paper_run.py:282-283` pinnt das). `final_rating_source="jev"` setzt `jev/hooks.py` nur, wenn das Fallback tatsächlich angewendet wurde (`applied_tier`), und setzt dann immer auch `final_state["jev"]`. Daraus folgt: **fehlendes Feld ⇒ Jev hat das Rating nicht geändert ⇒ `engine`**. Unbekannter Wert (weder `engine` noch `jev`) ⇒ fail-closed `rating-jev`/`review`. D-06 („`summary.json` fehlt oder unlesbar ⇒ `review`") ist schon erfüllt: `summary-missing` (Exit 2, Grund `review`), `summary-schema`/`summary-contract` (Exit 1, Lauf endet via `_RunAbort`). Das ist zu testen, nicht neu zu bauen. [VERIFIED: daily_paper_run.py:367-372, jev/hooks.py:120-175, ibkr_decision.py:223-264, ibkr_ledger.py REASON_BY_STATE]

### Pattern 6: Neue Zustände konsistent halten

Jeder Zustand steht an **drei** Stellen, und Tests prüfen sie:

| Stelle | Prüfender Test |
|---|---|
| `EXIT_BY_STATE` (Guards bzw. Decision) | `test_handbook_state_table_matches_guards_module` / `..._decision_module` (Zeile `\| \`state\` \| code \|` im Handbuch) |
| Ledger-Grund-Tabelle (`REASON_BY_STATE` bzw. `REJECTED_STATES`) | `_ledger_row_finished`-Fallback loggt `LEDGER_REASON_UNMAPPED`; Tests in `test_ibkr_ledger.py` |
| Handbuch (Zustands-, Exit-, Ledger-Tabelle) | `test_handbook_exit_table_matches_executor` (**`assert len(codes) == 10`** über alle `EXIT_*`-Konstanten, bei zwei neuen Codes auf 12 anheben) |

Vorschlag (Ermessen): `fill-timeout` → neuer Exit 9 (`EXIT_FILL_TIMEOUT`), `post-order-mismatch` → neuer Exit 10 (`EXIT_POST_ORDER`), `order-filled` → 0, `place-rejected` (definitive Ablehnung ohne Fill, schließt den Key mit `rejected`) → 5, `rating-jev` → 2, `not-live` → 1. Jeder neue Exit-Code muss in `_RUN_EXIT_RANK` (sonst `KeyError` in `worst_run_exit`), im Docstring-Kopf des Executors, in der Handbuch-Exit-Tabelle und im Rangsatz des Handbuchs stehen. Vorschlag Rang aufsteigend: `0 < 2 < 5 < 1 < 3 < 8 < 9 < 10 < 6 < 7 < 4`. Alternative mit weniger Churn: beide auf bestehenden Exit 6 abbilden; D-08 verlangt aber ausdrücklich einen eigenen Exit.

`fill-timeout` und `post-order-mismatch` beenden den Lauf wie `account-conflict`: `raise _ExecuteStop(code, state, detail)` (Muster Z. 2145). Die Ledger-Zeile `alarm` (neues, nicht-lifecycle Event; in `EVENTS` ergänzen, im Handbuch bei „Events" nennen) trägt `state`, `detail`, erwartete und gelesene Werte. Der `intent`/`placed` bleibt dadurch offen, und der Folgelauf gleicht per `_reconcile` ab.

### Anti-Patterns to Avoid

- **Mengen aus `trade.fills`/`trade.filled()` übernehmen:** zählt Korrekturen doppelt (siehe Pattern 3).
- **Auf `Trade.isDone()` warten:** `ValidationError` ist nicht „done" (60 s Hänger bei 321/399).
- **Ein globales Schalten im Code** (`EXECUTE_FORCED_DRY = False`): widerspricht D-01. Die Konstante verschwindet oder wird zum Default `True` ohne `--live`.
- **`cancelOrder` oder ein zweites Permit für 4/58 beim Timeout:** D-08 verbietet es; `test_global_cancel_open_permit_keeps_the_other_write_messages_shut` bleibt gültig.
- **Order im Placer anders bauen als die Vorschau:** ein zweiter Order-Bau lässt whatIf-Prüfung und echte Order auseinanderlaufen.
- **Neuen Erfolgszustand ohne Frühausstieg in `_ledger_row_finished`:** erzeugt falsche `skipped`-Zeilen.

## Order-Sequenz-Test (SC2, REQ-45)

`FakeIB.calls` ist eine geordnete Liste von Aufrufnamen (`connect`, `open_orders`, `completed_orders`, `executions`, `placeOrder(whatIf)`, `reqGlobalCancel`, …). Heute ist `FakeIB.placeOrder` als „forbidden" modelliert (wirft `AssertionError`) und `client.placeOrder` zeichnet `"placeOrder"` bzw. `"placeOrder(whatIf)"` auf. Für Phase 6 muss die Attrappe eine echte Order modellieren: Aufruf aufzeichnen, einen `Trade`-artigen Rückgabewert mit veränderlichem `orderStatus` liefern (Namespace mit `orderStatus.status/filled/avgFillPrice/permId`, `order`, `fills`), und die Nachricht 3 auf `client.sendMsg` durchreichen (Muster: `reqGlobalCancel` in `FakeIB` modelliert „Name, dann Leitung").

Der Test fährt `execute --live` gegen die Attrappe und prüft die Reihenfolge der Beobachtungen:

1. Lock gehalten (Lockdatei existiert während des Laufs; Zweitlauf → Exit 7).
2. Schalter-Preflight (`SWITCHES`-Logzeile) **vor** der ersten Broker-Lesung (**Abweichung 1**, D-21).
3. Reconciliation: erste Broker-Lesung ist `open_orders`/`completed_orders`/`executions` — nur wenn offene Ledger-Einträge existieren.
4. Paper-Log, Quellen/Integrität, Aktualität (inkl. Jev-Abgleich in der lokalen Kette).
5. Schlüsselprüfung `already-attempted` **nach** Aktualität (**Abweichung 4**).
6. `qualify`/`contract_details` (Auflösung + Handelbarkeit).
7. Position/„schon ausgeführt?"-Quellen **nach** Auflösung (**Abweichung 3**).
8. Größe, Sitzung, Schalter, `placeOrder(whatIf)`, zweiter Schalter-Check (**Abweichung 2**, `switch_check` im Ledger), Frische/Fenster neu, zweite Größenprüfung.
9. Ledger `intent` (fsync) **vor** dem echten `placeOrder`; danach `placed`, `filled`.

Technik: einen gemeinsamen Ereignisstrom aufbauen, in den `FakeIB.calls`, die Ledger-Zeilen (per `ledger.append`-Wrapper oder durch Lesen der Datei nach jedem Broker-Aufruf in der Attrappe) und die `SWITCHES`-Logzeile einlaufen, und dann die Teilfolge assertieren. Der entscheidende Beweis „`intent` vor `placeOrder`": in der Attrappe beim echten `placeOrder` die Ledger-Datei lesen und assertieren, dass der `intent` schon dort steht (Muster `DiskPlacer` in `test_ibkr_execute.py:~1078`).

Negativkontrollen (REQ-66): (a) whatIf-Reject (Fehlertext über `emit_during={"whatif": [...]}` bzw. Fehlerliste, siehe Pitfall 6) ⇒ Exit 5 und `"placeOrder" not in fake.calls`; (b) `KILL` zwischen zwei Tickern ⇒ zweiter Ticker bekommt keine Order (Bestand: `test_g3_kill_between_two_orders`); (c) Größenüberschreitung ⇒ kein whatIf, kein `intent`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Order über die Leitung senden | Eigenes Protokoll/Socket | `ib.placeOrder(contract, order)` aus `ib_async`, durch das Permit gefiltert | Layout, Versionsfelder und Throttling gehören der Bibliothek |
| Order-/Fill-Status verfolgen | Eigene Event-Verwaltung | `Trade.orderStatus` (aktualisiert die Bibliothek) | `wrapper.orderStatus` pflegt `filled`, `avgFillPrice`, `permId` |
| Idempotenz | Hash, Zähler, eigener Schlüssel | `decision_key` = `orderRef` (REQ-39), `Ledger.attempt_of` | Schon gebaut, über Phase 5 getestet |
| Lock | Eigener Lockfile-Code | `tradingagents.dataflows.files.locked(..., wait=False)` | Schon im Lauf |
| Append-only-Ledger | Neues Dateiformat | `Ledger` (fsync, Siegel nach abgerissenem Ende) | Torn-Tail-Logik ist subtil |
| Stunden-/Sitzungsfenster | Eigene Uhrzeitkonstanten | `contracts_mod.window_open`, `evaluate_session` | `test_no_hard_coded_trading_times_in_execution_code` verbietet Konstanten |
| Netto-Fillsumme | `sum(filled_qty)` | Signierte, korrekturbewusste Summe (Pattern 3/4) | WR-07 und REQ-47 |

**Key insight:** Alle Sicherheitsmechanismen existieren und sind negativ getestet; die Phase darf sie nur anschließen. Jede neue Leitplanke (außer den ausdrücklich geforderten) widerspricht dem Phasenzuschnitt „schaltet um, baut nicht".

## Runtime State Inventory

Phase 6 ist keine Umbenennung, aber sie schaltet erstmals den echten Ledger ein. Der Vollständigkeit halber:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `ledger.jsonl` existiert nicht; `ledger-dryrun.jsonl` (3 Zeilen, Kill-Lauf 2026-10-17); `contracts.json` (AAPL, MSFT, NVDA) [VERIFIED: ls] | Dry-Ledger bleibt unberührt; `ledger.jsonl` entsteht beim ersten `--live`-Lauf |
| Live service config | Gateway-Schalter „Read-Only API": aus (Stand 2026-10-17, Phase-5-Abnahme) | Handbuch-Tabelle „Gateway Read-Only switch" um die Einträge des Messtags ergänzen (ein/aus) |
| OS-registered state | Kein Scheduler (Phase 8) | None — verified by Phase-Zuschnitt |
| Secrets/env vars | `.env` mit `IBKR_HOST/PORT/ACCOUNT_ID`; kein neues Secret | None |
| Build artifacts | Keine | None |

## Common Pitfalls

### Pitfall 1: 321 zeigt sich am whatIf, nicht am `placeOrder`
**What goes wrong:** D-11 erwartet „`execute --live` scheitert beim Platzieren mit 321". Mit eingeschaltetem Schalter blockt das Gateway aber schon den whatIf (321, 10-s-Timeout, `PreviewResult.state = READ_ONLY_API`) [CITED: ibkr-konto-befund.md, Phase-4-Abschnitt Messung 2]. `judge_preview` macht daraus `preview-read-only` (Exit 5, `REJECTED_STATES`). Der `placeOrder` wird nie erreicht.
**Why it happens:** Die Kette ruft den whatIf vor dem `intent`.
**How to avoid:** Den D-11-Beleg als „`execute --live` mit Read-Only an endet an der ersten Schreibberührung (whatIf) mit 321: Zustand `preview-read-only`, Exit 5, kein `intent`, kein `placeOrder`" fassen und die Plan-Texte so formulieren. Nicht den Code ändern, um den 321 künstlich beim `placeOrder` zu erzwingen. Ergänzend belegt der Test mit Attrappe den Pfad „321/`ValidationError` am echten `placeOrder`" (REQ-10-Wortlaut), siehe Pitfall 2.
**Warning signs:** Der Plan verlangt `placeOrder` bei gesetztem Read-Only.

### Pitfall 2: Abgelehnte Order hinterlässt einen offenen `intent` (Exit 6 für immer)
**What goes wrong:** Endet die Order mit `ValidationError`/`Cancelled`/`Inactive` und ohne Fill, ist am Broker unter Umständen *keine* Spur vorhanden. Bleibt der `intent` (und `placed`) offen, löst die Reconciliation im Live-Ledger `no_trace` aus ⇒ Exit 6 in jedem Folgelauf. Es gibt keinen Lösungsweg (siehe Open Question 1).
**Why it happens:** `resolve_entry` ist im Live-Modus bewusst streng (`NO_TRACE` unlösbar); Trockenläufe haben `never_sent`.
**How to avoid:** Der Placer schließt eine *definitive* Ablehnung selbst mit `rejected` (State `place-rejected`, mit Statuscode, Fehlertexten aus `_request_error_texts`). Nur *unklare* Ausgänge (Timeout, Link-Ereignis während des Wartens) lassen den Eintrag offen für die Reconciliation.
**Warning signs:** Test „Order abgelehnt, zweiter Lauf" endet mit Exit 6.

### Pitfall 3: `trade.filled()` und Korrekturen
**What goes wrong:** Siehe Pattern 3. Eine Korrektur `.02` wird zusätzlich zum `.01`-Fill gezählt.
**How to avoid:** Eigene Aggregation aus `order_history().executions` über `effective_executions`.

### Pitfall 4: `Execution.orderRef` ist am echten Konto noch nie gemessen
**What goes wrong:** `resolve_entry`, `_fill_quantity` und der `executed_conflict`-Check matchen Executions über `orderRef`. Wenn `reqExecutions` das Feld für API-Orders leer liefert, sieht die Reconciliation keine Executions (`no_trace`/falsche Menge).
**Why it happens:** Bis heute gab es nie einen Fill; die Rohform von Executions fehlt im Befund (nur `completed` mit `Cancelled` und `executions: []` sind gemessen) [VERIFIED: ibkr-konto-befund.md, Messung 3]. D-13 verlangt daher „plus erster echter Fill" für das Fixture. [ASSUMED] dass das Feld gefüllt ist.
**How to avoid:** Placer matcht seine *eigene* Order in der Post-Order-Lesung zusätzlich über `perm_id`/`order_id` (beide aus dem `Trade`), nicht nur über `orderRef`; der Operator-Checkpoint sichert die Rohausgabe von `ibkr_order_probe.py --history` unmittelbar nach dem Fill in den Befund. Leere `orderRef` bei Executions → Alarm statt stiller Annahme.
**Warning signs:** Erste echte Order gefüllt, aber Folgelauf `no_trace`.

### Pitfall 5: Aggregat- und Einzelzeilen zählen doppelt
**What goes wrong:** Der Completed-Order-Fallback in `_fill_quantity` schreibt eine `filled`-Zeile mit der Gesamtmenge ohne `exec_id`; später kommen Einzelzeilen je `exec_id` dazu.
**How to avoid:** Regel in `filled_quantity`: pro Key zählen nur `exec_id`-Zeilen, wenn welche existieren, sonst das Aggregat. Test mit beiden.

### Pitfall 6: `rejectReason` gibt es in `ib_async` 2.1.0 nicht
**What goes wrong:** D-12 spricht von „einem whatIf mit `rejectReason`". `judge_preview` dokumentiert: `OrderState` hat in 2.1.0 kein `rejectReason`; der Reject-Grund wird aus den *Request-Fehlertexten* gebaut (`errors` ⇒ `PREVIEW_REJECTED`; `EMPTY` mit Fehlern ebenso).
**How to avoid:** Das Fixture treibt den Reject über `FakeIB(whatif=ibkr_fakes.order_state(...), emit_during={"whatif": [(reqId, code, text, None)]})` (Fehlerereignis während des whatIf) oder `whatif=[]` plus Fehler; nicht über ein Attribut `rejectReason` am OrderState. Erwartung: Exit 5, State `preview-rejected`, Ledger-`rejected`, `"placeOrder" not in fake.calls`. [VERIFIED: ibkr_decision.py:351-377]

### Pitfall 7: Kein Fill in 60 s ohne Marktdaten-Abonnement
**What goes wrong:** Das Paper-Konto hat kein Marktdaten-Abonnement (nur verzögerte Kurse, Typ 3). Ob eine Markt-Order unter diesen Umständen binnen 60 s gefüllt wird, ist unbekannt. [ASSUMED]
**How to avoid:** Genau dafür ist D-08 gebaut. Der Checkpoint rechnet mit dem Zweig „Timeout" als realem Ausgang und prüft den Folgelauf (Reconciliation `OPEN`/`FILLED`); der Plan darf Timeout nicht als „unmöglich" abtun.

### Pitfall 8: Post-Order-Lesung zu früh
**What goes wrong:** `orderStatus=Filled` kann vor dem `execDetails`/`reqExecutions`-Eintrag sichtbar sein; die drei Lesungen von `order_history()` sind nicht atomar.
**How to avoid:** Nach `Filled` die Historie lesen; ergeben die wirksamen Executions weniger als die Absichtsmenge, bis zu wenigen Sekunden (innerhalb des 60-s-Budgets) erneut lesen, bevor `post-order-mismatch` ausgelöst wird. [ASSUMED] dass der Versatz auftritt; der Retry ist billig.

### Pitfall 9: Eigene offene Order blockiert den Ticker als „fremd"
**What goes wrong:** Nach einem Timeout steht die eigene Order offen. `plan_order` behandelt jede offene Order als fremd (`foreign-open-order`, Exit 2; Docstring: „Own open orders are only netted … from phase 6 on").
**How to avoid:** Das ist fail-closed und für Phase 6 ausreichend (der Key selbst ist ohnehin `already-attempted`). Nicht netten, solange nur ein Ticker/Block im Spiel ist; im Handbuch nennen.

### Pitfall 10: Budget je Ticker statt summiert (P4 IN-05)
**What goes wrong:** Mehrere BUYs in einem Lauf werden je gegen dieselbe `AvailableFunds`-Messung geprüft. Bei `MAX_QTY_PER_ORDER = 2` und rund 1 Mio. EUR praktisch folgenlos; als Leitplanke trotzdem lückenhaft. Todo `06-open-info-findings-phase-2-4.md` verlangt, es beim Planen zu entscheiden.
**How to avoid:** Entscheidung für den Planer: entweder dokumentiert akzeptieren (Phase-Zuschnitt „keine neuen Leitplanken", ein Ticker genügt) oder `snapshot.available_funds` im Lauf um die bisherigen `initMarginChange` mindern (kleiner Eingriff in `_execute_ticker`). Empfehlung: akzeptieren und im Handbuch vermerken. P2 IN-07 (Loopback-Host) ähnlich: `IBKR_HOST` ist lokal `127.0.0.1`; optional im `validate_settings` prüfen, nicht Pflicht.

### Pitfall 11: Test-Churn durch `NOT_DRY`
`tests/test_ibkr_execute.py:312/330` erwarten `ibkr-state=NOT_DRY` bei nicht-trockenem Placer; `tests/test_ibkr_guards.py:319` pinnt `(NOT_DRY, 1)`. Das Verhalten bleibt für „kein `--live` + nicht-trockener Placer". Die Tests, die heute `DryPlacer`-Unterklassen mit `--live`-losen Läufen fahren, bleiben gültig.

## Code Examples

### Ledger-Ziel und Modus je Flag

```python
# Quelle: scripts/ibkr_executor.py (_run_locked, Z. ~1384) — Änderung
ledger_path = default_ledger_file() if args.live else default_dryrun_ledger_file()
mode = ledger_mod.MODE_LIVE if args.live else ledger_mod.MODE_DRYRUN
ctx.ledger = ledger_mod.Ledger.open(ledger_path, mode=mode, clock=clock, run_id=uuid.uuid4().hex)
```

### Frische vor dem `intent` neu prüfen (WR-05-Rest)

```python
# Quelle: scripts/ibkr_executor.py _execute_ticker; "now" wird für das Fenster schon gelesen
now = ctx.clock()
fresh = ctx.mods.decision.freshness(
    ctx.mods.decision.parse_trade_date(row["trade_date"]), now, ctx.calendar
)
if fresh.state != "fresh":
    _finish_row(ctx, row, fresh.state, fresh.detail)   # stale-decision / future-decision
    return
```
Steht direkt neben der Fensterprüfung, vor `intent_record`. `freshness()` fängt `CalendarRangeError` selbst ab (`stale-decision`).

### Fixture für die `execId`-Korrektur (SC5/D-13)

```python
# Quelle: tests/ibkr_fakes.fill(...); künstliche Korrektur .01 -> .02
e1 = ibkr_fakes.fill(265598, KEY, 2, exec_id="0000e0d5.6710a3c5.01.01", price=250.10)
e2 = ibkr_fakes.fill(265598, KEY, 2, exec_id="0000e0d5.6710a3c5.01.02", price=250.12)
# Erwartung: effective_executions([e1, e2]) == [e2]; filled_quantity == 2, nicht 4.
```
Die konkrete `execId`-Form ist ein Platzhalter; der Operator-Checkpoint ersetzt sie durch die echte Rohform des ersten Fills (D-13).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 5: `EXECUTE_FORCED_DRY = True`, Ledger nur `ledger-dryrun.jsonl` | `--live` je Lauf, `ledger.jsonl` im Live-Modus | Phase 6 | Placer-Naht und Ledger-Wahl hängen am Flag |
| `filled_quantity`: unsignierte Summe | Signiert, korrekturbewusst | Phase 6 (WR-07/REQ-47) | Verkauf blockiert Ticker nicht mehr |
| `rating_source` immer `None` | `engine`/`jev` aus `summary.json` | Phase 6 (D-23) | Jev-Fallback wird nicht gehandelt |

**Deprecated/outdated:**
- Handbuch-Sätze „phase 5 refuses to run / forced dry / `ledger.jsonl` (from phase 6)" und der Vorbehalt „`--resolve` comes with phase 6" müssen aktualisiert werden (Open Question 1 entscheidet, wie).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Fehlendes `rating_source` in `summary.json` bedeutet `engine` (Folgerung aus `jev/hooks.py` und `run_ticker`) | Pattern 5 | Wenn Jev-Fallback ohne Feld möglich wäre, würde ein Jev-Rating gehandelt; Gegenprüfung: Test über `run_ticker` + echtes `summary.json` des letzten Paper-Laufs |
| A2 | Die Ziffern nach dem letzten Punkt sind numerisch vergleichbar; höhere Zahl = spätere Korrektur | Pattern 3 | Falsche Wahl der gültigen Zeile bei exotischen Formaten; Fallback: bei Gleichstand/Nichtnumerik letzte nach `seq` |
| A3 | `reqExecutions` füllt `Execution.orderRef` für API-Orders | Pitfall 4 | Reconciliation/Fill-Zuordnung über `orderRef` greift ins Leere; Mitigation `perm_id`-Match |
| A4 | Eine Markt-Order auf AAPL im Sitzungsfenster füllt im Paper-Konto binnen 60 s, auch ohne Marktdaten-Abo | Pitfall 7 | Timeout-Pfad wird zum Normalfall |
| A5 | `reqExecutions` ohne Filter liefert nur den laufenden Handelstag (daher D-10/REQ-48) | Pattern 4 | Folgetag-Reconciliation findet Executions nicht mehr — D-10 mildert das |
| A6 | Order-Fehler 399 („geparkt") erscheint als `ValidationError`-Status bzw. Request-Fehler und ist nie am realen Gateway gemessen (REQ-67-Lücke) | Pitfall 2, Open Question 3 | Falsche Behandlung geparkter Orders; Test baut auf der offiziellen Liste |
| A7 | `Filled` im `orderStatus` kann vor der Execution in `reqExecutions` sichtbar sein | Pitfall 8 | Falscher `post-order-mismatch`-Alarm; Retry mildert |

## Open Questions (RESOLVED)

1. **`execute --resolve KEY=never_sent --note TEXT` (Phase-5-D-19) — in Phase 6 oder bewusst später?**
   - What we know: Phase-5-CONTEXT D-19 und das Handbuch (Zeile „A `--resolve` flag … comes with phase 6") versprechen es für Phase 6. 06-CONTEXT, Roadmap-SC und die fünf Requirements erwähnen es nicht. Im Ledger fehlt ein `resolved`-Event. Im Live-Ledger ist ein `intent` ohne Spur (Absturz zwischen `intent` und `placed`) unlösbar: Exit 6 in jedem Folgelauf; „Zeilen löschen" ist verboten, „Ledger umbenennen" würde die Idempotenz-Historie opfern.
   - What's unclear: Ob der Nutzer das als Eingangsaufgabe will.
   - Recommendation: Entscheiden lassen. Mindestweg: Placer schließt definitive Ablehnungen selbst (Pitfall 2) und das Handbuch beschreibt den Notausgang ehrlich. Sauberer Weg (klein, ein Plan): `resolved` als lifecycle-Event plus Flag.
   - RESOLVED: D-14 — eigener kleiner Plan (06-07)

2. **D-11 Wortlaut vs. Kette (Pitfall 1).** Der Nutzer sollte bestätigen, dass der 321-Beleg am whatIf (`preview-read-only`, Exit 5) als Erfüllung zählt.
   - RESOLVED: D-15 — `preview-read-only` (Exit 5) zählt als 321-Beleg

3. **Behandlung von 399/„geparkt" (REQ-63, D-22).** Vorschlag: Beobachtet der Placer in den Request-Fehlern 399 oder einen anderen als `Submitted/PreSubmitted/Filled` laufenden Status ohne Fill nach Ablauf, zählt das als Timeout bzw. `post-order-mismatch` mit Detail „parked (399)". Nicht am Gateway messbar ⇒ Fake-Test, in der Verifikation als REQ-67-Lücke benennen (wie `halted`).
   - RESOLVED: D-16 — nur Fake-Test, dokumentierte Lücke (06-06)

4. **Sollen mehrere Ticker pro Lauf live gehen?** D-03 sagt „ein Ticker genügt". Der Code unterstützt eine Liste; das Permit ist deshalb pro Order. Empfehlung: Der Operator-Checkpoint übergibt genau einen Ticker.
   - RESOLVED: D-03 — genau ein Ticker im Operator-Checkpoint (06-09/06-10)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv `.venv` | Tests, Lint, Executor | ✓ | `ib_async` 2.1.0; Pytest 1050 Tests in `test_ibkr_*.py` grün (28,5 s) | — |
| `ruff` | Lint | ✓ | `ruff check scripts tests`: All checks passed | — |
| IB Gateway / TWS auf 127.0.0.1:7497 | Operator-Checkpoint (321-Messung, erste echte Order) | ✗ (Port antwortete am 2026-10-18 nicht) | — | Operator startet Gateway am Handelstag; Pläne vor dem Checkpoint brauchen es nicht |
| `RELEASE`-Datei im State-Ordner | `execute --live` | ✗ (Phase 5 hat sie nach der Messung entfernt) | — | Operator legt sie per Handbuch-Einzeiler an |
| Handelstag im Sitzungsfenster (US-Börse) | Checkpoint | Operator-Termin | — | Bei Feiertag/Wochenende `outside-session`, kein Fehler |
| `uv run` | — | ✗ (TLS-Interception) | — | `.venv/Scripts/python.exe -m …` (MEMORY.md) |

**Missing dependencies with no fallback:** keine für die Code-Pläne; Gateway und Handelstag sind Voraussetzung nur für den Checkpoint-Plan.
**Missing dependencies with fallback:** `uv run` → direkter venv-Aufruf.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (Config in `pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `addopts = -ra --strict-markers -m "not integration"`), Marker `unit` |
| Config file | `pyproject.toml` (kein separates `pytest.ini`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_ledger.py tests/test_ibkr_guards.py tests/test_ibkr_decision.py -q` |
| Full suite command | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` (≈ 30 s) plus `.venv/Scripts/python.exe -m pytest -q` vor dem Gate |
| Lint | `.venv/Scripts/python.exe -m ruff check scripts tests` |

Bekannt rot schon vor der Phase: `test_yfinance_keeps_its_cache_out_of_the_users_home` (Windows-TEMP unter Home; 05-10-SUMMARY). Nicht der Phase anlasten.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-IBKR-10 | Ohne `--live` bleibt jeder Lauf trocken, schreibt nur `ledger-dryrun.jsonl`, sendet nichts | unit | `pytest tests/test_ibkr_execute.py -k "dry or not_dry" -x` | ✅ (erweitern) |
| REQ-IBKR-10 | `--live` ohne gültige `RELEASE` ⇒ Exit 4, kein `placeOrder`; `KILL` gewinnt | unit | `pytest tests/test_ibkr_execute.py -k "live and (release or kill)" -x` | ❌ Wave 0 |
| REQ-IBKR-10 | Placer/Modus-Abgleich (`not-dry`/`not-live`, Exit 1, vor jeder Datei) | unit | `pytest tests/test_ibkr_execute.py -k "not_live or not_dry" -x` | ⚠️ teilweise |
| REQ-IBKR-10 | `Read-Only` an ⇒ `preview-read-only`, Exit 5, kein `placeOrder`; `ValidationError`(321) am `placeOrder` ⇒ `place-rejected` ohne Hänger | unit | `pytest tests/test_ibkr_execute.py -k "read_only or validation_error" -x` | ❌ Wave 0 |
| REQ-IBKR-10 | Permit: geschlossen ⇒ `ReadOnlyViolation`; offen ⇒ genau eine STK-MKT; Limit/Nicht-STK/falsches Konto/leere `orderRef`/`whatIf=False`+LMT ⇒ refused; zweite Order ohne neues Öffnen ⇒ refused; Id 4/19/21/58 bleiben zu | unit (echte Client-Klasse) | `pytest tests/test_ibkr_broker.py -k "order_permit" -x` | ❌ Wave 0 |
| REQ-IBKR-10 | Aufrufstellen: `place_order` nur in `LivePlacer.complete`; echter `ib.placeOrder` nur im Adapter | unit (AST) | `pytest tests/test_ibkr_execute.py -k "place_order_called_at_one_site" -x` | ❌ Wave 0 |
| REQ-IBKR-10 | Öffentliche Methoden des Adapters = erwartete 10er-Menge | unit | `pytest tests/test_ibkr_isolation.py -k public_methods -x` | ✅ (anpassen) |
| REQ-IBKR-45 | Aufrufreihenfolge Lock→Schalter→Reconciliation→…→whatIf→intent→placeOrder inkl. 4 Abweichungen, `intent` auf Platte beim echten `placeOrder` | unit | `pytest tests/test_ibkr_execute.py -k "call_order" -x` | ❌ Wave 0 |
| REQ-IBKR-45 | whatIf-Reject im `--live`-Pfad ⇒ Exit 5, `placeOrder` nicht aufgerufen, Ledger `rejected` (D-12) | unit | `pytest tests/test_ibkr_execute.py -k "live and whatif_reject" -x` | ❌ Wave 0 |
| REQ-IBKR-45 | Frische-Neuprüfung vor `intent` (Uhr springt über Sitzungsgrenze ⇒ `stale-decision`, kein `intent`) | unit | `pytest tests/test_ibkr_execute.py -k "freshness_recheck" -x` | ❌ Wave 0 |
| REQ-IBKR-47 | `exec_family`/`effective_executions`: `.02` ersetzt `.01`; Gleichfamilie nicht addiert; andere Familie addiert | unit | `pytest tests/test_ibkr_ledger.py -k "exec_id" -x` | ❌ Wave 0 |
| REQ-IBKR-47 | Signierte Summe: BUY 2, SELL 2, Broker hält 0 ⇒ kein `source-conflict`; Negativkontrolle unsigniert ⇒ Konflikt | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_guards.py -k "signed" -x` | ❌ Wave 0 |
| REQ-IBKR-47 | `resolve_entry` und `_fill_quantity` mit Korrektur: Menge nicht verdoppelt | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -k "correction" -x` | ❌ Wave 0 |
| REQ-IBKR-47 | Kette `intent → placed → filled` mit `order_id`, `perm_id`, `order_ref == decision_key`, `exec_id`, `filled_qty`, `avg_price` | unit | `pytest tests/test_ibkr_execute.py -k "live_chain" -x` | ❌ Wave 0 |
| REQ-IBKR-48 | Executions + abgeschlossene Order im selben Lauf im Ledger; Folgetag-Lauf liest sie aus dem Ledger (Broker-Historie leer) | unit | `pytest tests/test_ibkr_execute.py -k "persisted_same_run" -x` | ❌ Wave 0 |
| REQ-IBKR-48 | Zweiter Lauf am selben Tag ⇒ keine zweite Order (`already-attempted`), `placeOrder` zählt 1; Folgetag mit Position am Ziel ⇒ `within-tolerance` | unit | `pytest tests/test_ibkr_execute.py -k "second_run" -x` | ❌ Wave 0 |
| REQ-IBKR-65 | Abweichung (Menge, Seite, `orderRef`, Status) ⇒ `post-order-mismatch`, `alarm` im Ledger, zweiter Ticker nicht platziert, eigener Exit | unit | `pytest tests/test_ibkr_execute.py -k "post_order_mismatch" -x` | ❌ Wave 0 |
| REQ-IBKR-65 | Fill-Timeout (60 s, Uhr/`sleep` injiziert) ⇒ `fill-timeout`, kein `cancelOrder`/`reqGlobalCancel`, Order bleibt; Folgelauf reconciliert `OPEN`/`FILLED` | unit | `pytest tests/test_ibkr_execute.py -k "fill_timeout" -x` | ❌ Wave 0 |
| D-05/06/07 | Jev: `rating_source=="jev"` ⇒ `rating-jev`/`review`; fehlendes Feld ⇒ `engine`; fehlende/kaputte `summary.json` ⇒ `review`/Exit 1; Ledger-Feld befüllt | unit | `pytest tests/test_ibkr_decision.py tests/test_ibkr_execute.py -k "rating_source or jev" -x` | ❌ Wave 0 |
| Konsistenz | Neue Zustände in `EXIT_BY_STATE`, Ledger-Tabellen und Handbuch; Exit-Konstanten-Zahl; Rangtabelle | unit | `pytest tests/test_ibkr_isolation.py tests/test_ibkr_guards.py -x` | ✅ (anpassen) |

### Sampling Rate

- **Per task commit:** `.venv/Scripts/python.exe -m pytest <betroffene Datei> -q` plus `.venv/Scripts/python.exe -m ruff check scripts tests`
- **Per wave merge:** `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` (≈ 30 s)
- **Phase gate:** volle Suite grün (bis auf den bekannten roten yfinance-Test) und `ruff check .` sauber, vom Orchestrator selbst nachgelaufen (nicht auf die Agent-Selbstangabe verlassen), vor `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/ibkr_fakes.py` — `FakeIB.placeOrder` (echte Order) modellieren: aufzeichnen, `Trade`-Attrappe mit steuerbarem `orderStatus` (Filled / bleibt Submitted / `ValidationError`), Nachricht 3 über `client.sendMsg` leiten; Fills in `executions` einspeisbar; `execId`-Korrektur-Fixture
- [ ] `tests/test_ibkr_broker.py` — Permit-Negativkontrollen gegen die echte Client-Klasse (`_wire_client`, `_stock_and_order`), inklusive Layout-Pin der String-Indizes 16/17/18/21/23/26/84
- [ ] `tests/test_ibkr_execute.py` — Hilfsfunktion `_live_run(...)` neben `_gateway_run` (Flag `--live`, `RELEASE` angelegt, Zeit-/Sleep-Injektion für den 60-s-Timeout ohne echtes Warten), Ereignisstrom für den Reihenfolgetest
- [ ] Test für `FakeIB`-Selbstkonsistenz (Attrappe verhält sich wie die Bibliothek: Status, `filled`, Idempotenz), damit die Attrappe nicht selbst eine Annahme wird
- [ ] Keine neue Framework-Installation nötig

## Security Domain

Das Projekt erzwingt Sicherheit über Leitplanken (Gate G3), nicht über eine Web-Oberfläche; die ASVS-Kategorien werden auf die lokale Ausführungs-Pipeline gemappt.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein (kein Benutzer-Login; die API braucht keine Zugangsdaten) | — |
| V3 Session Management | eingeschränkt (eine API-Session, fester `clientId` 20001, Paper-Guard `managedAccounts == ["DUQ634065"]`) | bestehender Guard, unverändert |
| V4 Access Control | ja | `RELEASE` (Datei, UTF-8-JSON, ≤ 90 Tage, Konto) und `KILL`; `--live` zusätzlich; Permit nur für STK-MKT, Paper-Konto, nicht leere `orderRef` |
| V5 Input Validation | ja | `decision_key` per `fullmatch`-Whitelist (`orderRef` geht auf die Leitung); `summary.json` über `read_summary` (Schema, Typen); `rating_source` auf `{engine, jev}` begrenzen; Permit-Whitelist der Order-Felder |
| V6 Cryptography | nein | — |
| V7 Error Handling and Logging | ja | `ibkr-state=`-Logzeilen, Ledger append-only mit fsync; keine Zugangsdaten im Log |
| V11 Business Logic | ja | Idempotenz per `decision_key`/Ledger/Broker-`orderRef`; `MAX_QTY_PER_ORDER = 2` doppelt geprüft; Long-only |

### Known Threat Patterns for diese Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Doppelorder (Neustart, zweiter Lauf, Race) | Tampering | Lock, Ledger-`intent` vor Senden (fsync), `attempt_of`, `orderRef`-Gegenprobe, Reconciliation |
| Order auf Live-Konto statt Paper | Spoofing/Elevation | `EXPECTED_ACCOUNT` als Code-Konstante, `managedAccounts`-Guard, Order-`account` fest, `RELEASE.account`, Echo-Vergleich |
| Ungewollte Schreiböffnung (Permit bleibt offen, Cancel/Replace) | Tampering | Permit pro Order, schließt auf der Leitung, Whitelist der Order-Felder, Negativkontrollen gegen echte Client-Klasse, AST-Aufrufstellen |
| Jev-Fallback-Rating wird als Engine-Rating gehandelt | Tampering | `summary.json`-Abgleich, fail-closed bei unbekanntem Wert |
| Falsche Positionsbasis durch doppelt gezählte Korrektur | Tampering | `exec_family`-Korrekturregel, signierte Summe |
| Unlösbarer offener `intent` sperrt den Betrieb | Denial of Service | Definitive Ablehnung selbst schließen; offene Frage `--resolve` |
| Ledger/Protokoll manipuliert oder abgerissen | Repudiation | Append-only, Siegel nach abgerissenem Ende, Ledger außerhalb jedes Git-Baums (`ensure_outside_git`) |

## Operator-Checkpoint (Muster 05-10)

05-10 ist das Vorbild: `autonomous: false`, `checkpoint:human-action`-Tasks, Ergebnis datiert mit Rohausgaben in `.planning/ibkr-konto-befund.md`, Abschnittsmuster „Messung 1/2 … Folgen … Abnahme". Für Phase 6 (D-02, D-11, Specifics):

1. **Vorprüfungen (Agent):** Suite grün (bis auf den bekannten yfinance-Test), `ruff`, State-Ordner enthält weder `KILL` noch `RELEASE`, Gateway-Port erreichbar, Handelstag/Sitzungsfenster geprüft (`resolve AAPL` zeigt „tradable until …").
2. **321-Messung (Operator + Agent):** Operator schaltet „Read-Only API" ein; Agent legt `RELEASE` an und führt `execute <TICKER> --live` aus. Erwartung (Pitfall 1): Zustand `preview-read-only`, Exit 5, **kein** `intent` im `ledger.jsonl`, nur Eintrag `rejected`; Wartezeit ≈ 10 s (whatIf-Timeout). Rohausgabe + Logzeilen sichern. Operator schaltet Read-Only wieder aus (Handbuch-Tabelle „Gateway Read-Only switch": Datum, Grund, Vorher/Nachher).
3. **Echte Order:** `execute <TICKER> --live`, Operator beobachtet TWS bzw. Gateway. Danach `ibkr_order_probe.py --history` sichern (Rohform von Executions: `execId`, `orderRef`, `permId`, `side`, `time`; `completed`: `status`, `filled`, `avgFillPrice`). Das ist das Fixture-Material für D-13.
4. **Zweiter Lauf am selben Tag:** erwartet `already-attempted` (Exit 2), `placeOrder` kein zweites Mal; Position über `ibkr_order_probe.py`/`account` bestätigen.
5. **Befund + Handbuch:** neuer datierter Abschnitt im Befund; Handbuch „First live order" und Read-Only-Zeilen.
6. **Wenn kein Fill binnen 60 s:** Timeout-Zweig ist ein *gültiges* Ergebnis (`fill-timeout`, Exit nach Wahl); Folgelauf reconciliert; kein manuelles Stornieren durch den Agenten (D-08), der Operator entscheidet in TWS.

Operator-Hinweise aus Phase 5: TWS und Gateway teilen sich eine Sitzung pro Benutzer; die Sonde über das Gateway genügt; `RELEASE` per PowerShell-Einzeiler aus dem Handbuch (UTF-8 ohne BOM, sonst `release-invalid`).

## Sources

### Primary (HIGH confidence)
- Codebase (gelesen 2026-10-18): `scripts/ibkr_executor.py` (Placer-Naht Z. 1051-1064, 2275; `run_execute` 1153; `_run_locked` 1332; `_reconcile` 1494; `_execute_ticker` 2095), `scripts/ibkr_broker.py` (Permit/Barrier 534-635, `cancel_all` 1224, `order_history` 1007, `preview_order` 1068), `scripts/ibkr_ledger.py`, `scripts/ibkr_guards.py`, `scripts/ibkr_decision.py`, `scripts/daily_paper_run.py:367-372`, `tradingagents/jev/hooks.py`
- `ib_async 2.1.0` im `.venv`: `ib.py` (`placeOrder` 780, `connectAsync` 2025, `whatIfOrderAsync` 2204, `reqExecutionsAsync` 2278), `wrapper.py` (`execDetails` 800, `orderStatus` 735, `error` 1580), `order.py` (`OrderStatus.DoneStates`, `Trade`), `objects.py` (`Execution`)
- Messung der PLACE_ORDER-String-Indizes mit der echten Client-Klasse (Skript im Scratchpad, 2026-10-18)
- `.planning/ibkr-konto-befund.md` (Phase 4 D-14, Phase 5 D-06), `.planning/phases/05-leitplanken-scharf/05-CONTEXT.md`, `05-10-PLAN.md`/`05-10-SUMMARY.md`, `05-VERIFICATION.md`, `05-REVIEW-FIX.md`, `scripts/IBKR_EXECUTION.md`, Todos (`05-wr07-signed-fills.md`, Jev-Todo, `06-open-info-findings-phase-2-4.md`)
- Testlauf: 1050 passed in `tests/test_ibkr_*.py`; `ruff check scripts tests` sauber

### Secondary (MEDIUM confidence)
- IBKR TWS API, „ExecID Behavior" und „The Execution Object" (https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/exec-id-behavior, https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/the-execution-object): Korrekturregel `.02` korrigiert `.01`, Korrektur als zusätzlicher `execDetails`-Callback, vier Segmente. Die Seite lieferte beim direkten Abruf HTTP 403; Inhalt aus der Suchergebnis-Zusammenfassung.

### Tertiary (LOW confidence)
- Verhalten von Markt-Orders im Paper-Konto ohne Marktdaten-Abo und die Befüllung von `Execution.orderRef` bei `reqExecutions` (nicht gemessen; A3/A4)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - keine neuen Pakete; Version am Pin und in der venv bestätigt
- Architecture: HIGH - jede Stelle (Placer-Naht, Ledger-Ziel, Permit-Vorlage, Test-Muster) im Code gelesen und teils ausgeführt
- Pitfalls: MEDIUM - Code-Pitfalls (321 am whatIf, `ValidationError`, `trade.fills`-Doppelzählung, `rejectReason`) sind verifiziert; Gateway-Verhalten bei echten Fills (A3-A7) ist erst mit der ersten Order messbar

**Research date:** 2026-10-18
**Valid until:** 2026-11-17 (Code ändert sich nur durch diese Arbeit; `ib_async` ist gepinnt; Gateway-Version 10.50.1 läuft ab, siehe `GATEWAY_VERSION_EXPIRING` 2172)
