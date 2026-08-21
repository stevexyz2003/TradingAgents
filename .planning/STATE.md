# Project State — TradingEngineX (TradingAgents)

**Milestone:** Produktionsreife v0.2.x → v0.2.5 (siehe [MILESTONE.md](./MILESTONE.md))
**Branch:** main

## Current Position

Last activity: 2026-08-21 - Täglicher Paper-Lauf als Heartbeat gebaut (Cron-Workflow + Runner + paper-log-Branch). Davor 2026-08-18: Rebase auf Upstream v0.3.1 (origin/main a33fd4c), 4 Feature-Ports + 4 Docs-Commits, Fork-CI vollständig grün (Run 32138694932).

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

### Rebase-Protokoll (2026-08-18)

- **Basis:** origin/main `a33fd4c` (v0.3.1 + 6 Fixes). Alter Strang gesichert als Branch `backup/pre-rebase-v0.3.1` und Tag `v0.2.5-tex`.
- **Gedroppt (upstream äquivalent/besser):** Release-Commit cf351de (#618 + DeepSeek V4 sind in Upstreams eigenem v0.2.5 dokumentiert; Version-Bump kollidierte) und CI-Commit 6bce117 (Upstream-CI ist strenger: strict ruff, clean-install-smoke; `[dev]`-Extras statt PEP-735-Gruppe; python-dotenv upstream als #994 gefixt).
- **Portiert:** Budget (#582, inkl. stream_run — CLI---checkpoint-Bugfix gilt auch gegen v0.3.1), Structured-Retry (#583, auf Upstreams None-Result-Pfad aufgesetzt), Fail-fast-Keys (Scope neu: nur native Familien anthropic/google/azure — OpenAI-kompatible validieren upstream registry-getrieben in get_llm), CLI-Ticker-Validierung.
- **Versionsstrategie:** pyproject bleibt auf Upstreams 0.3.1; unsere Features als „Unreleased"-CHANGELOG-Sektion. Kein neuer Tag bis zum nächsten Release-Schnitt.

### Blockers/Concerns

- Kein Push-Zugriff auf origin (nur pull) — veröffentlicht wird über den Fork (`fork` = stevexyz2003/TradingAgents, Force-Push nach Rebase nötig)
- uv.lock: Upstream hat die Datei entfernt (0b61eff) — Operator-Kopie liegt untracked auf Disk + Scratchpad-Backup; Lockfile-Thema damit erledigt
- CLI-Memory-Parität (kein past_context im CLI-initState) besteht auch upstream weiter — Known Issue, kein Port-Regress
- Known Issues (v0.2.6-Kandidaten): `python-dotenv` undeklariert (nur transitiv, Fix ändert uv.lock); CLI-Memory-Parität (kein past_context/_resolve_pending_entries im CLI-Pfad — vorbestehend, Codex-Finding #4); CI-Lockfile-Policy (`uv sync` ohne `--locked`, bis uv.lock-Drift geklärt)
- Fork-CI läuft und ist grün (Run 32138694932, alle 6 Jobs) — erledigt
- **Prämissen-Korrektur (2026-08-21):** `ai_tradex` konsumiert dieses Repo
  NICHT (0 Code-Referenzen; ADR-0026 baut das TradingAgents-Muster nativ
  nach). Die MILESTONE-Annahme „liefert das Framework unter ai_tradex" war
  falsch — daher der eigene Paper-Lauf als Daseinszweck.
- Reflexions-Horizont: `_fetch_returns` löst schon bei 2 Kursbalken auf, bei
  täglicher Kadenz also nach ~1 Handelstag statt der vorgesehenen 5. Der
  Track-Record ist damit eine 1-Tages-Renditereihe. Sauberer Fix (`len(bars)
  > holding_days`) wäre upstream-relevant — bewusst nicht mitgemacht.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260814-fast | Meilenstein Produktionsreife erstellen (Codex-reviewed) | 2026-08-14 | 216e1d4 | Verified | — |
| 260814-k1j | P1-Punkte umsetzen: v0.2.5-Release (Tag auf cf351de), CI-Paket, Kosten-Budget (#582), Schema-Retry (#583), Fail-fast-Keys + 4 Codex-Review-Fix-Commits | 2026-08-14 | f5839f3 | Verified | [260814-k1j](./quick/260814-k1j-setz-die-p1-punkte-um-fang-mit-dem-v0-2-/) |
