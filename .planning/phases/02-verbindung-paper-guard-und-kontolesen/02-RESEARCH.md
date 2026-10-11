# Phase 2: Verbindung, Paper-Guard und Kontolesen — Research

**Recherchiert:** 2026-10-11 (HEAD `8f4b6ea`, Gate G1 vom Operator geschlossen)
**Domäne:** TWS-API-Anbindung über `ib_async` 2.1.0 an IB Gateway (Paper `DUQ634065`), lokales Operator-Tooling unter `scripts/`
**Konfidenz gesamt:** HOCH für das Verhalten von `ib_async` (am installierten 2.1.0-Quelltext geprüft) und für die Auflösung der Abhängigkeiten (gemessen); MITTEL für die Wahl des Liveness-Probes und für das Gateway-Verhalten bei aktivem Read-Only

## Summary

Phase 2 baut zwei Python-Dateien unter `scripts/` (Adapter + Kommando), ein optionales Extra `ibkr` in `pyproject.toml`, eine optionale `--portfolio`-Option in `scripts/daily_paper_run.py` und einen Anfang des Betriebshandbuchs `scripts/IBKR_EXECUTION.md`. Fertig ist die Phase, wenn ein Kommando gegen das laufende Gateway Positionen und Cash liest, den Paper-Guard `managedAccounts() == ["DUQ634065"]` durchsetzt und ein `PortfolioContext`-JSON schreibt. Fehlerfälle enden mit benannten Exit-Codes und einer UTF-8-Logdatei, nie mit einem Traceback.

Drei Befunde aus dem Quelltext verändern den Plan gegenüber der Vorrecherche. **Erstens: `readonly=True` ist in `ib_async` 2.1.0 keine Schreibsperre.** Der Parameter unterdrückt beim Verbinden nur den Abgleich offener und abgeschlossener Orders (`ib.py:2057-2063`). `IB.placeOrder` prüft ihn nie (`ib.py:780-813`). Weil der Operator den Schreibschutz im Gateway nach dem 321-Nachweis wieder ausgeschaltet hat, gibt es zurzeit **gar keine** Schreibsperre — weder im Gateway noch im Client. Die Phase muss die Sperre deshalb selbst herstellen: Der Adapter bekommt in Phase 2 keine Schreibmethode, und im Read-Only-Betrieb werden die Schreibaufrufe auf `ib.client` durch eine Sperrfunktion ersetzt, die eine Ausnahme wirft (am Paket nachgewiesen). Zusätzlich empfiehlt sich ein blockierender Operator-Checkpoint, der vor der ersten echten Verbindung den Read-Only-Schalter im Gateway wieder einschaltet. **Zweitens: Erfolgskriterium 6 ist so, wie es formuliert ist, nicht erfüllbar.** Ohne den eigenen `tzdata`-Pin löst die Umgebung trotzdem auf, weil `ib_async` 2.1.0 die Obergrenze `tzdata<2026.0` selbst in seinen Metadaten trägt. Reproduzierbar scheitert die Kombination aus `ib_async==2.1.0` und dem aktuellen `tzdata>=2026.1` (gemessen mit `pip` und `uv`). **Drittens: Der Report enthält den Portfolio-Block heute gar nicht.** `PortfolioContext.render()` landet nur in den Prompts (`trading_graph.py:327`), nicht in `complete_report.md` (`reporting.py:20-46`). Erfolgskriterium 7 braucht deshalb eine kleine, zusätzliche Änderung an der Report-Erzeugung.

Dazu kommen zwei Umgebungsfallen, beide gemessen. Das Haupt-`.venv` kann die Tests derzeit nicht ausführen (`yfinance` 0.2.63, `AttributeError: module 'yfinance' has no attribute 'config'` schon beim Laden der Tests), und `ib_async` ist dort nicht installiert. Außerdem schützt die Netzsperre der Tests (`tests/conftest.py:_no_network`) unter Windows **nicht** vor einer asyncio-Verbindung zu `127.0.0.1`, sobald die Event-Loop existiert. Ein Test mit echtem `IB.connect` könnte also das echte Paper-Gateway auf 7497 erreichen. Gleichzeitig scheitert das Anlegen einer *neuen* Event-Loop unter dieser Sperre unter Windows an `socket.socketpair()`.

**Hauptempfehlung:** Adapter `scripts/ibkr_broker.py` (einzige Datei mit `ib_async`, Import erst bei Bedarf, injizierbare `IB`-Fabrik, öffentlich in Phase 2 nur `connect`/`positions`/`health`) und Kommando `scripts/ibkr_executor.py account --out <pfad>`. Getestet wird ausschließlich gegen ein Fake-`IB`. Vor der ersten echten Verbindung steht ein Operator-Checkpoint: Read-Only im Gateway an und `.venv` aufgefrischt.

<user_constraints>
## User Constraints (keine CONTEXT.md vorhanden — abgeleitet aus REQUIREMENTS.md / ROADMAP.md)

Für Phase 2 existiert keine `02-CONTEXT.md` (`/gsd:discuss-phase` wurde nicht gefahren). Bindend sind deshalb die gesetzten Operator-Entscheidungen aus `REQUIREMENTS.md` und die Abgrenzung aus `ROADMAP.md`; alles andere ist Ermessen des Planers.

### Gesetzte Entscheidungen (REQUIREMENTS.md, „nicht erneut aufzurollen")
1. **Orders werden direkt platziert.** Es gibt kein vorgeschaltetes Lese-Projekt. Konto-/Positionslesen und Symbol-Auflösung sind technische Voraussetzungen *innerhalb* der ersten Phasen dieses Meilensteins, kein eigener Meilenstein.
2. **Entkoppelte Architektur.** Die Analyse bleibt in GitHub Actions (`.github/workflows/daily-paper-run.yml`) und schreibt wie heute auf `paper-log`. Ein **lokaler** Prozess liest von dort und führt gegen das Gateway aus. Die CI erhält **keine** IBKR-Credentials.
3. **Vier Leitplanken sind Pflicht** (Phase 5, hier nicht berührt).
4. **Credentials liegen lokal** in der gitignorierten `.env`: `IBKR_USERNAME`, `IBKR_PASSWORD`, `IBKR_ACCOUNT_ID=DUQ634065`, `IBKR_TRADING_MODE=paper`, `IBKR_HOST=127.0.0.1`, `IBKR_PORT` — **gemessen und korrigiert: `IBKR_PORT=7497`** (Befund Frage 2; IB Gateway auf dem TWS-Paper-Port).
- Stack: IB Gateway Paper + `ib_async` 2.1.0 gepinnt (BSD-2-Clause, kein `ibapi`). `ib_async.Watchdog` ist nicht nutzbar (IBC-Controller Pflicht, IBC archiviert) → eigene Liveness-Logik.

### Gemessene Fakten (ibkr-konto-befund.md — überstimmen jede Recherche)
- `managedAccounts()` liefert wörtlich `['DUQ634065']`. Der Port (7497) ist reine Konfiguration und keine Paper-Garantie.
- Basiswährung des Kontos ist **EUR**, die Ticker notieren in USD. Positionen: 0. `TotalCashValue=1005459.44 EUR`, `AvailableFunds=NetLiquidation=1005888.32 EUR`, `BuyingPower=6705922.13 EUR`.
- `ineligibilityReasonList` gibt es in 2.1.0 nicht (betrifft Phase 3).
- Der Read-Only-Marker ist **321** und nicht 10015 (Gateway 10.50.1, Order-Status `ValidationError`). Read-Only ist **keine Voreinstellung**. Der Operator hat den Schreibschutz nach dem Nachweis um 20:27 **wieder deaktiviert**.
- Bei aktivem Read-Only „blieb ein Sondierungslauf über die Lese-Aufrufe ohne Antwort hängen" → **jeder API-Aufruf braucht ein Timeout**.
- Code 2172: Gateway-Version läuft am 2026-12-15 aus (Phase 8, hier nur erwähnt).

### Was diese Phase NICHT tut (ROADMAP.md, verbindlich)
- Keine Order und kein `whatIf`; die Verbindung läuft durchgehend mit `readonly=True`.
- Keine Symbol-Auflösung über das hinaus, was zum Lesen der Positionen nötig ist (die eigene Auflösungskette ist Phase 3).
- Kein Lesen von `paper-log`, keine Entscheidungsübernahme.
- **Keine Änderung am CI-Produktivpfad.** Das Portfolio-JSON wird in dieser Phase nur lokal übergeben; die Verdrahtung in den täglichen Lauf braucht den Veröffentlichungsbranch und passiert in Phase 7.

### Ermessen des Planers (Empfehlungen unten)
Ort und Namen der Module, `clientId`-Wert, Cash-Tag, Probe-Request, Timeouts, Ort der Logdatei, ob `ib_async` in einen CI-Job kommt, wie Kriterium 7 in den Report gelangt.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Beschreibung (gekürzt) | Was die Recherche dafür liefert |
|----|------------------------|----------------------------------|
| REQ-IBKR-03 | Nur IB Gateway Paper auf `.env`-Host/Port, Paper-Username, `readonly=True` bis zur ersten Order | `connectAsync(host, port, clientId, timeout, readonly=True, fetchFields=StartupFetchNONE)`. **`readonly=True` sperrt nicht** → Sperre in der Client-Schicht + Operator-Checkpoint (§ Architektur, Muster 2) |
| REQ-IBKR-04 | Paper-Guard: verwaltete Konten **genau** `{"DUQ634065"}`, sonst sofort trennen, Exit 8 | `ib.managedAccounts()` ist nach dem Handshake gefüllt (`client.py:398-410`). Der Sollwert ist eine **Konstante im Code**, nicht der `.env`-Wert. Der Guard ist die erste Anweisung nach `connectAsync` |
| REQ-IBKR-05 | Credentials nur lokal, CI credential-frei | Gemessen: `git ls-files .env` ist leer, `.gitignore:151`. In `.github/workflows/*.yml` steht keine IBKR-Referenz (grep). Ein Wächtertest hält beides fest |
| REQ-IBKR-06 | `ib_async==2.1.0` + `tzdata<2026.0` gepinnt, mit Kommentar | Extra `ibkr` in `pyproject.toml`. Positiv- und Negativnachweis gemessen (§ Standard Stack). **Kriterium 6 muss umformuliert werden** |
| REQ-IBKR-07 | Ein Adapter, ≤ 10 Methoden, einziger `ib_async`-Importort | `scripts/ibkr_broker.py`, Import erst bei Bedarf. AST-Test nach dem Muster von `tests/test_layering.py` plus `git grep` nur über `*.py` |
| REQ-IBKR-08 | Fester, dokumentierter `clientId`; Order-IDs ab `nextValidId` | `ib_async` übernimmt `nextValidId` beim Handshake (`client.py:401-404`, `updateReqId`). Empfohlener `clientId` außerhalb des Bereichs 0..9999, den `ai_tradex` belegt |
| REQ-IBKR-09 | Benannte Betriebszustände; Liveness über echte Probe-Antwort | Zuordnungstabelle Code → Zustand. 502/504/507 erzeugt `ib_async` **nicht**, sie müssen aus Exceptions abgeleitet werden. Probe: `reqContractDetails(conId=265598)` mit Timeout |
| REQ-IBKR-11 | Kontolesen → `PortfolioContext`-JSON, das `load_portfolio()` liest | Schema `portfolio.py:23-64`; Abbildung `Position`/`AccountValue` → `PortfolioContext`; `--portfolio` in `daily_paper_run.py` |
| REQ-IBKR-12 | Ist-Position bei jedem Lauf frisch vom Broker | `reqPositionsAsync()` bei jedem Aufruf, nie `ib.positions()` (Cache) und nie das geschriebene JSON zurücklesen |
| REQ-IBKR-55 | Disjunkte Exit-Codes 0/1/2/3/4/5/6/7/8/20 + UTF-8-Logdatei mit absolutem Pfad | Alle zehn Codes jetzt definieren, in Phase 2 benutzt: 0, 1, 3, 8, 20. Logdatei außerhalb des Arbeitsbaums |
</phase_requirements>

## Project Constraints (aus CLAUDE.md / AGENTS.md / Memory)

- `CLAUDE.md`/`AGENTS.md` nennen nur Graphify und Serena als **Navigationswerkzeuge**. Beide sind kein Build- oder Merge-Gate; Code-Vorgaben stehen dort keine.
- Sprache: `.planning/` auf Deutsch; Code, Commits und CHANGELOG auf Englisch (Memory `feedback_antworten_auf_deutsch`).
- Veröffentlicht wird nur über den Remote `fork` (stevexyz2003/TradingAgents); `origin` ist pull-only. Committet wird nur auf Anweisung.
- Der Operator arbeitet parallel in denselben Dateien (Memory `feedback_operator_coworks_in_parallel`; beobachtet: `8f4b6ea` kam während dieser Recherche). Der Plan sollte große Edits über viele Dateien vermeiden und vor jedem Edit neu lesen.
- Ruff (`pyproject.toml`): `line-length = 100`, `target-version = "py311"`, `select = ["E","W","F","I","B","UP","C4","SIM"]`, CI `ruff>=0.16` über das ganze Repo. Lokales `.venv` hat ruff 0.15.12 (zu alt).
- UTF-8 überall explizit (`encoding="utf-8"`; #543/#550/#576), auf Windows Pflicht.
- Tests: `pytest`, Marker `unit`/`integration`/`smoke`, Default `-m "not integration"`; Skripte werden per `importlib.util.spec_from_file_location` geladen (`tests/test_daily_paper_run.py:22-31`). Netzwerk ist in Tests gesperrt (`conftest.py:_no_network`).

## Architectural Responsibility Map

| Fähigkeit | Primäre Schicht | Sekundäre Schicht | Begründung |
|---|---|---|---|
| Socket/API-Handshake, `nextValidId`, `managedAccounts` | Broker-Adapter (`scripts/ibkr_broker.py`) | `ib_async` | Einzige Stelle mit Bibliothekskontakt (REQ-07) |
| Paper-Guard (Vergleich gegen Konstante) | Adapter, unmittelbar nach `connect` | Kommando (Exit 8) | Der Guard muss vor jedem weiteren Request laufen; die Bedeutung des Exit-Codes gehört dem Kommando |
| Schreibsperre im Read-Only-Betrieb | Adapter (Ersetzen der Methoden auf `ib.client`) | Gateway-Einstellung „Read-Only API" (Operator) | Der Client-Parameter `readonly` sperrt nicht; das Gateway ist zurzeit offen |
| Fehlercode → benannter Zustand, Liveness | Adapter (`errorEvent`-Handler, `health()`) | Kommando (Exit 3 + Logzeile) | Die Codes kommen aus `ib_async`-Events und -Exceptions |
| `.env` lesen, Konfig validieren, Exit 1/20 | Kommando (`scripts/ibkr_executor.py`) | — | Darf ohne `ib_async` laufen; Exit 20 muss ohne Bibliothek testbar sein |
| Snapshot → `PortfolioContext` → JSON (atomar) | Kommando | `tradingagents.portfolio` (Schema) | Die Bibliothek bleibt broker-neutral (`portfolio.py:9-11`) |
| Portfolio in Analyse + Report | `scripts/daily_paper_run.py` (`--portfolio`) | `tradingagents/reporting.py` (Header-Block) | Der Report zeigt den Block heute nicht |
| CI-Isolation (keine IBKR-Secrets) | Tests (Wächter über `.github/workflows`) | `.gitignore` | Nachweis von REQ-05 |

## Standard Stack

### Core
| Bibliothek | Version | Zweck | Warum |
|---|---|---|---|
| `ib_async` | **==2.1.0** (PyPI-Stand: letzte Version, `pip index versions` 2026-10-11) | TWS-API-Client | Gesetzte Entscheidung; BSD (`pip show`: License BSD), Requires `aeventkit, nest_asyncio, tzdata` [VERIFIED: pip index + installiertes Paket in `ai_tradex/.venv`] |
| `tzdata` | **>=2025.2,<2026.0** (löst auf **2025.3** auf; PyPI aktuell 2026.5) | Zeitzonendaten, von `ib_async` gedeckelt | Spiegelt die Obergrenze aus `ib_async`; aktueller Stand ist ausgeschlossen [VERIFIED: pip index, uv pip compile] |
| `pydantic` | vorhanden (Projektabhängigkeit) | `PortfolioContext`-Validierung | Schema existiert (`tradingagents/portfolio.py`) |
| `python-dotenv` | `>=1.0.0` (vorhanden) | `.env` explizit per Pfad lesen (`dotenv_values`) | Schon Projektabhängigkeit |

### Supporting
| Bibliothek | Zweck | Wann |
|---|---|---|
| `logging` (stdlib) mit `FileHandler(..., encoding="utf-8")` | Logdatei mit absolutem Pfad | REQ-55; `RotatingFileHandler` reicht |
| `asyncio` (stdlib) | `wait_for`-Timeouts um jeden Request | Pflicht laut Befund („jeder API-Aufruf braucht ein Timeout") |

### Alternatives Considered
| Statt | Möglich | Abwägung |
|---|---|---|
| Extra `ibkr` | `ib_async` in die Kern-`dependencies` | Würde jede Upstream-/CI-Installation an `tzdata<2026` ketten. **Abgelehnt** — Extra ist richtig |
| `reqContractDetails`-Probe | `reqCurrentTime` | Laut IBKR-Doku prüft `get_current_time` „the connection with the application" (also TWS/Gateway) und nicht die Server-Session. Taugt nicht als Session-Probe [CITED: interactivebrokers.com/docs/tws-api/sync-doc/current-time.md] |
| `reqContractDetails`-Probe | Historische Daten EURUSD (Muster des Watchdog, `ibcontroller.py:342`) | Braucht Marktdaten-/HMDS-Berechtigung, die am Paper-Konto nicht gemessen ist; Phase 3 klärt Marktdaten erst |

**Installation (lokal, dieses Gerät):**
```bash
# uv: --system-certs umgeht den UnknownIssuer-Fehler (gemessen 2026-10-11, besser als UV_OFFLINE=1)
uv pip install --system-certs --python .venv/Scripts/python.exe -e ".[dev,ibkr]"
# pip nutzt den System-Truststore schon (gemessen: pip 25.1.1 erreicht PyPI)
.venv/Scripts/python.exe -m pip install -e ".[dev,ibkr]"
```

**Deklaration (Vorschlag für `pyproject.toml`, `[project.optional-dependencies]`):**
```toml
# IBKR paper execution (local operator tooling under scripts/, milestone M2).
# Optional so the core install and upstream CI stay free of it: pip install ".[ibkr]".
ibkr = [
    # Pinned exactly: single maintainer, main idle since 2025-12-06; the adapter
    # (scripts/ibkr_broker.py) is the only module that imports it.
    "ib_async==2.1.0",
    # ib_async 2.1.0 itself declares tzdata>=2025.2,<2026.0 while tzdata is at
    # 2026.5 (2026-10-03). Stated here so the cap is visible where it bites:
    # any tzdata>=2026 requirement elsewhere makes this extra unresolvable.
    "tzdata>=2025.2,<2026.0",
]
```

### Gemessener Auflösungsnachweis (Kriterium 6)

| Anforderung | Werkzeug | Ergebnis |
|---|---|---|
| `ib_async==2.1.0` allein | `uv pip compile --system-certs --python-version 3.13` | löst auf, `tzdata==2025.3 # via ib-async` |
| `ib_async==2.1.0` + `tzdata>=2025.2,<2026.0` | uv | löst auf, `tzdata==2025.3` |
| `ib_async==2.1.0` + `tzdata>=2026.1` | uv | **„No solution found … ib-async==2.1.0 depends on tzdata>=2025.2,<2026.0 … requirements are unsatisfiable"** |
| dasselbe | `pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"` | **`ERROR: ResolutionImpossible`** |
| ganzes Projekt (`tradingagents @ file:///…`) + `ib_async==2.1.0` | uv, Py 3.11 / 3.13 / 3.14, win + linux | löst überall auf, `pandas==3.0.6`, `tzdata==2025.3` |

**Konsequenz:** Das Kriterium „ohne den `tzdata`-Pin bricht die Auflösung" ist **messbar falsch**. Ohne den Pin löst es weiter auf, weil die Obergrenze aus den Metadaten von `ib_async` kommt. Ehrlich und reproduzierbar ist dieser Negativnachweis: „`ib_async==2.1.0` **zusammen mit dem aktuellen `tzdata` (>=2026.1)** ist unauflösbar." Der Plan sollte dafür ein Prüfskript oder einen Testbefehl vorsehen, und der Operator sollte das Kriterium in ROADMAP.md umformulieren (offene Frage 1).

## Package Legitimacy Audit

| Paket | Registry | Alter | Downloads | Quell-Repo | slopcheck | Entscheidung |
|---|---|---|---|---|---|---|
| `ib_async` | PyPI | Versionen 1.0.0 … 2.1.0; 2.1.0 vom 2025-12-08 (Vorrecherche) | nicht erhoben | github.com/ib-api-reloaded/ib_async | **[ERR] — Registry nicht erreichbar (SSL)** | [ASSUMED] → erlaubt; schon in Phase 1 auf diesem Gerät benutzt (Sonde, `ai_tradex/.venv`) |
| `tzdata` | PyPI | 2020.1 … 2026.5 | nicht erhoben | github.com/python/tzdata | **[ERR] — Registry nicht erreichbar (SSL)** | [ASSUMED] → erlaubt; schon transitive Abhängigkeit (`.venv` hat 2025.2) |

**Wegen [SLOP] entfernt:** keine. **Als [SUS] markiert:** keine.
*slopcheck 0.6.1 ließ sich installieren (per `py -3.13 -m pip install --user` in die System-Python), erreichte PyPI aber wegen `CERTIFICATE_VERIFY_FAILED` nicht. Beide Pakete sind deshalb protokollgemäß [ASSUMED]. Abgefedert ist das Risiko: Beide Namen sind über `pip index versions` auf PyPI bestätigt, `ib_async` 2.1.0 lief am 2026-10-11 gegen das Gateway, und `tzdata` ist ohnehin schon installiert. Ein `postinstall`-Mechanismus existiert bei Python-Wheels nicht. Der Planer kann die Installation hinter den Operator-Checkpoint aus Wave 0 legen; einen eigenen Checkpoint braucht sie nicht.*

## Architecture Patterns

### System Architecture Diagram

```
 Operator / (Phase 8: Task Scheduler)
        │  python scripts/ibkr_executor.py account --out <abs.pfad> [--log-file <abs.pfad>]
        ▼
 ┌──────────────────────────── ibkr_executor.py (kein ib_async) ───────────────────────────┐
 │ 1 Logging einrichten (UTF-8, absoluter Pfad, erste Zeile = eigener Pfad)                │
 │ 2 .env per festem Pfad lesen ──fehlt/unlesbar/leer──────────────────────────► Exit 20   │
 │ 3 Konfig prüfen (Port int, ACCOUNT_ID == Konstante, MODE == paper) ──falsch──► Exit 1   │
 │ 4 Adapter laden (Lazy-Import) ──ImportError ("pip install .[ibkr]")─────────► Exit 1    │
 └───────────────┬─────────────────────────────────────────────────────────────────────────┘
                 ▼
 ┌──────────────────────────── ibkr_broker.py (einziger ib_async-Nutzer) ──────────────────┐
 │ connect():  errorEvent abonnieren → connectAsync(readonly=True, fetchFields=NONE,       │
 │             timeout) ──ConnectionRefused/OSError──► state GATEWAY_UNREACHABLE (502) ─┐  │
 │                        ──TimeoutError (+326 gesehen?)──► CONNECT_TIMEOUT / CLIENT_ID… ─┤  │
 │             Schreibsperre auf ib.client setzen                                         │  │
 │             PAPER-GUARD: managedAccounts() == ["DUQ634065"] ?                          │  │
 │                 nein ──► disconnect() ──► AccountGuardViolation ─────────────────────┐ │  │
 │ health():   connected ∧ ¬link_lost(1100) ∧ Probe reqContractDetails(conId) < T   │ │  │
 │                 nein ──► state SESSION_DEAD / PROBE_TIMEOUT ───────────────────────┤ │  │
 │ positions():wait_for(reqPositionsAsync) + wait_for(accountSummaryAsync) → Snapshot │ │  │
 └───────────────┬────────────────────────────────────────────────────────────────────┼─┼──┘
                 ▼                                                                    │ │
 ┌──── ibkr_executor.py ────┐                                                          │ │
 │ Snapshot → PortfolioContext (Konto gefiltert, qty≠0, cash=TotalCashValue/EUR)      │ │
 │ JSON atomar schreiben (tmp + os.replace) → load_portfolio() selbst gegenprüfen     │ │
 │ disconnect() im finally ──► Exit 0                                                 │ │
 └────────────────────────────┘                    Exit 3 ◄────────────────────────────┘ │
                                                   Exit 8 ◄──────────────────────────────┘
        │ (manuell, lokal)
        ▼
 scripts/daily_paper_run.py --portfolio <json> → graph.propagate(..., portfolio=ctx)
        → final_state["portfolio_context"] → reporting._header → complete_report.md (Kriterium 7)
```

### Empfohlene Struktur
```
scripts/
├── ibkr_broker.py        # Adapter: EINZIGE Datei mit "ib_async"; Import erst bei Bedarf; Zustandstabelle; Schreibsperre
├── ibkr_executor.py      # Kommando "account"; Exit-Code-Tabelle (alle 10); .env; Logging; JSON
├── IBKR_EXECUTION.md     # Handbuch (Beginn REQ-60): clientId, Exit-Codes, Read-Only-Zustand, Bedienung
│                         #   ACHTUNG: das Wort "ib_async" hier vermeiden ODER Grep auf *.py beschränken
├── daily_paper_run.py    # + optionales --portfolio (additiv, CI ruft es nicht)
tests/
├── test_ibkr_broker.py   # Fake-IB: Guard, Sperre, Zustände, health, positions-Frische
├── test_ibkr_executor.py # Exit 0/1/3/8/20, Logdatei, kein Traceback, JSON ↔ load_portfolio
├── test_ibkr_isolation.py# AST: ein Importort; ≤10 öffentliche Methoden; CI ohne IBKR; .env untracked
tradingagents/reporting.py # + Portfolio-Block im Header, wenn final_state["portfolio_context"] gesetzt
```
Der Ort `scripts/` folgt dem Muster für Betriebswerkzeuge (`daily_paper_run.py`, `state_maintenance.py`), dem Handbuch-Pfad aus REQ-60 und der Broker-Neutralität der Bibliothek (`portfolio.py:9-11`; MILESTONE.md:113 „kein direkter Live-Order-Flow aus diesem Framework"). Ein einziges Kommando `ibkr_executor.py` mit Unterkommandos hält die Exit-Code-Tabelle an **einer** Stelle, die Phase 4 bis 8 erweitern.

### Muster 1: Adapter mit injizierbarer `IB`-Fabrik und Lazy-Import
**Was:** Auf Modulebene importiert der Adapter `ib_async` nicht. Die Standardfabrik importiert es erst beim Aufruf. Tests übergeben ein Fake.
**Warum:** (a) Kommando und Tests laufen ohne das Extra, auch in der CI-Matrix 3.11–3.14. (b) In Tests wird nie eine echte Verbindung aufgebaut (Sicherheitsbefund unten). (c) Der AST-Test findet den Import trotzdem, denn `ast.walk` erfasst auch Importe innerhalb von Funktionen.
```python
# scripts/ibkr_broker.py  (Skizze, nicht final)
EXPECTED_ACCOUNT = "DUQ634065"          # Konstante — NIE aus .env übernehmen
EXECUTOR_CLIENT_ID = 20001              # siehe "clientId" unten; im Handbuch dokumentiert
PROBE_CON_ID = 265598                   # AAPL, aus dem Konto-Befund
CONNECT_TIMEOUT_S, REQUEST_TIMEOUT_S, PROBE_TIMEOUT_S = 10.0, 10.0, 5.0

def _default_ib_factory():
    from ib_async import IB              # der einzige Importort im Repo
    return IB()

class IbkrBroker:
    def __init__(self, host: str, port: int, *, ib_factory=_default_ib_factory, loop=None): ...
    def connect(self) -> None: ...       # Guard + Schreibsperre, wirft benannte Ausnahmen
    def positions(self) -> "AccountSnapshot": ...   # Bestand + Cash, immer frisch
    def health(self) -> "Health": ...    # echte Probe-Antwort
    def __enter__(self): self.connect(); return self
    def __exit__(self, *exc): self._disconnect()   # privat: zählt nicht zu den ≤10
```
REQ-07 nennt die Ziel-Methodenliste `connect, resolve, is_tradable_now, preview, place, positions, open_orders, executions, cancel_all, health`. Weder `disconnect` noch „account/cash" steht darin. Deshalb: Trennen läuft über `__exit__` bzw. private Methoden, und `positions()` liefert **Bestand und freies Kapital** als einen Snapshot. In Phase 2 sind **nur** `connect`, `positions` und `health` öffentlich. `place`/`preview`/`cancel_all` existieren noch nicht, auch nicht als Stub — dass sie fehlen, ist Teil des Nachweises „kein Platzierungsaufruf".

### Muster 2: Schreibsperre in der Client-Schicht (weil `readonly=True` nicht sperrt)
**Befund [VERIFIED: ib_async 2.1.0 Quelltext]:** `connectAsync` benutzt `readonly` nur, um `reqOpenOrdersAsync`/`reqCompletedOrdersAsync` beim Start wegzulassen (`ib.py:2057-2063`). `IB.placeOrder` (`ib.py:780-813`) schickt ohne jede Prüfung an `client.placeOrder`. Auch `whatIfOrderAsync` läuft über `client.placeOrder` (`ib.py:2204-2212`).
**Muster:** Nach dem Verbinden und vor dem Guard ersetzt der Adapter die Schreibaufrufe auf der Instanz `ib.client`:
```python
class ReadOnlyViolation(RuntimeError):
    """A write call reached the broker client while the session is read-only."""

_WRITE_CALLS = ("placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions")

def _arm_write_barrier(client) -> None:
    def refuse(*_a, **_k):
        raise ReadOnlyViolation("read-only session: write call refused before it reached the gateway")
    for name in _WRITE_CALLS:
        setattr(client, name, refuse)
```
Gemessen am Paket ohne Verbindung (`IB()`): `ib.placeOrder(...)` mit gesetzter `orderId` → `ReadOnlyViolation`, `ib.reqGlobalCancel()` → `ReadOnlyViolation`. Diese Sperre ist **zusätzlich** zum fehlenden Schreib-API und zum Gateway-Schalter gedacht und ersetzt keins von beiden. In Phase 4 braucht `whatIf` genau diesen Pfad; dort wird die Sperre gezielt gelockert (Phase-4-Thema).

### Muster 3: Guard als erste Anweisung nach dem Handshake
- `fetchFields=StartupFetchNONE` (aus `ib_async`) übergeben. Dann fordert `connectAsync` keine Kontoupdates, Executions oder Orders an. **Positionen fordert es trotzdem an**: `reqs["positions"]` hängt nicht an `fetchFields` (`ib.py:2055`). Das ist ein harmloser Lesezugriff vor dem Guard und gehört ins Handbuch.
- Der Handshake gilt erst als fertig, wenn `nextValidId` (Msg 9) **und** `managedAccounts` (Msg 15) eingetroffen sind (`client.py:398-410`). Direkt nach `connectAsync` ist `ib.managedAccounts()` also gefüllt.
- Vergleich: `accounts == [EXPECTED_ACCOUNT]` (exakte Liste, kein Präfix, keine Mengen-Toleranz für Duplikate). Bei Abweichung: sofort `ib.disconnect()`, `AccountGuardViolation(accounts_seen)`, das Kommando endet mit Exit 8. Die gesehenen Konten stehen im Log.

### Muster 4: Jeder Request mit Timeout, innerhalb einer laufenden Loop
- `IB.RequestTimeout` ist per Default `0` = **unbegrenzt warten** (`ib.py:138-141, 271`). Das erklärt den Hänger aus dem Befund.
- `ib_async` legt Futures in Funktionen an, die selbst keine Koroutinen sind (`wrapper.startReq` → `asyncio.Future()`, `wrapper.py:375`). Deshalb jeden Request **innerhalb** einer laufenden Loop erzeugen:
```python
def _call(self, make_awaitable, timeout: float):
    async def runner():
        return await asyncio.wait_for(make_awaitable(), timeout)
    return self._loop.run_until_complete(runner())

# Benutzung: self._call(lambda: self._ib.reqPositionsAsync(), REQUEST_TIMEOUT_S)
```
- Die Loop wird injiziert (`loop=`). In Produktion legt der Adapter sie einmal an. Tests übergeben eine Loop, die vor der Netzsperre entsteht (siehe Pitfall 5).

### Muster 5: Benannte Zustände (REQ-09)
`errorEvent(reqId, errorCode, errorString, contract)` wird **vor** `connectAsync` abonniert (`wrapper.py:1723`). Fehlermeldungen vor dem Handshake (z. B. 326) laufen ebenfalls durch den Decoder (`client.py:412-413`).

| Code | Quelle in `ib_async` | Zustand (Vorschlag) | Wirkung in Phase 2 |
|---|---|---|---|
| 502 | **kein Event** — `ConnectionRefusedError`/`OSError` aus `connectAsync` (`client.py:230-236`) | `GATEWAY_UNREACHABLE` | Exit 3, Logzeile mit „502" und „Gateway nicht erreichbar" |
| 326 | `errorEvent` vor dem Handshake, danach schließt der Gegenpart → `TimeoutError` (`client.py:418-427`: „clientId … already in use?") | `CLIENT_ID_IN_USE` | Exit 3 |
| (keiner) | `TimeoutError` ohne 326 (z. B. Trusted-IP-Ablehnung, hängendes Gateway) | `CONNECT_TIMEOUT` | Exit 3 |
| 504 | **kein Event** — `ConnectionError("Not connected")` aus `getReqId`/`send` (`client.py:162-166`) | `NOT_CONNECTED` | Exit 3 |
| 507 | **kein Event** — `disconnectedEvent`/`apiError` „Peer closed connection" | `SOCKET_EOF` | Exit 3 |
| 1100 | `errorEvent` | `CONNECTIVITY_LOST` → Flag `link_lost=True` | `health()` = ungesund |
| 1101 / 1102 | `errorEvent` (`ib.py:415` abonniert bei 1102 das Account-Summary neu) | `RESTORED_DATA_LOST` / `RESTORED_DATA_KEPT` → `link_lost=False` | — |
| 1300 | `errorEvent` | `PORT_CHANGED` | trennen, Exit 3 |
| 2103 / 2105 | `errorEvent` (in `ib_async` Warnung: 2100–2199) | `FARM_DOWN` | Warnung loggen |
| 2104 / 2106 / 2158 | `errorEvent` (Warnung) | `FARM_OK` | nur INFO, kein Fehler |
| 2110 | `errorEvent` | `SERVER_LINK_BROKEN` | `health()` = ungesund |
| 321 | `errorEvent`; in `ib_async` **Warnung** (`wrapper.py:1609`), setzt `ValidationError`, beendet den Request **nicht** | `READ_ONLY_API` | Warnung; wartende Requests laufen in den Timeout |
| 10015 | `errorEvent` | `TRADING_NOT_ALLOWED` | Tabelle vollständig halten (Recherche-Altlast) |
| 10089 / 10090 | `errorEvent` | `MARKET_DATA_NOT_SUBSCRIBED` | erwarteter Zustand (Phase 3) |
| 2172 | `errorEvent` (Warnung) | `GATEWAY_VERSION_EXPIRING` | Warnung (Phase-8-Hinweis) |

Logformat (Vorschlag, testbar): `ibkr-state=GATEWAY_UNREACHABLE code=502 detail="Gateway nicht erreichbar: 127.0.0.1:7497 (ConnectionRefusedError)"`. Kriterium 3 lässt sich dann über die Zeichenketten `GATEWAY_UNREACHABLE` und `502` und das Fehlen von `Traceback` prüfen.

### Muster 6: Liveness über eine echte Server-Antwort
`health()` ist gesund genau dann, wenn (a) `ib.isConnected()` gilt, (b) seit dem letzten 1100 ein 1101/1102 kam (`link_lost is False`), kein 2110 offen ist **und** (c) `reqContractDetailsAsync(Contract(conId=PROBE_CON_ID))` innerhalb von `PROBE_TIMEOUT_S` **genau einen** Treffer mit `conId == 265598` liefert. Die Probe geht an die Sec-Def-Farm, also an den Server (2158 = „Sec-def data farm connection is OK"). Ein Fehler auf den Request beendet ihn mit leerer Liste (`wrapper.py:1645-1650`, `RaiseRequestErrors=False`) → ungesund. Bleibt die Antwort aus → `TimeoutError` → ungesund. Der Test „Socket oben, Session tot" ist ein Fake mit `isConnected() == True` und einem Future, das nie fertig wird → `health().ok is False`, Zustand `PROBE_TIMEOUT`. [Probe-Wahl: MITTEL — ob die Sec-Def-Antwort bei 1100 ausbleibt, ist nicht gemessen; aussagekräftig ist sie in jedem Fall, weil Fehler und Ausbleiben beide als ungesund zählen.]

### Muster 7: Snapshot → `PortfolioContext`
- `reqPositionsAsync()` liefert die Positionen **aller** Konten und hängt auch Einträge mit `position == 0` an (`wrapper.py:597-618`: das `append` geschieht unabhängig von `posSize`). Gefiltert wird auf `account == EXPECTED_ACCOUNT` und `position != 0`.
- `Position(account, contract, position, avgCost)` (`objects.py:313-317`): für `STK` gilt `ticker = contract.symbol`, `quantity = position`, `average_price = avgCost` (pro Stück, in Kontraktwährung USD). Für Nicht-`STK` (nicht erwartet, Allow-List erst Phase 3): `ticker = localSymbol or symbol`, `average_price = None` (avgCost enthält dort den Multiplikator), plus eine Warnung mit `secType`.
- Cash: aus `accountSummaryAsync(EXPECTED_ACCOUNT)` das `AccountValue` mit `tag == "TotalCashValue"`. Genau eine Zeile wird verlangt; `float(value)`, `currency = value.currency` (gemessen: `EUR`). **Nicht** `BuyingPower` (Margin-Hebel, gemessen 6,7 Mio.). `AvailableFunds`/`NetLiquidation` gehen nur ins Log. [Wahl `TotalCashValue` vs. `AvailableFunds` = Annahme A3]
- **Währung:** `PortfolioContext` hat genau **ein** `currency`-Label für Cash und Preise (`portfolio.py:31`). Das Cash steht in EUR, die Durchschnittspreise in USD. `render()` hängt die Währung nur an die Cash-Zeile (`portfolio.py:46-47`); die Ausgabe bleibt damit korrekt beschriftet. Umgerechnet wird in Phase 2 **nicht** — die FX-Frage gehört zur Mengenrechnung in Phase 4 (Befund Frage 3). Ins Log kommt eine Warnung, wenn eine `STK`-Position eine andere Währung als das Cash hat.
- JSON: `PortfolioContext(...).model_dump_json(indent=2)`, **atomar** (`tmp` im selben Verzeichnis + `os.replace`), danach `load_portfolio(out)` als Gegenprobe im selben Lauf (Kriterium 1). Zusatzfelder (`as_of`, `account`) würde `load_portfolio` stillschweigend verwerfen (Pydantic-Default `extra="ignore"`, kein `model_config` in `portfolio.py`). Empfehlung: **JSON rein im Schema** halten, Herkunft (`as_of` UTC, Konto, `serverVersion`) ins Log.
- REQ-12: `positions()` fragt **jedes Mal** neu (`reqPositionsAsync`), liest nie `ib.positions()` (Cache) und nie eine vorhandene JSON-Datei. Ein Test zählt die Aufrufe des Fakes.

### Muster 8: `--portfolio` im Paper-Lauf + Block im Report (Kriterium 7)
- `daily_paper_run.py`: optionales `--portfolio PATH`. `load_portfolio()` wird **vor** dem Graph-Bau aufgerufen; ein `ValueError` dort ergibt `EXIT_CONFIG`. `run_ticker(graph, ticker, trade_date, out_dir, portfolio=None)` ruft `graph.propagate(ticker, trade_date, portfolio=portfolio)` (die Signatur existiert: `trading_graph.py:183`). Ohne die Option verhält sich der Lauf byte-gleich, die CI übergibt sie nicht (`daily-paper-run.yml` bleibt unverändert).
- `tradingagents/reporting.py:_header`: Wenn `final_state.get("portfolio_context")` gesetzt ist, wird der Block nach den Kopfzeilen eingefügt. **Gemessen:** heute steht er weder in `complete_report.md` noch im HTML (`grep portfolio_context` trifft nur `agents/`, `graph/propagation.py`, `agents/state.py`). Das ist eine kleine zusätzliche Änderung an einer Upstream-Datei und bringt Rebase-Kosten. Alternative ohne Upstream-Berührung: Der Block landet in `summary.md`/`summary.json` des Paper-Laufs. Siehe offene Frage 3.

### Anti-Patterns
- **Sollkonto aus `.env` übernehmen:** Ein auf ein Live-Konto `U…` geändertes `IBKR_ACCOUNT_ID` würde den Guard „bestehen". Der Sollwert ist eine Konstante; `.env` muss ihr nur entsprechen (sonst Exit 1).
- **Sich auf `readonly=True` verlassen:** Der Parameter sperrt nichts (Muster 2).
- **Synchrone `ib_async`-Aufrufe ohne Timeout** (`ib.reqPositions()`, `ib.accountSummary()`): Sie warten mit `RequestTimeout=0` unbegrenzt.
- **`reqAllOpenOrders`/`reqCompletedOrders` in Phase 2:** werden nicht gebraucht, und bei aktivem Gateway-Read-Only sind genau sie die wahrscheinlichen Hänger (Pitfall 2).
- **`ib.positions()` (Cache) für die Ist-Position:** verletzt REQ-12.
- **Das Wort `ib_async` in Handbuch, Kommando oder Kommentaren anderer Dateien:** macht den Grep aus Kriterium 4 rot, wenn er nicht auf `*.py` beschränkt ist.

## Don't Hand-Roll

| Problem | Nicht selbst bauen | Stattdessen | Warum |
|---|---|---|---|
| Handshake, `nextValidId`, `managedAccounts` | eigenes Socket-Protokoll | `ib_async` `connectAsync` | Der Handshake wartet schon auf Msg 9 + Msg 15 (`client.py:398-410`) |
| Order-ID-Sequenz | eigener Zähler / hart kodierte IDs | `client.getReqId()` (startet bei `nextValidId`) | REQ-08; `IB.placeOrder` nimmt `order.orderId or getReqId()` (`ib.py:790`). In Phase 6 nie `orderId` selbst setzen |
| Schema-Validierung des Portfolio-JSON | eigene JSON-Prüfung | `load_portfolio()` / `PortfolioContext.model_validate` | Das Schema ist der Vertrag (REQ-11) |
| `.env`-Parsing | eigener Parser | `dotenv.dotenv_values(path)` | Projektabhängigkeit, kennt Quoting/Kommentare |
| Reconnect-/Watchdog-Schleife | — | **in Phase 2 gar nicht** | Ein Lauf = eine Verbindung; die Reconnect-Logik ist Phase 8 |

## Runtime State Inventory

Kein Rename/Refactor — **entfällt**. Einziger Laufzeitzustand, den die Phase berührt: die **Gateway-Einstellung „Read-Only API"**. Sie ist nicht in Git und steht zurzeit auf **aus** (Befund, 20:27). Siehe Checkpoint-Empfehlung.

## Common Pitfalls

### Pitfall 1: Es gibt heute keine Schreibsperre
**Was schiefgeht:** Ein Code-Pfad, der versehentlich `placeOrder` erreicht, platziert wirklich — Phase 1 hat das gezeigt: `orderStatus='PreSubmitted'` bei ausgeschaltetem Read-Only.
**Warum:** Der Gateway-Schalter ist aus, und `readonly=True` sperrt nicht.
**Vermeiden:** (1) Kein Schreib-API im Adapter. (2) Schreibsperre auf `ib.client` (Muster 2). (3) Operator-Checkpoint: Read-Only im Gateway **an**, solange Phase 2 echte Verbindungen fährt. (4) Ein Test belegt, dass kein Aufruf aus `_WRITE_CALLS` passiert.
**Warnsignal:** Im Log steht `orderStatus`/`newOrderEvent`, oder ein Fake meldet einen `placeOrder`-Aufruf.

### Pitfall 2: Hänger bei aktivem Gateway-Read-Only
**Was schiefgeht:** Der zweite Sondierungslauf „blieb ohne Antwort hängen" (Befund).
**Warum (Schluss aus Quelltext und Rohausgabe, MITTEL):** Bei aktivem Read-Only beantwortet das Gateway Order-Abfragen mit 321. `ib_async` stuft 321 als **Warnung** ein und beendet den wartenden Request **nicht** (`wrapper.py:1609-1642`). Ohne Timeout wartet der Aufruf dann ewig. Die „zwei 321 beim Verbinden" passen genau zu `connectAsync` mit `readonly=False`, das `reqOpenOrders` **und** `reqCompletedOrders` schickt (`ib.py:2057-2063`). Die Sonde rief außerdem `reqAllOpenOrders`/`reqCompletedOrders` auf (Befund-Rohausgabe).
**Vermeiden:** `readonly=True` + `StartupFetchNONE` + keine Order-Abfragen in Phase 2 + Timeout um jeden Request. Der erste echte Lauf mit aktivem Read-Only bestätigt dann zugleich, dass Positionen, Account-Summary und Contract-Details nicht betroffen sind.

### Pitfall 3: Fehlercodes, die `ib_async` gar nicht erzeugt
**Was schiefgeht:** Ein Handler, der auf `errorEvent` mit 502 wartet, wartet vergeblich. Stattdessen fliegt eine `ConnectionRefusedError` als Traceback durch.
**Warum:** 502, 504 und 507 sind synthetische Codes des offiziellen `ibapi`-Clients. In `ib_async` 2.1.0 kommen sie nicht vor (`grep` über das Paket: keine Treffer für 502/504/507).
**Vermeiden:** `connect()` fängt `ConnectionRefusedError`/`OSError`/`TimeoutError`/`ConnectionError` und bildet sie auf die Zustände der Tabelle ab.

### Pitfall 4: Tests können das echte Gateway erreichen
**Was schiefgeht:** Ein Test, der eine echte `IB`-Instanz verbinden lässt, landet auf `127.0.0.1:7497` — beim offenen Schreibpfad.
**Warum (gemessen, Windows/Py 3.13):** Ist die Event-Loop schon angelegt, sperrt die `_no_network`-Fixture (`socket.socket.connect`, `connect_ex`, `getaddrinfo`) einen `asyncio.open_connection("127.0.0.1", port)` **nicht**: Ergebnis `CONNECTED despite patch: ProactorEventLoop`. Proactor verbindet über `ConnectEx`, und für IP-Literale überspringt asyncio `getaddrinfo`.
**Vermeiden:** Tests nutzen **nur** die injizierte Fake-Fabrik. Dazu kommt eine autouse-Fixture in den IBKR-Testmodulen, die (falls `ib_async` importierbar ist) `ib_async.IB.connectAsync` und `ib_async.client.Client.connectAsync` durch eine Funktion ersetzt, die sofort scheitert. Echte Verbindungen nur hinter `@pytest.mark.integration`.

### Pitfall 5: Neue Event-Loop scheitert unter der Netzsperre (Windows)
**Was schiefgeht:** `asyncio.new_event_loop()` innerhalb eines Tests wirft `OSError` — die Proactor-Loop baut ihre Self-Pipe über `socket.socketpair()`, dessen Windows-Fallback `connect` aufruft (gemessen, Traceback `_fallback_socketpair → csock.connect → blocked`). Unter Linux (CI) passiert das nicht, also wäre der Test nur lokal rot.
**Vermeiden:** Eine session-skopierte Fixture legt die Loop an. Session-Fixtures werden vor funktionsskopierten (auch autouse) instanziiert, die Netzsperre greift also noch nicht. Die Loop wird an `IbkrBroker(loop=...)` übergeben. Alternative: Die Loop schon beim Import des Testmoduls (Collection-Zeit) anlegen.

### Pitfall 6: `.env` hängt vom Arbeitsverzeichnis ab, Test-Env ist „echt"
**Was schiefgeht:** `import tradingagents` lädt `.env` per `find_dotenv(usecwd=True)` (`tradingagents/__init__.py:12`). Unter dem Task Scheduler (Phase 8) ist das cwd ein anderes. In Tests stehen die **echten** `IBKR_*`-Werte aus der lokalen `.env` in `os.environ`, denn die conftest leert nur `TRADINGAGENTS_*`.
**Vermeiden:** Das Kommando liest `.env` über einen festen Pfad (`Path(__file__).resolve().parents[1] / ".env"`, per `--env-file` überschreibbar) und nimmt ein injizierbares `environ`-Mapping. Tests übergeben ein explizites Dict bzw. `monkeypatch.delenv` und verlassen sich nie auf den Prozesszustand. Passwörter werden nie geloggt (`IBKR_PASSWORD` braucht das Kommando gar nicht).

### Pitfall 7: Kriterium-4-Grep zählt Nicht-Python-Dateien
**Was schiefgeht:** `git grep -l ib_async -- tradingagents scripts` findet auch `scripts/IBKR_EXECUTION.md`.
**Vermeiden:** Nachweis als AST-Test (wie `tests/test_layering.py`) plus `git grep -l -w ib_async -- "tradingagents/*.py" "scripts/*.py"`. Im Handbuch von „der IBKR-Bibliothek" sprechen.

### Pitfall 8: `clientId`-Kollision mit `ai_tradex`
**Was schiefgeht:** 326 „client id is already in use", wenn `ai_tradex` gegen dasselbe Gateway läuft.
**Warum:** `ai_tradex` vergibt `clientId = hash(...) % 10000` bzw. `% 9999 + 1` und benutzt in einem Debug-Lauf `clientId 1` (`ai_tradex/.planning/codebase/INTEGRATIONS.md:25`, `.planning/debug/d12-…md:61`). 0 bindet manuelle TWS-Orders an, 1 ist der `ib_async`-Default, 98 war die Phase-1-Sonde.
**Vermeiden:** Fester Wert **außerhalb 0..9999**, z. B. `20001`, als Konstante im Adapter und im Handbuch. [ASSUMED, A2: Werte über 9999 werden vom Gateway akzeptiert — beim ersten echten Lauf bestätigen]

### Pitfall 9: Lokale Umgebung ist nicht lauffähig
**Gemessen:** `.venv` mit `yfinance 0.2.63`, `pandas 2.3.0`, `langgraph 0.4.8`, `ruff 0.15.12`. `pytest tests/test_portfolio_context.py` → Collection-Fehler `module 'yfinance' has no attribute 'config'`. `ib_async` fehlt. Das `.venv` der Rebase-Worktree existiert nicht mehr (`git worktree list` zeigt nur `main`).
**Vermeiden:** Wave 0 frischt das `.venv` auf (`-e ".[dev,ibkr]"`), sonst ist keiner der lokalen Nachweise führbar.

## Code Examples

### Kommando-Skelett mit Exit-Codes (Muster von `daily_paper_run.py:13-40`)
```python
#!/usr/bin/env python3
"""IBKR paper executor for DUQ634065 (local operator tooling, milestone M2).

Operating manual: ``scripts/IBKR_EXECUTION.md``.

Exit codes:
    0   ok, including "nothing to do"
    1   configuration error - nothing was done
    2   precondition not met (not a trading day, stale decision, sources diverge, integrity finding)
    3   gateway/session not reachable
    4   kill switch active or release missing
    5   order rejected
    6   reconciliation unresolved, run aborted
    7   lock not acquired (second instance), clean exit
    8   account guard violated (managedAccounts != ["DUQ634065"])
    20  IBKR settings missing or unreadable - same meaning as EXIT_NO_CREDENTIALS in daily_paper_run.py
"""
EXIT_OK, EXIT_CONFIG, EXIT_PRECONDITION, EXIT_GATEWAY = 0, 1, 2, 3
EXIT_KILL_SWITCH, EXIT_REJECTED, EXIT_RECONCILE, EXIT_LOCKED = 4, 5, 6, 7
EXIT_ACCOUNT_GUARD, EXIT_NO_CREDENTIALS = 8, 20

REQUIRED_ENV = ("IBKR_HOST", "IBKR_PORT", "IBKR_ACCOUNT_ID")   # A1: Definition von "Zugangsdaten"
```
`main(argv=None, *, environ=None, broker_factory=None) -> int`: Beide Keyword-Argumente sind nur für Tests da, Produktion nutzt die Defaults. Jede erwartete Ausnahme endet in genau einer `logger.error("ibkr-state=…")`-Zeile und einem `return EXIT_*`. Ein letztes `except Exception` loggt `logger.exception` **nur in die Datei**, gibt auf stderr eine Zeile ohne Traceback aus und endet mit Exit 3 — oder Exit 1, wenn noch keine Verbindung bestand.

### Fake-IB für Tests (kein `ib_async` nötig)
```python
class FakeIB:
    def __init__(self, accounts=("DUQ634065",), refuse=None, probe=None):
        self.accounts, self.refuse, self.probe = list(accounts), refuse, probe
        self.calls: list[str] = []
        self.errorEvent = _Event(); self.disconnectedEvent = _Event()
        self.client = SimpleNamespace(placeOrder=self._record("placeOrder"), ...)
    async def connectAsync(self, host, port, clientId, timeout, readonly, **kw):
        self.calls.append("connect")
        if self.refuse: raise self.refuse          # z. B. ConnectionRefusedError()
    def managedAccounts(self): return list(self.accounts)
    def isConnected(self): return True
    def disconnect(self): self.calls.append("disconnect")
    def reqPositionsAsync(self): self.calls.append("positions"); return _done([...])
    def reqContractDetailsAsync(self, c): return self.probe or _done([...])  # never-done Future = "Session tot"
```
Kriterium-2-Test: `FakeIB(accounts=["DU0000001"])` → Exit 8, `"disconnect" in calls`, und weder `placeOrder` noch `cancelOrder`/`reqGlobalCancel`/`whatIfOrder` in `calls`. Den Unterschied zum Präfix belegt ein zweiter Fall mit `["DUQ634065", "DU0000001"]` (Obermenge) → ebenfalls Exit 8.

### Negativnachweis Kriterium 6 (gemessen)
```bash
.venv/Scripts/python.exe -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"
# → ERROR: Cannot install ib-async==2.1.0 and tzdata>=2026.1 ... ResolutionImpossible   (Exit ≠ 0)
.venv/Scripts/python.exe -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2025.2,<2026.0"
# → "Would install ..."  (Exit 0)
```

## State of the Art

| Alte Annahme | Gemessen / aktuell | Wann | Folge |
|---|---|---|---|
| Read-Only-Marker 10015 | **321**, Status `ValidationError` | 2026-10-11, Gateway 10.50.1 | Zustandstabelle führt 321 als `READ_ONLY_API` |
| Read-Only „standardmäßig an" | **keine** Voreinstellung; zurzeit aus | 2026-10-11 20:27 | Operator-Checkpoint + Sperre in der Client-Schicht |
| `readonly=True` schützt clientseitig (REQUIREMENTS-Notiz zu REQ-10) | sperrt **nicht**, unterdrückt nur den Order-Abgleich | ib_async 2.1.0 Quelltext | REQ-03-Behandlung: Schreibsperre im Adapter |
| Port 4002 | 7497 (`.env`) | Befund Frage 2 | Port ist reine Konfiguration |
| „ohne tzdata-Pin bricht die Auflösung" | löst ohne Pin auf; **mit `tzdata>=2026.1`** bricht es | gemessen | Kriterium 6 umformulieren |
| `ib_async.Watchdog` | nicht nutzbar (IBC) | Vorrecherche | eigene Probe (Muster 6) |

## Assumptions Log

| # | Annahme | Abschnitt | Risiko, falls falsch |
|---|---|---|---|
| A1 | „Zugangsdaten" für Exit 20 = `IBKR_HOST`, `IBKR_PORT`, `IBKR_ACCOUNT_ID` (fehlend/leer/`.env` unlesbar). `IBKR_USERNAME`/`PASSWORD` braucht die API nicht (Gateway-Login) und wird nicht verlangt | Code Examples | Der Operator erwartet Exit 20 auch bei fehlendem Passwort → Definition nachziehen |
| A2 | `clientId` 20001 (> 9999) wird vom Gateway akzeptiert | Pitfall 8 | 326/Ablehnung beim ersten Lauf → anderen Wert wählen, Handbuch anpassen |
| A3 | `cash = TotalCashValue` (konservativ, ohne Margin) statt `AvailableFunds` als „freies Kapital" | Muster 7 | Die Analyse sieht ein etwas anderes Cash; ändert keine Mengenrechnung (Phase 4 liest selbst) |
| A4 | Die Sec-Def-Probe (`reqContractDetails` per conId) bleibt bei toter Server-Session aus bzw. scheitert | Muster 6 | Wird sie bei 1100 aus einem Gateway-Cache beantwortet, erkennt die Probe nur Fälle ohne 1100. Das 1100-Flag deckt den Rest ab |
| A5 | Positionen, Account-Summary und Contract-Details funktionieren bei **aktivem** Gateway-Read-Only ohne Hänger (der Hänger kam von Order-Abfragen) | Pitfall 2 | Hängt doch ein Lese-Aufruf, greift der Timeout → Exit 3 mit Zustand; dann Read-Only für Phase 2 aus lassen und das begründen |
| A6 | Session-Fixtures werden vor der funktionsskopierten autouse-Netzsperre instanziiert | Pitfall 5 | Testinfrastruktur scheitert lokal → Loop zur Collection-Zeit anlegen |
| A7 | `whatIf` scheitert bei aktivem Gateway-Read-Only ebenfalls (321) | Checkpoint-Empfehlung | Betrifft nur, wann der Schalter vor Phase 4 wieder aus muss |

## Open Questions (RESOLVED)

1. **Kriterium 6 umformulieren?**
   - Bekannt: Ohne Pin löst es auf; mit `tzdata>=2026.1` ist es unauflösbar (gemessen, pip + uv).
   - Unklar: ob der Operator den Wortlaut in ROADMAP.md korrigieren will.
   - Empfehlung: Der Plan weist den gemessenen Negativnachweis nach und notiert die Abweichung im SUMMARY. Der Wortlaut ist ein Doku-Fix des Operators.
   - **RESOLVED:** per D-03 — Kriterium 6 wird auf den gemessenen Negativnachweis umformuliert (Plan 02-01 Task 1 ändert ROADMAP.md und REQUIREMENTS.md; Plan 02-01 Task 3 misst `ResolutionImpossible`).
2. **Read-Only im Gateway für Phase 2 wieder einschalten?**
   - Bekannt: Zurzeit aus, `readonly=True` sperrt nicht, Phase 2 braucht kein Schreibrecht. Phase 4 (`whatIf`) braucht es vermutlich wieder aus (A7).
   - Empfehlung: **Blockierender `checkpoint:human-action` vor der ersten Aufgabe, die gegen das echte Gateway verbindet.** Der Operator schaltet „Read-Only API" ein und bestätigt das. Der erste echte Lauf bestätigt dann zugleich A5. Lehnt der Operator ab, wird das im Handbuch mit Datum festgehalten, und die Sperre in der Client-Schicht ist die einzige Barriere.
   - **RESOLVED:** per D-02 — blockierender Operator-Checkpoint direkt VOR der ersten echten Verbindung, also in Plan 02-05 Task 1 (nicht vor früheren Aufgaben; Plans 02-01 bis 02-04 verbinden nie gegen das echte Gateway). Ergebnis „an“ oder begründete, datierte Ablehnung steht im Handbuch.
3. **Kriterium 7: Upstream-Datei `reporting.py` berühren oder nicht?**
   - Bekannt: Der Block steht heute in keinem Report. Die Änderung in `_header` ist klein (~3 Zeilen + Test), erzeugt aber eine weitere Konfliktstelle beim nächsten Upstream-Rebase.
   - Empfehlung: `reporting.py` ändern, weil Kriterium 7 wörtlich „im Report" sagt und CLI-Läufe mit `--portfolio` denselben Nutzen haben. Fallback ohne Upstream-Diff: Block in `summary.md` des Paper-Laufs.
   - **RESOLVED:** per D-04 — `reporting.py` wird minimal und nur additiv geändert (Block im `_header`, mit Test); `--portfolio` bleibt in unserem eigenen `scripts/daily_paper_run.py`.
4. **Gateway-Version:** Der Befund nennt erst 1045.1 (Code 2172, Ablauf 2026-12-15), der zweite Durchgang „Gateway 10.50.1". Ob inzwischen aktualisiert wurde, ist offen → Phase 8, hier nur notieren. `serverVersion` und `2172` gehören ins Log.
   - **RESOLVED:** auf Phase 8 verschoben — in Phase 2 nur protokolliert (`serverVersion` und Code 2172 im Log, Gateway-Version im Abschnitt „## First real run“ von Plan 02-05).
5. **Soll ein CI-Job das Extra installieren?** Wegen des Lazy-Imports laufen alle Phase-2-Tests ohne `ib_async`. Nur der Sperren-Test gegen das echte `ib_async`-`Client`-Objekt braucht es (`pytest.importorskip`). Empfehlung: ein kleiner zusätzlicher Job in `ci.yml` (Py 3.13, `pip install -e ".[dev,ibkr]"`, `pytest tests/test_ibkr_*.py`). Er belegt nebenbei die positive Auflösung in einer frischen Umgebung (Kriterium 6) und berührt `daily-paper-run.yml` nicht.
   - **RESOLVED:** per D-05 — KEIN CI-Job für das Extra in Phase 2; `ib_async` bleibt ein optionales Extra außerhalb der Kern-`dependencies`, die CI-Suite läuft wegen des Lazy-Imports ohne die Bibliothek, der Sperren-Test gegen das echte Client-Objekt nutzt `pytest.importorskip`, und der Positivnachweis von Kriterium 6 läuft lokal (Plan 02-01 Task 3, `uv pip compile`). Die obige Empfehlung ist damit verworfen.

## Environment Availability

| Abhängigkeit | Gebraucht von | Verfügbar | Version | Fallback |
|---|---|---|---|---|
| Python | alles | ✓ | 3.13.13 (`.venv`, Basis `Python313`) | — |
| Projekt-`.venv` lauffähig | Tests, Kriterium 7 | **✗** | yfinance 0.2.63 / pandas 2.3.0 / langgraph 0.4.8 / ruff 0.15.12 | auffrischen: `pip install -e ".[dev,ibkr]"` (Wave 0) |
| `ib_async` im `.venv` | Adapter, echter Lauf | **✗** | — (2.1.0 liegt nur in `ai_tradex/.venv`) | über das Extra `ibkr` installieren |
| `tzdata` | `ib_async` | ✓ | 2025.2 (`.venv`), auflösbar 2025.3 | — |
| `uv` | Auflösungsnachweis | ✓ | 0.11.7; **`--system-certs` nötig** (sonst `UnknownIssuer`) | pip (Truststore funktioniert) |
| pip | Installation, Negativnachweis | ✓ | 25.1.1, erreicht PyPI | — |
| IB Gateway Paper `127.0.0.1:7497` | Kriterien 1, 3 (echt), 5 (echt) | Operator-abhängig | Gateway 10.50.1 laut 2. Messung; `serverVersion=178` | Tests ohne Gateway über Fake; echte Läufe als Operator-Checkpoint |
| Gateway „Read-Only API" | Schreibsperre | **aus** (Befund 20:27) | — | Sperre in der Client-Schicht; Checkpoint |
| LLM-Key (Anthropic) in `.env` | Kriterium 7 (lokaler Paper-Lauf, ~0,18 $/Ticker) | ✓ (Variable vorhanden, Wert nicht geprüft) | — | Stub-Graph-Test belegt die Mechanik; der echte Lauf ist ein Operator-Checkpoint |
| slopcheck | Paket-Audit | ✗ (SSL) | 0.6.1 installiert, Registry nicht erreichbar | Pakete als [ASSUMED] geführt |

**Fehlend ohne Fallback:** keins. **Fehlend mit Fallback:** lauffähiges `.venv` und `ib_async` (Wave 0), Gateway-Read-Only (Checkpoint).

## Validation Architecture

### Test-Framework
| Eigenschaft | Wert |
|---|---|
| Framework | pytest (CI: aktuell via `pip install -e ".[dev]"`, `pytest>=8.0`; lokal 9.0.3, nach Auffrischung neuer) + `pytest-subtests` |
| Konfig | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `-m "not integration"`), `tests/conftest.py` |
| Schnelllauf | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py -q` |
| Volllauf | `.venv/Scripts/python.exe -m pytest -q` und `ruff check .` |

### Kriterium / Anforderung → Nachweis
| Kriterium / REQ | Verhalten | Typ | Automatischer Befehl | Datei existiert? |
|---|---|---|---|---|
| K1 / REQ-11 | Fake-Snapshot → JSON → `load_portfolio()` ok, Exit 0 | unit | `pytest tests/test_ibkr_executor.py -k "writes_portfolio" -q` | ❌ Wave 0 |
| K1 (echt) | gegen das laufende Gateway: JSON + Exit 0 | manuell/integration | `python scripts/ibkr_executor.py account --out %LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json; echo $?` | Operator-Checkpoint |
| K2 / REQ-04 | Fremdkonto bzw. Obermenge → Exit 8, `disconnect` aufgerufen, null Schreibaufrufe | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py -k "guard" -q` | ❌ Wave 0 |
| REQ-03 | `connectAsync` mit `readonly=True`, `clientId=EXECUTOR_CLIENT_ID`, `.env`-Host/Port; Schreibsperre wirft `ReadOnlyViolation` | unit (+ `importorskip` für echten `Client`) | `pytest tests/test_ibkr_broker.py -k "readonly or barrier" -q` | ❌ Wave 0 |
| K3 / REQ-09/55 | `ConnectionRefusedError` → Exit 3, Logzeile `GATEWAY_UNREACHABLE` + `502`, kein `Traceback` auf stderr/stdout; `TimeoutError`(+326) → Exit 3 `CLIENT_ID_IN_USE` | unit | `pytest tests/test_ibkr_executor.py -k "unreachable or client_id" -q` | ❌ Wave 0 |
| K3 / REQ-55 | fehlende/leere `IBKR_*` bzw. `.env` unlesbar → Exit 20; kaputter Port / falsches Konto / `MODE≠paper` → Exit 1 | unit | `pytest tests/test_ibkr_executor.py -k "credentials or config" -q` | ❌ Wave 0 |
| REQ-55 | Logdatei UTF-8, absoluter Pfad, Umlaut-Roundtrip (`"Gateway nicht erreichbar"`, `"schreibgeschützt"`) | unit | `pytest tests/test_ibkr_executor.py -k "log_file" -q` | ❌ Wave 0 |
| REQ-55 | Exit-Codes disjunkt, alle 10 definiert, Docstring-Tabelle = Konstanten | unit | `pytest tests/test_ibkr_executor.py -k "exit_codes" -q` | ❌ Wave 0 |
| K4 / REQ-07 | genau ein Modul importiert `ib_async` (AST, inkl. Funktions-Importe); ≤ 10 öffentliche Methoden auf `IbkrBroker` | unit | `pytest tests/test_ibkr_isolation.py -q` + `git grep -l -w ib_async -- "tradingagents/*.py" "scripts/*.py"` (genau 1 Zeile) | ❌ Wave 0 |
| K5 / REQ-09 | „Socket oben, Session tot" (nie fertiges Future) → `health().ok is False`, `PROBE_TIMEOUT`; nach 1100 ungesund, nach 1102 wieder gesund | unit | `pytest tests/test_ibkr_broker.py -k "health" -q` | ❌ Wave 0 |
| REQ-09 | jeder Code der Tabelle → erwarteter Zustand; 2104/2106/2158 nicht als Fehler | unit (parametrisiert) | `pytest tests/test_ibkr_broker.py -k "state_map" -q` | ❌ Wave 0 |
| REQ-08 | `clientId` konstant, im Handbuch genannt; kein hart kodiertes `orderId` im Adapter | unit | `pytest tests/test_ibkr_isolation.py -k "client_id" -q` (Handbuch-Grep auf die Konstante) | ❌ Wave 0 |
| REQ-12 | zwei `positions()`-Aufrufe → zwei `reqPositionsAsync`; Konto-Filter + `qty==0` raus; kein JSON-Rücklesen | unit | `pytest tests/test_ibkr_broker.py -k "fresh" -q` | ❌ Wave 0 |
| K6 / REQ-06 | Extra deklariert mit Kommentar; positiv auflösbar; mit `tzdata>=2026.1` unauflösbar | check (Netz) | `python -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"` (≠0) / `... "tzdata>=2025.2,<2026.0"` (=0); Test liest `pyproject.toml` per `tomllib` auf exakten Pin + Kommentarzeile | ❌ Wave 0 (tomllib-Test unit; Auflösung manuell/CI-Job) |
| K7 / REQ-11 | `--portfolio` reicht `PortfolioContext` an `propagate` durch (Stub-Graph); `write_report_tree` mit `portfolio_context` zeigt den Block; ungültige Datei → Exit 1 | unit | `pytest tests/test_daily_paper_run.py -k portfolio -q`, `pytest tests/test_reporting.py -k portfolio -q` | Dateien ✅, Tests ❌ |
| K7 (echt) | lokaler Paper-Lauf mit erzeugtem JSON, Block in `complete_report.md` | manuell (kostet LLM) | `python scripts/daily_paper_run.py --tickers AAPL --max-cost 1 --out <tmp> --state <tmp> --portfolio <json>` → `grep "Portfolio at the analysis date" <tmp>/reports/AAPL/complete_report.md` | Operator-Checkpoint |
| K8 / REQ-05 | `.env` nicht getrackt; kein `IBKR` in `.github/workflows/*.yml` | unit | `pytest tests/test_ibkr_isolation.py -k "ci or env" -q` (nutzt `git ls-files .env`, überspringt ohne `.git`) + `git ls-files .env` (leer) | ❌ Wave 0 |

### Sampling
- **Pro Task-Commit:** Schnelllauf (drei IBKR-Testdateien) + `ruff check scripts tests`.
- **Pro Wave:** Volllauf `pytest -q` + `ruff check .` (selbst ausführen — Memory: Selbstauskünfte der Executor-Agenten gegenprüfen).
- **Phase-Gate:** Volllauf grün, dann die beiden Operator-Checkpoints (echter Kontolauf, echter Paper-Lauf) und der Auflösungsnachweis.

### Wave-0-Lücken
- [ ] `.venv` auffrischen: `.venv/Scripts/python.exe -m pip install -e ".[dev,ibkr]"` (setzt das Extra aus Task 1 voraus; davor nur `.[dev]`)
- [ ] `tests/test_ibkr_broker.py`, `tests/test_ibkr_executor.py`, `tests/test_ibkr_isolation.py` neu
- [ ] Gemeinsames Fake-`IB` + session-skopierte Loop-Fixture + Sperre für echtes `connectAsync` (in einem `tests/ibkr_fakes.py`-Helfer oder einer Modul-Fixture; Pitfalls 4/5)
- [ ] Operator-Checkpoint: Gateway „Read-Only API" an (oder begründete Ablehnung ins Handbuch)

## Security Domain

### Anwendbare ASVS-Kategorien
| ASVS-Kategorie | Gilt | Kontrolle |
|---|---|---|
| V2 Authentication | nein (die Anwendung authentifiziert sich nicht; Gateway-Login macht der Operator) | — |
| V4 Access Control | **ja** — Paper-Guard ist die Autorisierungsgrenze „nur dieses Konto" | Konstante `EXPECTED_ACCOUNT`, exakter Listenvergleich, sofortiges Trennen |
| V5 Input Validation | ja | `.env`-Werte prüfen (Port `int`, `MODE == "paper"`, Konto == Konstante); JSON über Pydantic |
| V7 Error Handling & Logging | ja | benannte Zustände, kein Traceback auf der Konsole, keine Secrets im Log (`IBKR_PASSWORD` wird nie gelesen oder geloggt) |
| V14 Configuration | ja | `.env` gitignored (`.gitignore:151`), CI ohne IBKR-Secrets, `ib_async` exakt gepinnt |
| V6 Cryptography | nein | — |

### Bedrohungsmuster
| Muster | STRIDE | Abwehr |
|---|---|---|
| Verbindung landet auf einem Live-Konto (Port umkonfiguriert, falscher Login) | Spoofing / Elevation | Guard gegen Konstante, nicht gegen `.env`; Exit 8 vor jedem Nicht-Positions-Request |
| Unbeabsichtigte Order in der Lesephase | Tampering | kein Schreib-API, Sperre auf `ib.client`, Gateway-Read-Only (Checkpoint), Null-Aufrufe-Test |
| Test erreicht das echte Gateway | Tampering | nur Fake-Fabrik, `connectAsync`-Sperre in Tests, echte Läufe nur `-m integration` |
| Secret-Leck über CI oder Log | Information Disclosure | Wächtertest über `.github/workflows`, `.env` untracked, Passwort nie gelesen |
| Veraltetes Portfolio-JSON fließt in die Mengenrechnung | Tampering (Integrität) | REQ-12: frische Abfrage; JSON nur für die Analyse; atomares Schreiben, nur bei Exit 0 |
| Hänger legt den Lauf still (Denial of Service) | DoS | Timeout um jeden Request, Connect-Timeout, Exit 3 statt Hängen |
| `clientId`-Kollision mit `ai_tradex` | DoS | `clientId` außerhalb 0..9999 |

## Sources

### Primär (HOCH)
- `ib_async` 2.1.0, installierter Quelltext (`ai_tradex/.venv/Lib/site-packages/ib_async/`): `ib.py` (connect/connectAsync 329-381, 2029-2108; placeOrder 780-813; whatIfOrderAsync 2204-2212; RequestTimeout 138-141/271; StartupFetch 60-77; reqAccountSummaryAsync 2244-2261; reqPositionsAsync 2287-2290), `client.py` (connectAsync 206-236; getReqId/updateReqId 162-173; Handshake 385-416; _onSocketDisconnected 418-438), `wrapper.py` (error 1580-1723; position 597-620; accountSummary 554-563; startReq/_endReq 370-398), `objects.py` (AccountValue 218-223, Position 313-317), `ibcontroller.py` (Watchdog-Probe 337-351)
- Eigene Messungen 2026-10-11: `uv pip compile --system-certs` (4 Varianten, Py 3.11/3.13/3.14, win/linux), `pip install --dry-run` (positiv/negativ), `pip index versions ib_async|tzdata`, Schreibsperre am `IB()`-Objekt, asyncio-Loopback trotz Netzsperre, neue Loop unter Netzsperre (Windows)
- Repo: `tradingagents/portfolio.py`, `tradingagents/reporting.py`, `tradingagents/graph/trading_graph.py:183/327`, `tradingagents/__init__.py:12`, `scripts/daily_paper_run.py`, `tests/conftest.py`, `tests/test_layering.py`, `tests/test_daily_paper_run.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `.gitignore:151/251`
- `.planning/ibkr-konto-befund.md` (Stand `8f4b6ea`), `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`

### Sekundär (MITTEL)
- [IBKR TWS API — current time (sync-doc)](https://www.interactivebrokers.com/docs/tws-api/sync-doc/current-time.md) — Zeitabfrage prüft „the connection with the application"
- [IBKR System Message Codes](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/system-message-codes) / [message codes (Altseite)](https://interactivebrokers.github.io/tws-api/message_codes.html) — 1100/1101/1102/2110
- [IBKR Broken API socket connection](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/broken-api-socket-connection), [Verify API Connection](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/verify-api-connection)
- `.planning/research/ibkr-interface.md` §3.5/§3.6 (Codes-Tabelle), `.planning/research/ibkr-execution-architecture.md` §3.2/§5.4

### Tertiär (NIEDRIG)
- `ai_tradex/.planning/codebase/INTEGRATIONS.md:25` (clientId-Schema eines Nachbarprojekts, nicht nachgeprüft am Code)

## Metadata

**Konfidenz:**
- Standard Stack: HOCH — Versionen und Auflösung gemessen; Paket-Audit wegen SSL nur [ASSUMED]
- Architektur: HOCH für Guard/Sperre/Timeouts (Quelltext), MITTEL für die Probe-Wahl (A4)
- Pitfalls: HOCH für 1, 3, 4, 5, 9 (gemessen bzw. Quelltext); MITTEL für 2 (Schluss aus Rohausgabe + Quelltext)

**Recherchedatum:** 2026-10-11
**Gültig bis:** ~2026-11-10 (Pin ist fix; neu prüfen, falls `ib_async` ein Release > 2.1.0 bringt oder das Gateway-Upgrade auf ≥ 1050.1 vor dem 2026-12-15 kommt)
