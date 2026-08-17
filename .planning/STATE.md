# Project State — TradingEngineX (TradingAgents)

**Milestone:** Produktionsreife v0.2.x → v0.2.5 (siehe [MILESTONE.md](./MILESTONE.md))
**Branch:** main

## Current Position

Last activity: 2026-08-17 - main + Release-Tag zu Fork stevexyz2003/TradingAgents gepusht (Remote `fork`); lokales Release umbenannt in v0.2.5-tex (Upstream hat eigenes v0.2.5 released)

### Blockers/Concerns

- `uv.lock`-Drift lokal (+322/−1596) — Operator-Änderung, nicht anfassen (P2 im Milestone). Hinweis: Upstream hat uv.lock in 0b61eff komplett ENTFERNT — löst sich beim Rebase
- **Upstream weitergezogen:** origin/main ist 106 Commits voraus, Releases v0.2.5 (eigenes!), v0.3.0, v0.3.1. Unser Strang basiert auf v0.2.4. Folgen: (a) `v0.2.5` = Upstreams offizielles Release (a5cb7cb), unser Release heißt `v0.2.5-tex` (cf351de); (b) pyproject sagt bei uns 0.2.5 — kollidiert mit Upstream-Versionierung, beim Rebase renummerieren; (c) Upstream hat Teile unserer P1-Themen selbst adressiert (structured-output-Härtung 517eeaf, API-Key-Fixtures 8ab24f3, LLM-Retry-Budget daf1da9) — Rebase/Integration auf v0.3.1 ist ein eigener Task
- Kein Push-Zugriff auf origin (nur pull) — veröffentlicht wird über den Fork (`fork` = stevexyz2003/TradingAgents; fork/main per Force-Push auf unseren Strang gesetzt)
- Known Issues (v0.2.6-Kandidaten): `python-dotenv` undeklariert (nur transitiv, Fix ändert uv.lock); CLI-Memory-Parität (kein past_context/_resolve_pending_entries im CLI-Pfad — vorbestehend, Codex-Finding #4); CI-Lockfile-Policy (`uv sync` ohne `--locked`, bis uv.lock-Drift geklärt)
- Erster GitHub-Actions-Lauf nach Push beobachten (dev-group-Install-Annahme, Fallback-Kommentar in ci.yml)

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260814-fast | Meilenstein Produktionsreife erstellen (Codex-reviewed) | 2026-08-14 | 216e1d4 | Verified | — |
| 260814-k1j | P1-Punkte umsetzen: v0.2.5-Release (Tag auf cf351de), CI-Paket, Kosten-Budget (#582), Schema-Retry (#583), Fail-fast-Keys + 4 Codex-Review-Fix-Commits | 2026-08-14 | f5839f3 | Verified | [260814-k1j](./quick/260814-k1j-setz-die-p1-punkte-um-fang-mit-dem-v0-2-/) |
