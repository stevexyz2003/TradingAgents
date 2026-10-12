# Quick Task 261012-t8w: Jev an Klassifizierungs-/Bewertungsstellen – Research

**Recherchiert:** 2026-10-12 · **Konfidenz:** HOCH für Fundstellen (Code gelesen), MITTEL für Persistenz-Annahmen (markiert).

## 0. Werkzeuge: wer hat was gefunden

| Tool | Ergebnis |
|---|---|
| **Serena** (`initial_instructions` OK; `get_symbols_overview` auf `tradingagents/agents/rating.py`) | **Fehlgeschlagen**: Python-LSP startet nicht (`LanguageServerTerminatedException`, Log `~/.serena/logs/2026-10-12/mcp_20261012-202238_36448.txt`). Keine symbolischen Referenzen verfügbar. Ersatz: Grep auf Symbolnamen (`extract_rating|parse_rating|run_rating|is_review|RATING_REVIEW|final_rating`, `bind_structured|invoke_structured`, `record_decision`), danach gezieltes Read. Operator sollte Serena reparieren (`serena`-LSP/pyright-Install prüfen), bevor es fürs Executing gebraucht wird. |
| **Graphify** (`graphify-out/GRAPH_REPORT.md` + `graphify query "where is a rating, signal or sentiment classified from text"`) | Lieferte den Hotspot-Cluster (Community 4): `SignalProcessor`/`parse_rating`/`create_portfolio_manager`/`create_research_manager`/`create_trader` plus God-Nodes `TradingMemoryLog`, `ConditionalLogic`, `Reflector`. **Der Graph ist veraltet** (Pre-v0.6.0-Layout: `graph/signal_processing.py` und `agents/utils/rating.py` gibt es nicht mehr; CLI warnt außerdem: Skill 0.8.31 vs. Paket 0.9.23, alte Node-IDs). Er taugt nur als Wegweiser. Vor Stage-2-Nutzung `graphify . --update` bzw. `graphify extract --force` laufen lassen. |
| **Grep/Read** | Alle Zeilennummern unten (Stand `main` @ 7272181). Dabei gefunden: **Upstream hat bereits eine Jev-Integration**, siehe §1. |

## 1. Wichtigster Befund: Upstream nutzt Jev schon

`tradingagents/agents/post_screen.py` (upstream #1376/#1416, v0.5.1) screent StockTwits/Reddit-Posts für den Sentiment Analyst über `POST {TYPESAFE_BASE_URL|https://api.typesafe.ai}/v1/systemone`. Es nutzt `requests`, die Env-Variablen `TYPESAFE_API_KEY`/`TYPESAFE_DEFAULT_MODEL`/`TYPESAFE_BASE_URL` (stehen in `.env.example:25-28`), 15 s Timeout, 3 Versuche bei 429/529 und `Retry-After`. Es wird **automatisch aktiv, sobald `TYPESAFE_API_KEY` gesetzt ist**. Tests: `tests/test_post_screen.py` (monkeypatcht `post_screen.requests.post`).

Folgen für das Design:
- **Kein zweiter Name für dasselbe Ding im Upstream-Code.** Der neue Client liest `JEV_API_KEY` (CONTEXT-Entscheid, so steht er in der Operator-`.env`). `TYPESAFE_API_KEY` wird bewusst **nicht** als Fallback genommen: wer ihn setzt, schaltet zusätzlich das Upstream-Post-Screening ein (pro Post 1 Request, bis 16 parallel), und das ist eine eigene Entscheidung. Diese Trennung gehört in die SUMMARY.
- Endpoint/Modell analog zu Upstream: `https://api.typesafe.ai/v1/systemone`, `jev-latest`. Optional `TYPESAFE_BASE_URL` respektieren, damit OpenRouter funktioniert. Low priority, kann weg.
- Die Sentiment-**Post**-Klassifikation (`post_screen.py:147-148`, `about`/`stance`) ist schon Jev → abgelehnt (§4).

## 2. Fundstellen (Text → Klasse/Skala/ja-nein)

| # | file:line | Symbol | Was wird klassifiziert | Heutiger Mechanismus | Jev-Form + Entwurf | Rolle | Gesendete Daten | Risiko / Rebase-Kosten |
|---|---|---|---|---|---|---|---|---|
| F1 | `agents/managers/portfolio_manager.py:84-86` (→ `rating.py:96 parse_rating` → `:55 extract_rating`) | `portfolio_manager_node`, Free-Text-Zweig | Finales 5-Tier-Rating des PM | Strukturiert scheitert 2× (`structured.py:90-126`) → `llm.invoke` → Regex `extract_rating`; nichts gefunden → `REVIEW` (#1170) | **choice** `final_rating`: "Which single rating does `decision` itself commit to for the position (not a rating it quotes from someone else)?" criteria (Reihenfolge gemischt, nicht Hold zuerst): `underweight`, `buy`, `hold`, `sell`, `overweight` (je 1 Satz aus der PM-Skala), `other`: "No single own rating, or several conflicting ones" | **FALLBACK** (nur wenn `run_rating(...) == "REVIEW"`, conf ≥ `jev_min_confidence`, Antwort ≠ `other`) | nur `final_trade_decision` (PM-Ausgabetext). **Nicht** `portfolio_context` (Holdings/Cash) separat. Der Text kann Bestände zitieren, enthält aber keine Account-ID (`portfolio.py` hat kein Account-Feld). | Selten aktiv (beide Strukturversuche + Regex müssen scheitern). Hook **nicht** im PM-Node, sondern zentral in `record_decision` (§3), also 0 Zeilen in `portfolio_manager.py` |
| F2 | `agents/managers/portfolio_manager.py:80-83` | dto., strukturierter Zweig | Gleiches Rating, typisiert `PortfolioDecision.rating` | Pydantic-`StrEnum` `PortfolioRating` (`schemas.py:66`) | gleiche Frage wie F1 auf `render_pm_decision`-Text | **SHADOW**, kalibriert F1: wie oft liegt Jev ≥ 0.9 und stimmt mit dem typisierten Rating überein | `final_trade_decision` | keine Upstream-Änderung (Post-Run-Hook) |
| F3 | `agents/managers/research_manager.py:53-59` | `research_manager_node` | 5-Tier-Recommendation | `ResearchPlan.recommendation` (Enum). Wird nur gerendert (`schemas.py:133`, Zeile `**Recommendation**: X`), der typisierte Wert geht verloren | **choice** `research_recommendation`, gleiche 5 + `other`, "Which recommendation does `plan` commit to?" | **SHADOW**: Vergleich mit Regex `^\*\*Recommendation\*\*:\s*(\w+)` im Hook-Modul (Free-Text → `None`) | `investment_plan` | 0 Upstream-Zeilen (liest `final_state`) |
| F4 | `agents/trader/trader.py:85-91` | `trader_node` | Aktion Buy/Hold/Sell | `TraderProposal.action` (Enum `TraderAction`, `schemas.py:76`), gerendert als `FINAL TRANSACTION PROPOSAL: **X**` (`schemas.py:211`) | **choice** `trader_action`: `sell`, `buy`, `hold`, `other`, "Which transaction does `proposal` itself propose?" | **SHADOW**: Vergleich mit Regex auf `FINAL TRANSACTION PROPOSAL: \*\*(BUY|HOLD|SELL)\*\*` | `trader_investment_plan` (enthält Entry/Stop als Preise, kein Konto) | 0 Upstream-Zeilen |
| F5 | `agents/analysts/sentiment_analyst.py:114-120` | `sentiment_analyst_node` | Sentiment-Band (6 Stufen) + Score 0-10 + Konfidenz low/med/high | `SentimentReport` (`schemas.py:296-349`), gerendert als `**Overall Sentiment:** **Band** (Score: x/10)` (`:374`) | **choice** `sentiment_band`: `mixed`, `bearish`, `mildly_bullish`, `neutral`, `bullish`, `mildly_bearish`, `other`. Optional **score** `sentiment_level` (5 Stufen Bearish→Bullish, niedrigste zuerst), vergleichbar mit `overall_score/2.5` | **SHADOW**: Vergleich mit Header-Regex | `sentiment_report` (LLM-Ausgabe, keine Rohposts) | 0 Upstream-Zeilen. Report ist lang (~2-5k Token, < $0.0003) |
| F6 | `agents/rating.py:106-112` | `run_rating` | Rating eines (alten) Checkpoint-States ohne `final_rating` | Regex-Fallback | wie F1 | abgelehnt als eigener Hook: wird durch F1 im Post-Run-Hook abgedeckt | – | – |
| F7 | `memory/log.py:56` | `store_decision` | Rating-Tag | `parse_rating` | – | **abgelehnt**: läuft unter Datei-Lock (`locked(...)`), dort darf kein Netzcall laufen. Bekommt den Jev-Wert ohnehin über `run_rating(final_state)` (`trading_graph.py:396`) | – | – |
| F8 | `graph/conditional_logic.py:19,29` | `should_continue_debate/_risk_analysis` | Routing | `startswith("Bull"/"Aggressive")` auf selbst gesetzte Sprecher-Präfixe | – | **abgelehnt**: deterministisch, keine Textdeutung, Graph-Routing wäre blockierend | – | – |
| F9 | `memory/reflection.py:36-63` | `Reflector.reflect_on_final_decision` | – | erzeugt Prosa, klassifiziert nichts | (noul "war der Call richtig?" wäre eine neue Klassifikation) | **abgelehnt**: keine bestehende Klassifikation; Alpha-Vorzeichen ist Arithmetik | – | – |
| F10 | `agents/post_screen.py:147-148` | `jev_screen` | about/stance je Post | schon Jev (upstream) | – | **abgelehnt** (existiert) | – | – |
| F11 | `dataflows/vendors/stocktwits.py:142` | Tagging | Bullish/Bearish | User-Label der Plattform | – | **abgelehnt**: Metadaten, keine Textdeutung | – | – |
| F12 | `memory/log.py:17-18`, `backtest.py:196,207`, `cli/run.py:425`, `reporting.py:26`, `report_html.py:251` | Tag-Parser / REVIEW-Konsumenten | – | strukturelles Parsen bzw. `is_review` | – | **abgelehnt**: profitieren automatisch von F1 (lesen `run_rating`) | – | – |
| F13 | `scripts/daily_paper_run.py:366-369` | `run_ticker` | Signal | `graph.propagate()` → `run_rating` | – | kein eigener Klassifikator → nur **Persistenzziel** (§3) | – | fork-eigene Datei, additiv |

## 3. Empfohlene Auswahl (1 Fallback + 4 Shadow, **ein** Hook-Punkt)

**Kernidee:** Alle gewählten Stellen lesen nur Texte, die nach dem Graph-Lauf in `final_state` liegen. Deshalb gibt es einen einzigen Hook am Anfang von `TradingAgentsGraph.record_decision` (`graph/trading_graph.py:385`). Den durchlaufen `propagate()` (`:435`) **und** die CLI (`cli/run.py:371`), beide vor `_log_state`, `store_decision`, der `is_review`-Anzeige (`cli/run.py:425`) und dem Rückgabewert `run_rating(final_state)` (`:440`). Das ergibt **2 Zeilen Upstream-Churn** (Import + Aufruf); Agent-Dateien bleiben unberührt.

```python
def record_decision(self, company_name, trade_date, final_state):
    jev_hooks.review_run(final_state, self.config)   # neu: no-op wenn aus / kein Key
    self._log_state(trade_date, final_state)
    ...
```

`review_run` schickt **einen** Request pro Ticker. `state` ist ein Objekt `{"decision": ..., "plan": ..., "proposal": ..., "sentiment": ...}` (leere Felder weglassen), die Fragen referenzieren die Felder per Backtick wie in `post_screen`:
1. **F1/F2** `final_rating` (choice). Ist `run_rating(final_state) == "REVIEW"`, conf ≥ `jev_min_confidence` (0.9) und Antwort ∈ 5 Tiers, dann `final_state["final_rating"] = "<Tier>"` und `final_state["final_rating_source"] = "jev"` + `logger.warning("Jev fallback: REVIEW -> %s (conf %.2f)")`. Sonst bleibt REVIEW unverändert. Sonst Shadow-Vergleich gegen `final_state["final_rating"]`.
2. **F3** `research_recommendation`, **F4** `trader_action`, **F5** `sentiment_band` (+ optional `sentiment_level`): nur Shadow.

Kosten: ~5-10k Input-Token/Ticker ≈ **$0.0002-0.0004**; Paper-Run ~$0.18/Ticker ⇒ < 0.3 %. Hinweis: Jev-Kosten laufen **nicht** durchs `max_cost_per_run`-Budget (`budget.py` zählt nur LLM-Callbacks).

Fallback-Rückwirkung (bewusst, laut CONTEXT): Ein Jev-Rating wird wie ein normales behandelt, also Memory-Log-Tag, Backtest-Scoring, Paper-Signal. Der IBKR-Executor handelt heute **nicht** auf Signale (`scripts/ibkr_executor.py` kennt nur `account`/`resolve`), es besteht also kein Orderrisiko. Muss erkennbar sein über `final_rating_source` + Log + Shadow-Datensatz.

**Persistenz** (minimale Churn):
- `final_state["jev"] = {...}` direkt im Post-Run-Dict (kein LangGraph-Channel, `final_state` ist dort ein plain dict). Das funktioniert ohne Änderung an `AgentState`. [ASSUMED-frei, da nach `stream_run`.]
- `_log_state` (`trading_graph.py:497-523`) schreibt eine **explizite** Key-Liste und nimmt `jev` also nicht mit. Statt sie zu ändern: Der Hook schreibt eine Sidecar-Datei `<results_dir>/<safe_ticker>/TradingAgentsStrategy_logs/jev_review_<trade_date>.json` (`safe_ticker_component` aus `dataflows/symbols.py` wiederverwenden).
- `scripts/daily_paper_run.py:369` (fork-eigen, additiv, `SUMMARY_SCHEMA_VERSION` bleibt 1): `record["jev"] = final_state.get("jev")` plus `record["rating_source"]`. Optional eine Spalte in `render_summary_markdown`.
- Datensatz je Frage: `{existing, jev, confidence, agree, applied}` + `{model, input_tokens, cost_usd, latency_ms}` oder `{error: "<redigiert>"}`.

## 4. Abgelehnte Stellen (Kurz)
F6 (über F1 abgedeckt), F7 (Netz unter Lock), F8 (deterministisches Routing), F9 (keine bestehende Klassifikation), F10 (bereits Jev, upstream), F11 (Plattform-Label), F12 (Konsumenten, profitieren indirekt). Shadow-Hooks *in* den Agent-Nodes (RM/Trader/Sentiment/PM) verworfen: 4 Upstream-Dateien Churn, Latenz im kritischen Pfad, im Sentiment-Subgraph parallel. Der Post-Run-Hook liefert dieselben Vergleiche.

## 5. Design-Notizen

**Modul-Layout** (alles neu, fork-eigen):
- `tradingagents/jev/__init__.py`
- `tradingagents/jev/client.py`: stdlib `urllib` (aus `jev.py`): `validate`, `build_request`, `summarize` (noul-Konfidenz `abs(2p-1)`), `redact` (Key + Muster `apikey_…|sk-or-…`), `make_ssl_context` (Default/truststore/`JEV_CA_FILE`, nie `CERT_NONE`), `call_api` mit **1** Retry bei 429/502/503/524/529 (Backoff 1 s) und Timeout `jev_timeout`. Wirft `JevError`. Kein Keyring/OpenRouter-Zweig, nur der Direct-Backend-Pfad.
- `tradingagents/jev/hooks.py`: `review_run(final_state, config)`; Fragen-Konstanten; Regex-Extraktoren für F3/F4/F5-Header; Sidecar-Write. Fängt **jede** Exception (`except Exception`) → `logger.warning(redact(...))`, nie raise.
- Gate: `config.get("jev_enabled")` **und** `os.environ.get("JEV_API_KEY")`. Sonst sofort `return` ohne Import von Netzcode, damit das Verhalten bit-identisch bleibt.

**Config** (`default_config.py`): Defaults `"jev_enabled": False`, `"jev_min_confidence": 0.9`, `"jev_timeout": 10.0`. Zeilen in `_ENV_OVERRIDES` (`:10-34`): `TRADINGAGENTS_JEV_ENABLED`, `TRADINGAGENTS_JEV_MIN_CONFIDENCE`, `TRADINGAGENTS_JEV_TIMEOUT`. `_coerce` (`:41`) richtet sich nach dem Typ des Defaults, deshalb müssen die Defaults `bool`/`float` sein (nicht `None`). Ungültige Werte werfen laut `ValueError`. ~6 Zeilen Upstream-Churn.

**.env-Laden:** Ja, die Engine lädt sie. `tradingagents/__init__.py:12-13` ruft `load_dotenv(find_dotenv(usecwd=True))` (+ `.env.enterprise`). Damit ist `JEV_API_KEY` nach dem Import in `os.environ`, ein eigenes `.env`-Parsing ist nicht nötig. `JEV_API_KEY` **nicht** in `_ENV_OVERRIDES`, denn Keys gehören nicht in den Config-Dict (der landet in `run_settings`/Logs). Eine Zeile `#JEV_API_KEY=` in `.env.example` ist optional.

**Logging:** `logger = logging.getLogger(__name__)` (Muster aus `structured.py:29`, `post_screen.py:25`), `%s`-Formatierung, WARNING für Fehler/Fallback, INFO für Shadow-Disagreement, DEBUG für Agreement.

**Datenschutz:** Gesendet werden nur `final_trade_decision`, `investment_plan`, `trader_investment_plan`, `sentiment_report`. **Nie** `portfolio_context`, `run_settings`, Config, Env. Der Ticker steckt im Text, das ist laut Freigabe OK.

## 6. Tests & Tooling
- Layout: flach `tests/test_*.py`. Marker `unit|integration|smoke` (`pyproject.toml:65-72`, `--strict-markers`, Default `-m "not integration"`).
- `tests/conftest.py:59-75` `_no_network` blockt `socket.connect`/`getaddrinfo` autouse. Ein vergessener Stub schlägt also laut fehl, statt live zu gehen. `_blank_settings_overlay` setzt alle `TRADINGAGENTS_*` auf leer, damit ist `jev_enabled` in Tests aus, auch wenn die Operator-`.env` es setzt. `_isolate_config` resettet die Config.
- Stub-Muster: wie `tests/test_post_screen.py:32-48` den Transport monkeypatchen (`monkeypatch.setattr(client, "_post", fake)`, `time.sleep` patchen), `monkeypatch.setenv("JEV_API_KEY", "apikey_TEST")`. Für einen End-to-End-HTTP-Test geht alternativ `ThreadingHTTPServer` wie `scripts/smoke/stub_llm.py:26,179` (quick 261011-k4s), dann aber Localhost-Socket → Marker `integration` oder `_no_network` lokal umgehen. Monkeypatch reicht.
- Pflichttests: (a) aus/kein Key → kein `_post`-Aufruf, `final_state` unverändert; (b) REVIEW + conf 0.95 → Tier + `final_rating_source="jev"`; (c) REVIEW + conf 0.6 / `other` → bleibt REVIEW; (d) HTTP 500/Timeout/Malformed → Warnung, unverändert, kein Raise; (e) Shadow-agree/disagree-Records; (f) Key taucht in keinem Log-/Fehlertext auf (`caplog`); (g) Env-Override-Coercion.
- Ausführen (uv run geht hier nicht): `.venv/Scripts/python.exe -m pytest tests/test_jev_client.py tests/test_jev_hooks.py -q`, dann volle Suite `.venv/Scripts/python.exe -m pytest -q`, Lint `.venv/Scripts/python.exe -m ruff check tradingagents/jev tests scripts/daily_paper_run.py`. Bash-Tool hängt, also PowerShell nutzen.
- Live-Smoke (manuell, einmal): kleines Skript/REPL mit echtem `final_state`-Fixture und `TRADINGAGENTS_JEV_ENABLED=true`. Ergebnis (Antworten, conf, Kosten, Latenz) in der SUMMARY, Key nie ausgeben.

## 7. Vorschlag Plan-Schnitt (3 Tasks)
1. `tradingagents/jev/client.py` + Config-Keys/Env-Overrides + `tests/test_jev_client.py`.
2. `tradingagents/jev/hooks.py` (Fallback F1 + Shadow F2-F5, Sidecar) + 2-Zeilen-Hook in `trading_graph.record_decision` + `tests/test_jev_hooks.py`.
3. Paper-Run-Felder (`daily_paper_run.py:369`, additiv) + Doku (`.env.example`, CHANGELOG-Eintrag fork-seitig) + Live-Smoke + volle Suite/ruff.

## Annahmen
| # | Annahme | Risiko |
|---|---|---|
| A1 | `final_state` in `record_decision` ist ein plain dict, Mutation ist für Aufrufer sichtbar (`_run_graph` baut es per `.update`, CLI reicht seins durch) | gering, im Test absichern |
| A2 | Ein Request mit Objekt-`state` + 4 feldreferenzierenden Fragen klassifiziert so gut wie Einzel-Requests (Upstream macht es mit `{instrument, post}` genauso) | mittel. Fallback-Frage notfalls separat mit `state` = nur Decision-Text |
| A3 | `apikey_`-Präfix für Direct-Keys (aus `jev.py`-Redact-Muster) | gering. Zusätzlich exakter Key-Replace |
