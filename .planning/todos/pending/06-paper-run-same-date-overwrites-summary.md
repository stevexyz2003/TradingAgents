---
title: A second paper run for the same trade date overwrites summary.json
created: 2026-10-20
area: tooling
source: .planning/phases/06-die-erste-echte-order/06-VERIFICATION.md (gap 3)
files:
  - scripts/daily_paper_run.py (summary writer)
  - .github/workflows/daily-paper-run.yml
---

## Problem

Am 2026-10-19 liefen per `workflow_dispatch` zwei zusätzliche Paper-Runs für
`trade_date` 2026-10-16 (Runs 39270361112 und 39273689753). Jeder Lauf schreibt
`runs/2026-10-16/summary.json` neu. Danach fehlen dort die Ticker der früheren Läufe
(AAPL/MSFT/NVDA vom 17.10., dann die sieben aus Run 1). `decision-log.md` wird
dagegen nur ergänzt.

Der Executor findet für diese Ticker keine Summary-Zeile mehr und bricht
fail-closed mit `summary-missing` ab. Das ist sicher, aber eine echte BUY-Entscheidung
eines früheren Laufs wäre damit nicht mehr handelbar.

## Lösung

- `daily_paper_run.py`: Eine vorhandene `summary.json` desselben `trade_date`
  zusammenführen statt überschreiben. Die Zeilen in `runs` werden nach Ticker
  vereinigt, der neuere Lauf gewinnt je Ticker, `totals` werden neu berechnet.
  `started_at`/`finished_at` werden je Lauf in einer Liste festgehalten.
- Test: zwei Läufe mit disjunkten Tickern ergeben eine Summary mit allen Tickern;
  ein Ticker, der in beiden vorkommt, trägt den Wert des neueren Laufs.
