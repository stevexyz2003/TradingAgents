# Quick Task 260814-k1j: Setz die P1-Punkte um, fang mit dem v0.2.5 Release an - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning
**Modus:** Entscheidungen autonom getroffen (KD-19 — User arbeitet nicht live mit); Grundlage: MILESTONE.md (Codex-reviewed), Maintainer-Feedback auf PR #582/#583, Repo-Zustand.

<domain>
## Task Boundary

Alle fünf P1-Punkte aus `.planning/MILESTONE.md` umsetzen, Reihenfolge: Release zuerst.

1. Release v0.2.5 (CHANGELOG, Version-Bump, Tag)
2. CI-Paket (Workflows + Dev-Deps + Security-Scan)
3. Kosten-Budget pro Run erzwingen
4. Strukturierte Validierung härten (kein Run-Abbruch bei Schema-Fehlern)
5. Secrets-/Konfig-Handling: Doku + Fail-fast-Validierung

</domain>

<decisions>
## Implementation Decisions

### D1 — Release-Zuschnitt v0.2.5
- v0.2.5 enthält **nur** die zwei bereits vorhandenen Commits (`2c97bad` Security-Fix #618, `7e9e7b8` DeepSeek V4) plus Release-Commit (CHANGELOG-Sektion 0.2.5, `pyproject.toml` → 0.2.5, Compare-Links).
- **Annotierter** Tag `v0.2.5` mit Message „TradingAgents v0.2.5“ (Konvention wie v0.2.4). Tag setzt der **Orchestrator nach dem Worktree-Merge** auf den Release-Commit — nicht der Executor.
- **Kein Push** (weder Commits noch Tag) — origin ist TauricResearch/TradingAgents; Push entscheidet der User.
- `uv.lock` wird **nicht angefasst** (lokale Operator-Drift, als P2 im Milestone geführt).

### D2 — CI-Design
- `.github/workflows/ci.yml`: uv-basiert (astral-sh/setup-uv), pytest-Matrix Python 3.10/3.11/3.12/3.13 auf ubuntu-latest **plus** windows-latest mit 3.13 (Windows-Bug-Historie des Projekts: cp1252/Encoding).
- Lint: `ruff check` **nur kritische Regeln** (E9, F63, F7, F82) — Tag-1-grün; Ausbau später.
- Security-Scan: `pip-audit` als eigener Job, zunächst **advisory** (`continue-on-error: true`) — dauerhaft rote CI wird ignoriert und ist schlimmer; Eskalation auf blocking steht ins Runbook (P2).
- CI-Commit landet **nach** dem Tag (gehört zu v0.2.6, nicht ins v0.2.5-Release).

### D3 — Dev-Dependencies
- PEP-735-`[dependency-groups]` in `pyproject.toml`: `dev = ["pytest", "ruff"]` (uv-nativ). Keine weiteren Tools — pip-audit läuft in CI via uvx.

### D4 — Kosten-Budget (#582)
- Maintainer-Position (PR #582, closed): Callback + Abort + Partial-Save ist die richtige Form, aber **keine hartkodierte Preistabelle** — Kosten nur mit **user-supplied Rates**.
- Design: `max_cost_per_run` (USD, Default `None` = aus) + user-supplied Rates in der Config (`model_cost_rates`: USD pro 1M Input-/Output-Tokens). Zusätzlich `max_tokens_per_run` als ratenfreie Alternative (Token-Zählung existiert bereits im Stats-Handler).
- `BudgetExceededError` → `propagate()` bricht **sauber** ab: bisherige Reports werden gespeichert, Abbruchgrund geloggt; mit `--checkpoint` bleibt der Run resumefähig.
- CLI: `--max-cost` Flag. `--max-cost` ohne konfigurierte Rates → Fail-fast mit klarer Meldung (keine stillen Schätzpreise).

### D5 — Schema-Härtung (#583)
- Scope bleibt das Entscheider-Trio (Research Manager, Trader, Portfolio Manager) — Prosa-Agenten sind laut Maintainer-Entscheid bewusst prose-first; NICHT alle 13 Nodes umbauen.
- Muster je strukturiertem Call: 1 Retry mit Fehlerkontext, danach **Fallback auf Prosa-Aufruf** + bestehende Markdown-Render-/Parse-Pipeline (SignalProcessor liest gerendertes Markdown deterministisch). Schema-Fehler dürfen den Run nie mehr abbrechen; Warnung wird geloggt.

### D6 — Secrets/Konfig
- Doku: neuer Abschnitt (docs/ oder README) — welche Keys wohin (.env / Env-Vars / Docker), Verhalten bei fehlendem Key, Kosten-/Quota-Hinweise.
- Fail-fast: Validierung beim Start (CLI-Eintritt + `TradingAgentsGraph.__init__`): fehlender/leerer API-Key für den gewählten Provider → sofortige klare Fehlermeldung statt Crash mitten im Run. Bestehende Katalog-/Provider-Validierung nutzen, nicht duplizieren.

### D7 — Commit-/Release-Reihenfolge
1. Release-Commit (CHANGELOG + Version) → darauf Tag v0.2.5 (durch Orchestrator, nach Merge)
2. CI + Dev-Deps
3. Budget-Enforcement (D4)
4. Schema-Härtung (D5)
5. Secrets-Doku + Fail-fast (D6)
Atomare Commits je Punkt; keine Vermischung. Niemals `git add -A`/`-u` — nur explizite Pfade; `.gitignore`, `uv.lock`, `.mcp.json`, `.idea/`, `.serena/`, `scripts/graphify.sh` nicht anfassen (Operator-Dateien).

### D8 — Review-Kette (--review Codex)
- Codex reviewt den PLAN vor Ausführung (HIGH-Findings → Revision) und den Gesamt-Diff nach Ausführung (statt separatem gsd-code-reviewer — User hat Codex explizit als Reviewer benannt).
- Orchestrator verifiziert Executor-Claims selbst (Testlauf lokal wiederholen — Memory: Self-Claims nicht trauen).

### Claude's Discretion
Alle obigen Entscheidungen; eskaliert wird nur, falls Push/Remote-Operationen nötig würden (bleiben aus) oder ein P1-Punkt ohne destruktive Eingriffe nicht umsetzbar ist.

</decisions>

<specifics>
## Specific Ideas

- Token-Tracking existiert bereits in `cli/stats_handler.py` (Maintainer-Hinweis in #582) — Budget-Enforcement dockt dort bzw. an einem graph-nahen Callback an, kein Parallel-Tracking bauen.
- Structured-Output-Callsites: eingeführt in Commits `0fda245`/`bba1477` (#434) — Research soll exakte Dateien/Funktionen liefern.
- Testsuite: 108 Tests, läuft via `.venv` (Python 3.13); `PYTHONPATH=.` nötig bzw. `python -m pytest`.

</specifics>

<canonical_refs>
## Canonical References

- `.planning/MILESTONE.md` — P1-Definition (Codex-reviewed)
- GitHub PR #582 (closed) — Budget-Design + Maintainer-Feedback (user-supplied rates)
- GitHub PR #583 (closed) — Validierungs-Design + Maintainer-Entscheid (Trio-only, with_structured_output)
- `CHANGELOG.md` — Keep-a-Changelog-Format, Compare-Link-Konvention

</canonical_refs>
