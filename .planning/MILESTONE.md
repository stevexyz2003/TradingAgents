# Meilenstein: Produktionsreife v0.2.x → v0.2.5

**Stand:** 2026-08-14 · Branch `main`, HEAD `7e9e7b8` — 2 Commits nach Tag `v0.2.4`, noch ungetaggt (`pyproject.toml` steht auf 0.2.4)
**Ziel:** Das Framework soll in nächster Zeit produktiv eingesetzt werden. Dieser Meilenstein hält fest, was dafür bereits steht und was noch fehlt.

> Kontext: TradingEngineX ist der lokale Arbeitsklon von `TauricResearch/TradingAgents`
> (Multi-Agent-LLM-Trading-Framework, LangGraph).
>
> **Korrektur 2026-08-21:** Die ursprüngliche Annahme, der Produktivbetrieb laufe
> im Schwesterprojekt `ai_tradex` und dieses Repo liefere „das Framework darunter",
> ist faktisch falsch — `ai_tradex` referenziert `tradingagents` in keiner einzigen
> Code-Datei und baut das Muster per ADR-0026 nativ nach. Dieses Repo hat seinen
> Betriebszweck deshalb in sich selbst: den täglichen Paper-Lauf im Fork
> (`scripts/PAPER_RUN.md`), der zugleich als Heartbeat gegen erneuten Stillstand
> dient. Produktionsreife heißt hier: dieser Lauf trägt sich unbeaufsichtigt.

---

## ✅ Erledigt

### Kern & Agenten
- Multi-Agent-Pipeline stabil: 4 Analysten, Bull/Bear-Research, Trader, 3 Risk-Debater, Portfolio Manager (LangGraph).
- **Structured Output für das Entscheider-Trio** (Research Manager, Trader, Portfolio Manager) mit typisierten Pydantic-Schemas, providernativ (json_schema / response_schema / tool-use). (#434)
- **5-stufige Rating-Skala** (Buy/Overweight/Hold/Underweight/Sell) für Research Manager, Portfolio Manager, Signal-Processor und Memory-Log; der Trader bleibt bewusst 3-stufig (Buy/Hold/Sell). Signal-Processor liest deterministisch, ohne Extra-LLM-Call.

### Provider-Abdeckung
- 10 LLM-Provider: OpenAI, Anthropic, Google, xAI, OpenRouter (dynamische Modellauswahl), Ollama, DeepSeek, Qwen/DashScope, GLM/Zhipu, Azure OpenAI.
- `backend_url`-Leak in Fremd-Provider behoben; `base_url`-Proxy-Support überall.
- **DeepSeek V4 Thinking-Mode-Round-Trip** via `DeepSeekChatOpenAI` (@HEAD, unreleased).

### Robustheit & Betrieb
- **Checkpoint-Resume** (opt-in `--checkpoint`): abgestürzte Runs setzen am letzten erfolgreichen Node wieder auf; SQLite pro Ticker. (#594)
- **Persistentes Decision-Log** statt flüchtigem BM25-Memory: automatische Ablage je Run, Auflösung offener Einträge mit realisiertem Return + Alpha vs. SPY. (#578 u. a.)
- Tool-Fallbacks (Alpha Vantage primär, yfinance Fallback), Exponential-Backoff-Retries, Look-Ahead-Bias im Backtesting behoben (#475).
- Docker (Multi-Stage, dev + runtime), Cache/Logs unter `~/.tradingagents/` (Docker-Permissions gelöst, #519).
- Windows-tauglich: durchgängig explizites `encoding="utf-8"` (#543/#550/#576).

### Sicherheit
- **Ticker-Validierung vor Pfadverwendung** (Path-Traversal-Schutz, #618) — @HEAD, **noch in keinem Release**.
- `langchain-core`-Patch (LangGrinch, #335); `chainlit` (CVE-2026-22218) entfernt.

### Qualität
- Testsuite grün — letzter verifizierter Lauf: **2026-08-14**, `.venv` Python 3.13.13, `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q` → `108 passed, 42 subtests passed in 7.76s`.
- `scripts/smoke_structured_output.py` als Provider-Diagnose mit einem Kommando.
- Gepflegter CHANGELOG (Keep-a-Changelog, SemVer) bis v0.2.4.

---

## ⬜ Offen — auf dem Weg zum Produktivbetrieb

### P1 — blockierend
1. **Release v0.2.5 schnüren.** Zwei unveröffentlichte Commits auf `main`, darunter ein **Security-Fix** (#618). CHANGELOG hat keine „Unreleased“-Sektion → Einträge nachziehen, Version in `pyproject.toml` bumpen, taggen. Ein unveröffentlichter Security-Fix ist vor Produktivbetrieb nicht akzeptabel.
2. **CI aufsetzen — als Paket.** Es gibt **keine** `.github/workflows/`. Umfang: `pytest` auf Python 3.10–3.13 + Lint + Dependency-/Security-Scan (`pip-audit`/`uv audit` oder Dependabot). Dazu gehört zwingend, `pytest` (+ Lint-Tool) als Dev-Dependency-Gruppe in `pyproject.toml` zu deklarieren — heute läuft `uv run pytest` nicht reproduzierbar (venv ohne pytest, `sys.path`-Stolperer). CI ohne deklarierte Dev-Deps ist nicht baubar.
3. **Kosten-Budget pro Run erzwingen** (#582, Design-Feedback liegt vor). Das Framework soll unbeaufsichtigt im Paper-Trading-Loop laufen; ohne hartes Token-/Kosten-Limit ist Dauerbetrieb finanziell unkontrolliert — Anzeige allein reicht nicht.
4. **Strukturierte Validierung härten** (#583): Schema-Fehler der Provider sauber abfangen statt Run-Abbruch. Für Batch-/Scheduler-Betrieb ist ein abbrechender Run ein Betriebsblocker.
5. **Secrets-/Konfig-Handling für Produktion dokumentieren.** Welche Keys wohin (`.env`, Env-Vars, Docker-Secrets), Fail-fast-Validierung bei fehlendem/ungültigem Key statt Fehler mitten im Run.

### P2 — wichtig
6. **Observability für Dauerbetrieb:** Logs existieren, aber keine Metriken/Alerting (Vendor-Ausfälle, Fehlerraten, Latenz, Kosten je Run).
7. **State-Betrieb definieren:** Retention/Backup für Decision-Log und Checkpoints, Verhalten bei parallelen Runs (Locking), Recovery bei korrupten SQLite-Dateien.
8. **Provider-Ausfall-/Quota-Policy technisch verankern:** Timeout-/Retry-Obergrenzen, Degradations-Strategie (welcher Fallback wann), nicht nur dokumentieren.
9. **Release-Reproduzierbarkeit:** `uv.lock`-Drift klären (lokale Änderung +322/−1596 Zeilen — reviewen, committen oder verwerfen) und Lockfile-Policy festlegen; Build-/Publish-Prozedur für v0.2.5 festhalten.
10. **End-to-End-Smoke in Docker:** Tests sind unit-nah; ein reproduzierbarer CLI-/Docker-Smoke mit Stub-Providern fehlt.
11. **Betriebs-Runbook:** Checkpoint-Hygiene (`--clear-checkpoints`), Memory-Log-Pflege (`memory_log_max_entries`), Vendor-Quota-Verhalten, Recovery-Ablauf.

### P3 — Hygiene
12. Repo-Hygiene: lokale Tool-Artefakte (`.mcp.json`, `scripts/graphify.sh`, `.gitignore`-Erweiterung) bewusst committen oder lokal halten.

---

## Produktionsrisiken (bewusst offen)
- **LLM-Entscheidungen sind nicht deterministisch.** Produktiveinsatz nur hinter einem Paper-Trading-Gate (läuft in `ai_tradex`); kein direkter Live-Order-Flow aus diesem Framework.
- **Datenvendor-Abhängigkeit:** Alpha-Vantage-Quota und yfinance-Stabilität sind Community-Niveau; für Produktion ggf. bezahlten Datenfeed evaluieren.
- **Kosten:** Ein Full-Run über alle Agenten ist teuer; bis Budget-Enforcement (P1/3) steht, kein unbeaufsichtigter Dauerbetrieb.

## Definition of Done für diesen Meilenstein
- [ ] v0.2.5 getaggt, CHANGELOG vollständig (inkl. #618, DeepSeek V4)
- [ ] CI-Pipeline grün (Tests + Lint + Security-Scan) auf mind. 2 Python-Versionen, Dev-Deps deklariert
- [ ] Kosten-Budget pro Run erzwingbar
- [ ] Schema-Fehler der Provider führen nicht mehr zum Run-Abbruch
- [ ] Secrets-/Konfig-Doku für Produktion vorhanden, Fail-fast-Konfigvalidierung
- [ ] Docker-/CLI-Smoke mit Stub-Providern läuft reproduzierbar
- [ ] Lockfile-Policy geklärt, `uv.lock`-Drift aufgelöst
- [ ] State-Retention/Backup/Recovery (Decision-Log, Checkpoints) dokumentiert

---

## Review
**Codex-Review** (codex-cli 0.137.0, read-only, 2026-08-14) — vollständig eingearbeitet:
- Faktenkorrektur: 5-Tier-Rating gilt nicht „über alle Entscheidungsstellen“ — Trader ist 3-Tier (→ korrigiert).
- Teststatus jetzt mit Beleg (Datum, Interpreter, Befehl, Output) statt unbelegter Grün-Aussage.
- Release-Stand präzisiert: „HEAD nach v0.2.4, noch ungetaggt“ statt implizitem „v0.2.5 in Arbeit“.
- Priorisierung angehoben: Dev-Dependencies in P1/CI gebündelt; Kosten-Budget und Schema-Validierung P2 → P1; `uv.lock`-Drift P3 → P2 (Release-Reproduzierbarkeit).
- Ergänzt: Security-/Dependency-Scanning, Build-/Publish-Prozedur + Lockfile-Policy, State-Betrieb (Retention/Backup/Locking/Recovery), technische Provider-Ausfall-Policy, Docker-E2E-Smoke; DoD entsprechend erweitert.
