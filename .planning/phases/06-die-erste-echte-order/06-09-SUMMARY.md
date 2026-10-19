---
phase: 06-die-erste-echte-order
plan: 09
subsystem: ibkr-execution
tags: [operator-checkpoint, read-only, measurement]
requires: [06-07, 06-08]
provides: [read-only proof on the live path, ticker for 06-10]
affects: [06-10]
key-files:
  created: []
  modified:
    - .planning/ibkr-konto-befund.md
decisions:
  - "D-03 relaxed by the operator on 2026-10-19: first order is a pipeline test (AAPL Overweight = 1 share) from branch fork/paper-log-pipeline-test, not an engine decision"
metrics:
  completed: 2026-10-19
---

# Phase 6 Plan 09: Read-Only-Beleg im scharfen Pfad — Summary

Am Messtag 2026-10-19 ist der gesperrte Zustand im `--live`-Pfad belegt: Die Sonde hat 321 gemessen und die maschinelle Prüfung bestanden, danach endete `execute AAPL --live` mit 321 im Log fail-closed, ohne `intent`. Als Ticker für 06-10 steht AAPL fest, BUY 1, als Pipeline-Test nach gelockertem D-03.

## Ablauf

1. Vorprüfungen: `ruff check .` sauber, die IBKR-Kernsuiten mit 48 Tests grün. Volle Suite: 2883 passed, 6 failed. Neben dem bekannten Fehler `test_yfinance_…` schlagen fünf Tests ohne IBKR-Bezug fehl: `test_chatgpt_auth` ×2 (prüft `0o600` unter Windows), `test_cli_commands` ×1, `test_cli_updates` ×2. Im State-Ordner lag weder `KILL` noch `RELEASE`.
2. Erster Anlauf, 14:29–14:30 UTC: Sonde `READ_ONLY_API`/321, Prüfung Exit 0. `preview` zeigte AAPL, MSFT und NVDA als Hold, also kein BUY. Nach D-03 verschoben, kein `RELEASE` (Commit 035af86).
3. Der Operator wollte nicht bis zum nächsten Tag warten. Zwei Paper-Runs per `workflow_dispatch` (17 weitere Ticker, zusammen $3.75) brachten wieder kein BUY: 20 von 20 Entscheidungen ohne BUY.
4. Der Operator lockerte D-03. Branch `fork/paper-log-pipeline-test` (`8453e76`) mit einem markierten Eintrag `[2026-10-16 | AAPL | Overweight | pending]`. Der Executor bleibt unverändert; den Branch bekommt er über eine `--env-file` mit nur den IBKR-Keys.
5. Zweiter Anlauf, 15:28–15:30 UTC: Sonde 321, Prüfung Exit 0. `preview` meldete `preview-read-only` BUY 1, Exit 5. `RELEASE` wurde angelegt, dann lief `execute AAPL --live`: **Exit 3** `REQUEST_TIMEOUT` nach 321 bei `reqCompletedOrders`. Kein `intent`, kein `placed`, kein `ORDER_SENT`. Danach `RELEASE` entfernt (Commit e1313c6).
6. Der Operator meldet „Read-Only“ an um 17:28 und aus um 17:36 MESZ. Mit dem Schalter aus antwortet `--history` wieder (alles leer).

## Deviations from Plan

- **D-03 gelockert (Operator-Entscheidung):** Die erste Order ist ein markierter Pipeline-Test, keine Entscheidung der Engine. Begründung und Belege stehen im Befund.
- **Messung 1 weicht von D-15 ab:** Im Read-Only-Modus scheitert der Lauf schon beim Lesen der Historie (Exit 3, `REQUEST_TIMEOUT`), nicht erst am whatIf (Exit 5, `preview-read-only`). Das ist fail-closed und belegt den Zustand.
- **Ablauf-Fehler des Agenten:** Im ersten Anlauf lief `preview` in derselben Befehlskette wie eine fehlgeschlagene Prüfung. Die Prüfung scheiterte nur am BOM in der Datei und war beim erneuten Lauf Exit 0. Der `preview` sendet nichts und war deshalb unkritisch.

## Lücken für die Verifikation

- Eine 321 mit `reqId -1` während eines Lesefensters wird als Timeout (Exit 3) gemeldet statt als `READ_ONLY_API` (Exit 5).
- Das Handbuch nennt diesen Effekt bei `--history` und `execute --live` nicht.
- Ein zweiter Paper-Run auf dasselbe `trade_date` überschreibt `runs/<date>/summary.json` und verliert die Ticker der früheren Läufe (fail-closed `summary-missing`).
- Das Ledger trägt beim Pipeline-Test `rating_source: engine`; die Herkunft belegen nur `preview.json` und der Befund.

## Self-Check: PASSED

- Befund-Abschnitt „Erste echte Order (Phase 6)“ mit „Read-Only-Beleg vor RELEASE“ und „Messung 1: 321 im scharfen Pfad“ vorhanden.
- `ledger.jsonl` ohne `intent`/`placed`, Log ohne `ORDER_SENT`, State-Ordner ohne `RELEASE`/`KILL`.
