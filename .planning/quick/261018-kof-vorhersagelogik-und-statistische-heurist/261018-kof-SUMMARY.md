---
phase: quick-261018-kof
plan: 01
status: complete
subsystem: patterns
tags: [patterns, evaluation, wilson, paper-log, codex-review]
requirements: [QUICK-261018-kof]
key-files:
  created:
    - tradingagents/patterns/__init__.py
    - tradingagents/patterns/signals.py
    - tradingagents/patterns/evaluate.py
    - scripts/pattern_eval.py
    - tests/test_patterns_signals.py
    - tests/test_patterns_evaluate.py
    - tests/test_pattern_eval_cli.py
  modified:
    - tradingagents/backtest.py
    - tests/test_backtest.py
commits:
  - 362c611 feat(patterns): add look-ahead-free pattern signals and small-N evaluation (fork-only)
  - e1a2bc0 feat(patterns): add pattern_eval CLI for decision-log evaluation (fork-only)
  - c757adf fix(patterns): apply codex review findings
  - 33767b3 fix(backtest): do not count settled entries with unreadable alpha as pending (Upstream-Kandidat)
completed: 2026-10-18
---

# Quick 261018-kof: Muster-Auswertung und Codex-Validierung (Summary)

**Status: complete.** Alle drei Tasks sind erledigt. Die Codex-Validierung lief nach dem CLI-Update (0.137.0 auf 0.163.0) mit dem Modell `gpt-6.1-sol` (nicht `gpt-5.5`, das das Konto nicht mehr anbietet), Reasoning Effort high, gegen e1a2bc0. Details und Disposition aller 25 Befunde in `261018-kof-CODEX-REVIEW.md`.

## Ergebnis

- Fork-only Modul `tradingagents/patterns/`: sechs Muster, die selbst auf `Date <= as_of` abschneiden (Test belegt Look-ahead-Freiheit). Auswertung je Muster, Seite und Modus (`engine` / `pattern`) mit `n_all`, `n_independent`, Ties getrennt je Metrik, Wilson-95-%, alpha- und raw-basierten Trefferquoten und **Status je Metrik** (`MIN_N = 20` am tatsaechlichen Nenner).
- CLI `scripts/pattern_eval.py` (`--log` / `--git-ref`, md/json, Exit 0/1/3).
- Echter Lauf auf `fork/paper-log` (5541cd9) mit echten Yahoo-Kursen, vor und nach den Fixes: **zu wenig Daten**, alle 24 Zellen `insufficient`; 1 von 16 Eintraegen abgerechnet (Hold). 2026-10-09 AAPL als alte Konvention markiert. Siehe `261018-kof-EVALUATION.md`.

## Codex-Fixes (c757adf, Strangmodul)

#11 MIN_N je Metrik am Nenner; #12 Alpha und Raw unabhaengig; #13 Unabhaengigkeit und Konvention aus echten Handelssitzungen (Wochentags-Fallback als `approximate` markiert); #14 Duplikate und tz-aware `as_of`; #15 Wilder-RSI-Startwert; #16 MACD-Kreuz ueber exakte Null; #21 Markdown mit Nennern und Bezugsgruppen, `mean_alpha` als ungerichtet dokumentiert; #18 Docstring Close-Donchian; #7 Warnung abgeschwaecht. Jeweils mit Regressionstest (Signal-Fixes zuerst als RED bestaetigt).

## Upstream

- **Gepatcht (33767b3, Upstream-Kandidat):** `backtest.py` zaehlte settled-unlesbare Eintraege als pending (#5). Kleinster Patch (5 Zeilen) plus Test; sie werden jetzt als `unscored` gemeldet.
- **Nicht gepatcht, Upstream-Kandidat:** #17, `settlement` prueft nicht, ob der Ausstiegsbar final ist (vorlaeufiger Tagesclose von Yahoo kann ein Fenster vortaeuschen); konkrete Beschreibung und Vorschlag im CODEX-REVIEW.
- **Fragen an den Operator:** #1 Rundung/Tie als Fehltreffer, #2 Beschriftung "called the direction", #3/#4 Konvention, Benchmark und Fenster nicht im Log-Tag, Config-Drift beim Settlement.
- Keine Aenderung an `rating.py`, `settlement.py`, `log.py`, `ohlcv.py`, `market.py`, keine IBKR-Dateien beruehrt.

## Tests

- Neue/erweiterte Tests: Signale 11, Auswertung 22, CLI 10 (zusammen 43 passed), dazu 1 neuer Test in `tests/test_backtest.py` (`test_backtest.py` + `test_memory_log.py`: 128 passed).
- Volle Suite auf 33767b3: **2662 passed, 4 skipped, 1 deselected, 5 failed**. Die 5 Fehler sind die bekannten Windows-Umgebungsfehler (`test_chatgpt_auth` x2, `test_cli_updates` x2, `test_suite_isolation::test_yfinance_keeps_its_cache_out_of_the_users_home`), keine Regression.
- `ruff check .` (repo-weit): All checks passed.

## Abweichungen vom Plan

1. **[Plan-Fehler] Konventionstest:** Das Plan-Beispiel "2026-10-12 -> 2026-10-19 ist next_close" widerspricht der Formel (Montag bis Montag = 5 Handelstage = `decision_close`). Getestet wurden 2026-10-09 -> 2026-10-19 und 2026-10-12 -> 2026-10-20.
2. Trefferquoten und Intervalle laufen auf der unabhaengigen Teilmenge; `n_all`, Ties und `mean_alpha` ueber alle Faelle der Zelle (jetzt in Markdown-Legende und Docstring dokumentiert).
3. Das Zellfeld `status` wurde durch `status_alpha` / `status_raw` ersetzt (Codex #11); JSON-Konsumenten muessten umstellen, es gibt noch keine.
4. Koordinator-Auftrag nach dem ersten Abschluss: Fixes A bis D umgesetzt; #17 wie angewiesen nicht gepatcht.

## Hinweise

- Alle drei Ticker stehen im ganzen Zeitraum ueber SMA200 und im Golden-Cross-Regime; beide Trend-Muster sind in dieser Stichprobe konstant +1.
- Parallele Session: Es wurden nur eigene Dateien gestaged (`git commit -- <pfade>`), kein stash/reset/add -A.

## Uncommittete Docs-Artefakte fuer den Orchestrator

- `.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md`
- `.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md`
- `.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-SUMMARY.md`

## Self-Check: PASSED

Commits c757adf und 33767b3 im Log, 43 + 128 Tests gruen, Ruff sauber, Docs ungestaged.
