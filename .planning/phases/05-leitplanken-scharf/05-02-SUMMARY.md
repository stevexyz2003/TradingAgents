---
phase: 05-leitplanken-scharf
plan: 02
subsystem: ibkr-execution
tags: [ledger, jsonl, reconciliation, write-ahead, tdd]
requires: []
provides:
  - scripts/ibkr_ledger.py (Ledger, LedgerError, StateInGitTree, REASON_BY_STATE, REJECTED_STATES, intent_record, resolve_entry, ensure_outside_git)
affects: [05-04, 05-05, 05-06, 05-07]
tech-stack:
  added: []
  patterns: [append-only JSONL mit fsync je Zeile, Duck-Typing für Broker-Historie]
key-files:
  created: [scripts/ibkr_ledger.py, tests/test_ibkr_ledger.py]
  modified: []
key-decisions:
  - "Zustand je decision_key nur aus LIFECYCLE_EVENTS; reconcile/skipped/switch_check schließen nie einen offenen intent"
  - "Abgerissene letzte Zeile wird toleriert und beim nächsten Append mit Zeilenumbruch abgeschlossen"
metrics:
  tasks: 2
  files: 2
  completed: 2026-10-17
---

# Phase 5 Plan 02: Ledger und Reconciliation-Klassifikation Summary

Append-only JSONL-Ledger (`scripts/ibkr_ledger.py`) mit fsync je Zeile, Modus-Trennung dryrun/live, Zustand je `decision_key`, Grund-Tabelle und reiner Reconciliation `resolve_entry` über offene Orders, erledigte Orders und Executions.

## Ergebnis

- 50 Tests in `tests/test_ibkr_ledger.py` grün (`pytest tests/test_ibkr_ledger.py -q`: 50 passed); `ruff check` und `ruff format` auf beiden Dateien sauber.
- Akzeptanz-Greps: verbotene Zeichenketten (datetime.now, ib_async, tradingagents, ibkr_market_data usw.) = 0; `"w"`/`truncate(` = 0; Adapter-Importe = 0.
- Commits: RED `e4686b3` (test), GREEN `9735ccf` (feat).

## Deviations from Plan

**1. [Hinweis] Task 1 und 2 in einem RED- und einem GREEN-Commit**
Beide Tasks ändern dieselben zwei Dateien; Tests und Implementierung wurden je in einem Commit abgelegt statt je Task getrennt. Inhaltlich vollständig.

**2. [Hinweis] Plan-Widerspruch zur abgerissenen Zeile**
Der Plan verlangt, dass eine ungültige Restzeile beim nächsten Append mit `\n` abgeschlossen wird *und* dass eine defekte Zeile in der Mitte `LedgerError` ist. Beides zusammen heißt: nach Torn-Tail + Append wirft das nächste `Ledger.open` `LedgerError` (die abgeschlossene Restzeile liegt dann in der Mitte). Umgesetzt wie spezifiziert (fail-closed, Test `test_ledger_torn_tail_invalid_fragment_is_tolerated` belegt es). Ein gültiges JSON ohne `\n` ist dagegen unproblematisch. Folge für 05-04..07: nach einem echten Absturz mitten im Schreiben braucht der Operator eine Bereinigung der Restzeile, bevor der nächste Lauf startet (Exit 6); falls das nicht gewollt ist, wäre eine Entscheidung nötig (z. B. Restzeile als eigener Marker tolerieren).

**3. [Hinweis] Guards-Test bedingt**
Der Zustandsabdeckungs-Test prüft `ibkr_guards.EXIT_BY_STATE` nur, wenn `scripts/ibkr_guards.py` existiert (Plan 05-01 läuft parallel). Die Guards-Zustände (`size-cap`, `kill-*`, `release-*` usw.) sind zusätzlich als feste Liste geprüft.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche über den Threat-Register des Plans hinaus.

## Self-Check: PASSED

- scripts/ibkr_ledger.py, tests/test_ibkr_ledger.py vorhanden; Commits e4686b3 und 9735ccf vorhanden.
