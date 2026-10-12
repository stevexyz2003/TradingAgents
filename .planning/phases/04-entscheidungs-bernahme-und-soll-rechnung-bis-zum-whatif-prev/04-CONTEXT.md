# Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Aus der Entscheidung auf `paper-log` entsteht eine vollständig geprüfte, von IBKR per `whatIf` vorab bewertete Order-Absicht, die der Lauf **nachweislich nicht sendet**. Kette: `paper-log` lesen (nur `decision-log.md` als Entscheidungsquelle) → Vorbedingungen (`schema_version`, `state_maintenance verify`, `status`, Rating, Divergenz) → Aktualität in Sitzungen → Auflösung/Handelbarkeit/Sitzung (Phase 3, `resolve_all`) → Ziel/Ist/offen → Toleranzband → `whatIf` → Protokoll.

Requirements laut Phasenkopf: REQ-IBKR-13, -14, -15, -16, -17, -18, -19, -20, -21, -22, -23, -24, -25, -38, -61, -68.
**Zusätzlich im Scope** (Traceability ordnet sie Phase 4 zu, der Phasenkopf nennt sie nicht): **REQ-IBKR-69** (`tif` explizit setzen und zurücklesen, sonst kommt `whatIf` leer zurück) und **REQ-IBKR-70** (Budgetprüfung über `initMarginChange` in Kontowährung), außerdem die **Übergabe aus Phase 3**: Halt-Teil von REQ-IBKR-37 (Fehler 154 am `whatIf`).

**Nicht in dieser Phase:** kein `placeOrder` (Gate G2), kein Kill-Switch, keine feste Größen-Obergrenze, keine Reconciliation, kein Ledger mit Write-Ahead und Lock, kein Push, kein Heartbeat.

</domain>

<decisions>
## Implementation Decisions

### Zugriff auf `paper-log`
- **D-01:** Gelesen wird über `git fetch <remote> <branch>` und danach `git show <sha>:<pfad>`, **ohne Checkout und ohne Arbeitsbaum**. Für `scripts/state_maintenance.py verify --memory-log <kopie>` (REQ-15) landet eine Kopie von `decision-log.md` unter `%LOCALAPPDATA%\TradingEngineX\ibkr\` (Muster aus Phase 2/3).
- **D-02:** Scheitert der fetch (offline, Auth, SSL), stoppt der Lauf mit **eigenem benanntem Zustand** und Exit-Code. Es gibt **keinen Rückfall** auf den zuletzt lokal bekannten Ref, weil eine veraltete Sicht den Divergenzfall aus REQ-17 unsichtbar machen würde.
- **D-03:** Remote und Branch sind Settings: `IBKR_PAPER_LOG_REMOTE` (Default `fork`) und `IBKR_PAPER_LOG_BRANCH` (Default `paper-log`), im selben Settings-Mechanismus wie die bestehenden Executor-Settings.
- **D-04:** Der gelesene `paper-log`-Commit-SHA steht in der Logzeile und im Trockenlauf-JSON, als **Provenienz, nicht als Schlüssel** (REQ-39: kein SHA im `decision_key`).

### Aktualität in Sitzungen (REQ-19, REQ-20)
- **D-05:** Die Vergangenheit wird über einen Börsenkalender gezählt, als **neue Abhängigkeit `exchange_calendars`** (Kalender `XNYS`). Grund: `liquidHours` reicht nur vom heutigen Tag etwa fünf Tage nach vorn, nicht zurück (`.planning/ibkr-konto-befund.md` §5, Rohausgabe). Für den **heutigen Tag** gilt `liquidHours` aus Phase 3. Widersprechen sich Kalender und `liquidHours` für heute (eine Quelle sagt Sitzung, die andere nicht), **stoppt** der Lauf mit eigenem Zustand.
- **D-06:** `weekend_gap` markiert **jede Kalenderlücke**: Liegt zwischen `trade_date` und Ausführung mehr als ein Kalendertag, aber keine geschlossene Sitzung (Wochenende, Feiertag oder beides), wird markiert, und die Zahl der Kalendertage wird mitprotokolliert. Ausgeführt wird trotzdem (REQ-20).
- **D-07:** Ein Lauf nimmt je Ticker den **neuesten** Eintrag in `decision-log.md`. Es gibt **keinen `--trade-date`-Schalter**, damit keine alte Entscheidung von Hand nachgeschoben werden kann. Die Aktualitätsregel entscheidet. Fixtures und Tests laufen über injizierte Pfade bzw. injizierte Quellen.
- **D-08:** Außerhalb einer Sitzung (abends, Wochenende) wird die Aktualität gegen die **nächste** Sitzung geprüft. Die Absicht wird als `closed` markiert, **`whatIf` läuft trotzdem**, weil es laut Befund auch außerhalb der Regelsitzung antwortet. So ist Phase 4 jederzeit testbar. SC4 (vier Gegenproben) wird mit injizierter Uhr und Kalender getestet.

### Blöcke, Ist-Position, offene Orders (REQ-21..24)
- **D-09:** Die Stückzahl pro Block steht als neues Feld **`block_qty` je Eintrag in `CONTRACT_TABLE`** (`scripts/ibkr_contracts.py`), also als Code-Konstante wie D-01 aus Phase 3; jede Änderung ist ein Commit. Ein Unit-Test prüft, dass jeder handelbare Eintrag `block_qty > 0` hat. Es gibt keine Ableitung aus einem Kurs (REQ-22, REQ-68).
- **D-10:** Startwert: **1 Stück je Block** für AAPL, MSFT und NVDA. Damit gilt `Buy` = 2 Stück, `Overweight` = 1, `Underweight` = `Sell` = 0, und `Hold` erzeugt nie eine Order.
- **D-11:** Die Ist-Position kommt aus `positions()` (Phase 2) und wird über den **aufgelösten `conId`** abgeglichen, nicht über das Symbol. Eine Position auf einen anderen `conId` mit gleichem Symbol zählt nicht und wird gemeldet.
- **D-12:** Offene Orders kommen über eine **neue Adapter-Lesemethode**, die alle offenen Orders des Kontos für den `conId` liest. Weil Phase 4 selbst nie sendet, ist **jede** offene Order fremd (manuell oder TWS). Das ergibt einen eigenen Zustand und **keine Absicht für diesen Ticker**. Ab Phase 6 gehen eigene offene Orders in `Ziel − Ist − offen` ein (REQ-23).

### `whatIf` trotz Schreibsperre (REQ-38, -61, -69, -70, Halt-Teil REQ-37)
- **D-13:** Eine eigene Adapter-Methode (Arbeitsname `preview_order(...)`) baut die Order **selbst**: Markt-Order (REQ-25), `whatIf=True`, `tif="DAY"` **explizit** (REQ-69). Die Schreibsperre lässt Msg-Id 3 (`placeOrder`) **nur** durch, wenn im ausgehenden Nachrichteninhalt das `whatIf`-Feld gesetzt ist. Jede echte `placeOrder` bleibt am Socket gesperrt. Tests belegen beides: Ein `whatIf` geht durch, eine `placeOrder` ohne `whatIf` wird blockiert. Der tatsächlich wirksame `tif` wird aus dem Ergebnis zurückgelesen und protokolliert (REQ-69). **10349** kommt in die Liste der behandelten Codes.
- **D-14:** Ob der Read-Only-Schalter im Gateway auch `whatIf` blockt, **muss die Research am Paper-Gateway messen** (REQ-67, mit Datum belegt). Falls er es blockt, wird SC2 angepasst. Der Schutz in Phase 4 ist dann die Socket-Sperre aus D-13 allein, und der Gateway-Schalter bleibt während Phase 4 aus. Die SC2-Änderung bestätigt der Operator im Verifikationsbericht der Phase 4, wie beim REQ-67-Override in Phase 2.
- **D-15:** Budget (REQ-70): `initMarginChange` (in Kontowährung EUR) muss kleiner sein als `AvailableFunds` aus dem Kontobericht (Phase 2). Andernfalls gibt es einen eigenen Zustand und Exit 5. Eine **feste Obergrenze pro Order** kommt erst mit den Leitplanken in Phase 5. Es gibt keine eigene Währungsrechnung.
- **D-16:** Alle Ablehnungen am `whatIf` enden mit **Exit 5 (`EXIT_REJECTED`)**, jeweils mit eigenem benanntem Zustand: leere oder unvollständige Vorschau (REQ-61: leere Liste, `None`, fehlende Margin- oder Kommissionsfelder), gesetztes `rejectReason` (REQ-38), Budget überschritten (D-15) und Fehler **154** = `halted` (Halt-Teil REQ-37). Vorbedingungen (`Hold`, `null`/`REVIEW`, `status != "ok"`, Divergenz, Aktualität, `state_maintenance`-Befund, fremde offene Order) bleiben **Exit 2**. `schema_version != 1` bleibt **Exit 1** (REQ-14).

### Claude's Discretion
- Name des Subkommandos (Vorschlag `preview`) und Aufruf in derselben Familie wie `account`/`resolve`: gleiche Settings, gleiches Log, gleiche Exit-Code-Tabelle.
- Format und Ort des Trockenlauf-Protokolls (JSON, atomar, unter `%LOCALAPPDATA%`), Konsolenzeile je Ticker im Stil von `resolve:`. Ausdrücklich **kein** Ledger (Phase 5).
- Namen der neuen Zustände (z. B. `skipped-hold`, `rating-review`, `run-not-ok`, `signal-divergence`, `stale-decision`, `foreign-open-order`, `within-tolerance`, `long-only-noop`, `preview-empty`, `preview-rejected`, `over-budget`, `halted`, `paper-log-unavailable`, `calendar-conflict`). Vorgabe: jeder Grund ist ein eigener benannter Zustand.
- Schnitt der neuen Adapter-Methoden (offene Orders, `preview_order`). **Achtung:** Der Adapter hat heute 5 öffentliche Methoden. `test_adapter_has_at_most_ten_public_methods` pinnt die Menge exakt und muss mitgezogen werden.
- Wie `resolve_all` (Phase 3) in den Lauf eingebunden wird. Der Ticker kommt aus der Entscheidung, nicht aus einer Default-Liste.
- Form des Vertragstests für die aus `summary.json` gelesenen Felder (SC7, REQ-14).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phasen-Scope und Anforderungen
- `.planning/ROADMAP.md` §„Phase 4" — Ziel, 8 Success Criteria, „Was diese Phase NICHT tut", Übergabe aus Phase 3; Traceability-Tabelle (REQ-69/70 → Phase 4)
- `.planning/REQUIREMENTS.md` — REQ-IBKR-13..25, -37 (Änderungsnotiz D-20), -38, -61, -67, -68, -69, -70

### Gemessene Wahrheit am Paper-Gateway
- `.planning/ibkr-marktdaten-befund.md` Befund 4 — `whatIf` braucht explizites `tif`, sonst 10349 und eine leere Liste; Margin in EUR, Kommission in USD (AAPL `initMarginChange=997.14`)
- `.planning/ibkr-konto-befund.md` §5 und Rohausgabe — `liquidHours` beginnt beim heutigen Tag und reicht etwa 5 Tage nach vorn (Grund für D-05); §„Read-Only" (Messung 321)

### Entscheidungsquelle und Produzent
- `tradingagents/memory/log.py` — `TradingMemoryLog.load_entries()` (:76), `_parse_entry` verwirft unvollständige Blöcke lautlos (:310)
- `scripts/state_maintenance.py` — `check_decision_log` (:141), `verify` (:177)
- `scripts/daily_paper_run.py` — `summary.json` mit `schema_version` (:508), `runs[]`-Felder `status`/`signal` (:354-375), `report`-Feld mit Runner-Pfad (REQ-18)
- `tradingagents/agents/rating.py` — `is_review` (:115), `RATING_REVIEW`-Sentinel
- `tradingagents/backtest.py` — `_DIRECTION` (:90): `Hold == 0`
- `.github/workflows/daily-paper-run.yml` — Zeitplan Di–Sa 06:30 UTC, Schreiber auf `paper-log`

### Vorphasen (gesperrte Muster)
- `.planning/phases/03-symbol-aufl-sung-handelbarkeit-und-handelszeiten/03-CONTEXT.md` — D-01 (Code-Konstanten-Tabelle), D-21..D-24 (Sitzung, Puffer, `session-unknown`), D-28/D-29 (Exit 2, `closed` = 0)
- `.planning/phases/03-symbol-aufl-sung-handelbarkeit-und-handelszeiten/03-REVIEW-FIX.md` — `REQUEST_FAILED` nur für `reqId >= 0`, Lock auf `contracts.json`
- `.planning/phases/02-verbindung-paper-guard-und-kontolesen/02-VERIFICATION.md` — Override-Muster (REQ-67) für die SC2-Anpassung aus D-14
- `scripts/IBKR_EXECUTION.md` — Betriebshandbuch, Exit-Tabelle, Zustandstabelle

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/ibkr_broker.py` `IbkrBroker`: `connect()` (Paper-Guard, `reqMarketDataType(3)`), `positions()` (liefert `AccountSnapshot` inkl. `AvailableFunds`, :505/:573), `search_contract`/`contract_details`, `_call` (Timeout, Link-Ereignisse, `REQUEST_FAILED`), Schreibsperre `_WRITE_MESSAGE_IDS = {3, 4, 19, 21, 58}` (:66, :289) — hier setzt D-13 an
- `scripts/ibkr_contracts.py`: `CONTRACT_TABLE`, `classify`, `resolve_all` (Broker und Uhr injiziert), `evaluate_session`, atomare Schreibhilfen `write_json_atomic`
- `scripts/ibkr_executor.py`: Subkommando-Muster (`account`, `resolve`), `_guarded` (gemeinsame Fehlerabbildung), Exit-Konstanten `EXIT_PRECONDITION=2`, `EXIT_REJECTED=5` (:60-69), Uhr nur über das `clock`-Keyword in `main`
- `tests/ibkr_fakes.py` `FakeIB`: `emit_during`, `details_calls`; muss um `whatIfOrder` bzw. `placeOrder`/`openOrders` erweitert werden

### Established Patterns
- Bibliotheksfreie Fachlogik (`ibkr_contracts.py`) getrennt vom einzigen Bibliothekskontakt (`ibkr_broker.py`); AST-Guards in `tests/test_ibkr_isolation.py` erzwingen das
- Keine Uhrzeit-Literale in `scripts/ibkr_*.py`, keine eigene Uhr im Fachmodul (Guards aus 03-04)
- Jeder Abweisungsgrund ist ein eigener benannter Zustand; eine Konsolenzeile pro Ticker; Details im Log
- Fehlercodes, auf die ein Test baut, sind vorher am Gateway gemessen (REQ-67)

### Integration Points
- Neues Subkommando in `scripts/ibkr_executor.py`
- Neue Lesemethode „offene Orders" und `preview_order` in `IbkrBroker`
- `CONTRACT_TABLE` bekommt `block_qty`
- `pyproject.toml`: neue Abhängigkeit `exchange_calendars`
- Konsumentenvertrag zu `scripts/daily_paper_run.py` (`summary.json`) als Test

</code_context>

<specifics>
## Specific Ideas

- SC1 ist der wichtigste Einzelnachweis: Der Trockenlauf gegen den **echten** Branchstand vom 2026-10-09 (AAPL, `Hold`) protokolliert `skipped: hold` und erzeugt nichts.
- Gate G2 prüft auf einen `OrderState` **mit Margin-Feldern**, nicht auf „kein Fehler" (Befund 4, Anforderung 2).
- Budget-Test vergleicht gegen den EUR-Wert aus dem Preview, nicht gegen ein selbst gerechnetes Produkt aus Stückzahl und USD-Kurs (REQ-70).

</specifics>

<deferred>
## Deferred Ideas

- Feste Größen-Obergrenze pro Order, Kill-Switch, Ledger mit Write-Ahead und Lock: Phase 5.
- Verrechnung **eigener** offener Orders in `Ziel − Ist − offen`: Phase 6, sobald der Lauf selbst sendet.
- Limit-Orders mit Preisfindung aus Marktdaten, Marktdaten-Abo: außerhalb M2 (REQ-26, Offener Punkt 1 im Marktdaten-Befund).
- 4-Block-Leiter (Underweight ≠ Sell): Erweiterungspfad, nicht M2.

</deferred>

---

*Phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev*
*Context gathered: 2026-10-12*
