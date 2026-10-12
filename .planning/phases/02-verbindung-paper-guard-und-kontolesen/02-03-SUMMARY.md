---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 03
subsystem: paper-run / reporting
tags: [portfolio, paper-run, report, REQ-IBKR-11]
requires:
  - 02-01 (tradingagents.portfolio.load_portfolio / PortfolioContext)
provides:
  - "scripts/daily_paper_run.py --portfolio <json> (optional, lokal)"
  - "Portfolio-Block im complete_report.md-Header"
affects:
  - scripts/daily_paper_run.py
  - tradingagents/reporting.py (Upstream-Datei, additiv)
tech-stack:
  added: []
  patterns:
    - "Optionales kwarg nur bei gesetztem Wert durchreichen (CI-Aufruf byte-gleich)"
    - "Validierungsfehler -> ConfigError -> EXIT_CONFIG vor Preflight-Zweig"
key-files:
  created: []
  modified:
    - scripts/daily_paper_run.py
    - tradingagents/reporting.py
    - tests/test_daily_paper_run.py
    - tests/test_reporting.py
decisions:
  - "propagate bekommt portfolio= nur wenn gesetzt; sonst wörtlich der alte Aufruf (Sentinel-Test belegt das)"
  - "summary.json bleibt unverändert (Phase-4-Konsumentenvertrag)"
  - "reporting.py: genau ein additiver Block (4 Zeilen hinzu, 0 entfernt)"
metrics:
  duration: ~10min
  completed: 2026-10-12
  tasks: 2
  files: 4
---

# Phase 02 Plan 03: --portfolio im Paper-Lauf und Portfolio-Block im Report Summary

`scripts/daily_paper_run.py --portfolio <json>` lädt den `PortfolioContext` per `load_portfolio()` im Konfig-`try`, gibt ihn an `graph.propagate(..., portfolio=...)` weiter, und `complete_report.md` zeigt den `render()`-Block im Header. Damit ist Erfolgskriterium 7 mechanisch erfüllt (Stub-Graph- und Report-Tests). Der echte Lauf mit LLM-Kosten folgt als Operator-Checkpoint in Plan 02-06.

## Tasks

| Task | Name | Commits |
|------|------|---------|
| 1 | `--portfolio` in `daily_paper_run.py` mit Durchreichen und Exit 1 | 49c4422 (RED), 1c160d2 (GREEN) |
| 2 | Portfolio-Block im Report-Header (additiv, Upstream-Datei) | b9ce501 (RED), 5122738 (GREEN) |

## Umsetzung

- **Task 1:** Neues Argument `--portfolio` (`type=Path, default=None`). In `main()` direkt nach `load_rates()` wird die Datei geladen; ein `ValueError` aus `load_portfolio()` wird zu `ConfigError`. Die vorhandene Fehlerbehandlung liefert dann `error: ...` und `EXIT_CONFIG`, und zwar vor dem Preflight-Zweig und vor dem Graph-Bau. Mit gesetztem Portfolio kommt nach der `paper-run:`-Zeile eine zusätzliche Zeile `portfolio: <pfad> (<n> position(s), cash <cash> <currency>)`. `run_ticker(..., portfolio=None)` ruft `graph.propagate(ticker, trade_date)` unverändert auf, wenn kein Portfolio übergeben wurde. `_FakeGraph.propagate` nimmt jetzt `**kwargs` an und zeichnet `portfolio` auf, bei fehlendem kwarg den Sentinel `"<absent>"`. `self.calls` ist unverändert.
- **Task 2:** `_header` hat nach dem `memory_note`-Block einen Kommentar und ein `if final_state.get("portfolio_context")` mit Leerzeile und Blocktext bekommen. `git diff --numstat`: 4 Zeilen hinzu, 0 entfernt.

## Verifikation

- `pytest tests/test_daily_paper_run.py -q`: 43 passed. Mit `-k portfolio` werden 5 Tests gesammelt.
- `pytest tests/test_reporting.py tests/test_report_html.py tests/test_portfolio_context.py -q`: 47 passed
- `ruff check .`: sauber
- `git diff --quiet -- .github/workflows/`: Exit 0
- `grep 'final_state.get("portfolio_context")' tradingagents/reporting.py`: genau 1 Treffer
- Gesamte Suite `.venv/Scripts/python.exe -m pytest -q`: **1 failed, 1454 passed, 4 skipped**, 1 deselected. Das ist der bekannte yfinance-Cache-Windows-Test `test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`. Gegenüber der Basis (1446 passed) sind 8 Tests dazugekommen: 5 Portfolio-Tests im Paper-Lauf, 1 Block-Test und 2 parametrisierte Ohne-Block-Tests im Report.

## TDD Gate Compliance

Beide Tasks haben RED vor GREEN: `test(02-03)` 49c4422 vor `feat(02-03)` 1c160d2, `test(02-03)` b9ce501 vor `feat(02-03)` 5122738. Im RED-Lauf von Task 1 war `test_without_portfolio_propagate_gets_no_portfolio_kwarg` schon grün. Das ist so gewollt: Der Test hält das bisherige Verhalten fest, also den Aufruf ohne kwarg. Die vier anderen neuen Tests schlugen wie erwartet fehl (`unrecognized arguments: --portfolio`). Ein REFACTOR-Schritt war nicht nötig.

## Deviations from Plan

None - plan executed exactly as written.

Am Rande: Beim ersten Einfügen der Report-Tests hat ein `\\n`-Escape im Python-Heredoc einen echten Zeilenumbruch im String-Literal erzeugt. Das wurde vor dem RED-Commit korrigiert, ohne Auswirkung auf den Code.

## Threat Flags

Keine. Die neue Angriffsfläche (lokale Portfolio-JSON) ist durch T-02-10/T-02-11 abgedeckt und so umgesetzt: Validierung vor dem Graph-Bau, CI-Aufruf unverändert, Workflows unberührt.

## Known Stubs

Keine.

## Self-Check: PASSED

- FOUND: scripts/daily_paper_run.py, tradingagents/reporting.py, tests/test_daily_paper_run.py, tests/test_reporting.py
- FOUND commits: 49c4422, 1c160d2, b9ce501, 5122738
