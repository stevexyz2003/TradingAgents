---
created: 2026-10-16T19:55:44.946Z
title: Mark or exclude Jev fallback ratings in IBKR preview
area: tooling
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
files:
  - tradingagents/jev/hooks.py
  - tradingagents/graph/trading_graph.py:398
  - tradingagents/memory/log.py:32
  - scripts/ibkr_executor.py:1100-1122
  - scripts/state_maintenance.py:167-174
  - tradingagents/backtest.py:192
  - scripts/daily_paper_run.py
---

## Problem

Der opt-in Jev-REVIEW-Fallback (Quick 261012-t8w, im Daily Paper Run aktiv seit 261012-uth) setzt `final_rating` auf Jevs Lesart, wenn die Engine `REVIEW` liefert und Jev ≥ 0.9 sicher ist. Das passiert **vor** `store_decision()` (`trading_graph.py:398`). Deshalb landet das Jev-Rating im `TradingMemoryLog`, also in `decision-log.md` auf `paper-log`, und ist dort **nicht** von einem Engine-Rating zu unterscheiden.

Die Kennzeichnung `final_rating_source="jev"` existiert nur in:
- `final_state["jev"]` bzw. `final_state["final_rating_source"]`
- der Sidecar-Datei `jev_review_<date>.json` neben dem State-Log
- dem Paper-Run-Datensatz `runs/<date>/summary.json` → `record.rating_source`

Phase 04 liest Entscheidungen für die whatIf-Vorschau aus `decision-log.md` (`ibkr_executor.py:1122`, `TradingMemoryLog(...).load_entries()`). Ein von Jev nachgetragenes Rating würde dort wie eine normale Engine-Entscheidung zur Soll-Rechnung und Order-Vorschau führen. Dasselbe gilt für Backtest-Scoring (`backtest.py:192`) und das Settlement.

Gefunden per Graphify-Analyse des Brückenknotens `TradingMemoryLog` (2026-10-16). Das Log-Format ist eine Schnittstelle für Engine, Settlement, Backtest, `state_maintenance` (nutzt sogar das private `_SEPARATOR`) und den IBKR-Executor.

## Solution

Offen, Entscheidung in Phase 04 treffen:

- **(a) Quelle ins Log-Tag schreiben**, z. B. `[date | ticker | rating | pending | src=jev]`. Saubere Single Source of Truth, aber das Format ist eine Schnittstelle: alle Parser und Prüfungen anpassen und testen (`log.py` Parser/Tag-Bau, `settlement`, `backtest`, `state_maintenance.verify` Blockzählung, `ibkr_executor`, Fixture `tests/fixtures/paper_log_71df89d`). Rebase-Kosten gegen Upstream beachten (`log.py` ist eine Upstream-Datei).
- **(b) Executor gleicht mit `summary.json` ab**: Für jeden Eintrag `record.rating_source` aus `runs/<date>/summary.json` lesen; bei `jev` ausschließen (fail-closed, wie REVIEW) oder in der Vorschau sichtbar markieren. Kein Formatwechsel, aber zweite Quelle mit eigener Konsistenzprüfung (fehlt summary → wie behandeln?).
- **(c) Bewusst akzeptieren und dokumentieren**: Jev-Ratings sind nur bei Konfidenz ≥ 0.9 gesetzt; im Handbuch `scripts/IBKR_EXECUTION.md` festhalten.

Empfehlung zum Prüfen: (b) mit fail-closed-Ausschluss passt zum Sicherungsprinzip „positiver Nachweis“ (261012-ap2) und vermeidet einen Formatwechsel in einer Upstream-Datei.
