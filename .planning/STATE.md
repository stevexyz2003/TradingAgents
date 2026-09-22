# Project State — TradingEngineX (TradingAgents)

**Milestone:** Produktionsreife v0.2.x → v0.2.5 (siehe [MILESTONE.md](./MILESTONE.md))
**Branch:** main

## Current Position

Last activity: 2026-09-22 - Rebase auf Upstream v0.5.0 (origin/main 2d17df8) auf Branch `rebase/upstream-v0.5.0`: 5 Features portiert (Budget #582 neu auf dem #1249-Lifecycle, Structured-Retry #583, Fail-fast-Keys, CLI-Ticker-Fehlermeldung, Paper-Lauf), 16 Commits über v0.5.0 + dieser Docs-Commit. Gates: ruff clean, Paper-Preflight ohne Keys rc=20, pytest 1024 passed / 4 failed — dieselben 4 umgebungsabhängigen Upstream-Tests wie auf purem v0.5.0 (mit TZ=UTC0 und ohne Yahoo-Netzprobe 1027 passed, 0 failed). Davor 2026-08-21: Täglicher Paper-Lauf als Heartbeat gebaut.

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

### Rebase-Protokoll (2026-09-22)

- **Basis:** v0.5.0 `2d17df8` (= origin/main, 90 Upstream-Commits über a33fd4c). Alter Strang gesichert als Branch `backup/pre-rebase-v0.5.0` @`16bbe96`; `backup/pre-rebase-v0.3.1` und Tag `v0.2.5-tex` bleiben. Gearbeitet im separaten Worktree `TradingEngineX-rebase-v050` (Branch `rebase/upstream-v0.5.0`); nichts gepusht, `main`/`fork/main` unverändert.
- **Gedroppt:** 402cd8b (leerer CI-Trigger-Commit, `--no-keep-empty`). Kein weiterer Commit automatisch oder per Auflösung gedroppt. Geschrumpft: 8eaadf5 (der `clear_run_checkpoint`-Teil entfällt — Upstreams `clear_checkpoint_on_success` läuft nach der Persistenz, bbcd666 räumt die SQLite-Sidecars) und 359bd03 (B904 schon bei der Auflösung gesetzt; bleibt Import-Sortierung + budget.py-Annotationen).
- **Portiert:** Budget (#582) auf Upstreams #1249-Lifecycle — Reset als erste Anweisung in `create_run_state` *vor* der Reflexion (trading_graph.py:566-567; die Reflektor-Kosten zählen jetzt zum Run, vorher wurden sie weggesetzt — bewusste Verhaltensänderung), `_run_graph` streamt immer und ruft bei Abbruch best-effort `_save_partial_state` (trading_graph.py:621/:633/:652), CLI-Abbruch innerhalb Upstreams begin_checkpoint/checkpoint_input/end_checkpoint-Block (cli/main.py:1311-1317); `stream_run` und `clear_run_checkpoint` entfernt, weil Upstream (#1249, CHANGELOG 0.4.0) beides besitzt. Structured-Retry (#583) unverändert (structured.py upstream unberührt). Fail-fast-Keys: Factory unverändert, CLI-Except `(BudgetConfigError, MissingAPIKeyError)`; Upstreams `ensure_api_key` schreibt den Key auch nach `os.environ` (cli/utils.py:672), Fail-fast kann nach einem Prompt also nicht fälschlich feuern. Ticker-Validierung behalten, aber auf Upstreams `_run_directory` umgebaut (cli/main.py:995 in v0.5.0 prüft schon vor jedem Disk-Write, wirft aber nur einen Traceback) — unser Anteil ist rote Meldung + Exit 1 (cli/main.py:1087-1091). Paper-Lauf unverändert, bis auf die Ratentabelle (s. u.).
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
- CLI-Memory-Parität — **erledigt upstream (geprüft 2026-09-22 gegen v0.5.0):** `create_run_state` ruft `_resolve_pending_entries` und injiziert `past_context` (tradingagents/graph/trading_graph.py:568, :573), die CLI startet über `graph.create_run_state` und loggt über `graph.record_decision` (cli/main.py:1174, :1307).
- Known Issues (v0.2.6-Kandidaten) — **alle drei erledigt upstream (geprüft 2026-09-22 gegen v0.5.0):** `python-dotenv` ist deklariert (pyproject.toml:19 `python-dotenv>=1.0.0`); CLI-Memory-Parität siehe oben; CI-Lockfile-Policy entfällt — ci.yml installiert per pip statt `uv sync` (.github/workflows/ci.yml:28, :43) und `uv.lock` ist seit 0b61eff nicht mehr im Baum.
- Fork-CI läuft und ist grün (Run 32138694932, alle 6 Jobs) — erledigt
- **Prämissen-Korrektur (2026-08-21):** `ai_tradex` konsumiert dieses Repo
  NICHT (0 Code-Referenzen; ADR-0026 baut das TradingAgents-Muster nativ
  nach). Die MILESTONE-Annahme „liefert das Framework unter ai_tradex" war
  falsch — daher der eigene Paper-Lauf als Daseinszweck.
- Reflexions-Horizont — **erledigt upstream (geprüft 2026-09-22 gegen v0.5.0):**
  `_fetch_returns` lässt einen Eintrag pending, bis das volle Haltefenster
  gehandelt ist (`len(stock) <= holding_days` → kein Settlement,
  tradingagents/graph/trading_graph.py:338; #1169, 30d42ab). Das Fenster ist
  über `holding_period_days` konfigurierbar (default_config.py:166, gelesen in
  trading_graph.py:379; 85d9137). Der Track-Record ist damit eine
  5-Tages-Renditereihe; `scripts/PAPER_RUN.md` entsprechend korrigiert.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260814-fast | Meilenstein Produktionsreife erstellen (Codex-reviewed) | 2026-08-14 | 216e1d4 | Verified | — |
| 260814-k1j | P1-Punkte umsetzen: v0.2.5-Release (Tag auf cf351de), CI-Paket, Kosten-Budget (#582), Schema-Retry (#583), Fail-fast-Keys + 4 Codex-Review-Fix-Commits | 2026-08-14 | f5839f3 | Verified | [260814-k1j](./quick/260814-k1j-setz-die-p1-punkte-um-fang-mit-dem-v0-2-/) |
| 260922-iz5 | Rebase strand onto upstream v0.5.0 (Budget auf #1249-Lifecycle neu aufgesetzt, gpt-5.6-Raten ergänzt, 402cd8b gedroppt) | 2026-09-22 | 164869a | Gates re-run (Promotion offen) | [260922-iz5](./quick/260922-iz5-rebase-strand-onto-upstream-v0-5-0/) |
