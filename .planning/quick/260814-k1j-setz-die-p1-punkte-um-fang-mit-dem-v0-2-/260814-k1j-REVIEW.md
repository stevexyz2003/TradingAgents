# Quick Task 260814-k1j — Review-Protokoll (Codex, D8)

**Reviewer:** OpenAI Codex (codex-cli 0.137.0, read-only Sandbox)
**Datum:** 2026-08-14

## Runde 1 — Plan-Review (vor Ausführung)

3 HIGH / 3 MEDIUM / 1 LOW — alle in PLAN.md-Revision 1 eingearbeitet (u. a. gemeinsame `stream_run`-Methode für CLI + Python-API, Rates-Validierung in `build_spend_tracker`, Azure-Teilvalidierung). Zusätzlich Plan-Checker: 0 Blocker + 4 Warnings (Runde 1), 1 Blocker (Runde 2: test_memory_log-Kollision) — behoben in Revision 2.

## Runde 2 — Code-Review (nach Ausführung, Commits cf351de..986ac5d)

| # | Schwere | Finding | Outcome |
|---|---------|---------|---------|
| 1 | HIGH | SpendTracker akkumuliert über Runs (kein Reset bei Graph-Wiederverwendung) | **Gefixt** (d09904f): `reset()` zu Beginn von `stream_run` |
| 2 | HIGH | CLI-Ticker ungeprüft als Pfadkomponente (results_dir, Save-Pfad) — #618 deckte nur Graph-Pfade | **Gefixt** (a6ab202): `safe_ticker_component` vor Verzeichnisanlage. Hinweis: Alt-Code, nicht durch diesen Task eingeführt; bleibt für v0.2.6 unreleased |
| 3 | MEDIUM | CLI-Erfolgspfad: `clear_checkpoint` fehlte → stale Checkpoints | **Gefixt** (d09904f): Erfolgs-Clear in `stream_run` verschoben (Parität CLI/API) |
| 4 | MEDIUM | CLI baut init_state ohne past_context, `_resolve_pending_entries` fehlt (Memory-Parität) | **Deferred** (vorbestehende Lücke, nicht durch Task eingeführt; Known Issue v0.2.6/P2) |
| 5 | MEDIUM | Alias-/Revisionsmodellnamen → $0-Kosten trotz max_cost | **Gefixt** (d09904f): Präfix-Match + konservativer Teuerste-Rate-Fallback |
| 6 | MEDIUM | Azure: OPENAI_API_VERSION nicht validiert | **Gefixt** (f5839f3) |
| 7 | LOW | `response=None` → AttributeError bei raise_error=True | **Gefixt** (d09904f) |
| 8 | LOW | CI ohne `--locked` nicht reproduzierbar | **Bewusst offen** (D2-Entscheidung: uv.lock-Drift ist P2; Lockfile-Policy folgt) |

**Unauffällig laut Codex:** structured.py-Retry (BudgetExceededError-Re-raise korrekt an beiden Stellen).

**Nach den Fixes:** Testsuite 148 passed + 42 subtests (11 neue Tests für Reset, Raten-Fallback, Checkpoint-Clear/Keep, Azure-api_version).
