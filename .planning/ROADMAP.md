# Roadmap — TradingEngineX (TradingAgents)

**Aktueller Meilenstein:** `M2 — IBKR Paper Execution` · Anforderungen in [REQUIREMENTS.md](./REQUIREMENTS.md) (68 IDs)
**Abgeschlossen:** Meilenstein „Produktionsreife v0.2.x → v0.2.5" — [MILESTONE.md](./MILESTONE.md). Bewusst offen geblieben: P2 #6 (Observability/Alerting, von M2 **teilweise** mitbedient) und P2 #8 (Provider-Ausfall-Policy, von M2 **nicht** berührt).

**Ziel von M2 in einem Satz:** Die Entscheidungen, die der tägliche Paper-Lauf heute protokolliert, werden gegen das IBKR-Paper-Konto `DUQ634065` tatsächlich ausgeführt, mit nachvollziehbarer Soll-Ist-Zusammenführung.

Keine Zeitschätzungen — dieses Projekt arbeitet ohne. Phasen sind Arbeitspakete mit einem prüfbaren Ende, keine Termine.

---

## Schnittprinzip

Vier Regeln haben den Zuschnitt bestimmt:

1. **Die riskanten Teile liegen vorn.** Verbindung, Paper-Guard und Symbol-Auflösung sind vollständig abgeschlossen und bewiesen, **bevor** die erste echte Order entsteht. Eine falsche Auflösung oder eine Paper/Live-Verwechslung erzeugt keine Exception, sondern plausible falsche Ergebnisse — das ist die Fehlerklasse, die man nicht hinterher bemerkt.
2. **Die erste echte Order steht hinter einem `whatIf`-Preview-Gate.** Phase 4 rechnet die Order vollständig aus, lässt sie von IBKR auf Margin, Kommission und `rejectReason` prüfen — und sendet sie nicht. Erst Phase 6 schaltet um.
3. **Jede Phase endet lauffähig.** Nach Phase 2 gibt es ein Kommando, das das Konto liest. Nach Phase 4 ein Kommando, das einen vollständigen Trockenlauf macht. Nach Phase 5 ein Kommando, das alle Leitplanken scharf durchläuft, ohne zu handeln. Keine Phase endet in einem Zustand, der nur mit der nächsten Phase einen Sinn ergibt.
4. **Alle vier Pflicht-Leitplanken sind vor der ersten Order scharf.** Keine wird „nachgezogen".

**Drei harte Gates:**

| Gate | Zwischen | Bedingung |
|---|---|---|
| **G1 — Messung** | Phase 1 → 2 | `.planning/ibkr-konto-befund.md` ist committet und beantwortet alle fünf Fragen aus REQ-IBKR-01. Ohne ihn beginnt kein Code. |
| **G2 — Preview** | Phase 4 → 5 | Für mindestens ein Fixture liegt ein `whatIf`-Protokoll mit Margin, Kommission und leerem `rejectReason` vor, und der Lauf hat nachweislich nichts gesendet. |
| **G3 — Leitplanken** | Phase 5 → 6 | Alle vier Leitplanken sind ohne Gateway testbar nachgewiesen (Kill-Switch-Test, Größen-Test, Sitzungs-Test, Reconciliation-Test). Erst danach wird das API-Schreibrecht freigegeben. |

---

## Phasen

- [x] **Phase 1: Konto-Messung und Gateway-Grundbetrieb** — messen, was am Konto wirklich gilt, bevor Code darauf baut (Operator-Aufgabe, kein Entwicklungsschritt; completed 2026-10-11)
- [x] **Phase 2: Verbindung, Paper-Guard und Kontolesen** — ein lokaler Prozess liest `DUQ634065` read-only und füllt `PortfolioContext` (completed 2026-10-12)
- [ ] **Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten** — vom Roh-Ticker zu genau einem Contract, oder begründet gar nicht
- [ ] **Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview** — vollständiger Trockenlauf, der nichts sendet
- [ ] **Phase 5: Leitplanken scharf** — Kill-Switch, Ledger, Lock, Reconciliation, ohne eine einzige Order
- [ ] **Phase 6: Die erste echte Order** — umschalten, platzieren, im Ledger wiederfinden
- [ ] **Phase 7: Rückkanal und Soll-Ist-Zusammenführung** — eigener Branch, Join beim Lesen
- [ ] **Phase 8: Unbeaufsichtigter Betrieb** — Scheduler, Heartbeat, lauter Ausfall

| Phase | Anforderungen | Status |
|---|---|---|
| 1. Konto-Messung | 2 | abgeschlossen |
| 2. Verbindung & Kontolesen | 12 | abgeschlossen |
| 3. Symbol & Handelszeiten | 7 | offen |
| 4. Entscheidung & Trockenlauf | 16 | offen |
| 5. Leitplanken | 15 | offen |
| 6. Erste echte Order | 5 | offen |
| 7. Rückkanal | 4 | offen |
| 8. Unbeaufsichtigter Betrieb | 7 | offen |

---

## Phase Details

### Phase 1: Konto-Messung und Gateway-Grundbetrieb

**Ziel:** Messen, was am Konto `DUQ634065` tatsächlich gilt, bevor eine Zeile Code auf einer Annahme aufsetzt.
**Depends on:** nichts
**Requirements:** REQ-IBKR-01, REQ-IBKR-02
**Warum das eine Phase ist und kein Nebensatz:** Ob der Paper-Login einen Zweitfaktor verlangt, ist offiziell **widersprüchlich** dokumentiert — IBKRs Aussagen betreffen die Enrollment-Pflicht auf Kontoebene, nicht den Prompt beim Login mit dem separaten Paper-Username, und die Community-Berichte widersprechen sich direkt. Diese eine Antwort entscheidet, ob unbeaufsichtigter Wochenbetrieb überhaupt möglich ist, also über den Zuschnitt von Phase 8. Sie ist in fünf Minuten am Konto messbar und durch keine weitere Recherche zu beschaffen. Dasselbe gilt für vier weitere Punkte, deren Doku nachweislich falsch oder widersprüchlich ist (`ineligibilityReasonList`-Felder, `reqExecutions`-Fenster, `orderRef`-Zeichen, `managedAccounts`-Inhalt).

**Success Criteria** (was wahr sein muss):

1. `.planning/ibkr-konto-befund.md` liegt committet im Repo und beantwortet alle fünf Fragen aus REQ-IBKR-01 — jeweils mit der **Rohausgabe**, nicht nur mit einer Zusammenfassung, und mit Datum.
2. Die 2FA-Frage ist mit „ja" oder „nein" beantwortet, und der Befund enthält den daraus abgeleiteten Satz zur Betriebsform („Wochenlogin automatisierbar" oder „ein manueller Quittierungsvorgang pro Woche").
3. Das IB Gateway läuft im Paper-Modus, der API-Port auf `127.0.0.1:4002` antwortet, und `managedAccounts` ist wörtlich notiert.
4. Für `AAPL` stehen `conId`, `primaryExchange`, `currency`, `localSymbol`, `validExchanges`, `ineligibilityReasonList` und das `tradingHours`/`liquidHours`/`timeZoneId`-Tripel im Rohformat im Befund; für je ein Exemplar von `IND`, `FUT`, `CMDTY`, `CASH`, `CRYPTO` entweder dasselbe oder die Fehlermeldung, die stattdessen kam.
5. ~~Read-Only ist noch **an**, Platzierungsversuch scheitert mit **10015**~~ — **erfüllt am 2026-10-11, mit zwei Korrekturen:** der reale Marker ist **321** („Die API befindet sich im schreibgeschützten Modus", Order-Status `ValidationError`) — **gemessen 2026-10-11 an Gateway 10.50.1**; der in der Recherche erwartete Code **10015** trat nicht auf; und Read-Only war am Gateway **nicht** voreingestellt, sondern aus (erste Probe wurde angenommen und sofort storniert). Siehe [ibkr-konto-befund.md](./ibkr-konto-befund.md).

**Was diese Phase NICHT tut:**

- Keine Zeile Ausführungscode, kein Adapter, keine Abhängigkeitsänderung.
- Keine Order, auch keine `whatIf`-Order (das Preview gehört in Phase 4, wo die Mengenrechnung existiert).
- Keine Entscheidung über das Signal→Order-Mapping — das ist in REQUIREMENTS.md bereits gesetzt und wird hier nicht neu aufgerollt.
- Keine Gateway-Dauerbetriebseinstellung (Auto-Restart, `ClosedownAt`, Scheduler) — das ist Phase 8.

**Plans:** keine (Operator-Phase, kein Entwicklungsschritt)

---

### Phase 2: Verbindung, Paper-Guard und Kontolesen

**Ziel:** Ein lokaler Prozess verbindet sich reproduzierbar gegen `DUQ634065`, beweist beim Verbinden, dass es das Paper-Konto ist, und legt Bestand und freies Kapital als `PortfolioContext`-JSON ab — ohne Schreibrecht.
**Depends on:** Phase 1 (Gate G1)
**Requirements:** REQ-IBKR-03, -04, -05, -06, -07, -08, -09, -11, -12, -55, -62, -67

**Success Criteria:**

1. Ein Kommando liest gegen das laufende Gateway Positionen und Cash und schreibt ein JSON, das `tradingagents.portfolio.load_portfolio()` ohne Fehler validiert; Exit 0.
2. Der Paper-Guard ist bewiesen, nicht behauptet: ein Stub, der eine abweichende Kontomenge liefert, führt zu Exit 8, zu einer Trennung und zu keinem einzigen Platzierungsaufruf.
3. Ohne laufendes Gateway endet der Lauf mit Exit 3 und einer Logzeile, die den Zustand benennt (502 / „Gateway nicht erreichbar") — nicht mit einem Traceback. Fehlende Zugangsdaten ergeben Exit 20.
4. Eine Suche nach `ib_async` in `tradingagents/` und `scripts/` nennt genau eine Datei, und dieser Adapter hat höchstens zehn öffentliche Methoden.
5. Die Liveness-Prüfung hängt an einer **echten Antwort** auf einen Probe-Request, nicht am Socket-Status; ein Test mit „Socket oben, Session tot" liefert „nicht gesund".
6. `ib_async==2.1.0` und der `tzdata>=2025.2,<2026.0`-Pin lösen in einer frischen Umgebung auf; `ib_async==2.1.0` **zusammen mit dem aktuellen `tzdata>=2026.1`** ist reproduzierbar unauflösbar (`pip install --dry-run` → `ResolutionImpossible`) — damit ist der Deckel dokumentiert statt entdeckt. *Korrigiert 2026-10-11: Ohne den eigenen Pin löst es weiter auf, weil `ib_async` 2.1.0 die Obergrenze `tzdata<2026.0` selbst in seinen Metadaten trägt; der eigene Pin macht sie nur sichtbar.*
7. Ein **lokaler** Lauf von `scripts/daily_paper_run.py` mit dem erzeugten Portfolio-JSON zeigt den Positionsblock aus `PortfolioContext.render()` im Report — der Beweis, dass das Kontolesen die Analysequalität verbessert und nicht nur die Mengenrechnung bedient.
8. `git ls-files .env` ist leer, und in `.github/workflows/` steht keine IBKR-Secret-Referenz.

**Was diese Phase NICHT tut:**

- Keine Order und kein `whatIf`; die Verbindung läuft durchgehend mit `readonly=True`.
- Keine Symbol-Auflösung über das hinaus, was zum Lesen der Positionen nötig ist (die eigene Auflösungskette ist Phase 3).
- Kein Lesen von `paper-log`, keine Entscheidungsübernahme.
- **Keine Änderung am CI-Produktivpfad.** Das Portfolio-JSON wird in dieser Phase nur lokal übergeben; die Verdrahtung in den täglichen Lauf braucht den Veröffentlichungsbranch und passiert in Phase 7.

**Plans:** 6/6 plans complete

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Extra `ibkr` mit Pin + Kommentar, Kriterium 6 umformuliert, CI-/`.env`-Wächter, Paket-Freigabe, `.venv` aufgefrischt, Pin-Deckel gemessen

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Adapter `scripts/ibkr_broker.py`: Schreibsperre vor dem Connect, Paper-Guard, Zustandstabelle, Liveness-Probe, frisches Konto-Lesen (Fake-IB)
- [x] 02-03-PLAN.md — `--portfolio` in `daily_paper_run.py` + additiver Portfolio-Block in `reporting._header`

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — Kommando `scripts/ibkr_executor.py account`: Exit-Codes, `.env`, UTF-8-Log, atomares JSON + Gegenprobe; Handbuch `scripts/IBKR_EXECUTION.md`

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-05-PLAN.md — Operator-Checkpoint Read-Only an, echter `account`-Lauf gegen DUQ634065, Abnahme

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 02-06-PLAN.md — Preflight mit echtem JSON, Operator-Checkpoint echter Paper-Lauf mit `--portfolio`

---

### Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten

**Ziel:** Jeder Roh-Ticker wird auf genau einen IBKR-Contract aufgelöst oder begründet abgewiesen, und „ist jetzt Sitzung?" wird aus den Contract-Daten beantwortet statt aus einer hart kodierten Uhrzeit.
**Depends on:** Phase 2
**Requirements:** REQ-IBKR-26, -27, -28, -29, -30, -31, -37
**Warum vor der ersten Order:** Das ist die fünfschichtige Kette gegen die gefährlichste Fehlerklasse dieses Meilensteins — eine falsche Auflösung wirft keine Exception, sie kauft etwas Handelbares mit falschem Nominal und füllt das Decision-Log mit Returns, die zu einer anderen Position gehören als die Entscheidung.

**Success Criteria:**

1. `AAPL`, `MSFT`, `NVDA` lösen auf genau einen Contract auf, und `conId`, `primaryExchange`, `currency`, `localSymbol` stimmen mit dem Befund aus Phase 1 überein; der `conId` ist persistiert und wird ab dem zweiten Lauf als Auflösungsweg benutzt.
2. Ein nicht gemappter Roh-Ticker (`XYZQ`) wird abgewiesen, **ohne** „SMART/USD zu probieren"; ein gemappter Nicht-`STK`-Ticker (`^GSPC`, `XAUUSD+`) wird mit Verweis auf die Allow-List abgewiesen.
3. Ein künstlich mehrdeutiger Request führt zum Abbruch, und die Kandidatenliste aus `returnAll=True` steht im Log — nicht nur im Bibliotheks-Log.
4. Ein manipulierter persistierter `conId` (gleiches Symbol, andere Zahl) führt zu einer Meldung und keiner Auflösung.
5. Die Auflösung setzt nachweislich am **Roh-Ticker** an: ein Test belegt, dass `XAUUSD+` nicht über `normalize_symbol()` zu `GC=F` wird, und dass die IBKR-Auflösung und die Vendor-Normalisierung zwei getrennte Pfade sind.
6. „Ist jetzt Sitzung?" wird aus `liquidSessions()` beantwortet; Tests decken einen `CLOSED`-Tag, einen Halbtag und **beide** Datumsschreibweisen des Rohformats (`20261001:0400-20261001:2000` und das Alt-Format `20090507:0700-1830`) ab. Der Cache verfällt nach höchstens einem Handelstag.
7. Eine Suche nach hart kodierten Handelszeiten (`13:30`, `14:30`, `09:30`, `16:00`) im Ausführungscode ist leer.
8. `reqMarketDataType(3)` ist gesetzt, und 10089/10090 erscheinen im Log als erwarteter Zustand, nicht als Fehler.

**Was diese Phase NICHT tut:**

- Keine Order, kein `whatIf`, keine Mengenrechnung.
- Keine Entscheidung von `paper-log` gelesen.
- Keine Marktdaten über den delayed-Default hinaus; kein Limitpreis, keine Preisabfrage im Order-Pfad.
- Keine Erweiterung der Allow-List über `STK` hinaus — die breitere Liste ist dokumentierter Erweiterungspfad.

**Plans:** 4/6 plans executed

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Bibliotheksfreies Modul `ibkr_contracts.py`: Tabelle, Allow-List, Zustände, Handelbarkeit, Identität, Sitzungs-Parser (Wave 1)
- [x] 03-02-PLAN.md — Adapter: `search_contract`/`contract_details`, `reqMarketDataType(3)` nach Guard, 10167 + Delayed-Codes auf INFO, Fakes (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-03-PLAN.md — Persistenz `contracts.json` + History, `resolve_all` (Lernen, Gegenprobe, Drift, init-Anker, rebaseline) (Wave 2)
- [x] 03-04-PLAN.md — Guards D-07/SC7/Uhr-Injektion, REQ-IBKR-31 nach D-19 umformuliert (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 03-05-PLAN.md — Subkommando `ibkr_executor.py resolve` mit Exit 2, Connect-on-demand, `--init`/`--rebaseline`/`--out` (Wave 3)

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 03-06-PLAN.md — Handbuch `resolve`/neuer Ticker, echter Gateway-Lauf, Operator-Abnahme (Wave 4)

---

### Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview

**Ziel:** Aus der Entscheidung auf `paper-log` entsteht eine vollständig geprüfte, von IBKR vorab bewertete Order-Absicht — die der Lauf nachweislich nicht sendet.
**Depends on:** Phase 3
**Requirements:** REQ-IBKR-13, -14, -15, -16, -17, -18, -19, -20, -21, -22, -23, -24, -25, -38, -61, -68
**Übergabe aus Phase 3:** Halt-Teil von REQ-IBKR-37 — Fehler 154 am `whatIf` verhindert die Order-Absicht und wird als eigener Zustand protokolliert (Phase 3 sieht nur den Zustand `halted` in der Ergebnisschnittstelle vor, D-20).

**Success Criteria:**

1. Der Trockenlauf gegen den **echten** Branchstand vom 2026-10-09 (AAPL, `Hold`) erzeugt keine Order und protokolliert `skipped: hold`. Das ist der wichtigste Einzelnachweis dieser Phase: die eine reale Entscheidung im Bestand darf am Tag 1 nichts kaufen.
2. Ein Fixture mit `Buy` und flacher Position erzeugt die Absicht „2 Blöcke kaufen", durchläuft `whatIf` und protokolliert Margin-Impact, Kommission und `rejectReason` — und sendet nichts; ein versehentliches `place` scheitert in dieser Phase an 321 — aber nur, solange der Operator den Gateway-Schreibschutz gesetzt hat (am 2026-10-11 war er wieder aus).
3. Der Divergenzfall ist abgedeckt: ein Fixture, in dem `summary.json` ein anderes Signal zeigt als `decision-log.md`, endet mit Exit 2 und protokollierter Abweichung — und der Lauf hat die Fassung aus `decision-log.md` gelesen, nicht die aus dem Summary.
4. Die Aktualitätsregel ist **in Sitzungen** getestet, mit allen vier Gegenproben: Di-Lauf/`trade_date`=Mo → ausführbar · Sa-Entscheidung am Mo → ausführbar, markiert als `weekend_gap` · Mi verpasst, Do nachgeholt → Exit 2 · Feiertagsmontag, Di-Lauf → ausführbar.
5. `null`, `"REVIEW"`, `status != "ok"`, `schema_version != 1` und ein Befund von `state_maintenance.py verify` führen jeweils zu einem eigenen protokollierten Zustand und zu keiner Order.
6. Das Toleranzband greift: ein Fixture mit `Ziel − Ist` unterhalb eines Blocks erzeugt keine Order; offene Orders gehen in die Differenz ein (`Ziel − Ist − offen`).
7. Ein Vertragstest hält die aus `summary.json` gelesenen Felder fest und schlägt bei einer nicht-additiven Änderung an `scripts/daily_paper_run.py` fehl — der Konsumentenvertrag ist heute unbewacht.
8. Ein `Sell` ohne Bestand ist eine protokollierte Nulloperation und kein Short.

**Was diese Phase NICHT tut:**

- Kein `placeOrder`. Gate **G2** ist genau diese Grenze.
- Kein Kill-Switch, keine Größen-Obergrenze, keine Reconciliation — die Leitplanken sind Phase 5, und bis dahin ist Read-Only der Schutz.
- Das Trockenlauf-Protokoll ist **noch nicht** der Ledger, auf den sich Idempotenz stützt: es gibt in dieser Phase keine Write-Ahead-Disziplin und keinen Lock.
- Kein Push auf irgendeinen Branch, kein Heartbeat.

**Plans:** TBD

---

### Phase 5: Leitplanken scharf

**Ziel:** Die vier Pflicht-Leitplanken sind scharf und ohne eine einzige Order bewiesen.
**Depends on:** Phase 4 (Gate G2)
**Requirements:** REQ-IBKR-32, -33, -34, -35, -36, -39, -40, -41, -42, -43, -44, -46, -63, -64, -66
**Warum eigene Phase:** Alle Nachweise dieser Phase sind **ohne** Gateway führbar (Stub nach dem Muster von `scripts/smoke/stub_llm.py`) bzw. read-only. Eine Leitplanke, die erst nach der ersten echten Order geprüft wird, ist keine Leitplanke.

**Success Criteria:**

1. Fail-closed ist in allen drei Varianten bewiesen: Freigabe fehlt · Kill-Datei vorhanden · Zustand nicht lesbar → jeweils Exit 4, kein Platzierungsaufruf, Schalterzustand protokolliert.
2. Ein Test, der den Kill-Switch **zwischen** zwei Orders eines Laufs aktiviert, weist nach, dass die zweite Order nicht entsteht — die Prüfung sitzt unmittelbar vor jeder einzelnen Order, nicht einmal pro Lauf.
3. Bei aktivem Kill-Switch wird `reqGlobalCancel` aufgerufen; nachgewiesen gegen den Stub und einmal gegen das Gateway mit einer manuell in TWS platzierten Order, die danach storniert ist.
4. Eine Order über `MAX_QTY_PER_ORDER` wird **abgelehnt und gemeldet**, nicht gekürzt.
5. Der Ledger ist JSONL, liegt außerhalb jedes Git-Arbeitsbaums, und `git status` ist nach einem Lauf leer — kein `.lock`-Sidecar im Baum (der Gegenbeweis liegt heute als committetes `decision-log.md.lock` auf `paper-log`).
6. Write-Ahead ist bewiesen: ein künstlich abgebrochener Lauf hinterlässt einen `intent`-Eintrag, und der nächste Lauf löst ihn gegen alle drei Broker-Quellen (`reqAllOpenOrders`, `reqCompletedOrders`, `reqExecutions`) auf, **bevor** eine neue Order entsteht; ein unauflösbarer `intent` bricht mit Exit 6 ab.
7. Zwei gleichzeitig gestartete Läufe: der zweite endet mit Exit 7 ohne Order; ein `OSError` beim Sperrversuch führt zu „nicht ausführen", nicht zu einem Absturz.
8. `decision_key` steht als `orderRef` in der (noch nicht gesendeten) Order, und der gelesene `paper-log`-SHA steht als Provenienz im Ledger-Eintrag; eine zweite, abweichende Fassung derselben `(trade_date, ticker)`-Entscheidung wird protokolliert und nicht ausgeführt.

**Was diese Phase NICHT tut:**

- Keine echte Order; das Schreibrecht bleibt gesperrt.
- Keine Fill-Verarbeitung (es gibt noch keine Fills).
- Kein Branch, kein Heartbeat, kein Scheduler.
- Keine Backup-Erweiterung — die kommt mit Phase 7, wenn der Ledger seine endgültige Form hat.

**Plans:** TBD

---

### Phase 6: Die erste echte Order

**Ziel:** Eine echte Markt-Order gegen `DUQ634065` wird platziert, gefüllt und vollständig im Ledger wiedergefunden — und ein zweiter Lauf am selben Tag erzeugt keine zweite.
**Depends on:** Phase 5 (Gate G3)
**Requirements:** REQ-IBKR-10, -45, -47, -48, -65
**Diese Phase ist bewusst klein: sie schaltet um, sie baut nicht.** Dass hier nur vier Anforderungen liegen, ist das Ergebnis des Zuschnitts und kein Versehen — alles, was eine Order riskant macht, ist in den Phasen 2 bis 5 abgeschlossen.

**Success Criteria:**

1. Die Freischaltung des API-Schreibrechts ist mit Datum, Grund und Vorher-/Nachher-Zustand im Betriebshandbuch notiert, und der gesperrte Zustand ist vorher über Fehler 321 belegt.
2. Die Prüfkette läuft an genau einer Stelle und in der festgelegten Reihenfolge (Lock → Reconciliation → Quellen/Integrität → Aktualität → Auflösung/Handelbarkeit → Menge → Größe → Handelszeit → Kill-Switch → `whatIf` → `intent` → platzieren); ein Test prüft die **Aufrufreihenfolge** gegen einen Stub-Broker, nicht nur das Ergebnis.
3. Eine echte Markt-Order über einen Block ist platziert, und der Ledger zeigt die vollständige Kette `intent → placed → filled` mit `orderId`, `permId`, `orderRef == decision_key`, `execId`(s), `filled_qty` und `avg_price`.
4. Die Position im Konto entspricht dem Ziel der Leiter, und ein **zweiter Lauf am selben Tag** erzeugt keine zweite Order — Toleranzband, Ledger-Guard und Reconciliation greifen nachweislich zusammen.
5. Die `execId`-Korrekturregel ist belegt: eine `execId`, die bis auf die Ziffern nach dem letzten Punkt mit einer früheren identisch ist, **ersetzt** den Eintrag statt zu addieren — gegen echte Daten, falls eine Korrektur auftritt, sonst gegen ein Fixture aus der Rohform des Konto-Befunds.
6. Executions und abgeschlossene Orders des Handelstags sind **am selben Tag** persistiert; ein Lauf am Folgetag braucht sie nicht mehr abzufragen (das Broker-Fenster gibt sie dann nicht mehr her).
7. Ein `whatIf` mit gesetztem `rejectReason` verhindert die Order auch im scharfen Pfad — nachgewiesen, indem die Order bewusst über ein Limit getrieben wird, das IBKR ablehnt (z. B. Größen-/Margin-Grenze), und der Lauf mit Exit 5 endet.

**Was diese Phase NICHT tut:**

- Kein Scheduler, kein Push, kein Heartbeat, kein Soll-Ist-Bericht.
- Keine Limit-Order; Markt-Order im Sitzungsfenster bleibt der einzige Pfad.
- Kein zweiter oder dritter Ticker zwingend — ein Durchstich genügt, die Mechanik ist tickerunabhängig.
- Keine Ausweitung der Leiter und keine Änderung der Blockgröße „weil es gut lief".

**Plans:** TBD

---

### Phase 7: Rückkanal und Soll-Ist-Zusammenführung

**Ziel:** Soll und Ist stehen in einem Bericht nebeneinander, ohne dass ein Prozess in den Branch eines anderen schreibt.
**Depends on:** Phase 6
**Requirements:** REQ-IBKR-49, -50, -51, -52

**Success Criteria:**

1. Der Ausführer veröffentlicht auf einem eigenen Branch, den ausschließlich er schreibt; nach einem Ausführungslauf zeigt `paper-log` **keinen** neuen Commit vom lokalen Prozess. Die Invariante „ein Schreiber pro Branch" ist im Handbuch als Invariante benannt, nicht als Gewohnheit.
2. Ein Berichtsskript liest beide Branches und erzeugt eine Tabelle über `(trade_date, ticker)` mit Rating, Zielposition, Ist-Position, Ordermenge, Fill-Menge, Durchschnittspreis, Abweichung Ziel↔Ist und `weekend_gap`-Markierung — der Join passiert beim **Lesen**, kein Prozess schreibt dafür woanders hin.
3. Der Bericht trennt Ausführungsmetriken (Slippage, Fill-Quote, Abweichung) sichtbar von Entscheidungsmetriken (realisierter Return, Alpha) — zwei Tabellen oder zwei klar getrennte Spaltengruppen — und trägt den Hinweis, dass Paper-Fills aus Top-of-Book-Simulation stammen und systematisch nach oben verzerrt sind.
4. `state_maintenance.py backup --dry-run` listet Ledger und Contract-Cache; vor der Änderung tat es das nicht (die Allow-Liste war auf `decision-log.md`, `index.md`, `runs/**` und das CLI-Log begrenzt).
5. Duplikate werden beim Lesen dedupliziert — der Branch enthält `2026-10-09 | AAPL` dreifach in `index.md`, und der Bericht zeigt eine Zeile.
6. Die Analyse liest das Portfolio-JSON vom Veröffentlichungsbranch und bekommt es als `portfolio` übergeben; **fehlt die Datei, verhält sich der Lauf exakt wie heute** (fail-open). Das ist die einzige Berührung des Produktivpfads in diesem Meilenstein, sie ist additiv, read-only und ohne neue Fehlerquelle.

**Was diese Phase NICHT tut:**

- Kein Schreiben auf `paper-log` und keine Änderung an dessen Commit-Schritt (`fetch --depth=1` → `reset --hard` → `push` ohne Rebase/Retry bleibt, wie es ist — ein zweiter Schreiber kostet im Konflikt einen ganzen Entscheidungstag).
- Keine Alpha-/Backtest-Auswertung aus Fills.
- Kein Alarm — der Bericht ist eine Lesefunktion, die Alarmierung ist Phase 8.

**Plans:** TBD

---

### Phase 8: Unbeaufsichtigter Betrieb

**Ziel:** Der Lauf trägt sich über eine Woche ohne Eingriff, und sein Ausfall wird laut statt still.
**Depends on:** Phase 7
**Requirements:** REQ-IBKR-53, -54, -56, -57, -58, -59, -60

**Success Criteria:**

1. Der Task-Scheduler-Task ist mit den festgelegten Einstellungen eingerichtet und als Export (`schtasks /query /xml`) im Handbuch dokumentiert; „Run whether user is logged on or not" ist **nicht** gesetzt, „Do not start a new instance" ist gesetzt.
2. Jeder Lauf pusht einen Heartbeat — nachgewiesen für drei Fälle: normaler Lauf, „nichts zu tun" (Hold/Toleranzband), „Gateway nicht erreichbar".
3. Ein CI-Cron, der **nur** den Veröffentlichungsbranch liest, wird rot, wenn der Heartbeat älter als die erwartete Kadenz ist; nachgewiesen mit einem künstlich alten Heartbeat. Der Job hat keine Secrets, und `gh`-seitig ist belegt, dass er keine braucht.
4. Ein verpasster Lauf (Rechner aus) ist im Ledger als Lücke sichtbar, und der nächste Lauf stellt die Zielposition der **aktuellen** Entscheidung her, statt etwas nachzuholen — der Catch-up-Fall ist einmal real durchlaufen und protokolliert.
5. Die Task-History ist aktiviert, und „Last Run Result" zeigt den Exit-Code des Ausführers.
6. Eine Woche Betrieb ist mit Datum, Zahl der Läufe, Zahl der Orders und dem Zeitpunkt des Wochenlogins im Handbuch protokolliert; der Wochenwechsel (Samstagnacht-Reset, Montag neuer Zyklus) ist mindestens einmal durchlaufen, und das Fehlerbild eines vergessenen Logins (`Soft token=0 …` / 1100 / 502) ist mit seiner Behebung notiert.
7. `scripts/IBKR_EXECUTION.md` existiert und deckt Einrichtung, Gateway- und Scheduler-Einstellungen, die Exit-Code-Tabelle, Bedienung des Kill-Switch, das Wochenlogin-Ritual, die typischen Fehlerbilder und den Soll-Ist-Bericht ab.

**Was diese Phase NICHT tut:**

- Keine Erweiterung auf neue Instrumentenklassen, keine größere Leiter, kein Live-Konto.
- **Keine vollständige Lösung von P2 #6.** Dieser Meilenstein liefert den Heartbeat-Kanal samt Alarm für die *Ausführungsseite*. Metriken und Alerting für die *Analyseseite* (Vendor-Ausfälle, Fehlerraten, Latenz, Kosten je Run) bleiben offen und sind in MILESTONE.md weiter als offen zu führen.
- Keine Berührung von P2 #8 (Provider-Ausfall-Policy). Für den Ausführer ist ein ausgefallener Analyselauf „keine Entscheidung für heute" und damit ein normaler, protokollierter Zustand.
- Kein IBC-Einbau, außer die Messung aus Phase 1 hat „kein Zweitfaktor" ergeben; dann ist es eine explizite, eigene Entscheidung am Ende dieser Phase und keine stille Erweiterung.

**Plans:** TBD

---

## Coverage: REQ-ID → Phase

Alle 70 Anforderungen aus [REQUIREMENTS.md](./REQUIREMENTS.md) sind genau einer Phase zugeordnet. Keine ID fehlt, keine ist doppelt.

| REQ-ID | Kurztitel | Phase |
|---|---|---|
| REQ-IBKR-01 | Messung am Konto (fünf Fragen, schriftlich) | 1 |
| REQ-IBKR-02 | 2FA-Ausgang entscheidet die Betriebsform | 1 |
| REQ-IBKR-03 | Gateway Paper, Paper-Username, `.env`, read-only bis zur ersten Order | 2 |
| REQ-IBKR-04 | Paper-Guard `managedAccounts == {"DUQ634065"}` | 2 |
| REQ-IBKR-05 | Credentials nur lokal, CI credential-frei | 2 |
| REQ-IBKR-06 | `ib_async==2.1.0` + `tzdata`-Pin mit benanntem Grund | 2 |
| REQ-IBKR-07 | Adapter mit ≤ 10 Methoden, einziger `ib_async`-Importort | 2 |
| REQ-IBKR-08 | Fester `clientId`, Order-IDs ab `nextValidId` | 2 |
| REQ-IBKR-09 | Betriebszustände benannt, Liveness über Probe-Antwort | 2 |
| REQ-IBKR-10 | Schreibrecht als dokumentierte Einmalhandlung (Marker 321) | 6 |
| REQ-IBKR-11 | Kontolesen füllt `PortfolioContext` für die Analyse | 2 |
| REQ-IBKR-12 | Ist-Position bei jedem Lauf frisch vom Broker | 2 |
| REQ-IBKR-13 | Lesequelle ist genau `decision-log.md` | 4 |
| REQ-IBKR-14 | `schema_version == 1` + Vertragstest | 4 |
| REQ-IBKR-15 | `state_maintenance verify` als Vorbedingung | 4 |
| REQ-IBKR-16 | Nur `status == "ok"` + fünf Stufen; `null`/`REVIEW` nie | 4 |
| REQ-IBKR-17 | Querprobe Log-Rating gegen Summary-`signal` | 4 |
| REQ-IBKR-18 | Kein Zugriff auf `runs[*].report` (Runner-Pfad) | 4 |
| REQ-IBKR-19 | Aktualitätsregel in Sitzungen, nicht in Stunden | 4 |
| REQ-IBKR-20 | Freitag→Montag als `weekend_gap` markiert | 4 |
| REQ-IBKR-21 | Zielpositions-Leiter; `Hold` erzeugt nie eine Order | 4 |
| REQ-IBKR-22 | Block = konfigurierte feste Stückzahl, kein Kurs | 4 |
| REQ-IBKR-23 | `Ziel − Ist − offen` mit Toleranzband | 4 |
| REQ-IBKR-24 | long-only, `Sell` ohne Bestand ist Nulloperation | 4 |
| REQ-IBKR-25 | Markt-Order im Sitzungsfenster; Limit nur mit TIF `DAY` | 4 |
| REQ-IBKR-26 | Marktdaten außerhalb des Order-Pfads, `reqMarketDataType(3)` | 3 |
| REQ-IBKR-27 | Auflösung vom Roh-Ticker, nicht über `normalize_symbol()` | 3 |
| REQ-IBKR-28 | Allow-List `{STK}`, Unbekanntes wird abgewiesen | 3 |
| REQ-IBKR-29 | `qualifyContracts(returnAll=True)`, genau ein Treffer | 3 |
| REQ-IBKR-30 | `conId` persistiert + Identitätsvergleich | 3 |
| REQ-IBKR-31 | `validExchanges` ≠ nur `VALUE`, enthält `SMART`; `orderTypes` ⊇ `MKT`,`LMT` (D-19) | 3 |
| REQ-IBKR-32 | `[L1]` Harte Obergrenze pro Order, keine Kürzung | 5 |
| REQ-IBKR-33 | `[L2]` Kill-Switch fail-closed | 5 |
| REQ-IBKR-34 | `[L2]` Prüfung vor jeder einzelnen Order | 5 |
| REQ-IBKR-35 | `[L2]` `reqGlobalCancel` als scharfer Arm | 5 |
| REQ-IBKR-36 | `[L2]` Schalterzustand in jedem Lauf protokolliert | 5 |
| REQ-IBKR-37 | `[L3]` Sitzungsfenster aus `ContractDetails`; `HALTED`/154 am `whatIf` in Phase 4 (D-20) | 3 |
| REQ-IBKR-38 | `whatIf`-Preview vor jeder echten Order | 4 |
| REQ-IBKR-39 | `[L4]` `decision_key` aus `trade_date` und Ticker, kein SHA | 5 |
| REQ-IBKR-40 | `[L4]` Ein Versuch pro Schlüssel, erste Fassung gewinnt | 5 |
| REQ-IBKR-41 | `[L4]` `orderRef` trägt den Schlüssel, SHA als Provenienz | 5 |
| REQ-IBKR-42 | `[L4]` Write-Ahead-Zustände mit Grund bei `skipped` | 5 |
| REQ-IBKR-43 | `[L4]` Startup-Reconciliation über alle drei Quellen | 5 |
| REQ-IBKR-44 | `[L4]` Einzelinstanz über `locked(..., wait=False)` | 5 |
| REQ-IBKR-45 | Prüfkette an einer Stelle, Reihenfolge getestet | 6 |
| REQ-IBKR-46 | Ledger-Hygiene: JSONL, außerhalb Git, keine Sidecars | 5 |
| REQ-IBKR-47 | `execId`-Dedup mit Korrekturregel | 6 |
| REQ-IBKR-48 | Executions tagesgleich persistiert | 6 |
| REQ-IBKR-49 | Soll-Ist-Join beim Lesen über `(trade_date, ticker)` | 7 |
| REQ-IBKR-50 | Ausführungs- und Entscheidungsmetriken getrennt | 7 |
| REQ-IBKR-51 | Backup-Allow-Liste um Ledger + Contract-Cache erweitert | 7 |
| REQ-IBKR-52 | Kein Schreiben auf `paper-log`, ein Schreiber pro Branch | 7 |
| REQ-IBKR-53 | Heartbeat bei jedem Lauf, auch im Fehlerfall | 8 |
| REQ-IBKR-54 | CI-Cron prüft Heartbeat-Alter, ohne Credentials | 8 |
| REQ-IBKR-55 | Disjunkte Exit-Codes + UTF-8-Logdatei | 2 |
| REQ-IBKR-56 | Task-Scheduler-Einstellungen, kein Dienst | 8 |
| REQ-IBKR-57 | Vorbedingungen selbst prüfen, nicht die Startzeit glauben | 8 |
| REQ-IBKR-58 | Task-History aktiviert und dokumentiert | 8 |
| REQ-IBKR-59 | Gateway-Dauerbetrieb + Wochenlogin als Betriebsaufgabe | 8 |
| REQ-IBKR-60 | Betriebshandbuch `scripts/IBKR_EXECUTION.md` | 8 |
| REQ-IBKR-61 | Leere/unvollständige `whatIf`-Antwort = Ablehnung | 4 |
| REQ-IBKR-62 | Timeout auf jedem API-Aufruf, benannter Fehlerzustand | 2 |
| REQ-IBKR-63 | Zwei unabhängige Quellen je sicherheitskritischem Fakt | 5 |
| REQ-IBKR-64 | Kill-Switch fail-closed, vor jeder Order geprüft | 5 |
| REQ-IBKR-65 | Nach der Order gegen IBKR verifizieren | 6 |
| REQ-IBKR-66 | Negativ-Kontrolle je Schutzmaßnahme | 5 |
| REQ-IBKR-67 | Fehlercodes gemessen, nicht angenommen | 2 |
| REQ-IBKR-68 | Stückzahlen statt geschätzter Größen ohne Kurs | 4 |
| REQ-IBKR-69 | `tif` explizit setzen und zurücklesen (sonst kommt `whatIf` leer) | 4 |
| REQ-IBKR-70 | Budgetprüfung über `initMarginChange` in Kontowährung | 4 |

**Gegenprobe:** 68 IDs vergeben (`REQ-IBKR-01` … `REQ-IBKR-68`; -61 … -68 am 2026-10-12 aus dem Sicherungsprinzip `quick/261012-ap2` übernommen), 68 Zeilen in dieser Tabelle, Summe über die Phasenspalte 2 + 12 + 7 + 16 + 15 + 5 + 4 + 7 = **68**. Keine Anforderung ohne Phase, keine Phase ohne Anforderung. REQ-IBKR-62, -66 und -67 stehen bei der Phase, in der sie zuerst nachgewiesen werden, gelten aber in jeder späteren Phase weiter.

**Zwei Anforderungen wirken über ihre Phase hinaus** — das ist Absicht und keine Doppelzuordnung:

- **REQ-IBKR-11** (Kontolesen → `PortfolioContext`) wird in Phase 2 erzeugt und lokal nachgewiesen; die Verdrahtung in den täglichen CI-Lauf ist ein Erfolgskriterium von Phase 7, weil sie den Veröffentlichungsbranch braucht.
- **REQ-IBKR-37** (Sitzungsfenster) entsteht in Phase 3 als Abfrage und wird in Phase 6 Teil der scharfen Prüfkette (REQ-IBKR-45); der Halt-Teil (Fehler 154) wird in Phase 4 am `whatIf` abgefangen (D-20 der Phase 3).

---

## Historie

Der Vorgänger-Meilenstein „Produktionsreife v0.2.x → v0.2.5" ist in [MILESTONE.md](./MILESTONE.md) dokumentiert und wurde über Quick-Tasks umgesetzt (`.planning/quick/`), ohne Phasenzuschnitt — angemessen für ein Bestandsprojekt mit externem Upstream. M2 bekommt einen Phasenzuschnitt, weil hier erstmals **neuer** Code mit Kapitalwirkung entsteht und die Reihenfolge der Nachweise sicherheitsrelevant ist.
