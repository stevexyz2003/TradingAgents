# Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Jeder Roh-Ticker wird auf **genau einen** IBKR-Contract aufgelöst oder mit benanntem Grund abgewiesen. Identität (`conId`, `primaryExchange`, `currency`, `localSymbol`) wird persistiert und bei jedem Lauf gegengeprüft, Handelbarkeit wird abgefragt statt angenommen, und „ist jetzt Sitzung?" wird aus `liquidHours`/`timeZoneId` des aufgelösten Contracts beantwortet, nie aus einer hart kodierten Uhrzeit. Lauffähiges Ende: Subkommando `ibkr_executor.py resolve`.

Requirements: REQ-IBKR-26, -27, -28, -29, -30, -31, -37.

**Nicht in dieser Phase:** keine Order, kein `whatIf`, keine Mengenrechnung, kein Lesen von `paper-log`, keine Marktdaten über den delayed-Default hinaus, keine Allow-List-Erweiterung über `STK` hinaus.

</domain>

<decisions>
## Implementation Decisions

### Mapping-Tabelle (Roh-Ticker → Contract-Suchschlüssel)
- **D-01:** Die Tabelle ist eine **Code-Konstante** in einem neuen, **bibliotheksfreien** Modul (Arbeitsname `scripts/ibkr_contracts.py`), analog zu `EXPECTED_ACCOUNT`. Keine TOML/JSON-Datei, kein `.env`, kein LOCALAPPDATA. Jede Änderung ist ein Commit.
- **D-02:** Die Tabelle enthält nur **Suchschlüssel**: `symbol`, `secType`, `exchange` (`SMART`), `currency`, `primaryExchange`. `conId` und `localSymbol` werden **nicht** fest eingetragen. Sie werden beim ersten Lauf gelernt und persistiert (siehe D-09).
- **D-03:** Der Roh-Ticker wird **exakt und case-sensitiv** verglichen. `aapl` oder ` AAPL` sind „nicht gemappt". Keine Trim-/Upper-Normalisierung, also auch kein zweiter Normalizer.
- **D-04:** Nicht-STK-Beispiele stehen **mit ihrem echten secType** in der Tabelle (`^GSPC` → IND/CBOE/SPX, `XAUUSD+` → CMDTY/SMART/XAUUSD/USD) und werden von der Allow-List `{STK}` **vor** jeder IBKR-Anfrage mit Verweis auf die Allow-List abgewiesen (SC2). Das ist gleichzeitig der dokumentierte Erweiterungspfad: Allow-List erweitern statt Tabelle umbauen.
- **D-05:** Keine Alias-Logik. Es gibt nur Einträge für Roh-Strings, die real vorkommen (M2: `AAPL`, `MSFT`, `NVDA` + die zwei Sperr-Beispiele). Alles andere (`XYZQ`, `GOLD`, `XAU` …) ist „nicht gemappt" und wird abgewiesen, ohne „SMART/USD zu probieren".
- **D-06:** Ein **Unit-Test prüft die Tabelle selbst**: Pflichtfelder vorhanden, keine Duplikate, jeder handelbare Eintrag hat `secType=STK`, und jeder Ticker aus dem dokumentierten `PAPER_RUN_TICKERS`-Default (`.github/workflows/daily-paper-run.yml:72`, `scripts/PAPER_RUN.md:40`) ist gemappt.
- **D-07:** Die Trennung von `normalize_symbol()` (SC5, REQ-27) wird **doppelt** nachgewiesen. Ein AST-Importtest in `tests/test_ibkr_isolation.py` zeigt, dass das Resolver-Modul `tradingagents.dataflows.symbols` nicht importiert. Ein Verhaltenstest zeigt, dass `XAUUSD+` zu CMDTY/XAUUSD führt (und dann von der Allow-List abgewiesen wird), nie zu `GC=F`/FUT.
- **D-08:** Neuer Ticker = Code-Commit + einmaliger `resolve <TICKER>`-Probelauf gegen das Gateway (genau ein Treffer). Die Ausgabe gehört in Commit-Message/PR. Das wird in `scripts/IBKR_EXECUTION.md` dokumentiert und ist kein technisches Gate.

### Identität, conId-Persistenz & Drift
- **D-09:** Identitätsprüfung über genau die **4 Felder aus REQ-30**: `conId`, `primaryExchange`, `currency`, `localSymbol`. `tradingClass` und `longName` werden nur **geloggt**, nicht geprüft (Umfirmierung ≠ Risiko).
- **D-10:** Erstlauf pro Ticker: bei genau einem Treffer und passenden Suchschlüsseln wird der `conId` **automatisch gelernt** und persistiert, mit INFO-Logzeile `learned conId=…`. Der Lauf geht weiter.
- **D-11:** Speicher: `%LOCALAPPDATA%\TradingEngineX\ibkr\contracts.json`, **atomar** geschrieben (Muster `write_portfolio_atomic` aus Phase 2), überschreibbar per `--contracts`. Mit Schema-Version.
- **D-12:** **Fehlt** `contracts.json` ganz, stoppt der Lauf mit Hinweis auf `resolve --init`. Auto-Lernen (D-10) gilt nur für einzelne neue Ticker in einer **existierenden** Datei. So kann ein versehentliches Löschen die Identitätsprüfung nicht still zurücksetzen.
- **D-13:** `resolve --init` prüft den gelernten AAPL-`conId` gegen `PROBE_CON_ID = 265598` (`scripts/ibkr_broker.py`). Bei Abweichung bricht es ab.
- **D-14:** Ist `contracts.json` **unlesbar, kaputt oder hat eine falsche Schema-Version**, stoppt der **ganze Lauf** (laut). Keine stille Neu-Lernung.
- **D-15:** Ab dem zweiten Lauf: Abfrage per `conId` + `exchange` (liefert `ContractDetails` für Sitzung/Handelbarkeit) **und** Gegenprobe per Symbol-Suche mit `returnAll=True`. Beide müssen auf denselben `conId` zeigen. So fällt eine Symbol-Wanderung (Corporate Action) sofort auf.
- **D-16:** Drift (anderer `conId` bei gleichem Symbol oder Abweichung in einem der 4 Felder) betrifft **nur diesen Ticker**: abweisen, laute Meldung, Exit 2 (D-24). Die anderen Ticker laufen weiter. SC4 (manipulierter persistierter `conId`) gehört in diese Klasse.
- **D-17:** Neufestlegung nach legitimer Änderung nur über das explizite Kommando `resolve --rebaseline <TICKER>`. Es zeigt alt vs. neu, schreibt und protokolliert. **Nie automatisch.**
- **D-18:** Historie als append-only `contracts-history.jsonl` neben `contracts.json`: eine Zeile pro `learn`/`init`/`rebaseline` mit Zeitstempel, alt/neu und Grund.

### Handelbarkeit (ohne `ineligibilityReasonList`) und Handelszeiten
- **D-19:** `ineligibilityReasonList` existiert in ib_async 2.1.0 nicht (`.planning/ibkr-konto-befund.md` §4). **REQ-IBKR-31 wird mit Verweis auf den Befund geändert**, nach dem Muster des REQ-67-Overrides in Phase 2. Ersatzsignale sind: `validExchanges` ist nicht nur `VALUE` und enthält `SMART`, `orderTypes` enthält **`MKT` und `LMT`** (Leitplanke [L3]), und `whatIf` (Phase 4) ist die letzte Schicht.
- **D-20:** Halt-Erkennung (REQ-37: `HALTED`-Tick / Fehler 154): **Die Research klärt**, ob delayed-Daten (`reqMarketDataType(3)`) den Halted-Tick (generic tick 49) liefern. Wenn ja, prüft Phase 3 per Snapshot und weist den Ticker bei einem Halt ab. Wenn nein, wird 154 beim `whatIf` in Phase 4 abgefangen, und Phase 3 sieht nur den Zustand `halted` in der Ergebnisschnittstelle vor. Kein Abo-Zwang, kein Marktdatenpfad im Order-Pfad (REQ-26).
- **D-21:** „Ist jetzt Sitzung?" verlangt, dass der Zeitpunkt in einem `liquidHours`-Fenster liegt, mit **15 Minuten Puffer nach Öffnung und 15 Minuten vor Schluss**. Der Puffer ist eine benannte Konstante in Minuten, relativ zum Fenster und keine Uhrzeit (SC7 bleibt grün). Halbtage werden dadurch automatisch richtig behandelt. `outsideRth` bleibt aus.
- **D-22:** Für Handelszeiten gibt es **keinen persistenten Cache**. Sie leben nur im RAM des einen Laufs, denn jeder Lauf holt `ContractDetails` ohnehin (D-15). Damit ist „Cache ≤ 1 Handelstag / überlebt keinen Gateway-Restart" konstruktiv erfüllt. Ein Test belegt, dass kein Sitzungswert auf Platte geschrieben wird.
- **D-23:** Den Rohstring parst ein **eigener reiner Parser** im bibliotheksfreien Modul: beide Formate (`20261001:0400-20261001:2000` und das Alt-Format `20090507:0700-1830`), `CLOSED`, Fenster über Mitternacht, führendes `;`, Zeitzone per `zoneinfo` aus `timeZoneId`. Ein **Gegentest** vergleicht ihn mit ib_async `liquidSessions()` auf denselben Strings, wenn das `ibkr`-Extra installiert ist (SC6).
- **D-24:** Hat der heutige Tag kein Fenster (Tag fehlt, Parse-Fehler, leer), ist das der eigene Zustand `session-unknown`, unterscheidbar von `closed`. Der Ticker wird abgewiesen, ohne Fallback auf eine Uhrzeit.
- **D-25:** 10089/10090 erscheinen auf **INFO** mit State-Label (z. B. `ibkr-state=MARKET_DATA_DELAYED code=10089`) über `state_for_code()`/`INFO_CODES`, analog zu FARM_OK in Phase 2. Kein WARNING, kein Einfluss auf den Exit-Code. `reqMarketDataType(3)` wird gesetzt (SC8).

### Kommando & Fehlerverhalten
- **D-26:** Lauffähiges Ende: Subkommando **`ibkr_executor.py resolve <TICKER…> [--contracts PATH] [--init | --rebaseline TICKER] [--out PATH]`** in derselben Familie wie `account`, mit gleichen Settings, gleichem Log und gleicher Exit-Code-Tabelle. Pro Ticker: Auflösung, Identität, Handelbarkeit, Sitzung jetzt (offen/geschlossen + nächstes Fenster).
- **D-27:** Ticker-Argumente sind **Pflicht**. Ohne sie gibt es Exit 1 mit Usage, keinen Default aus der Tabelle oder der Env. Phase 4 übergibt die Ticker aus der Entscheidung.
- **D-28:** Ein Ticker abgewiesen (nicht gemappt, Allow-List, mehrdeutig, nicht gefunden, Drift, nicht handelbar, `session-unknown`) ergibt **Exit 2 (`EXIT_PRECONDITION`)**. Der reservierte Code wird damit aktiviert. Alle Ticker werden trotzdem geprüft und berichtet.
- **D-29:** **Außerhalb der Sitzung** (z. B. Samstag) gilt Exit 0 mit Zustand `closed` + nächstem Fenster. Geschlossen ist ein korrektes Ergebnis und kein Fehler. Was das für eine Order heißt, entscheidet Phase 4.
- **D-30:** Ausgabe: eine Konsolenzeile pro Ticker (Stil wie `account:`), Details inkl. Kandidatenliste in der Logdatei, optional `--out resolve.json`, atomar geschrieben. Phase 4 ruft die Python-Funktion direkt auf, das JSON ist für Operator und Tests.
- **D-31:** SC3 (Mehrdeutigkeit) wird per **Fake-Test** nachgewiesen: `qualifyContracts` liefert 2+ Kandidaten, das führt zum Abbruch, und **alle** Kandidaten (`conId`, `primaryExchange`, `localSymbol`, …) stehen in einer Zeile in **unserer** Logdatei. Als echte Evidenz gilt der ES-Befund (21 Treffer) aus Phase 1. **Kein** Diagnose-Schalter, der die Allow-List umgeht.

### Claude's Discretion
- Konkrete Dataclass-/Feldnamen des Ergebnisobjekts und die Namen der Zustände (`ok`, `not-mapped`, `not-allowed`, `ambiguous`, `not-found`, `drift`, `not-tradable`, `closed`, `session-unknown`, `halted`). Vorgabe: jeder Abweisungsgrund ist ein eigener benannter Zustand.
- JSON-Schema von `contracts.json` / `contracts-history.jsonl` (Schema-Version Pflicht).
- Name und Schnitt der neuen Broker-Lesemethoden. **Achtung:** `tests/test_ibkr_isolation.py::test_adapter_has_at_most_ten_public_methods` begrenzt den Adapter auf ≤ 10 öffentliche Methoden.
- Ob 154/HALTED als neue Codes in `STATE_BY_CODE` landen (abhängig von D-20).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phasen-Scope und Anforderungen
- `.planning/ROADMAP.md` §„Phase 3" — Ziel, 8 Success Criteria, „Was diese Phase NICHT tut"
- `.planning/REQUIREMENTS.md` — REQ-IBKR-26, -27, -28, -29, -30, -31, -37 (REQ-31 wird gemäß D-19 geändert)

### Gemessene Kontowahrheit
- `.planning/ibkr-konto-befund.md` §4 „Contract-Auflösung je secType" — AAPL conId 265598/NASDAQ/USD, **`ineligibilityReasonList` fehlt in ib_async 2.1.0**, ES FUT = 21 Treffer, Rohausgabe aller ContractDetails-Felder
- `.planning/ibkr-konto-befund.md` §5 „Handelszeiten" — reale `tradingHours`/`liquidHours`-Strings inkl. `CLOSED` und führendem `;`
- `.planning/ibkr-marktdaten-befund.md` — Marktdaten-Lage am Paper-Konto (für D-20/D-25)

### Research
- `.planning/research/ibkr-interface.md` §5.2–5.5 — Empfehlung „eigene Mapping-Tabelle auf dem Roh-Ticker", Mapping-Tabelle je Instrumentenklasse, fünfschichtige Erkennungskette
- `.planning/research/ibkr-execution-architecture.md` — JSONL statt SQLite (Grundlage für D-18), keine harte UTC-Uhrzeit (§ Cron/Sitzung)

### Bestehender Code / Betrieb (Phase 2)
- `scripts/ibkr_broker.py` — einziger Bibliothekskontakt, Schreibsperre, `PROBE_CON_ID`, `state_for_code`, `INFO_CODES`, Timeouts
- `scripts/ibkr_executor.py` — Subkommando-Struktur (`account`), Exit-Codes, `write_portfolio_atomic`, Logging
- `scripts/IBKR_EXECUTION.md` — Betriebshandbuch, Exit-Code-Tabelle; erhält den Abschnitt zu `resolve` und „neuer Ticker"
- `tradingagents/dataflows/symbols.py` — `normalize_symbol()`/`_ALIASES`: der Pfad, der **nicht** benutzt werden darf (REQ-27)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/ibkr_fakes.py` (`FakeIB`, `FakeContract`, `make_handles`, `block_real_ib_connect`): wird für `qualifyContracts`/`reqContractDetails` erweitert und trägt alle Tests ohne Gateway.
- `scripts/ibkr_executor.py::write_portfolio_atomic`: Muster für atomares Schreiben von `contracts.json` und `--out`.
- `scripts/ibkr_broker.py::_request`/`_call` mit `asyncio.wait_for`: jede neue Leseanfrage läuft darüber (der Bibliotheks-Default wartet ewig).
- `scripts/ibkr_broker.py::state_for_code` + `INFO_CODES`: Ort für 10089/10090 als INFO-Zustand.

### Established Patterns
- Nur `ibkr_broker.py` importiert die Client-Bibliothek. Das erzwingt `test_only_the_adapter_imports_the_client_library`, und das neue Fachmodul muss bibliotheksfrei bleiben.
- Konstanten im Code statt `.env` für sicherheitsrelevante Werte (`EXPECTED_ACCOUNT`, `EXECUTOR_CLIENT_ID`).
- Laufzeitzustand unter `%LOCALAPPDATA%\TradingEngineX\ibkr\`, nie im Repo.
- Logzeilenformat `ibkr-state=<STATE> code=<code> detail="..."`.
- Adapter hat höchstens 10 öffentliche Methoden (Test).

### Integration Points
- `ibkr_executor.py` `build_parser()`/`main()`: neues Subkommando `resolve`.
- `ibkr_broker.py`: neue Lesemethode(n) für Qualifizieren/ContractDetails (Schreibsperre bleibt aktiv) sowie `reqMarketDataType(3)` nach dem Connect.
- `tests/test_ibkr_isolation.py`: AST-Test „Resolver importiert nicht `symbols`" (D-07) und Suche nach harten Uhrzeiten `13:30|14:30|09:30|16:00` im Ausführungscode (SC7).
- Phase 4 ruft die Resolver-Funktion direkt auf und konsumiert die Ergebniszustände.

</code_context>

<specifics>
## Specific Ideas

- Testfälle für den Parser stammen aus den **echten** Strings im Konto-Befund (§ Rohausgabe), dazu das Alt-Format `20090507:0700-1830`, ein `CLOSED`-Tag und ein Halbtag.
- SC1-Abgleich gegen die Befund-Werte (AAPL 265598/NASDAQ/USD/`AAPL`). MSFT und NVDA werden beim `--init`-Lauf gelernt und im UAT gegen das Gateway belegt.
- Die Kandidatenliste bei Mehrdeutigkeit muss in **unserer** Logdatei landen, nicht nur im Bibliotheks-Log (Zitat REQ-29).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Allow-List-Erweiterung über `STK`, Limit-Preisfindung und Marktdaten-Abos sind bereits in REQUIREMENTS.md als Erweiterungspfad bzw. Out-of-Scope geführt.)

</deferred>

---

*Phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten*
*Context gathered: 2026-10-12*
