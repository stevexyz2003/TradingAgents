# Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten - Research

**Researched:** 2026-10-12
**Domain:** IBKR-Contract-Auflösung (ib_async 2.1.0, Gateway 10.50.1, Paper `DUQ634065`), Identitäts-Persistenz, Sitzungsfenster aus `ContractDetails`
**Confidence:** HIGH (Bibliotheks-Quelltext gelesen, am laufenden Paper-Gateway gemessen am 2026-10-12 ~13:20 New York, bei offener US-Sitzung)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
D-01..D-31 aus `03-CONTEXT.md` sind **gesperrt** (Wortlaut dort; hier nur die Kurzfassung, Quelle bleibt CONTEXT.md):

- **Mapping (D-01..D-08):** Code-Konstante in neuem bibliotheksfreiem Modul `scripts/ibkr_contracts.py`; nur Suchschlüssel (`symbol`, `secType`, `exchange`=`SMART`, `currency`, `primaryExchange`); exakter, case-sensitiver Vergleich ohne Normalisierung; Nicht-STK-Beispiele (`^GSPC` IND/CBOE/SPX, `XAUUSD+` CMDTY/SMART/XAUUSD/USD) stehen mit echtem secType in der Tabelle und scheitern an der Allow-List `{STK}` vor jeder IBKR-Anfrage; keine Alias-Logik; Tabellen-Unit-Test (Pflichtfelder, keine Duplikate, handelbar => STK, alle `PAPER_RUN_TICKERS`-Default-Ticker gemappt); Trennung von `normalize_symbol()` doppelt belegt (AST-Importtest + Verhaltenstest); neuer Ticker = Commit + einmaliger `resolve <TICKER>`-Probelauf.
- **Identität (D-09..D-18):** 4 Felder (`conId`, `primaryExchange`, `currency`, `localSymbol`); `tradingClass`/`longName` nur loggen; Erstlauf lernt `conId` automatisch (INFO `learned conId=…`); Speicher `%LOCALAPPDATA%\TradingEngineX\ibkr\contracts.json`, atomar, `--contracts` überschreibt, mit Schema-Version; Datei fehlt => Stopp mit Hinweis auf `resolve --init`; `--init` prüft AAPL gegen `PROBE_CON_ID = 265598`; unlesbar/kaputt/falsche Schema-Version => ganzer Lauf stoppt; ab Lauf 2: Abfrage per `conId`+`exchange` **und** Gegenprobe per Symbol-Suche mit `returnAll=True`, beide müssen auf denselben `conId` zeigen; Drift trifft nur diesen Ticker (Exit 2); Neufestlegung nur per `resolve --rebaseline <TICKER>`, nie automatisch; append-only `contracts-history.jsonl` (`learn`/`init`/`rebaseline`).
- **Handelbarkeit/Zeiten (D-19..D-25):** REQ-IBKR-31 wird geändert (kein `ineligibilityReasonList`; Ersatz: `validExchanges` nicht nur `VALUE` und enthält `SMART`, `orderTypes` enthält `MKT` und `LMT`, `whatIf` in Phase 4 als letzte Schicht); D-20 Halt-Erkennung: Research entscheidet den Zweig; Sitzung = Zeitpunkt in `liquidHours`-Fenster mit **15 min Puffer nach Öffnung und 15 min vor Schluss** (benannte Konstante); kein persistenter Cache für Handelszeiten (nur RAM des Laufs; Test belegt, dass kein Sitzungswert auf Platte landet); eigener reiner Parser (beide Formate, `CLOSED`, über Mitternacht, führendes `;`, `zoneinfo`) mit Gegentest gegen `liquidSessions()`; heute kein Fenster => eigener Zustand `session-unknown`, abgewiesen, kein Uhrzeit-Fallback; 10089/10090 auf INFO über `state_for_code()`/`INFO_CODES`, `reqMarketDataType(3)` gesetzt.
- **Kommando (D-26..D-31):** `ibkr_executor.py resolve <TICKER…> [--contracts PATH] [--init | --rebaseline TICKER] [--out PATH]`; Ticker-Argumente Pflicht (sonst Exit 1); abgewiesener Ticker => Exit 2 (`EXIT_PRECONDITION`), alle Ticker werden trotzdem geprüft; außerhalb der Sitzung Exit 0 mit `closed` + nächstem Fenster; eine Konsolenzeile pro Ticker, Details inkl. Kandidatenliste im Log, optional `--out resolve.json` atomar; SC3 per Fake-Test (`qualifyContracts` liefert 2+ Kandidaten, alle in **unserer** Logdatei), echte Evidenz = ES-Befund (21 Treffer), kein Diagnose-Schalter.

### Claude's Discretion
- Konkrete Dataclass-/Feldnamen des Ergebnisobjekts und Namen der Zustände (`ok`, `not-mapped`, `not-allowed`, `ambiguous`, `not-found`, `drift`, `not-tradable`, `closed`, `session-unknown`, `halted`). Vorgabe: jeder Abweisungsgrund ist ein eigener benannter Zustand.
- JSON-Schema von `contracts.json` / `contracts-history.jsonl` (Schema-Version Pflicht).
- Name und Schnitt der neuen Broker-Lesemethoden (Achtung: `test_adapter_has_at_most_ten_public_methods`).
- Ob 154/HALTED als neue Codes in `STATE_BY_CODE` landen (abhängig von D-20).

### Deferred Ideas (OUT OF SCOPE)
Keine. (Allow-List-Erweiterung über `STK`, Limit-Preisfindung und Marktdaten-Abos sind bereits in REQUIREMENTS.md als Erweiterungspfad bzw. Out-of-Scope geführt.) Nicht in dieser Phase: Order, `whatIf`, Mengenrechnung, Lesen von `paper-log`, Marktdaten über den delayed-Default hinaus.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-IBKR-26 | `reqMarketDataType(3)` Default; 10089/10090 erwartete Zustände | `reqMarketDataType` ist eine reine Sendung (ib.py:1324), nach Connect+Guard in `connect()` setzen; Code-Mapping siehe „Fehlercodes" (auch **10167**, am Gateway gemessen) |
| REQ-IBKR-27 | Auflösung unabhängiger zweiter Pfad, nicht über `normalize_symbol()` | Modul darf kein `tradingagents` importieren; AST-Test + Verhaltenstest (`XAUUSD+` -> CMDTY) |
| REQ-IBKR-28 | Allow-List `{STK}`, nicht gemappt -> abgewiesen | exakte Tabelle, Prüfreihenfolge mapping -> allow-list -> IBKR |
| REQ-IBKR-29 | Eindeutigkeit, Kandidatenliste im Log | `qualifyContractsAsync(..., returnAll=True)` gemessen: 1 Treffer -> `Contract`, 21 (ES) -> `list`, 0 -> `None` |
| REQ-IBKR-30 | `conId` persistieren, 4 Felder prüfen, ab Lauf 2 über `conId`+`exchange` | `reqContractDetailsAsync(Contract(conId=…, exchange="SMART"))` gemessen: liefert genau 1 Detail mit `primaryExchange`, `localSymbol`, `currency` |
| REQ-IBKR-31 | Handelbarkeit abfragen (wird geändert, D-19) | Felder `validExchanges`, `orderTypes` gemessen vorhanden; Änderungstext siehe „REQ-31-Änderung" |
| REQ-IBKR-37 | Sitzungsfenster aus `ContractDetails`, kein hartes Datum, Halt | Parser-Semantik, Alt-Format-Befund, **Halt-Zweig „nein"** (gemessen) |
</phase_requirements>

## Summary

Die Phase ist überwiegend reine Logik (Tabelle, Parser, Zustandsautomat, Persistenz) in einem bibliotheksfreien Modul plus zwei bis drei schmale Lesemethoden im Adapter. Alle offenen Forschungsfragen sind jetzt entschieden, und zwar mit Messung am echten Paper-Gateway (Probe mit `clientId=20098`, `readonly=True`, Paper-Guard vorher geprüft, nur Lesezugriffe; Skripte lagen im Scratchpad, nichts im Repo).

Vier Befunde ändern den Plan gegenüber den Annahmen in CONTEXT.md. (1) **D-20: Zweig „nein".** Das Gateway lehnt `reqMktData` mit generischem Tick `49` im Streaming ab (`321 … Incorrect generic tick list of 49`), und ein Snapshot ohne generische Ticks (was `reqTickersAsync` sendet) liefert weder `halted` noch `delayedHalted`; ein Snapshot mit `"49"` bleibt leer. Phase 3 sieht also nur den Zustand `halted` in der Schnittstelle vor, 154 wird in Phase 4 am `whatIf` gefangen. (2) **Der Alt-Format-String `20090507:0700-1830` wird von ib_async 2.1.0 mit `ValueError` abgelehnt** — der Gegentest nach D-23 kann dieses Format nicht gegen `liquidSessions()` prüfen; er muss für dieses Format den `ValueError` als erwartetes Verhalten festhalten und unser Parser trotzdem korrekt parsen. (3) **Das Gateway meldet für verzögerte Aktienkurse 10167**, nicht 10089/10090 (10089 kam nur bei Forex). SC8 ist ohne 10167 im Mapping nur formal erfüllt; 10167 gehört auf INFO. (4) Der bestehende Test `test_state_map` pinnt 10089/10090 auf `MARKET_DATA_NOT_SUBSCRIBED`; das D-25-Beispiellabel `MARKET_DATA_DELAYED code=10089` würde ihn brechen. Empfehlung: bestehende Labels behalten, 10167 als `MARKET_DATA_DELAYED` neu, alle drei in `INFO_CODES`.

Außerdem gilt: `scripts/` enthält heute **keine** der vier Uhrzeit-Muster (SC7 ist vorab leer), und die Abfrage `reqContractDetails` per `conId` liefert für AAPL, MSFT, NVDA je genau 1 Treffer mit `primaryExchange=NASDAQ`, `MKT` und `LMT` in `orderTypes`.

**Primary recommendation:** Neues reines Modul `scripts/ibkr_contracts.py` (Tabelle, Allow-List, Parser, Zustände, Persistenz-Funktionen mit injizierter Uhr und injiziertem Broker-Interface), Adapter um zwei öffentliche Methoden (`search_contract`, `contract_details`) erweitern (5 von 10 erlaubten), `reqMarketDataType(3)` in `connect()`, `resolve` als Subkommando; Gegenprobe über `qualifyContractsAsync(returnAll=True)`, Details über `reqContractDetailsAsync`.

## Architectural Responsibility Map

Lokales Operator-Tooling, keine Web-Tiers. Zuordnung nach den Schichten dieses Repos:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Roh-Ticker -> Suchschlüssel, Allow-List | `scripts/ibkr_contracts.py` (reine Logik) | — | bibliotheksfrei, Code-Konstante (D-01), ohne Netz testbar |
| Sitzungs-Parser, Puffer, Zustandsentscheidung | `scripts/ibkr_contracts.py` | — | rein, Uhr als Parameter, kein Gateway nötig (SC6/SC7) |
| Persistenz `contracts.json` + History | `scripts/ibkr_contracts.py` (Funktionen), Pfad/Wiring in Executor | Dateisystem `%LOCALAPPDATA%` | atomar nach Muster `write_portfolio_atomic` |
| Contract-Lesen (Suche, Details), `reqMarketDataType` | `scripts/ibkr_broker.py` (einziger Bibliothekskontakt) | — | erzwungen durch `test_only_the_adapter_imports_the_client_library` |
| CLI, Exit-Codes, Konsolenzeile, `--out` | `scripts/ibkr_executor.py` | — | gleiche Familie wie `account` (D-26) |
| Halt-Erkennung 154 | Phase 4 (`whatIf`) | Phase 3: nur Zustand `halted` im Ergebnistyp | D-20 Zweig „nein" (gemessen) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ib_async | 2.1.0 (exakt gepinnt, Extra `ibkr`) | `qualifyContractsAsync`, `reqContractDetailsAsync` | bereits Phase-2-Stack; Quelltext in `.venv/Lib/site-packages/ib_async` gelesen [VERIFIED: installierter Quelltext] |
| Python stdlib `zoneinfo`, `datetime`, `json`, `dataclasses`, `os.replace` | py>=3.11 | Parser, Zeitzonen, Persistenz | keine neue Abhängigkeit nötig [VERIFIED: pyproject.toml `requires-python>=3.11`] |
| tzdata | >=2025.2,<2026.0 (im Extra) | IANA-Zonen auf Windows | `zoneinfo.ZoneInfo("US/Eastern")` funktionierte in der .venv beim Parser-Lauf [VERIFIED: Messung] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest (+ pytest-subtests) | >=8.0 | Tests; Marker `unit` | alle neuen Tests; Bestandskonventionen in `tests/test_ibkr_*.py` |
| ruff | >=0.16 | Lint (line-length 100) | vor Push (Erinnerung aus Memory: `UV_OFFLINE=1`, SUMMARY-Behauptung "lint passed" selbst gegenprüfen) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Eigener Parser | `ContractDetails.liquidSessions()` direkt | Verworfen durch D-23 (Alt-Format wirft `ValueError`, `CLOSED`-Unterscheidung fehlt, Modul muss bibliotheksfrei bleiben) |
| `reqMatchingSymbols` | `qualifyContractsAsync(returnAll=True)` | `reqMatchingSymbolsAsync` hat festes 4-s-Timeout und liefert Fuzzy-Treffer; REQ-29 verlangt `qualifyContracts` |

**Installation:** keine neue Abhängigkeit. Pakete: keiner neu zu installieren.

## Package Legitimacy Audit

Diese Phase installiert **keine** neuen externen Pakete (ib_async 2.1.0 und tzdata sind seit Phase 2 gepinnt und freigegeben). slopcheck nicht nötig.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
CLI: resolve AAPL XYZQ ^GSPC [--init|--rebaseline T] [--contracts P] [--out P]
        |
        v
 ibkr_executor.resolve (Settings, Log, Exit-Tabelle wie `account`)
        |
        |-- Tickerliste leer? --> Exit 1 (Usage)                           [D-27]
        |-- contracts.json laden (ausser --init)
        |      fehlt --> Stopp "resolve --init"  [D-12]
        |      kaputt/Schema --> Stopp, ganzer Lauf  [D-14]
        v
 fuer JEDEN Ticker (alle werden geprüft, D-28):
   ibkr_contracts.lookup(raw)  --exakt-->  nicht in Tabelle? -> not-mapped
        |
        v
   secType in ALLOW_LIST {STK}? --nein--> not-allowed   (kein IBKR-Request)
        |ja
        v
   Broker (einzige Stelle mit ib_async):
     erster Lauf des Tickers:   search_contract(spec)  [qualify, returnAll]
         0 -> not-found | list -> ambiguous (Kandidaten -> unser Log) | 1 -> lernen (D-10)
     ab Lauf 2:  contract_details(conId, "SMART")  UND  search_contract(spec)
         conId gleich? 4 Felder gleich?  nein -> drift  [D-15/16]
        |
        v
   Handelbarkeit: validExchanges != {VALUE}, enthält SMART, orderTypes ⊇ {MKT,LMT}
        nein -> not-tradable                                       [D-19]
        |
        v
   Sitzung: parse(liquidHours, timeZoneId) -> Fenster
        kein Eintrag für "heute" -> session-unknown                [D-24]
        jetzt in [Start+15min, Ende-15min] -> ok   sonst -> closed + nächstes Fenster
        (Halt: Zustand `halted` im Typ vorgesehen, in Phase 3 nie gesetzt)
        |
        v
 Ergebnisliste -> Konsole (1 Zeile/Ticker), Log (Details), optional --out atomar
 Exit 2 wenn mind. ein Ticker abgewiesen, sonst 0 (closed zählt als 0, D-29)
```

### Recommended Project Structure
```
scripts/
├── ibkr_contracts.py     # NEU, bibliotheksfrei: Tabelle, Allow-List, Parser, Zustände, Persistenz
├── ibkr_broker.py        # +search_contract, +contract_details, +reqMarketDataType(3), +Codes
├── ibkr_executor.py      # +resolve-Subkommando, laedt ibkr_contracts per importlib
└── IBKR_EXECUTION.md     # +Abschnitt resolve / neuer Ticker / Exit 2 aktiv
tests/
├── test_ibkr_contracts.py        # Tabelle, Parser, Zustandsautomat, Persistenz (kein Gateway)
├── test_ibkr_resolve.py          # resolve-Kommando mit FakeIB
├── ibkr_fakes.py                 # erweitert: qualifyContractsAsync, reqContractDetailsAsync je conId, reqMarketDataType
└── test_ibkr_isolation.py        # +AST symbols-Test, +SC7-Grep, Methodenmenge angepasst
```

`scripts/` ist kein Paket: Executor lädt Module per `importlib.util.spec_from_file_location` und trägt sie vor `exec_module` in `sys.modules` ein (Muster `load_broker_module`, `tests/ibkr_fakes.load_broker`). Für `ibkr_contracts` dasselbe Muster, damit Executor und Tests dieselben Klassen sehen. [VERIFIED: scripts/ibkr_executor.py, tests/ibkr_fakes.py]

### Pattern 1: Adapter-Lesemethoden (broker-neutral, mit Timeout)
**What:** Zwei neue öffentliche Methoden, die nur frozen Dataclasses zurückgeben (`ContractInfo`, Kandidatenliste), nie ib_async-Objekte. Jede läuft über `self._request(name, make_awaitable)` (Timeout, `ConnectionError` -> `GatewayUnavailable`).
**Schnitt (Empfehlung, 5 öffentliche Methoden gesamt):**
- `search_contract(spec) -> tuple[ContractInfo, ...]`: ruft `ib.qualifyContractsAsync(handles.contract(symbol=…, secType=…, exchange=…, currency=…, primaryExchange=…), returnAll=True)`; Ergebnis-Slot `None` -> leeres Tuple, `Contract` -> 1 Element, `list` -> alle Kandidaten.
- `contract_details(con_id, exchange) -> ContractInfo | None`: ruft `ib.reqContractDetailsAsync(handles.contract(conId=con_id, exchange=exchange))`; `len != 1` -> Fehlerzustand.
- `ContractInfo` trägt: `con_id, symbol, sec_type, primary_exchange, currency, local_symbol, trading_class, long_name, valid_exchanges, order_types, time_zone_id, liquid_hours, trading_hours`. Aus `qualifyContracts` kommt nur der `Contract` (ohne Sitzungsfelder) — dort bleiben diese Felder leer/None.
**Test-Anpassung:** `test_adapter_has_at_most_ten_public_methods` pinnt `public == {"connect","positions","health"}` exakt; die Menge muss mitgezogen werden (≤10 bleibt).
**Wichtig:** die Schreibsperre (`_arm_write_barrier`) bleibt unberührt; `reqContractDetails` (Msg-Id 9) und `reqMarketDataType` (Msg-Id 59) liegen nicht in `_WRITE_MESSAGE_IDS` {3,4,19,21,58} [ASSUMED: Msg-Id 9/59 aus Kenntnis des TWS-Protokolls, nicht im Quelltext nachgezählt; die Probe unten lief aber ohne Schreibsperre — der Test mit FakeIB und echter Sperre fängt es ab, siehe Pitfall 6].

### Pattern 2: Reine Funktionen mit injizierter Uhr
`evaluate_session(info_hours, tz_id, now_utc: datetime, buffer_min=SESSION_BUFFER_MINUTES)` bekommt `now` als Argument; kein `datetime.now()` im Modul außer an der Aufrufstelle im Executor. So sind Wochenende, Halbtag und DST ohne Mocks testbar.

### Pattern 3: Persistenz mit Fail-loud
`contracts.json`: `{"schema_version": 1, "contracts": {"AAPL": {"conId": 265598, "primaryExchange": "NASDAQ", "currency": "USD", "localSymbol": "AAPL", "learned_at": "...Z"}}}`. Schreiben: temp-Datei im selben Verzeichnis mit `uuid`-Suffix, `os.replace` (Muster `write_portfolio_atomic`; unter Windows atomar genug für den Einzelprozess-Fall). `contracts-history.jsonl`: eine Zeile pro Ereignis, Datei mit `open("a", encoding="utf-8", newline="\n")`, Zeile **vor** dem Ersetzen von `contracts.json` schreiben und `flush`+`os.fsync`, damit ein Abbruch dazwischen keine ungeloggte Änderung hinterlässt.

### Anti-Patterns to Avoid
- **`details[0]` bei mehreren Treffern** (Befund ES: 21 Treffer). Immer `len == 1` verlangen.
- **Sitzungswerte in `contracts.json` ablegen** (verletzt D-22; ein Test prüft den Dateiinhalt auf Abwesenheit von `liquidHours`/`tradingHours`).
- **Uhrzeit-Literale im Ausführungscode**, auch in Kommentaren/Docstrings von `scripts/ibkr_*.py` (der SC7-Test würde sie finden). Beispiele für Strings gehören in `tests/`.
- **Tabelle um `conId`/`localSymbol` anreichern** (D-02): wird gelernt, nicht festgeschrieben.
- **Gegenprobe über `normalize_symbol()` oder `tradingagents.*`** (D-07).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Zeitzonen / DST | eigene Offset-Rechnung | `zoneinfo.ZoneInfo(time_zone_id)` | gleiche Quelle wie ib_async; `replace(tzinfo=…)` auf naive Wanduhrzeit ist dort identisch |
| Feiertage/Halbtage | eigener Kalender | `liquidHours` des Contracts | Befund §5: kommt vom Server; Halbtag erscheint als verkürztes Fenster |
| Atomares Schreiben | neues Muster | Muster `write_portfolio_atomic` (temp + `os.replace`) | schon in Phase 2 geprüft |
| Mehrdeutigkeitserkennung | eigene Heuristik | `qualifyContractsAsync(returnAll=True)` plus `len`-Prüfung | Bibliothek filtert zusätzlich nach `secType` (ib.py:2140) |
| Timeouts | eigene Threads | `IbkrBroker._request`/`_call` (`asyncio.wait_for`) | Bibliotheks-Default wartet ewig |
| Sitzungs-Parser | — | **doch** selbst bauen (D-23) | ib_async lehnt das Alt-Format ab und kennt keinen Unterschied `CLOSED` vs. fehlend; aber klein und rein |

**Key insight:** Das Teure sind nicht die Bibliotheksaufrufe, sondern die Entscheidungslogik um sie herum (Zustände, Fail-closed). Die gehört in reine, bibliotheksfreie Funktionen, damit die Tests ohne Fake-Gateway auskommen.

## Messergebnisse zu den offenen Fragen

### D-20 Halt-Erkennung — Zweig „nein" (gemessen 2026-10-12, offene US-Sitzung)

Quelltext: `GENERIC_TICK_MAP` ordnet `49 -> halted` und `90 -> delayedHalted` zu (wrapper.py:145,151); `tickGeneric` ersetzt Werte `<= 0` durch `defaultEmptySize` (NaN) (wrapper.py:1260-1263). **Folge: nur ein Halt-Wert > 0 ist am Ticker sichtbar; „nicht gehalten" (0) sieht aus wie „nie geliefert".** `reqTickersAsync` sendet `genericTickList=""` und `snapshot=True` (ib.py:2195). [VERIFIED: ib_async-Quelltext]

Gemessen mit `reqMarketDataType(3)`, AAPL (`conId=265598`, SMART):

| Aufruf | Ergebnis |
|--------|----------|
| Snapshot, `""` (wie `reqTickersAsync`) | `last=339.83`, `marketDataType=3`, `halted=nan`, `delayedHalted=nan`, keine Generic-Ticks; Meldung 10167 |
| Snapshot, `"49"` | nach 5 s **leer** (keine Ticks, kein Preis, kein Fehler 321); nur 10167 |
| Streaming, `"49"` | **Fehler 321: „Incorrect generic tick list of 49"**, keine Ticks |
| Streaming, `""` | nur Tick-Typen 66, 67 (verzögert bid/ask), `halted=nan` |

[VERIFIED: Messung am Paper-Gateway 10.50.1, 2026-10-12] **Entscheidung: Zweig „nein".** Das Gateway liefert den Halted-Tick mit delayed-Daten nicht; Phase 3 prüft keinen Halt, setzt keinen Marktdatenpfad auf, und der Ergebnistyp führt den Zustand `halted` vorsorglich (Phase 4 setzt ihn bei Fehler 154 aus dem `whatIf`). Positive Gegenprobe (echter Halt) war nicht möglich — AAPL ist nicht gehalten; das ist die Grenze der Messung.

Konsequenz für REQ-37 (Halt-Teil): nach Phase-3-Abschluss deckt Phase 3 „Sitzungsfenster", der Halt-Teil bleibt offen bis Phase 4/6 und muss in der Verifikation als solcher geführt werden (nicht als erfüllt behaupten). Fehlercode 154 **nicht** in `STATE_BY_CODE` aufnehmen: er ist hier nicht gemessen (REQ-IBKR-67 verlangt Messung vor dem Bauen darauf); Eintrag erst in Phase 4 nach Messung. [ASSUMED: Bedeutung von 154 aus REQUIREMENTS.md, nicht verifiziert]

### D-23 `liquidSessions()` / `_parseSessions` — tatsächliche Semantik in 2.1.0

Quelle: `contract.py:605-635`. Gegen den Quelltext geprüft und mit der .venv ausgeführt:

| Eingabe | ib_async 2.1.0 |
|---------|----------------|
| `20261011:CLOSED;20261012:0930-20261012:1600` | 1 Fenster (CLOSED-Segmente übersprungen: `"CLOSED" in sess`) |
| `;20261011:1800-20261012:1700` (führendes `;`) | 1 Fenster, Leersegmente übersprungen; Fenster über Mitternacht: Start und Ende tragen je ihr Datum, korrekt |
| `""` | `[]` |
| `20261127:0930-20261127:1300` (Halbtag) | 1 Fenster 09:30-13:00, `-05:00` (DST korrekt) |
| mehrere Fenster am selben Tag | alle, als eigene Einträge |
| **`20090507:0700-1830` (Alt-Format)** | **`ValueError: time data '1830' does not match format '%Y%m%d:%H%M'`** |
| `timeZoneId=""` bei gefülltem String | `ValueError: ZoneInfo keys must be normalized relative paths` |
| `timeZoneId="Bad/Zone"` | `ZoneInfoNotFoundError` |

Weitere Eigenschaften: `if not (s or self.timeZoneId): return []` (Quirk: leerer String **und** leere Zone gibt `[]`; ein leerer String mit Zone läuft durch `split` und gibt ebenfalls `[]`); Rückgabe ist `NamedTuple TradingSession(start, end)` mit zeitzonenbewussten `datetime`s; Zeitzone wird per `.replace(tzinfo=ZoneInfo)` aufgesetzt; keine Sortierung, keine Deduplizierung, keine Unterscheidung `CLOSED` vs. fehlender Tag. [VERIFIED: Quelltext + Ausführung]

**Folgen für den Gegentest (SC6):**
1. Gleiche-Strings-Vergleich nur für das Neu-Format (inkl. `CLOSED`, Halbtag, führendes `;`, über Mitternacht).
2. Alt-Format: Test erwartet **unser** Ergebnis (Fenster 07:00-18:30 am 2009-05-07) und hält fest, dass ib_async dafür `ValueError` wirft (damit der Grund unseres eigenen Parsers dokumentiert und regressionsgeschützt ist). Nicht als „Divergenz" melden.
3. `pytest.importorskip("ib_async")` für den Gegentest (CI ohne Extra bleibt grün).
4. Verträglichkeit: unser Parser liefert eigene Typen (`start`/`end` aware); Vergleich über `(start, end)`-Tupel.

**Unser Parser: Spezifikation (Empfehlung)**
- Segmente an `;` trennen; leere Segmente überspringen (führendes `;`).
- Segment `YYYYMMDD:CLOSED` => Datum als „abgedeckt/geschlossen" merken, kein Fenster.
- Segment `YYYYMMDD:HHMM-YYYYMMDD:HHMM` (Neu) und `YYYYMMDD:HHMM-HHMM` (Alt; Ende am Startdatum) => Fenster. Alles andere => Parse-Fehler => `session-unknown` (kein Raten).
- `ZoneInfo(time_zone_id)`-Fehler => `session-unknown`.
- Ende `<=` Start => Parse-Fehler (nicht stillschweigend übernehmen).
- „Heute" = lokales Datum von `now` in der Contract-Zone. `closed` nur, wenn für dieses Datum (oder ein Fenster, das `now`s Datum überdeckt) ein Eintrag existiert (CLOSED oder Fenster); sonst `session-unknown` (D-24). Fenster über Mitternacht erscheinen unter dem **Startdatum**; ein `now` nach Mitternacht liegt im Fenster des Vortags, also nicht nach Datumsschlüssel, sondern nach Enthaltensein prüfen.
- Puffer: `start + 15 min <= now <= end - 15 min`. Ein Fenster kürzer als 30 min ergibt nie `ok` (kein Sonderfall nötig). Grenzen: Test bei `start+15min` (ok), `start+15min-1s` (closed), `end-15min` (ok), `end-15min+1s` (closed).
- `now` muss aware sein; naive `now` => `ValueError`.
- Nächstes Fenster: kleinstes `start > now` aus `liquidHours`; keines vorhanden (Horizont ~5 Handelstage) => `None` im Ergebnis, nicht erfunden.

### D-15 Auflösung in ib_async 2.1.0

- `qualifyContractsAsync(*contracts, returnAll=False)` (ib.py:2110): Signatur **hat** `returnAll`. Ergebnis hat pro Eingabe einen Slot: `None` (unbekannt oder mehrdeutig ohne `returnAll`), ein `Contract` (genau 1; **mutiert das übergebene Objekt per `dataclassUpdate` und gibt es zurück**), oder bei mehreren Treffern eine **`list[Contract]`** (nur mit `returnAll=True`). Bei gesetztem `secType` filtert die Bibliothek mehrere Details auf passenden `secType` und liefert einen Einzeltreffer, wenn danach genau einer bleibt. Mehrdeutigkeit wird zusätzlich als WARNING „Ambiguous contract … possibles are […]" an den Bibliotheks-Logger geschrieben; REQ-29 verlangt die Kandidatenliste in **unserer** Logzeile. [VERIFIED: Quelltext]
- Gemessen am Gateway: AAPL (`primaryExchange=NASDAQ`) -> `Contract` conId 265598; AAPL ohne `primaryExchange` -> ebenfalls `Contract`; ES FUT -> `list` mit **21** Contracts; XYZQ -> `None` plus Gateway-Fehler 200 („keine Wertpapierdefinition gefunden"). MSFT -> conId **272093**, NVDA -> conId **4815747**, jeweils `primaryExchange=NASDAQ`, `localSymbol` = Symbol, `exchange=SMART`, `tradingClass=NMS`. [VERIFIED: Messung 2026-10-12] (D-10 lernt diese Werte beim `--init`-Lauf; sie sind hier nur Erwartung fürs UAT.)
- `qualify` gibt nur `Contract`, keine `ContractDetails`. Für Sitzung/Handelbarkeit braucht jeder Ticker einmal `reqContractDetailsAsync`. Ab Lauf 2 liefert die Abfrage per `conId` die Details; der Erstlauf braucht nach dem Lernen eine zweite Anfrage per `conId` (zwei Round-Trips beim Erstlauf, vertretbar).
- `reqContractDetailsAsync(Contract(conId=…, exchange="SMART"))`: gemessen genau **1** Detail, `contract.primaryExchange=NASDAQ`, `contract.exchange=SMART`, `tradingClass=NMS`, `orderTypes` enthält `MKT` und `LMT`, `validExchanges` enthält `SMART`. [VERIFIED: Messung] `PROBE_CON_ID` benutzt dieselbe Form (ohne `exchange`).
- **Wo wird geloggt:** Bibliothek schreibt WARNING nur in ihren Logger (propagiert auf Root, landet über `setup_logging` ebenfalls in der Logdatei, aber unstrukturiert). Wir schreiben zusätzlich **eine** eigene Zeile `ibkr-state=AMBIGUOUS_CONTRACT code=- detail="symbol=ES candidates=[conId=…/primaryExchange=…/localSymbol=…, …]"` im Logger `ibkr_executor`/`ibkr_contracts`. Bei 21 Kandidaten ist die Zeile lang; Empfehlung: alle auflisten (Anforderung REQ-29), Länge nicht kürzen.
- Fehler 200 kommt als `errorEvent` (WARNING über `_on_error`, Zustand `UNKNOWN`). Empfehlung: 200 mit Label `CONTRACT_NOT_FOUND` in `STATE_BY_CODE` aufnehmen (gemessen, REQ-67-konform). Das ist Zusatzkomfort, kein Muss.

### D-25 Codes: `state_for_code()` / `INFO_CODES` / `STATE_BY_CODE`

Heutiger Stand (`ibkr_broker.py`): `10089`/`10090` -> `MARKET_DATA_NOT_SUBSCRIBED`, `INFO_CODES = {2104, 2106, 2158}`; `_on_error` loggt WARNING für alles außerhalb `INFO_CODES`. Die Tests (`tests/test_ibkr_broker.py:302-303`) pinnen die Labels, `test_farm_ok_codes_log_at_info` ist auf `FARM_OK` parametrisiert.

Gemessen am Gateway: **verzögerte Aktienkurse melden `10167`** („Sie haben die angeforderten Marktdaten nicht abonniert. Es werden verzögerte Marktdaten angezeigt."), 10089 kam nur bei Forex (`ibkr-marktdaten-befund.md` §2). [VERIFIED: Messung + Befund]

Empfehlung:
- `STATE_BY_CODE[10167] = "MARKET_DATA_DELAYED"`; `INFO_CODES` um `10089, 10090, 10167` erweitern. Labels für 10089/10090 **unverändert** lassen (bestehender Test bleibt grün; D-25 sagt „z. B."). Neuer parametrisierter Test: alle drei loggen auf INFO mit `ibkr-state=<LABEL> code=<n>` und lassen `exit`-relevante Flags (`link_lost` usw.) unberührt.
- 10167 kommt in Phase 3 nur, wenn Marktdaten angefragt werden; Phase 3 fragt keine an. SC8 ist dann per Unit-Test von `_on_error` belegbar; reale Evidenz stammt aus `ibkr-marktdaten-befund.md`. Das im Verifikationsbericht ehrlich benennen.
- `reqMarketDataType(3)`: in `connect()` nach erfolgreichem Paper-Guard senden (`ib.reqMarketDataType(3)`, synchron, ohne Antwort). FakeIB braucht die Methode (aufzeichnen in `calls`), und ein Test prüft, dass sie **nach** dem Guard und nicht bei Guard-Verletzung gesendet wird.
- 154: nicht aufnehmen (siehe D-20).

### Handelbarkeit (REQ-31-Ersatzprüfung)

Gemessen für AAPL/MSFT/NVDA: `validExchanges` enthält `SMART`; `orderTypes` enthält `MKT` und `LMT`. Prüfung: `valid = set(valid_exchanges.split(","))`; abweisen wenn `valid == {"VALUE"}` oder `"SMART" not in valid` oder `{"MKT","LMT"} - set(order_types.split(","))`. Leere Felder => `not-tradable` (fail-closed, nicht `ok`). [VERIFIED: Messung für die drei Ticker; `VALUE` als Pseudo-Börse stammt aus REQ-31, nicht selbst gemessen]

### REQ-31-Änderung (Muster aus Phase 2)

Das REQ-67-Muster liegt in `02-VERIFICATION.md` als Frontmatter-Block `overrides:` (`must_have`, `reason`, `accepted_by`, `accepted_at`) plus Hinweis in STATE. Für REQ-31 ist das eine **Textänderung der Anforderung**, nicht ein Override der Prüfung. Empfehlung als eigene Planaufgabe (Doku, kein Code):
1. `REQUIREMENTS.md` REQ-IBKR-31 umformulieren: „… Handelbarkeit wird abgefragt, nicht angenommen: `validExchanges` besteht nicht nur aus `VALUE` und enthält `SMART`, `orderTypes` enthält `MKT` und `LMT`; `ineligibilityReasonList` existiert in ib_async 2.1.0 nicht (`ibkr-konto-befund.md` §4); die letzte Schicht ist `whatIf` (Phase 4). Geändert 2026-10-12 (Phase 3, D-19)."
2. Zeile in der Traceability/Fußnote von `ROADMAP.md`, wenn dort REQ-31 mit Wortlaut steht (nicht geprüft; planner soll `grep REQ-IBKR-31` über `.planning` ausführen).
3. In der Phase-3-`VERIFICATION.md` den Eintrag unter `overrides:` mit `accepted_by: Operator` führen, sobald der Operator bestätigt hat (nicht vom Agenten selbst vergeben).

## Common Pitfalls

### Pitfall 1: Alt-Format im Gegentest gegen ib_async
**What goes wrong:** Ein parametrisierter Test schickt `20090507:0700-1830` an beide Parser und bekommt von ib_async `ValueError`.
**How to avoid:** Format getrennt behandeln (siehe D-23-Abschnitt); Divergenz ist erwartet und wird als Test dokumentiert.

### Pitfall 2: `qualifyContracts` mutiert die Anfrage
**What goes wrong:** Das übergebene Suchobjekt wird beim Einzeltreffer per `dataclassUpdate` überschrieben; ein wiederverwendeter Suchschlüssel trägt danach `conId`, und die „Gegenprobe" sucht dann nach `conId` statt nach Symbol — Drift bliebe unentdeckt.
**How to avoid:** Pro Aufruf frisches `Contract` aus dem Suchschlüssel bauen; im Adapter nie ein Contract-Objekt cachen. Test: zweimal denselben Ticker suchen, der Suchschlüssel bleibt unverändert.

### Pitfall 3: Einzelkandidat nach `secType`-Filter verdeckt Mehrdeutigkeit
**What goes wrong:** Die Bibliothek filtert mehrere Details auf `secType` und liefert bei genau einem Rest einen Einzeltreffer. Das ist für STK korrekt, aber die Gegenprobe sieht die gefilterten Kandidaten nicht.
**How to avoid:** Mit voll angegebenem Suchschlüssel (inkl. `primaryExchange`) suchen; Kandidaten in die Logzeile nur aus dem `list`-Fall. Dokumentiert als Grenze: eine zweite Quotierung auf anderem Primärmarkt wird durch `primaryExchange` im Schlüssel bereits ausgeschlossen.

### Pitfall 4: `halted=nan` heißt nicht „nicht gehalten"
**What goes wrong:** Jemand wertet `ticker.halted != 1` als „läuft".
**How to avoid:** Phase 3 wertet den Tick gar nicht (Zweig „nein"); im Ergebnistyp ist `halted` kein Ergebnis einer Messung, sondern ein von Phase 4 setzbarer Zustand. In der Doku explizit: „unbekannt, nicht ‚nein‘".

### Pitfall 5: Windows-Atomizität und Dateisperren
**What goes wrong:** `os.replace` schlägt unter Windows mit `PermissionError` fehl, wenn ein Editor/Virenscanner die Zieldatei offen hält; `contracts.json` bliebe dann alt, History-Zeile aber schon geschrieben.
**How to avoid:** Reihenfolge festlegen (temp schreiben -> History-Zeile + fsync -> `os.replace`); bei Fehler im Replace History-Zeile mit Folgezeile `status=aborted` ergänzen oder die Reihenfolge umdrehen und Lauf mit Exit 1 beenden. `PermissionError` nicht schlucken (Muster Phase 2). Temp-Datei in `finally` löschen.

### Pitfall 6: Schreibsperre und neue Aufrufe
**What goes wrong:** Neue Request-Wege laufen durch `Client.send`; die Wire-Sperre prüft das erste Feld als Msg-Id. Eine fehlerhafte Annahme über Ids würde den neuen Lesepfad blockieren.
**How to avoid:** Ein Integrationstest mit **echtem** unverbundenen `ib_async.IB()` ist nicht möglich ohne Socket; stattdessen unit-Test, der `_message_id` für die Felder-Köpfe von `reqContractDetails`/`reqMktData`/`reqMarketDataType` gegen `_WRITE_MESSAGE_IDS` prüft (Ids aus `client.py`: `reqMktData` sendet `[1, 11, …]` — erstes Feld `1`, nicht 3). Beim UAT-Lauf am echten Gateway ist das ohnehin die Endkontrolle. [VERIFIED für reqMktData: client.py:452 `fields = [1, 11, reqId, contract]`; ASSUMED für reqContractDetails/reqMarketDataType]

### Pitfall 7: `session-unknown` vs. `closed` bei Wochenende
**What goes wrong:** Samstag: `liquidHours` enthält `20261010:CLOSED` für Samstag, aber nicht zwingend jeden Tag (Horizont ~5 Tage, siehe Befund: Sonntag `CLOSED`, danach Mo-Fr). Ein fehlender „heute"-Eintrag am Samstag würde als `session-unknown` abweisen, obwohl das Ergebnis `closed` korrekt wäre (D-29 Exit 0).
**How to avoid:** Offene Frage 1 unten — vor dem Planen am Gateway einen Samstags-/Sonntagslauf als Fixture sichern oder die Regel festlegen. Gemessen ist: Sonntag `20261011:CLOSED` stand drin (Befund §5, AAPL), der Horizont beginnt also am Messtag. Für „Samstag" gibt es noch keine Messung.

### Pitfall 8: Parallele Operator-Arbeit
**What goes wrong:** Memory-Notiz „Operator co-works in parallel": `.planning/ibkr-marktdaten-befund.md` hat unbestätigte Operator-Änderungen.
**How to avoid:** Diese Datei in keinem Plan anfassen oder stagen; Commits nur mit expliziten Pfaden (`git add <pfad>`), nie `-A`.

## Runtime State Inventory

Nicht zutreffend (Greenfield-Modul, kein Rename/Refactor/Migration). Hinweis: `contracts.json`/`contracts-history.jsonl` entstehen neu unter `%LOCALAPPDATA%\TradingEngineX\ibkr\`; bei der Abnahme darf dort **keine** Alt-Datei vorliegen (Erst-`--init`-Lauf).

## Code Examples

### Zustandsentscheidung (Skizze, kein Code zum Abtippen)
```python
# ibkr_contracts.py (bibliotheksfrei)
SESSION_BUFFER_MINUTES = 15      # D-21, relativ zum Fenster, keine Uhrzeit
ALLOWED_SEC_TYPES = frozenset({"STK"})

# Prüfreihenfolge je Ticker: not-mapped -> not-allowed -> (Broker) not-found/ambiguous
# -> drift -> not-tradable -> session-unknown -> closed|ok
```

### Beide Datumsformate (Testfälle, echte Strings)
```
Neu:   20261011:CLOSED;20261012:0400-20261012:2000;...      (Befund §5, AAPL tradingHours)
Neu:   ;20261011:1800-20261012:1700;20261012:1800-20261013:1700   (XAUUSD: führendes ';', über Mitternacht)
Neu:   20261127:0930-20261127:1300                          (Halbtag; Datum als Testfixture, nicht gemessen)
Alt:   20090507:0700-1830                                   (nur unser Parser; ib_async: ValueError)
```
Hinweis: das Halbtag-Beispiel (`20261127`, Black Friday) ist ein **erfundenes Fixture**, kein gemessener Wert [ASSUMED]; die Struktur entspricht dem gemessenen Neu-Format.

### Quelle der Messung
Probe-Skripte (nur lesend, `clientId=20098`, Paper-Guard vorher): `…\scratchpad\probe_halt.py`, `probe2.py`, `probe_parse.py` (außerhalb des Repos, nicht committen).

## State of the Art

| Old Approach (Recherche-Annahme) | Current (gemessen) | Impact |
|-----------------|------------------|--------|
| `ineligibilityReasonList` als Handelbarkeits-Signal | Attribut fehlt in 2.1.0 | REQ-31 ändern (D-19) |
| Halted-Tick (49) auch mit delayed-Daten | Streaming: 321 „Incorrect generic tick list"; Snapshot: leer | D-20 Zweig „nein" |
| 10089/10090 als delayed-Meldung | Aktien melden 10167; 10089 nur Forex | 10167 in Mapping + INFO |
| `liquidSessions()` parst beide Formate | Alt-Format -> `ValueError` | Gegentest nur für Neu-Format |

**Deprecated/outdated:** nichts in dieser Phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Msg-Ids von `reqContractDetails` (9) und `reqMarketDataType` (59) liegen nicht in `_WRITE_MESSAGE_IDS` | Pattern 1 / Pitfall 6 | Schreibsperre blockiert den Lesepfad; fällt im FakeIB-Test/UAT sofort auf |
| A2 | Bedeutung von Fehler 154 (Halt) wie in REQUIREMENTS.md | D-20 | falsches Label in Phase 4; deshalb in Phase 3 nicht aufgenommen |
| A3 | `VALUE` ist die Pseudo-Börse in `validExchanges`, die Unhandelbarkeit anzeigt | Handelbarkeit | Prüfung greift nie; schadlos, da zusätzlich `SMART`/`MKT`/`LMT` verlangt werden |
| A4 | Halbtag-Fixture `20261127:0930-20261127:1300` entspricht dem realen Server-Format | Code Examples | Parser-Test belegt nur Struktur; Format ist identisch zum gemessenen Neu-Format, Risiko gering |
| A5 | Samstag-`liquidHours` enthält einen Eintrag für „heute" | Pitfall 7 | `session-unknown` statt `closed` am Wochenende (Exit 2 statt 0) — **vor Planabschluss messen** |

## Open Questions

1. **Wie sieht `liquidHours` am Samstag aus (Eintrag für „heute" vorhanden?)**
   - Bekannt: Sonntag-Messung zeigt `20261011:CLOSED` als erstes Segment; Horizont beginnt am Messtag.
   - Unklar: Samstag, Feiertag (z. B. Thanksgiving) — fehlt der Tag oder steht `CLOSED`?
   - Empfehlung: Operator/Agent führt am Samstag eine Lese-Probe aus und sichert den Rohstring als Test-Fixture; Regel „kein Eintrag für heute = `session-unknown`" bleibt dann streng. Bis dahin Fixture aus Befund verwenden und den Fall als UAT-Punkt führen. Alternative (nur mit Operator-Freigabe): „fehlt heute, aber ein späterer Tag ist belegt, und `now` liegt in keinem Fenster" => `closed`. Das lockert D-24; deshalb nicht ohne Rückfrage.
2. **Soll `resolve` ohne Gateway-Verbindung für `not-mapped`/`not-allowed` laufen?**
   - Bekannt: beide Abweisungen brauchen kein IBKR (SC2 „vor jeder Anfrage").
   - Unklar: Executor verbindet heute immer zuerst. Empfehlung: erst alle Ticker lokal klassifizieren; Verbindung nur, wenn mindestens ein Ticker `ok`-Kandidat ist. Vorteil: SC2 in CI/Offline ohne Gateway testbar und ein Tippfehler braucht kein Gateway. Planner entscheidet (Discretion).
3. **Zeitzone der Eingabe:** `now` ist UTC-aware (Executor: `datetime.now(UTC)`); `--now` als Test-/Operator-Override ist nicht beschlossen und sollte **nicht** als CLI-Option eingeführt werden (ein Override der Uhr wäre ein Weg um die Sitzungsprüfung). Test-Injection nur über die Python-Funktion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Paper-Gateway 127.0.0.1:7497 | UAT, Messungen | ✓ (Port offen, Probe lief) | 10.50.1 | Tests laufen mit FakeIB |
| ib_async | Gegentest, Adapter | ✓ (`.venv`) | 2.1.0 | `importorskip`; Fake-Tests |
| tzdata / zoneinfo | Parser | ✓ | im Extra gepinnt | — |
| uv (Netz) | Installation | ✗ SSL | — | `UV_OFFLINE=1`; direkt `.venv/Scripts/python.exe -m pytest` |
| Makefile (`make ci-local-lint`) | Lint laut Memory | ✗ im Repo-Root nicht gefunden | — | `UV_OFFLINE=1 uv run ruff check scripts tests` (Planner bitte das reale Lint-Kommando in `.github/workflows/ci.yml` nachlesen) |

**Missing dependencies with no fallback:** keine.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 + pytest-subtests, Marker `unit` (`--strict-markers`, `-m "not integration"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `UV_OFFLINE=1 uv run pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py tests/test_ibkr_isolation.py tests/test_ibkr_broker.py -x -q` |
| Full suite command | `UV_OFFLINE=1 uv run pytest -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-26 | `reqMarketDataType(3)` nach Guard gesendet; 10089/10090/10167 loggen INFO | unit (FakeIB) | `pytest tests/test_ibkr_broker.py -k "market_data or info_codes" -x` | ❌ Wave 0 (Erweiterung) |
| REQ-27 | Resolver importiert kein `tradingagents`/`symbols`; `XAUUSD+` -> CMDTY, nie `GC=F` | unit/AST | `pytest tests/test_ibkr_isolation.py -k symbols -x` | ❌ Wave 0 |
| REQ-28 | `XYZQ` not-mapped ohne Broker-Aufruf; `^GSPC`/`XAUUSD+` not-allowed | unit | `pytest tests/test_ibkr_contracts.py -k "mapped or allow" -x` | ❌ Wave 0 |
| REQ-29 | 2+ Kandidaten -> `ambiguous`, alle in **unserer** Logzeile | unit (FakeIB, caplog) | `pytest tests/test_ibkr_resolve.py -k ambiguous -x` | ❌ Wave 0 |
| REQ-30 | Lernen, Persistenz, Gegenprobe, manipulierter `conId` -> `drift`; fehlend/kaputt/Schema -> Stopp; `--rebaseline`, History | unit (tmp_path) | `pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py -k "persist or drift or init or rebaseline" -x` | ❌ Wave 0 |
| REQ-31 | `not-tradable` bei `VALUE`-only, ohne SMART, ohne MKT/LMT, leere Felder | unit | `pytest tests/test_ibkr_contracts.py -k tradable -x` | ❌ Wave 0 |
| REQ-37 | Parser (beide Formate, CLOSED, Halbtag, Mitternacht, `;`), Puffer-Grenzen, `session-unknown`, kein Sitzungswert auf Platte, Gegentest ib_async | unit | `pytest tests/test_ibkr_contracts.py -k "session or parse" -x` | ❌ Wave 0 |
| SC7 | Grep `13:30|14:30|09:30|16:00` in `scripts/ibkr_*.py` leer | unit | `pytest tests/test_ibkr_isolation.py -k hard_coded_times -x` | ❌ Wave 0 |
| D-26..D-30 | Exit 0/1/2, eine Konsolenzeile/Ticker, `--out` atomar, kein Ticker-Default | unit (FakeIB) | `pytest tests/test_ibkr_resolve.py -x` | ❌ Wave 0 |
| Handbuch | Exit-2-Zeile nicht mehr „reserved"; `resolve`-Abschnitt | unit | `pytest tests/test_ibkr_isolation.py -k handbook -x` | ❌ (bestehender Test `test_handbook_exit_table_matches_executor` anpassen) |

Hinweis zum SC7-Test: Suchmuster in den Testdateien selbst als zusammengesetzte Zeichenkette halten oder die Suche auf `scripts/ibkr_*.py` beschränken, sonst findet der Test sich selbst; `tests/` wird nicht durchsucht.

### Sampling Rate
- **Per task commit:** `UV_OFFLINE=1 uv run pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py tests/test_ibkr_isolation.py -x -q`
- **Per wave merge:** zusätzlich `tests/test_ibkr_broker.py tests/test_ibkr_executor.py` und `UV_OFFLINE=1 uv run ruff check scripts tests`
- **Phase gate:** Volle Suite grün, dann `/gsd:verify-work`; Lint selbst nachlaufen lassen, nicht der SUMMARY des Executors glauben (Memory-Notiz).

### Wave 0 Gaps
- [ ] `tests/test_ibkr_contracts.py` — Tabelle, Parser, Zustände, Persistenz, Gegentest (REQ-27..31, 37)
- [ ] `tests/test_ibkr_resolve.py` — `resolve`-Kommando, Exit-Codes, Ausgabe
- [ ] `tests/ibkr_fakes.py` erweitern — `FakeContract` (+`primaryExchange`, `tradingClass`), `FakeIB.qualifyContractsAsync` (0/1/n Slots, nach `returnAll`), `FakeIB.reqContractDetailsAsync` je `conId`/Symbol konfigurierbar (heute: immer Probe-Antwort), `reqMarketDataType`; `health()` darf nicht brechen
- [ ] `tests/test_ibkr_isolation.py` — Methodenmenge, AST-`symbols`, SC7
- [ ] Framework-Install: keiner

**UAT (Operator, Gateway):** `resolve --init AAPL MSFT NVDA` gegen das Paper-Gateway; `resolve AAPL MSFT NVDA` zweiter Lauf (Pfad „conId+exchange"); `resolve XYZQ ^GSPC XAUUSD+`; Samstags-Lauf (Open Question 1); manipulierter `conId` in der Datei -> `drift`. 10089/10090 sind real nur bei Forex beobachtet (SC8-Evidenz kommt aus dem Befund, nicht aus einem Phase-3-Lauf).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein (Paper-Guard aus Phase 2 bleibt) | `EXPECTED_ACCOUNT`-Konstante |
| V3 Session Management | nein | — |
| V4 Access Control | ja (Fail-closed Allow-List) | `ALLOWED_SEC_TYPES = {STK}`, Schreibsperre unverändert |
| V5 Input Validation | ja | exakter Tabellenvergleich der Ticker-Argumente; keine Pfad-/Shell-Auswertung; `--contracts`/`--out` als `Path` |
| V6 Cryptography | nein | — |
| V12 Files/Resources | ja | `contracts.json` atomar, Schema-Version, strenges Laden; History append-only |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Falscher Contract nach Corporate Action (Symbol wandert) | Tampering | `conId`-Persistenz + Gegenprobe + 4-Felder-Vergleich, Drift -> Exit 2 |
| Stilles Zurücksetzen der Identität durch gelöschte Datei | Tampering | D-12: fehlende Datei stoppt; nur `--init` legt an |
| Manipulierte/korrupte `contracts.json` | Tampering | D-14: ganzer Lauf stoppt, Schema-Version, Typprüfung jedes Felds (`conId` int > 0) |
| Mehrdeutiger Treffer -> falsche Order | Tampering | `len == 1` verlangen, Kandidaten loggen |
| Order außerhalb der Sitzung (parkt bis Eröffnung, Befund Warnung 399) | Tampering/Info | Fenster mit Puffer; `session-unknown` fail-closed |
| Uhr-Override umgeht Sitzungsprüfung | Tampering | kein `--now`-CLI-Schalter |
| Log-Injection über Roh-Ticker | Tampering | Ticker nur nach Tabellentreffer in Logs als Rohstring; vor Treffer mit `repr()` loggen |

## Sources

### Primary (HIGH confidence)
- ib_async 2.1.0 Quelltext in `.venv/Lib/site-packages/ib_async/`: `contract.py:546-635` (`TradingSession`, `_parseSessions`), `ib.py:1324` (`reqMarketDataType`), `ib.py:1358-1425` (`reqMktData`), `ib.py:2110-2180` (`qualifyContractsAsync`), `ib.py:2182-2202` (`reqTickersAsync`), `ib.py:2292` (`reqContractDetailsAsync`), `wrapper.py:120-160, 1255-1277` (Tick-Maps, `tickGeneric`), `client.py:443-467` (`reqMktData`-Wire)
- Messung am Paper-Gateway 10.50.1 (127.0.0.1:7497), 2026-10-12, `clientId=20098`, `readonly=True`, Paper-Guard `['DUQ634065']`: Halt-Tick-Matrix, `qualify`-Slots (AAPL/ES/XYZQ), conId+exchange-Abfrage, MSFT/NVDA, Fehler 200/321/10167, Parser-Ausführung
- Repo: `scripts/ibkr_broker.py`, `scripts/ibkr_executor.py`, `tests/ibkr_fakes.py`, `tests/test_ibkr_isolation.py`, `tests/test_ibkr_broker.py`, `.planning/ibkr-konto-befund.md` §4/§5, `.planning/ibkr-marktdaten-befund.md`, `02-VERIFICATION.md` (Override-Muster), `REQUIREMENTS.md` REQ-26..31/37/67, `ROADMAP.md` Phase 3

### Secondary (MEDIUM confidence)
- keine Websuche nötig; keine externe Doku herangezogen (IBKR-Doku zu Snapshot+generic ticks nicht abgerufen; die Aussage stützt sich auf die eigene Messung)

### Tertiary (LOW confidence)
- Msg-Ids 9/59 (A1) und Bedeutung von 154 (A2) aus Kenntnis, nicht verifiziert

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — keine neuen Pakete, Quelltext gelesen
- Architecture: HIGH — folgt den Phase-2-Mustern, die Tests erzwingen
- Pitfalls: HIGH für gemessene Punkte (1-4, 7 teilweise), MEDIUM für 5/6 (Windows-Dateisemantik, Msg-Ids)
- Halt-Entscheidung: HIGH für „liefert nicht", Grenze: kein positiver Halt-Fall beobachtbar

**Research date:** 2026-10-12
**Valid until:** 2026-11-11 (30 Tage) bzw. bis zum Gateway-Upgrade vor 2026-12-15 (Code 2172), das die Messungen neu laufen lassen sollte
