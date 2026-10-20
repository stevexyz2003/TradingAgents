# Architecture Research: M3 Vorhersage-Engine (Europa)

**Domain:** Einbindung einer Prognose-Engine (PIT-Daten → Merkmale → kalibriertes Modell → Entscheidung → Größe → IBKR-Ausführer) in die bestehende TradingEngineX-Architektur
**Researched:** 2026-10-20 · Arbeitsbaum `main` (letzter Commit `e5b18c6`, Phase-7-Commits enthalten)
**Confidence:** HOCH für die Integrationspunkte. Sie sind am Code geprüft, Zeilen beziehen sich auf den Arbeitsbaum vom 2026-10-20. MITTEL für Timing und Betriebsort, weil Vendor-Lieferzeiten und GitHub-Cron-Verzug nicht normativ belegt sind. NIEDRIG für Kostenannahmen der LLM-Stufe.

> Hinweis: `git` hing in dieser Session (Timeout bei `git log`/`git show`). Provenienz-Aussagen wie „Upstream" oder „Strang" stammen deshalb aus dem o31-Research (`git cat-file`-geprüft, Stand 2026-10-19) und wurden nicht neu gegen `origin/main` gezogen.

---

## 0. Kernaussagen

1. **Neues entsteht als eigenes Strang-Paket `tradingagents/forecast/` plus Skripte unter `scripts/`.** Am Upstream-Kern wird für M3 **keine Datei zwingend geändert**. Die Einstellungen für Benchmark, Horizont und Temperatur lassen sich über `build_config(base_config=…)` (`scripts/daily_paper_run.py:374-391`) und `_ENV_OVERRIDES` (`default_config.py:10-34`, u. a. `TRADINGAGENTS_BENCHMARK_TICKER`, `TRADINGAGENTS_TEMPERATURE`) setzen. Eine einzige Upstream-Berührung ist optional: eine Hook-Zeile in `TradingAgentsGraph.record_decision` (`trading_graph.py:388-419`) an derselben Stelle, an der der Strang heute schon `jev_hooks.review_run` aufruft (`:391`).
2. **Die Entscheidung trifft nicht mehr das LLM, sondern ein Modell.** Die Kette lautet: Archiv → Feature-Store → Modell (P je Horizont) → Kosten → LLM-Veto (darf nur verkleinern) → Sizing/Risiko → `targets.json` → Ausführer. Die Upstream-Pipeline läuft nur noch für eine **Shortlist** als Veto- und Begründungsgeber. Die News-Merkmale liefert ein eigener, billiger Extraktionsschritt mit einem LLM-Aufruf je Meldung, nicht die 12-Knoten-Pipeline.
3. **`decision-log.md` und die SETTLEMENT-Zeile bleiben formatgleich.** Der Parser ist für zusätzliche Schlüssel tolerant (`log.py:359-366` liest beliebige `k=v`, `settlement.py:160-173` wertet nur `entry`, `holding` und `benchmark` aus). Neue Felder sind deshalb **additiv**. Den Schlüssel `entry` darf M3 **nie** mit einem neuen Wert belegen. Sonst bleibt der Eintrag für immer `pending` (`settlement.py:161-164`). Die gate-relevante Abrechnung (EUR, nach Kosten, 5d/20d, `next_open`) läuft in einem **eigenen** Forecast-Ledger. Das Upstream-Settlement bleibt die Lernschleife des LLM.
4. **Der Betriebsort ist zweigeteilt.** Ingest, Merkmale, Prognose und Shortlist-LLM laufen in GitHub Actions eines **privaten** Begleit-Repos, abends nach Börsenschluss (ca. 20:40–22:00 UTC). Die Ausführung läuft lokal am nächsten Morgen nach der Eröffnungsauktion. Der Grund: Die Fork ist als Fork eines öffentlichen Repos zwingend öffentlich, und zwar Repo **und** Actions-Logs. Gekaufte PIT-Daten und archivierte News-Texte dürfen dort nicht liegen.
5. **Bauen in dieser Reihenfolge:** News-Archiv sofort, denn jeder verpasste Tag ist unwiederbringlich. Danach Universum, Kalender und FX, dann Labels, Kosten und Validierungsrahmen **vor** dem Modell. Es folgen Modell und Registry, LLM-Merkmale und Veto, Entscheidung und Sizing im Schattenbetrieb, der EU-Ausführer und zuletzt Betrieb und Gate. Den Ausführer-Umbau kann man parallel bauen, sobald das Schema von `targets.json` fest ist.

---

## 1. Standard Architecture

### 1.1 System Overview (Soll M3)

```
┌──────────────────────────── Z0  Privates Begleit-Repo (GitHub Actions, privat) ────────────────────────────┐
│                                                                                                              │
│  eu-ingest.yml (Mo–Fr ~20:40 UTC)        eu-forecast.yml (Mo–Fr ~21:10 UTC, nach Ingest)                     │
│  ┌──────────────┐  ┌──────────────┐      ┌───────────┐  ┌──────────┐  ┌────────────┐  ┌──────────────┐         │
│  │ news_archive │  │ pit_ingest   │ ──▶  │ features  │─▶│  model   │─▶│ cost+decide│─▶│ sizing/risk  │         │
│  │ (stündlich+) │  │ Kurse/Fund./ │      │ store     │  │ P(5d,20d)│  │ (Edge n.K.)│  │ targets.json │         │
│  └──────┬───────┘  │ CA/FX/Index  │      │ (as_of)   │  └────┬─────┘  └─────┬──────┘  └──────┬───────┘         │
│         │          └──────┬───────┘      └─────▲─────┘       │ Shortlist    │ Veto (nur ↓)   │                 │
│         │                 │                    │             ▼              │                │                 │
│         │                 │      ┌─────────────┴───┐   ┌──────────────────┐ │                │                 │
│         └─────────────────┴────▶ │ llm_features    │   │ Upstream-Pipeline│─┘                │                 │
│                                  │ (1 Call/Meldung,│   │ (≤ N Ticker/Tag, │                  │                 │
│                                  │  gecacht)       │   │  daily_paper_run)│                  │                 │
│                                  └─────────────────┘   └──────────────────┘                  │                 │
│  Speicher (privat): data/raw/** (append-only) · store/*.parquet · models/<id>/ · models/ACTIVE.json           │
│                     llm-cache/** · Branch forecast-log: forecasts.jsonl, runs/<date>/targets.json,            │
│                                    decision-log.md (EU-LLM-Schleife), index.md                                │
└───────────────────────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                                │ git fetch (read-only, eigener Remote)
┌──────────────────────── Z3  Lokaler Windows-Host (Operator) ──▼──────────────────────────────────────────────┐
│  ibkr_executor.py execute --source targets  (Mo–Fr nach Eröffnungsauktion, Kalender je MIC)                    │
│   GitPaperLog(remote="private", branch="forecast-log") → ibkr_targets.plan_target → guards (Notional-Cap,     │
│   Kill/Release, Session je MIC) → ledger (write-ahead) → ibkr_broker (ib_async) → IB Gateway (Paper)          │
│   ibkr_publish → Branch ibkr-log (Fills, portfolio.json, Heartbeat)  [Phase 7, besteht]                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────── Z1  Öffentliche Fork (GitHub Actions) ───────────────────────────────────────────────┐
│  daily-paper-run.yml (US, Di–Sa 06:30 UTC) → paper-log  [unverändert; pausierbar per Variable]                │
│  CI, Security-Audit, Heartbeat-Check (liest ibkr-log und forecast-log-Heartbeat, keine Daten)                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Komponente | Verantwortung | Umsetzung (Vorschlag) | neu/geändert |
|---|---|---|---|
| `forecast/universe.py` | Festes EU-Universum: ISIN, Yahoo-/Vendor-Symbol, MIC, Primärbörse, Währung, Benchmark, PIT-Zugehörigkeit (`valid_from`/`valid_to`) | versionierte CSV/JSON im privaten Repo, Pydantic-Validierung | neu |
| `forecast/calendars.py` | Sitzungen je MIC (XETR, XPAR, XAMS, XLON, XSWX, XMIL, XMAD …), „letzte geschlossene Sitzung", Sessions zwischen zwei Daten | Verallgemeinerung von `XnysSessions` (`scripts/ibkr_decision.py:469-531`) auf `exchange_calendars.get_calendar(mic)` | neu (Ausführer übernimmt es) |
| `forecast/archive/` | News und Meldungen mit `published_ts`, `first_seen_ts`, Quelle, Hash, Qualitätsstatus je Tag; append-only | Fetcher je Quelle, Normalisierung, JSONL/Parquet je Tag | neu |
| `forecast/ingest.py` | PIT-Kurse, Fundamentaldaten, Kapitalmaßnahmen, FX, Benchmark-Serie vom gekauften Vendor; bitemporal (`as_of`, `ingested_at`) | Vendor-Client (Wahl siehe STACK.md), Rohdateien unveränderlich | neu |
| `forecast/store.py` | Feature-Store: `features(as_of_date, isin, feature, value, knowledge_ts, feature_set_version)`; Abfrage nur `knowledge_ts <= cutoff` | Parquet je Monat + DuckDB-Abfragen | neu |
| `forecast/features/*.py` | Kurs-, Fundamental- und Textmerkmale, deterministisch aus Store-Rohdaten | reine Funktionen, Golden-Tests | neu |
| `forecast/llm_features.py` | Strukturierte Extraktion je Meldung (Sentiment −1..1, Ereignistyp, Relevanz, Konfidenz) | ein Quick-Modell-Call, Pydantic-Schema analog `agents/structured.py`, Cache `(model, prompt_hash, input_hash)` | neu |
| `forecast/labels.py` + `costs.py` | Ziel: `beat_{5,20}d = r_EUR(next_open→close_{t+h}) − r_bench − 2×cost > 0`; Kosten 20 bp je Seite; FX | rein, aus Store-Kursen (nicht yfinance-adjusted) | neu |
| `forecast/walkforward.py`, `baselines.py`, `gate.py` | Zeitliche Splits mit Purging/Embargo, Baselines (Benchmark, Zufall, Momentum), Kalibrierung, Block-Bootstrap-KI, Drawdown, Mehrfachtest-Protokoll | reine Bibliothek + `scripts/forecast_backtest.py`, `scripts/gate_report.py` | neu |
| `forecast/model.py` + `registry.py` | Training, Kalibrierung, Prognose; unveränderliche Modell-Artefakte mit Manifest; `ACTIVE.json`-Zeiger | Bibliothek siehe STACK.md; Artefakt ohne Pickle (Text/JSON) | neu |
| `forecast/veto.py` | Ergebnis der Upstream-Pipeline (PM-Rating, REVIEW, Jev-Schatten) → Veto ja/nein mit Grund; nie Vergrößerung | rein | neu |
| `forecast/sizing.py` + `risk.py` | Zielgewicht aus P, Edge, Volatilität; Caps je Titel/brutto; Drawdown-Stopp; Abbaupfad | rein; Eingaben NAV/Positionen aus `ibkr-log:portfolio.json` | neu |
| `forecast/decide.py` | Bündelt Modell, Kosten, Veto, Sizing → `targets.json` + Zeilen in `forecasts.jsonl` (inkl. kontrafaktischer Ziele ohne Veto) | rein | neu |
| `forecast/settle.py` | Gate-Abrechnung je (Prognose, Horizont): EUR, netto, nicht überlappende Kohorten | rein, Kurse aus Store | neu |
| `forecast/hooks.py` | Optional: additive SETTLEMENT-Schlüssel für die EU-`decision-log.md` | analog `tradingagents/jev/hooks.py` | neu (optional) |
| `scripts/forecast_daily.py` | Orchestrator (analog `daily_paper_run.py`): Cutoff bestimmen, Datenqualität prüfen, Prognose, Shortlist-LLM, Entscheidung, Commit auf `forecast-log` | CLI mit Exit-Codes nach Repo-Konvention | neu |
| `scripts/news_archive.py` | Cron-Erfassung der Meldungen, Tagesstatus | CLI | neu |
| `scripts/label_ui.py` | ~50 Meldungen/Monat labeln (Jev-Schatten, Entscheidung 8) | lokales Mini-UI (stdlib `http.server` oder Streamlit, siehe STACK.md) | neu |
| `scripts/ibkr_targets.py` | Ausführer-Gegenstück: liest `targets.json`, prüft Vertrag, `plan_target()` | rein, analog `ibkr_decision.py` | neu |
| `scripts/ibkr_decision.py` | Kalender je MIC statt nur XNYS | `load_xnys_calendar` → `load_calendar(mic)` | geändert (Strang) |
| `scripts/ibkr_contracts.py` | Auflösung über ISIN/Primärbörse/Währung aus dem Universum statt `_stock()` mit USD/NASDAQ | `CONTRACT_TABLE` (`:91-100`) aus Datei, `ContractSpec` + `isin` | geändert (Strang) |
| `scripts/ibkr_guards.py` | Notional-Cap (EUR) zusätzlich zu `MAX_QTY_PER_ORDER = 2` (`:349`); Abbaupfad | `check_notional()` neu, `check_size` bleibt für US | geändert (Strang) |
| `scripts/ibkr_executor.py` | Quelle wählbar (`--source paper-log|targets`), Währungsbehandlung, Fenster je MIC | additiv | geändert (Strang) |
| `scripts/ibkr_report.py` | Soll-Ist mit Prognosen; Slippage gegen `next_open` statt Close | additiv | geändert (Strang) |
| `scripts/state_maintenance.py` | Backup-Allow-Liste um Forecast-State erweitern | `:382-393` | geändert (Strang) |

---

## 2. Neu vs. geändert, mit Rebase-Fläche

### 2.1 Upstream-Dateien (Rebase-Risiko): Ziel null Änderungen

| Datei | Status in M3 | Begründung |
|---|---|---|
| `tradingagents/memory/log.py` | **nicht ändern** | Parser ist für additive SETTLEMENT-Schlüssel schon tolerant (`_parse_settlement`, `:359-366`); die Tag-Zeile bleibt `[date \| ticker \| rating \| pending]`. |
| `tradingagents/memory/settlement.py` | **nicht ändern** | Für die LLM-Lernschleife genügt die vorhandene Logik. Die Gate-Abrechnung (EUR, Kosten, `next_open`, 2 Horizonte) gehört in `forecast/settle.py`. Die Konstante `ENTRY_CONVENTION = "next_close"` (`:16`) bleibt unangetastet. |
| `tradingagents/default_config.py` | **nicht ändern** | `holding_period_days` (`:195`), `benchmark_ticker`/`benchmark_map` (`:196-214`) werden über `base_config` in `build_config` bzw. über `TRADINGAGENTS_BENCHMARK_TICKER` gesetzt. |
| `tradingagents/backtest.py` | **nicht nutzen fürs Gate** | Grid-Backtest ohne Portfolio, Kosten, Overlap-Kontrolle (`:9-14`, `_tally :87`); bleibt Upstream-Funktion. |
| `tradingagents/graph/trading_graph.py` | **optional 1–3 Zeilen** | Nur wenn Prognosefelder in der EU-`decision-log.md` gepinnt werden sollen: `terms.update(forecast_hooks.settlement_terms(company_name, trade_date, self.config))` nach `:401-405`. Die Datei ist schon strangberührt (Import `:18`, Aufruf `:391`). Empfehlung: **zunächst weglassen**, denn der Join über `(trade_date, ticker)` genügt. |
| `pyproject.toml` | **1 neues Extra** `forecast = [...]` | Analog den vorhandenen Extras `ibkr`/`ci` (`:33-60`). Ein Konflikt entsteht nur, wenn Upstream im selben Block Extras ändert. |
| Agents, Dataflows, Schemas | **nicht ändern** | Die Pipeline wird als Blackbox über `TradingAgentsGraph.propagate` aufgerufen, so wie es `daily_paper_run.run_ticker` (`:456-495`) heute tut. |

### 2.2 Strang-Dateien (kein Rebase-Risiko, eigene Verantwortung)

- **Neu:** `tradingagents/forecast/**`, `scripts/forecast_daily.py`, `scripts/news_archive.py`, `scripts/forecast_backtest.py`, `scripts/gate_report.py`, `scripts/label_ui.py`, `scripts/ibkr_targets.py`, `tests/test_forecast_*.py`, `scripts/FORECAST.md` (Handbuch) und die Workflows im privaten Repo.
- **Geändert:** `scripts/ibkr_decision.py`, `ibkr_contracts.py`, `ibkr_guards.py`, `ibkr_executor.py`, `ibkr_report.py`, `ibkr_publish.py` (Heartbeat-Feld für EU-Quelle), `state_maintenance.py`. `scripts/daily_paper_run.py` wird **importiert, nicht geändert**: `run_ticker`, `build_config` und `load_rates` sind wiederverwendbar, das Ladeschema zeigt `_load_sibling` (`:193`). Ein harter Punkt bleibt: `parse_tickers(max_tickers=10)` (`:96`). Für die Shortlist passt das, fürs Universum nicht. Deshalb ruft der Orchestrator nur die Shortlist durch diesen Pfad.

---

## 3. Data Flow

### 3.1 Täglicher Fluss (EU, Handelstag D)

```
D 15:30/16:30 UTC  Xetra/Euronext/LSE/SIX schließen (17:30 Ortszeit CET/CEST; LSE 16:30 UK = gleicher Zeitpunkt)
   │
   ├─ news_archive (laufend, z. B. stündlich 06–22 UTC)  → data/raw/news/D/*.jsonl  (first_seen_ts!)
   ▼
D ~20:40 UTC  eu-ingest: Vendor-EOD (Kurse, CA, FX, Index) + Fundamental-Deltas → data/raw/vendor/D/
              → Qualitätsstatus je Datentyp (vollständig / verspätet / fehlt) → quality/D.json
   ▼
D ~21:10 UTC  eu-forecast (needs: ingest grün ODER Qualitätsstatus erlaubt Degradation)
   1. cutoff = letzte geschlossene Sitzung je MIC (calendars.py), nicht previous_weekday()
   2. store.materialize(as_of=D, cutoff_ts) → Merkmale (Kurs, Fundamental)
   3. llm_features: neue Meldungen seit letztem Lauf → Cache-Treffer oder 1 Call je Meldung → Textmerkmale
   4. model.predict(ACTIVE) → p_5d, p_20d je ISIN (+ Variante ohne Textmerkmale: Ablation)
   5. costs: edge_h = f(p_h, erwartete Spannweite) − Kosten; Kandidaten = edge > Schwelle
   6. Shortlist (≤ N, z. B. 5): Upstream-Pipeline via daily_paper_run.run_ticker()
        → EU-decision-log.md (holding=5d, benchmark=EU-Benchmark) → veto.py
   7. sizing/risk: Zielgewicht → Zielstück (mit Referenzkurs close_D, Währung) → Caps, Drawdown-Stopp
   8. decide → runs/D/targets.json, Zeilen in forecasts.jsonl (model_id, code_sha, data_snapshot,
        p_5d, p_20d, target_pre_veto, target_post_veto, veto_reason, ref_price, ccy)
   9. Commit auf forecast-log (einziger Schreiber) + Heartbeat
   ▼
D+1 ~08:15–09:00 UTC (≥ 10–15 min nach Eröffnungsauktion; je MIC)   Lokaler Ausführer
   GitPaperLog(remote=private, branch=forecast-log).fetch → targets.json (schema_version prüfen)
   → Frische: zwischen cutoff-Sitzung D und jetzt hat keine Sitzung geschlossen (bestehende Regel, je MIC)
   → plan_target(target_qty, held, open) → Guards (Kill/Release vor jeder Order, Notional-Cap, Session)
   → Ledger intent → MKT-Order → Fill → ibkr-log (Fills, portfolio.json, Heartbeat)
   ▼
D+h  forecast/settle.py (im nächsten eu-forecast-Lauf): Label je Horizont, EUR, netto → outcomes.jsonl
     Upstream-Settlement der Shortlist-Einträge läuft wie bisher im _memory_step (trading_graph.py:333-365)
```

**Fallback:** Ist der Abendlauf rot, holt ein Morgenlauf ihn nach (z. B. 05:40 UTC). Er liegt im Sommer wie im Winter vor der Eröffnung (07:00 bzw. 08:00 UTC). Die Frischeregel bleibt unverändert, denn zwischen D und D+1 früh hat keine Sitzung geschlossen.

### 3.2 Wo das LLM sitzt: Merkmalsschritt **und** Veto, nie finale Entscheidung

| Rolle | Wo | Was fließt | Messung |
|---|---|---|---|
| **Merkmalslieferant** | `forecast/llm_features.py`, vor dem Modell | Je Meldung eine strukturierte Ausgabe → je (ISIN, Tag) aggregiert zu Zahlen | Ablation: Modell mit/ohne Textmerkmale, beide Prognosen in `forecasts.jsonl` |
| **Veto/Begründung** | Upstream-Pipeline für die Shortlist, nach dem Modell und vor dem Sizing | PM-Rating (`run_rating`), REVIEW, Jev-Schatten → `veto.py` | Kontrafaktum: `target_pre_veto` vs. `target_post_veto`, beide abgerechnet |
| **Nicht** | Finales Rating → Order | Die Blockleiter `BLOCKS` (`ibkr_decision.py:323`) gilt nur für den US-Altpfad | – |

Warum nicht die volle Pipeline als Merkmalslieferant: Sie kostet etwa 0,18 USD je Ticker (Memory-Notiz) und ca. 2 Minuten. Für 50–100 Titel × 21 Tage wären das 190–380 USD im Monat und damit über dem Budget von 150 €. Die Ausgabe ist zudem ein ungesteuerter Freitext mit 5-Stufen-Rating (o31 §3a). Ein Quick-Call je Meldung mit festem Schema ist billiger und lässt sich cachen und damit reproduzieren. Die Schätzung ist NIEDRIG belastbar; den Preis rechnet STACK.md nach.

Veto-Regel (Vorschlag, im Gate vorab festzuschreiben): Hat das Modell einen Kauf-Kandidaten und die Pipeline liefert `Sell`/`Underweight`, folgt Ziel 0. `REVIEW` oder Pipeline-Fehler lassen das Ziel unverändert, setzen das Veto aber nicht. Grund: Ein Ausfall des LLM darf das Modell nicht systematisch abschalten, der Fall wird markiert. `Buy`/`Overweight`/`Hold` → kein Veto. Ein Veto erzeugt nie einen Kauf und nie eine Vergrößerung.

### 3.3 Decision-Log und Settlement: was sich ändert und was nicht

**Zwei getrennte Messreihen.** Das ist bewusst so, weil eine Spalte zwei Größen nicht tragen kann (vgl. `ibkr-execution-architecture.md` §4.1).

| | Upstream-Settlement (LLM-Lernschleife) | Forecast-Settlement (Gate) |
|---|---|---|
| Datei | `forecast-log:decision-log.md` (EU) | `forecast-log:forecasts.jsonl` + `outcomes.jsonl` |
| Rechner | `settlement.fetch_returns` (yfinance-Closes) | `forecast/settle.py` (Vendor-PIT-Kurse aus dem Store) |
| Einstieg | `next_close` (`settlement.py:16`) | `next_open` (passt zur Morgenausführung) |
| Horizont | 5d (gepinnt `holding=5d`) | 5d **und** 20d je Prognosezeile |
| Benchmark | ein EU-Benchmark für alle EU-Ticker über `TRADINGAGENTS_BENCHMARK_TICKER` | dieselbe Serie aus dem Store, in EUR |
| Währung | jede Rendite in ihrer Währung (Docstring `settlement.py:27`) | in EUR umgerechnet (FX aus dem Store) |
| Kosten | keine | 20 bp je Seite, optional FX-Kosten |
| Rundung | 0,1 pp im Tag (`log.py:174-175`) | volle Präzision |

**SETTLEMENT-Zeile, rückwärtskompatibel (nur wenn der optionale Hook aus 2.1 gebaut wird):**

```
SETTLEMENT: holding=5d | benchmark=<EU-Benchmark> | entry=next_close | ccy=EUR | p_5d=0.574 | p_20d=0.611 | model=m3-2026-11-03-a1b2c3d4 | fc_entry=next_open | cost_bp=20
```

Regeln, am Code begründet:
- Bestehende Schlüssel `holding`, `benchmark` und `entry` behalten ihre Bedeutung. `entry` bleibt `next_close`, sonst schreibt `settle_pending` den Eintrag als `unknown entry convention` in `failed` und er bleibt dauerhaft pending (`settlement.py:161-164`).
- Neue Schlüssel bekommen eigene Namen (`fc_entry`, nicht `entry`). Werte ohne `|` und ohne Zeilenumbruch, sonst wirft `store_decision` `ValueError` (`log.py:52-55`), und `record_decision` fällt auf das alte Format ohne SETTLEMENT zurück (`trading_graph.py:411-419`). Das geht nicht verloren, aber das Pinning fehlt dann.
- `holding=20d` wäre technisch lesbar (Regex `(\d+)d`, `settlement.py:166`), verlangsamt aber die Reflexionsschleife um vier Wochen. Der 20d-Horizont gehört deshalb nur in den Forecast-Ledger.
- `ibkr_report.parse_decisions` (`scripts/ibkr_report.py:106`) und `ibkr_decision` lesen nur Tag und Rating. Zusätzliche Schlüssel stören sie nicht. Das sollte ein Test für den EU-Log absichern.

**Vertrag `targets.json`** (neu, `schema_version: 1`, Konsument `scripts/ibkr_targets.py`). Muster ist der Vertrag von `summary.json` (`ibkr_decision.read_summary`, `:190`):
`{schema_version, trade_date, cutoff_session{mic: date}, model_id, code_sha, data_snapshot, status, nav_eur, targets: [{isin, ticker, mic, currency, target_qty, ref_price, ref_price_ccy, p_5d, p_20d, edge_bp, veto, reason}]}`.
Die Ziele stehen als **Stückzahl**, berechnet in der CI aus `close_D`. Damit bleibt die bewährte Eigenschaft erhalten, dass im Order-Pfad kein Kurs abgeleitet wird (REQ-IBKR-68, `ibkr_contracts.py:89-90`). Der Notional-Cap prüft gegen `ref_price`.

### 3.4 Ausführer: konkrete Änderungen

| Stelle | Heute | M3 |
|---|---|---|
| `ibkr_decision.evaluate_decision` (`:253-301`) | Rating aus `decision-log.md` + Querprobe `summary.json` | bleibt für `--source paper-log`; neu `ibkr_targets.evaluate_target(row, doc)` mit `status`, `schema_version`, `veto`, Frische |
| `ibkr_decision.plan_order` (`:336-372`) + `BLOCKS` (`:323`) | Zielblöcke aus Rating, Toleranz 1 Block, Abbruch bei offenen Orders | neu `plan_target(target_qty, held_qty, open_qty, min_trade_qty)`: `Ziel − Ist − offen` (schließt N-07), Toleranzband in Stück/Notional, long-only bleibt |
| `ibkr_decision.load_xnys_calendar` (`:527-531`), `freshness` (`:584`) | nur XNYS | `load_calendar(mic)`; die Frischeregel ist schon sitzungsbasiert und bleibt inhaltlich gleich |
| `ibkr_guards.MAX_QTY_PER_ORDER = 2` (`:349`), `check_size` (`:352`) | Stück-Cap, lehnt ab, kürzt nie | zusätzlich `check_notional(qty, ref_price, ccy, fx, cap_eur)`; **Abbaupfad** gehört in den Plan, nicht in den Guard. Verkäufe über dem Cap werden in Tranchen ≤ Cap über mehrere Tage geplant (`staged-reduction`). Damit ist N-08 geschlossen, und der Guard bleibt „ablehnen statt kürzen". |
| `ibkr_contracts._stock` (`:83-84`), `CONTRACT_TABLE` (`:91-100`) | fest USD/NASDAQ, 3 Ticker | Tabelle aus `universe` (ISIN, `primaryExchange`, Währung, Symbol); Identitätspersistenz (`contracts.json`, `IDENTITY_FIELDS :169`) bleibt |
| `ibkr_decision.judge_preview` (`:386-445`, `CURRENCY_MISMATCH :430`) | Funds-Währung ≠ Kontowährung → abgelehnt | EUR/GBP/CHF-Käufe auf einem Paper-Konto mit Basiswährung USD treffen diese Prüfung. Die Regel (Auto-FX vs. Cash je Währung) muss vorher entschieden werden, siehe PITFALLS. |
| `tradingagents/portfolio.PortfolioContext` (`portfolio.py:29-31`) | eine `currency` für Cash | Upstream, nicht ändern. Das Sizing liest NAV und Positionen je Währung direkt aus `ibkr-log:portfolio.json` (Strang-Format), nicht aus `PortfolioContext`. |

---

## 4. Wo der tägliche Lauf läuft

| Kriterium | GitHub Actions (öffentliche Fork) | GitHub Actions (privates Begleit-Repo) | Lokal (Windows, Task Scheduler) |
|---|---|---|---|
| Lizenzdaten/News-Texte erlaubt | **nein**: Forks öffentlicher Repos sind zwingend öffentlich, Logs ebenfalls | ja | ja |
| Zuverlässigkeit unabhängig vom PC | ja | ja | nein; der PC muss abends **und** morgens laufen |
| Heartbeat/Alarm über vorhandenen Kanal | ja | ja (Status lesbar über Token) | nur über Push (Phase-7-Muster) |
| Kosten | frei | Free-Plan: 2.000 Minuten/Monat privat; ~20 min × 22 Tage ≈ 440 min (MITTEL) | Strom |
| Cron-Präzision | Verzug möglich, Spitzen zur vollen Stunde | dito | hoch |

**Empfehlung:** Rechnen im privaten Repo, Ausführung lokal.
- Der Workflow im privaten Repo checkt den Fork-Code an einem **gepinnten SHA bzw. Tag** aus. Das dient gleichzeitig der Reproduzierbarkeit.
- Cron-Minuten weg von `:00` legen (z. B. `40 20 * * 1-5`, `10 21 * * 1-5`). Der Abendlauf hat Stunden Puffer bis zur Eröffnung, deshalb ist Cron-Verzug unkritisch.
- Der US-Lauf `daily-paper-run.yml` (06:30 UTC) bleibt unberührt. Er kann über `vars.PAPER_RUN_TICKERS` leer oder pausiert werden (Entscheidung 1: zunächst nur Europa).
- Lokale Ausführung des Orchestrators (`python scripts/forecast_daily.py --local`) gibt es nur als Notpfad, mit identischem Code und identischer Datenquelle (Klon des privaten Repos).

Warum abends statt morgens vor der Eröffnung:
- Die EU-Börsen öffnen um 07:00 UTC (Sommer) bzw. 08:00 UTC (Winter). Ein Morgenlauf hätte bei LLM-Shortlist, Vendor-Latenz und Cron-Verzug kaum Puffer.
- EOD-Vendordaten liegen typischerweise wenige Stunden nach Schluss vor. Das ist NIEDRIG belastbar und je Vendor zu messen.
- Die Settlement-Konvention `next_open` passt sauber zur Morgenausführung.

---

## 5. Reproduzierbarkeit von Modellversionen

| Ebene | Maßnahme | Ort |
|---|---|---|
| Code | Jede Prognosezeile trägt `code_sha`. Der Rechen-Workflow checkt einen gepinnten SHA aus, und `uv.lock` ist Teil des SHA. | `forecasts.jsonl`, `targets.json` (analog `summary.json["commit"]`, `daily_paper_run.py`) |
| Rohdaten | append-only, nie überschreiben; Revisionen als neue Zeile mit `ingested_at` (bitemporal) | `data/raw/**` |
| Merkmale | `feature_set_version` (semver) + `data_snapshot` = Hash über die gelesenen Partitionen und den Cutoff | `store/`, Manifest |
| Modell | unveränderliches Verzeichnis `models/<model_id>/` mit `model.(txt|json)`, `calibrator.json` und `manifest.json`. Das Manifest enthält Trainingsfenster, Feature-Set, Data-Snapshot, Code-SHA, Bibliotheksversionen, Seed, Hyperparameter und OOS-Metriken. Die `model_id` enthält einen Inhalts-Hash. Kein Pickle. | privates Repo |
| Aktivierung | `models/ACTIVE.json` zeigt je Horizont auf eine `model_id`. Ein Wechsel ist ein eigener Commit mit Begründung. **Im Gate-Zeitraum ist der Zeiger eingefroren**, oder Retrain-Termine sind vorab festgelegt. | privates Repo |
| LLM | Modell-ID gepinnt (wie heute im Workflow), `TRADINGAGENTS_TEMPERATURE=0`, `prompt_hash`. Die **Antworten werden gecacht** und sind damit die Reproduktionsquelle. Temperatur 0 ist bei Providern nicht garantiert deterministisch, deshalb heißt Wiederholen „Cache lesen", nicht „neu fragen". | `llm-cache/` |
| Replay | `scripts/forecast_backtest.py --replay <date> --model <id>` muss `targets.json` des Tages bitgleich reproduzieren. Das wird als Test im CI geprüft (Fixture-Tag). | Tests |

---

## 6. Architectural Patterns

### Pattern 1: Bitemporaler Feature-Store mit hartem Cutoff
**What:** Jeder Wert trägt `as_of_date` (wofür er gilt) und `knowledge_ts` (wann er bekannt war). Abfragen filtern immer `knowledge_ts <= cutoff`.
**When to use:** immer, wenn Fundamentaldaten, Index-Mitgliedschaft oder News eingehen.
**Trade-offs:** mehr Speicher und Disziplin. Dafür ist es die einzige Verteidigung gegen Look-ahead und Survivorship (Codex P0). Das bestehende `as_of`-Kappen im Router (`dataflows/router.py`) ist dasselbe Prinzip für die LLM-Tools.

```python
def features_as_of(store, isins, cutoff_ts, feature_set):  # forecast/store.py
    return store.query("""
        SELECT isin, feature, arg_max(value, knowledge_ts) AS value
        FROM features WHERE knowledge_ts <= ? AND feature_set_version = ? AND isin IN ?
        GROUP BY isin, feature""", [cutoff_ts, feature_set, isins])
```

### Pattern 2: Reiner Kern, dünne Ränder (wie im IBKR-Strang)
**What:** `labels`, `costs`, `decide`, `sizing`, `risk`, `veto`, `settle` und `plan_target` sind reine Funktionen. I/O (Vendor, Git, LLM, Broker) liegt nur in Orchestrator und Adaptern.
**When to use:** überall im Entscheidungspfad. Das Muster ist im Repo bewährt: `ibkr_decision.py` und `ibkr_guards.py` sind rein, `ibkr_broker.py` ist der einzige `ib_async`-Import.
**Trade-offs:** mehr Parameter-Durchreichen. Dafür lassen sich Backtest und Live-Lauf **mit demselben Code** fahren. Das ist die Voraussetzung dafür, dass das Gate etwas über den Live-Pfad aussagt.

### Pattern 3: Kontrafaktisches Logging je Stufe
**What:** Je Kandidat werden `p` (mit/ohne Text), `target_pre_veto`, `target_post_veto`, `target_pre_risk` und `target_final` geschrieben.
**When to use:** sobald mehrere Stufen das Ergebnis verändern (Entscheidung 3: Beiträge getrennt messen).
**Trade-offs:** breitere Zeilen. Ohne das Muster ist der Beitrag von LLM-Merkmal und Veto nicht messbar.

### Pattern 4: Ein Schreiber je Branch (besteht, wird erweitert)
**What:** `paper-log` schreibt nur `daily-paper-run`, `ibkr-log` nur der lokale Ausführer (`ibkr_publish.py:29-30`), `forecast-log` nur `eu-forecast`. Gelesen wird über `GitPaperLog(repo, remote, branch)` (`ibkr_paperlog.py:82-106`), das schon generisch über Remote und Branch ist.
**Trade-offs:** Joins passieren beim Lesen. Dafür gibt es strukturell keine Push-Konflikte (`daily-paper-run.yml` pusht ohne Rebase).

---

## 7. Anti-Patterns

### Anti-Pattern 1: Die volle Agenten-Pipeline als Merkmal über das ganze Universum
**What people do:** Für jeden Titel täglich `propagate()` laufen lassen und das Rating als Feature nehmen.
**Why it's wrong:** Das sprengt das Budget (vgl. 3.2), ist nicht reproduzierbar (Sampling), und historisch lässt es sich nicht validieren: Das LLM „kennt" die Zukunft vor seinem Wissensstichtag.
**Do this instead:** Quick-Extraktion je Meldung, gecacht. LLM-Merkmale werden **nur prospektiv** (Paper ab Archivstart) und als Ablation bewertet. Der historische Walk-forward nutzt nur Kurs- und Fundamentalmerkmale.

### Anti-Pattern 2: `entry` in der SETTLEMENT-Zeile umdeuten oder die Tag-Zeile erweitern
**What people do:** `entry=next_open` oder ein siebtes Feld `p=0.6` in `[date | ticker | …]` schreiben.
**Why it's wrong:** `settle_pending` bricht bei unbekannter Konvention ab und lässt den Eintrag pending. Feld 7+ wird als `resolved:`-Kandidat gelesen (`log.py:336-338`), und `ibkr_report`/`ibkr_decision` parsen die Tags.
**Do this instead:** additive Schlüssel mit eigenem Namen, Prognosen im eigenen Ledger.

### Anti-Pattern 3: Upstream-Settlement oder `backtest.py` als Gate-Nachweis
**Why it's wrong:** Es gibt keine Kosten, keine Währung, nur einen Horizont und überlappende Fenster. Die Kurse sind yfinance-adjusted und heute rückwirkend verändert (Codex H-12, N-04). Ties fallen aus dem Nenner (N-02).
**Do this instead:** `forecast/settle.py` + `gate.py` auf Store-Kursen.

### Anti-Pattern 4: Lizenzdaten oder News-Volltexte in der öffentlichen Fork
**Why it's wrong:** Die Fork ist zwingend öffentlich, inklusive Actions-Logs. Das ist ein Vertrags- und Urheberrechtsrisiko, und rückgängig machen lässt es sich nicht.
**Do this instead:** privates Begleit-Repo bzw. privater Speicher. Öffentlich gehen nur abgeleitete Prognosen und Ziele, falls überhaupt.

### Anti-Pattern 5: Sizing im Ausführer
**Why it's wrong:** Dann bräuchte der Order-Pfad einen Kurs (REQ-IBKR-68). Backtest und Live würden auseinanderlaufen, weil der Ausführer nicht im Backtest läuft.
**Do this instead:** Sizing in der CI (`forecast/sizing.py`). Der Ausführer setzt Stückziele nur um und prüft Caps.

### Anti-Pattern 6: Modell im Gate-Zeitraum still nachtrainieren
**Why it's wrong:** Die OOS-Strecke wird unbemerkt zur In-Sample-Strecke, und das Gate verliert seinen Wert.
**Do this instead:** `ACTIVE.json` einfrieren, Retrain nur nach vorab registriertem Plan, jede Prognose trägt `model_id`.

---

## 8. Scaling Considerations

| Universumsgröße | Anpassung |
|---|---|
| 30–60 Titel (Start) | Parquet + DuckDB im Git-Repo, ein Workflow-Job, Shortlist ≤ 5 |
| 100–200 Titel | News-Volumen wächst (Schätzung 250 MB/Jahr Rohtext, NIEDRIG). Monatspartitionen, LLM-Cache ausdünnen, eventuell Objektspeicher statt Git für `data/raw` |
| STOXX 600 | Vendor-Kosten und LLM-Calls je Meldung sind der Engpass, nicht Rechenzeit. Relevanzfilter vor dem LLM, Batch-API |

**Erster Engpass:** Budget für LLM und Vendor, nicht Technik. **Zweiter Engpass:** Laufzeit der Shortlist-Pipeline (~2 min/Ticker, seriell) gegen das 60-Minuten-Timeout des Jobs.

---

## 9. Integration Points

### External Services

| Dienst | Muster | Hinweise |
|---|---|---|
| PIT-Datenvendor (EU-Kurse, Fundamentaldaten, Kapitalmaßnahmen) | Batch-Pull im Ingest, Rohdatei unverändert speichern | Wahl und Lizenz siehe STACK.md; Lieferzeit nach Schluss messen |
| News/Meldungen (RSS, IR-Seiten, Pflichtmeldungen) | Polling, `first_seen_ts` ist maßgeblich, nicht `published_ts` | Volltext nur privat |
| LLM (Anthropic, gepinnt) | Quick-Modell für Merkmale; Deep/Quick für die Shortlist | Kosten über `budget.py` (`SpendTracker`) und `scripts/paper_run_rates.json` |
| IBKR (lokal) | unverändert `ib_async` über `ibkr_broker.py` | EU-Berechtigungen, Währungen, Auktionen |
| `exchange_calendars` | heute im Extra `ibkr` (`pyproject.toml:53`) | gehört auch ins Extra `forecast` |

### Internal Boundaries

| Grenze | Kommunikation | Hinweise |
|---|---|---|
| `forecast` ↔ Upstream-Graph | `TradingAgentsGraph.propagate` über `daily_paper_run.run_ticker` | keine Imports in Agents/Graph-Interna |
| `forecast-log` ↔ Ausführer | Datei-Vertrag `targets.json` (`schema_version`) | Vertragstest wie für `summary.json` |
| `ibkr-log` ↔ `forecast` | `portfolio.json` (NAV, Positionen je Währung) als Eingang des Sizing | Frischeprüfung wie `load_fresh_portfolio` (`daily_paper_run.py:151-190`) |
| Jev ↔ `forecast` | Schatten, Labels aus `label_ui` | Kalibrierung getrennt von der Kursprognose (Codex) |

---

## 10. Build Order (abhängigkeitsgetrieben)

| # | Baustein | hängt ab von | Warum hier |
|---|---|---|---|
| 0 | Umschalten: M2-Phase 6 abschließen, Phase-7-Stand übernehmen (`ibkr_publish`, `ibkr_report`, Portfolio-Feed) | – | Der Ausführer-Rückkanal ist Voraussetzung für das Sizing (NAV) |
| 1 | **News-Archiv + privates Repo** (`news_archive.py`, Tagesstatus) | – | Die Uhr läuft, jeder Tag fehlt sonst für immer. Das ist eine kleine, unabhängige Aufgabe, gern als erster Plan |
| 2 | Universum (ISIN/MIC/Währung/Benchmark), `calendars.py`, FX, PIT-Vendor-Ingest, Store-Schema | 1 (Repo) | Grundlage für Labels und Merkmale |
| 3 | `labels.py`, `costs.py`, `settle.py`, Baselines, `walkforward.py`, `gate.py` (Gate-Kriterien vorab als Datei registriert) | 2 | **Validierung vor Modell.** Sonst wird das Modell auf den Messrahmen hin gebaut |
| 4 | Merkmale (Kurs/Fundamental), `model.py`, Kalibrierung, `registry.py`; historischer Walk-forward-Bericht | 3 | Erste ehrliche No-Go-Möglichkeit, noch ohne LLM-Kosten |
| 5 | `llm_features.py` + Cache, Shortlist-Pipeline-Aufruf, `veto.py`, Ablation | 1, 4 | Kann nur prospektiv gemessen werden, deshalb möglichst früh im Paper |
| 6 | `sizing.py`, `risk.py`, `decide.py`, `forecast_daily.py`, `targets.json`-Vertrag; **Schattenbetrieb ohne Orders** | 4, 0 | Der Vertrag fixiert die Schnittstelle zu Schritt 7 |
| 7 | EU-Ausführer: `ibkr_targets.py`, Kalender je MIC, ISIN-Auflösung, Notional-Cap, Abbaupfad, Währung | Vertrag aus 6 (Schema reicht), 0 | **parallel zu 4–6 baubar**; IBKR-EU-Berechtigungen früh klären |
| 8 | Betrieb (übernimmt M2 7–8): Heartbeat `forecast-log`, Backup inkl. privates Repo und IBKR-State, Soll-Ist mit Prognosen, Alarm | 6, 7 | Ab dann zählt die Paper-Bewährung, mindestens 6 Monate laut Gate |
| 9 | Gate-Protokoll: Auswertung nach ≥ 300 Fällen und ≥ 6 Monaten, Go/No-Go-Commit | 8 + Zeit | No-Go ist ein gültiges Ergebnis |

Kritischer Pfad: 1 → 2 → 3 → 4 → 6 → 8 → Zeit → 9. Die 6 Monate Paper beginnen frühestens mit 6 und 8. Jede Verzögerung vor 6 verschiebt das Gate direkt.

**Vertiefende Recherche je Phase nötig:** 2 (Vendor-Lizenz, PIT-Qualität, Symbolik ISIN ↔ Yahoo ↔ IBKR), 3 (Bootstrap mit Zeit- und Titelabhängigkeit, Mehrfachtest), 7 (IBKR-EU-Routing, Auktionen, Währungskonto). Standardmuster ohne eigene Recherche: 6 (folgt dem `daily_paper_run`-Muster) und 8 (folgt Phase 7).

---

## Sources

- **Code (HOCH, Arbeitsbaum 2026-10-20):** `tradingagents/memory/log.py` (`store_decision :32-73`, `_parse_entry :323-357`, `_parse_settlement :359-366`), `tradingagents/memory/settlement.py` (`ENTRY_CONVENTION :16`, `resolve_benchmark :19-40`, `fetch_returns :68-125`, `settle_pending :136-201`), `tradingagents/graph/trading_graph.py` (`_memory_step :333-365`, `record_decision :388-419`), `tradingagents/default_config.py` (`_ENV_OVERRIDES :10-34`, `:173-214`), `tradingagents/portfolio.py :23-47`, `scripts/daily_paper_run.py` (`parse_tickers :96`, `previous_weekday :126`, `build_config :374-391`, `run_ticker :456-495`), `scripts/ibkr_decision.py` (`evaluate_decision :253`, `BLOCKS :323`, `plan_order :336`, `judge_preview :386`, `XnysSessions :469`, `freshness :584`), `scripts/ibkr_guards.py` (`MAX_QTY_PER_ORDER :349`), `scripts/ibkr_contracts.py` (`_stock :83`, `CONTRACT_TABLE :91`), `scripts/ibkr_paperlog.py` (`GitPaperLog :82-106`), `scripts/ibkr_publish.py :29-33`, `scripts/ibkr_report.py :106`, `.github/workflows/daily-paper-run.yml :28-80`, `pyproject.toml :21-60`
- **Planung (HOCH/MITTEL):** `.planning/MILESTONE-CONTEXT.md`, `261019-o31-RESEARCH-architecture.md`, `261019-oxc-CODEX-REVIEW.md`, `.planning/research/ibkr-execution-architecture.md`
- **Extern:** [GitHub Docs: About permissions and visibility of forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-permissions-and-visibility-of-forks) (HOCH: Forks öffentlicher Repos sind öffentlich) · [Flutter-Doku mit Zitat der GitHub-Schedule-Hinweise](https://flutter.googlesource.com/mirrors/flutter/+/refs/heads/main/docs/infra/Scheduled-Recurring-Tasks.md) (MITTEL: Verzug bei hoher Last, besonders zur vollen Stunde) · [Deutsche Börse Handelskalender/-zeiten](https://www.eurexchange.com/cash-en/trading/trading-calendar-and-trading-hours), [Wiener Börse Xetra-T7-Zeiten](https://wienerborse.at/en/trading/trading-information/trading-hours) (MITTEL: Xetra 09:00–17:30 CET, Schlussauktion ab 17:30) · Euronext/LSE/SIX-Zeiten nicht separat verifiziert (NIEDRIG; via `exchange_calendars` im Code prüfen)

---
*Architecture research for: M3 Vorhersage-Engine (Europa)*
*Researched: 2026-10-20*
