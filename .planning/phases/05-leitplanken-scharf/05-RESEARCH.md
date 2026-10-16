# Phase 5: Leitplanken scharf - Research

**Researched:** 2026-10-16
**Domain:** Fail-closed Ausführungs-Leitplanken (Freigabe/Kill-Datei, Größenlimit, Sitzungsfenster, Write-Ahead-Ledger, Startup-Reconciliation, Lauf-Lock) um einen IBKR-Adapter (`ib_async` 2.1.0), ohne dass eine Order gesendet wird
**Confidence:** HIGH für alles, was am Repo und an der installierten `ib_async`-Quelle belegt ist; MEDIUM für Gateway-Verhalten, das noch nie gemessen wurde (siehe Annahmen A1-A7)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Die Freigabe ist eine **Datei mit Ablaufdatum**, nicht eine Env-Variable: `%LOCALAPPDATA%\TradingEngineX\ibkr\RELEASE` nennt ein „gültig bis"-Datum. Fehlt die Datei, ist sie unlesbar, nicht parsebar oder abgelaufen → Exit 4, kein Platzierungsaufruf. Grund: Phase 8 läuft unbeaufsichtigt, eine tägliche Freigabe würde sie sabotieren; eine ewige Freigabe wird vergessen. Eine Freigabe wird Wochen im Voraus gesetzt. **REQ-IBKR-33** spricht von einer „Freigabe-Variable" und wird beim Planen auf „Freigabe-Datei" umformuliert; REQ-IBKR-64 („Freigabe vorhanden und lesbar", Test mit unlesbarer Freigabedatei) passt bereits wörtlich.
- **D-02:** Die Freigabe **nennt das Konto**, für das sie gilt (`DUQ634065`). Weicht das verbundene Konto ab → Exit 4. Das ist eine zweite Quelle für „richtiges Konto" im Sinne von REQ-63, neben dem Paper-Guard (Exit 8) beim Verbinden.
- **D-03:** Die Kill-Datei liegt im selben State-Ordner: `%LOCALAPPDATA%\TradingEngineX\ibkr\KILL`. Nur die **Existenz** zählt, der Inhalt ist egal. Ist der Ordner nicht prüfbar, gilt das als aktiv (Exit 4, REQ-33 „Zustand nicht lesbar"). Das Handbuch nennt den Einzeiler zum Anlegen.
- **D-04:** Freigabe und Kill-Datei werden **unmittelbar vor jeder einzelnen Order** neu geprüft (REQ-34), und jeder Lauf protokolliert den Zustand beider Schalter im Ledger, auch wenn sie inaktiv sind (REQ-36).
- **D-05:** `reqGlobalCancel` (Nachricht 58) bleibt in der Socket-Sperre gesperrt. **Nur im Kill-Pfad** — nachdem der Ausführer einen aktiven Kill-Switch festgestellt hat — öffnet der Adapter für **genau einen** protokollierten Aufruf, danach ist die Sperre wieder zu. Kein anderer Code-Pfad kann stornieren. Die Negativ-Kontrolle (REQ-66) belegt, dass 58 außerhalb des Kill-Pfads weiter scheitert.
- **D-06:** Der echte SC3-Nachweis läuft so: Der **Operator legt in TWS Paper eine kleine `DAY`-Limit-Order weit vom Markt an**, legt `KILL` an, der Lauf startet; belegt wird Exit 4, die Order ist storniert, der Schalterzustand steht im Ledger. Phase 5 selbst sendet dabei nie eine Order. Eine `DAY`-Order bleibt auch außerhalb der Handelszeit offen, der Test braucht keine offene Börse.
- **D-07:** Ein **neues Subkommando `execute`** fährt die volle Kette: Lock → Startup-Reconciliation → je Ticker Freigabe-/Kill-Prüfung, Größengrenze, Sitzungsfenster, `intent` schreiben → statt `placeOrder` ein **Trocken-Abschluss**. In Phase 5 ist `execute` **zwangsweise trocken**; Phase 6 nimmt nur diesen Zwang heraus. `preview` bleibt unverändert der reine `whatIf`-Trockenlauf aus Phase 4.
- **D-08:** Trockenläufe schreiben in eine **eigene Datei `ledger-dryrun.jsonl`**, über denselben Code-Pfad wie der echte Ledger `ledger.jsonl`. Der echte Ledger bleibt bis Phase 6 leer; die Startup-Reconciliation sieht nie einen Trocken-`intent` (der sonst unauflösbar wäre und jeden Lauf mit Exit 6 beenden würde). Ein Markierungsfehler kann einen Trockenlauf nicht zu einem echten machen. Beide Dateien liegen im State-Ordner außerhalb jedes Git-Baums (REQ-46).
- **D-09:** `MAX_QTY_PER_ORDER = 2` als **Code-Konstante** (jede Änderung ist ein Commit, wie `block_qty` in D-09 aus Phase 4). 2 ist genau die größte Order, die D-10 aus Phase 4 heute erzeugen kann (`Buy` = 2 Blöcke à 1 Stück); jeder Tabellen- oder Rechenfehler darüber wird **abgelehnt und gemeldet, nicht gekürzt** (REQ-32). Wer `block_qty` erhöht, muss die Grenze bewusst mitziehen — ein Test soll das sichtbar machen.
- **D-10:** Das Sitzungsfenster für Markt-Orders übernimmt den **Phase-3-Puffer**: Beginn der regulären Sitzung +15 min bis Ende −15 min, über dieselbe Konstante `SESSION_BUFFER_MINUTES` und `evaluate_session` aus `scripts/ibkr_contracts.py`. Ein Halbtag verkürzt das Fenster automatisch. Außerhalb → `skipped` mit Grund `outside_session` (REQ-42).
- **D-11:** Quellen-Widerspruch (REQ-63): Widerspricht sich das **Konto**, stoppt der **ganze Lauf**. Widersprüche zu **Position**, „**schon ausgeführt?**" oder **Handelbarkeit** stoppen **nur diesen Ticker** (`skipped` mit Grund, gemeldet), die übrigen Ticker laufen weiter. Es gilt immer der vorsichtigere Wert.

### Claude's Discretion

- Dateiformat von `RELEASE` (z. B. zwei Zeilen `account=` / `valid_until=` oder kleines JSON) — solange Konto und Datum maschinell und streng geparst werden und jeder Parse-Fehler fail-closed endet.
- Exaktes Ledger-Schema (Feldnamen), solange REQ-41/-42 erfüllt sind: Zustand, `decision_key`, `paper-log`-SHA als Provenienz, `skipped`-Grund, Zeitstempel, Schalterzustand.
- Benannte Zustände und Logzeilen im Stil der bestehenden `ibkr-state=<LABEL>`-Zeilen; Zuordnung zu den reservierten Exit-Codes 4/6/7.
- Ob die `execute`-Kette Bausteine aus `run_preview` wiederverwendet oder herauslöst.

### Deferred Ideas (OUT OF SCOPE)

- Kurs-Stream und Marktdaten-Modul (`scripts/ibkr_market_data.py`, laufende Arbeit des Operators): außerhalb des Order-Pfads (REQ-IBKR-26), nicht Teil von Phase 5. Offene Frage dort: Soll 2103 (Marktdaten-Farm kaputt) einen Stream beenden, obwohl er im Lesefenster als harmlos gilt?
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-IBKR-32 | `abs(order_qty) <= MAX_QTY_PER_ORDER`, ablehnen statt kürzen | `guards.check_size`, Konstante = 2, Sentinel-Test `max(BLOCKS) * max(block_qty)`; Exit 5; zweite Prüfung an der Placer-Grenze (Abschnitt Muster 5) |
| REQ-IBKR-33 | Fail-closed: Freigabe **und** keine Kill-Datei, sonst Exit 4 | `read_release`/`read_kill` mit `os.stat` statt `Path.exists`; Format JSON; Text von REQ-33 wird „Freigabe-Datei" (Muster 1) |
| REQ-IBKR-34 | Prüfung unmittelbar vor jeder einzelnen Order | `switches.check()` im Lauf-Preflight **und** erneut direkt vor `intent`/Placer; Test mit Placer, der `KILL` nach Order 1 anlegt (Muster 2) |
| REQ-IBKR-35 | Aktiver Kill → `reqGlobalCancel`, Exit 4 | Einmal-Permit im Adapter (`cancel_all`), Kill-Beleg als Argument, Nachlese per `open_orders()`; Operator-Checkpoint SC3 (Muster 3) |
| REQ-IBKR-36 | Schalterzustand jedes Laufs im Ledger | `run_start`-Ereignis mit beiden Schalterzuständen vor jeder Entscheidung, auch bei Exit 4 |
| REQ-IBKR-39 | `decision_key = "<trade_date>\|<ticker>"`, kein SHA | `guards.decision_key`; Zeichen `\|` am Gateway **nicht gemessen** (A3) |
| REQ-IBKR-40 | Ein Versuch pro Schlüssel, erste Fassung gewinnt | Versuch = Schlüssel hat `intent` erreicht; `skipped` verbraucht ihn nicht; zweite Fassung → `decision_changed` (Muster 4) |
| REQ-IBKR-41 | `orderRef` = Schlüssel, `paper-log`-SHA als Provenienz | `preview_order(order_ref=...)` + Echo-Rücklesung; `FakeOrder` braucht Feld `orderRef` |
| REQ-IBKR-42 | Write-Ahead-Zustände, `skipped` mit Grund | Ereignisse append-only, Zustand = letztes Ereignis je Schlüssel; Grund-Tabelle (Abschnitt Ledger) |
| REQ-IBKR-43 | Reconciliation über alle drei Quellen, Exit 6 | `order_history()` im Adapter, reine Funktion `resolve_entry`; Fenstersemantik offen (A4) |
| REQ-IBKR-44 | `locked(<ledger>, wait=False)`, `OSError` = nicht ausführen (Exit 7) | `ExitStack`-Muster; unter Windows geprüft: zweiter Versuch im selben Prozess liefert `False`, fehlendes Verzeichnis wirft `FileNotFoundError` |
| REQ-IBKR-46 | JSONL, außerhalb Git, kein Sidecar im Baum | State-Ordner + Laufzeitprüfung „nicht in einem Git-Arbeitsbaum"; `git status` vorher/nachher vergleichen (Operator-WIP macht „leer" unmöglich) |
| REQ-IBKR-63 | Zwei Quellen je sicherheitskritischem Fakt | vier Vergleichsfunktionen; Position und Handelbarkeit haben in Phase 5 nur eine schwache zweite Quelle (offene Fragen 2 und 3) |
| REQ-IBKR-64 | Freigabe „vorhanden und lesbar", Test mit unlesbarer Datei | Parser-Matrix aus Muster 1 inkl. BOM, UTF-16, Verzeichnis statt Datei, Berechtigungsfehler |
| REQ-IBKR-66 | Negativ-Kontrolle je Schutzmaßnahme | Tabelle „Schutz → Negativ-Kontrolle" im Abschnitt Validation Architecture |
| REQ-IBKR-25 (Teil Sitzungsfenster) | Fenster der regulären Sitzung, nicht Auktion/Schlussminuten | schon implementiert in `evaluate_session` (+15/−15); Phase 5 verdrahtet `CLOSED` → `skipped outside_session` **vor** `whatIf` und testet Halbtag/Fenstergrenzen auf Ausführungsebene |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Projekt-`CLAUDE.md`: Graphify (Architektur-Navigation, kein Build-/Merge-Gate) und Serena (symbolgenaue Navigation) sind reine Navigationswerkzeuge. Sie liefern keine Anforderungen an den Code; Phase 5 darf sie zum Lesen nutzen, braucht sie aber nicht.
- Globale `CLAUDE.md`: `/graphify` ruft den Skill auf. Keine weitere Vorgabe.
- Aus dem Memory des Operators (gilt für Plan und Ausführung): Chat deutsch, Code/Commits/CHANGELOG englisch, `.planning/` deutsch. Werkzeuge nur über `.venv/Scripts/python.exe -m pytest|ruff` (uv/make gehen hier nicht). Der Operator committet parallel in dasselbe Repo: bei „file modified since read" neu lesen und angleichen, nie überschreiben. Agent-Selbstaussagen („lint PASSED") immer selbst nachfahren.
- Projektkonvention aus Phase 2-4: RED zuerst, Negativ-Kontrolle zu jeder Sicherung, Tests nie gegen das echte Gateway außer in ausdrücklichen Operator-Checkpoints, Sockets in `tests/conftest.py` gesperrt.

## Summary

Phase 5 braucht **keine neue Abhängigkeit**. Alles besteht aus Standardbibliothek (`os`, `json`, `pathlib`, `contextlib`), dem vorhandenen `tradingagents.dataflows.files.locked` und `ib_async` 2.1.0, das schon installiert ist. Die Arbeit teilt sich in vier Teile: (1) zwei kleine reine Module, `scripts/ibkr_guards.py` (Schalter, Größe, Schlüssel, Quellenvergleich) und `scripts/ibkr_ledger.py` (append-only JSONL, Zustand je Schlüssel, Reconciliation als reine Funktion), im Stil von `ibkr_decision.py` (bibliotheksfrei, Uhr als Parameter); (2) drei schmale Erweiterungen des Adapters (`order_history`, `cancel_all` mit Einmal-Permit, `preview_order(order_ref=...)` samt Rücklesung, `open_orders` ohne `conId`-Filter), wobei die Grenze von zehn öffentlichen Methoden nur hält, wenn Completed-Orders und Executions in **einer** Methode stecken; (3) das Subkommando `execute` im Executor, das genau eine Kette in der Reihenfolge aus REQ-IBKR-45 fährt und in Phase 5 zwangsweise einen Trocken-Abschluss statt `placeOrder` ruft; (4) Handbuch, Wächter-Tests und Operator-Checkpoints.

Die größten Risiken sind nicht technisch, sondern Fehlbeschreibungen, die still fail-open werden: `Path.exists()`/`os.path.exists` schlucken Berechtigungsfehler je nach Version, ein PowerShell-`echo > RELEASE` schreibt UTF-16 oder BOM, ein `except OSError` um den ganzen `with locked(...)`-Block fängt auch Fehler des Laufs und macht sie zu Exit 7, ein abgebrochener Append lässt eine Zeile ohne Zeilenumbruch zurück, an die der nächste Append anhängt, und `reqGlobalCancel` ist Fire-and-forget, also muss der Erfolg durch erneutes Lesen der offenen Orders bewiesen werden, nicht durch das Senden. Dazu kommen drei **ungemessene Gateway-Fakten** (A1-A3: Verhalten von 58, Zeichen `|` in `orderRef`, Rohform von `reqCompletedOrders`/`reqExecutions` mit echtem Inhalt), die REQ-IBKR-67 vor dem Bauen verlangt. Alle drei lassen sich im ohnehin geplanten Operator-Checkpoint (SC3) mit abdecken; das ist ein Vorschlag, keine Entscheidung (siehe Offene Fragen).

**Primary recommendation:** Zwei reine Module plus drei Adapter-Methoden bauen, `execute` als **eine** Kettenfunktion in der Reihenfolge von REQ-IBKR-45 (mit einem Placer-Parameter, dessen einziger CLI-Wert der Trocken-Placer ist), Ledger je Modus als eigene Datei über denselben Code, und die Operator-Messungen (Kill-Storno, `|` in `orderRef`, Rohform der Completed-Orders nach dem Storno) in **einen** Checkpoint legen, der vor dem Verifizieren von G3 liegt.

## Architectural Responsibility Map

Die Tier-Tabelle des Templates (Browser/SSR/CDN) passt nicht; hier sind es die Schichten dieses Projekts.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Freigabe-/Kill-Datei lesen, Größenlimit, Schlüsselbau, Quellenvergleich | Reine Logik (`scripts/ibkr_guards.py`) | — | Bibliotheksfrei, Uhr injiziert, ohne Gateway testbar (G3) |
| Ledger schreiben/lesen, Zustand je Schlüssel, Reconciliation-Klassifikation | Reine Logik (`scripts/ibkr_ledger.py`) | Executor (Datei-I/O, fsync) | Reconciliation als Funktion über drei Listen, damit Tests keine Fakes brauchen |
| Lauf-Lock | Executor (`tradingagents.dataflows.files.locked`) | — | Vorhandene, prozessübergreifende Sperre, nicht neu bauen |
| Kette in fester Reihenfolge, Exit-Codes, Kill-Pfad-Entscheidung | Executor (`run_execute`) | — | Genau eine Stelle (REQ-45); Entscheidung „Kill aktiv" fällt hier, nie im Adapter |
| `reqCompletedOrders`/`reqExecutions`/alle offenen Orders lesen | Adapter (`ibkr_broker.py`) | — | Einziger `ib_async`-Importort (REQ-07), Lesefenster fail-closed über `_read` |
| `reqGlobalCancel` durchlassen | Adapter (Einmal-Permit im Schreibschutz) | Executor (liefert den Kill-Beleg) | Die Sperre sitzt im Adapter; nur eine Stelle öffnet sie, nur einmal |
| Sitzungsfenster | `ibkr_contracts.evaluate_session` (vorhanden) | Executor (verdrahtet `CLOSED` → `outside_session`) | Puffer und Halbtag stecken schon in der Phase-3-Logik |
| Zustandsablage | Dateisystem außerhalb Git (`%LOCALAPPDATA%\TradingEngineX\ibkr`) | — | Kein Sidecar im Arbeitsbaum, kein SQLite (REQ-46) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python-Standardbibliothek (`os`, `json`, `pathlib`, `contextlib`, `dataclasses`, `re`, `datetime`) | Python 3.13.13 (`.venv`) [VERIFIED: `.venv/Scripts/python.exe --version`] | Schalterdateien, JSONL-Ledger, Zustände, Kette | Keine neue Abhängigkeit; entspricht dem Stil von `ibkr_decision.py`/`ibkr_contracts.py` |
| `tradingagents.dataflows.files.locked` | im Repo | Lauf-Lock `wait=False` (REQ-44) | Vorhanden, unter Windows (`msvcrt.locking`) und POSIX (`flock`) implementiert [VERIFIED: `tradingagents/dataflows/files.py`] |
| `ib_async` | 2.1.0 exakt gepinnt [VERIFIED: `.venv` Import, `pyproject.toml`] | `reqAllOpenOrdersAsync`, `reqCompletedOrdersAsync`, `reqExecutionsAsync`, `reqGlobalCancel` | Bestehender Adapter; die vier Aufrufe existieren in 2.1.0 (`ib.py:857, :2268, :2273, :2278`) [VERIFIED: Quelle der installierten Bibliothek] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `exchange_calendars` | 4.13.2 [VERIFIED: `.venv`] | XNYS-Kalender für die Aktualität (`ibkr_decision.freshness`) | Unverändert, von `execute` über `_local_chain` mitgenutzt |
| `pytest` 9.x, `ruff` 0.17.0 | im `.venv` [VERIFIED] | Tests, Lint | Wie Phase 4; CI installiert `.[ci]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON für `RELEASE` | zwei Zeilen `key=value` | Beides streng parsbar. JSON liefert Typprüfung und „genau diese Schlüssel" fast gratis, hat aber keine Kommentare. Empfehlung JSON; der Parser ist ohnehin für BOM zu härten (Pitfall 2) |
| Eine Methode `order_history()` | zwei Methoden `completed_orders()` und `executions()` | Zwei Methoden sprengen mit `cancel_all` die Grenze von zehn, sobald Phase 6 `place` ergänzt (siehe Muster 6). Eine Methode mit einem Ergebnisobjekt hält Platz für `place` |
| JSONL mit Ereignissen | JSONL mit „Zustand fortschreiben" (Zeile ändern) | Ändern widerspricht append-only und zerstört die Spur. Ereignisse anhängen, Zustand = letztes Ereignis je Schlüssel |

**Installation:** keine. `pip install` ist in Phase 5 **nicht** nötig.

**Version verification:** `ib_async 2.1.0` und `exchange_calendars 4.13.2` stammen aus dem `.venv` dieses Rechners; es wird nichts Neues installiert, deshalb entfällt `npm view`/`pip index versions`.

## Package Legitimacy Audit

Diese Phase installiert **kein** externes Paket. Es gibt nichts zu prüfen und nichts für `slopcheck`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| — | — | — | — | — | — | Kein neues Paket |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Der Planer braucht deshalb **kein** `checkpoint:human-verify` für eine Installation. (Die Operator-Checkpoints aus Abschnitt „Operator-Checkpoints" betreffen das Gateway, nicht Pakete.)

## Architecture Patterns

### System Architecture Diagram

```
  CLI: ibkr_executor.py execute TICKER...
        │
        ▼
  [Settings .env] ──► ConfigError ─────────────► Exit 1 / 20
        │
        ▼
  [State-Ordner prüfen: nicht in Git-Baum, mkdir] ──► Exit 1 (in Git-Baum)
        │
        ▼
  [LOCK  locked(ledger.jsonl, wait=False)] ── nicht erhalten / OSError ──► Exit 7 (kein Ledger-Eintrag, keine Order)
        │ gehalten
        ▼
  [Ledger öffnen + lesen (Modus dry → ledger-dryrun.jsonl)] ── defekt/unschreibbar ──► Exit 6
        │
        ▼
  [Schalter lesen: RELEASE + KILL]  ──► run_start-Ereignis mit beiden Zuständen (REQ-36), immer
        │
        ├── KILL positiv vorhanden ──► [verbinden → cancel_all (1×) → open_orders prüfen] ──► Exit 4
        ├── RELEASE fehlt/unlesbar/ungültig/abgelaufen/falsches Konto ──► Exit 4 (kein Storno)
        ▼
  [Reconciliation: unaufgelöste intent/placed?] ── ja ──► [verbinden, order_history: offene + erledigte + Executions]
        │                                                      ├── aufgelöst ──► Ereignisse schreiben, weiter
        │                                                      └── unauflösbar ──► Exit 6, keine neue Order
        ▼
  [paper-log lesen, Vorbedingungen, Aktualität]  (_local_chain, unverändert)
        │
        ▼  je Ticker, der überlebt:
  [Auflösung + Handelbarkeit] → [Kalenderabgleich] → [Position/offene Orders] → [Zielrechnung plan_order]
        │
        ▼
  [Größe: abs(qty) <= MAX_QTY_PER_ORDER] ── zu groß ──► skipped size_cap (Exit 5)
        │
        ▼
  [Sitzungsfenster: result.state == CLOSED] ── ja ──► skipped outside_session (Exit 2)
        │
        ▼
  [Schalter erneut lesen] ── Kill ──► skipped kill_switch, Rest-Ticker skipped, cancel_all, Exit 4
        │
        ▼
  [Quellenvergleiche REQ-63 (Position, schon ausgeführt?, Handelbarkeit)] ── Widerspruch ──► skipped source_conflict
        │
        ▼
  [whatIf mit orderRef = decision_key] ── Urteil nicht OK ──► rejected (Exit 5)
        │
        ▼
  [Schlüssel schon versucht? / Fassung geändert?] ── ja ──► skipped already_attempted / decision_changed
        │
        ▼
  [Schalter ein drittes Mal, unmittelbar davor] ── Kill ──► wie oben
        │
        ▼
  [Ledger: intent  (flush + fsync)]  ◄── Write-Ahead
        │
        ▼
  [Placer.complete(intent)]  Phase 5: DryPlacer → Ledger: dry_complete (kein Broker-Aufruf)
                              Phase 6: RealPlacer → placeOrder → placed/filled
        │
        ▼
  [run_end-Ereignis mit Exit-Code] → Exit = Maximum der Rangfolge (4/6/7 vor 1 > 5 > 2 > 0)
```

Hinweis zur Reihenfolge: REQ-IBKR-45 (Phase 6) legt die Kette als `Lock → Reconciliation → Quellen/Integrität → Aktualität → Auflösung/Handelbarkeit → Menge → Größe → Handelszeit → Kill-Switch → whatIf → intent → platzieren` fest. Das Diagramm hält sie ein und ergänzt nur zwei billige Wiederholungen der Schalterprüfung (Lauf-Preflight und unmittelbar vor `intent`). Das Preflight-Lesen der Schalter steht **vor** der Reconciliation, damit ein aktiver Kill nicht von einem Exit 6 überdeckt wird; der Phase-6-Reihenfolgetest muss das erwarten (siehe Offene Frage 1).

### Recommended Project Structure

```
scripts/
├── ibkr_guards.py       # NEU, rein: Schalter, Größe, decision_key, Quellenvergleiche, benannte Zustände
├── ibkr_ledger.py       # NEU, rein: Ledger-Klasse (JSONL), Zustand je Schlüssel, resolve_entry, Gründe
├── ibkr_broker.py       # ERWEITERT: order_history, cancel_all (+Permit), open_orders(con_id=None), preview_order(order_ref)
├── ibkr_executor.py     # ERWEITERT: Subkommando execute, run_execute, DryPlacer, State-Pfade
├── ibkr_decision.py     # unverändert (neue Zustände gehören in guards/ledger, nicht in EXIT_BY_STATE)
└── IBKR_EXECUTION.md    # ERWEITERT: RELEASE/KILL mit Einzeilern, execute, Ledger, Exit 4/6/7 aktiv
tests/
├── test_ibkr_guards.py  # NEU
├── test_ibkr_ledger.py  # NEU
├── test_ibkr_execute.py # NEU: Kette gegen FakeIB, SC1-SC8, G3-Tests
├── ibkr_fakes.py        # ERWEITERT: FakeOrder.orderRef, completed/executions/globalCancel
├── test_ibkr_broker.py  # ERGÄNZT: cancel_all-Permit (echte Client-Klasse), order_history, order_ref
└── test_ibkr_isolation.py  # ANGEPASST: öffentliche Methoden, Handbuch-Tests, Einzelstelle cancel_all
```

Neue Zustände gehören **nicht** in `ibkr_decision.EXIT_BY_STATE`: `test_handbook_state_table_matches_decision_module` verlangt für jeden dortigen Zustand eine Handbuchzeile, und das Modul beschreibt Entscheidungs-Zustände von Phase 4. Eigene Tabellen in `guards`/`ledger` mit eigenem Handbuch-Test halten die Schichten sauber.

### Pattern 1: Schalter lesen, fail-closed, ohne `exists()`

**What:** `KILL` und `RELEASE` werden mit `os.stat` bzw. `read_bytes` gelesen und jede Abweichung vom Erwarteten ist ein benannter Zustand.
**When to use:** am Lauf-Preflight und unmittelbar vor jeder Order.
**Warum nicht `Path.exists()`:** `os.path.exists` gibt laut Doku `False` zurück, wenn `os.stat()` an Berechtigungen scheitert; „kein Kill-Datei" wäre dann fail-open [CITED: docs.python.org/3/library/os.path.html#os.path.exists]. `Path.exists()` unter 3.13.13 wirft stattdessen bei allem außer ENOENT/ENOTDIR/EBADF/ELOOP und einigen Windows-Fehlern [VERIFIED: `inspect.getsource(pathlib.Path.exists)` im `.venv`]; das Verhalten hängt also von der Python-Version ab. Eine eigene Funktion mit `os.stat` ist versionsunabhängig.

```python
# Source: eigener Entwurf, geprüft gegen docs.python.org/3/library/os.path.html
import json, os, re
from dataclasses import dataclass
from datetime import date

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELEASE_KEYS = frozenset({"account", "valid_until"})
MAX_RELEASE_BYTES = 4096


@dataclass(frozen=True)
class KillState:
    state: str   # "absent" | "active" | "unreadable"
    detail: str = ""


def read_kill(state_dir: str) -> KillState:
    try:
        os.stat(os.path.join(state_dir, "KILL"))
    except FileNotFoundError:
        return KillState("absent")          # Ordner fehlt auch hierher: RELEASE fehlt dann ebenfalls
    except OSError as exc:                   # PermissionError, NotADirectoryError, ...
        return KillState("unreadable", type(exc).__name__)
    return KillState("active")               # Datei ODER Verzeichnis: nur die Existenz zählt (D-03)


@dataclass(frozen=True)
class ReleaseState:
    state: str   # "ok" | "missing" | "unreadable" | "invalid" | "expired" | "account_mismatch"
    detail: str = ""
    valid_until: date | None = None


def read_release(path, *, today_utc: date, expected_account: str) -> ReleaseState:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_RELEASE_BYTES + 1)
    except FileNotFoundError:
        return ReleaseState("missing")
    except OSError as exc:                   # auch IsADirectoryError, PermissionError
        return ReleaseState("unreadable", type(exc).__name__)
    if len(raw) > MAX_RELEASE_BYTES:
        return ReleaseState("invalid", "file too large")
    try:
        data = json.loads(raw.decode("utf-8-sig"))     # BOM tolerieren, UTF-16 nicht
    except (UnicodeDecodeError, ValueError):
        return ReleaseState("invalid", "not UTF-8 JSON")
    if not isinstance(data, dict) or set(data) != RELEASE_KEYS:
        return ReleaseState("invalid", f"keys must be exactly {sorted(RELEASE_KEYS)}")
    account, until = data["account"], data["valid_until"]
    if not isinstance(account, str) or not isinstance(until, str) or not _DATE_RE.match(until):
        return ReleaseState("invalid", "account/valid_until have the wrong type or shape")
    try:
        valid_until = date.fromisoformat(until)        # Regex vorher: fromisoformat nimmt ab 3.11 auch "20261031"
    except ValueError:
        return ReleaseState("invalid", "valid_until is not a calendar date")
    if account != expected_account:
        return ReleaseState("account_mismatch", f"release names {account!r}", valid_until)
    if today_utc > valid_until:
        return ReleaseState("expired", f"valid until {valid_until}", valid_until)
    return ReleaseState("ok", "", valid_until)
```

Empfohlene Regel für `valid_until`: ISO-Datum `YYYY-MM-DD`, gültig **einschließlich** dieses Kalendertags in **UTC**; `today_utc` kommt aus der injizierten Uhr. Die Ausführung läuft in der US-Sitzung (17-21 Uhr UTC), der letzte Gültigkeitstag deckt sie also noch ab. Das ist eine Empfehlung im Rahmen des Ermessens von D-01, kein Beschluss. Ob zusätzlich eine Obergrenze für die Laufzeit gilt (z. B. nicht weiter als 90 Tage in der Zukunft), ist offen und optional (Offene Frage 6).

### Pattern 2: Schalter vor jeder einzelnen Order, Placer als Naht

**What:** Die Kette ruft `switches.check()` an drei Stellen (Preflight, Kill-Position nach REQ-45, unmittelbar vor `intent`). Der Abschluss einer Order ist ein austauschbarer **Placer**; Tests geben einen, der nach der ersten Order `KILL` anlegt.
**Warum der Placer-Parameter:** SC2 verlangt zwei Orders in einem Lauf und eine Aktivierung dazwischen. Ohne Naht ist das nur mit Monkeypatching der Datei zwischen zwei Fake-Aufrufen lösbar. Mit `main(..., placer=...)` bleibt der CLI-Weg zwangsweise trocken (kein CLI-Schalter), und Phase 6 ersetzt nur den Standardwert.

```python
# Source: eigener Entwurf
class DryPlacer:
    """Phase 5: keine Order; schreibt nur den Abschluss. Phase 6 ersetzt dies, sonst nichts."""
    dry = True

    def complete(self, ctx, intent):            # intent: Ledger-Eintrag, orderRef steht schon darin
        ctx.ledger.append(event="dry_complete", decision_key=intent["decision_key"])
        return "dry_complete"
```

Test für SC2 (Skizze): zwei Ticker mit `Buy`; ein Test-Placer legt in `complete()` die Datei `KILL` an; erwartet wird: Ledger enthält `intent`+Abschluss für Ticker 1, für Ticker 2 `skipped kill_switch` ohne `intent`, Exit 4, `cancel_all` genau einmal, `FakeIB.calls` ohne `placeOrder`.

### Pattern 3: `reqGlobalCancel` als Einmal-Permit im Adapter

**What:** `_arm_write_barrier` bekommt ein veränderliches Permit-Objekt. Nachricht 58 und der benannte Aufruf `reqGlobalCancel` sind **nur** durchlässig, solange das Permit offen ist; sobald die Nachricht 58 auf dem Draht (`sendMsg`) durchging, schließt es und zählt hoch. `cancel_all` öffnet es, ruft `ib.reqGlobalCancel()` und schließt es im `finally`.
**Wichtig:** Der benannte Aufruf, die Feldebene (`send`) und die Drahtebene (`sendMsg`) prüfen **dasselbe** Permit; gezählt wird nur auf der Drahtebene, damit ein Aufruf nicht dreimal verbraucht wird.

```python
# Source: eigener Entwurf auf Basis von scripts/ibkr_broker.py:435-500 und ib_async 2.1.0 ib.py:857, client.py:980
class _CancelPermit:
    def __init__(self):
        self.open = False
        self.sent = 0                       # Nachrichten 58, die den Draht erreicht haben


# in _arm_write_barrier(client, permit):
def guarded_global_cancel(*args, **kwargs):
    if not permit.open:
        raise ReadOnlyViolation("read-only session: reqGlobalCancel refused before it reached the gateway")
    return original_global_cancel(*args, **kwargs)      # original = vor dem Ersetzen gesicherter Client-Aufruf

# guarded_send / guarded_send_msg: für msg_id == 58
#   if not permit.open: refuse_message(58)
# guarded_send_msg zusätzlich, nachdem 58 passiert ist:  permit.open = False; permit.sent += 1


# in IbkrBroker:
def cancel_all(self, *, kill_evidence) -> None:
    if not getattr(kill_evidence, "active", False):
        raise ReadOnlyViolation("global cancel needs a positively detected kill switch")
    if self._permit.sent:
        raise ReadOnlyViolation("global cancel already used in this session")
    self._permit.open = True
    try:
        self._ib.reqGlobalCancel()
    finally:
        self._permit.open = False
    if self._permit.sent != 1:
        raise GatewayUnavailable(REQUEST_FAILED, None, "global cancel did not reach the wire exactly once")
    self._log.warning('ibkr-state=GLOBAL_CANCEL_SENT code=- detail="count=1 reason=kill_switch"')
```

`reqGlobalCancel` hat keine Antwortnachricht. Der Erfolg ist nur durch ein erneutes Lesen **aller** offenen Orders (`open_orders(None)`) mit kurzer Wiederholung (z. B. bis 10 s, im Takt von 0,5 s) belegbar; der Executor protokolliert `remaining=<n>` und endet in jedem Fall mit Exit 4. Ob das Gateway-Schalterverhalten „Read-Only API" 58 blockt, ist nicht gemessen (A1): bei eingeschaltetem Schalter wäre das Senden still wirkungslos, deshalb zählt nur die Nachlese.

**Kill-Beleg:** `cancel_all(kill_evidence=...)` verlangt ein Objekt mit `active is True`, das nur `read_kill` bei positiv vorhandener Datei liefert. Ein Aufruf ohne Beleg scheitert im Adapter. Das macht „nur im Kill-Pfad" zusätzlich auf API-Ebene prüfbar. Ein AST-Test stellt sicher, dass `cancel_all(` im Executor an genau **einer** Stelle steht.

### Pattern 4: Ledger append-only, Zustand = letztes Ereignis je Schlüssel

**Schema-Vorschlag** (Ermessen, minimal für REQ-41/-42): eine JSON-Zeile je Ereignis.

```json
{"v":1,"seq":7,"ts":"2026-10-16T17:21:03+00:00","run_id":"<uuid4>","mode":"dryrun",
 "event":"intent","decision_key":"2026-10-09|AAPL","ticker":"AAPL","rating":"Buy",
 "paper_log_sha":"<40 hex>","side":"BUY","quantity":2,"con_id":265598,"weekend_gap":false,
 "order_ref":"2026-10-09|AAPL"}
```

Ereignisarten: `run_start` (beide Schalterzustände, `paper_log_sha`, Modus), `switch_check` (nur wenn der Zustand sich ändert oder vor einer Order), `reconcile` (Ergebnis je Eintrag), `intent`, `dry_complete`, `placed`/`filled`/`partial`/`rejected` (ab Phase 6), `skipped` (mit `reason`), `kill_cancel`, `run_end` (Exit-Code).

**Regeln, die der Planer als Aufgaben und Tests braucht:**

- **Versuch = Schlüssel hat `intent` erreicht.** `skipped` verbraucht den Schlüssel nicht (sonst blockiert ein `outside_session` um 09:40 den gültigen Lauf um 10:00). Ein Schlüssel mit `intent` oder einem späteren Zustand blockiert jede weitere `intent` (REQ-40).
- **Zweite Fassung.** Der `intent` speichert das Rating; liest ein späterer Lauf für denselben `(trade_date, ticker)` ein anderes Rating oder einen anderen `paper_log_sha`-Inhalt für denselben Eintrag, wird `skipped` mit Grund `decision_changed` protokolliert und nicht ausgeführt (SC8). Das ist in der Praxis selten (das Decision-Log hält die erste Fassung), die Abweichung zeigt sich meist als `signal-divergence` aus Phase 4.
- **Dateiende.** Ein abgebrochener Append kann eine Zeile ohne `\n` hinterlassen. Beim Öffnen prüfen, ob die Datei auf `\n` endet; wenn nicht und die letzte Zeile kein gültiges JSON ist, ist sie **toleriert und wird beim nächsten Append mit `\n` abgeschlossen**, nicht angehängt. Eine defekte Zeile **in der Mitte** ist ein Befund → Exit 6 (Ledger nicht vertrauenswürdig). Begründung für die Toleranz: Die Order folgt erst, nachdem der `intent`-Append samt `fsync` zurückkam; eine abgerissene Zeile heißt also „nichts gesendet".
- **Dauerhaftigkeit.** `open(path, "ab")`, genau ein `write()` je Zeile, `flush()`, `os.fsync()`. `fsync` auf dem Verzeichnis gibt es unter Windows nicht; für eine neu angelegte Datei ist das ein hingenommenes Restrisiko [ASSUMED].
- **Modus in der Datei und im Dateinamen.** `ledger-dryrun.jsonl` trägt in jeder Zeile `"mode":"dryrun"`. Der echte Ledger darf keine solche Zeile enthalten; findet die Reconciliation eine, ist das ein Befund (Exit 6). Das ist eine billige Gegenprobe, die D-08 nicht ersetzt, sondern absichert.
- **Reconciliation je Modus.** Die Reconciliation läuft auf dem Ledger des **aktuellen Modus**, mit identischem Code. In Phase 5 heißt das: `execute` (trocken) reconciled `ledger-dryrun.jsonl`; der echte Ledger bleibt leer und wird nie berührt. Ein abgebrochener Trockenlauf (`intent` ohne `dry_complete`) macht den nächsten Trockenlauf deshalb zu Exit 6 und ist damit zugleich der CLI-Nachweis für SC6; die Behebung ist „`ledger-dryrun.jsonl` löschen oder umbenennen" und steht im Handbuch. Das ist eine Lesart von D-07/D-08, die beim Bestätigen im Plan-Check zu bestätigen ist (Annahme A6).
- **Dry-Läufe verbrauchen keinen echten Schlüssel.** Dieselbe Trennung bedeutet: ein Trockenlauf am Tag X blockiert den echten Lauf am Tag X in Phase 6 nicht. Negativ-Kontrolle: nach einem Trockenlauf existiert `ledger.jsonl` nicht oder ist leer.

**Gründe für `skipped`** (REQ-42 nennt neun; die Kette erzeugt mehr). Zuordnung zu den Zuständen der Phase 4 und zu Exit-Codes, damit Handbuch-Test und Tabelle eindeutig sind:

| `reason` | Quelle | Exit des Tickers |
|---|---|---|
| `hold` | `skipped-hold` | 2 (D-16 aus Phase 4) |
| `review` | `rating-review`, `run-not-ok`, `signal-null` | 2 |
| `tolerance` | `within-tolerance`, `long-only-noop` | 0 |
| `stale` | `stale-decision`, `future-decision` | 2 |
| `not_tradable` | Phase-3-Zustände `not-mapped`, `not-allowed`, `ambiguous`, `not-found`, `drift`, `not-tradable`, `session-unknown`, `halted`; `calendar-conflict` | 2 |
| `outside_session` | `CLOSED` aus `evaluate_session` | 2 |
| `size_cap` | `check_size` | 5 |
| `kill_switch` | Schalter | 4 |
| `source_conflict` (neu, REQ-63) | Vergleichsfunktionen | 2 |
| `already_attempted` (neu, REQ-40) | Schlüssel hat `intent` | 2 |
| `decision_changed` (neu, REQ-40/SC8) | abweichende Fassung | 2 |
| `foreign_open_order` (neu, reicht Phase 4 durch) | `foreign-open-order` | 2 |
| `rejected` ist **kein** `skipped`, sondern ein eigener Zustand | `whatIf`-Urteil ≠ OK | 5 |

`weekend_gap` ist laut REQ-IBKR-20 eine **Markierung** am `intent` (Feld), kein Grund; in der REQ-42-Aufzählung steht es trotzdem als Grund. Empfehlung: Feld `weekend_gap: true` am `intent` und am `skipped`-Eintrag, kein eigener Grund (REQ-42 und REQ-20 werden bei dieser Gelegenheit zusammengezogen).

### Pattern 5: Größe als Konstante, doppelt geprüft, mit Sentinel

```python
# Source: eigener Entwurf zu D-09
MAX_QTY_PER_ORDER = 2

def check_size(quantity) -> str | None:
    """None, wenn erlaubt; sonst der Grund. Nie kürzen (REQ-32)."""
    if type(quantity) is not int or quantity <= 0:
        return f"quantity {quantity!r} is not a positive whole number"
    if quantity > MAX_QTY_PER_ORDER:
        return f"quantity {quantity} exceeds MAX_QTY_PER_ORDER {MAX_QTY_PER_ORDER}"
    return None
```

- **Sentinel (D-09):** ein Test rechnet `max(decision.BLOCKS.values()) * max(spec.block_qty für handelbare Einträge in CONTRACT_TABLE)` und verlangt `<= MAX_QTY_PER_ORDER`. Heute 2 × 1 = 2 (grün). Wird `block_qty` auf 2 erhöht, ergibt es 4 und der Test fällt, mit einer Meldung, die auf die bewusste Anhebung der Konstante hinweist.
- **Zweite Prüfung** an der Placer-Grenze (`DryPlacer.complete` und in Phase 6 der echte Placer) mit **derselben** Konstante, damit ein Fehler in der Kettenreihenfolge die Grenze nicht umgeht. Keine zweite Konstante im Adapter: zwei Zahlen driften auseinander.
- **Folge, die der Operator kennen muss:** `plan_order` kann `SELL` über der Grenze erzeugen, z. B. ein von Hand gekaufter Bestand von 5 Stück und Rating `Sell` ergibt `SELL 5`. Das wird abgelehnt (Exit 5, `size_cap`), nicht auf 2 gekürzt. Das ist gewollt (REQ-32) und gehört ins Handbuch.

### Pattern 6: Adapter-Erweiterung innerhalb der Grenze von zehn Methoden

Öffentliche Methoden heute: `connect, positions, health, search_contract, contract_details, open_orders, preview_order` (7) [VERIFIED: `tests/test_ibkr_isolation.py:128`]. REQ-IBKR-07 nennt zusätzlich `place`, `executions`, `cancel_all`. Phase 6 braucht `place`.

Empfehlung: **`order_history()`** (liefert offene + erledigte Orders + Executions in einem Ergebnisobjekt, drei Anfragen in einem Lesefenster), **`cancel_all(kill_evidence=)`** und `open_orders(con_id=None)` (ohne Filter = alle). Damit sind es 9, und Phase 6 hat Platz für `place` (= 10). Der Isolations-Test hat die **exakte Menge** der Namen festgeschrieben und muss mitgeändert werden.

`order_history()` liefert broker-neutrale Datensätze (keine Bibliotheksobjekte):

```python
@dataclass(frozen=True)
class OrderRecord:        # aus reqAllOpenOrdersAsync und reqCompletedOrdersAsync
    source: str           # "open" | "completed"
    order_ref: str        # Order.orderRef, "" für manuelle TWS-Orders
    status: str           # orderStatus.status (completedOrder setzt nur orderId+status!)
    action: str
    quantity: float
    filled: float         # bei "completed": Order.filledQuantity, UNSET_DOUBLE abfangen
    con_id: int
    perm_id: int
    order_id: int
    client_id: int

@dataclass(frozen=True)
class ExecutionRecord:    # aus reqExecutionsAsync
    exec_id: str; order_ref: str; perm_id: int; order_id: int; client_id: int
    shares: float; price: float; side: str; time: datetime
```

Tatsachen aus der installierten Bibliothek, die den Zuschnitt bestimmen [VERIFIED: `ib_async` 2.1.0 `wrapper.py:722-733`, `objects.py:54-95`, `client.py:726-740, :1157`]:

- `completedOrder` baut `OrderStatus(orderId, status)` und **nur** das; Füllmenge steht in `order.filledQuantity` (Standardwert `UNSET_DOUBLE`, `order.py:147`), nicht in `orderStatus.filled`.
- `ExecutionFilter` hat **kein** `orderRef`-Feld (nur `clientId, acctCode, time, symbol, secType, exchange, side`). Die Filterung auf `orderRef` (REQ-43) ist **clientseitig** auf `fill.execution.orderRef`.
- `reqCompletedOrders` trägt Nachricht 99, `reqExecutions` Nachricht 7, `reqAllOpenOrders` 16; keine liegt in `_WRITE_MESSAGE_IDS = {3, 4, 19, 21, 58}`, die Sperre lässt sie also durch.
- Jede der drei Anfragen läuft über `self._read(...)` und erbt damit Timeout, „kein offener Link vorher" und „Link-Ereignis im Fenster verwirft die Antwort" (`WINDOW_BENIGN_CODES` unverändert lassen; er wird vom Operator-WIP `ibkr_market_data.py` mitgenutzt).

### Pattern 7: Reconciliation als reine Funktion

```python
# Source: eigener Entwurf zu REQ-IBKR-43
def resolve_entry(entry, open_orders, completed, executions) -> Resolution:
    key = entry["decision_key"]
    match_open = [o for o in open_orders if o.order_ref == key]
    match_done = [o for o in completed if o.order_ref == key]
    match_exec = [x for x in executions if x.order_ref == key]
    # 1. Kollision: gleiche orderRef, aber falscher Contract/Seite/Menge -> unauflösbar (orderRef ist nicht eindeutig, REQ-41)
    # 2. offene Order vorhanden (nicht erledigt)          -> "open"   (Eintrag bleibt placed, Ticker wird übersprungen)
    # 3. Executions vorhanden: Summe(shares) == quantity   -> "filled"; 0 < Summe < quantity -> "partial"
    # 4. erledigt ohne Executions: Filled -> "filled" nur mit Executions oder filled>0, sonst "unresolved";
    #    Cancelled/ApiCancelled/Inactive/ValidationError   -> "not_filled" (rejected)
    # 5. keine Spur in allen drei Quellen                  -> "no_trace"  -> unauflösbar
    # 6. Quellen widersprechen sich (offen vs. erledigt)   -> "unresolved"
```

`no_trace` ist **bewusst unauflösbar**: Ein `intent` ohne Spur kann „nie gesendet" heißen oder „gesendet, aber außerhalb der Fenster der Broker-Abfragen". Beides ist ohne Operator nicht unterscheidbar; REQ-43 sagt „statt zu raten". Das führt zu Exit 6 bei jedem Folgelauf, bis der Operator den Eintrag auflöst (Offene Frage 4 nennt einen Weg).

### Anti-Patterns to Avoid

- **`Path.exists()`/`os.path.exists()` für `KILL`:** Siehe Pattern 1; fail-open bei Berechtigungsfehlern oder versionsabhängig.
- **`try: with locked(...): ... except OSError:` um den ganzen Lauf:** Fängt `OSError`s des Laufs selbst und macht sie zu Exit 7. Erst die Sperre nehmen (`ExitStack.enter_context`), nur **diesen** Aufruf in `try/except OSError`, dann den Lauf außerhalb.
- **Zustand im Ledger durch Umschreiben fortschreiben:** zerstört append-only und die Spur. Ereignisse anhängen.
- **Reconciliation im Dry-Modus mit dem echten Ledger:** würde den echten Ledger anfassen und D-08 aushöhlen.
- **`cancel_all` an mehr als einer Stelle oder ohne Kill-Beleg:** bricht „kein anderer Code-Pfad kann stornieren".
- **`reqGlobalCancel` bei „Zustand nicht lesbar":** Das Storno ist destruktiv (auch manuelle TWS-Orders). Fail-closed heißt „nicht handeln", nicht „alles stornieren". Empfehlung: Storno nur bei **positiv vorhandener** `KILL`-Datei (Offene Frage 5).
- **Zweite Konstante für die Größengrenze im Adapter:** driftet.
- **`ib_async` oder Marktdaten-Aufrufe in den neuen Modulen:** die Wächter-Tests verbieten beides.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prozessübergreifender Lauf-Lock | eigene Lock-Datei mit PID/Zeitstempel | `tradingagents.dataflows.files.locked(path, wait=False)` | Wird beim Prozesstod vom Betriebssystem freigegeben; eine PID-Datei bleibt liegen und blockiert danach. Geprüft: zweiter Versuch im selben Prozess → `False` (Windows) |
| Strenges Datum parsen | eigenes `strptime`-Muster | Regex `^\d{4}-\d{2}-\d{2}$` **plus** `date.fromisoformat` | `fromisoformat` akzeptiert ab 3.11 auch `20261031` und Wochenformate; die Regex hält das Format eng |
| Sitzungsfenster | neue Zeitfenster-Logik | `ibkr_contracts.evaluate_session` mit `SESSION_BUFFER_MINUTES` | Halbtage, Alt-Format, `CLOSED`-Tage, Zeitzonen sind dort getestet (995 Zeilen Tests) |
| Entscheidungs-/Aktualitätskette | Neuimplementierung in `execute` | `_local_chain`, `_load_stored_contracts`, `_session_info`, `resolve_all`, `plan_order`, `judge_preview` wiederverwenden | 424 grüne Tests bewachen sie; `preview` bleibt unverändert |
| Atomares JSON für `--out`-Datensätze | eigener Schreiber | `contracts_mod.write_json_atomic` | schon vorhanden, wird von `preview` benutzt |
| Fail-closed-Lesefenster | eigene Link-Prüfung | `IbkrBroker._read` | Timeout, offener Link, Link-Ereignis im Fenster; neue Lesemethoden erben es |
| Idempotenz über Order-IDs | `orderId`-Monotonie | Ledger + `orderRef` | `orderId` ist laut REQ-IBKR-08 kein Idempotenzschutz |

**Key insight:** Die Leitplanken sind klein; ihr Wert liegt in der lückenlosen Verdrahtung und in den Negativ-Kontrollen. Jede selbstgebaute Variante einer vorhandenen Stelle (Lock, Fenster, Lesefenster) wäre eine neue ungeprüfte Fehlerquelle in genau dem Pfad, der später Orders auslöst.

## Common Pitfalls

### Pitfall 1: Kill-Prüfung fail-open durch `exists()`
**What goes wrong:** Ein Berechtigungsfehler auf dem State-Ordner ergibt „keine Kill-Datei", der Lauf handelt.
**Why it happens:** `os.path.exists` liefert bei Zugriffsfehlern `False` [CITED: docs.python.org os.path.exists]; `Path.exists` verhält sich je nach Python-Version anders.
**How to avoid:** `os.stat` mit drei Ausgängen (`FileNotFoundError` → absent, anderer `OSError` → unreadable, sonst active).
**Warning signs:** ein Test „State-Ordner nicht prüfbar" fehlt; `KILL` wird mit `.exists()` geprüft.

### Pitfall 2: `RELEASE` per PowerShell angelegt, Encoding falsch
**What goes wrong:** `echo ... > RELEASE` in Windows PowerShell 5.1 schreibt UTF-16LE mit BOM, `Set-Content -Encoding utf8` schreibt UTF-8 mit BOM. Ein strenges UTF-8-Lesen scheitert, der Lauf endet mit Exit 4, der Operator sieht nur „ungültig".
**Why it happens:** Windows-Standard-Encodings; im Projekt gab es dasselbe schon beim Jev-Key („BOM-Fix im Key-Lesen", STATE.md).
**How to avoid:** `utf-8-sig` zum Dekodieren (BOM tolerieren), UTF-16 bewusst ablehnen mit einer Meldung, die „not UTF-8" nennt. Handbuch-Einzeiler per `python -c` oder `[IO.File]::WriteAllText(path, text)` (UTF-8 ohne BOM) angeben; **den Einzeiler vor dem Dokumentieren auf diesem Rechner ausführen** [ASSUMED: Verhalten von PS 5.1 nicht in dieser Sitzung gemessen].
**Warning signs:** `RELEASE_INVALID` direkt nach dem Anlegen.

### Pitfall 3: `except OSError` um den ganzen `with locked(...)`
**What goes wrong:** Ein `OSError` aus dem Lauf (z. B. Ledger-Schreibfehler) wird als „Lock nicht erhalten" gemeldet.
**Why it happens:** `contextmanager` wirft Ausnahmen des Rumpfes an der `yield`-Stelle zurück.
**How to avoid:**
```python
from contextlib import ExitStack
stack = ExitStack()
try:
    held = stack.enter_context(locked(lock_path, wait=False))
except OSError as exc:                       # nur der Sperrversuch (auch open() des Sidecars: FileNotFoundError, PermissionError)
    return EXIT_LOCKED                       # protokolliert als LOCK_ERROR
if not held:
    stack.close()
    return EXIT_LOCKED                       # protokolliert als LOCK_HELD
with stack:
    return run_chain(...)                    # Fehler des Laufs behalten ihren eigenen Exit
```
Geprüft [VERIFIED: Skript in dieser Sitzung]: fehlendes Verzeichnis wirft `FileNotFoundError` aus `locked(..., wait=False)` (`open(f"{path}.lock", "a+b")`), also muss der State-Ordner **vor** dem Sperrversuch angelegt werden, und ein Anlegefehler ist ebenfalls „nicht ausführen".
**Warning signs:** Exit 7 bei einem Schreibfehler.

### Pitfall 4: Ledger-Zeile ohne Zeilenumbruch
**What goes wrong:** Nach einem Absturz mitten im Schreiben hängt der nächste Append an die halbe Zeile an; beide Zeilen sind danach unlesbar und die Reconciliation sieht einen Mittelbefund.
**How to avoid:** Pattern 4 (Dateiende prüfen, toleranter letzter Rest, Mittendefekt = Exit 6).
**Warning signs:** `json.JSONDecodeError` beim Lesen nach einem erzwungenen Abbruch.

### Pitfall 5: `reqGlobalCancel` gilt als erfolgreich, weil es nicht scheitert
**What goes wrong:** Nachricht 58 hat keine Antwort; ein Gateway mit eingeschaltetem „Read-Only API" oder ein Link-Fehler lässt sie wirkungslos.
**How to avoid:** Nachlese über `open_orders(None)` mit Wiederholung; Exit 4 unabhängig vom Ergebnis, aber `remaining>0` laut protokollieren. Messung A1 im Operator-Checkpoint.

### Pitfall 6: Dry-Lauf und echter Lauf teilen sich den Lock nicht
**What goes wrong:** Ein Trockenlauf und ein späterer echter Lauf (Phase 6) laufen gleichzeitig.
**How to avoid:** Lock-Pfad ist **immer** der des echten Ledgers (`ledger.jsonl.lock`), unabhängig vom Modus; die Datenverzeichnisse sind getrennt, die Sperre nicht.

### Pitfall 7: Tests schreiben in den echten State-Ordner
**What goes wrong:** Ein `execute`-Test ohne `LOCALAPPDATA`-Umbiegung legt `ledger-dryrun.jsonl`/`ledger.jsonl.lock` im echten `%LOCALAPPDATA%\TradingEngineX\ibkr` an (dort liegen bereits `contracts.json`, `preview.json`, `portfolio.json`) [VERIFIED: Verzeichnisliste in dieser Sitzung]. Umgekehrt würde eine vom Operator dort liegen gelassene `KILL` jeden ungesicherten Test beeinflussen.
**How to avoid:** autouse-Fixture `monkeypatch.setenv("LOCALAPPDATA", tmp_path)` wie in `test_ibkr_preview.py`, **und** ein Wächtertest, der `default_ledger_file()` & Co. ohne Umbiegung nicht aufruft bzw. den Pfad auf `tmp_path` zurückführt.

### Pitfall 8: Ein `git status`-Test, der „leer" verlangt
**What goes wrong:** Das Repo hat uncommittete Dateien des Operators (`scripts/ibkr_market_data.py`, `tests/test_ibkr_market_data.py`, Änderungen an `IBKR_EXECUTION.md`/`test_ibkr_isolation.py`); ein absoluter „Status ist leer"-Test ist dauerhaft rot.
**How to avoid:** `git status --porcelain` **vor und nach** dem Lauf vergleichen (Gleichheit), und zusätzlich strukturell prüfen, dass kein State-Pfad unter dem Repo-Root liegt und keine `.lock`/`.tmp`-Datei im Baum entsteht. Zusätzlich eine Laufzeitprüfung im Executor: State-Ordner mit `.git` in einem Elternverzeichnis → Exit 1.

### Pitfall 9: Handbuch- und Isolationstests, die Phase 5 absichtlich bricht
Diese Tests müssen **mitgeändert** werden, sonst fällt CI aus dem falschen Grund:
- `test_adapter_has_at_most_ten_public_methods` pinnt die exakte Namensmenge (neu: `order_history`, `cancel_all`).
- `test_handbook_exit_table_matches_executor` verlangt genau 10 `EXIT_*`-Konstanten und je eine Tabellenzeile. **Keine neuen `EXIT_*`-Konstanten einführen.** Die Zeilen 4, 6, 7 verlieren „reserved for later phases"; dafür gibt es bereits Muster-Tests für 2 und 5 (`test_handbook_exit_two_is_active`, `…_five_…`), analog ergänzen.
- `test_no_hard_coded_trading_times_in_execution_code` prüft alle `scripts/ibkr_*.py`, also auch die neuen Module: keine `09:30`-artigen Literale (auch nicht in Docstrings/Beispielen).
- `test_execution_path_does_not_load_the_market_data_session` (Operator-WIP) iteriert `(EXECUTOR, ADAPTER, DECISION, PAPERLOG)`: die neuen Module in diese Tupel aufnehmen und sicherstellen, dass sie `ibkr_market_data` nicht nennen.
- `test_no_market_data_in_execution_path` prüft die Aufrufnamen: die neuen Module aufnehmen.

### Pitfall 10: `FakeOrder` kennt kein `orderRef`
`tests/ibkr_fakes.py:71` definiert `FakeOrder` ohne `orderRef`; `preview_order(order_ref=...)` würde im Adapter mit `TypeError` scheitern. Feld `orderRef: str = ""` ergänzen; ebenso `FakeIB` um `completed_orders`, `executions`, `reqCompletedOrdersAsync`, `reqExecutionsAsync` und `reqGlobalCancel` (letzteres ruft `self.client.reqGlobalCancel()`, damit die Sperre im Fake sichtbar wird). Die vorhandenen `_forbidden`-Attrappen heißen `reqCompletedOrders`/`reqExecutions` (synchron) und bleiben richtig, weil der Adapter die `...Async`-Varianten nutzt.

### Pitfall 11: Der SC3-Nachweis misst nichts, wenn der Schreibschutz-Schalter an ist
Ist „Read-Only API" am Gateway an, scheitert `whatIf` (321, 10 s) und `reqGlobalCancel` ist vermutlich wirkungslos (A1). Der Operator muss vor dem Checkpoint den Schalter **aus** haben (Stand seit 2026-10-12: aus) und das im Protokoll vermerken.

## Code Examples

### Lock mit `OSError` als „nicht ausführen"
Siehe Pitfall 3 (vollständig).

### Ledger-Anhängen mit `fsync`
```python
# Source: eigener Entwurf; Windows-fsync auf Dateien funktioniert, auf Verzeichnissen nicht
def append(self, **fields) -> dict:
    self._seq += 1
    record = {"v": 1, "seq": self._seq, "ts": self._clock().isoformat(), "mode": self.mode, **fields}
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with open(self.path, "ab") as handle:
        if self._torn_tail:                    # beim Öffnen festgestellt (Pitfall 4)
            handle.write(b"\n")
            self._torn_tail = False
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return record
```

### Beide Schalter vor jeder Order, mit einem Beleg für den Kill-Pfad
```python
# Source: eigener Entwurf zu D-04
def check_switches(state_dir, *, today_utc, expected_account) -> Switches:
    return Switches(
        release=read_release(os.path.join(state_dir, "RELEASE"), today_utc=today_utc,
                             expected_account=expected_account),
        kill=read_kill(state_dir),
    )

# Switches.allowed  = release.state == "ok" and kill.state == "absent"
# Switches.cancel   = kill.state == "active"          # nur positiv vorhanden löst das Storno aus
```

### Zwei Quellen für „schon ausgeführt?" (REQ-63)
```python
# Source: eigener Entwurf
def executed_conflict(ledger_attempted: bool, history_has_ref: bool) -> str | None:
    """Vorsichtiger Wert gewinnt: ein Treffer in einer der Quellen heißt 'schon ausgeführt'."""
    if ledger_attempted != history_has_ref:
        return ("ledger says attempted, broker shows no trace" if ledger_attempted
                else "broker shows an order with this orderRef, ledger has none")
    return None
```
Der erste Fall (Ledger ja, Broker nein) ist die Reconciliation (Exit 6); der zweite (Broker ja, Ledger nein) ist der Ticker-Widerspruch dieser Funktion (`skipped source_conflict`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Freigabe als Env-Variable (REQ-33 Wortlaut) | Freigabe-Datei mit Konto und Ablaufdatum | D-01, 2026-10-16 | REQ-33 und REQ-64 im Text angleichen, mit datiertem Änderungsvermerk wie bei D-19/D-20 aus Phase 3 |
| Sitzungsfenster in Phase 4 (REQ-25) | Phase 5 | 2026-10-16 | Logik existiert (`evaluate_session`); neu ist die Verdrahtung und der Test auf Ausführungsebene |
| `Path.exists()` für Schalter | `os.stat` mit drei Zuständen | dieser Plan | siehe Pitfall 1 |

**Deprecated/outdated:** die Annahme „Gateway-Read-Only schützt in den Phasen 2-4" ist seit D-14 aufgegeben; die Socket-Sperre im Adapter ist der Schutz, und `cancel_all` ist die **einzige** Öffnung darin.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `reqGlobalCancel` (58) storniert am Paper-Gateway 10.50.1 auch eine manuell in TWS angelegte `DAY`-Limit-Order; ein eingeschalteter Schalter „Read-Only API" macht es wirkungslos (Verhalten bei 58 nie gemessen, nur die Bibliotheks-Doku sagt „including those placed by other clients or TWS") | Pattern 3, Pitfall 5, 11 | SC3 am Gateway scheitert oder belegt nur das Senden; REQ-67 verlangt Messung vor dem Bauen auf Fehlercodes. Der Operator-Checkpoint ist die Messung |
| A2 | `reqCompletedOrders(apiOnly=False)` liefert die per Hand in TWS angelegte und danach stornierte Order mit Status `Cancelled` und `orderRef == ""`; Rohform mit **echtem** Inhalt wurde nie gemessen (Befund Phase 1: nur `count=0`) | Pattern 6, 7 | Reconciliation-Klassifikation stützt sich auf eine ungemessene Rohform; der Checkpoint sollte die Rohausgabe protokollieren |
| A3 | `|` in `orderRef` wird vom Gateway akzeptiert und im `whatIf`-Echo zurückgegeben (Befund Phase 1 sagt nur „akzeptiert `orderRef`", Zeichenfrage REQ-01d nicht beantwortet) | Pattern 4, REQ-39 | Ist `|` unzulässig, muss `decision_key` `_` nutzen (REQ-39 sieht das vor); wird erst in Phase 6 an einer echten Order sichtbar, wenn man es nicht vorher per `whatIf` misst |
| A4 | Fenster von `reqCompletedOrders`/`reqExecutions` reicht für den Handelstag; ältere `intent`s sind damit nicht auflösbar (REQ-48, offiziell widersprüchlich, nie mit Inhalt gemessen) | Pattern 7, Offene Frage 4 | Ein `intent` vom Vortag ist immer unauflösbar → Exit 6; in Phase 5 folgenlos (kein echter Ledger), in Phase 6/8 relevant |
| A5 | Das `whatIf`-Echo trägt `order.account` und `order.orderRef` (Echo-Tap in `preview_order` liest bisher nur `tif`) | Offene Frage 3 | Bei fehlendem Echo muss die zweite Quelle für „Konto" allein `RELEASE.account` sein (D-02); Fail-closed bei „Echo leer" würde jeden Lauf stoppen, deshalb als optionale dritte Quelle behandeln |
| A6 | Die Reconciliation läuft auf dem Ledger des **aktuellen Modus** (trocken → `ledger-dryrun.jsonl`), nicht auf dem echten | Pattern 4 | Andere Lesart von D-07/D-08: SC6 wäre über die CLI nicht zeigbar; Bestätigung im Plan-Check einholen |
| A7 | Kein neues Paket nötig; `fsync` auf neu angelegten Dateien ohne Verzeichnis-`fsync` ist unter Windows hinnehmbar | Standard Stack, Pattern 4 | Bei Stromausfall direkt nach Anlegen könnte der erste Ledger-Eintrag fehlen; der echte Ledger entsteht erst in Phase 6, der Lauf-Nachweis kommt davor |

## Open Questions (RESOLVED)

1. **Wo steht die erste Schalterprüfung relativ zur Reconciliation?**
   - **RESOLVED:** D-21 (Preflight direkt nach dem Lock, vor der Reconciliation; umgesetzt in 05-05, Vermerk für Phase 6 in 05-09)
   - Was wir wissen: REQ-45 setzt Kill-Switch zwischen Handelszeit und `whatIf`; SC1/SC2 und D-04 verlangen Prüfung vor jeder Order und Protokoll in jedem Lauf; ein aktiver Kill muss den Gateway-Kontakt zum Stornieren auslösen können, auch wenn die Reconciliation scheitern würde.
   - Was unklar ist: ob der Phase-6-Reihenfolgetest einen zusätzlichen Preflight-Schritt zulässt.
   - Empfehlung: Preflight direkt nach dem Lock, vor der Reconciliation (Schalterzustand ins Ledger, Kill → Storno-Pfad), plus die Prüfungen an den Stellen nach REQ-45 und unmittelbar vor `intent`. Im Plan als „Superset von REQ-45" benennen und REQ-45 bei Phase 6 entsprechend lesen.

2. **Was heißt „Widerspruch der Position" in Phase 5, wo es keine Fills gibt?**
   - **RESOLVED:** D-18 (enge Regel; umgesetzt in 05-01 und 05-07)
   - Was wir wissen: REQ-63 nennt „Ledger und `reqPositions()`". Der echte Ledger ist leer, der Trocken-Ledger enthält nie Fills. Ein Ledger-Soll von 0 stünde jedem manuell gehaltenen Bestand gegenüber und würde diesen Ticker dauerhaft stoppen.
   - Empfehlung: Mechanismus und Test jetzt bauen, aber nur mit einer **engen** Regel: Widerspruch, wenn der Ledger eigene gefüllte Menge `Q > 0` für diese `conId` kennt und der Broker-Bestand kleiner als `Q` ist (der Executor kann nicht weniger halten, als er selbst gekauft hat, ohne dass etwas Fremdes passiert wäre). Ohne Fills im Ledger ergibt sich kein Widerspruch. Die Regel für Verkäufe und Fremdbestände wird mit der Fill-Verarbeitung in Phase 6/7 geschärft. Bestätigung des Operators einholen.

3. **Was ist die zweite Quelle für „Handelbarkeit" und „Konto der Order" vor der ersten Order?**
   - **RESOLVED:** D-22 (Kalender + `liquidHours`, `managedAccounts` + `RELEASE.account`, Echo optional; umgesetzt in 05-07, Handbuch 05-09)
   - Was wir wissen: „Order-Status nach Platzierung (399 geparkt)" existiert erst mit einer echten Order (Phase 6). Die `whatIf`-Antwort zeigte bei geschlossener Börse **keinen** Warntext (`warningText=''`, Messung 2026-10-12), taugt also nicht als Ersatz. Das Konto-Feld der Order kommt nur zurück, wenn das Gateway es im Echo spiegelt (A5).
   - Empfehlung: Vergleichsfunktionen, Tests (zwei Quellen laufen auseinander → keine Order) und Verdrahtung jetzt; die Handelbarkeits-Quelle „Order-Status 399" im Placer von Phase 6 anschließen, bis dahin ist die zweite Quelle die Kombination aus `evaluate_session` und `calendar_conflict` (beides schon in der Kette) und im Handbuch so benannt. Konto: `managedAccounts` (Guard) und `RELEASE.account` sind die zwei Quellen; das Echo ist optional und nur bei Abweichung maßgeblich.

4. **Wie wird ein unauflösbarer `intent` (Exit 6) aufgelöst?**
   - **RESOLVED:** D-19 (Abbruch + Meldung in 05-07, Handbuch-Ablauf in 05-09, `--resolve` in Phase 6)
   - Was wir wissen: REQ-43 verlangt Abbruch statt Raten; ohne Auflösungsweg blockiert jeder Folgelauf dauerhaft, auch in Phase 8 unbeaufsichtigt.
   - Empfehlung: Phase 5 liefert Abbruch + eindeutige Meldung (welcher Schlüssel, was die Quellen zeigen). Die Auflösung ist **Operator-Handlung mit Spur**: ein dokumentierter Ablauf (Handbuch) oder ein kleines Flag `execute --resolve KEY=never_sent --note TEXT`, das ein `resolved`-Ereignis anhängt, nie eine Zeile ändert. Ob das Flag in Phase 5 oder Phase 6 gehört, entscheidet der Operator; für Phase 5 reicht der Abbruch samt Handbuchabschnitt.

5. **Löst „Zustand nicht lesbar" das `reqGlobalCancel` aus?**
   - **RESOLVED:** D-17 (Storno nur bei vorhandener `KILL`-Datei; 05-01, 05-05)
   - Was wir wissen: D-03 sagt „gilt als aktiv (Exit 4)"; D-05/REQ-35 binden das Storno an einen **festgestellten** aktiven Kill-Switch; die Diskussion nannte als Risiko, dass ein Bug fremde TWS-Orders wegräumt.
   - Empfehlung: Storno **nur bei positiv vorhandener `KILL`-Datei**. Unlesbarer Zustand und fehlende/abgelaufene Freigabe enden mit Exit 4 **ohne** Storno (`KILL_UNREADABLE`, `RELEASE_*`). Das liest D-03 „aktiv" als „Handel gesperrt", nicht als „Storno". Operator bestätigen lassen; die Gegenlesart (Storno auch bei unlesbar) ist ein Einzeiler im Executor.

6. **Obergrenze für die Laufzeit der Freigabe?**
   - **RESOLVED:** D-20 (90 Tage; 05-01)
   - Was wir wissen: D-01 will „Wochen im Voraus"; eine ewige Freigabe wird vergessen.
   - Empfehlung (optional): `valid_until` weiter als N Tage in der Zukunft → `invalid`. N ist Operator-Ermessen (Vorschlag 90). Ohne Obergrenze genügt `valid_until=9999-12-31` als „ewige" Freigabe.

7. **Jev-Todo (`2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview`): gehört es in Phase 5?**
   - **RESOLVED:** D-23 (nicht in Phase 5, Eingangsaufgabe von Phase 6; Feld `rating_source` in 05-02, ROADMAP-Vermerk in 05-09)
   - Was wir wissen: Das Todo betrifft die **Entscheidungsquelle** (Rating im Decision-Log nicht von einem Engine-Rating unterscheidbar), nicht eine Leitplanke. `summary.json` trägt `rating_source` (`daily_paper_run.py:372`); der Konsumentenvertrag `SUMMARY_FIELDS/RUN_FIELDS` liest das Feld heute nicht. Phase 5 sendet nichts, ein Jev-Rating in einem Trockenlauf ist folgenlos.
   - **Empfehlung: nicht in Phase 5.** Es ist eine Vorbedingungsprüfung in der Familie von REQ-IBKR-16/-17 (Phase 4) und hat drei Lösungswege (a Log-Tag, b `summary.json`-Abgleich, c bewusst akzeptieren), von denen (a) eine Upstream-Datei ändert. Die Entscheidung muss **vor der ersten echten Order** fallen, also als Eingangsaufgabe von Phase 6 (oder als eigene kleine Einfügung zwischen 5 und 6 nach G3) eingeplant werden, nicht als Teil von G3. Billige Mitnahme in Phase 5, falls gewünscht: das Ledger-Schema hat ein optionales Feld `rating_source`, das erst in Phase 6 befüllt wird. Das ist keine Entscheidung; sie liegt beim Operator.

8. **`execute` und Aktualisierung von REQUIREMENTS-/ROADMAP-Text.**
   - **RESOLVED:** 05-09 Task 2 (datierte Vermerke zu REQ-25/-33/-42/-63 und ROADMAP)
   - Dokumentpflege, die der Plan einplanen muss (jeweils mit datiertem „Geändert 2026-10-..."-Vermerk nach dem Muster aus Phase 3): REQ-33 (Freigabe-Datei statt -Variable), REQ-42 (Gründe `source_conflict`, `already_attempted`, `decision_changed`, `foreign_open_order`; `weekend_gap` als Markierung), REQ-25 (Fenster = Phase-3-Puffer), und im ROADMAP SC1 „Freigabe fehlt" bleibt wörtlich richtig.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `.venv` | alles | ✓ | 3.13.13 | — |
| `ib_async` | Adapter, echte Client-Klasse in Tests | ✓ | 2.1.0 | — (CI installiert `.[ci]` und schlägt sonst fehl) |
| `exchange_calendars` | `execute` über `_local_chain` | ✓ | 4.13.2 | — |
| `ruff` | Lint | ✓ | 0.17.0 | — |
| `git` | Wächtertest „Status vorher = nachher" | ✓ | 2.56.0.windows.1 | strukturelle Prüfung ohne `git` |
| IB Gateway Paper (127.0.0.1:7497) | nur Operator-Checkpoints | nicht geprüft (Operator) | 10.50.1 laut Befund | Tests laufen ohne Gateway |
| TWS Paper (manuelle Order) | Operator-Checkpoint SC3 | nicht geprüft (Operator) | — | — |
| `uv`/`make` | — | ✗ (SSL, siehe Memory) | — | `.venv/Scripts/python.exe -m pytest|ruff` |

**Missing dependencies with no fallback:** keine für die Entwicklung. Der Operator-Checkpoint braucht ein laufendes Gateway und TWS Paper und liegt in der Hand des Operators.

**Missing dependencies with fallback:** `uv`/`make` (Fallback bekannt).

Vorhandener State-Ordner `%LOCALAPPDATA%\TradingEngineX\ibkr` enthält `contracts.json`, `contracts-history.jsonl`, `portfolio.json`, `preview.json`, `resolve.json`, `logs/`, `paper-log/`; weder `RELEASE`, `KILL` noch ein Ledger [VERIFIED: Verzeichnisliste]. Tests dürfen ihn nicht anfassen (Pitfall 7).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x (`--strict-markers`, Marker `unit`; `-m "not integration"` voreingestellt) [VERIFIED: `pyproject.toml`] |
| Config file | `pyproject.toml [tool.pytest.ini_options]`, `tests/conftest.py` (blockt `socket.connect`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_guards.py tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -x -q` |
| Full suite command | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_contracts.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py tests/test_ibkr_resolve.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_ibkr_guards.py tests/test_ibkr_ledger.py tests/test_ibkr_execute.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_paper_summary_contract.py -q` und danach `.venv/Scripts/python.exe -m ruff check scripts tests` |

Ausgangslage: `tests/test_ibkr_broker.py tests/test_ibkr_isolation.py tests/test_ibkr_executor.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py` → **424 passed in 11,08 s** [VERIFIED in dieser Sitzung, HEAD `b356a5f`, mit dem uncommitteten Operator-WIP im Baum].

### Phase Requirements → Test Map

Für G3 bekommen die vier Nachweise je einen Test mit `g3` im Namen (`-k g3`), damit das Gate ohne Gateway per Befehl belegbar ist.

| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| SC1 / REQ-33, -64 | Freigabe fehlt · unlesbar (PermissionError, Verzeichnis statt Datei) · UTF-16 · abgelaufen · falsches Konto · Kill vorhanden · State nicht prüfbar → je Exit 4, kein Platzierungsaufruf (`FakeIB.calls` ohne `placeOrder`), Schalterzustand im Ledger | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "release or kill or fail_closed" -x` | ❌ Wave 0 |
| SC2 / REQ-34, -66 | `KILL` zwischen zwei Orders → zweite Order entsteht nicht, kein `intent` für Ticker 2, Exit 4 | unit | `pytest tests/test_ibkr_execute.py -k "g3 and kill_between" -x` | ❌ Wave 0 |
| SC3 / REQ-35 | Kill aktiv → `cancel_all` genau 1×, Nachlese `open_orders`, Exit 4; ohne `KILL` kein `reqGlobalCancel`; echte `Client`-Klasse: 58 nur im Permit, danach wieder gesperrt | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_execute.py -k "cancel_all or global_cancel" -x` | ❌ Wave 0 |
| SC3 real | manuelle TWS-Order wird storniert, Exit 4, Ledger-Zustand | Operator-Checkpoint | manuell (Abschnitt unten) | — |
| SC4 / REQ-32 | Menge 3 wird abgelehnt (`size_cap`, Exit 5), nicht gekürzt; `whatIf` und `intent` entstehen nicht; Sentinel `BLOCKS × block_qty ≤ MAX_QTY_PER_ORDER` | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "g3 and size" -x` | ❌ Wave 0 |
| SC5 / REQ-46 | JSONL; State-Pfade nicht in einem Git-Baum; `.lock` neben dem Ledger im State-Ordner; `git status --porcelain` vor = nach dem Lauf; kein `.lock`/`.tmp` unter dem Repo-Root; Laufzeitprüfung lehnt State in Git-Baum ab (Negativ-Kontrolle) | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_isolation.py -k "ledger or git" -x` | ❌ Wave 0 |
| SC6 / REQ-42, -43 | abgebrochener Lauf (Placer wirft nach `intent`) hinterlässt `intent`; Folgelauf liest offene/erledigte/Executions (je Quelle ein Fall), löst vor jeder neuen Order auf; unauflösbar (`no_trace`, Kollision, Widerspruch) → Exit 6 ohne neue Order; torn tail toleriert, Mittendefekt → Exit 6 | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -k "g3 and reconcil or write_ahead" -x` | ❌ Wave 0 |
| SC7 / REQ-44 | Zweiter gleichzeitiger Lauf (verschachtelt im selben Prozess, unter Windows geprüft) → Exit 7, kein Ledger-Eintrag, keine Order; `OSError` beim Sperrversuch (fehlendes Verzeichnis, `PermissionError` per monkeypatch) → Exit 7, **kein** Traceback; `OSError` im Lauf bleibt Nicht-7 | unit | `pytest tests/test_ibkr_execute.py -k "lock" -x` | ❌ Wave 0 |
| SC8 / REQ-39, -40, -41 | `order.orderRef == decision_key` an der `whatIf`-Order (`fake.whatif_calls[-1][1].orderRef`), `paper_log_sha` im `intent`; abweichende zweite Fassung → `skipped decision_changed`, nicht ausgeführt; zweiter Lauf mit gleichem Schlüssel → `already_attempted` | unit | `pytest tests/test_ibkr_execute.py tests/test_ibkr_broker.py -k "order_ref or decision_key or decision_changed or already_attempted" -x` | ❌ Wave 0 |
| REQ-25 (Fenster) | `CLOSED` → `skipped outside_session` vor `whatIf` (Fake zeigt keinen `whatif`-Aufruf): innerhalb Fenster; erste 15 min (Eröffnungsauktion-Proxy); letzte 15 min; Halbtag verkürzt automatisch; geschlossener Tag; `session-unknown` bleibt Ablehnung | unit | `pytest tests/test_ibkr_execute.py -k "g3 and session" -x` | ❌ Wave 0 |
| REQ-36 | Jeder Lauf schreibt Schalterzustand ins Ledger, auch bei Exit 0 und bei Exit 4 | unit | `pytest tests/test_ibkr_execute.py -k "switch_state" -x` | ❌ Wave 0 |
| REQ-63 | je ein Test, in dem beide Quellen auseinanderlaufen: Konto (ganzer Lauf stoppt), Position, „schon ausgeführt?", Handelbarkeit (nur der Ticker); es entsteht keine Order | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "source_conflict" -x` | ❌ Wave 0 |
| REQ-66 | je Schutz eine Negativ-Kontrolle (Tabelle unten) | unit | `pytest tests/test_ibkr_execute.py tests/test_ibkr_broker.py -k "negative_control" -x` | ❌ Wave 0 |
| D-07 | `execute` ist zwangsweise trocken: über alle Pfade nie `placeOrder`/`cancelOrder`/`whatIfOrder` (`reqGlobalCancel` nur im Kill-Pfad, genau einmal); `ledger.jsonl` entsteht nie | unit | `pytest tests/test_ibkr_execute.py -k "nothing_sent or forced_dry" -x` | ❌ Wave 0 |
| D-08 | Dry-Lauf schreibt `ledger-dryrun.jsonl`, nie `ledger.jsonl`; Dry-`intent` ist für den echten Modus unsichtbar; echte Datei mit `mode:"dryrun"`-Zeile → Exit 6 | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -k "dryrun" -x` | ❌ Wave 0 |
| Wächter | öffentliche Adapter-Methoden ≤ 10 und exakte Menge; `cancel_all(` im Executor nur an einer Stelle (AST); `ibkr_market_data.py` nennt weder `cancel_all` noch `reqGlobalCancel`; neue Module bibliotheksfrei, ohne `datetime.now`, ohne Marktdatenaufrufe, ohne harte Handelszeiten; Handbuch: Exit 4/6/7 ohne „reserved", RELEASE/KILL-Einzeiler, `execute`, Zustandstabelle gleich Modultabelle | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ (angepasst) |

**Negativ-Kontrollen (REQ-66)** – jede Schutzmaßnahme braucht einen Test, in dem sie auslösen **muss** und der Lauf scheitert:

| Schutz | Negativ-Kontrolle |
|---|---|
| Freigabe/Kill fail-closed | Ohne die Prüfung (Test-Ersatz „alles erlaubt") würde `placeOrder`-Attrappe aufgerufen → der Test belegt, dass sie es mit Prüfung nicht wird; je ein Fall pro Schalterzustand |
| Prüfung vor jeder Order | Variante „einmal pro Lauf" (Test-Ersatz) lässt Order 2 durch; echte Kette nicht |
| `reqGlobalCancel`-Sperre | außerhalb des Permits scheitert 58 auf Name, Feldebene und Draht (echte Client-Klasse); nach `cancel_all` ist das Permit wieder zu; `cancel_all` ohne Beleg scheitert; zweiter `cancel_all` scheitert |
| Größenlimit | Menge 3 wird abgelehnt; Menge 2 passiert |
| Lock | zweiter Lauf → Exit 7; Test-Ersatz ohne Lock ließe beide laufen |
| Write-Ahead | ohne `intent`-Append vor dem Placer gäbe es nach dem Abbruch keinen Eintrag; Test prüft Reihenfolge `intent` vor `Placer.complete` |
| Reconciliation | unauflösbarer Fall → Exit 6, kein `whatIf` für neue Order |
| Ledger-Trennung | Dry-Lauf erzeugt keine `ledger.jsonl` |

### Sampling Rate
- **Per task commit:** der jeweilige `-k`-Befehl aus der Tabelle
- **Per wave merge:** Full suite command (inkl. `ruff check scripts tests`)
- **Phase gate:** gesamte Suite grün (`.venv/Scripts/python.exe -m pytest -q`) vor `/gsd:verify-work`; die Agentenaussage „lint PASSED" selbst nachfahren
- Erwartete Laufzeit: Basis ~11 s, mit Phase 5 voraussichtlich < 30 s

### Wave 0 Gaps
- [ ] `tests/test_ibkr_guards.py` — Schalter, Größe, Schlüssel, Quellenvergleich (REQ-32, -33, -39, -63, -64)
- [ ] `tests/test_ibkr_ledger.py` — Append-only, torn tail, Zustand je Schlüssel, `resolve_entry` (REQ-40, -42, -43, -46)
- [ ] `tests/test_ibkr_execute.py` — Kette gegen `FakeIB` mit Placer-Naht (SC1-SC8, REQ-25, REQ-36)
- [ ] `tests/ibkr_fakes.py` — `FakeOrder.orderRef`, `FakeIB.completed_orders/executions`, `reqCompletedOrdersAsync`, `reqExecutionsAsync`, `reqGlobalCancel`, `emit_during`-Namen `completed_orders`/`executions`/`global_cancel`
- [ ] Anpassung `tests/test_ibkr_isolation.py` (öffentliche Methoden, Handbuchzeilen, Wächter für neue Module)
- Framework-Installation: keine (alles vorhanden)

## Operator-Checkpoints (ein Block, vor der G3-Verifikation)

Diese Messungen sind nach REQ-IBKR-67 nötig, bevor Tests auf ihre Ergebnisse bauen; sie liegen in einem Checkpoint, weil der Operator das Gateway und TWS dafür ohnehin öffnet. Phase 5 sendet dabei **nie** eine Order.

1. **SC3 (D-06):** In TWS Paper `DAY`-Limit-Order weit vom Markt anlegen, `KILL` anlegen (gültige `RELEASE` muss vorhanden sein, sonst endet der Lauf aus dem falschen Grund mit Exit 4), `execute` starten. Belegen: Exit 4, Order storniert (TWS und `open_orders`), Log `GLOBAL_CANCEL_SENT count=1`, `kill_cancel` und Schalterzustand im Ledger. „Read-Only API" am Gateway **aus** (A1, Pitfall 11).
2. **Rohform nach dem Storno (A2):** `order_history()` einmal gegen das Gateway laufen lassen und die Rohausgabe von `reqCompletedOrders(apiOnly=False)` (Status, `orderRef`, `permId`, `filledQuantity`) und `reqExecutions` im Befund festhalten.
3. **`orderRef` mit `|` (A3):** einen `whatIf` mit `orderRef="2026-10-09|AAPL"` absetzen; Annahme und Echo des `orderRef`/`account` prüfen (A5). Ein Fehlschlag ändert nur den Trenner in `decision_key` (`_`).
4. **Aufräumen:** `KILL` entfernen, Schalterstand „Read-Only API" im Protokoll vermerken, bestehenden State-Ordner nicht mit Testdateien vermischen.

Ergebnis in `.planning/ibkr-konto-befund.md` als neuer datierter Abschnitt (Muster der Phase-4-Messung), Tests auf die gemessenen Werte stützen.

## Security Domain

`security_enforcement` ist in `.planning/config.json` nicht gesetzt (nur `workflow._auto_chain_active`); der Abschnitt gilt als aktiviert. Phase 5 ist selbst eine Sicherheitsphase (Fail-closed-Sicherungen für Kapitalwirkung); web-typische Kategorien greifen nicht.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein (kein Benutzer-Login im Ausführer; Gateway-Login ist Operator-Sache) | — |
| V3 Session Management | nein | — |
| V4 Access Control | ja (Freigabe/Kill als Zugriffsentscheidung über Handelsrecht) | Fail-closed-Schalter, Konto-Bindung (D-02), Socket-Sperre im Adapter |
| V5 Input Validation | ja (RELEASE-Datei, Ledger-Zeilen, Broker-Antworten) | strenges Parsen mit exakter Schlüsselmenge, Typ- und Formprüfung, Größenlimit, kein `eval`, `json` aus der Standardbibliothek |
| V6 Cryptography | nein (keine Kryptografie nötig; `RELEASE` ist kein Geheimnis und nicht signiert, siehe Hinweis) | — |
| V7 Error Handling/Logging | ja (Schalterzustand und jede Entscheidung protokolliert, keine Secrets im Log) | `ibkr-state=`-Logzeilen, Ledger; Zugangsdaten werden nirgends kopiert (bestehende Regel) |
| V12 Files | ja (State-Ordner außerhalb Git, Dateiformat, Pfade) | `os.stat`/`open` mit expliziter Fehlerbehandlung, kein Pfad aus Benutzereingabe außer den bestehenden `--`-Optionen |

Hinweis: `RELEASE` und `KILL` sind lokale Dateien eines Ein-Operator-Systems ohne Manipulationsschutz. Wer Schreibrechte auf `%LOCALAPPDATA%` hat, kann die Freigabe setzen; das ist hier akzeptiert, weil derselbe Benutzer auch das Gateway bedient. Eine Signatur würde nur eine Illusion von Schutz liefern [ASSUMED].

### Known Threat Patterns for diesen Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Fail-open durch verschluckten Fehler (`exists()`, `except Exception`) | Elevation/Tampering | `os.stat` mit drei Zuständen; jede nicht erwartete Ausnahme in der Schalterprüfung ist `unreadable` |
| Doppelorder durch Absturz zwischen Senden und Aufschreiben | Tampering | Write-Ahead mit `fsync` **vor** dem Placer, Reconciliation über drei Quellen |
| Doppelorder durch zweite Instanz | Tampering | `locked(wait=False)` auf dem echten Ledger-Pfad, `OSError` = nicht ausführen |
| Storno fremder Orders durch Bug | Denial of Service | Einmal-Permit + Kill-Beleg + Einzelstelle; nur positive `KILL`-Datei löst es aus |
| Manipulierte/verwechselte `orderRef` (nicht eindeutig bei IBKR) | Spoofing | Abgleich zusätzlich auf `conId`, Seite, Menge; Kollision → Exit 6 |
| Trocken-Eintrag im echten Ledger | Tampering | getrennte Datei, `mode`-Feld als Gegenprobe, Exit 6 bei Mischung |
| Ledger/State in einem Git-Baum (Publikation von Positionsdaten) | Information Disclosure | Laufzeitprüfung des State-Ordners, Wächtertest, `.gitignore` bleibt unberührt |
| Schalter im Log offengelegt | Information Disclosure | nur Zustand und Konto-ID loggen (Konto-ID steht ohnehin im Handbuch); keine Zugangsdaten |

## Operator-WIP und Wechselwirkungen (nur zur Kenntnis, nichts daran planen)

Uncommittet: `scripts/ibkr_market_data.py`, `tests/test_ibkr_market_data.py` (neu), Änderungen an `scripts/IBKR_EXECUTION.md` und `tests/test_ibkr_isolation.py`. Der Stream läuft als **eigene** `IbkrBroker`-Sitzung mit clientId `20002`, im selben Adapter, also hinter derselben Schreibsperre und demselben Paper-Guard [VERIFIED: `ibkr_market_data.py`].

Wechselwirkungen mit Phase 5:

- **`cancel_all` ist Methode der Klasse `IbkrBroker`**, die auch der Stream instanziiert. Technisch könnte also auch die Stream-Sitzung stornieren (und `reqGlobalCancel` wirkt clientübergreifend). Gegenmaßnahmen im Plan: Kill-Beleg als Pflichtargument, Einmal-Permit je Sitzung, und ein Wächtertest, der `cancel_all`/`reqGlobalCancel` in `ibkr_market_data.py` verbietet.
- **REQ-IBKR-68/`test_execution_path_does_not_load_the_market_data_session`:** gilt für die neuen Module mit; sie dürfen den Stream nicht nennen.
- **`WINDOW_BENIGN_CODES`/`INFO_CODES` sind geteilt.** Phase 5 ändert sie nicht; die offene Frage zu 2103 (Deferred) bleibt dem Stream-Strang überlassen.
- **Handbuch:** Der Operator hat einen Absatz zu clientId 20002 ergänzt. Phase 5 ergänzt `IBKR_EXECUTION.md` an **anderen** Stellen (RELEASE/KILL, `execute`, Exit-Tabelle); vor dem Schreiben neu lesen (Parallelarbeit).
- **`tests/test_ibkr_isolation.py`:** Der Operator hat Tests am Dateiende ergänzt; Phase 5 ändert Tests in der Mitte (öffentliche Methoden, Handbuch). Konfliktarm, aber vor jedem Bearbeiten neu lesen.

## Sources

### Primary (HIGH confidence)
- Repo-Dateien dieser Sitzung gelesen: `scripts/ibkr_executor.py`, `scripts/ibkr_broker.py`, `scripts/ibkr_decision.py`, `scripts/ibkr_contracts.py`, `scripts/ibkr_market_data.py`, `tradingagents/dataflows/files.py`, `tests/ibkr_fakes.py`, `tests/test_ibkr_preview.py`, `tests/test_ibkr_isolation.py`, `tests/conftest.py`, `.planning/{ROADMAP,REQUIREMENTS,STATE,ibkr-konto-befund}.md`, `05-CONTEXT.md`, `04-VERIFICATION.md`, `04-VALIDATION.md`, das Jev-Todo.
- Installierte `ib_async` 2.1.0 (`ib.py:857, :929-:972, :2263-:2290`, `client.py:726, :980, :1157`, `wrapper.py:668-733, :800-868`, `objects.py:54-95`, `order.py:38, :147, :238`) — Quelle der gepinnten Bibliothek, VERIFIED.
- Python-Doku `os.path.exists` (docs.python.org/3/library/os.path.html) — Rückgabe `False` bei fehlender Berechtigung für `os.stat()`.
- Eigene Läufe dieser Sitzung: `locked(..., wait=False)` verschachtelt (Windows → `False`), fehlendes Verzeichnis (`FileNotFoundError`), `inspect.getsource(Path.exists)` (3.13.13), 424 Tests grün.

### Secondary (MEDIUM confidence)
- `.planning/ibkr-konto-befund.md` — Messungen vom 2026-10-11/12 (321, 10349, `reqCompletedOrders → 0`, `reqExecutions → 0`, `warningText=''` bei geschlossener Börse); belastbar, aber ohne Inhalt für Completed-Orders/Executions und ohne Messung von 58.

### Tertiary (LOW confidence)
- Verhalten von Windows PowerShell 5.1 beim Schreiben von Dateien (UTF-16 bzw. BOM) — Trainingswissen, nicht gemessen [ASSUMED]; der Handbuch-Einzeiler ist vor der Aufnahme auszuführen.
- Dateisystem-Dauerhaftigkeit von `fsync` auf neu angelegten Dateien unter Windows [ASSUMED].

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — keine neue Abhängigkeit, alles am Repo und an der installierten Bibliothek geprüft.
- Architecture: HIGH — folgt den vorhandenen Mustern (bibliotheksfreie Module, Adapter-Sperre, `_read`-Fenster); die offenen Punkte sind Entscheidungsfragen, keine technischen Unbekannten.
- Pitfalls: HIGH für die am Code und per Skript belegten (1, 3, 4, 7-10), MEDIUM für 2 (PowerShell) und 5/11 (Gateway-Verhalten von 58 ungemessen).
- Gateway-Fakten (A1-A5): MEDIUM bis LOW bis zum Operator-Checkpoint.

**Research date:** 2026-10-16
**Valid until:** 2026-11-15 (stabil; das Gateway läuft laut Befund am 2026-12-15 ohne Upgrade aus, das betrifft Phase 8, nicht diese Phase). Verfällt früher, falls `ib_async` oder der Adapter-Zuschnitt von Phase 4 sich ändern.
