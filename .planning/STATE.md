---
gsd_state_version: 1.0
milestone: M2
milestone_name: IBKR Paper Execution
status: ready_to_plan
last_updated: "2026-10-19T07:03:51.902Z"
last_activity: 2026-10-19
progress:
  total_phases: 8
  completed_phases: 4
  total_plans: 41
  completed_plans: 33
  percent: 50
---

# Project State — TradingEngineX (TradingAgents)

**Milestone:** M2 — IBKR Paper Execution (siehe [ROADMAP.md](./ROADMAP.md) + [REQUIREMENTS.md](./REQUIREMENTS.md)), 8 Phasen / 68 Anforderungen, Phasen 1–2 abgeschlossen (Gate G1 zu seit 8f4b6ea), Phase 3 als Nächstes
**Vorgänger:** Produktionsreife v0.2.x → v0.2.5 — **abgeschlossen 2026-10-11** (siehe [MILESTONE.md](./MILESTONE.md)); bewusst offen geblieben: P2 #6 Observability (von M2 Phase 8 teilweise mitbedient) und P2 #8 Provider-Ausfall-Policy
**Branch:** main

## Current Position

Phase: 06 (die-erste-echte-order) — EXECUTING
Plan: 3 of 10
**Nächster Schritt: M2 Phase 5 planen — `/gsd:plan-phase 5`** (Kontext steht in
`.planning/phases/05-leitplanken-scharf/05-CONTEXT.md`). Kill-Switch, Ledger,
Lock, Reconciliation und neu das Sitzungsfenster aus REQ-IBKR-25, alles ohne eine
einzige Order; am Ende steht Gate G3 vor der Freigabe des Schreibrechts.
Phase 4 ist abgenommen (2026-10-16): 9/9 Pläne, Review-Fixes WR-01..06
(`04-REVIEW-FIX.md`), Verifikation `passed` (8/8, SC2 umformuliert: der
Read-Only-Schalter blockt auch `whatIf` und bleibt aus, Schutz ist die Socket-Sperre;
154 per Override), UAT `complete`. Gate G2 ist geschlossen.
Querschnitts-Fix d344433: Jede nicht als harmlos geführte System-Meldung
(`reqId == -1`) im Lesefenster verwirft den Read (`WINDOW_BENIGN_CODES`); vorher lief
z. B. 2157 (Sec-Def-Farm kaputt) still durch und konnte in `contracts.json` gelernt
werden.

Last activity: 2026-10-19

Davor: 2026-10-11 - **Beide offenen P2-Punkte geschlossen** (Quick-Task 261011-k4s, 4 Commits a734955..86ac1ae): Docker-/CLI-Smoke mit Stub-LLM im `--internal`-Netz (kein echter LLM-Call, 9 Stub-Calls, Negativ-Kontrolle gegen unerreichbaren Endpunkt) als CI-Job `docker-smoke`, dazu `scripts/state_maintenance.py` (prune/backup/verify, dry-run per Default, `quick_check` in try/except, Sidecar-Glob) mit 18 Tests und das Runbook `scripts/STATE_OPERATIONS.md`. Gates selbst nachgefahren: 1374 passed / rc=0, ruff clean, Smoke lokal gruen ohne Reste. Retention: Decision-Log unbegrenzt, Checkpoints 7 Tage, Reports 90 Tage. Der CI-Job `docker-smoke` ist seit Run 38147084939 gruen (7/7 Jobs). Der erste CI-Lauf schlug fehl und deckte einen Fehler im Gate selbst auf: `printf | grep -q` liess grep beim ersten Treffer aussteigen, printf starb an SIGPIPE, und `pipefail` + `if !` drehten das um - die Assertion scheiterte also genau dann, wenn der Marker GEFUNDEN wurde (lokal unsichtbar, weil der kuerzere Traceback in den 64-KiB-Puffer passte). Behoben mit Here-String (67b815a). Danach Code-Review mit 2 Blockern + 15 Warnungen: `prune` loeschte per Glob-Injection das WAL einer behaltenen DB, und negative Tageswerte loeschten heutigen State; beide samt 5 weiterer Befunde gefixt (b0205f2..9d7391b, 8 neue Regressionstests, 1382 passed). Verifier: 10/10 must-haves, keine Luecke. Davor am selben Tag: erster erfolgreicher Paper-Lauf (AAPL Hold, $0.18), v0.6.0-Rebase promoviert, P3-Repo-Hygiene.

### Heartbeat: täglicher Paper-Lauf (2026-08-21)

Beschluss nach der Stillstands-Analyse: Dieses Repo bekommt einen eigenen
Betriebszweck statt nur Framework-Zulieferer zu sein.

- **Was:** `.github/workflows/daily-paper-run.yml` (Di-Sa 06:30 UTC) ruft
  `scripts/daily_paper_run.py` für 2-3 Ticker mit hartem Kosten-Cap pro Ticker.

- **Wohin:** Reports als Build-Artefakt (90 Tage), Decision-Log + Index +
  Tages-Summary dauerhaft auf Branch `paper-log`. Der tägliche Commit hält
  außerdem den Cron am Leben (GitHub deaktiviert Schedules nach 60 Tagen
  Repo-Inaktivität).

- **Warum rot sichtbar wird:** Fehlende Credentials = grün mit Warning
  (kein Cry-Wolf), echte Fehler = rot mit Exit-Code-Semantik (1 Config,
  3 Ticker-Fehler, 4 Budget). Handbuch: `scripts/PAPER_RUN.md`.

- **Operator-Restaufgaben (bewusst offen, brauchen Zugangsdaten):**
  Provider-Secret im Fork setzen, `scripts/paper_run_rates.json` gegen die
  echte Preisliste prüfen (aktuell konservative Platzhalter), danach einen
  scharfen Lauf beobachten und `PAPER_RUN_MAX_COST` kalibrieren.

### Rebase-Protokoll (2026-10-17)

- **Basis:** v0.7.0 `e8f5503` (= origin/main, 11 Upstream-Commits über v0.6.0: `chatgpt`-Provider mit Plan-Anmeldung, Bewertung ab dem ersten Schlusskurs nach dem Entscheidungsdatum, Update-Hinweis nur mit Terminal, `cryptography>=42`/`packaging>=24`). Alter Strang gesichert als Branch `backup/pre-rebase-v0.7.0` @`fecb76b`. Gearbeitet im separaten Worktree `TradingEngineX-rebase-v070` mit eigenem venv; die Phase-5-Commits, die währenddessen auf `main` kamen, sind vor der Promotion nachgezogen (keiner berührt eine Upstream-Datei).
- **Methode:** linear; die 23 Executor-Merges des Strangs waren alle konfliktfrei entstanden (0 Auflösungs-Hunks) und sind aufgelöst. **Ein** Konflikt: `CHANGELOG.md` (Strang-Abschnitt über `[0.7.0]`). Alles andere, auch `cli/run.py`, `factory.py`, `default_config.py`, lief ohne Konflikt.
- **Gates:** pytest differentiell gegen pures v0.7.0 identisch (dieselben 5 Fehlschläge: 2× `test_chatgpt_auth`, 2× `test_cli_updates` — neu in 0.7.0 und auf diesem Windows-Rechner schon im Original rot — plus der bekannte `test_yfinance_keeps_its_cache_out_of_the_users_home`); Strang 2606 passed. ruff 0.17.1 sauber. Gegen den alten `main` unterscheiden sich nur die Upstream-Dateien; der Strang-Anteil in allen acht beidseitig geänderten Dateien ist zeilengleich.
- **Semantisch geprüft:** Unsere Fail-fast-Keys verlangen für `chatgpt` nichts (nur Anthropic/Google/Azure); das Eintragsformat von `decision-log.md` ist unverändert (`memory/log.py` unberührt), die IBKR-Kette liest `paper-log` wie bisher.
- **Nachzieharbeit:** Das Haupt-venv braucht `pip install -e ".[dev,ibkr]"` (tradingagents 0.7.0, `cryptography`, `packaging`).
- Protokoll: [261017-r7x](./quick/261017-r7x-rebase-strand-onto-upstream-v0-7-0/).

### Rebase-Protokoll (2026-10-10)

- **Basis:** v0.6.0 `1394a3f` (= origin/main, 135 Upstream-Commits über 2d17df8, inkl. v0.5.1 und v0.5.2). Alter Strang gesichert als Branch `backup/pre-rebase-v0.6.0` @`cc6a5dc`; `backup/pre-rebase-v0.5.0`, `backup/pre-rebase-v0.3.1` und Tag `v0.2.5-tex` bleiben. Gearbeitet im separaten Worktree `TradingEngineX-rebase-v060` (Branch `rebase/upstream-v0.6.0`) mit EIGENEM venv: das Haupt-`.venv` kann v0.6.0 nicht ausführen (yfinance 0.2.63 < 1.7.0 lässt schon `import tradingagents` scheitern, pandas 2.3.0 < 3.0.6, langgraph 0.4.8 < 1.2.12, langchain-core 1.3.2 < 1.6.5, ruff 0.15.12 < 0.16) und bleibt unangetastet. Nichts gepusht, `main`/`fork/main` unverändert.
- **Gedroppt:** kein Commit — alle 18 Strang-Commits liegen auf v0.6.0 (der leere CI-Trigger war schon beim v0.5.0-Rebase weg). **Geschrumpft:** 843c433 (nur noch die `budget.py`-Annotationen; der `cli/main.py`-Import-Teil entfällt, weil unsere CLI-Hälften nach `cli/run.py` umgezogen sind) und 3c42285 (best-effort-Save und die CLI-Meldung sind schon in 79ff6e4 so aufgesetzt; bleiben zwei `_run_graph`-Robustheitstests).
- **Portiert (neue Sitze):** Upstream hat `cli/main.py` auf eine 160-Zeilen-Typer-Hülle eingekürzt — unsere CLI-Hälften (Budget-Abbruch, `BudgetConfigError`/`MissingAPIKeyError`-Exit, Ticker-Validierung) sitzen jetzt in `cli/run.py` (:127-135, :143-149, :375-385, :408-418); `cli/main.py` ist byte-gleich mit Upstream. Der Structured-Retry (#583) zog von `agents/utils/structured.py` (upstream gelöscht) in Upstreams neues `agents/structured.py` und sitzt dort in `invoke_structured` (:90-127), das der Portfolio Manager direkt aufruft — der Retry deckt damit mehr Aufrufer ab als vorher. Der Budget-Reset bleibt die erste Anweisung in `create_run_state` (trading_graph.py:320-321); weil #1428/#1445 das Settlement als Graph-Schritt `_memory_step` fahren (trading_graph.py:330-343), zählt die Reflexions-Spend jetzt strukturell zum Run. `_run_graph` streamt über Upstreams eigenes `stream_run` (trading_graph.py:419) und speichert bei Abbruch den gemergten Zwischenstand (:429-433, `_save_partial_state` :442-470). Ein Budget-Abbruch wird weder von `_memory_step` noch von `invoke_structured` verschluckt (`except BudgetExceededError: raise` in trading_graph.py:347 und structured.py:110/:119). Fail-fast deckt über `create_tier_client` beide Tier-Provider ab (#1440): jeder Tier läuft durch `create_llm_client`, wo `_validate_credentials` sitzt (factory.py:94, :201-209) — mit eigenem Test für einen Deep-Tier auf fremdem Provider.
- **Konfliktauflösungen:**
  - 79ff6e4 `default_config.py`: Upstreams komplette neue Key-Liste (Tier-Provider, `holding_period_days`, `_ENV_OVERRIDES`) + unsere 3 Budget-Keys vor `checkpoint_enabled`.
  - 79ff6e4 `trading_graph.py`: Upstreams Lifecycle, `_memory_step`, `stream_run`, `run_config`-Kontexte und `run_rating`-Rückgabe wörtlich; dazu Budget-Import, Klassen-Default `spend_tracker = None`, Tracker-Bau vor `extra`, Reset in `create_run_state`, ein Stream-Loop mit `except BudgetExceededError`, `_save_partial_state`.
  - 79ff6e4 `cli/run.py`: Upstreams Stream-/Checkpoint-Block wörtlich; dazu `except BudgetConfigError` um den Graph-Bau, `except BudgetExceededError` vor Upstreams `finally`, Abschluss-Block nur ohne Abbruch, danach rote Meldung + Exit 1. `_save_partial_state` bekommt den gemergten `trace` statt nur des letzten Chunks und den Ticker als Argument — `self.ticker`/`self.curr_state` gibt es upstream nicht mehr, der `graph.ticker`-Workaround von 2026-09-22 ist damit erledigt.
  - 79ff6e4 Tests: `test_budget.py` auf `stream_run`-Paare, die 3-Argument-Signatur von `_save_partial_state` und `cli.run` umgeschrieben, + neue Tests für den Merge statt des letzten Chunks und für den Budget-Abbruch aus `_memory_step`. Upstream-Stubs: `test_memory_log.py` `graph.invoke` → `stream_run` (1 Zeile), `test_portfolio_context.py` `invoke` → `stream`-Generator (Assertions unverändert).
  - 6290e0e `agents/structured.py`: Upstreams Löschung des alten Moduls akzeptiert, `invoke_structured_or_freetext` upstream-gleich gelassen, Retry + `_with_error_context` + Budget-Re-raise in `invoke_structured` neu aufgesetzt; `test_structured_agents.py` rein additiv (130/0).
  - 2629505 `factory.py`: nur der Import-Konflikt; `MissingAPIKeyError`, `_required_env_vars` und der `_validate_credentials`-Aufruf bleiben in `create_llm_client`, Upstreams `build_llm_kwargs`/`tier_provider`/`create_tier_client` unverändert.
  - 8239ada: Upstreams `_run_directory`-Aufruf in `cli/run.py` in try/except gewickelt (rote Meldung + Exit 1); er liegt jetzt vor dem `Live`-Block, die Meldung ist also sichtbar.
  - 801f7e0 `CHANGELOG.md`: Unreleased-Sektion über `## [0.6.0] — 2026-10-03`, Intro auf v0.6.0; Upstream-Sektionen byte-gleich (0 gelöschte Zeilen gegen 1394a3f).
  - d9dc5fe (Fixup nach Gate-Fund): `scripts/daily_paper_run.py` importierte `safe_ticker_component` aus `tradingagents.dataflows.utils`, das Upstream nach `dataflows.symbols` verschoben hat — ohne den Fix bricht der Paper-Lauf beim Import. Dazu Platzhalter-Raten für `gpt-6-sol`/`gpt-6-luna` (sonst Exit 1 jeden Morgen) und UP017 (`datetime.UTC`), weil v0.6.0 auf py311 zielt.
- **Gates:** pytest HEAD `1 failed, 1353 passed, 4 skipped, 1 deselected, 99 subtests` gegen purem v0.6.0 `1 failed, 1258 passed, 4 skipped, 1 deselected, 99 subtests` — identische FAILED-Menge, nur `test_suite_isolation::test_yfinance_keeps_its_cache_out_of_the_users_home` (auf Windows liegt `TEMP` unter `Path.home()`, die Zusicherung des Tests gilt nur auf POSIX; auch mit `TZ=UTC0` rot, Upstream-CI auf Linux nicht betroffen). Unsere Änderungen bringen 95 Tests mehr. `ruff check .` clean (0.17.0, auch mit `--target-version py311`). Paper-Preflight ohne Credentials: rc=20, `deep=gpt-6-sol quick=gpt-6-luna`, ohne `--preflight` rc=1 vor dem Graph-Bau. venv des Worktrees: pandas 3.0.6, langgraph 1.2.14, langgraph-checkpoint-sqlite 3.1.1, langchain-core 1.6.9, langchain-openai 1.7.0, langchain-anthropic 1.7.5, langchain-google-genai 4.4.0, yfinance 1.7.0, markdown-it-py 4.2.0, ruff 0.17.0, pytest 9.1.1, `pip check` clean.
- **Versionsstrategie:** pyproject bleibt Upstreams v0.6.0 (dynamische Version aus `tradingagents.__version__`, beide Dateien byte-gleich mit 1394a3f); unsere Features als „Unreleased"-Sektion über `## [0.6.0]`. Kein Tag.
- **Offen:** Promotion nach `main` + Force-Push von `fork/main` braucht die Freigabe des Operators. Danach der Anthropic-Umbau des Paper-Runs (Secret, `TRADINGAGENTS_LLM_PROVIDER`, echte Claude-Preise) — die neuen Platzhalter-Raten `gpt-6-sol`/`gpt-6-luna` sind nur der Minimalstand, den der Guard-Test verlangt. Offen bleibt außerdem, dass `missing_credentials` im Paper-Run nur `config["llm_provider"]` prüft (daily_paper_run.py:371-372), während v0.6.0 je Tier einen eigenen Provider erlaubt — ein Tier-Key könnte ungeprüft fehlen; gehört zum Anthropic-Umbau.

### Rebase-Protokoll (2026-09-22)

- **Basis:** v0.5.0 `2d17df8` (= origin/main, 90 Upstream-Commits über a33fd4c). Alter Strang gesichert als Branch `backup/pre-rebase-v0.5.0` @`16bbe96`; `backup/pre-rebase-v0.3.1` und Tag `v0.2.5-tex` bleiben. Gearbeitet im separaten Worktree `TradingEngineX-rebase-v050` (Branch `rebase/upstream-v0.5.0`); nichts gepusht, `main`/`fork/main` unverändert.
- **Gedroppt:** 402cd8b (leerer CI-Trigger-Commit, `--no-keep-empty`). Kein weiterer Commit automatisch oder per Auflösung gedroppt. Geschrumpft: 8eaadf5 (der `clear_run_checkpoint`-Teil entfällt — Upstreams `clear_checkpoint_on_success` läuft nach der Persistenz, bbcd666 räumt die SQLite-Sidecars) und 359bd03 (B904 schon bei der Auflösung gesetzt; bleibt Import-Sortierung + budget.py-Annotationen).
- **Portiert:** Budget (#582) auf Upstreams #1249-Lifecycle — Reset als erste Anweisung in `create_run_state` *vor* der Reflexion (trading_graph.py:566-567; die Reflektor-Kosten zählen jetzt zum Run, vorher wurden sie weggesetzt — bewusste Verhaltensänderung), `_run_graph` streamt immer und ruft bei Abbruch best-effort `_save_partial_state` (trading_graph.py:621/:633/:652), CLI-Abbruch innerhalb Upstreams begin_checkpoint/checkpoint_input/end_checkpoint-Block (cli/main.py:1311-1317); `stream_run` und `clear_run_checkpoint` entfernt, weil Upstream (#1249, CHANGELOG 0.4.0) beides besitzt. Structured-Retry (#583) unverändert (structured.py upstream unberührt). Fail-fast-Keys: Factory unverändert, CLI-Except `(BudgetConfigError, MissingAPIKeyError)`; Upstreams `ensure_api_key` schreibt den Key auch nach `os.environ` (an HEAD `cli/prompts.py:681`; unter v0.5.0 lag die Funktion in `cli/utils.py`, neu geprüft 2026-10-10), Fail-fast kann nach einem Prompt also nicht fälschlich feuern. Ticker-Validierung behalten, aber auf Upstreams `_run_directory` umgebaut (cli/main.py:995 in v0.5.0 prüft schon vor jedem Disk-Write, wirft aber nur einen Traceback) — unser Anteil ist rote Meldung + Exit 1 (cli/main.py:1087-1091). Paper-Lauf unverändert, bis auf die Ratentabelle (s. u.).
- **Konfliktauflösungen:**
  - a6f8581 `default_config.py`: Upstreams `max_tokens` + unsere 3 Budget-Keys behalten.
  - a6f8581 `trading_graph.py`: Upstreams Datei als Basis; Budget-Import, `spend_tracker` im `__init__` (+ Klassen-Default `None` für Graphen ohne `__init__`), Reset in `create_run_state`, ein Stream-Loop in `_run_graph` statt debug-stream/else-invoke, neuer Helfer `_save_partial_state`.
  - a6f8581 `cli/main.py`: Upstreams #1249-Block wörtlich; dazu `except BudgetConfigError` um den Graph-Bau, `except BudgetExceededError` vor Upstreams `finally` (setzt `graph.ticker`, ruft `_save_partial_state`), Abschluss-Block nur ohne Abbruch, danach rote Meldung + Exit 1. Unser `while True`/`stream_run`-Loop verworfen.
  - a6f8581 Tests: `test_budget.py` von `stream_run`/`clear_run_checkpoint` auf `_run_graph`/`_save_partial_state`/`create_run_state`/CLI umgeschrieben (+ Integrationstest: Abbruch behält den Checkpoint, Resume schließt ab und cleared); Upstream-Stubs `graph.invoke` → `graph.stream` in `test_memory_log.py` und `test_portfolio_context.py` (Assertions unverändert).
  - 4a31720 `test_structured_agents.py`: Upstreams und unsere Tests behalten, keine Duplikate.
  - baf53d0 `cli/main.py`: statt zweitem `safe_ticker_component`-Aufruf Upstreams `_run_directory` in try/except gewickelt; die alte `Path(...)/selections["ticker"]`-Zeile nicht zurückgeholt.
  - 3944ac3 `CHANGELOG.md`: Unreleased-Sektion über `## [0.5.0] — 2026-09-18`, Intro auf v0.5.0, `stream_run()`-Bullet gestrichen, Fixed-Bullet auf die tatsächliche Wirkung umformuliert; Upstream-Sektionen byte-gleich.
  - 8eaadf5: best-effort-Save in `_save_partial_state`, CLI-Meldung verspricht keinen State-Save mehr; Tests auf den neuen Sitz verschoben.
  - 359bd03 `cli/main.py`: `MissingAPIKeyError`-Import an die sortierte Stelle vor `tradingagents.portfolio`.
  - 9916b84 (Fixup nach Gate-Fund): Upstream hat die Default-Modelle auf `gpt-5.6`/`gpt-5.6-luna` umgestellt, die Ratentabelle kannte sie nicht — der Lauf wäre jeden Morgen mit Exit 1 rot gewesen. Platzhalter-Raten für gpt-5.6/-terra/-luna ergänzt, Test-Fixture folgt `DEFAULT_CONFIG`, neuer Guard-Test prüft die Tabelle gegen die Defaults.
- **Gates:** 4 Upstream-Tests sind auf diesem Rechner umgebungsabhängig rot, identisch auf purem v0.5.0 (per `git archive` geprüft): 3× `test_ohlcv_cache_freshness` (nimmt UTC als lokale Zeitzone an; mit `TZ=UTC0` grün) und `test_no_data_handling::test_empty_download_raises_and_does_not_cache` (echte Yahoo-Erreichbarkeitsprobe). Upstream-CI (UTC, mit Netz) ist nicht betroffen.
- **Versionsstrategie:** pyproject bleibt Upstreams 0.5.0 (identisch zu 2d17df8); unsere Features als „Unreleased"-Sektion über 0.5.0. Kein Tag.
- **Offen:** Promotion nach `main` + Force-Push von `fork/main` ist ein eigener Schritt und braucht die Freigabe des Operators. Die neuen Platzhalter-Raten (gpt-5.6-Familie) gehören zur bestehenden Operator-Aufgabe „Ratentabelle gegen echte Preisliste prüfen".

### Rebase-Protokoll (2026-08-18)

- **Basis:** origin/main `a33fd4c` (v0.3.1 + 6 Fixes). Alter Strang gesichert als Branch `backup/pre-rebase-v0.3.1` und Tag `v0.2.5-tex`.
- **Gedroppt (upstream äquivalent/besser):** Release-Commit cf351de (#618 + DeepSeek V4 sind in Upstreams eigenem v0.2.5 dokumentiert; Version-Bump kollidierte) und CI-Commit 6bce117 (Upstream-CI ist strenger: strict ruff, clean-install-smoke; `[dev]`-Extras statt PEP-735-Gruppe; python-dotenv upstream als #994 gefixt).
- **Portiert:** Budget (#582, inkl. stream_run — CLI---checkpoint-Bugfix gilt auch gegen v0.3.1), Structured-Retry (#583, auf Upstreams None-Result-Pfad aufgesetzt), Fail-fast-Keys (Scope neu: nur native Familien anthropic/google/azure — OpenAI-kompatible validieren upstream registry-getrieben in get_llm), CLI-Ticker-Validierung.
- **Versionsstrategie:** pyproject bleibt auf Upstreams 0.3.1; unsere Features als „Unreleased"-CHANGELOG-Sektion. Kein neuer Tag bis zum nächsten Release-Schnitt.

### Blockers/Concerns

- Kein Push-Zugriff auf origin (nur pull) — veröffentlicht wird über den Fork (`fork` = stevexyz2003/TradingAgents, Force-Push nach Rebase nötig)
- uv.lock: Upstream hat die Datei entfernt (0b61eff) — Operator-Kopie liegt untracked auf Disk + Scratchpad-Backup; Lockfile-Thema damit erledigt
- CLI-Memory-Parität — **erledigt upstream (neu geprüft 2026-10-10 gegen v0.6.0):** die Lessons kommen jetzt aus dem Graph-Schritt `_memory_step`, der settelt und `past_context` zurückgibt (tradingagents/graph/trading_graph.py:330, :356, :362; verdrahtet in `__init__` über `memory_node=self._memory_step`, :128). Die CLI startet über `graph.create_run_state` (cli/run.py:237) und loggt über `graph.record_decision` (cli/run.py:371), nutzt also denselben Weg wie `propagate`. Die alte Zitatstelle `_resolve_pending_entries` existiert nicht mehr — die Methode ist in `tradingagents/memory/settlement.py` aufgegangen.
- Known Issues (v0.2.6-Kandidaten) — **alle drei erledigt upstream (neu geprüft 2026-10-10 gegen v0.6.0):** `python-dotenv` ist deklariert (pyproject.toml:20 `python-dotenv>=1.0.0`); CLI-Memory-Parität siehe oben; CI-Lockfile-Policy entfällt — ci.yml installiert per pip statt `uv sync` (.github/workflows/ci.yml:34 `pip install -e ".[dev]"`, :49 `pip install .`) und `uv.lock` ist nicht im Baum (`git ls-files uv.lock` leer).
- Fork-CI läuft und ist grün (Run 32138694932, alle 6 Jobs) — erledigt
- **Prämissen-Korrektur (2026-08-21):** `ai_tradex` konsumiert dieses Repo
  NICHT (0 Code-Referenzen; ADR-0026 baut das TradingAgents-Muster nativ
  nach). Die MILESTONE-Annahme „liefert das Framework unter ai_tradex" war
  falsch — daher der eigene Paper-Lauf als Daseinszweck.

- Reflexions-Horizont — **erledigt upstream (neu geprüft 2026-10-10 gegen v0.6.0):**
  die Logik ist aus `trading_graph.py` in das Settlement-Modul gezogen:
  `fetch_returns` lässt einen Eintrag pending, bis das volle Haltefenster
  gehandelt ist (`len(stock) <= holding_days` → kein Settlement,
  tradingagents/memory/settlement.py:81; #1169). Das Fenster ist über
  `holding_period_days` konfigurierbar (default_config.py:187, gelesen in
  settlement.py:130). NEU in v0.6.0: jeder Lauf settelt über `_memory_step` →
  `settle_all_pending(wait=False)` die fälligen Entscheidungen *aller* Ticker,
  nicht nur des analysierten (trading_graph.py:343, settlement.py:158-170;
  #1428, #1445) — eine Entscheidung wird damit beim ersten Lauf nach Ablauf
  ihres Fensters bewertet, unabhängig davon, welcher Ticker gerade analysiert
  wird. Der Track-Record ist weiter eine 5-Tages-Renditereihe;
  `scripts/PAPER_RUN.md` ist entsprechend korrigiert.

### Pending Todos

1 offen (`.planning/todos/pending/`):

- **Phase 04:** Jev-Fallback-Ratings in der IBKR-Vorschau markieren oder ausschließen. Im `decision-log.md` ist ein Jev-Rating nicht von einem Engine-Rating unterscheidbar, `ibkr_executor.py:1122` würde es als normale Entscheidung lesen. ([2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview](./todos/pending/2026-10-16-mark-or-exclude-jev-fallback-ratings-in-ibkr-preview.md))

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260814-fast | Meilenstein Produktionsreife erstellen (Codex-reviewed) | 2026-08-14 | 216e1d4 | Verified | — |
| 260814-k1j | P1-Punkte umsetzen: v0.2.5-Release (Tag auf cf351de), CI-Paket, Kosten-Budget (#582), Schema-Retry (#583), Fail-fast-Keys + 4 Codex-Review-Fix-Commits | 2026-08-14 | f5839f3 | Verified | [260814-k1j](./quick/260814-k1j-setz-die-p1-punkte-um-fang-mit-dem-v0-2-/) |
| 260922-iz5 | Rebase strand onto upstream v0.5.0 (Budget auf #1249-Lifecycle neu aufgesetzt, gpt-5.6-Raten ergänzt, 402cd8b gedroppt) | 2026-09-22 | 164869a | Promoted (fork/main) | [260922-iz5](./quick/260922-iz5-rebase-strand-onto-upstream-v0-5-0/) |
| 261010-raj | Rebase strand onto upstream v0.6.0 (#583-Retry in upstreams invoke_structured neu angesetzt, CLI-Ports nach cli/run.py, Budget-Re-raise durch _memory_step, gpt-6-Raten) | 2026-10-10 | a6a06b2 | Promoted (fork/main) | [261010-raj](./quick/261010-raj-rebase-strand-onto-upstream-v0-6-0/) |
| 261017-r7x | Rebase strand onto upstream v0.7.0 (ein Konflikt in CHANGELOG, Gates differentiell identisch, Phase-5-Commits nachgezogen) | 2026-10-17 | — | Promoted (fork/main) | [261017-r7x](./quick/261017-r7x-rebase-strand-onto-upstream-v0-7-0/) |
| 261011-k4s | P2 geschlossen: Docker-/CLI-Smoke mit Stub-LLM (ThreadingHTTPServer, Negativ-Kontrolle, CI-Job `docker-smoke`) + `scripts/state_maintenance.py` (prune/backup/verify, 18 Tests) + Runbook `scripts/STATE_OPERATIONS.md` | 2026-10-11 | 9d7391b | Verified (CI 7/7 gruen, Review-Fixes) | [261011-k4s](./quick/261011-k4s-p2-docker-cli-smoke-mit-stub-providern-u/) |
| 261012-sg6 | Jev (TypeSafe jev-1.13) als globaler Skill `~/.claude/skills/jev` (jev.py direkt/OpenRouter, Key `JEV_API_KEY` in gitignored `.env`), Live-Test 427 ms / ~$0.000024 | 2026-10-12 | — (Skill ausserhalb des Repos) | Verified | [261012-sg6](./quick/261012-sg6-wire-jev-decision-model-typesafe-jev-1-1/) |
| 261012-t8w | Jev opt-in in der Engine: `tradingagents/jev/` (stdlib-Client, nur `JEV_API_KEY`), Hook in `record_decision` mit REVIEW-Fallback (choice, Konfidenz ≥0.9, `final_rating_source="jev"`) + Shadow-Checks F2-F5 (PM/Research/Trader/Sentiment) → `final_state["jev"]`/Sidecar/Paper-Run; Läufe mit Portfolio-Kontext ausgeschlossen; Codex-Review BLOCK→SHIP | 2026-10-12 | 08eeff6 | Verified (Codex SHIP, 8/8) | [261012-t8w](./quick/261012-t8w-integrate-jev-into-tradingenginex-at-cla/) |
| 261012-uth | Nachtrag t8w: Jev-Review im Daily Paper Run aktiv (Secret `JEV_API_KEY`, `TRADINGAGENTS_JEV_ENABLED` default true) + BOM-Fix im Key-Lesen; AAPL-Testlauf 38301659963: 4/4 Checks einig, 154 ms, $0.00017 | 2026-10-12 | 2622b23 | Verified (Live-Lauf grün) | [261012-uth](./quick/261012-uth-enable-jev-review-in-the-daily-paper-run/) |
| 261018-kof | Vorhersagekette analysiert und mit Codex (gpt-6.1-sol, CLI 0.163) validiert: fork-Modul `tradingagents/patterns/` (6 Muster ohne Look-ahead, Wilson, MIN_N je Metrik) + `scripts/pattern_eval.py`; 8 Modul-Befunde gefixt, Upstream-Patch #5 in `backtest.py`; paper-log: alle Zellen insufficient (1 von 16 abgerechnet); #17 vorläufiger Exit-Bar = Upstream-Kandidat | 2026-10-18 | 33767b3 | Verified | [261018-kof](./quick/261018-kof-vorhersagelogik-und-statistische-heurist/) |
