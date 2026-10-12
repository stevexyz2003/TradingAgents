# Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview - Research

**Recherchiert:** 2026-10-12
**Domäne:** Lokaler Python-Ausführer (`scripts/ibkr_*.py`) gegen IBKR-Paper-Gateway 10.50.1 mit `ib_async` 2.1.0; Entscheidungsquelle ist der Git-Branch `paper-log`
**Konfidenz:** MEDIUM-HIGH (Codebasis und Bibliotheksquellen gelesen und verifiziert; drei Gateway-Verhalten sind nicht messbar ohne Operator, siehe Offene Fragen)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Zugriff auf `paper-log`**
- **D-01:** Gelesen wird über `git fetch <remote> <branch>` und danach `git show <sha>:<pfad>`, **ohne Checkout und ohne Arbeitsbaum**. Für `scripts/state_maintenance.py verify --memory-log <kopie>` (REQ-15) landet eine Kopie von `decision-log.md` unter `%LOCALAPPDATA%\TradingEngineX\ibkr\` (Muster aus Phase 2/3).
- **D-02:** Scheitert der fetch (offline, Auth, SSL), stoppt der Lauf mit **eigenem benanntem Zustand** und Exit-Code. Es gibt **keinen Rückfall** auf den zuletzt lokal bekannten Ref, weil eine veraltete Sicht den Divergenzfall aus REQ-17 unsichtbar machen würde.
- **D-03:** Remote und Branch sind Settings: `IBKR_PAPER_LOG_REMOTE` (Default `fork`) und `IBKR_PAPER_LOG_BRANCH` (Default `paper-log`), im selben Settings-Mechanismus wie die bestehenden Executor-Settings.
- **D-04:** Der gelesene `paper-log`-Commit-SHA steht in der Logzeile und im Trockenlauf-JSON, als **Provenienz, nicht als Schlüssel** (REQ-39: kein SHA im `decision_key`).

**Aktualität in Sitzungen (REQ-19, REQ-20)**
- **D-05:** Die Vergangenheit wird über einen Börsenkalender gezählt, als **neue Abhängigkeit `exchange_calendars`** (Kalender `XNYS`). Grund: `liquidHours` reicht nur vom heutigen Tag etwa fünf Tage nach vorn, nicht zurück (`.planning/ibkr-konto-befund.md` §5, Rohausgabe). Für den **heutigen Tag** gilt `liquidHours` aus Phase 3. Widersprechen sich Kalender und `liquidHours` für heute (eine Quelle sagt Sitzung, die andere nicht), **stoppt** der Lauf mit eigenem Zustand.
- **D-06:** `weekend_gap` markiert **jede Kalenderlücke**: Liegt zwischen `trade_date` und Ausführung mehr als ein Kalendertag, aber keine geschlossene Sitzung (Wochenende, Feiertag oder beides), wird markiert, und die Zahl der Kalendertage wird mitprotokolliert. Ausgeführt wird trotzdem (REQ-20).
- **D-07:** Ein Lauf nimmt je Ticker den **neuesten** Eintrag in `decision-log.md`. Es gibt **keinen `--trade-date`-Schalter**, damit keine alte Entscheidung von Hand nachgeschoben werden kann. Die Aktualitätsregel entscheidet. Fixtures und Tests laufen über injizierte Pfade bzw. injizierte Quellen.
- **D-08:** Außerhalb einer Sitzung (abends, Wochenende) wird die Aktualität gegen die **nächste** Sitzung geprüft. Die Absicht wird als `closed` markiert, **`whatIf` läuft trotzdem**, weil es laut Befund auch außerhalb der Regelsitzung antwortet. So ist Phase 4 jederzeit testbar. SC4 (vier Gegenproben) wird mit injizierter Uhr und Kalender getestet.

**Blöcke, Ist-Position, offene Orders (REQ-21..24)**
- **D-09:** Die Stückzahl pro Block steht als neues Feld **`block_qty` je Eintrag in `CONTRACT_TABLE`** (`scripts/ibkr_contracts.py`), also als Code-Konstante wie D-01 aus Phase 3; jede Änderung ist ein Commit. Ein Unit-Test prüft, dass jeder handelbare Eintrag `block_qty > 0` hat. Es gibt keine Ableitung aus einem Kurs (REQ-22, REQ-68).
- **D-10:** Startwert: **1 Stück je Block** für AAPL, MSFT und NVDA. Damit gilt `Buy` = 2 Stück, `Overweight` = 1, `Underweight` = `Sell` = 0, und `Hold` erzeugt nie eine Order.
- **D-11:** Die Ist-Position kommt aus `positions()` (Phase 2) und wird über den **aufgelösten `conId`** abgeglichen, nicht über das Symbol. Eine Position auf einen anderen `conId` mit gleichem Symbol zählt nicht und wird gemeldet.
- **D-12:** Offene Orders kommen über eine **neue Adapter-Lesemethode**, die alle offenen Orders des Kontos für den `conId` liest. Weil Phase 4 selbst nie sendet, ist **jede** offene Order fremd (manuell oder TWS). Das ergibt einen eigenen Zustand und **keine Absicht für diesen Ticker**. Ab Phase 6 gehen eigene offene Orders in `Ziel − Ist − offen` ein (REQ-23).

**`whatIf` trotz Schreibsperre (REQ-38, -61, -69, -70, Halt-Teil REQ-37)**
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

### Deferred Ideas (OUT OF SCOPE)
- Feste Größen-Obergrenze pro Order, Kill-Switch, Ledger mit Write-Ahead und Lock: Phase 5.
- Verrechnung **eigener** offener Orders in `Ziel − Ist − offen`: Phase 6, sobald der Lauf selbst sendet.
- Limit-Orders mit Preisfindung aus Marktdaten, Marktdaten-Abo: außerhalb M2 (REQ-26, Offener Punkt 1 im Marktdaten-Befund).
- 4-Block-Leiter (Underweight ≠ Sell): Erweiterungspfad, nicht M2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Beschreibung | Research-Unterstützung |
|----|--------------|------------------------|
| REQ-IBKR-13 | Entscheidung nur aus `decision-log.md` via `TradingMemoryLog.load_entries()`, `summary.json` nur Vorbedingung | Abschnitt „Lesepfad paper-log"; `load_entries` liefert `date/ticker/rating` (`log.py:76,310`) |
| REQ-IBKR-14 | `schema_version != 1` → Exit 1 | Konsumentenvertrag + Test (SC7); `SUMMARY_SCHEMA_VERSION = 1` (`daily_paper_run.py:46`) |
| REQ-IBKR-15 | `state_maintenance verify` mit Kopie, Befund → Exit 2 | `verify(cache_dir, memory_log)` direkt aufrufen, leeres `--cache-dir` übergeben (Pitfall 4) |
| REQ-IBKR-16 | `status=="ok"` und 5 Stufen; `null`/`REVIEW` nie Order | `RATINGS_5_TIER`, `RATING_REVIEW` (`rating.py`); `null` heißt: kein Log-Eintrag (Pitfall 6) |
| REQ-IBKR-17 | Log-Rating ≠ Summary-Signal → kein Lauf, Exit 2, Log-Fassung gewinnt | Vorbedingungsfunktion rein; Fixture-Paar |
| REQ-IBKR-18 | Kein Zugriff auf `runs[*].report` | Konsumentenfelder enthalten `report` nicht; Test prüft das (AST/Feldliste) |
| REQ-IBKR-19 | Aktualitätsregel in Sitzungen | Algorithmus „Ausführungssitzung E" mit `exchange_calendars` XNYS (verifiziert) |
| REQ-IBKR-20 | `weekend_gap`-Markierung | `(E − trade_date).days > 1` ohne geschlossene Sitzung dazwischen |
| REQ-IBKR-21 | Signal → Zielblöcke | Tabelle `{Buy:2, Overweight:1, Hold:None, Underweight:0, Sell:0}`; Hold zuerst abfangen |
| REQ-IBKR-22 | Block = feste Stückzahl je Ticker | `block_qty` in `CONTRACT_TABLE` (D-09), kein Kursbezug |
| REQ-IBKR-23 | `Ziel − Ist − offen`, Toleranzband | Reine Funktion `plan_order`; fremde offene Order = eigener Zustand (D-12) |
| REQ-IBKR-24 | Long-only, Sell ohne Bestand = Nulloperation | Ziel ≥ 0 und SELL-Menge ≤ Bestand als Invariante |
| REQ-IBKR-25 | Markt-Order im Fenster der regulären Sitzung | Order `MKT`+`tif=DAY`; Fenster aus Phase-3-Zustand `ok`/`closed` |
| REQ-IBKR-38 | `whatIf` vor jeder Order; Margin, Kommission, `rejectReason` protokollieren | `preview_order`; **`OrderState` in ib_async 2.1.0 hat kein Feld `rejectReason`** (Pitfall 1) |
| REQ-IBKR-61 | Leere/unvollständige Vorschau = abgelehnt | Gescheiterte Anfrage liefert `[]` (wrapper `_endReq`), Unset-Margin = `1.797e308` (Pitfall 2) |
| REQ-IBKR-68 | Keine Größenschätzung ohne Kurs | Kein `reqMktData` im Pfad; AST-Wächter + `FakeIB`-Falle |
| REQ-IBKR-69 (Zusatz) | `tif` explizit, zurücklesen | `tif="DAY"`; Rücklesen über `openOrder`-Echo (Annahme A3) |
| REQ-IBKR-70 (Zusatz) | Budget über `initMarginChange` in Kontowährung | `available_funds` in `AccountSnapshot` ergänzen (heute nur Log) |
| REQ-IBKR-37 Halt-Teil (Übergabe) | Fehler 154 am `whatIf` → `halted` | 154 = „Orders cannot be transmitted for a halted security." (offizielle Codeliste) |
</phase_requirements>

## Zusammenfassung

Phase 4 ist zu etwa 80 % reine, gut testbare Fachlogik (Entscheidung lesen, Vorbedingungen, Aktualität, Zielrechnung, Toleranzband) und zu etwa 20 % neuer Adapter-Code mit echtem Risiko: eine `whatIf`-Anfrage geht auf der Leitung als Nachricht Id 3 (`placeOrder`) hinaus, also genau die Nachricht, die die Schreibsperre heute komplett blockt. Die Sperre muss deshalb von „Id 3 verboten" auf „Id 3 nur mit gesetztem `whatIf`-Feld" umgebaut werden, und zwar an drei Stellen gleichzeitig (Aufruf `client.placeOrder`, `client.send`, `client.sendMsg`). `ib.whatIfOrderAsync` ruft intern `self.client.placeOrder`, und dieses Attribut ist heute durch einen Refuser ersetzt; der Umbau ersetzt es durch einen Wächter, der nur Orders mit `whatIf is True` an die Originalmethode weiterreicht.

Drei Bibliotheksfakten, die die CONTEXT-Annahmen verschieben (alle in `ib_async` 2.1.0 gelesen): (1) `OrderState` hat **kein** `rejectReason`; ein „Ablehnungsgrund" kann nur aus `warningText` und aus den Fehlerereignissen des `whatIf`-Request kommen. (2) Eine gescheiterte `whatIf`-Anfrage endet mit **leerer Liste** (`RaiseRequestErrors=False`), 154 und 10349 sind dabei nur als Fehlerereignis sichtbar. (3) Ein Fehler 321 (Gateway im Read-Only-Modus) steht in `warningCodes`; er beendet die wartende Anfrage nicht, es bleibt nur das Timeout. Der Adapter muss deshalb Fehlercodes samt Text pro Request mitschreiben und Timeout plus 321 als `READ_ONLY_API` melden.

Die Aktualitätsregel ist mit `exchange_calendars` 4.13.2 (XNYS, mit pandas 3.0.6 und Python 3.13 in einem Scratch-Ziel geprüft) sauber als „Zähle XNYS-Sitzungen strikt zwischen `trade_date` und der Ausführungssitzung E" lösbar; alle vier Gegenproben aus SC4 fallen daraus ohne Sonderfall heraus. Offen und nicht ohne Operator messbar: ob der Gateway-Schalter „Read-Only API" auch `whatIf` blockt (D-14), ob das `openOrder`-Echo eines `whatIf` das wirksame `tif` trägt (REQ-69), und die Antwort bei einem real gehaltenen Wert (154 lässt sich nicht herbeiführen).

**Primäre Empfehlung:** Zuerst (Welle 1) die Schreibsperre auf „nur `whatIf`" umbauen und mit echter `ib_async.client.Client`-Klasse auf Leitungsebene testen; parallel die reine Fachlogik in ein neues bibliotheksfreies Modul `scripts/ibkr_decision.py` legen; Gateway-Messungen (D-14, tif-Echo) als Operator-Checkpoint planen, nicht als Voraussetzung für die Fachlogik.

## Architektur-Verantwortungskarte

Kein Web-Stack; die „Tiers" dieses Systems sind lokale Schichten.

| Fähigkeit | Primäre Schicht | Sekundär | Begründung |
|-----------|-----------------|----------|------------|
| `paper-log` lesen (fetch, SHA, Blobs) | Executor (`ibkr_executor.py`, Subprozess `git`) | — | Einziger Prozesskontakt zu Git; Fachlogik bekommt Text, nie Pfade |
| Eintrag parsen, Vorbedingungen, Divergenz | Fachmodul `scripts/ibkr_decision.py` (rein) | `tradingagents.memory` (Parser) | Kein Broker, keine Uhr; `TradingMemoryLog` ist der einzige Parser (REQ-13) |
| Aktualität (Kalender) | Fachmodul `ibkr_decision.py` | `exchange_calendars` | Uhr und Kalender werden injiziert (Guard aus 03-04) |
| Auflösung/Handelbarkeit/Sitzung | `ibkr_contracts.resolve_all` (Phase 3) | Broker-Adapter | Bereits vorhanden, wird nur aufgerufen |
| Ziel/Ist/offen, Toleranz, Menge | Fachmodul `ibkr_decision.py` | — | Reine Funktion über `block_qty` aus `CONTRACT_TABLE` |
| Positionen, offene Orders, `whatIf` | Broker-Adapter `ibkr_broker.py` | `ib_async` | Einziger Bibliothekskontakt (AST-Wächter) |
| Schreibsperre (Id 3 nur `whatIf`) | Broker-Adapter | — | Sicherheitskritisch, Leitungsebene |
| Budget-/Ablehnungsentscheid | Executor/Fachmodul | — | Vergleich von Zahlen, Exit-Mapping |
| Protokoll (JSON + Log) | Executor | `write_json_atomic` | Atomar unter `%LOCALAPPDATA%`; kein Ledger |

## Standard Stack

### Core
| Bibliothek | Version | Zweck | Warum |
|------------|---------|-------|-------|
| `ib_async` | 2.1.0 (exakt gepinnt, installiert) | IBKR-Client | Bestehende Entscheidung; nur `ibkr_broker.py` importiert sie |
| `exchange_calendars` | 4.13.2 (PyPI, 2026-10 aktuell) | XNYS-Sitzungskalender (D-05) | Von D-05 gesetzt; in Scratch-Ziel mit pandas 3.0.6/Py 3.13 geladen (0,21 s), `is_session`, `sessions_in_range`, `next_session`, `session_close` funktionieren [VERIFIED: lokaler Lauf] |
| `pandas` | 3.0.6 (bereits Kerndependency) | Von `exchange_calendars` benötigt | Kein Konflikt |
| Standardbibliothek: `subprocess`, `zoneinfo`, `dataclasses`, `json` | – | git-Aufrufe, Zeitzone, Werttypen | Kein neuer Code von Dritten nötig |

### Supporting
| Bibliothek | Version | Zweck | Wann |
|------------|---------|-------|------|
| `tradingagents.memory.TradingMemoryLog` | repo | Eintrags-Parser | Einziger Weg zu `entry["rating"]` (REQ-13) |
| `scripts/state_maintenance.py` | repo | `verify`/`check_decision_log` | REQ-15 |
| `pytest` 9.0.3, `ruff` 0.17.0 | installiert | Tests/Lint | `.venv/Scripts/python.exe -m pytest|ruff` |

### Alternativen
| Statt | Möglich | Abwägung |
|-------|---------|----------|
| `exchange_calendars` | `pandas_market_calendars` | Von D-05 ausgeschlossen (Entscheidung gesperrt) |
| `git show` | `git cat-file blob <sha>:<pfad>` | Gleiche Bytes; `cat-file` hat keine Pager-/Format-Überraschung. Beides binär-sicher als `bytes` lesen und selbst als UTF-8 dekodieren |

**Installation:** Abhängigkeit in den Extra `ibkr` eintragen (Executor-Werkzeug, nicht Kern):
```bash
# pyproject.toml, [project.optional-dependencies] ibkr:
#   "exchange_calendars>=4.13,<5",
.venv/Scripts/python.exe -m pip install -e ".[ibkr]"
```
`exchange_calendars` verlangt `tzdata>=2025.2`; der bestehende Deckel `tzdata>=2025.2,<2026.0` bleibt damit lösbar [VERIFIED: METADATA des Wheels]. `uv.lock` enthält `ib_async` heute gar nicht (grep leer), der Extra ist also nicht im Lock; keine Lock-Änderung nötig.

**Versionsprüfung:** `pip index versions exchange_calendars` → 4.13.2 (neueste), Wheel `py3-none-any`, `Requires-Python <4,>=3.10`; PyPI-Metadaten: erste Veröffentlichung 2021-02-02, ca. 1,2 Mio. Downloads/Woche, Quelle github.com/gerrymanoim/exchange_calendars [VERIFIED: PyPI-JSON, pypistats].

## Package Legitimacy Audit

| Paket | Registry | Alter | Downloads | Source Repo | slopcheck | Disposition |
|-------|----------|-------|-----------|-------------|-----------|-------------|
| exchange_calendars | PyPI | ca. 5,7 J | ca. 1,2 Mio./Woche | github.com/gerrymanoim/exchange_calendars | nicht ausführbar (SSL zu pypi.org im Tool) | Freigegeben durch D-05 des Operators; `[ASSUMED]` laut Protokoll → Planer setzt `checkpoint:human-verify` vor dem Install |
| korean_lunar_calendar | PyPI | – | – | transitiv | nicht ausführbar | transitiv `[ASSUMED]` |
| pyluach | PyPI | – | – | transitiv | nicht ausführbar | transitiv `[ASSUMED]` |
| toolz | PyPI | – | – | transitiv | nicht ausführbar | transitiv `[ASSUMED]` |

**Entfernt wegen [SLOP]:** keine. **Als [SUS] markiert:** keine. slopcheck war installierbar, scheiterte aber an `CERTIFICATE_VERIFY_FAILED` gegen pypi.org (bekanntes SSL-Problem dieser Maschine), daher alle Pakete `[ASSUMED]`. `pip index versions`/`pip download` über pip lief dagegen durch (Version und METADATA oben verifiziert).

## Architekturmuster

### Systemdiagramm (Datenfluss je Ticker)

```
CLI preview TICKER... ──► Settings (.env + IBKR_PAPER_LOG_REMOTE/BRANCH)
        │
        ▼
 git fetch <remote> <branch> ──fail──► state paper-log-unavailable (Exit 2*)   *siehe Offene Frage 2
        │ ok: SHA = rev-parse FETCH_HEAD
        ▼
 git show SHA:decision-log.md  ──► Kopie unter %LOCALAPPDATA%\...\ibkr\decision-log.copy.md
        │                                      │
        │                         state_maintenance.verify(--memory-log Kopie) ──Befund──► state-log-finding (Exit 2)
        ▼
 TradingMemoryLog.load_entries() ──► neuester Eintrag je Ticker (kein Eintrag → no-decision)
        │
        ▼
 git show SHA:runs/<trade_date>/summary.json ──► schema_version!=1 ► Exit 1
        │          status!="ok" / run fehlt ► run-not-ok     Rating∉5 Stufen / REVIEW ► rating-review
        │          Rating ≠ signal ► signal-divergence (Exit 2, Log-Fassung gewinnt)
        ▼
 Hold? ──► skipped-hold (kein Gateway nötig)
        ▼
 Aktualität (Uhr+XNYS) ──stale──► stale-decision (Exit 2);  Lücke ► weekend_gap-Marke
        ▼
 [Gateway] connect ► health ► resolve_all (Phase 3) ► rejected? ► Zustand (Exit 2)
        │                         ► Kalender vs liquidHours(heute) widerspricht ► calendar-conflict
        ▼
 positions() (nach conId) ─ fremder conId gleiches Symbol ► melden
 open_orders(conId) ─ vorhanden ► foreign-open-order (Exit 2)
        ▼
 plan_order: Ziel=blocks*block_qty; |Ziel−Ist|<block_qty ► within-tolerance (0)
             Ziel=0 und Ist=0 ► long-only-noop (0); sonst BUY/SELL qty
        ▼
 preview_order (whatIf, MKT, tif=DAY) ──► leer/unvollständig/Fehlertext ► preview-empty|preview-rejected (5)
                                       ──► 154 ► halted (5)   ──► initMarginChange ≥ AvailableFunds ► over-budget (5)
        ▼
 Protokoll: Logzeile + atomare JSON (SHA, State, Intent, Margin, Kommission, tif, closed-Marke). NICHTS gesendet.
```

### Empfohlene Struktur
```
scripts/
├── ibkr_broker.py     # + _arm_write_barrier umbauen, preview_order, open_orders, AccountSnapshot.available_funds, BrokerPosition.con_id
├── ibkr_contracts.py  # + block_qty in ContractSpec/CONTRACT_TABLE; SessionVerdict um "heute ist Handelstag laut liquidHours"
├── ibkr_decision.py   # NEU, bibliotheksfrei: Parser-Hülle, Vorbedingungen, Divergenz, Aktualität, plan_order, Zustände
├── ibkr_executor.py   # + Subkommando preview, git-Zugriff, Settings, Exit-Mapping, Protokoll
tests/
├── ibkr_fakes.py      # FakeIB: whatIfOrderAsync, reqAllOpenOrdersAsync, Order-Fabrik, Positionen mit conId
├── test_ibkr_decision.py, test_ibkr_paperlog.py, test_ibkr_preview.py, test_paper_summary_contract.py
```
`ibkr_decision.py` darf `tradingagents` **nicht** zur Importzeit ziehen, wenn der Wächter `test_resolver_is_library_free` auf ihn ausgedehnt wird; der Parser-Aufruf (`TradingMemoryLog`) liegt deshalb im Executor, `ibkr_decision.py` bekommt bereits geparste Einträge (`list[dict]`). (Der Executor importiert `tradingagents.portfolio` schon heute.)

### Muster 1: Schreibsperre „Id 3 nur mit `whatIf`" (D-13)
**Was:** `_arm_write_barrier` behält die Originalmethode `client.placeOrder` und ersetzt sie durch einen Wächter; `send`/`sendMsg` prüfen zusätzlich das `whatIf`-Feld im Inhalt (fail-closed bei unbekanntem Layout).
**Warum drei Stellen:** `IB.whatIfOrderAsync` ruft `self.client.placeOrder(reqId, contract, whatIfOrder)` (`ib.py:2204-2212`); die echte Methode serialisiert alle Felder und ruft `self.send(*fields)` (`client.py:472-707`), das über das Instanzattribut wieder durch den Wächter läuft; `send` baut den String und ruft `self.sendMsg(...)`.
**Layout (aus `client.placeOrder`, 2.1.0):** `fields = [3, orderId, contract, secIdType, secId, action, totalQuantity, orderType, lmtPrice, auxPrice, tif, ocaGroup, account, openClose, notHeld, dncFlag(+4 Felder wenn True), algoStrategy, (algoParams), algoId, whatIf, …]`. Auf Feldebene (in `send`) ist `contract` ein einziges Feld, auf String-Ebene (in `sendMsg`) expandiert es zu 12 Feldern (`conId, symbol, secType, lastTradeDate, strike, right, multiplier, exchange, primaryExchange, currency, localSymbol, tradingClass`); Bool wird `"1"`/`"0"`.
```python
# Skizze, scripts/ibkr_broker.py (Quelle: ib_async 2.1.0 client.py / ib.py, lokal gelesen)
def _whatif_in_fields(fields) -> bool:
    """True only if the parsed layout says whatIf is set. Unknown layout -> False (fail closed)."""
    try:
        i = 15                                   # index of the delta-neutral flag
        i += 5 if fields[i] else 1               # dnc: flag + 4 values, else flag only
        algo = fields[i]; i += 1
        if algo:
            return False                         # algo orders: not an M2 shape, refuse
        i += 1                                   # algoId
        return fields[i] is True
    except (IndexError, TypeError):
        return False

original_place = client.placeOrder
def guarded_place(order_id, contract, order):
    if getattr(order, "whatIf", None) is not True:
        raise ReadOnlyViolation("placeOrder without whatIf refused before it reached the gateway")
    return original_place(order_id, contract, order)
client.placeOrder = guarded_place
# guarded_send:  msg 3 -> allowed only if _whatif_in_fields(fields); other write ids unchanged.
# guarded_send_msg: msg 3 -> split("\0"): index 0 == "3", whatIf at 12 more positions: parse
#   the same layout on strings ("1" == set); unknown layout -> refuse.
```
**Test:** Mit der **echten** Klasse `ib_async.client.Client` und einer Stub-Verbindung (die `sendMsg`-Bytes mitschreibt) dieselbe Order einmal mit `whatIf=True` (geht durch, Feld an erwarteter Stelle `"1"`) und mit `whatIf=False` (`ReadOnlyViolation`, Stub empfängt nichts). Das fängt ein verschobenes Layout bei einem Bibliotheks-Update auf (Pin ist exakt `==2.1.0`, der Test macht ein Update laut). Die vorhandenen Tests mit `FakeIB` bleiben für Aufrufnamen; `WRITE_CALLS`-Prüfung `placeOrder`-Refuser muss auf „ohne whatIf refused" umgestellt werden. `cancelOrder`, `reqGlobalCancel`, `exerciseOptions`, Ids 4/19/21/58 bleiben hart gesperrt.
**Falle:** `tests/test_ibkr_isolation.py::test_adapter_hard_codes_no_order_id` verbietet im Adaptertext die Zeichenfolgen `orderId=` und `.orderId =`. Parameter also `order_id`, keyword-Aufrufe vermeiden.

### Muster 2: `preview_order` (Adapter, ein Request, vollständig ausgewertet)
```python
@dataclass(frozen=True)
class PreviewResult:
    state: str            # "OK" | "EMPTY" | "HALTED" | "READ_ONLY_API" | "TIF_OVERRIDDEN" | "REJECTED"
    init_margin_change: float | None   # Kontowährung
    maint_margin_change: float | None
    commission: float | None
    commission_currency: str
    warning_text: str
    errors: tuple[tuple[int, str], ...]  # (Code, Text) der Request-Fehler, reqId >= 0
    effective_tif: str | None            # aus dem openOrder-Echo, sonst None
    sent_tif: str                        # "DAY"
```
Ablauf: Offenen Link prüfen wie `_read`; `mark` auf `_request_errors`/Textliste setzen; `Order(action, totalQuantity=qty, orderType="MKT", tif="DAY", account=EXPECTED_ACCOUNT)` über `handles.order` (neues Feld in `IbHandles`, Default `None`, damit bestehende Fakes weiter laufen); Contract aus Identität (`conId`, `exchange="SMART"`, plus `secType`/`currency`/`primaryExchange`); `self._request("whatIf", lambda: ib.whatIfOrderAsync(contract, order))` mit `request_timeout`. `ib.whatIfOrderAsync` setzt `whatIf=True` auf einer Kopie selbst.
**Ergebnisauswertung (Reihenfolge wichtig):**
1. Fehler seit `mark` mit Code 154 → `HALTED` (auch wenn die Liste leer ist).
2. 10349 → `TIF_OVERRIDDEN` (Gateway hat `tif` überschrieben und die Anfrage verworfen, Befund 4).
3. `TimeoutError` und 321 in `_seen_codes` seit `mark` → `READ_ONLY_API` (321 beendet die Anfrage nicht, nur das Timeout; `wrapper.warningCodes`).
4. Ergebnis `[]`/`None`/kein `OrderState` → `EMPTY`; sonst Felder prüfen (Pitfall 2).
5. Link-Ereignis während des Fensters → verwerfen wie `_read`.
Der Adapter liefert nur Daten; Ablehnung vs. Budget entscheidet der Executor.

### Muster 3: Offene Orders (D-12)
`ib.reqAllOpenOrdersAsync()` (Msg-Id 16, nicht in `_WRITE_MESSAGE_IDS`) liefert `list[Trade]` über alle Clients inkl. TWS-Handorders; Abschluss kommt mit `openOrderEnd`. Filter auf `trade.contract.conId == con_id` und Status nicht in `OrderStatus.DoneStates`. Rückgabe broker-neutral (`OpenOrder(con_id, action, quantity, order_type, status, client_id)`). Läuft durch `_read` (Timeout, Linkprüfung). `reqOpenOrders` allein wäre für Orders anderer Clients unvollständig. Vorsicht: `FakeIB.reqAllOpenOrders` ist heute als „verboten" (wirft `AssertionError`) gebaut und muss für Phase 4 zur Async-Variante mit steuerbarer Antwort werden.

### Muster 4: Aktualität (REQ-19/20, D-05, D-06, D-08)
```python
# ibkr_decision.py (rein). calendar = exchange_calendars.get_calendar("XNYS"), injiziert.
def execution_session(now_utc, calendar):
    today = pd.Timestamp(now_utc.astimezone(calendar.tz).date())      # tz-naive Datum
    if calendar.is_session(today) and now_utc < calendar.session_close(today).to_pydatetime():
        return today.date(), True            # E = heute, Sitzung läuft oder kommt noch
    return calendar.next_session(today).date(), False   # abends, Wochenende, Feiertag -> nächste Sitzung (D-08)

def freshness(trade_date, now_utc, calendar):
    e, in_or_before_session = execution_session(now_utc, calendar)
    if trade_date >= e: return "future-decision"
    between = calendar.sessions_in_range(pd.Timestamp(trade_date) + 1 day, pd.Timestamp(e) - 1 day)
    if len(between): return "stale", len(between)                    # geschlossene Sitzung dazwischen
    gap = (e - trade_date).days
    return ("weekend_gap", gap) if gap > 1 else ("fresh", gap)
```
Alle vier Gegenproben (an echten Daten des Kalenders nachgerechnet bzw. aus den Sitzungsdaten abgeleitet):
| Fall | trade_date | Lauf | E | Sitzungen dazwischen | Ergebnis |
|---|---|---|---|---|---|
| Di-Lauf, Mo-Entscheidung | Mo | Di in Sitzung | Di | 0 | fresh (Lücke 1) |
| Sa-Lauf-Entscheidung am Mo | Fr (Hinweis unten) | Mo | Mo | 0 | executable, `weekend_gap` (3 Tage) |
| Mi verpasst, Do nachgeholt | Di | Do | Do | 1 (Mi) | stale, Exit 2 |
| Feiertagsmontag, Di-Lauf | Mo (Feiertag) | Di | Di | 0 | fresh (Lücke 1); `2026-09-07` ist Labor Day: `is_session` False [VERIFIED: lokaler Lauf] |
**Hinweis „Sa-Entscheidung":** `previous_weekday` (`daily_paper_run.py:120-123`) liefert nie Sa oder So; der Sa-06:30-Lauf hat `trade_date` = Freitag. Die Gegenprobe ist daher „Freitag-`trade_date`, Montag ausführen". Das passt zur Absicht von SC4; die Formulierung „Sa-Entscheidung" ist im Plan als „Entscheidung vom Sa-Lauf (trade_date Fr)" zu fassen.
**Datumsfalle:** `previous_weekday` kennt keine Feiertage. Ein Di-Lauf nach Feiertagsmontag hat `trade_date` = Montag (Feiertag, keine Sitzung, die Analyse nutzte die Daten von Freitag). Das ist kein Fehler der Regel: zwischen Mo und Di liegt keine geschlossene Sitzung, Ausführung ist erlaubt.
**Kalender gegen `liquidHours` für heute (D-05):** Phase 3 gibt im `ResolveResult` nur `state` (`ok`/`closed`/`session-unknown`), `window`, `next_open`. Daraus lässt sich „heute ist Handelstag laut liquidHours" nicht ableiten (`closed` gilt auch innerhalb eines Handelstags vor/nach dem Fenster). **Erweiterung nötig:** `SessionVerdict` bzw. `ResolveResult` bekommt ein Feld `session_day: bool | None` (heute hat Fenster → True; heute `:CLOSED` → False; kein Eintrag → None, bleibt `session-unknown`). Vergleich nur wenn der Lauf am Kalendertag in NY selbst `today` wertet (also jederzeit); bei Widerspruch `calendar-conflict`. Das ist eine kleine, getestete Änderung an `evaluate_session` (reine Funktion, bestehende Tests bleiben).
**Grenzen des Kalenders:** `get_calendar("XNYS")` deckt standardmäßig etwa −20 J bis +1 J ab; ein `trade_date` außerhalb löst `DateOutOfBounds`/`NotSessionError` aus → als `stale-decision` behandeln, nie als Absturz.

### Muster 5: Zielrechnung (REQ-21..24, rein)
```python
BLOCKS = {"Buy": 2, "Overweight": 1, "Underweight": 0, "Sell": 0}   # Hold ausdrücklich nicht drin

def plan_order(rating, held_qty, open_net_qty, block_qty):
    if rating == "Hold": return Plan("skipped-hold")
    target = BLOCKS[rating] * block_qty                      # >= 0 immer: long-only
    if open_net_qty != 0: return Plan("foreign-open-order")  # D-12, vor der Rechnung
    if held_qty == 0 and target == 0: return Plan("long-only-noop")      # Sell/Underweight ohne Bestand
    if abs(target - held_qty) < block_qty: return Plan("within-tolerance")
    diff = target - held_qty
    if not float(diff).is_integer(): return Plan("fractional-qty")
    side = "BUY" if diff > 0 else "SELL"
    assert side == "BUY" or -diff <= held_qty                # nie Short
    return Plan("intent", side, int(abs(diff)))
```
`held_qty` kommt aus `positions()` gefiltert auf den **aufgelösten `conId`**; Positionen mit gleichem Symbol, anderem `conId` werden gezählt und als Warnung protokolliert, nicht verrechnet (D-11). Das heutige `BrokerPosition` hat **kein** `con_id`; Feld ergänzen (`p.contract.conId`), `tests/ibkr_fakes.position()` muss einen `conId` setzen können.
**Verhalten, das der Plan bewusst benennen sollte:** Ein bestehender Bestand über dem Ziel wird per Zielrechnung abgebaut (`Overweight`=1 Stück, Bestand 3 → SELL 2). Das ist die vom Operator gesetzte Zielmechanik (REQ-21), betrifft aber manuell gehaltene Papier-Positionen. Phase 4 sendet nichts, aber das Protokoll zeigt es.

### Muster 6: Lesepfad `paper-log` (D-01..D-04)
```python
def read_paper_log(repo, remote, branch, run=subprocess.run):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    f = run(["git", "fetch", "--no-tags", "--quiet", remote, f"+refs/heads/{branch}"],
            cwd=repo, env=env, capture_output=True, timeout=60)
    if f.returncode: raise PaperLogUnavailable(f.stderr.decode("utf-8", "replace"))
    sha = run(["git", "rev-parse", "FETCH_HEAD"], cwd=repo, capture_output=True, timeout=10, check=True).stdout.decode().strip()
    blob = lambda path: run(["git", "show", f"{sha}:{path}"], cwd=repo, capture_output=True, timeout=30)
```
Verifiziert am echten Repo: `git fetch fork paper-log` ist exit 0, `FETCH_HEAD` = `71df89df8a078acdcea92f966c10332086f6cf43`, Remote `fork` → github.com/stevexyz2003/TradingAgents (Fetch-Refspec `+refs/heads/*:refs/remotes/fork/*`). `git show <sha>:decision-log.md` liefert die Datei; `runs/2026-10-09/summary.json` existiert, `runs/2026-10-10`/`-11` nicht.
- **Bytes statt Text lesen**, dann `utf-8` selbst dekodieren (`errors="strict"`): Windows-Textmodus würde `\n` verändern und der `_SEPARATOR` (`<!-- ENTRY_END -->` mit Zeilenumbrüchen) könnte sich verschieben; Parser und `verify` müssen auf identischen Bytes laufen.
- `GIT_TERMINAL_PROMPT=0` und `timeout`, sonst hängt ein Auth-Prompt den Lauf (kein TTY). Ein Hang ist Zustand `paper-log-unavailable`.
- Der Runner (`run`) ist injizierbar; Tests brauchen kein Git und kein Netz (`conftest._no_network` blockt Python-Sockets, nicht Git-Subprozesse, daher ist die Injektion Pflicht, nicht Kür).
- `decision-log.md.lock` ist 0 Byte im Branch und wird ignoriert.

### Anti-Muster
- **Eintrag für `trade_date` filtern statt „neuester je Ticker":** D-07 sagt neuester Eintrag; REQ-13 formuliert `entry["date"] == trade_date` — beides vereinbar: erst neuester Eintrag, dessen `date` ist dann das `trade_date` für Summary und Aktualität.
- **`verify` ohne `--cache-dir`:** prüft sonst die Checkpoint-DBs des Operators mit (Pitfall 4).
- **Hold erst nach Gateway-Verbindung prüfen:** SC1 muss ohne Gateway laufen können.
- **`ib.whatIfOrder()` (blockierend) benutzen:** läuft über `_run` und die Library-Loop statt über `_call` mit Timeout; immer `whatIfOrderAsync` unter `_request`.
- **Preis oder Kurs schätzen (REQ-68):** keine `reqMktData`/Ticker-Aufrufe im Pfad.

## Nicht selbst bauen

| Problem | Nicht bauen | Stattdessen | Warum |
|---------|-------------|-------------|-------|
| Börsenkalender / Feiertage | eigene Feiertagsliste | `exchange_calendars` XNYS | Halbtage, Sonderschließungen, Verschiebungen |
| Decision-Log-Parsing | eigener Regex | `TradingMemoryLog.load_entries()` | REQ-13; `_parse_entry` ist die einzige Wahrheit |
| Log-Integritätsprüfung | eigener Block-Zähler | `state_maintenance.verify`/`check_decision_log` | zählt Blöcke vs. Einträge, fängt stilles Verwerfen |
| Atomares JSON | eigene Schreiblogik | `ibkr_contracts.write_json_atomic` | vorhanden, getestet |
| Sitzung heute | eigene Uhrzeiten | `evaluate_session`/`resolve_all` (Phase 3) | Guard verbietet Uhrzeit-Literale |
| `whatIf`-Protokoll | eigene Serialisierung der Nachricht | `ib.whatIfOrderAsync` hinter dem Wächter | Layout gehört der Bibliothek |
| Wechselkurs für Budget | EUR/USD-Rechnung | `initMarginChange` (Kontowährung) | REQ-70, Befund 4 |

## Laufzeit-Zustandsinventar
Entfällt (keine Umbenennung/Migration). Neue Laufzeitzustände: `%LOCALAPPDATA%\TradingEngineX\ibkr\` bekommt Kopie von `decision-log.md` und Trockenlauf-JSON; keine bestehenden Daten ändern sich. `contracts.json` wird nur durch `resolve_all` im Lernmodus berührt (Pitfall 9).

## Häufige Fallstricke

### Pitfall 1: `rejectReason` existiert in `ib_async` 2.1.0 nicht
**Was schiefgeht:** REQ-38 und SC2 verlangen „`rejectReason` protokollieren". `OrderState` (`order.py:308-325`) hat nur `status`, die Margin-Felder, Kommissionen, `warningText`, `completedTime/Status`; der Decoder (`decoder.py:1058-1077`) liest kein Reject-Feld. [VERIFIED: grep + Quelle]
**Vermeiden:** „Ablehnungsgrund" definieren als Konkatenation aus (a) `warningText` des `OrderState`, (b) Text aller Request-Fehler (`reqId >= 0`, nicht in `INFO_CODES`) im `whatIf`-Fenster. Das Protokollfeld heißt weiter `rejectReason` (Operator-Vokabular), Quelle im Feldnamen dokumentieren (`reject_source`). Leeres `rejectReason` + vollständige Margin-Felder = G2 erfüllt. Entscheid: ein nicht leerer `warningText` allein ist **Warnung**, keine Ablehnung (Befund-Messung 1.0 EUR Kommission ohne Warnung; unbekannt, ob IBKR Warnungen wie „Order wird gehalten" über `warningText` schickt) → protokollieren, aber nur bei zusätzlichem Fehler/Leere ablehnen. `[ASSUMED]` (A2).
**Warnzeichen:** Test erwartet `state.rejectReason` und scheitert an `AttributeError`.

### Pitfall 2: „Erfolg" bei Unset-Werten und leerer Liste
**Was schiefgeht:** Gescheiterte `whatIf`-Anfragen liefern `[]` (der `_results`-Container, `wrapper._endReq`), nicht `None` und keinen Fehler (`RaiseRequestErrors=False`, `wrapper.py:1613-1625`). Der Wrapper beendet die Anfrage mit Erfolg nur, wenn `float(initMarginChange) != UNSET_DOUBLE` (`wrapper.py:680-683`); sonst Hängen bis Timeout. Felder können `"1.7976931348623157E308"` (UNSET) tragen.
**Vermeiden:** `float()`-Parsing mit `ValueError`-Fang; Werte `>= 1e300` oder NaN → fehlt. „Vollständig" = `initMarginChange`, `maintMarginChange` (beide gesetzt), `commission` gesetzt (`!= UNSET_DOUBLE`, `commissionCurrency` nicht leer). Alles andere `preview-empty` (Exit 5).
**Warnzeichen:** Test mit `OrderState()` Default (alle `""`/Unset) wird als OK durchgewunken.

### Pitfall 3: 321 hängt statt zu scheitern; 10349 verwirft still
321 steht in `warningCodes` (`wrapper.py:1583`): kein `_endReq`, nur Timeout (deckt sich mit der Konto-Befund-Beobachtung „Sondierungslauf blieb ohne Antwort hängen"). 10349 gibt leere Liste (Befund 4). `STATE_BY_CODE` kennt 321 schon als `READ_ONLY_API`; 10349 und 154 ergänzen (`TIF_OVERRIDDEN`, `HALTED`) und aus `_request_error_since` heraushalten, damit `preview_order` sie selbst auswertet statt als generisches `REQUEST_FAILED`.

### Pitfall 4: `state_maintenance verify` prüft mehr als das Log
`verify(cache_dir, memory_log)` iteriert zusätzlich die Checkpoint-DBs in `<cache_dir>/checkpoints`; Default ist der Cache des Operators (`DEFAULT_CONFIG["data_cache_dir"]`). Ein defekter fremder Checkpoint würde Phase 4 mit Exit 2 stoppen. Aufruf deshalb mit leerem Temp-Verzeichnis als `cache_dir`, oder `check_decision_log(kopie)` direkt (dasselbe Prüfstück). Fehlt die Datei/ist sie leer, meldet `verify` „nothing to check" mit Exit 0: den Dateivorhandensein-Check selbst machen. Eingabe: Kopie, nicht der git-Blob im Speicher (die Funktion liest Pfade).

### Pitfall 5: Ein `null`-Signal erreicht den Log nie
`store_decision` wird nur im Erfolgsfall aufgerufen; ein `failed`/`skipped`/`budget_aborted`-Lauf erzeugt **keinen** Log-Eintrag. REQ-16 „`null` → nie Order" realisiert sich also als: neuester Eintrag ist alt → Aktualitätsregel → `stale-decision`; zusätzlich muss Phase 4 für den **aktuellen** Tag nachsehen, ob `summary.json` eines neueren `trade_date` `status != "ok"` für den Ticker meldet, sonst bleibt der Grund unklar (stale statt run-not-ok). Echter Stand: alle Läufe 09-24 bis 10-08 sind `failed` (OpenAI-429, kein Guthaben, siehe `runs/*/summary.json`); `runs/2026-10-10`, `-11` fehlen im Branch trotz Commits „paper-run: auto". Der Plan sollte „Summary des neuesten Eintrags-Datums" (für Divergenz) von „neuester Summary im Branch" (für Diagnose, optional) trennen.

### Pitfall 6: Divergenz ist nur bei vorhandenem Summary prüfbar
Fehlt `runs/<date>/summary.json` zu einem Log-Eintrag, ist weder Divergenz noch `status` prüfbar → eigener Zustand `summary-missing`, Exit 2, keine Order (fail closed). Rating-Vergleich exakt und case-sensitiv gegen `signal`.

### Pitfall 7: Fehlerhandling in `_guarded`
`ReadOnlyViolation` wird im Executor auf `WRITE_REFUSED`/Exit 3 abgebildet. Läuft die Sperre künftig für `whatIf` durch, darf ein echter Verstoß weiter nur als `WRITE_REFUSED` enden; Test, dass `preview` die Exception nie schluckt.

### Pitfall 8: Mehrere Tickers und Exit-Code
`resolve` verarbeitet alle Ticker und gibt dann 2 bei irgendeinem Reject. Für `preview`: alle Ticker verarbeiten, Exit = schwerster Code nach fester Reihenfolge (Gateway/Guard-Abbruch bricht sofort ab; sonst `max`-Logik über 0/2/5 prüfen, dass 5 vor 2 steht, weil eine abgelehnte Order-Vorschau gravierender ist als eine Vorbedingung). Als Tabelle `EXIT_BY_STATE` halten, damit Änderungen (Offene Frage 1) einzeilig sind.

### Pitfall 9: `resolve_all` lernt im Run-Modus fehlende Ticker
Ein Ticker ohne Eintrag in `contracts.json` wird im `MODE_RUN` neu gelernt und erzeugt History-Events. Das ist für Phase 4 unerwünscht still. Empfehlung: vor `resolve_all` prüfen, dass der Ticker in `contracts.json` steht; sonst Zustand `not-resolved-yet` (Exit 2, Hinweis `resolve --init`), und keine Events committen. Bleibt `contracts.json` fehlend, gilt wie bei `resolve` `CONTRACTS_MISSING` Exit 2.

### Pitfall 10: Geld in Kontowährung
`AvailableFunds` kommt je Kontowährung (`AccountSnapshot.cash_currency` EUR); `initMarginChange` ebenso. Vor dem Vergleich Währungs-Gleichheit prüfen (`account_value.currency`), sonst Zustand `currency-mismatch` (Exit 5). Beim `SELL` ist `initMarginChange` negativ/null (Entlastung): Budgetprüfung gilt trotzdem (`< AvailableFunds`) und ist dann trivial wahr. `AvailableFunds`-Zeile muss genau einmal vorhanden sein (wie `TotalCashValue`), sonst `SNAPSHOT_INCOMPLETE`.

### Pitfall 11: Handbuch und Wächter
Neue Wächter in `test_ibkr_isolation.py`: `test_handbook_exit_table_matches_executor` erwartet **genau 10** `EXIT_*`-Konstanten und jeden Wert in der Handbuch-Tabelle; `test_handbook_exit_two_is_active` verbietet „reserved" in Zeile 2. Exit 5 aktiv setzen (Handbuch + Modul-Docstring „reserved for later phases" entfernen) und ein Gegenstück `test_handbook_exit_five_is_active` anlegen. Handbuch darf `ib_async` nicht nennen. Public-Methoden-Test: Menge auf `{connect, positions, health, search_contract, contract_details, preview_order, open_orders}` (7 ≤ 10) anheben.

## Code-Beispiele

### Konsumentenvertrag `summary.json` (SC7, REQ-14, REQ-18)
```python
# ibkr_decision.py: einzige Quelle der gelesenen Felder
SUMMARY_SCHEMA_VERSION = 1
SUMMARY_FIELDS = {"schema_version": int, "trade_date": str, "status": str, "runs": list}
RUN_FIELDS = {"ticker": str, "status": str, "signal": (str, type(None))}   # report bewusst NICHT (REQ-18)
RUN_STATUSES = frozenset({"ok", "failed", "budget_aborted", "skipped"})

def read_summary(text): ...   # json.loads; fehlende/falsch typisierte Felder -> SummaryContractError (Exit 1)
```
```python
# tests/test_paper_summary_contract.py: erzeugt die Summary mit dem ECHTEN Erzeuger
runner = _load_runner()                         # wie tests/test_daily_paper_run.py:26
... _run_main(monkeypatch, tmp_path, FakeGraph(signal="Buy"))      # vorhandener Helfer :289
summary = json.loads((tmp_path / "out" / "summary.json").read_text("utf-8"))
assert runner.SUMMARY_SCHEMA_VERSION == ibkr_decision.SUMMARY_SCHEMA_VERSION
ibkr_decision.read_summary(json.dumps(summary))                   # additive Felder bleiben grün
# Negativ-Kontrolle: Feld entfernt/umbenannt/Typ geändert -> SummaryContractError
```
Zusätzlich Rundlauf: `TradingMemoryLog.store_decision(...)` schreibt in eine Temp-Datei, `load_entries()` liefert `date/ticker/rating` wie vom Konsumenten gelesen. Nicht-additive Änderung = Entfernen/Umbenennen/Typänderung eines Feldes aus `SUMMARY_FIELDS`/`RUN_FIELDS`, Wertebereich von `status`, `schema_version`-Änderung. Additive Felder dürfen den Test nicht brechen (Test-Fall mit Zusatzfeld).

### Fehlerprüfung am `whatIf`-Ergebnis
```python
def judge_preview(p, available_funds, funds_currency, account_currency):
    if p.state != "OK": return {"HALTED": "halted", "READ_ONLY_API": "preview-empty", ...}[p.state]
    if None in (p.init_margin_change, p.commission) or not p.commission_currency: return "preview-empty"
    if p.errors: return "preview-rejected"          # rejectReason = joined error texts (+ warning_text)
    if funds_currency != account_currency: return "currency-mismatch"
    if p.init_margin_change >= available_funds: return "over-budget"
    return "preview-ok"
```

## Stand der Technik

| Alt | Aktuell | Seit | Wirkung |
|-----|---------|------|---------|
| `placeOrder` komplett gesperrt (Phase 2) | Id 3 nur mit `whatIf` | Phase 4 | `whatIf` läuft, echte Order bleibt unmöglich |
| Read-Only im Gateway als Schutz | Socket-Sperre als Hauptschutz | Phase 2 Befund (Operator schaltet ab) | D-14 |
| `LimitOrder` ohne `tif` | `tif` immer explizit | Befund 4, 2026-10-12 | sonst leere Liste (10349) |

**Veraltet:** Erwartung „10015 bei Read-Only" → real 321. `rejectReason` am `OrderState` → existiert in dieser Bibliotheksversion nicht.

## Annahmen-Log

| # | Aussage | Abschnitt | Risiko bei Irrtum |
|---|---------|-----------|-------------------|
| A1 | Gateway-Schalter „Read-Only API" blockt `whatIf` (321) oder nicht: **ungemessen** (nur das Bibliotheksverhalten „321 = Warnung, Timeout" ist aus der Quelle belegt) | Muster 2, Pitfall 3 | SC2 bleibt ohne Operator-Test unbelegt; D-14 verlangt Messung |
| A2 | `warningText` bei Preview ist nur Hinweis, nicht Ablehnung; IBKR liefert kein eigenes „Reject"-Feld im `OrderState` für 10.50.1 | Pitfall 1 | zu lasche/zu strenge Ablehnung; per Live-Messung klären |
| A3 | Das `openOrder`-Echo einer `whatIf`-Anfrage trägt das wirksame `tif`; Abgriff über Wrapper des `wrapper.openOrder` im Zeitfenster (der Wrapper wirft das `Order`-Objekt weg und gibt nur `orderState` an die Future) | REQ-69 | `effective_tif` bleibt `None`; Ersatz: 10349-Abwesenheit als Beleg, gesendetes `tif` protokollieren |
| A4 | Contract mit `conId` + `exchange="SMART"` + `secType`/`currency`/`primaryExchange` reicht für `whatIf` (Befund 4 maß mit vollständig qualifizierten Contracts) | Muster 2 | Preview leer; im Live-Test mit der Identität aus `contracts.json` prüfen |
| A5 | Code 154 am `whatIf` hat `reqId` des Requests und ergibt leere Liste; die Bedeutung ist offiziell, ein reales Auslösen ist nicht möglich | Muster 2 | `halted` nur per Unit-Test mit Fake belegt; REQ-67 verlangt Messung, hier nicht herstellbar → im Verifikationsbericht ausweisen |
| A6 | `exchange_calendars` ist legitim (Alter, Downloads, Quelle geprüft; slopcheck nicht lauffähig) | Package Legitimacy | Supply-Chain; `checkpoint:human-verify` vor Install |
| A7 | `git fetch <remote> +refs/heads/<branch>` + `FETCH_HEAD` verhält sich wie am echten Repo gemessen auch bei erster Nutzung eines frisch geklonten Remotes | Muster 6 | Für Operator unkritisch |

## Offene Fragen

1. **Exit-Code für `Hold` und weitere „nichts zu tun"-Zustände (Konflikt D-16 vs. Modul-Doku).**
   - Bekannt: D-16 zählt `Hold` unter „Vorbedingungen … bleiben Exit 2". Der Executor-Docstring sagt „0 ok, including nothing to do"; SC1 verlangt `skipped: hold` ohne Exitwert.
   - Unklar: Soll ein täglicher Hold wirklich Exit 2 erzeugen.
   - Empfehlung: D-16 wörtlich umsetzen (Hold = 2), aber `EXIT_BY_STATE` als einzige Tabelle halten und die Frage im ersten Plan als `checkpoint:decision` markieren. `within-tolerance`, `long-only-noop`, `closed` → Exit 0 (SC6/SC8 sprechen von „keine Order"/„Nulloperation").
2. **Exit-Code für `paper-log-unavailable` (D-02) und `summary-missing`.** CONTEXT nennt „eigenen Zustand und Exit-Code" ohne Wert. Empfehlung: Exit 2 (Vorbedingung nicht erfüllt) für beide; nur Gateway-Fehler bleiben 3.
3. **D-14 Messung.** Braucht den Operator: Gateway „Read-Only API" an, dann `whatIf` AAPL einmal über eine kleine Sonde. Vorschlag: Sonde `scripts/`-extern (nicht im Repo) mit der neuen Sperre, Ergebnis mit Datum in `.planning/ibkr-konto-befund.md`. Das Gateway lauscht auf `127.0.0.1:7497` (Port offen, 2026-10-12), der Schalter ist laut Befund aus; ich habe bewusst nichts gesendet. Plan: Checkpoint `human-action` am Ende von Welle 1, Fachlogik blockiert nicht darauf.
4. **Welche Ticker laufen?** `resolve` hat keine Default-Liste. Empfehlung: `preview TICKER...` mit Pflicht-Positionals (Muster wie `resolve`); „Ticker kommt aus der Entscheidung" heißt: Block/Contract werden je Ticker aus Tabelle und Entscheidung gezogen. Ein Ticker ohne Log-Eintrag → `no-decision` (Exit 2).
5. **SC1 gegen den „echten" Branchstand.** Am 2026-10-12 (Mo) gilt der Fr-Eintrag noch (E = Mo, `weekend_gap` 3 Tage), ab Mi 14.10. wäre er `stale-decision` (Exit 2) vor Hold. Plan: SC1 als Test mit eingefrorener Kopie von Commit `71df89d` und injizierter Uhr 2026-10-12; zusätzlich Operator-Handlauf in HUMAN-UAT am Mo/Di.

## Verfügbarkeit der Umgebung

| Abhängigkeit | Benötigt von | Verfügbar | Version | Fallback |
|--------------|--------------|-----------|---------|----------|
| git | Lesepfad | ✓ | 2.56.0.windows.1 | — |
| Remote `fork` / Branch `paper-log` | Lesepfad | ✓ (fetch exit 0, SHA 71df89d) | — | Test mit Fixture |
| Python venv | Tests | ✓ | 3.13.13 (venv); `python` im PATH ist 3.10.11, nicht benutzen | `.venv/Scripts/python.exe` |
| `ib_async` | Adapter | ✓ | 2.1.0 | — |
| `exchange_calendars` | Aktualität | ✗ im venv (in Scratch-Ziel geprüft: 4.13.2 lädt) | – | Install via Extra `ibkr`; kein Fallback (D-05) |
| IBKR-Paper-Gateway | Live-Messung | ✓ Port 7497 offen | 10.50.1 | Unit-Tests mit `FakeIB` |
| `uv` | – | ✓ 0.11.7, SSL-Problem | – | `.venv/Scripts/python.exe -m …` |

**Fehlend ohne Fallback:** `exchange_calendars` bis zum Install. **Hinweis:** `pip` über den venv lief im Test durch (kein SSL-Fehler), `slopcheck` nicht.

## Validierungsarchitektur

### Test-Framework
| Eigenschaft | Wert |
|-------------|------|
| Framework | pytest 9.0.3 (`-m "not integration"`, `--strict-markers`, Marker `unit`) |
| Konfiguration | `pyproject.toml [tool.pytest.ini_options]`, `tests/conftest.py` (blockt Python-Sockets) |
| Schnelllauf | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_ibkr_preview.py tests/test_paper_summary_contract.py -x -q` |
| Volllauf IBKR | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_contracts.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py tests/test_ibkr_resolve.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_paper_summary_contract.py -q` |
| Lint | `.venv/Scripts/python.exe -m ruff check scripts tests` |
Basislinie heute: 419 passed in 7,2 s (obige Dateien ohne die neuen).

### Anforderung → Test-Zuordnung
| Req / SC | Verhalten | Typ | Automatisierter Befehl | Datei |
|----------|-----------|-----|------------------------|-------|
| SC1 / REQ-21 | Echter Branchstand (AAPL Hold 10-09, eingefrorene Kopie von 71df89d) → `skipped-hold`, kein Gateway-Kontakt, keine Order | unit/E2E-Fake | `pytest tests/test_ibkr_preview.py -k real_branch_hold -x` | ❌ Wave 0 |
| SC2 / REQ-38, -25 | Buy-Fixture + flache Position → Intent „BUY 2", `whatIf` MKT/DAY, Log Margin/Kommission/`rejectReason`, `FakeIB.calls` enthält keinen echten Versand | unit | `pytest tests/test_ibkr_preview.py -k buy_flat -x` | ❌ Wave 0 |
| SC2 / D-13 | Schreibsperre: `whatIf` passiert Leitung, `placeOrder` ohne `whatIf` → `ReadOnlyViolation`, Ids 4/19/21/58 weiter blockiert, mit echter `Client`-Klasse | unit | `pytest tests/test_ibkr_broker.py -k "whatif_barrier or place_order_refused" -x` | ❌ Wave 0 |
| SC3 / REQ-17 | Log „Buy" vs Summary „Sell" → Exit 2, `signal-divergence`, gelesen = Log-Fassung | unit | `pytest tests/test_ibkr_decision.py -k divergence -x` | ❌ Wave 0 |
| SC4 / REQ-19, -20 | Vier Gegenproben mit injizierter Uhr + echtem XNYS-Kalender (+ Feiertagsmontag 2026-09-07) | unit | `pytest tests/test_ibkr_decision.py -k freshness -x` | ❌ Wave 0 |
| SC5 / REQ-14,-15,-16 | `null`, `REVIEW`, `status!=ok`, `schema_version!=1` (Exit 1), `verify`-Befund (Exit 2) → je eigener Zustand, `FakeIB.calls` ohne `whatIf` | unit | `pytest tests/test_ibkr_decision.py tests/test_ibkr_preview.py -k "preconditions or schema or verify" -x` | ❌ Wave 0 |
| SC6 / REQ-23 | `|Ziel−Ist|<Block` → `within-tolerance`; fremde offene Order → `foreign-open-order` | unit | `pytest tests/test_ibkr_decision.py -k "tolerance or open_order" -x` | ❌ Wave 0 |
| SC7 / REQ-14, -18 | Vertragstest gegen den echten Erzeuger inkl. Negativ-Kontrolle; `report` nicht gelesen | unit | `pytest tests/test_paper_summary_contract.py -x` | ❌ Wave 0 |
| SC8 / REQ-24 | Sell/Underweight ohne Bestand → `long-only-noop`, nie Short; SELL ≤ Bestand | unit (+ Property über Ratings × Bestände) | `pytest tests/test_ibkr_decision.py -k long_only -x` | ❌ Wave 0 |
| REQ-13 | Parser = `TradingMemoryLog`; neuester Eintrag je Ticker; Rundlauf `store_decision` | unit | `pytest tests/test_ibkr_decision.py -k log_entries -x` | ❌ Wave 0 |
| REQ-22 / D-09 | jeder handelbare `CONTRACT_TABLE`-Eintrag hat `block_qty > 0`; keine Preisableitung | unit | `pytest tests/test_ibkr_contracts.py -k block_qty -x` | ❌ Wave 0 |
| REQ-61 | `[]`, `None`, Unset-Margin, fehlende Kommission → `preview-empty`, Exit 5 | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_preview.py -k "preview_empty" -x` | ❌ Wave 0 |
| REQ-37 Halt / D-16 | Fehler 154 am `whatIf` → `halted`, Exit 5 | unit | `pytest tests/test_ibkr_broker.py -k halted -x` | ❌ Wave 0 |
| REQ-69 | `tif="DAY"` auf der gesendeten Order, 10349 → `TIF_OVERRIDDEN`, wirksames `tif` protokolliert | unit | `pytest tests/test_ibkr_broker.py -k tif -x` | ❌ Wave 0 |
| REQ-70 / D-15 | `initMarginChange ≥ AvailableFunds` → `over-budget` (Exit 5); Währungsgleichheit; kein FX-Code | unit | `pytest tests/test_ibkr_preview.py -k budget -x` | ❌ Wave 0 |
| REQ-68 | Kein `reqMktData`/Ticker im Pfad: `FakeIB` wirft bei Marktdaten; AST-Wächter auf Executor/Broker | unit | `pytest tests/test_ibkr_isolation.py -k no_market_data -x` | ❌ Wave 0 |
| D-02/D-04 | fetch scheitert → `paper-log-unavailable`, kein Rückfall; SHA in Logzeile und JSON, nicht im Schlüssel | unit | `pytest tests/test_ibkr_paperlog.py -x` | ❌ Wave 0 |
| D-05 | Kalender vs `liquidHours` heute widersprüchlich → `calendar-conflict` | unit | `pytest tests/test_ibkr_decision.py tests/test_ibkr_contracts.py -k "calendar_conflict or session_day" -x` | ❌ Wave 0 |
| D-08 | Abends/Wochenende: `closed`-Marke, `whatIf` läuft | unit | `pytest tests/test_ibkr_preview.py -k closed_still_previews -x` | ❌ Wave 0 |
| Wächter | öffentliche Adaptermethoden = 7; Handbuch Exit 5 aktiv; Exit-Tabelle = 10 Konstanten; Uhrzeit-Literale leer; Adapter ohne `orderId=` | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ (anpassen) |
| „nichts gesendet" (G2) | über alle Pfade: `FakeIB.calls` hat nie `placeOrder`/`cancelOrder`; Leitungs-Stub sieht nur `whatIf=1` | unit | `pytest tests/test_ibkr_preview.py -k nothing_sent -x` | ❌ Wave 0 |
| D-14 / REQ-67 | Gateway-Messung Read-Only an + `whatIf` | manuell (Operator) | Sonde, Datum im Befund | HUMAN-UAT |

### Abtastrate
- **Pro Task-Commit:** der jeweilige `-k`-Befehl der Zeile oben
- **Pro Wellen-Merge:** Volllauf IBKR (oben) + `ruff check scripts tests`
- **Phasen-Gate:** gesamte Suite grün (`.venv/Scripts/python.exe -m pytest -q`) vor `/gsd:verify-work`

### Wave-0-Lücken
- [ ] `tests/test_ibkr_decision.py`, `tests/test_ibkr_paperlog.py`, `tests/test_ibkr_preview.py`, `tests/test_paper_summary_contract.py`
- [ ] `tests/ibkr_fakes.py`: `whatIfOrderAsync` mit steuerbarer Antwort (OrderState/`[]`/Fehler-Emission 154, 10349, 321 mit Hängen), `reqAllOpenOrdersAsync` (aus „forbidden" in steuerbar), `position(..., conId)`, Order-Fabrik für `IbHandles.order`, Account-Summary-Zeile `AvailableFunds`
- [ ] Fixture: eingefrorene Kopie von `decision-log.md` + `runs/2026-10-09/summary.json` aus Commit `71df89d`
- [ ] Kalender-Fixture (echter `XNYS`; Tests mit `pytest.importorskip("exchange_calendars")` nur, falls der Extra optional bleibt, sonst Pflicht-Install)
- [ ] Install: `.venv/Scripts/python.exe -m pip install -e ".[ibkr]"` nach Eintrag der Abhängigkeit

## Sicherheitsdomäne

### Anwendbare ASVS-Kategorien
| ASVS | Gilt | Standardkontrolle |
|------|------|-------------------|
| V2 Authentifizierung | nein (API ohne Login; Paper-Guard `managedAccounts == [DUQ634065]` besteht) | Paper-Guard aus Phase 2 unverändert |
| V3 Sitzung | nein | — |
| V4 Zugriffskontrolle | ja | Schreibsperre am Socket: Id 3 nur `whatIf`; 4/19/21/58 hart; `order.account` auf `EXPECTED_ACCOUNT` |
| V5 Eingabevalidierung | ja | Strikte Typprüfung `summary.json`; Dekodierung UTF-8 strict; `float`-Parsing mit Sentinel-Abweisung |
| V6 Kryptografie | nein | — |
| V10/V12 Dateien/Subprozess | ja | `subprocess` ohne Shell, Listenform; feste Argumente, `remote`/`branch` aus Settings validieren (kein führendes `-`, nur `[A-Za-z0-9._/-]`) |

### Bedrohungsmuster
| Muster | STRIDE | Mitigation |
|--------|--------|-----------|
| Unbeabsichtigte echte Order über `whatIf`-Öffnung | Tampering/EoP | Dreistufige Sperre (Aufruf, `send`, `sendMsg`), fail-closed bei unbekanntem Layout, Test mit echter `Client`-Klasse |
| Veralteter/manipulierter `paper-log`-Stand | Tampering | Fetch Pflicht, SHA im Protokoll, `verify` auf Kopie, Divergenzprüfung |
| Options-Injection über Settings (`remote`/`branch` mit `-`-Präfix) | Tampering | Whitelist-Validierung, `--` vor Pfadargumenten |
| Auth-Prompt/Hang blockiert Lauf | DoS | `GIT_TERMINAL_PROMPT=0`, Timeouts |
| Geheimnisse im Protokoll | Info Disclosure | Protokoll enthält Menge, Margin, SHA; keine Zugangsdaten (`IBKR_USERNAME/PASSWORD` werden nicht gelesen) |
| Pfad im Branch (`runs/<date>`) manipuliert | Tampering | `trade_date` aus Log strikt `YYYY-MM-DD` validieren, bevor ein Pfad gebaut wird; Ticker gegen `CONTRACT_TABLE` |

## Quellen

### Primär (HIGH)
- Lokale Quellen `ib_async` 2.1.0 (`ib.py:610,929-950,2204-2212,2263-2272`; `client.py:245-321,323-346,472-707`; `wrapper.py:670-727,1559-1690`; `order.py:308-325`; `decoder.py:1040-1100`) — Verhalten von `whatIf`, `reqAllOpenOrders`, Fehlerbehandlung, `OrderState`
- Repo: `scripts/ibkr_broker.py`, `ibkr_contracts.py`, `ibkr_executor.py`, `scripts/state_maintenance.py`, `scripts/daily_paper_run.py`, `tradingagents/memory/log.py`, `tradingagents/agents/rating.py`, `tests/ibkr_fakes.py`, `tests/test_ibkr_isolation.py`
- `.planning/ibkr-marktdaten-befund.md` §4, `.planning/ibkr-konto-befund.md` §Read-Only (Messungen 2026-10-11/12)
- Echter Branchstand `fork/paper-log` @ `71df89d` (fetch/show lokal ausgeführt)
- Lokaler Lauf `exchange_calendars` 4.13.2 mit pandas 3.0.6/Python 3.13 (`is_session`, `sessions_in_range`, `next_session`, `session_close`)
- [TWS API Message Codes](https://interactivebrokers.github.io/tws-api/message_codes.html) — 154 „Orders cannot be transmitted for a halted security."; 321 „Server error when validating an API client request."

### Sekundär (MEDIUM)
- PyPI-JSON `exchange-calendars` und pypistats (Alter, Downloads, Source-Repo)

### Tertiär (LOW)
- Keine; alle ungeklärten Punkte stehen im Annahmen-Log.

## Metadaten

**Konfidenzaufschlüsselung:**
- Standard Stack: HIGH, Bibliotheksquellen und Kalender lokal geprüft
- Architektur (Sperre, Aktualität, Zielrechnung): HIGH aus Quelltext; Gateway-Details (A1–A4) MEDIUM/LOW
- Fallstricke: HIGH, jeweils an Quelltext oder Echtdaten belegt

**Recherchedatum:** 2026-10-12
**Gültig bis:** 2026-11-12 (Gateway 10.50.1 läuft am 2026-12-15 aus; `ib_async` ist exakt gepinnt)

## Project Constraints (from CLAUDE.md)
- Projekt-CLAUDE.md: Graphify und Serena sind reine Navigations-/Analysewerkzeuge, kein Build- oder Merge-Gate; nichts davon in Pläne als Gate aufnehmen.
- Globale Vorgaben: Chat auf Deutsch, `.planning/` deutsch, Code/Commits/CHANGELOG englisch.
- Umgebung: Tests und Lint nur über `.venv/Scripts/python.exe -m pytest|ruff` (uv run scheitert an SSL); nichts pushen (Publish nur via `fork`, `origin` ist pull-only); parallel arbeitender Operator: vor Edits neu lesen, nie überschreiben.
- Phase-3-Wächter bleiben bindend: keine Uhrzeit-Literale (`13:30`, `14:30`, `09:30`, `16:00`) in `scripts/ibkr_*.py`; Fachmodul ohne eigene Uhr; Bibliothek nur im Adapter; Handbuch nennt `ib_async` nicht.
