# Meilenstein: Produktionsreife v0.2.x → v0.2.5

> **ABGESCHLOSSEN am 2026-10-11.** Nachfolger ist **M2 — IBKR Paper Execution**
> ([ROADMAP.md](./ROADMAP.md), [REQUIREMENTS.md](./REQUIREMENTS.md)). Von der
> P2-Liste blieben bewusst zwei Punkte offen: #6 Observability/Alerting (M2
> Phase 8 bedient die Ausführungsseite credential-frei mit, die Analyseseite
> bleibt offen) und #8 Provider-Ausfall-Policy. Der eigentliche Beweis, dass
> der Meilenstein trägt: der tägliche Paper-Lauf produziert seit 2026-10-11
> Entscheidungen (AAPL Hold, $0.18 bei 12 % des Caps).

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
7. ~~**State-Betrieb definieren:** Retention/Backup für Decision-Log und Checkpoints, Verhalten bei parallelen Runs (Locking), Recovery bei korrupten SQLite-Dateien.~~
   **Erledigt 2026-10-11** (`28f4a75`, `e32c6a4`): `scripts/STATE_OPERATIONS.md`
   hält Pfade, Sidecars, Fristen und die fünf Locking-Lücken fest;
   `scripts/state_maintenance.py` (`verify`/`prune`/`backup`) macht
   Integritätsprüfung und Recovery ausführbar statt behauptet — 18 Tests, darunter
   eine künstlich korrupte DB (das `quick_check`-Pragma *wirft* dort, ein
   Rückgabevergleich hätte nie etwas gesehen) und der Beweis, dass `prune` die
   `-wal`/`-shm`-Sidecars mitnimmt und das Decision-Log nie anfasst.
8. **Provider-Ausfall-/Quota-Policy technisch verankern:** Timeout-/Retry-Obergrenzen, Degradations-Strategie (welcher Fallback wann), nicht nur dokumentieren.
9. **Release-Reproduzierbarkeit:** `uv.lock`-Drift klären (lokale Änderung +322/−1596 Zeilen — reviewen, committen oder verwerfen) und Lockfile-Policy festlegen; Build-/Publish-Prozedur für v0.2.5 festhalten.
10. ~~**End-to-End-Smoke in Docker:** Tests sind unit-nah; ein reproduzierbarer CLI-/Docker-Smoke mit Stub-Providern fehlt.~~
    **Erledigt 2026-10-11** (`12ed32d`): `scripts/smoke/docker_smoke.sh` +
    `scripts/smoke/stub_llm.py`, in CI als Job `docker-smoke`. Ein echter CLI-Lauf
    **durch das Image** gegen einen Stub-LLM im `--internal`-Netz, mit eingebauter
    Negativ-Kontrolle gegen einen unerreichbaren Endpunkt — damit ist genau das
    abgedeckt, was Unit-Tests nicht erreichen: Image, Entrypoint,
    Pfade/Permissions und die Client-Kette. Was der Smoke **nicht** beweist:
    inhaltliche Analysequalität — im isolierten Netz liefern alle Datenvendoren
    `DATA_UNAVAILABLE`.
11. **Betriebs-Runbook — Restumfang: Vendor-Quota-Verhalten.** Checkpoint-Hygiene
    (`--clear-checkpoints`), Memory-Log-Pflege (`memory_log_max_entries`) und der
    Recovery-Ablauf sind seit 2026-10-11 mit `scripts/STATE_OPERATIONS.md`
    (`e32c6a4`) abgedeckt. Offen bleibt allein das Vendor-Quota-Verhalten; es
    gehört sachlich zu Punkt 8 und wird dort entschieden, deshalb ist dieser Punkt
    reduziert und nicht abgehakt.

> **Bewusst offen (Operator-Entscheidung 2026-10-11):** Punkt 6
> (Observability/Alerting) und Punkt 8 (Provider-Ausfall-/Quota-Policy) wurden in
> der P2-Schlussrunde **nicht** angefasst und bleiben sichtbar offen. Der
> Produktivpfad (`daily-paper-run.yml`, `scripts/daily_paper_run.py`) läuft seit
> 2026-10-11 täglich und bekommt keine neuen beweglichen Teile — auch das
> Wartungswerkzeug aus Punkt 7 ist absichtlich *nicht* in den täglichen Lauf
> eingehängt.

### P3 — Hygiene
12. ~~Repo-Hygiene: lokale Tool-Artefakte bewusst committen oder lokal halten.~~
    **Erledigt 2026-10-11** (`4c1769b`): committet sind `CLAUDE.md`, `AGENTS.md`,
    `scripts/graphify.sh` und die `.gitignore`-Erweiterung; lokal bleiben
    `.mcp.json`, `.codex/`, `.claude/`, `.agents/`, `.serena/`, `.idea/` und
    `uv.lock` — die ersten tragen absolute `C:\Users\<name>\`-Pfade und dieses
    Fork ist öffentlich. Arbeitsbaum seitdem sauber (`git status` leer).

---

## Produktionsrisiken (bewusst offen)
- **LLM-Entscheidungen sind nicht deterministisch.** Produktiveinsatz nur hinter einem Paper-Trading-Gate (läuft in `ai_tradex`); kein direkter Live-Order-Flow aus diesem Framework.
- **Datenvendor-Abhängigkeit:** Alpha-Vantage-Quota und yfinance-Stabilität sind Community-Niveau; für Produktion ggf. bezahlten Datenfeed evaluieren.
- **Kosten:** Ein Full-Run über alle Agenten ist teuer; bis Budget-Enforcement (P1/3) steht, kein unbeaufsichtigter Dauerbetrieb.

## Definition of Done für diesen Meilenstein

**Stand 2026-10-11** (nachgezogen; die Haken sind gegen den Code auf `main` =
`1849413` geprüft, nicht gegen die Absicht):

- [x] ~~v0.2.5 getaggt~~ **obsolet durch die Rebase-Strategie:** `pyproject`
  trägt die Upstream-Version (jetzt 0.6.0), eigene Features stehen in der
  CHANGELOG-Sektion „Unreleased", eigene Tags gibt es seit 2026-08-18 nicht
  mehr (`v0.2.5-tex` war der letzte). #618 und DeepSeek V4 sind in Upstreams
  eigenen Releases dokumentiert.
- [x] CI-Pipeline grün — Fork-CI auf **py3.11–3.14** + Clean-Install-Smoke +
  strict ruff, Dev-Deps als `[dev]`-Extra deklariert (zuletzt grün: Run auf
  `0462c1a`).
- [x] Kosten-Budget pro Run erzwingbar — `tradingagents/budget.py`, hartes
  `max_cost_per_run`, Abbruch vor dem nächsten LLM-Call, Teilzustand wird
  gesichert; seit dem v0.5.0-Rebase zählen auch die Reflexions-Calls mit.
- [x] Schema-Fehler brechen den Run nicht ab — Retry mit Fehlerkontext in
  `tradingagents/agents/structured.py`, danach Prosa-Fallback.
- [x] Secrets-/Konfig-Doku + Fail-fast — README-Abschnitt „Secrets &
  configuration for production", `scripts/PAPER_RUN.md`, Credential-Prüfung
  über alle Tier-Provider (#1440).
- [x] Docker-/CLI-Smoke mit Stub-Providern läuft reproduzierbar —
  `scripts/smoke/docker_smoke.sh` + `scripts/smoke/stub_llm.py` (`12ed32d`),
  in CI als Job `docker-smoke` (`.github/workflows/ci.yml`, Zeitlimit 10 min).
  Lokal nachgewiesen am 2026-10-11: **zweimal hintereinander Exit 0**, beide mit
  `SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)`;
  der zweite Lauf war auch dann grün, wenn der erste per `SMOKE_KEEP=1`
  absichtlich Container und Netz stehen ließ (idempotentes Pre-Flight-Teardown).
  Die Negativ-Kontrolle läuft in einem eigenen Container `tex-smoke-neg` und endet
  mit Exit 1 — nicht 125 — plus Verbindungsfehler-Marker in der Ausgabe. Kein
  API-Key, kein echter LLM-Call: der Lauf hängt an einem `--internal`-Docker-Netz,
  in dem nur der Stub auflösbar ist, und der Stub-Zähler == 9 ist die Kontrolle,
  dass kein Call woanders landete.
- [x] Lockfile-Policy geklärt — Upstream hat `uv.lock` entfernt (0b61eff), die
  Operator-Kopie liegt untracked auf Disk; damit erledigt, kein Drift mehr.
- [x] State-Retention/Backup/Recovery dokumentiert — `scripts/STATE_OPERATIONS.md`
  (`e32c6a4`): beide Decision-Log-Orte getrennt, Sidecars mit ihren echten Namen,
  Fristen (Log unbegrenzt / Checkpoints 7 d / Reports 90 d) inklusive der ehrlichen
  Einschränkung, dass die 90 Tage nur das Workflow-Artefakt treffen, Rotation,
  Backup-Allow-List, Recovery ohne `.recover` und die fünf Locking-Lücken — jede
  Aussage mit `file:line`. Nicht nur Doku: `scripts/state_maintenance.py`
  (`verify`/`prune`/`backup`) mit **18 Tests** (`28f4a75`) macht die
  Integritätsprüfung ausführbar. Suite mit dem einen vorbestehenden
  `test_suite_isolation`-Knoten deselektiert: `1374 passed, 4 skipped,
  2 deselected, 20 warnings, 101 subtests passed in 29.62s`, rc=0.

**Nicht in der DoD, aber der eigentliche Zweck (siehe Korrektur oben):** der
tägliche Paper-Lauf produziert **seit 2026-10-11** Entscheidungen. Erster
erfolgreicher Lauf: AAPL auf Handelstag 2026-10-09, `signal=Hold`, **$0.1800**
(123305 in / 32004 out Tokens, 131 s) — 12 % des $1.50-Caps pro Ticker. Der
Eintrag liegt dauerhaft auf `paper-log` (`runs/2026-10-09/summary.json`).

Kostenprojektion für den Cron-Default (3 Ticker, Di–Sa): ~$0.54/Tag, also
~$12/Monat — und das ist die *konservative* Rechnung, weil die Rate-Tabelle
`claude-haiku-5-5` absichtlich zum >100K-Tarif ansetzt. Der Cap bleibt zunächst
bei $1.50: der Reflexions-Anteil wächst mit der Historie des Decision-Logs, und
8-facher Kopfraum ist billiger als ein abgebrochener Lauf.

Die 12 roten Läufe vom 2026-09-25 bis 2026-10-10 lagen ausschließlich an
Zugangsdaten (OpenAI ohne Guthaben, danach ein widerrufener Anthropic-Key mit
401), nicht am Code; jeder Fehlversuch kostete $0.00. Verifiziert ist damit die
ganze Kette: Preflight, Fehler-Semantik mit Exit-Codes, Keep-alive-Commit auch
im Fehlerfall, Budget-Buchhaltung und das persistente Decision-Log.

---

## Review
**Codex-Review** (codex-cli 0.137.0, read-only, 2026-08-14) — vollständig eingearbeitet:
- Faktenkorrektur: 5-Tier-Rating gilt nicht „über alle Entscheidungsstellen“ — Trader ist 3-Tier (→ korrigiert).
- Teststatus jetzt mit Beleg (Datum, Interpreter, Befehl, Output) statt unbelegter Grün-Aussage.
- Release-Stand präzisiert: „HEAD nach v0.2.4, noch ungetaggt“ statt implizitem „v0.2.5 in Arbeit“.
- Priorisierung angehoben: Dev-Dependencies in P1/CI gebündelt; Kosten-Budget und Schema-Validierung P2 → P1; `uv.lock`-Drift P3 → P2 (Release-Reproduzierbarkeit).
- Ergänzt: Security-/Dependency-Scanning, Build-/Publish-Prozedur + Lockfile-Policy, State-Betrieb (Retention/Backup/Locking/Recovery), technische Provider-Ausfall-Policy, Docker-E2E-Smoke; DoD entsprechend erweitert.
