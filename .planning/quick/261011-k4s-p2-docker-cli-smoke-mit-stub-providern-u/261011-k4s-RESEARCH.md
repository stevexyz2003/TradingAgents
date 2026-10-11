# Quick Task 261011-k4s: P2 — Docker-/CLI-Smoke + State-Retention — Research

**Researched:** 2026-10-11 · **Basis:** `main` = `a734955` (Upstream v0.6.0 + Strang)
**Confidence:** HIGH für alles mit `[V]` (im Docker-Image ausgeführt), MEDIUM/offen wo markiert

Legende: `[V]` = in dieser Sitzung ausgeführt und beobachtet · `[C]` = aus dem Code zitiert
(Datei:Zeile) · `[?]` = offen, nicht verifiziert.

---

## Summary

Die kritische Frage ist beantwortet, und besser als erwartet: **ein CLI-Lauf im Image kommt
ohne Netz und ohne Keys komplett durch — und zwar auch dann, wenn die Analysten ihre
Datentools wirklich aufrufen.** Der Grund ist keine Offline-Option (die gibt es nicht),
sondern dass `route_to_vendor` jeden Vendor-Fehler in einen *String* (`DATA_UNAVAILABLE:` /
`NO_DATA_AVAILABLE:`) verwandelt statt in eine Exception. Ein vollständiger Lauf mit 12
ausgeführten Datentools endete mit Exit 0 in 3 Sekunden. `[V]`

Ein vorbereiteter Daten-Cache ist dagegen eine Falle: er taugt nur am Kalendertag seines
Schreibens, und der wichtigste Tool-Pfad (`get_stock_data` → yfinance) benutzt den Cache
überhaupt nicht. Also: **kein Cache, keine Daten-Stubs — nur ein LLM-Stub plus
Netzisolation.**

**Primärempfehlung:** `docker network create --internal`, Stub als zweiter Container auf
diesem Netz, `docker run` (nicht compose), `--analysts market`, fester Vergangenheitstag,
Reports mit `docker cp` aus dem gestoppten Container holen. Der Stub muss `ThreadingHTTPServer`
sein — mit einem einthreadigen Server lief der Lauf in einen Deadlock. `[V]`

---

## Teil A — Der Smoke-Lauf

### A1 Welche Datenquellen ein Lauf tatsächlich anfasst

| Analyst | Tools | Vendor-Default |
|---|---|---|
| `market` | `get_stock_data`, `get_indicators`, `get_verified_market_snapshot` `[C market_analyst.py:9-11]` | yfinance `[C default_config.py:166-167]` |
| `news` | `get_news`, `get_global_news`, `get_macro_indicators`, `get_prediction_markets` `[C news_analyst.py:14-17]` | yfinance / fred / polymarket `[C default_config.py:171-173]` |
| `fundamentals` | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` `[C fundamentals_analyst.py:15-19]` | `sec_edgar,yfinance` `[C default_config.py:170]` |
| `social` | **keine Tools** — holt Reddit/Stocktwits/News *vor* dem Modellaufruf `[C analyst_execution.py:27-33, sentiment_analyst.py:34,40,66]` | — |

Dazu **zwei Netzaufrufe außerhalb der Tools**:
- `resolve_instrument_identity` → yfinance `info`, bewusst fail-open `[C agents/context.py:78-82]`.
  Beobachtet als `Cookie/crumb fetch failed (DNSError), continuing without crumb` `[V]`.
- `fetch_announcements` → `https://api.tauric.ai/v1/announcements`, Timeout 1.0 s, `except
  Exception` `[C cli/announcements.py:11-29, cli/config.py]`.

**Es gibt in v0.6.0 keinen Offline-/Fixture-/`--offline`-Pfad.** Ein grep über
`tradingagents/`, `cli/`, `scripts/` nach `offline|OFFLINE|fixture_dir|FIXTURE|stub` liefert
genau einen Treffer, und das ist ein Kommentar über yfinance-Rückgaben
(`vendors/yahoo/fundamentals.py:97`). `[V]`

Das Einzige, was existiert, ist eine Test-Fixture **im Prozess**:
`tests/test_graph_end_to_end.py:102-120` monkeypatcht jeden Eintrag in
`router.VENDOR_METHODS`. Über die CLI/Docker nicht erreichbar.

**Caches — und warum sie nicht helfen:**
- OHLCV: `<data_cache_dir>/<SAFE>-YFin-data.csv` `[C ohlcv.py:191-194]`.
  `_cache_is_fresh` verlangt `written.date() == now.date()` `[C ohlcv.py:146-158]` — ein
  ins Image gebackener Cache ist am nächsten Tag kalt, außer man `touch`t ihn.
- Und entscheidend: `get_stock_data` → yfinance = `get_YFin_data_online`, das
  `yf.Ticker(...).history()` **direkt** aufruft, ohne Cache
  `[C router.py:101, market.py:18-34]`. Der Cache bedient nur `get_indicators` und
  `get_verified_market_snapshot` `[C market.py:219,284, snapshot.py:39]`.
- SEC EDGAR: `<data_cache_dir>/sec_edgar/<name>` mit TTL `[C sec_edgar.py:122-132]`.

**Der tragende Mechanismus ist die Fehler-Degradation, nicht der Cache:**
`yf_retry` mappt jede Nicht-404-Exception auf `VendorUnavailableError`
`[C yahoo/common.py:73-76]`; `route_to_vendor` gibt daraufhin einen Sentinel-String
zurück statt zu werfen `[C router.py:265-266, 274-282]`; optionale Kategorien
(`macro_data`, `prediction_markets`) degradieren zusätzlich `[C router.py:94, 288-294]`.
Nur wenn *kein* Vendor antwortete und *keiner* saubere „no data" meldete, wird geworfen
`[C router.py:295]` — und genau dieser Fall tritt bei Netzausfall nicht ein.

**Verifiziert:** Im isolierten Netz schlagen alle Netzaufrufe in **0.0 s** fehl (kein
Timeout-Hänger): `getaddrinfo` → `gaierror`, `requests` → `ConnectionError`,
`yf.Ticker().history()` → `DNSError`. `[V]` Ein Lauf mit `--analysts market,news,fundamentals`
rief alle **12** Datentools auf (`grep -c "[Tool Call]"` → 12), loggte 6
`DATA_UNAVAILABLE`-Sentinels und endete mit **Exit 0 nach 3 s**. `[V]`

> **Empfehlung:** Daten-Stubs weglassen. Netzisolation + Fehler-Degradation ist der
> Offline-Pfad. Wer Tool-Coverage will, lässt den LLM-Stub einmal pro Analyst Datentools
> anfordern — das ist deterministisch und kostet nichts.

### A2 Kleinster Lauf, der etwas beweist

Der Graph fährt **immer** Bull → Bear → Research Manager → Trader → 3 Risk-Debater →
Portfolio Manager, unabhängig von der Analysten-Auswahl `[C graph/setup.py:148-185]`.
Die Auswahl bestimmt nur die erste (parallele) Welle `[C setup.py:160-166]`.

Gemessen `[V]`:

| Auswahl | LLM-Calls | Laufzeit im Container |
|---|---|---|
| `--analysts market`, 1/1 Runden | **9** | 2.2 s (`docker inspect` StartedAt→FinishedAt) |
| `--analysts market,news,fundamentals`, 1/1 | **14** | 3 s |

**Steuerung.** Flags: `--ticker --date --analysts --save/--no-save --show/--no-show
--html/--no-html` `[C cli/main.py:52-66]`. Ohne TTY prüft `unattended_gaps` und nennt
alle Lücken vorab `[C cli/selections.py:55-68, cli/run.py:104-110]` — nötig sind:

```
TRADINGAGENTS_OUTPUT_LANGUAGE=English
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1          # beide, sonst kommt die Depth-Frage
TRADINGAGENTS_LLM_PROVIDER=openai_compatible
TRADINGAGENTS_LLM_BACKEND_URL=http://stub:8000/v1
TRADINGAGENTS_QUICK_THINK_LLM=stub-quick # QUICK *oder* DEEP genügt formal, aber
TRADINGAGENTS_DEEP_THINK_LLM=stub-deep   # ohne beide fällt der andere auf gpt-6-* zurück
```
Env→Config-Mapping: `[C default_config.py:10-34]`. `openai_compatible` ist
`key_optional=True, require_base_url=True` `[C openai_client.py:230-233]`, und
`ensure_api_key` fragt für key-optionale Provider nicht `[C cli/prompts.py:642-647]` —
kein Key nötig. `[V]` bestätigt: `✓ Backend URL: http://stub:8000/v1`.

**Wichtig:** `data_vendors` / `tool_vendors` sind **nicht** env-überschreibbar (fehlen in
`_ENV_OVERRIDES`, `[C default_config.py:10-34]`). Vendors lassen sich also nicht per Env
auf einen Stub umbiegen — nur per Code/`set_config`.

**Datum** muss ≤ heute sein `[C trading_graph.py:40, cli/prompts.parse_analysis_date]` →
festes Vergangenheitsdatum pinnen (ich habe `2026-10-09` benutzt), nicht `auto`.

> **Empfehlung:** ein Ticker, `--analysts market`, 1/1 Runden, festes Datum,
> `--save --no-show --no-html`. 9 Calls, ~2 s. Optional ein zweiter Lauf mit drei
> Analysten für Tool-Router-Coverage (14 Calls, ~3 s).
> **`social` nicht ohne Vorab-Test aufnehmen** — der holt Reddit/Stocktwits eager vor dem
> Modellaufruf; dass das ohne Netz ebenfalls sauber degradiert, ist `[?]` ungetestet.

### A3 Welche Antwortform der LLM-Stub liefern muss

`openai_compatible` → `LocalCompatibleChatOpenAI`; `with_structured_output` löst über die
Capability-Tabelle auf. Ein unbekannter Modellname landet auf `_DEFAULT` mit
`preferred_structured_method="function_calling"` `[C capabilities.py:85-90, 124-140]`,
und `tool_choice` wird unterdrückt `[C openai_client.py:64-68]`.

**Verifiziert aus dem Stub-Log** `[V]` — die Entscheider bekommen je *genau ein* gebundenes
Tool mit dem Schema-Namen:

```
STUB call 1  model=stub-quick tools=['get_stock_data','get_indicators','get_verified_market_snapshot'] -> text
STUB call 4  model=stub-deep  tools=['ResearchPlan']      -> ResearchPlan
STUB call 5  model=stub-quick tools=['TraderProposal']    -> TraderProposal
STUB call 9  model=stub-deep  tools=['PortfolioDecision'] -> PortfolioDecision
```

Daraus folgt die Stub-Mechanik: **Rollenerkennung über `request["tools"]`**, nicht über die
URL.

1. Ist ein Tool-Name in `{ResearchPlan, TraderProposal, PortfolioDecision,
   SentimentReport}` → antworte mit `tool_calls[0].function.name = <dieser Name>` und
   `arguments` = JSON-String, der das Schema erfüllt `[C agents/schemas.py:95-127,
   146-189, 221-266, 311-363]`, `finish_reason="tool_calls"`.
   Minimal ausreichende Argumente (getestet `[V]`):
   `ResearchPlan {recommendation:"Overweight", rationale, strategic_actions}`,
   `TraderProposal {action:"Buy", reasoning}`,
   `PortfolioDecision {rating:"Overweight", executive_summary, investment_thesis}`.
2. Sonst → Klartext. **Damit die Analysten keine Datentools anfordern, muss der
   Nicht-Schema-Fall Klartext sein** (`_tools_or_done` beendet den Analysten, sobald
   `tool_calls` leer ist, `[C setup.py:48-50]`).

**Parser-Stellen:** `invoke_structured` behandelt ein `None`-Parse-Ergebnis als Miss,
wiederholt einmal mit Fehlerkontext und fällt dann auf Prosa zurück
`[C agents/structured.py:79-126]`. Aufrufer: Research Manager
`[C managers/research_manager.py:53-59]` und Trader `[C trader/trader.py:85-91]` über
`invoke_structured_or_freetext` `[C structured.py:129-140]`, Portfolio Manager direkt
`[C managers/portfolio_manager.py:80-86]`. Der „Signal-Processor" ist deterministisch:
`run_rating` liest `final_rating` `[C agents/rating.py:106-112]`, das der PM aus dem
typisierten Rating setzt `[C portfolio_manager.py:83]`.

**Ein rein textueller Stub funktioniert auch** — kostet nur 2 verworfene Structured-Versuche
pro Entscheider. Dann muss die Prosa die gelabelten Zeilen tragen, die
`extract_rating` liest `[C rating.py:55-93]`. Der kanonische Minimaltext steht schon im
Repo, `[C tests/test_graph_end_to_end.py:32]`:

```
Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**
```

**Die wichtigste Erkenntnis dieses Blocks — der Stub muss threaded sein.**
Die Analysten hängen als parallele START-Kanten am Graph `[C setup.py:160-166]`, es kommen
also mehrere gleichzeitige HTTP/1.1-Keep-alive-Verbindungen an. Mit
`http.server.HTTPServer` (einthreadig) **lief der Lauf in einen Deadlock: 400 s abgebrochen,
nur 2 von 14 Calls bedient**. Mit `ThreadingHTTPServer`, sonst identisch: **Exit 0 nach
3 s, 14 Calls**. `[V]` Das ist kein Stilproblem, das ist der Unterschied zwischen grün und
Timeout in CI.

Antwortkörper, der genügt `[V]`: `{id, object:"chat.completion", created, model,
choices:[{index, message, finish_reason}], usage:{prompt_tokens, completion_tokens,
total_tokens}}`. `usage` liest der `SpendTracker`, aber Budget ist per Default aus
(`max_cost_per_run=None`, `[C default_config.py:130-132]`).

### A4 Docker-Start, Rechte, Netz — alle Fallen verifiziert

**Start.** `ENTRYPOINT ["tradingagents"]` `[C Dockerfile:27]` → Console-Script aus
`[C pyproject.toml:44]`. Kein `CMD`, CLI-Argumente werden direkt angehängt. Im Container
verifiziert `[V]`: `uid=1000(appuser) gid=1000(appuser)`, `HOME=/home/appuser`,
`os.path.expanduser("~")` → `/home/appuser`, `/home/appuser/.tradingagents` =
`drwxr-xr-x 2 1000 1000` `[C Dockerfile:21-24]`. **Kein `sqlite3`-CLI im Image** `[V]`;
Pythons sqlite-Lib dort: 3.46.1.

Der funktionierende Aufruf (so gelaufen, Exit 0) `[V]`:

```bash
docker network create --internal tex-smoke-net
docker run -d --name stub --network tex-smoke-net --network-alias stub \
  -v "$PWD/stub":/stub:ro python:3.13-slim python -I /stub/stub_llm.py
docker run --name run --network tex-smoke-net \
  -e TRADINGAGENTS_LLM_PROVIDER=openai_compatible \
  -e TRADINGAGENTS_LLM_BACKEND_URL=http://stub:8000/v1 \
  ... tex-smoke:local --ticker AAPL --date 2026-10-09 --analysts market \
                      --save --no-show --no-html
docker cp run:/home/appuser/.tradingagents ./out
```

**Erzeugte Artefakte** (alle `[V]` beobachtet):

| Pfad unter `~/.tradingagents` | Quelle |
|---|---|
| `logs/<T>/<date>/reports/{market_report,investment_plan,trader_investment_plan,final_trade_decision}.md` | `[C cli/run.py:180-193]` |
| `logs/<T>/<date>/message_tool.log` | `[C cli/run.py:153]` |
| `logs/<T>/TradingAgentsStrategy_logs/full_states_log_<date>.json` | `[C trading_graph.py:527-531]` |
| `logs/reports/<T>_<stamp>/complete_report.md` + `1_analysts/ … 5_portfolio/` | `[C trading_graph.py:304-307, reporting.py:100-120]` |
| `memory/trading_memory.md` (+ `.lock`) | `[C log.py:46,59]` |
| `cli_prefs.json` | `[C cli/prefs.py:28,57]` |
| `cache/checkpoints/<T>.db` (nur mit `--checkpoint`) | `[C checkpointer.py:19-25]` |

**Netz-Fallen.**

| Variante | Befund |
|---|---|
| `--internal` User-Netz + Stub-Container | **Funktioniert.** Embedded DNS löst `stub` auf, alles nach außen scheitert in 0.0 s. `[V]` |
| `--network none` | Stub auf dem Host unerreichbar. Nur mit Stub *im* Container (Loopback lebt), was `--entrypoint` überschreiben hieße — damit testet man das Dockerfile nicht mehr. `[?]` nicht getestet |
| `--network host` (ubuntu-latest) | Erreicht einen Host-Stub über `127.0.0.1`, lässt aber echtes Outbound offen → Vendor-Calls gehen wirklich raus, Lauf nicht mehr deterministisch. `[?]` nicht getestet |
| `host.docker.internal` | Auf Linux nicht auflösbar ohne `--add-host=host.docker.internal:host-gateway`. `[ASSUMED]` — dokumentiertes Docker-Verhalten, hier nicht geprüft |

**Rechte-Fallen — beide verifiziert.**
- **Leeres** Named Volume auf `/home/appuser/.tradingagents`: Docker übernimmt
  Owner/Mode des Image-Verzeichnisses (1000:1000) → Lauf grün. `[V]` Deshalb funktioniert
  `[C docker-compose.yml:7]`.
- **Nicht-leeres** Mount mit fremder uid (1001 = die uid des GitHub-Runners `runner`):
  → `PermissionError: [Errno 13] … cli_prefs.json.<uuid>.tmp`, Traceback, **Exit 1**. `[V]`
  Ein Host-Bind-Mount aus dem Runner-Workspace ist genau dieser Fall. Also entweder vorher
  `chown 1000:1000` / `chmod 777`, oder gar nicht mounten und `docker cp` aus dem
  gestoppten Container (so gemacht, funktioniert).
- `--user $(id -u)` ist keine Lösung: eine uid ohne `/etc/passwd`-Eintrag bekommt
  `HOME=/`, dann zeigt `expanduser("~")` auf `/` und `/.tradingagents` ist nicht
  schreibbar `[C default_config.py:3]`. `[ASSUMED]`, nicht separat getestet.

**`docker compose` taugt hier nicht.** `[C docker-compose.yml:4-5]` hat
`env_file: - .env`, und `.env` ist gitignored `[C .gitignore:151]`. In einem Verzeichnis
ohne `.env` scheitert schon `docker compose config`: `env file …\.env not found`, **RC=1**
`[V]`. Dazu `tty: true` / `stdin_open: true` `[C docker-compose.yml:8-9]` — für CI falsch.
→ **`docker run`.** (Alternativ `required: false` am `env_file` ergänzen; dann wäre compose
auch nutzbar.)

**Kosten.** Kalter `docker build --no-cache` lokal: `pip install --no-cache-dir .` = 24.0 s,
Image-Export 11.3 s, Rest < 3 s `[V]`. Auf dem Runner kommt der Pull von
`python:3.13-slim` dazu. Die im CONTEXT akzeptierten 2–3 CI-Minuten sind komfortabel.
Der eigentliche Lauf ist 2–3 s.

**Negativ-Kontrolle** (beweist, dass der Smoke Signal hat): unerreichbare LLM-Base-URL
→ `APIConnectionError`, Traceback, **Exit 1**. `[V]`

**Versionen, die der kalte Build auflöst** (Pin-Referenz) `[V]`: `tradingagents 0.6.0`,
`langchain-core 1.6.9`, `langchain-openai 1.7.0`, `langgraph 1.2.14`,
`langgraph-checkpoint-sqlite 3.1.1`, `pandas 3.0.6`, `yfinance 1.7.0`, `pydantic 2.14.0`,
`openai 3.28.0`, `rich 15.0.0`, `typer 0.27.3`.

---

## Teil B — State-Retention / Backup / Recovery

### B5 Wo State liegt, wie die Dateien heißen, welche Sidecars es gibt

**Decision-Log — zwei verschiedene Orte, das muss das Runbook trennen:**

| Kontext | Pfad |
|---|---|
| CLI/Default | `~/.tradingagents/memory/trading_memory.md` `[C default_config.py:86]` |
| Paper-Lauf | `<state_dir>/decision-log.md` `[C scripts/daily_paper_run.py:223]`; in CI `state_dir=$RUNNER_TEMP/paper-state` `[C daily-paper-run.yml:101]`, committet auf Branch `paper-log` `[C daily-paper-run.yml:194-211]` |

Sidecars:
- `<log>.lock` — immer, bei jedem Write `[C log.py:46,156,211 → files.py:158]`.
- `<log>.settle.lock` — erst wenn eine Settlement-Runde tatsächlich startet.
  `settle_all_pending` iteriert zuerst die Pending-Einträge und ruft `settle_pending` nur
  dafür `[C settlement.py:158-168]`; ein leeres Log erzeugt die Datei nie.
  **Verifiziert:** `git ls-tree -r fork/paper-log` enthält `decision-log.md.lock`, aber
  kein `.settle.lock`. `[V]`
- Rewrite-Temp: `Path.with_suffix(".tmp")` `[C log.py:198-200, 252-254]` — das **ersetzt**
  die Endung, heißt also **`trading_memory.tmp`** bzw. **`decision-log.tmp`**, nicht
  `…md.tmp`. `[V]` (mit pathlib geprüft)
- `files.replace_file` erzeugt `<name>.<uuid32>.tmp` neben der Datei `[C files.py:136]` —
  benutzt für OHLCV-Cache `[C ohlcv.py:224]`, SEC-Cache `[C sec_edgar.py:131]` und
  CLI-Prefs `[C prefs.py:57]`.

> **Fund:** `decision-log.md.lock` liegt committet auf `paper-log` `[V]`. Ursache ist
> `git add -A .` ohne Ausschluss `[C daily-paper-run.yml:203]`. Kosmetisch, aber gehört
> ins Runbook (oder ein `.gitignore` im State-Dir).

> **Fund:** Die Retention-Entscheidung „Reports: 90 Tage" trifft nur das Workflow-Artefakt
> `[C daily-paper-run.yml:192]`. `runs/<date>/<TICKER>.md` und `runs/<date>/summary.json`
> werden **dauerhaft** auf `paper-log` committet `[C daily_paper_run.py:323-331]`,
> verifiziert im Branch-Tree `[V]`. Entweder Formulierung anpassen oder den Archiv-Teil
> prunen.

Größenordnung `[V]`: `decision-log.md` = **3105 Bytes** nach einem Eintrag, 15 Commits auf
`fork/paper-log`. ~3 KB/Eintrag × 3 Ticker × 21 Handelstage ≈ 190 KB/Monat. „Unbegrenzt"
ist auf Jahre unkritisch.

**Checkpoints:** `<data_cache_dir>/checkpoints/<SAFE_TICKER>.db`, default
`~/.tradingagents/cache/checkpoints/` `[C checkpointer.py:19-25, default_config.py:85]`.
Verifiziert: `--checkpoint`-Lauf erzeugte `cache/checkpoints/MSFT.db`, 106496 Bytes. `[V]`

- `SqliteSaver` fährt **WAL**: `PRAGMA journal_mode` → `('wal',)` `[V]`. `-wal`/`-shm`
  existieren nur **solange eine Verbindung offen ist** — verifiziert: während der offenen
  Verbindung `['AAPL.db','AAPL.db-shm','AAPL.db-wal']`, nach `conn.close()`
  `[C checkpointer.py:51]` nur noch `['AAPL.db']`. `[V]`
  Die Sidecars überleben also nur einen **Crash** — genau dafür globt
  `clear_all_checkpoints` `{db.name}-*` `[C checkpointer.py:80]`, eingeführt mit
  `bbcd666` (2026-09-18, „remove the database sidecars when clearing checkpoints").
- Tabellen: `checkpoints`, `writes` `[V]`, passend zu `[C checkpointer.py:93]`.

> **Retention-Fund:** Ein erfolgreicher Lauf ruft `clear_checkpoint`, und das **löscht
> Zeilen, nicht die Datei** `[C checkpointer.py:85-99]`. Verifiziert: nach erfolgreichem
> Lauf existierte `MSFT.db` weiter mit 106 KB und `checkpoints=0, writes=0`. `[V]`
> `.db`-Dateien sammeln sich also eine pro Ticker für immer an; nur
> `--clear-checkpoints` `[C cli/main.py:75-78]` entfernt sie. Eine 7-Tage-Retention heißt
> daher: `.db` nach mtime löschen — **und `-wal`/`-shm` mit**, so wie
> `clear_all_checkpoints` es tut.

> **Scope-Fund:** In CI gibt es **nie** Checkpoints. Der Paper-Lauf setzt
> `checkpoint_enabled = False` hart `[C daily_paper_run.py:224-226]`, und `data_cache_dir`
> bleibt im ephemeren Runner-Home. Checkpoint-Retention ist ausschließlich ein Thema der
> lokalen Arbeitsmaschine.

### B6 Integritätsprüfung ohne die Bibliothek — und die Recovery-Empfehlung

`PRAGMA quick_check` und `PRAGMA integrity_check` laufen über die stdlib `sqlite3`, auch
read-only per URI `file:<db>?mode=ro` → beide `('ok',)` `[V]`.

Drei nicht offensichtliche Befunde, alle verifiziert `[V]`:

1. **Bei korruptem Image *wirft* `quick_check`**, es liefert keine Zeile ≠ `"ok"`:
   `sqlite3.DatabaseError: database disk image is malformed`. Bei Müll-Header:
   `sqlite3.DatabaseError: file is not a database`.
   → Das `verify`-Unterkommando muss `try/except sqlite3.DatabaseError` kapseln und die
   Exception als Befund werten, nicht nur den Rückgabewert mit `"ok"` vergleichen.
2. **Dieselbe korrupte Datei beantwortete `select count(*) from checkpoints` mit `1`.**
   Ein „kann ich abfragen?"-Test ist also *keine* Integritätsprüfung.
3. **Sidecar-Caveat:** Mein `mode=ro`-Öffnen gelang *mit* lebendigem `-wal`/`-shm` — aber
   SQLite braucht für WAL-Lesen Schreibzugriff auf `-shm`. Für eine Datei aus einem
   abgestürzten Lauf ist der belastbare Weg: `*.db*` in ein Temp-Verzeichnis kopieren und
   die Kopie prüfen, oder read-write öffnen (das recovert die WAL). `[?]` als allgemeine
   Garantie offen.

**Recovery-Empfehlung: verwerfen, nicht `.recover`.**
`.recover` ist ein Kommando der `sqlite3`-**Shell**, nicht des Python-Moduls. Das Binary
fehlt auf dieser Maschine (`command -v sqlite3` → nichts) **und** im Image `[V]`. Dazu
sind Checkpoints per Operator-Entscheidung 7-Tage-Wiederaufsetzpunkte. Also:

- **Checkpoints korrupt →** `rm <T>.db <T>.db-wal <T>.db-shm` (oder
  `tradingagents --clear-checkpoints`) und frisch laufen. Verlust: ein Resume-Punkt.
- **Decision-Log korrupt/verloren →** es ist reines Markdown; autoritative Kopie ist der
  Branch `paper-log`. Recovery = `git fetch fork paper-log && git checkout
  fork/paper-log -- decision-log.md`. Ein `verify` für das Log ist ein Parse-Check:
  `TradingMemoryLog.load_entries()` darf nicht 0 Einträge liefern, wenn die Datei
  nicht-leer ist, und jede Tag-Zeile muss ≥ 4 Felder haben `[C log.py:310-341]`.

### B7 Locking / Parallellauf — was es gibt und was fehlt

**Vorhanden, und besser als der CONTEXT annimmt:**

| Mechanismus | Stelle |
|---|---|
| Cross-Prozess-Lock auf jedem Log-Write | `[C log.py:46,156,211]` → `files.locked`, `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) `[C files.py:148-200]` |
| Separater Settlement-Lock, `wait=False` vom Graph | `[C log.py:62-72, settlement.py:120-122, trading_graph.py:343]` |
| Atomare Rewrites (Temp + `replace`) | `[C log.py:198-200, 252-254]`, generisch `[C files.py:126-145]` |
| Idempotenz: kein zweiter Eintrag für Ticker+Datum | `[C log.py:47-55]` |
| Rotation `memory_log_max_entries` (inkl. Tests) | `[C default_config.py:90, log.py:273-308]`, `tests/test_memory_log.py:322-351` |

Aber: `memory_log_max_entries` ist `None` per Default, hat **keinen
`TRADINGAGENTS_*`-Override** (fehlt in `_ENV_OVERRIDES`, `[C default_config.py:10-34]`) und
wird vom Paper-Lauf nicht gesetzt `[C daily_paper_run.py:210-227]`. Rotation ist in
Produktion also dauerhaft aus — konsistent mit „Decision-Log unbegrenzt", aber das Runbook
sollte sagen, dass sie nur im Code umschaltbar ist.

**Lücken, die das Runbook benennen muss:**

1. **Checkpoints haben keinen Applikations-Lock.** Nur SQLites eigenes Locking, und die
   Verbindung läuft mit `check_same_thread=False` `[C checkpointer.py:45]`. Zwei
   gleichzeitige Läufe auf gleichem Ticker+Datum+Signature teilen eine `.db` **und eine
   `thread_id`** `[C checkpointer.py:28-38]` → `database is locked` bzw. verschränkte
   Writes. Die Per-Ticker-DB isoliert nur *verschiedene* Ticker — genau das behauptet der
   Modul-Docstring auch `[C checkpointer.py:3]`.
2. **`clear_all_checkpoints` löscht ungesichert über alle Ticker** `[C checkpointer.py:68-82]`.
   Während ein anderer Lauf seinen Checkpoint hält, zerstört das dessen Resume.
   `--clear-checkpoints` ist kein Routine-, sondern ein Wartungsbefehl.
3. **Der Paper-Lauf ist nur per GitHub-`concurrency`-Gruppe serialisiert**
   `[C daily-paper-run.yml:59]`, genannt in `[C scripts/PAPER_RUN.md:156-158]`. Auf
   `paper-log` selbst gibt es keinen Lock. Ein zweiter Writer aus einem anderen Workflow
   würde am Non-fast-forward-`push` scheitern — der Fehlermodus ist also ein *verlorener*
   Lauf, nicht ein kaputtes Log.
4. `get_pending_entries()` in `settle_all_pending` liest das Log **außerhalb** jedes Locks
   `[C settlement.py:165]`. Harmlos (der Pass liest unter Lock neu), aber erwähnenswert.
5. `.lock`-Dateien werden nie gelöscht und akkumulieren pro Log-Pfad — und landen im Git
   (siehe B5).

---

## Konkrete Empfehlungen für den Plan

**Smoke (CI-Job):**
1. `docker build -t tex-smoke:ci .`
2. `docker network create --internal tex-smoke-net`
3. Stub-Container (`python:3.13-slim`, Stub per `-v … :ro`), `ThreadingHTTPServer`,
   Rollenerkennung über `request["tools"]`, Netz-Alias `stub`.
4. `docker run` (kein compose) mit den sieben Env-Variablen aus A2 und
   `--ticker AAPL --date <fest> --analysts market --save --no-show --no-html`.
5. Assertions: Exit 0; `logs/reports/AAPL_*/complete_report.md` existiert;
   `full_states_log_<date>.json` hat `final_rating == "Overweight"`;
   `memory/trading_memory.md` enthält `[<date> | AAPL | Overweight | pending]`;
   Stub-Call-Zähler == 9 (Beweis „kein echter LLM-Call" und zugleich ein Regressionsfühler
   für Graph-Form-Änderungen).
6. Reports per `docker cp` holen — **kein Host-Bind-Mount** (B/A4-Rechtefalle).
7. Teardown: `docker rm -f`, `docker network rm`.

**State-Wartungsskript `scripts/state_maintenance.py`:**
- `verify` — pro `*.db` unter `<cache>/checkpoints/`: Kopie nach Temp (inkl. `-wal`/`-shm`),
  `PRAGMA quick_check` in `try/except sqlite3.DatabaseError`, Tabellen
  `checkpoints`/`writes` vorhanden. Plus Decision-Log-Parse-Check über
  `TradingMemoryLog.load_entries()`.
- `prune` — Checkpoints: `.db` mit `mtime` älter als N Tage (Default 7) löschen,
  **zusammen mit `-wal`/`-shm`** (gleiche Glob-Logik wie `checkpointer.py:80`).
  Decision-Log: bewusst **kein** Prune (Operator-Entscheidung). Reports:
  `<results_dir>/reports/<T>_<stamp>/` nach `stamp` älter als 90 Tage.
- `backup` — Decision-Log + `index.md` + `runs/` kopieren/tarren; die Checkpoints
  gehören nicht ins Backup (Wiederaufsetzpunkte).
- Tests: Korruption künstlich erzeugen (Bytes ab Offset 4096 überschreiben — so
  reproduziert `[V]`), prüfen dass `verify` die `DatabaseError` als Fehler meldet; prüfen
  dass `prune` Sidecars mitnimmt; prüfen dass `prune` das Decision-Log nicht anfasst.

**Runbook-Kapitel (an `scripts/PAPER_RUN.md` anschließen):** Pfad-Tabelle aus B5,
Retention-Tabelle (Decision-Log unbegrenzt / Checkpoints 7 d / Artefakt 90 d **+ Hinweis,
dass `runs/` dauerhaft ist**), Recovery-Ablauf aus B6, und die fünf Locking-Lücken aus B7.

---

## Offene Punkte

1. **`social`-Analyst ohne Netz** — `sentiment_analyst.py:66` holt News/Reddit/Stocktwits
   eager vor dem Modellaufruf. Nicht getestet. Vor Aufnahme in den Smoke einmal laufen
   lassen, sonst `--analysts market[,news,fundamentals]` bleiben.
2. **GitHub-Runner statt Docker Desktop** — alle Docker-Beobachtungen stammen von Docker
   Desktop 29.8.1 (desktop-linux) / Compose v5.5.1. Container-internes Verhalten trägt 1:1
   über; die uid-Falle habe ich mit einem gechownten Volume faithful nachgebaut, aber ein
   echter Bind-Mount auf dem Runner ist ungetestet.
3. **`--network host` / `host.docker.internal`** als Alternativen: nur erwogen, nicht
   getestet. Die `--internal`-Zwei-Container-Variante ist getestet und funktioniert —
   ich sehe keinen Grund, die anderen zu evaluieren.
4. **Read-only Öffnen einer `.db` mit lebender `-wal`** aus einem abgestürzten Lauf:
   bei mir gelungen, als allgemeine Garantie offen. Daher die Kopie-nach-Temp-Empfehlung.
5. **Lokale Verifikation außerhalb Docker** geht derzeit nicht: das Haupt-`.venv` trägt
   noch den Vor-v0.6.0-Stand (`langchain-core 1.3.2`, `langgraph 0.4.8`, `pandas 2.3.0`,
   `yfinance 0.2.63` gegen die Minima in `pyproject.toml:12-28`) `[V]`. Für
   `pytest`-Arbeit an `state_maintenance.py` braucht es ein frisches venv — und auf dieser
   Maschine gelten die bekannten SSL-Workarounds (`NODE_OPTIONS=--use-system-ca`,
   `UV_OFFLINE=1`).
