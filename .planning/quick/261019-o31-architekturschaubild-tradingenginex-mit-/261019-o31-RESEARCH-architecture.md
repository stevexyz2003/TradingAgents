# Quick 261019-o31 (Teil B): Architektur und Vorhersagemethoden - Research

**Researched:** 2026-10-19 · `main` @ `b0989aa` · `origin/main` Stand 2026-10-16
**Domain:** Knoten und Kanten für das Architekturschaubild; ehrliche Bestandsaufnahme der Vorhersagemethoden
**Confidence:** HIGH (alles am Code belegt, Zeilenangaben aus diesem Stand). Ausnahmen sind im Assumptions Log markiert.

<user_constraints>
## User Constraints (aus CONTEXT.md, wörtlich gekürzt; verbindlich)

- **Anforderungsumfang:** alles inklusive Upstream (M1 `.planning/MILESTONE.md`, M2 `.planning/REQUIREMENTS.md` REQ-IBKR-xx, Upstream-Funktionen). Status je Anforderung (umgesetzt / teilweise / offen / verworfen bzw. Override) mit Herkunft (Upstream/Strang), Phase oder Quick-Task und Nachweis. Am Code und an `.planning` belegen, nicht raten. Phase 6 läuft parallel: Stand mit Datum und HEAD-SHA ausweisen. *(Anforderungsmatrix = Teil A, nicht hier.)*
- **Darstellung:** interaktive HTML-Seite, ein großes Architekturdiagramm (Upstream-Kern, Strang-Module Jev/Patterns/Budget/State-Maintenance/IBKR-Ausführer, GitHub Actions → `paper-log`, lokaler IBKR-Ausführer mit IB Gateway, Datenquellen, Datenflüsse), darunter filterbare Anforderungsmatrix, Klick auf Komponente zeigt ihre Anforderungen, eigener Abschnitt „Vorhersagemethoden". Daten eingebettet, statisch. Beide Themes, Handybreite. Seite deutsch.
- **Methodenteil:** ehrliche Bestandsaufnahme je Methode: Datei, was sie tut, Einfluss (entscheidet / Eingabe / Nachauswertung), was fehlt. Stochastisch/statistisch, heuristisch, semantische Auswertung von Ticker-Meldungen. **Keine Empfehlungsliste, nur Lücken benennen.**
- **Claude's Discretion:** visuelle Gestaltung, Diagrammtechnik (Inline-SVG oder Mermaid), Gruppierung.
</user_constraints>

## Project Constraints (aus CLAUDE.md / Memory)
- `.planning/` deutsch, Code/Commits englisch. Graphify/Serena nur Navigation, kein Gate.
- `graphify-out/GRAPH_REPORT.md` ist vom **2026-10-12** (vor Phase 4-6, vor `patterns/`) → für dieses Schaubild **veraltet**, nur als grobe Community-Liste brauchbar. Alles unten ist direkt am Code geprüft.
- Kein Commit in diesem Schritt.

---

## 1. Architektur: Knoten

Zonen (Vorschlag für Swimlanes/Gruppen): **Z1** GitHub Actions (Cloud, täglich) · **Z2** Branch `paper-log` (Git-Speicher) · **Z3** Lokaler Windows-Host (Operator, IBKR) · **Z4** Externe Daten-/LLM-Anbieter · **Z5** LangGraph-Pipeline (läuft in Z1 bzw. lokal per CLI) · **Z6** Speicher/Caches (lokal oder Runner-Temp).

### 1a. Laufzeit- und Betriebsknoten

| id | Label | Zone | Herkunft | Hauptdatei(en) | Beschreibung |
|---|---|---|---|---|---|
| `gha_daily` | Daily Paper Run (Workflow) | Z1 | Strang | `.github/workflows/daily-paper-run.yml` | Cron `30 6 * * 2-6` UTC (Di-Sa), Preflight → Lauf → Artefakt → Commit auf `paper-log`; `concurrency: daily-paper-run`, kein Cancel. |
| `paper_runner` | daily_paper_run.py | Z1 | Strang | `scripts/daily_paper_run.py` | Tickerliste (Default AAPL,MSFT,NVDA), `trade_date` = voriger Wochentag, harte Kostenbremse je Ticker (Default 1,50 USD) und je Tag, setzt `memory_log_path=<state>/decision-log.md`, `checkpoint_enabled=False` (`:264-281`). Optional `--portfolio` mit Frischeprüfung `as_of` (`:137-176`). |
| `gha_ci` | CI | Z1 | Upstream+Strang | `.github/workflows/ci.yml` | Tests/Lint (Extra `ci` = dev+ibkr, `pyproject.toml`). |
| `gha_artifact` | Run-Artefakt `paper-run-N` | Z1 | Strang | Workflow `upload-artifact` | Reports + `summary.md`, 90 Tage Aufbewahrung. |
| `paper_log` | Branch `paper-log` | Z2 | Strang | Workflow `:144-211` | Track Record: `decision-log.md`, `index.md` (append), `runs/<date>/summary.json` + `<TICKER>.md`. Ein Schreiber (CI); `reset --hard FETCH_HEAD` → `git add -A` → push ohne Rebase. |
| `executor` | IBKR-Ausführer (CLI) | Z3 | Strang (M2) | `scripts/ibkr_executor.py` | Unterbefehle `account`, `resolve`, `preview`, `execute [--live]`; manuell vom Operator gestartet (kein Task Scheduler eingerichtet). Exit-Codes 0-10, 20. |
| `ibkr_paperlog` | paper-log-Leser | Z3 | Strang | `scripts/ibkr_paperlog.py` | `git fetch` + `git cat-file`, ohne Working Tree; liest nur `decision-log.md` und `runs/<date>/summary.json`. |
| `ibkr_decision` | Entscheidungslogik (rein) | Z3 | Strang | `scripts/ibkr_decision.py` | Neuester Eintrag je Ticker, Frische (XNYS-Kalender), Soll-Rechnung `BLOCKS={Buy:2, Overweight:1, Underweight:0, Sell:0}`, Hold → skip, long-only, Toleranzband 1 Block (`:323-375`), Urteil über whatIf. |
| `ibkr_guards` | Leitplanken (rein) | Z3 | Strang | `scripts/ibkr_guards.py` | RELEASE-/KILL-Datei fail-closed, vor **jeder** Order geprüft; `MAX_QTY_PER_ORDER = 2` (lehnt ab, kürzt nie, `:348-358`); Idempotenzschlüssel `<trade_date>|<TICKER>`; Quellenabgleich Konto/Position/„schon ausgeführt". |
| `ibkr_contracts` | Kontrakt-Auflösung (rein) | Z3 | Strang | `scripts/ibkr_contracts.py` | Ticker → Suchschlüssel, Allow-List, persistierte Identität (`contracts.json`), Handelbarkeit/Session. |
| `ibkr_broker` | IBKR-Adapter | Z3 | Strang | `scripts/ibkr_broker.py` | Einziger Import von `ib_async==2.1.0` (`:486`); Schreibsperre vor dem Socket, Paper-Guard `managedAccounts == ["DUQ634065"]`, `asyncio.wait_for` um jede Anfrage. |
| `ibkr_ledger` | Ausführungs-Ledger | Z3 | Strang | `scripts/ibkr_ledger.py` | Append-only JSONL, Write-ahead `intent` (fsync) vor Order, `orderRef` = Entscheidungsschlüssel, paper-log-SHA als Provenienz; getrennte Dateien dry/live. |
| `ibkr_md` | Marktdaten-Stream | Z3 | Strang | `scripts/ibkr_market_data.py` | Eigene Session/clientId, delayed (`reqMarketDataType(3)`), bewusst **nicht** im Orderpfad (REQ-IBKR-26). |
| `ib_gateway` | IB Gateway / TWS (Paper) | Z3 | extern | `.env` `IBKR_HOST/PORT` | Konto `DUQ634065`; gemessener Port **7497** (TWS-Paper-Port, nicht 4002; `scripts/IBKR_EXECUTION.md:115`). |
| `ibkr_server` | IBKR Paper-Konto (Simulator) | Z4 | extern | – | Füllt Market-Orders simuliert. |
| `state_maint` | state_maintenance.py | Z3 | Strang | `scripts/state_maintenance.py` | `verify` / `prune` (Dry-Run-Default) / `backup` für Decision-Log, Checkpoints, Reports; bewusst kein `rotate`. Vom Ausführer für `verify` der paper-log-Kopie genutzt. |
| `pattern_eval` | pattern_eval.py | Z3 | Strang | `scripts/pattern_eval.py` | CLI für die Musterauswertung gegen `paper-log:decision-log.md`. |
| `smoke` | Smoke-Skripte | Z3 | Strang | `scripts/smoke/ibkr_order_probe.py`, `jev_live_smoke.py`, `stub_llm.py` | Manuelle Proben: Orderhistorie/whatIf ohne Senden; Jev-Live-Probe; Stub-LLM für kostenlose Läufe. |
| `cli` | CLI (interaktiv) | Z3 | Upstream | `cli/main.py`, `cli/run.py` | Interaktiver Einzellauf; nutzt dieselbe Pipeline und `budget`. |

### 1b. Bibliothek: Querschnitt (Graph-Hülle)

| id | Label | Zone | Herkunft | Hauptdatei(en) | Beschreibung |
|---|---|---|---|---|---|
| `tag` | TradingAgentsGraph | Z5 | Upstream | `tradingagents/graph/trading_graph.py` | Baut zwei LLM-Stufen (quick/deep), Memory-Log, Reflector, Graph; `_run_graph` streamt, danach `record_decision` (`:388-419`). |
| `llm_factory` | LLM-Clients | Z5 | Upstream | `tradingagents/llm_clients/factory.py` u. a. | OpenAI, Anthropic, Google, Azure, Bedrock, OpenAI-kompatible; `temperature` nur weitergereicht wenn gesetzt (Default `None`). Paper-Lauf: anthropic, deep `claude-sonnet-5-5`, quick `claude-haiku-5-5`. |
| `budget` | Budget/Kostenbremse | Z5 | **Strang** (nicht in `origin/main`) | `tradingagents/budget.py` | `SpendTracker` als LangChain-Callback; bricht mit `BudgetExceededError` ab, Teilzustand wird gespeichert. Raten aus `scripts/paper_run_rates.json`. |
| `router` | Daten-Router | Z5 | Upstream | `tradingagents/dataflows/router.py`, `agents/tools.py` | Tool → Vendor-Kette; `as_of`-Kappung gegen Look-ahead; `DATA_UNAVAILABLE`/`NO_DATA_AVAILABLE`-Sentinels statt Erfinden. |
| `structured` | Strukturierte Ausgaben | Z5 | Upstream | `agents/schemas.py`, `agents/structured.py` | `SentimentReport`, `ResearchPlan`, `TraderProposal`, `PortfolioDecision` (Pydantic), Freitext-Fallback. |
| `rating` | Rating-Extraktion | Z5 | Upstream | `agents/rating.py` | 5er-Skala, Regex auf „Rating: X"; widersprüchlich/fehlend → `REVIEW`, nie Hold. |
| `jev_hooks` | Jev-Review | Z5 | **Strang** | `tradingagents/jev/hooks.py`, `jev/client.py` | Nach dem Lauf, vor dem Log: Fallback nur bei `REVIEW` und Konfidenz ≥ 0,9; sonst Schattenprüfung. Sidecar `jev_review_<date>.json`. |
| `post_screen` | Social-Post-Screening | Z5 | Upstream (#1376) | `agents/post_screen.py` | Nur mit `TYPESAFE_API_KEY`; im Paper-Lauf bewusst **aus** (Workflow-Kommentar). |
| `memory_log` | Memory-Log + Settlement | Z5 | Upstream | `memory/log.py`, `memory/settlement.py`, `memory/reflection.py` | Speichert Entscheidung pending, rechnet nach 5 Handelstagen raw/alpha vs. Benchmark ab, LLM-Reflexion, liefert `past_context`. |
| `patterns` | Musterauswertung | Z6/Z3 | **Strang** | `tradingagents/patterns/signals.py`, `evaluate.py` | 6 kursbasierte Muster, Wilson-95-%, `MIN_N=20`; nur Nachauswertung, nirgends im Graph importiert. |
| `backtest` | Backtest/Summarize | Z5 | Upstream (#1234) | `tradingagents/backtest.py` | Trefferquote/mittleres Alpha über Ticker×Datum-Gitter. |
| `portfolio` | PortfolioContext | Z5 | Upstream (#1304) | `tradingagents/portfolio.py` | Eingangs-Bestand (was gehalten wird) für Trader/Risiko/PM. |
| `reporting` | Reports MD/HTML | Z5 | Upstream | `reporting.py`, `report_html.py` | Speichert Berichte je Lauf. |

### 1c. LangGraph-Pipeline (Reihenfolge verifiziert, `graph/setup.py:118-187`, `conditional_logic.py`)

| id | Label | LLM-Stufe | Herkunft | Datei | Liest aus State | Schreibt |
|---|---|---|---|---|---|---|
| `a_market` | Market Analyst | quick | Upstream | `agents/analysts/market_analyst.py` | Tools `get_stock_data`, `get_indicators`, `get_verified_market_snapshot` | `market_report` |
| `a_social` | Sentiment Analyst | quick | Upstream | `agents/analysts/sentiment_analyst.py` | **keine Tools**, vorab geholt: Yahoo-News, StockTwits (30), Reddit-RSS | `sentiment_report` (`SentimentReport`) |
| `a_news` | News Analyst | quick | Upstream | `agents/analysts/news_analyst.py` | Tools `get_news`, `get_global_news`, `get_macro_indicators`, `get_prediction_markets` | `news_report` |
| `a_fund` | Fundamentals Analyst | quick | Upstream | `agents/analysts/fundamentals_analyst.py` | Tools `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` | `fundamentals_report` |
| `mem_node` | Memory Log (Knoten) | quick (Reflector) | Upstream | `trading_graph.py:333-365` | Decision-Log; Kurse yfinance | `past_context`, `memory_note` |
| `bull` | Bull Researcher | quick | Upstream | `researchers/bull_researcher.py` | 4 Reports + Debattenverlauf | `investment_debate_state` |
| `bear` | Bear Researcher | quick | Upstream | `researchers/bear_researcher.py` | dito | dito |
| `rm` | Research Manager | **deep** | Upstream | `managers/research_manager.py` | nur Debattenverlauf (nicht die Rohreports) | `investment_plan` (`ResearchPlan`, 5er-Rating) |
| `trader` | Trader | quick | Upstream | `trader/trader.py` | `investment_plan`, `market_report`, Portfolio | `trader_investment_plan` (`TraderProposal`: Aktion, Entry, Stop, Sizing) |
| `r_aggr` | Aggressive Analyst | quick | Upstream | `risk_mgmt/aggressive_debator.py` | 4 Reports, Trader-Plan, Portfolio, Verlauf | `risk_debate_state` |
| `r_cons` | Conservative Analyst | quick | Upstream | `risk_mgmt/conservative_debator.py` | dito | dito |
| `r_neut` | Neutral Analyst | quick | Upstream | `risk_mgmt/neutral_debator.py` | dito | dito |
| `pm` | Portfolio Manager | **deep** | Upstream | `managers/portfolio_manager.py` | Risikodebatte, `investment_plan`, Trader-Plan, `past_context`, Portfolio | `final_trade_decision` (`PortfolioDecision`: Rating, Kursziel, Horizont) |

Jeder Analyst ist ein **eigener Subgraph** (`_analyst_graph`, `setup.py:51-91`): `agent ⇄ tools` bis `max_tool_rounds=20`, danach `wrap_up` (Zwangsbericht). Sentiment hat keine Tools → `agent → END`.

### 1d. Datenspeicher

| id | Label | Zone | Herkunft | Ort | Beschreibung |
|---|---|---|---|---|---|
| `s_declog` | `decision-log.md` | Z2 | Upstream-Format, Strang-Ablage | paper-log; lokal `~/.tradingagents/memory/trading_memory.md` | Tag `[date | TICKER | Rating | pending]` bzw. `[… | raw | alpha | 5d | resolved:…]`, `<!-- ENTRY_END -->`; Idempotenz je (date,ticker). Unbegrenzt (keine Rotation). |
| `s_summary` | `runs/<date>/summary.json`, `index.md` | Z2 | Strang | paper-log | Maschinenlesbarer Tageslauf (`schema_version 1`), Eingabe des Ausführers. |
| `s_cache` | OHLCV-Cache | Z6 | Upstream | `~/.tradingagents/cache` (`data_cache_dir`) | 5 Jahre je Symbol als CSV, auf `as_of` gekappt. |
| `s_ckpt` | Checkpoints (SQLite) | Z6 | Upstream | `<cache>/checkpoints/<TICKER>.db` (`graph/checkpointer.py`) | Resume nach Absturz; im Paper-Lauf aus. |
| `s_results` | State-Logs/Reports | Z6 | Upstream | `results_dir` (`~/.tradingagents/logs` bzw. `$OUT_DIR/logs`) | Volle Zustände, Jev-Sidecar. |
| `s_ibkr` | IBKR-State | Z3 | Strang | `%LOCALAPPDATA%\TradingEngineX\ibkr\` | `ledger.jsonl`, `ledger-dryrun.jsonl`, `contracts.json`, `preview.json`, `RELEASE`, `KILL`, `paper-log/decision-log.md` (Kopie), `logs/ibkr_executor.log`. Außerhalb jedes Git-Trees erzwungen. |
| `s_rates` | Preistabelle | Z1 | Strang | `scripts/paper_run_rates.json` | USD/1M Tokens je Modell für die Kostenbremse. |

### 1e. Externe Anbieter (Z4)

| id | Label | genutzt von | im Paper-Lauf aktiv? |
|---|---|---|---|
| `x_yf` | Yahoo Finance (yfinance) | OHLCV, Indikatoren, News (`yf.Search`), Fundamentals-Übersicht, Insider, Settlement-Kurse | ja (Default aller Kernkategorien) |
| `x_sec` | SEC EDGAR (XBRL companyfacts) | Bilanz/Cashflow/GuV | ja (`fundamental_data: "sec_edgar,yfinance"`) |
| `x_av` | Alpha Vantage | alternative Vendor-Kette | **nein**: `data_vendors` ist nicht per Env überschreibbar, Default `yfinance` |
| `x_fred` | FRED | `get_macro_indicators` | nur mit `FRED_API_KEY` (optional, degradiert zu Sentinel) |
| `x_poly` | Polymarket (keyless) | `get_prediction_markets` | ja (optional-Kategorie) |
| `x_st` | StockTwits API | Sentiment Analyst | ja |
| `x_reddit` | Reddit RSS (wallstreetbets, stocks, investing) | Sentiment Analyst | ja |
| `x_llm` | LLM-Anbieter (Anthropic im Paper-Lauf) | alle LLM-Knoten, Reflector | ja |
| `x_jev` | Jev/TypeSafe (über OpenRouter oder api.typesafe.ai) | `jev_hooks` (JEV_API_KEY), `post_screen` (TYPESAFE_API_KEY) | Review: nur wenn Secret gesetzt; Screening: aus |

Nicht vorhanden (grep leer): Google News, Finnhub, eigene Nachrichten-Scraper.

---

## 2. Architektur: Kanten

### 2a. Pipeline (verifiziert)

| von | nach | was fließt / Bedingung |
|---|---|---|
| START | `a_market`, `a_social`, `a_news`, `a_fund`, `mem_node` | parallel; `company_of_interest`, `trade_date`, `asset_type`, Portfolio |
| `a_*`, `mem_node` | `bull` | Join: erst wenn alle Berichte + `past_context` da sind (`setup.py:170`) |
| `bull` | `bear` | Argument; Router `should_continue_debate` (letzter Sprecher Bull → Bear) |
| `bear` | `bull` / `rm` | `rm` sobald `count >= 2 × max_debate_rounds` (Default 1, Paper-Lauf 1 → genau Bull, Bear, RM) |
| `rm` | `trader` | `investment_plan`, Rating 5er-Skala |
| `trader` | `r_aggr` | `trader_investment_plan` (Aktion, Entry, Stop-Loss, Sizing) |
| `r_aggr` → `r_cons` → `r_neut` | … / `pm` | feste Reihenfolge; `pm` sobald `count >= 3 × max_risk_discuss_rounds` (Default/Paper 1 → genau 3 Beiträge) |
| `mem_node` | `pm` | `past_context` (nur der PM liest es, `portfolio_manager.py:35`) |
| `pm` | END | `final_trade_decision` (Rating, Kursziel, Horizont) |

### 2b. Nach dem Graph und Betrieb

| von | nach | was fließt |
|---|---|---|
| `pm` (final_state) | `jev_hooks` | Entscheidung, Plan, Trader-Vorschlag, Sentiment-Text → Jev-Fragen; bei `REVIEW` ggf. Rating-Fallback |
| `jev_hooks` | `rating` / `memory_log` | `run_rating` (strukturiert vor Regex) → `store_decision` pending mit Settlement-Bedingungen (5d, Benchmark, `next_close`) |
| `mem_node` | `x_yf` | Schlusskurse Ticker + Benchmark (SPY bzw. Suffix-Map) für raw/alpha |
| `mem_node` | `x_llm` | Reflexion 2-4 Sätze je abgerechneter Entscheidung |
| `paper_runner` | `tag` | je Ticker `propagate()` mit Budget-Callback |
| `budget` | `x_llm`-Aufrufe | Token-/Kostenzählung, Abbruch bei Überschreitung |
| `gha_daily` | `paper_log` | `decision-log.md`, `index.md`, `runs/<date>/…` via `git push` (ein Schreiber) |
| `paper_log` | `gha_daily` | Zustand des Vortags via `git fetch --depth=1` + `reset --hard` |
| `gha_daily` | `gha_artifact` | Reports, `summary.md` |
| `paper_log` | `ibkr_paperlog` | `decision-log.md` + `summary.json` via `git fetch`/`cat-file` (nur lesend) |
| `ibkr_paperlog` | `state_maint` | `verify` der Kopie |
| `ibkr_paperlog` | `ibkr_decision` | neueste Entscheidung je Ticker, paper-log-SHA |
| `ibkr_decision` | `ibkr_guards` | Plan (Seite, Menge, Ziel) |
| `ibkr_guards` | `ibkr_ledger` | `intent` write-ahead, Schlüssel `date|TICKER` |
| `ibkr_ledger` | `ibkr_broker` | Market-Order (nur `execute --live`), `orderRef` |
| `ibkr_broker` | `ib_gateway` | Order/whatIf/Positionen via `ib_async` (Socket, Port 7497) |
| `ib_gateway` | `ibkr_server` | Order an Paper-Simulator; Fills zurück |
| `ibkr_broker` | `ibkr_ledger` | Fills, Nachkontrolle (Abweichung → Exit 10) |
| `executor` (`account`) | `paper_runner` | `portfolio.json` mit `as_of` (optional `--portfolio`, Frischeprüfung) — **manueller** Übergang, nicht automatisiert in der CI |
| `ibkr_md` | `ib_gateway` | eigene Session, delayed Kurse; keine Kante zum Orderpfad |
| `pattern_eval` | `paper_log`, `x_yf` | Decision-Log + Kurse → Musterbericht (kein LLM) |

Kein Rückkanal von Fills nach `paper_log` (bewusst; ein Schreiber je Branch). Ein Branch `paper-fills` ist **nicht** umgesetzt (grep leer); der Ledger bleibt lokal.

---

## 3. Vorhersagemethoden - Bestandsaufnahme

Grep über `tradingagents/`, `scripts/`, `cli/` nach `monte carlo|garch|arch_model|bayes|np.random|bootstrap|embedding|cosine|vectorstore|chroma|faiss|bm25|tfidf|vader|textblob|nltk|spacy|transformers|finbert|sklearn|scipy|statsmodels` → **keine Treffer** außer `random.uniform` für Retry-Jitter (`post_screen.py:84`, `reddit.py:148`). Abhängigkeiten (`pyproject.toml`): pandas, stockstats, yfinance, langchain/langgraph; **kein** scipy, sklearn, statsmodels, NLP-Paket, keine Embedding-Bibliothek.

### 3a. Stochastisch / statistisch

| Methode | Kategorie | Wo | Was sie tatsächlich tut | Einfluss | Lücke |
|---|---|---|---|---|---|
| Wahrscheinlichkeitsmodell, Monte Carlo, GARCH, Bayes, Random Walk | stochastisch | – | **existiert nicht** | keiner | Kein Modell erzeugt eine Prognoseverteilung, Trefferwahrscheinlichkeit oder Volatilitätsprognose. |
| LLM-Sampling | stochastisch | `default_config.py:119` (`temperature: None`), `llm_clients/factory.py:177-180` | Provider-Default-Temperatur; jeder Lauf ist zufallsbehaftet | indirekt **entscheidend** (alle Urteile sind LLM-Ausgaben) | Einziges stochastisches Element im Entscheidungspfad; nicht gesteuert, nicht gemessen (keine Mehrfachläufe/Streuung je Ticker). |
| Polymarket-Wahrscheinlichkeiten | statistisch (extern, marktimpliziert) | `dataflows/vendors/polymarket.py`, Tool `get_prediction_markets` | Holt `outcomePrices` offener Märkte zu einem vom LLM gewählten Stichwort | Eingabe für LLM (News Analyst, optional) | Keine Verrechnung; nur Text im Prompt; Themenwahl durch das LLM. |
| Bollinger (2σ), ATR | statistisch-deskriptiv | stockstats über `dataflows/vendors/yahoo/market.py`, `snapshot.py` | Streuungs- bzw. Range-Maße der Vergangenheit | Eingabe für LLM | Einzige „Volatilitäts"-Größen; keine Prognose, kein Sizing aus ATR (Sizing im Ausführer ist eine feste Leiter). |
| Settlement raw/alpha | statistisch (Messung) | `memory/settlement.py:68-125` | Rendite 5 Handelstage ab erstem Schluss nach `trade_date`, Alpha = raw − Benchmark (ohne Beta) | Nachauswertung; über Reflexion → `past_context` → Eingabe für PM | Kein Beta, gerundet auf 0,1 pp im Log, überlappende Fenster. |
| Backtest-Summary (Trefferquote, mittleres Alpha) | statistisch (Messung) | `backtest.py` `summarize` | Anteil `alpha × Richtung > 0` je Rating | Nachauswertung | Ties zählen als Fehltreffer, keine Konfidenzintervalle. |
| Wilson-95-%-Intervall, `MIN_N=20`, Unabhängigkeitsfilter | statistisch (Inferenz) | `patterns/evaluate.py:50-75, 221-225` | Intervall für Trefferquoten je Muster; unter 20 unabhängigen Fällen `insufficient` | Nachauswertung (kein Import im Graph) | Datenlage: Stand 2026-10-17 1 abgerechneter Eintrag → alles `insufficient`. |
| Jev-Konfidenzen | probabilistisch (extern, kalibriertes Modell) | `jev/hooks.py`, `agents/post_screen.py` | Typisierte Fragen mit Konfidenz/Wahrscheinlichkeiten | Leitplanke: Fallback-Rating nur bei `REVIEW` und ≥ 0,9; sonst Schatten. Screening (Off-Topic < 0,3 raus, Stance ab 0,5) im Paper-Lauf aus | Keine eigene Kalibrierung geprüft; Schattenergebnisse nicht ausgewertet. |

### 3b. Heuristisch

| Methode | Kategorie | Wo | Was sie tatsächlich tut | Einfluss | Lücke |
|---|---|---|---|---|---|
| Technische Indikatoren (Auswahl durch LLM) | heuristisch | Prompt `market_analyst.py:20-46`; Allow-List `yahoo/market.py:77-150` | LLM wählt bis zu 8 aus 12: `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma` (Allow-List zusätzlich `mfi`) und liest die Zahlen | Eingabe für LLM | Keine feste Regel, kein Schwellen-Signal; Interpretation (z. B. RSI 70/30) nur als Prompttext. Prompt nennt `stochrsi`, das nicht unterstützt ist. |
| Verified Market Snapshot | heuristisch (deterministisch) | `yahoo/snapshot.py:23-26`, Tool `get_verified_market_snapshot` | Fester Satz von 11 Indikatoren + letzter OHLCV-Row + Schlusskurse als „Source of Truth" | Eingabe für LLM (Faktenanker gegen Halluzination) | Keine Bewertung, nur Zahlen. |
| Musterschicht `patterns` | heuristisch | `patterns/signals.py` | 6 Muster (+1/−1/0/None): `rsi_extreme` (Wilder 14, 30/70, konträr), `macd_cross` (12/26/9, 3 Sitzungen), `breakout_20` (Donchian auf Closes), `trend_sma200`, `sma50_200`, `bollinger_out` (20, 2σ); look-ahead-frei | Nachauswertung | Bewusst kein Veto/keine Entscheidung (Schritt 2 erst bei belegter Wirkung). |
| StockTwits-Zählung | heuristisch | `dataflows/vendors/stocktwits.py:131-160` | Zählt **nutzergesetzte** Labels Bullish/Bearish/ohne → Prozentkopf | Eingabe für LLM | Kein eigenes Klassifizieren der ~70 % unlabelten Posts (Anteil nicht gemessen). |
| post_screen | heuristisch + probabilistisch | `agents/post_screen.py` | Jev-Fragen je Post; Off-Topic raus, Stance-Zählung | Eingabe für LLM, **im Paper-Lauf aus** | Wirkung im Track Record nicht vorhanden. |
| Rating-Extraktion | heuristisch (Regex) | `agents/rating.py:55-110` | Strukturiertes `rating` zuerst, sonst Label-Regex; widersprüchlich → `REVIEW` | **entscheidet** über das gespeicherte Signal | Freitext-Pfad bleibt Regex-abhängig. |
| Jev-Review | heuristisch-Leitplanke | `jev/hooks.py` | s. o. | Leitplanke (nur REVIEW-Fallback) | Schatten-Agreement nicht aggregiert. |
| Debattenrunden | heuristisch (Ablauf) | `conditional_logic.py`, Config 1/1 | Feste Rundenzahl, kein Konvergenz- oder Uneinigkeitsmaß | Ablaufsteuerung | Keine Messung von Uneinigkeit als Unsicherheitssignal. |
| Kosten-/Token-Budget | Leitplanke | `budget.py` | Abbruch bei Überschreitung | Leitplanke (Lauf, nicht Richtung) | – |
| Soll-Leiter | heuristisch (Regel) | `scripts/ibkr_decision.py:323-375` | Buy=2, Overweight=1, Underweight/Sell=0 Blöcke; Hold → skip; long-only; Toleranz 1 Block | **entscheidet** über die Order | Größe unabhängig von Konfidenz, Volatilität, Kursziel, Stop-Loss des Traders. |
| Größenlimit, Kill/Release, Sessionprüfung, Frische | Leitplanke | `scripts/ibkr_guards.py`, `ibkr_decision.py:540-610` | `MAX_QTY_PER_ORDER=2`, KILL/RELEASE fail-closed vor jeder Order, XNYS-Kalender, veraltete Entscheidung → stop | Leitplanke | Kein Stop-Loss/Take-Profit aus `TraderProposal` wird an IBKR gegeben. |

### 3c. Semantisch / NLP (Ticker-Meldungen)

| Methode | Kategorie | Wo | Was sie tatsächlich tut | Einfluss | Lücke |
|---|---|---|---|---|---|
| Ticker-News | LLM-Urteil | `yahoo/news.py` (`yf.Search`, Titel+Summary+Publisher), Tool `get_news`; max. 20 Artikel | Rohtext in den Prompt von News- und Sentiment-Analyst | Eingabe für LLM | Kein Sentiment-Score, keine Deduplizierung nach Inhalt, keine Relevanzgewichtung. |
| Globale News | LLM-Urteil | `get_global_news`, 5 feste Suchanfragen (`default_config.py` `global_news_queries`), 7 Tage, 10 Artikel | Rohtext | Eingabe für LLM | wie oben. |
| Alpha-Vantage NEWS_SENTIMENT | semantisch (extern) | `alpha_vantage/news.py:9-70` | Würde die JSON-Antwort inkl. Sentiment-Arrays **ungefiltert** in den Prompt geben | **keiner im Paper-Lauf** (Vendor `yfinance`, `data_vendors` nicht per Env schaltbar) | Selbst wenn aktiv: Scores werden nicht ausgewertet, nur als Text gelesen. |
| Social (StockTwits, Reddit) | LLM-Urteil | `sentiment_analyst.py:57-125`, `reddit.py` (RSS, HTML gestrippt) | Vorab geholt, in Prompt-Blöcke; LLM schreibt `SentimentReport` mit `overall_band` (6 Stufen), `overall_score` 0-10, `confidence` | Eingabe für Researcher/Risiko | Der „Score" ist **vom LLM erzeugt**, nicht gerechnet; nicht point-in-time (Feeds nicht archiviert). |
| Insider-Transaktionen | LLM-Urteil | `get_insider_transactions` (yfinance), `date_window.withhold_undisclosed_trades` | Tabelle im Prompt des Fundamentals Analyst | Eingabe für LLM | Keine Aggregation (Netto-Käufe, Cluster). |
| Fundamentals | LLM-Urteil | SEC EDGAR XBRL, yfinance | Tabellen im Prompt | Eingabe für LLM | Keine Kennzahlen-Scores/Faktormodelle. |
| Memory-Retrieval | heuristisch (nicht semantisch) | `memory/log.py:106-143` | Neueste 5 abgerechnete Einträge desselben Tickers + 3 fremde, rein nach Zeit, gefiltert auf `resolved <= as_of` | Eingabe für PM | **Keine Embeddings, keine Ähnlichkeitssuche.** |
| Debatte/Urteil | LLM-Urteil | Bull/Bear/RM/Trader/Risiko/PM | Freitext-Argumentation, strukturierte Endausgabe | **entscheidet** (PM-Rating) | Keine Begründungs- oder Konsistenzprüfung außer Jev-Schatten. |

---

## 4. Fünf-Zeilen-Antwort (für die Seite)

1. Stochastische Vorhersagemodelle (Wahrscheinlichkeitsmodell, Monte Carlo, GARCH, Bayes) gibt es in TradingEngineX nicht; das einzige Zufallselement im Entscheidungspfad ist das ungesteuerte LLM-Sampling.
2. Statistik steckt nur in der Nachauswertung: Settlement (5-Tage-Rendite und Alpha gegen SPY), Backtest-Trefferquote und im Strang Wilson-Intervalle mit Mindest-N; nichts davon wirkt auf die nächste Entscheidung außer über LLM-Reflexionstexte.
3. Heuristiken sind technische Indikatoren (12 stockstats-Werte), die das LLM auswählt und liest, die Musterschicht als reine Nachauswertung und feste Regeln im Ausführer (Rating-Leiter 2/1/0 Blöcke, Größenlimit, Kill-Switch, Handelszeiten).
4. Ticker-News, Social und Insider werden ausschließlich vom LLM als Rohtext gelesen; es gibt kein eigenes NLP, keine Embeddings, keine gerechneten Sentiment-Scores (der „Score" 0-10 schreibt das LLM selbst, Alpha-Vantage-Scores sind im Paper-Lauf nicht aktiv).
5. Die Entscheidung ist damit im Kern ein LLM-Urteil über Text und Zahlen; die Code-Logik sichert Fakten (Snapshot, Look-ahead-Kappung), Ausführung und Kosten ab, sagt aber selbst nichts vorher.

---

## Common Pitfalls (für das Schaubild)
- **Market Analyst „hat 12 Indikatoren" ≠ „rechnet Signale":** im Diagramm als „Eingabe für LLM" kennzeichnen, nicht als Signalgeber.
- **Sentiment-Score wirkt gerechnet**, ist aber LLM-Ausgabe (`schemas.py:311-349`). Nicht als NLP-Modul zeichnen.
- **Research Manager liest nur die Debatte**, nicht die Rohreports; der Trader liest nur Plan + Market-Report. Kanten nicht pauschal „alle Reports → alle" ziehen.
- **Memory Log läuft parallel zu den Analysten** (nicht davor) und speist nur den PM.
- **Alpha Vantage, FRED, post_screen** sind im Paper-Lauf aus bzw. optional → gestrichelt zeichnen.
- **Budget, Jev, Patterns** sind Strang, obwohl sie in `tradingagents/` liegen (nicht in `origin/main`, geprüft per `git cat-file`). `post_screen.py` ist dagegen Upstream (#1376, Autor Yijia-Xiao).
- **Ausführer ist manuell**, kein Task Scheduler; keine Kante „CI → IBKR".
- **IB-Port 7497**, nicht 4002.

## Assumptions Log
| # | Annahme | Abschnitt | Risiko |
|---|---|---|---|
| A1 | Provider-Default-Temperatur bei Anthropic ist > 0 (typisch 1,0), also echtes Sampling | 3a | Gering; Aussage „stochastisch" gilt auch für Reasoning-Modelle (`default_config.py:115-118`). |
| A2 | Ob `JEV_API_KEY` und `FRED_API_KEY` als Repo-Secrets gesetzt sind, wurde nicht geprüft (keine Secrets-Einsicht) | 1e | Gering; im Diagramm als „optional" kennzeichnen. |
| A3 | Anteil unlabelter StockTwits-Posts nicht gemessen | 3b | Nur Formulierung in „Lücke". |
| A4 | Status Phase 6 (erste echte Order) laut letzten Commits: Messtag verschoben, 2026-10-19 keine Kaufentscheidung | 1a | Teil A belegt den Status. |

## Open Questions
1. Soll `cli`/`backtest` als eigener Knoten oder nur in der Matrix erscheinen? Empfehlung: kleiner Knoten in Z3 bzw. Z5, damit Upstream-Funktionen klickbar sind.
2. `graphify-out` ist veraltet (2026-10-12); für das Schaubild nicht als Quelle verwenden.

## Sources
- Code (HIGH): `tradingagents/graph/setup.py`, `conditional_logic.py`, `trading_graph.py`, `analyst_execution.py`, `agents/tools.py`, `agents/analysts/*.py`, `agents/schemas.py`, `agents/rating.py`, `agents/post_screen.py`, `dataflows/router.py`, `dataflows/vendors/{yahoo,alpha_vantage,stocktwits,reddit,polymarket,fred,sec_edgar}`, `memory/{log,settlement,reflection}.py`, `patterns/{signals,evaluate}.py`, `jev/hooks.py`, `budget.py`, `default_config.py`, `pyproject.toml`
- Betrieb (HIGH): `.github/workflows/daily-paper-run.yml`, `scripts/daily_paper_run.py`, `scripts/ibkr_*.py`, `scripts/state_maintenance.py`, `scripts/smoke/*`, `scripts/IBKR_EXECUTION.md`
- Planung (MEDIUM, Stand-Doku): `.planning/research/ibkr-execution-architecture.md` (2026-10-11, teils Entwurf: `paper-fills`, Task Scheduler nicht umgesetzt), `.planning/quick/261018-kof-*/261018-kof-RESEARCH.md`
- Provenienz: `git log --diff-filter=A`, `git cat-file -e origin/main:<pfad>`

**Valid until:** ca. 2026-11-02 (Phase 6 läuft; Upstream-Rebase kann Pipeline ändern).
