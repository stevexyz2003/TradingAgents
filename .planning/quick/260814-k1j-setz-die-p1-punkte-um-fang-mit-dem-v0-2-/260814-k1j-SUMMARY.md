---
phase: quick-260814-k1j
plan: 01
subsystem: release, ci, budget, structured-output, config
tags: [v0.2.5, github-actions, budget-enforcement, schema-hardening, fail-fast]
requirements-completed: [P1-1, P1-2, P1-3, P1-4, P1-5]
dependency-graph:
  requires: []
  provides:
    - "Release-Metadaten v0.2.5 (CHANGELOG/pyproject/README) — Tag setzt der Orchestrator"
    - "CI-Workflow .github/workflows/ci.yml (test/lint/audit) + PEP-735 dev-Gruppe"
    - "tradingagents/budget.py: SpendTracker, BudgetExceededError, BudgetConfigError, build_spend_tracker"
    - "TradingAgentsGraph.stream_run: gemeinsamer Stream-Pfad CLI + Python-API"
    - "Retry-mit-Fehlerkontext in invoke_structured_or_freetext"
    - "MissingAPIKeyError + Fail-fast-Validierung in create_llm_client"
  affects: [cli/main.py, tradingagents/graph/trading_graph.py]
tech-stack:
  added: ["[dependency-groups] dev = pytest, ruff (Deklaration, kein lokaler Install)"]
  patterns: ["check-before-spend Callback (raise_error=True)", "unbound-method Tests mit MagicMock(spec=...)"]
key-files:
  created:
    - .github/workflows/ci.yml
    - tradingagents/budget.py
    - tests/test_budget.py
    - tests/test_api_key_failfast.py
  modified:
    - CHANGELOG.md
    - README.md
    - pyproject.toml
    - tradingagents/default_config.py
    - tradingagents/graph/trading_graph.py
    - tradingagents/agents/utils/structured.py
    - tradingagents/llm_clients/factory.py
    - cli/main.py
    - tests/test_memory_log.py
    - tests/test_structured_agents.py
metrics:
  duration: ~35 min
  completed: 2026-08-14
  tests: "137 passed, 42 subtests (Baseline 108 + 29 neue)"
---

# Quick Task 260814-k1j: P1-Umsetzung (v0.2.5 Release zuerst) Summary

Alle 5 P1-Punkte in D7-Reihenfolge umgesetzt: Release v0.2.5 (Security #618 zuerst), CI-Matrix mit plain uv sync, hartes Kosten-/Token-Budget mit Partial-Save über gemeinsame stream_run-Methode, Schema-Retry-dann-Prosa-Fallback, Fail-fast-Key-Validierung — 5 atomare Commits, 137 Tests grün.

## Commits (D7-Reihenfolge)

| Task | Commit | Message | Dateien |
| ---- | ------ | ------- | ------- |
| 1 | cf351de | chore: release v0.2.5 — ticker path security fix (#618), DeepSeek V4 thinking mode | CHANGELOG.md, pyproject.toml, README.md |
| 2 | 6bce117 | ci: add GitHub Actions (pytest matrix, ruff critical rules, pip-audit advisory) + dev dependency group | .github/workflows/ci.yml, pyproject.toml |
| 3 | 6d5b078 | feat(budget): enforce per-run cost/token budget with abort and partial save (#582) | tradingagents/budget.py, default_config.py, trading_graph.py, cli/main.py, tests/test_budget.py, tests/test_memory_log.py |
| 4 | 4e60282 | feat(structured): retry once with error context before prose fallback (#583) | structured.py, tests/test_structured_agents.py |
| 5 | 986ac5d | feat(config): fail-fast API key validation at startup + production secrets docs | factory.py, cli/main.py, README.md, tests/test_api_key_failfast.py |

## Was umgesetzt wurde

- **Task 1 (P1-1):** CHANGELOG-Sektion `## [0.2.5] — 2026-08-14` (Gedankenstrich, Security VOR Added), Compare-Link, Version-Bump auf 0.2.5, README-News-Zeile `[2026-08]`. Kein Tag, kein Push.
- **Task 2 (P1-2):** ci.yml mit Jobs test (ubuntu 3.10–3.13 + windows 3.13, fail-fast: false), lint (ruff nur E9,F63,F7,F82), audit (pip-audit via uvx, continue-on-error). Plain `uv sync` — nie --locked/--frozen (uv.lock kennt die dev-Gruppe nicht). PEP-735 `[dependency-groups]` dev = pytest, ruff.
- **Task 3 (P1-3, #582):** Neues Modul `tradingagents/budget.py`. SpendTracker mit `raise_error = True` (Klassenattribut, sonst schluckt langchain_core die Exception), check-before-spend in on_llm_start/on_chat_model_start, defensive Extraktion überall. `build_spend_tracker` validiert Rates beim Graph-Bau (BudgetConfigError, nie stilles 0-Kosten-Zählen). Gemeinsame Generator-Methode `TradingAgentsGraph.stream_run` kapselt Checkpointer-Setup/-Cleanup, thread_id-Injektion und Budget-Partial-Save (`_log_state` mit tolerantem `.get`-Zugriff). CLI: `--max-cost`, rote Meldung + Exit 1 bei BudgetConfigError/Abbruch statt Traceback.
- **Task 4 (P1-4, #583):** `invoke_structured_or_freetext`: 1 Retry mit Fehlerkontext (str-Prompt: angehängt; Message-Liste: neue User-Message, Original unmutiert), dann Prosa-Fallback mit ORIGINAL-Prompt. `except BudgetExceededError: raise` an BEIDEN Stellen — Budget-Abort wird nie als Schema-Fehler verschluckt.
- **Task 5 (P1-5):** `MissingAPIKeyError` + `_required_env_vars` in factory.py (Env-Var-Map aus `_PROVIDER_CONFIG` wiederverwendet, lazy import). Leer/Whitespace zählt als fehlend; expliziter `api_key`-kwarg ersetzt NUR `*_API_KEY`-Prüfungen (Azure Endpoint/Deployment bleiben validiert). README-Abschnitt "Secrets & configuration for production".

## Bugfix (dokumentationspflichtig)

**`--checkpoint` war im CLI-Pfad bisher wirkungslos:** cli/main.py streamte direkt über `graph.graph.stream(...)` an `propagate()` vorbei — Checkpointer wurde nie initialisiert, thread_id nie gesetzt, `_log_state` nie aufgerufen. Nach der Umstellung auf `graph.stream_run(...)` greifen Checkpointer, thread_id und Partial-Save erstmals auch in der CLI; die Abbruchmeldung ("resume with --checkpoint") ist jetzt korrekt.

## Deviations from Plan

None — plan executed exactly as written. (Der CLI-Stream-Loop wurde mit einem `while True / next(stream)`-Muster statt einem umschließenden try/except umgestellt — semantisch identisch zur Planvorgabe "try/except um den Stream-Loop", vermeidet Re-Indentierung von ~100 Zeilen Loop-Body.)

## Known Issues (NICHT gefixt, bewusst)

- **python-dotenv undeklariert:** `cli/main.py:7` importiert `dotenv`, das Paket kommt nur transitiv. Fix würde uv.lock ändern — Kandidat v0.2.6/P2.
- **CI-Commit (Task 2) liegt bewusst NACH dem Release-Commit:** Der Orchestrator taggt den Task-1-Commit (cf351de); CI gehört inhaltlich zu v0.2.6 (D2).

## Hinweis an den Orchestrator

Annotierten Tag **v0.2.5** nach dem Merge auf den Task-1-Commit (cf351de) setzen — Message "TradingAgents v0.2.5" + Highlights-Liste, Konvention wie v0.2.4. Highlights: ticker path-traversal security fix (#618), DeepSeek V4 thinking-mode round-trip.

## Verification (lokal, vom Orchestrator zu wiederholen)

1. `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -q` → **137 passed, 42 subtests, 0 failed**
2. `git log --oneline -5` → exakt 5 neue Commits in D7-Reihenfolge ✓
3. `git status --porcelain uv.lock .gitignore .mcp.json scripts/graphify.sh` → im Worktree leer; `git log 4327233..HEAD -- uv.lock .gitignore .mcp.json .idea .serena scripts/graphify.sh CLAUDE.md` → leer ✓
4. `git tag -l v0.2.5` → leer ✓
5. `grep -c 'graph\.graph\.stream(' cli/main.py` → 0 ✓

## Known Stubs

None.

## Self-Check: PASSED

- tradingagents/budget.py, tests/test_budget.py, tests/test_api_key_failfast.py, .github/workflows/ci.yml existieren ✓
- Commits cf351de, 6bce117, 6d5b078, 4e60282, 986ac5d in git log ✓
- Testsuite 137 passed ✓
