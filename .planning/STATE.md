# Project State — TradingEngineX (TradingAgents)

**Milestone:** Produktionsreife v0.2.x → v0.2.5 (siehe [MILESTONE.md](./MILESTONE.md))
**Branch:** main

## Current Position

Last activity: 2026-08-18 - Rebase auf Upstream v0.3.1 (origin/main a33fd4c) abgeschlossen: 4 Feature-Ports + 4 Docs-Commits, Release-/CI-Commits gedroppt (upstream erledigt), 616 Tests grün

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
- Erster GitHub-Actions-Lauf nach Push beobachten (dev-group-Install-Annahme, Fallback-Kommentar in ci.yml)

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260814-fast | Meilenstein Produktionsreife erstellen (Codex-reviewed) | 2026-08-14 | 216e1d4 | Verified | — |
| 260814-k1j | P1-Punkte umsetzen: v0.2.5-Release (Tag auf cf351de), CI-Paket, Kosten-Budget (#582), Schema-Retry (#583), Fail-fast-Keys + 4 Codex-Review-Fix-Commits | 2026-08-14 | f5839f3 | Verified | [260814-k1j](./quick/260814-k1j-setz-die-p1-punkte-um-fang-mit-dem-v0-2-/) |
