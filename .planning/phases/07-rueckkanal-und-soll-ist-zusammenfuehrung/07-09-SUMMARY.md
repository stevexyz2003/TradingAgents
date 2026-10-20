---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 09
subsystem: operator-acceptance
tags: [publish, ibkr-log, ci, portfolio-feed, report, acceptance]
requires: [07-08]
key-files:
  created: []
  modified: []
requirements: [REQ-IBKR-49, REQ-IBKR-50, REQ-IBKR-52]
completed: 2026-10-20
---

# Phase 7 Plan 09: Operator-Abnahme gegen die echte Welt Summary

Erster echter `publish` auf `fork/ibkr-log`, Code-Push auf `fork/main`, ein CI-Lauf mit übernommenem Portfolio (`portfolio_feed.status == used`) und der Bericht gegen die echten Branches — alles gegen den Remote nachgeprüft und vom Operator abgenommen („approved“, 2026-10-20).

## Task 1: Vorprüfung (nur lesend)

| Prüfung | Ergebnis |
|---|---|
| `git merge-base --is-ancestor 448ffa9 HEAD` / `28ef33a` | Exit 0 / Exit 0 |
| Live-Ledger `%LOCALAPPDATA%\TradingEngineX\ibkr\ledger.jsonl` | 12 Zeilen, `intent` mit `2026-10-16\|AAPL` |
| `git ls-remote --exit-code --heads fork ibkr-log` | Exit 2 (Branch fehlte) |
| `fork/paper-log`-Tip vorher | `c4cad1a` (github-actions[bot], 2026-10-20 07:03 UTC) |
| `fork` ≠ `origin` | ja |
| `fork/main..main` | 52 Commits voraus, 0 zurück (Fast-Forward) |
| Volle Suite | 3034 passed, 5 failed (alle aus der bekannten Fremdliste: `test_chatgpt_auth` ×2, `test_cli_updates` ×2, `test_yfinance_keeps_its_cache_out_of_the_users_home`), 4 skipped |
| `ruff check scripts tests` | sauber |

## Task 2: publish, Push, Dispatch

Eine erste Rückmeldung „published“ ließ sich am Remote nicht belegen (kein `ibkr-log`, kein Push, kein Dispatch, keine `publish:`-Logzeile). Der Operator hat daraufhin Claude ausdrücklich beauftragt („publish, push fork main und Dispatch AAPL ausführen“). Ausgeführt:

1. `ibkr_executor.py account --out …\portfolio.json` → Exit 0, `1 position(s), cash 1005152.72 EUR`, `as_of 2026-10-20T10:53:14Z` (vorher 2026-10-12, wäre im CI `stale` gewesen)
2. `ibkr_executor.py publish` → Exit 0, `publish: published c141694523a4 to fork/ibkr-log (first publish)`
3. `git push fork main` → `23b4a4b..036dd7b` (ohne Force)
4. `gh workflow run daily-paper-run.yml -f tickers=AAPL` → Run 39411116928, `completed success`, Kosten $0.23

## Task 3: Nachprüfung

| Kriterium | Befund |
|---|---|
| SC1 `ibkr-log` | `ls-remote` Exit 0; `c141694` von `TradingEngineX publish <publish@tradingenginex.invalid>`; Baum genau `.gitattributes`, `contracts.json`, `ledger.jsonl`, `portfolio.json`; `ledger.jsonl` per `cmp` byte-gleich mit dem lokalen Live-Ledger |
| SC1 `paper-log` | `c4cad1a..fork/paper-log` = nur `041288a` von `github-actions[bot]` |
| SC6 `portfolio_feed` | `runs/2026-10-19/summary.json`: `{"status": "used", "as_of": "2026-10-20T10:53:14.858280+00:00", "cutoff": "2026-10-16T20:00:00+00:00", "sha": "c141694…", "positions": 1}`; Job-Log: `portfolio-feed: used (as_of …, 1 position(s))`; 0 Treffer für „IBKR“ |
| SC2/SC3 Bericht | `ibkr_report.py` Exit 0 gegen `paper-log` und `paper-log-pipeline-test`; beide Tabellen, Paper-Fill-Hinweis oben; `2026-10-16 \| AAPL`: `filled [1][2]`, BUY 1, gefüllt 1 zu 342.86, Fill-Quote 1.00, −17.5 bp; Fußnoten „ledger rating Overweight != log rating Hold (paper-log 8453e76)“ und „alarm: post-order-mismatch“; `git status --porcelain` unverändert |
| SC5 | genau eine Zeile `2026-10-09 \| AAPL` in `## Execution`; `fork/paper-log:index.md` führt den Tag 5× |

Berichtsauszug (Kopf):

```
- Decision log fork/paper-log: @ c4cad1a6416d
- Ledger fork/ibkr-log: @ c141694523a4
- Period: start .. end
- Fill ratio (sum filled / sum ordered): 1.00
| 2026-10-16 | AAPL | Overweight | filled [1][2] | 1 | 0 -> 1 | BUY 1 | 1 | 342.86 | 0 | true | 1.00 | -17.5 |
```

## Task 4: Sichtprüfung

Operator: „approved“.

## Beobachtungen (nicht blockierend)

1. **Dispatch überschreibt den Tagesordner.** Der Dispatch lief mit `trade_date 2026-10-19` (wie der planmäßige Lauf am Morgen) und hat `runs/2026-10-19/summary.json` auf nur AAPL reduziert (vorher 3 Ticker) sowie `AAPL.md` ersetzt; `index.md` hat eine doppelte Zeile (vom Bericht per D-12 verworfen). Verhalten bestand schon vor Phase 7.
2. Ohne `--since/--until` druckt der Bericht `Period: start .. end` (kosmetisch).
3. Fußnote 1 nennt den Log-Stand, aus dem die Order entstand (`8453e76`, Pipeline-Test-Branch), auch im Bericht gegen `paper-log` — inhaltlich korrekt, kann verwirren.

## Deviations from Plan

- Task 2 wurde auf ausdrücklichen Operator-Auftrag von Claude statt vom Operator ausgeführt; `account` (nur lesend) wurde vorgeschaltet, weil das Portfolio sonst vom 2026-10-12 gewesen wäre.

## Self-Check: PASSED
