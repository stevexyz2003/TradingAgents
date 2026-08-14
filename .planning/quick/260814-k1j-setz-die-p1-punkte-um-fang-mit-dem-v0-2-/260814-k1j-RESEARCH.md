# Quick Task 260814-k1j: P1-Punkte umsetzen (Release v0.2.5 zuerst) — Research

**Researched:** 2026-08-14
**Domain:** Python/LangGraph-Framework — Release, CI, Budget-Enforcement, Schema-Härtung, Secrets
**Confidence:** HIGH (fast ausschließlich Codebasis-Verifikation, kaum Fremdquellen nötig)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### D1 — Release-Zuschnitt v0.2.5
- v0.2.5 enthält **nur** die zwei bereits vorhandenen Commits (`2c97bad` Security-Fix #618, `7e9e7b8` DeepSeek V4) plus Release-Commit (CHANGELOG-Sektion 0.2.5, `pyproject.toml` → 0.2.5, Compare-Links).
- **Annotierter** Tag `v0.2.5` mit Message „TradingAgents v0.2.5" (Konvention wie v0.2.4). Tag setzt der **Orchestrator nach dem Worktree-Merge** auf den Release-Commit — nicht der Executor.
- **Kein Push** (weder Commits noch Tag) — origin ist TauricResearch/TradingAgents; Push entscheidet der User.
- `uv.lock` wird **nicht angefasst** (lokale Operator-Drift, als P2 im Milestone geführt).

#### D2 — CI-Design
- `.github/workflows/ci.yml`: uv-basiert (astral-sh/setup-uv), pytest-Matrix Python 3.10/3.11/3.12/3.13 auf ubuntu-latest **plus** windows-latest mit 3.13 (Windows-Bug-Historie des Projekts: cp1252/Encoding).
- Lint: `ruff check` **nur kritische Regeln** (E9, F63, F7, F82) — Tag-1-grün; Ausbau später.
- Security-Scan: `pip-audit` als eigener Job, zunächst **advisory** (`continue-on-error: true`) — dauerhaft rote CI wird ignoriert und ist schlimmer; Eskalation auf blocking steht ins Runbook (P2).
- CI-Commit landet **nach** dem Tag (gehört zu v0.2.6, nicht ins v0.2.5-Release).

#### D3 — Dev-Dependencies
- PEP-735-`[dependency-groups]` in `pyproject.toml`: `dev = ["pytest", "ruff"]` (uv-nativ). Keine weiteren Tools — pip-audit läuft in CI via uvx.

#### D4 — Kosten-Budget (#582)
- Maintainer-Position (PR #582, closed): Callback + Abort + Partial-Save ist die richtige Form, aber **keine hartkodierte Preistabelle** — Kosten nur mit **user-supplied Rates**.
- Design: `max_cost_per_run` (USD, Default `None` = aus) + user-supplied Rates in der Config (`model_cost_rates`: USD pro 1M Input-/Output-Tokens). Zusätzlich `max_tokens_per_run` als ratenfreie Alternative (Token-Zählung existiert bereits im Stats-Handler).
- `BudgetExceededError` → `propagate()` bricht **sauber** ab: bisherige Reports werden gespeichert, Abbruchgrund geloggt; mit `--checkpoint` bleibt der Run resumefähig.
- CLI: `--max-cost` Flag. `--max-cost` ohne konfigurierte Rates → Fail-fast mit klarer Meldung (keine stillen Schätzpreise).

#### D5 — Schema-Härtung (#583)
- Scope bleibt das Entscheider-Trio (Research Manager, Trader, Portfolio Manager) — Prosa-Agenten sind laut Maintainer-Entscheid bewusst prose-first; NICHT alle 13 Nodes umbauen.
- Muster je strukturiertem Call: 1 Retry mit Fehlerkontext, danach **Fallback auf Prosa-Aufruf** + bestehende Markdown-Render-/Parse-Pipeline (SignalProcessor liest gerendertes Markdown deterministisch). Schema-Fehler dürfen den Run nie mehr abbrechen; Warnung wird geloggt.

#### D6 — Secrets/Konfig
- Doku: neuer Abschnitt (docs/ oder README) — welche Keys wohin (.env / Env-Vars / Docker), Verhalten bei fehlendem Key, Kosten-/Quota-Hinweise.
- Fail-fast: Validierung beim Start (CLI-Eintritt + `TradingAgentsGraph.__init__`): fehlender/leerer API-Key für den gewählten Provider → sofortige klare Fehlermeldung statt Crash mitten im Run. Bestehende Katalog-/Provider-Validierung nutzen, nicht duplizieren.

#### D7 — Commit-/Release-Reihenfolge
1. Release-Commit (CHANGELOG + Version) → darauf Tag v0.2.5 (durch Orchestrator, nach Merge)
2. CI + Dev-Deps
3. Budget-Enforcement (D4)
4. Schema-Härtung (D5)
5. Secrets-Doku + Fail-fast (D6)
Atomare Commits je Punkt; keine Vermischung. Niemals `git add -A`/`-u` — nur explizite Pfade; `.gitignore`, `uv.lock`, `.mcp.json`, `.idea/`, `.serena/`, `scripts/graphify.sh` nicht anfassen (Operator-Dateien).

#### D8 — Review-Kette (--review Codex)
- Codex reviewt den PLAN vor Ausführung (HIGH-Findings → Revision) und den Gesamt-Diff nach Ausführung (statt separatem gsd-code-reviewer — User hat Codex explizit als Reviewer benannt).
- Orchestrator verifiziert Executor-Claims selbst (Testlauf lokal wiederholen — Memory: Self-Claims nicht trauen).

### Claude's Discretion
Alle obigen Entscheidungen; eskaliert wird nur, falls Push/Remote-Operationen nötig würden (bleiben aus) oder ein P1-Punkt ohne destruktive Eingriffe nicht umsetzbar ist.

### Deferred Ideas (OUT OF SCOPE)
— (keine in CONTEXT.md gelistet; `uv.lock`-Drift und Runbook sind P2 im Milestone)
</user_constraints>

## Summary

Alle fünf P1-Bereiche wurden gegen die Codebasis verifiziert. Kernaussagen: (1) Die Version steht **nur** in `pyproject.toml:7` — kein `__version__`, kein CLI-Banner; CHANGELOG-Konventionen sind exakt dokumentierbar. (2) Es gibt kein `.github/`; die Testsuite läuft ohne API-Keys (conftest setzt Platzhalter), aber `uv sync --locked/--frozen` in CI **wird brechen**, sobald `[dependency-groups]` in pyproject landet, weil `uv.lock` nicht angefasst werden darf. (3) Der Stats-Handler ist ein sauberer LangChain-Callback, der bereits graph-seitig andockbar ist (`TradingAgentsGraph(callbacks=...)` → LLM-Konstruktor aller 4 Client-Familien) — **aber**: LangChain schluckt Callback-Exceptions, solange `raise_error = True` nicht gesetzt ist (verifiziert in installiertem langchain_core 1.3.2). Und: die CLI umgeht `propagate()` komplett und streamt den Graph direkt. (4) Die Schema-Härtung ist zu ~70 % vorhanden (`tradingagents/agents/utils/structured.py` zentralisiert alles); es fehlt nur der 1 Retry mit Fehlerkontext vor dem Prosa-Fallback. (5) Es gibt heute **keinerlei** API-Key-Validierung beim Start; die vollständige Provider→Env-Var-Map existiert verstreut (openai_client `_PROVIDER_CONFIG`, conftest `_API_KEY_ENV_VARS`, azure_client Docstring).

**Primary recommendation:** Fail-fast-Validierung zentral in `create_llm_client()` (factory.py) einhängen — deckt CLI und Python-API mit einem Hook ab; Budget-Callback als eigene Handler-Klasse mit `raise_error = True` neben dem bestehenden StatsCallbackHandler.

## Befunde je P1-Bereich

### 1. Release v0.2.5

**Versions-Fundstellen** [VERIFIED: repo grep]:
- `pyproject.toml:7` — `version = "0.2.4"` → einzige maschinenrelevante Stelle.
- `README.md:31` — News-Zeile „[2026-04] TradingAgents v0.2.4 released…". Konvention: pro Release eine News-Zeile (Format siehe README:30–34). Neue Zeile für v0.2.5 ist Claude's Discretion (D1 nennt nur CHANGELOG + pyproject + Compare-Links); empfohlen der Konsistenz halber.
- **Kein** `__version__` in `tradingagents/__init__.py`, kein Versions-Banner in `cli/main.py` [VERIFIED: grep auf `0.2.4|__version__`].

**CHANGELOG-Konventionen** [VERIFIED: CHANGELOG.md gelesen]:
- Keep-a-Changelog 1.1.0, SemVer. Sektions-Header: `## [0.2.5] — 2026-08-14` (Gedankenstrich `—`, kein Bindestrich).
- Sektions-Reihenfolge in 0.2.4: `### Added` → `### Changed` → `### Fixed` → `### Removed` → `### Contributors`. 0.2.1 nutzt zusätzlich `### Security` **an erster Stelle** (vor Added) — für #618 relevant: Security-Sektion zuerst.
- Einträge: Fließtext mit **Fett-Lead**, Issue-/PR-Nummern in Klammern `(#618)`.
- Compare-Links am Dateiende (CHANGELOG.md:260–267), neuester zuerst: `[0.2.5]: https://github.com/TauricResearch/TradingAgents/compare/v0.2.4...v0.2.5` als neue erste Zeile ergänzen.
- Es gibt **keine** „Unreleased"-Sektion (Milestone bestätigt das).

**Release-Inhalt** (die zwei Commits): `2c97bad` = fix(security) Ticker-Pfad-Validierung (#618) → `### Security`; `7e9e7b8` = DeepSeek V4 Thinking-Mode-Round-Trip via `DeepSeekChatOpenAI` → `### Added` oder `### Fixed` (Commit sagt „feat" → Added).

**Tag-Konvention** [VERIFIED: `git cat-file tag v0.2.4`]: annotierter Tag, Message „TradingAgents v0.2.4" + Leerzeile + „Highlights:" + Liste. Tagger setzt der Orchestrator (D1).

### 2. CI + Dev-Deps

**pyproject.toml-Struktur** [VERIFIED: gelesen]: build-backend `setuptools.build_meta`, `requires-python = ">=3.10"`, `[project.scripts] tradingagents = "cli.main:app"`, Packages `tradingagents*` + `cli*`, `[tool.pytest.ini_options]` existiert bereits (`testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`, Marker unit/integration/smoke, DeprecationWarning-Filter). `[dependency-groups]` (PEP 735) noch nicht vorhanden — neue Sektion ans Dateiende.

**requirements.txt** [VERIFIED]: Inhalt ist exakt `.` (eine Zeile) — reiner Verweis auf pyproject, keine Abweichung, nichts zu pflegen.

**Testsuite ohne Keys** [VERIFIED: tests/conftest.py]: autouse-Fixture `_dummy_api_keys` setzt Platzhalter für alle 10 Key-Env-Vars (`_API_KEY_ENV_VARS`, conftest.py:14–25); `mock_llm_client`-Fixture patcht `tradingagents.llm_clients.factory.create_llm_client`. Suite läuft in ~8 s ohne Netz/Keys (Milestone-Beleg 2026-08-14: 108 passed, 42 subtests). Die „Subtests" sind `unittest.TestCase.subTest` (test_google_api_key.py, test_model_validation.py) — pytest 9.0.3 zählt sie nativ, **kein** pytest-subtests-Plugin nötig [VERIFIED: venv pip list, nur pytest installiert].

**Import-Pfade:** Tests importieren `tradingagents.*` und `cli.utils` (tests/test_ticker_symbol_handling.py:5). Lokal via `PYTHONPATH=.` gelöst; in CI reicht `uv sync` (installiert das Projekt selbst, beide Packages sind in `[tool.setuptools.packages.find]`) → `uv run pytest` ohne PYTHONPATH-Trick. 5 Testdateien nutzen `import unittest`, Rest pytest-style mit MagicMock.

**Kritischer uv-Lock-Konflikt** (Pitfall #3 unten): `uv sync --locked`/`--frozen` schlägt fehl, sobald `[dependency-groups]` in pyproject steht, aber uv.lock (das nicht angefasst werden darf, D1/D7) die Gruppe nicht kennt. → CI muss **plain `uv sync`** verwenden (re-resolved im Runner, Lock bleibt im Repo unberührt). Reproduzierbarkeit ist bewusst P2 (Milestone Punkt 9).

**setup-uv-Syntax** [CITED: github.com/astral-sh/setup-uv, docs.astral.sh/uv/guides/integration/github]: aktuelle Major-Version v10; `uses: astral-sh/setup-uv@v10` mit `python-version: ${{ matrix.python-version }}` Input; danach `uv sync` + `uv run pytest`. `actions/checkout@v5`. pip-audit via `uvx pip-audit` (D3).

**Python-3.10-Kompatibilität:** Kein `tomllib`/`match`/`Self`-Gebrauch gefunden [VERIFIED: grep]; `str | Path`-Annotationen sind PEP 604 (3.10-ok) bzw. hinter `from __future__ import annotations`. `__pycache__` enthält cpython-310-Artefakte — Suite lief schon mal unter 3.10. Restrisiko gering, CI-Matrix verifiziert es.

### 3. Kosten-Budget (#582)

**Token-Tracking heute** [VERIFIED: cli/stats_handler.py komplett gelesen]:
- `StatsCallbackHandler(BaseCallbackHandler)` — thread-safe (Lock), zählt `llm_calls` (on_llm_start + on_chat_model_start), `tool_calls` (on_tool_start), `tokens_in/tokens_out` (on_llm_end via `generation.message.usage_metadata["input_tokens"/"output_tokens"]`). `get_stats()` liefert Dict.
- Registrierung CLI-seitig doppelt: (a) `TradingAgentsGraph(..., callbacks=[stats_handler])` (cli/main.py:956–961) → landet via `llm_kwargs["callbacks"]` im **LLM-Konstruktor** (trading_graph.py:83–84); (b) `graph.propagator.get_graph_args(callbacks=[stats_handler])` (cli/main.py:1052) → Graph-Config für Tool-Tracking (propagation.py:57–70).

**Graph-seitiger Callback-Pfad existiert** [VERIFIED]: `TradingAgentsGraph.__init__(callbacks=...)` reicht Callbacks an `create_llm_client(**llm_kwargs)` durch; **alle vier** Client-Familien haben `"callbacks"` in ihren Passthrough-Kwargs (openai_client.py:109, anthropic_client.py:10, google_client.py:34, azure_client.py:11). Ein Budget-Handler, der in `__init__` (z. B. bei gesetztem `max_cost_per_run`/`max_tokens_per_run` in config) automatisch zu `self.callbacks` hinzugefügt wird, greift damit auch für Python-API-Nutzer ohne CLI.

**⚠ Entscheidender LangChain-Mechanismus** [VERIFIED: installierte langchain_core 1.3.2, callbacks/base.py:503 + callbacks/manager.py:306–314]: `BaseCallbackHandler.raise_error = False` ist Default; `handle_event()` **fängt und loggt** Handler-Exceptions und re-raised **nur wenn `handler.raise_error` True ist**. Der Budget-Handler MUSS also `raise_error = True` als Klassenattribut setzen, sonst wird `BudgetExceededError` still geschluckt. Empfohlener Check-Punkt: `on_chat_model_start`/`on_llm_start` (Budget prüfen **bevor** der nächste teure Call rausgeht, auf Basis der akkumulierten Token aus on_llm_end).

**Zwei Ausführungspfade — beide müssen abfangen:**
1. **Python-API:** `TradingAgentsGraph.propagate()` (trading_graph.py:265–301) → `_run_graph()` (303–348): non-debug `graph.invoke()` (Z. 327), debug `graph.stream()` (Z. 319). BudgetExceededError propagiert aus invoke/stream heraus → sauber fangbar in `propagate()` um `self._run_graph(...)` (dort sitzt schon das try/finally für den Checkpointer, Z. 295–301). Partial-Reports: `_log_state()` (Z. 350–390) läuft heute nur bei Erfolg; bei `graph.invoke` gibt es im Fehlerfall **keinen** Partial-State im Speicher — mit `checkpoint_enabled` bleibt der Zustand aber in SQLite (resumefähig, D4-konform). Für Partial-Save ohne Checkpoint müsste `_run_graph` auf Stream-Basis den letzten Chunk halten (Chunks in `stream_mode="values"` sind der volle State nach jedem Node) — Design-Option für den Planner.
2. **CLI:** `run_analysis()` (cli/main.py:929) ruft **nicht** `propagate()`, sondern streamt direkt `graph.graph.stream(init_agent_state, **args)` (cli/main.py:1056). Die CLI speichert Report-Sektionen bereits **inkrementell** auf Platte (save_report_section_decorator, cli/main.py:999–1011 → `reports/*.md` je Sektion) — Partial-Reports sind dort also automatisch da; der Stream-Loop braucht nur ein try/except BudgetExceededError mit sauberer Meldung statt Traceback.

**Config & CLI-Flags:** Defaults in `tradingagents/default_config.py` (flaches Dict `DEFAULT_CONFIG`) — neue Schlüssel `max_cost_per_run: None`, `max_tokens_per_run: None`, `model_cost_rates: {}` dort ergänzen. CLI-Flow: `run_analysis()` kopiert `DEFAULT_CONFIG` und überschreibt aus `selections` (cli/main.py:934–946); das `--checkpoint`-Flag (Typer-Option am `@app.command()` `analyze`, cli/main.py:1200–1217) ist das exakte Vorbild für `--max-cost` (Option → `run_analysis(max_cost=...)` → `config["max_cost_per_run"]`). Fail-fast „--max-cost ohne Rates" gehört an den Anfang von `run_analysis` nach den Selections (Provider/Modelle dann bekannt).

**Ablageort Budget-Code:** nicht `cli/` — der Handler muss importierbar für Python-API-Nutzer sein. Empfehlung: neues Modul `tradingagents/budget.py` o. ä. (`BudgetCallbackHandler`, `BudgetExceededError`); `cli/stats_handler.py` bleibt unverändert Anzeige-only. Kein Parallel-Tracking: der Budget-Handler zählt selbst via denselben `usage_metadata`-Events (gleiche Logik, eigener Zweck) oder subklassiert `StatsCallbackHandler` — Achtung: Import-Richtung `tradingagents` → `cli` wäre eine Verletzung der Paketgrenzen; wenn geteilt, Zähl-Logik nach `tradingagents/` ziehen und `cli/stats_handler` re-exportieren lassen (Claude's Discretion).

### 4. Schema-Härtung (#583)

**Zentraler Mechanismus existiert bereits** [VERIFIED: tradingagents/agents/utils/structured.py komplett]:
- `bind_structured(llm, schema, agent_name)` (Z. 31–45): wrappt `llm.with_structured_output(schema)`, fängt `NotImplementedError`/`AttributeError` (z. B. DeepSeek-Reasoner, alte Ollama-Modelle) → `None` + Warnung.
- `invoke_structured_or_freetext(structured_llm, plain_llm, prompt, render, agent_name)` (Z. 48–73): try `structured_llm.invoke(prompt)` → `render(result)`; bei **jeder** Exception (`except Exception`, Z. 66) Warnung + direkter Prosa-Fallback `plain_llm.invoke(prompt).content`.

**Die drei Callsites** [VERIFIED]:
| Agent | Datei | Factory | Schema → Renderer | LLM |
|---|---|---|---|---|
| Research Manager | `tradingagents/agents/managers/research_manager.py:13–48` | `create_research_manager` | `ResearchPlan` → `render_research_plan` | deep (setup.py:80) |
| Trader | `tradingagents/agents/trader/trader.py:17–53` | `create_trader` | `TraderProposal` → `render_trader_proposal` | quick (setup.py:81) |
| Portfolio Manager | `tradingagents/agents/managers/portfolio_manager.py:24–72` | `create_portfolio_manager` | `PortfolioDecision` → `render_pm_decision` | deep (setup.py:87) |

Schemas + Render-Helpers in `tradingagents/agents/schemas.py` (Enums `PortfolioRating` Z. 32, `TraderAction` Z. 42; Renderer Z. 93/141/209). Prompt-Formen: RM/PM übergeben einen String, Trader eine Message-Dict-Liste — der Helper ist bereits prompt-agnostisch.

**Was heute fehlt (= D5-Delta):** Der „1 Retry mit Fehlerkontext" existiert nicht — bei Fehlschlag geht es sofort in Prosa. Umbau ist auf **eine Datei** begrenzt (`structured.py`): Retry = zweiter `structured_llm.invoke` mit angehängtem Fehlerkontext (Exception-Text an den Prompt anhängen; bei String-Prompt konkatenieren, bei Message-Liste User-Message anhängen), erst danach Prosa. Bestehende Tests decken den Ist-Zustand ab: `tests/test_structured_agents.py` (Mock-Muster: `MagicMock`-LLM, `with_structured_output.return_value = structured` bzw. `.side_effect = NotImplementedError`, Z. 102–160) und `tests/test_memory_log.py:87–101` — der Retry braucht neue Tests im selben Muster (`structured.invoke.side_effect = [ValidationError/Exception, gültiges Objekt]`).

**Was heute noch entweichen kann:** (a) Exceptions aus dem **Prosa-Fallback** selbst (`plain_llm.invoke`, structured.py:72 — Provider-/Netzfehler) — das sind keine Schema-Fehler, D5-Scope-Entscheidung des Planners; (b) `bind_structured` fängt nur `NotImplementedError`/`AttributeError` — andere Fehler beim Binden (selten) würden die Node-Erstellung, d. h. `TradingAgentsGraph.__init__`, abbrechen. Retry-Logik auf Provider-Ebene existiert separat (langchain `max_retries`-Passthrough), betrifft aber Transportfehler, nicht Schema-Validierung.

### 5. Secrets/Fail-fast (D6)

**Ist-Zustand — keine Start-Validierung** [VERIFIED: grep über cli/ + llm_clients/]:
- `cli/utils.py` (Provider-/Modell-Auswahl, Z. 21–360): fragt **nie** nach Keys, prüft **nie** Env-Vars.
- `cli/main.py:7–11`: `load_dotenv()` + `load_dotenv(".env.enterprise", override=False)` beim Import — Keys kommen aus `.env`/Env.
- OpenAI-kompatible Provider: `_PROVIDER_CONFIG` in `tradingagents/llm_clients/openai_client.py:113–120` mappt Provider→Env-Var (xai/deepseek/qwen/glm/openrouter; ollama = kein Key). Fehlt der Key, wird er **stillschweigend weggelassen** (Z. 153–156) → Crash erst beim ersten LLM-Call mitten im Run (genau das D6-Problem). Native OpenAI/Anthropic/Google lesen ihre Env-Vars implizit im LangChain-Client; Azure braucht `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, opt. `OPENAI_API_VERSION` (azure_client.py:25–29, nur Docstring).
- Alpha Vantage: einziger Ort mit Fail-fast-Ansatz — `tradingagents/dataflows/alpha_vantage_common.py:12–14` raised `ValueError` wenn Key fehlt (aber erst beim Tool-Call). Default-Vendor ist yfinance (keyless, default_config.py:40–45).
- Vollständige Key-Liste existiert bereits in `tests/conftest.py:14–25` (10 Env-Vars) und `.env.example`/`.env.enterprise.example` [VERIFIED: gelesen].

**Einhängepunkte (D6-konform, ohne Duplikation):** Zentrale Funktion im `llm_clients`-Paket (z. B. in `factory.py` oder `validators.py`): `provider → benötigte Env-Var(s)` — die Map aus `_PROVIDER_CONFIG` erweitern um openai/anthropic/google/azure statt neu bauen. Aufruf in `create_llm_client()` deckt **beide** Eintrittspfade ab (CLI `run_analysis` → `TradingAgentsGraph.__init__` → factory; Python-API identisch). Zusätzlich früher, freundlicher Check im CLI nach der Provider-Auswahl (rich-Meldung statt Stacktrace). Ollama: kein Key; OpenRouter/Azure-Sonderfälle beachten. **Achtung Tests:** conftest setzt Platzhalter-Keys autouse — Fail-fast-Tests müssen `monkeypatch.delenv` verwenden.

**Doku-Ort:** Kein `docs/`-Verzeichnis vorhanden [VERIFIED]. README hat bereits „Required APIs" (README.md:135–158, Export-Liste aller Keys + .env-Hinweis). Empfehlung: README-Abschnitt erweitern (Fail-fast-Verhalten, Docker-Secrets via `docker compose` + `.env`, Quota-/Kosten-Hinweis) statt neues docs/ für einen einzelnen Abschnitt — Claude's Discretion laut D6 („docs/ oder README").

## Don't Hand-Roll

| Problem | Nicht bauen | Stattdessen | Warum |
|---|---|---|---|
| Token-Zählung | eigenes Zähl-Framework | vorhandene `usage_metadata`-Extraktion (stats_handler.py:40–56) | funktioniert provider-übergreifend, thread-safe, getestet im Betrieb |
| Abort-Mechanik | Custom-Graph-Interrupt | Exception aus Callback mit `raise_error = True` | LangChain-nativer Weg; propagiert durch invoke/stream |
| Preistabelle | hartkodierte Modellpreise | user-supplied `model_cost_rates` | Maintainer-Entscheid #582 (gelockt, D4) |
| Schema-Fallback | neue Fallback-Pipeline | `invoke_structured_or_freetext` erweitern | Zentrale Stelle, alle 3 Agenten + Tests hängen dran |
| Key-Env-Map | neue Konstanten-Datei | `_PROVIDER_CONFIG` (openai_client.py:113) erweitern/zentralisieren | Single Source of Truth, D6 verbietet Duplikation |

## Package Legitimacy Audit

slopcheck nicht verfügbar auf dieser Maschine (Graceful Degradation greift). Registry via `pip index versions` erreichbar und geprüft:

| Package | Registry | Aktuelle Version | Verwendung | Status |
|---|---|---|---|---|
| pytest | PyPI | 9.0.3 (bereits im venv, 108 Tests laufen damit) | dev-Gruppe | Bereits im Projekt in Benutzung — kein Neu-Install-Risiko |
| ruff | PyPI | 0.16.3 [VERIFIED: pip index] | dev-Gruppe + CI-Lint | [ASSUMED] (kanonisches Astral-Tool; slopcheck-Bestätigung fehlt) |
| pip-audit | PyPI | 2.10.1 [VERIFIED: pip index] | nur CI via `uvx pip-audit` | [ASSUMED] (offizielles PyPA-Tool; slopcheck-Bestätigung fehlt) |

GitHub-Actions (keine PyPI-Pakete): `astral-sh/setup-uv@v10`, `actions/checkout@v5` [CITED: docs.astral.sh/uv/guides/integration/github].

## Common Pitfalls

1. **Callback-Exceptions werden geschluckt.** `BaseCallbackHandler.raise_error` ist per Default `False`; ohne `raise_error = True` im Budget-Handler kommt `BudgetExceededError` nie an (nur ein `logger.warning`). [VERIFIED: .venv langchain_core 1.3.2, callbacks/manager.py:306–314]
2. **CLI umgeht `propagate()`.** Budget-Abort nur in `propagate()` abzufangen deckt die CLI nicht — `cli/main.py:1056` streamt `graph.graph.stream(...)` direkt. Beide Pfade behandeln.
3. **`uv sync --locked/--frozen` bricht nach dependency-groups.** uv.lock darf nicht regeneriert werden (D1/D7); nach Ergänzung von `[dependency-groups]` passt der Lock nicht mehr zur pyproject → CI muss plain `uv sync` nutzen (re-resolve im Runner). Lokal gilt weiter: `.venv` + `PYTHONPATH=. python -m pytest` (Memory: `UV_OFFLINE=1` wegen SSL-Problemen der Maschine — uv-Netzzugriffe lokal vermeiden).
4. **`python-dotenv` ist undeklariert.** `cli/main.py:7` importiert `dotenv`, aber pyproject listet es nicht — es kommt nur transitiv (langchain-community → pydantic-settings → python-dotenv). Fix würde uv.lock ändern → in diesem Task **nicht** fixen, aber als Known Issue notieren (Kandidat v0.2.6/P2). CI-Tests betrifft es nicht direkt (kein Test importiert `cli.main`), `uv sync` installiert es transitiv mit.
5. **conftest-Platzhalter-Keys maskieren Fail-fast-Tests.** Autouse-Fixture setzt alle 10 Keys — Tests für „Key fehlt" brauchen explizites `monkeypatch.delenv(..., raising=False)`.
6. **Windows/Encoding-Konvention:** durchgängig explizites `encoding="utf-8"` bei jedem `open()`/`read_text()`/`write_text()` (Projektregel seit #543/#550/#576; Beispiele memory.py:42–58, trading_graph.py:389). Neue Dateien (Workflow-YAML unkritisch, aber jeder Python-I/O-Code) müssen das einhalten; deshalb auch der windows-latest-Job in D2.
7. **Git-Hygiene:** `.gitignore` und `uv.lock` sind aktuell **modified im Working Tree** (Operator-Drift) — niemals `git add -A`; nur explizite Pfade (D7). `.env` mit echten Keys liegt lokal im Repo-Root (gitignored, Zeile 151) — nie anfassen/committen.
8. **`—` vs `-` im CHANGELOG-Header** und Security-Sektion **vor** Added (0.2.1-Präzedenz) — Codex-Review wird auf Formattreue achten.

## Environment Availability

| Dependency | Benötigt von | Verfügbar | Version | Fallback |
|---|---|---|---|---|
| .venv Python | Tests lokal | ✓ | 3.13.13 | — |
| pytest | Tests | ✓ (venv) | 9.0.3 | — |
| ruff | Lint lokal | ✗ (nicht im venv) | — | CI-only; lokal `uvx ruff` (Achtung SSL/Offline-Memory) |
| slopcheck | Package-Audit | ✗ | — | Graceful degradation, Pakete [ASSUMED] |
| PyPI-Zugriff (pip) | Verifikation | ✓ | — | — |
| git | Release-Commit/Tag | ✓ | — | — |
| .github/workflows/ | CI | ✗ (existiert nicht) | — | wird neu angelegt |
| langchain_core (venv) | Callback-Verhalten | ✓ | 1.3.2 (pyproject verlangt nur >=0.3.81 — venv ist neuer als Lock/Spec) | — |

## Validation Architecture

| Property | Value |
|---|---|
| Framework | pytest 9.0.3 (+ unittest-TestCases, native Subtest-Zählung) |
| Config | `[tool.pytest.ini_options]` in pyproject.toml (kein pytest.ini) |
| Quick run | `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q -x` |
| Full suite | `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q` (Soll: 108 passed, 42 subtests, ~8 s) |

Requirement→Test-Map (neue Tests im Muster von test_structured_agents.py / test_checkpoint_resume.py):
- Budget (D4): neue `tests/test_budget.py` — Handler-Zählung, Abort bei Überschreitung (MagicMock-LLM), Fail-fast --max-cost ohne Rates. ❌ neu
- Schema-Retry (D5): Erweiterung `tests/test_structured_agents.py` — `side_effect=[Exception, obj]` → Retry-Erfolg; `[Exception, Exception]` → Prosa-Fallback. ❌ neu
- Fail-fast Keys (D6): neue Tests mit `monkeypatch.delenv`. ❌ neu
- Release/CI: kein Unit-Test; Verifikation = Suite grün + `ruff check` (E9,F63,F7,F82) grün + YAML-Syntax (z. B. `uvx --from yamllint yamllint` optional, oder Review).

## Open Questions (RESOLVED)

1. **Partial-Report-Save im Python-API-Pfad ohne Checkpoint** — bei `graph.invoke` gibt es keinen Zwischenstand im Speicher. Optionen: (a) nur mit `--checkpoint` resumefähig (minimal, D4-Wortlaut erfüllt: „mit --checkpoint bleibt der Run resumefähig"; CLI speichert Sektionen ohnehin inkrementell), (b) `_run_graph` auf Stream umstellen und letzten values-Chunk bei Abort loggen. Empfehlung: (b) ist klein (Stream statt invoke, gleiche Semantik) und liefert echten Partial-Save; Entscheidung beim Planner.
   → **RESOLVED (PLAN Task 3):** Option (b) umgesetzt — gemeinsame Stream-Methode `stream_run` in trading_graph.py hält den letzten values-Chunk und speichert ihn bei Budget-Abort via `_log_state` (deckt CLI- UND Python-API-Pfad).
2. **Budget-Zähl-Logik teilen oder duplizieren:** `cli/stats_handler.py` kann nicht aus `tradingagents/` importiert werden ohne Paketgrenzen-Verletzung. Empfehlung: Zähl-Kern nach `tradingagents/` (z. B. `tradingagents/budget.py`), CLI-Handler bleibt eigenständig für Anzeige — kein Umbau des bestehenden Handlers nötig (minimalinvasiv).
   → **RESOLVED (PLAN Task 3):** Neues Modul `tradingagents/budget.py` (SpendTracker, BudgetExceededError, BudgetConfigError); `cli/stats_handler.py` bleibt unverändert Anzeige-only.
3. **README-News-Zeile für v0.2.5** — nicht in D1 gefordert, aber Release-Konvention seit 0.2.0. Empfehlung: mit aufnehmen (eine Zeile, gleicher Commit).
   → **RESOLVED (PLAN Task 1):** README-News-Zeile für v0.2.5 ist Teil des Release-Commits.

## Sources

### Primary (HIGH confidence — Codebasis/Installation verifiziert)
- Repo-Dateien: pyproject.toml, CHANGELOG.md, README.md, requirements.txt, tests/conftest.py, tests/test_structured_agents.py, cli/main.py, cli/stats_handler.py, cli/utils.py, tradingagents/graph/{trading_graph,propagation,checkpointer,setup}.py, tradingagents/agents/utils/structured.py, tradingagents/agents/{managers,trader}/*.py, tradingagents/agents/schemas.py, tradingagents/llm_clients/{factory,openai_client,anthropic_client,google_client,azure_client,validators,model_catalog}.py, tradingagents/default_config.py, tradingagents/dataflows/alpha_vantage_common.py
- Installierte Pakete: `.venv` langchain_core 1.3.2 (callbacks/base.py, callbacks/manager.py — raise_error-Verhalten), pytest 9.0.3
- git: Tag-Format v0.2.4 (`git cat-file tag`), Remote origin, tracked files

### Secondary (MEDIUM confidence)
- [CITED: github.com/astral-sh/setup-uv + docs.astral.sh/uv/guides/integration/github] — setup-uv v10, Matrix-Syntax, checkout@v5 (WebSearch, mit offizieller Doku abgeglichen)
- PyPI via `pip index versions`: ruff 0.16.3, pip-audit 2.10.1

### Assumptions Log
| # | Claim | Sektion | Risiko |
|---|---|---|---|
| A1 | ruff / pip-audit legitim (slopcheck fehlt) | Package Audit | vernachlässigbar — kanonische Astral-/PyPA-Tools, Registry geprüft |
| A2 | Plain `uv sync` installiert die PEP-735-dev-Gruppe per Default | CI | uv-Standardverhalten; falls nicht, `uv sync --group dev` als expliziter Fallback im Workflow |

**Research date:** 2026-08-14 · **Valid until:** ~2026-09-14 (Codebasis-Fakten gelten bis zum nächsten Merge)
