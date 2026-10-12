---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 09
subsystem: ibkr-handbuch-und-waechter
tags: [preview, handbuch, waechter, D-14, SC1, REQ-68]
requires: [04-07, 04-08]
provides:
  - "Handbuch: ## preview, Zustandstabelle Phase 4, Exit 5 aktiv, D-14-Ergebnis"
  - "Statische Waechter fuer ibkr_decision.py / ibkr_paperlog.py und Marktdaten-Ausschluss (REQ-68)"
  - "Operator-Abnahme des realen preview AAPL und des Schalterzustands"
affects: [04-VERIFICATION]
key-files:
  modified:
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_isolation.py
decisions:
  - "Read-Only-API-Schalter bleibt waehrend Phase 4 aus (D-14, Variante a); Schutz allein durch die Socket-Sperre"
metrics:
  completed: 2026-10-12
  tasks: 2
requirements: [REQ-IBKR-68, REQ-IBKR-38, REQ-IBKR-21, REQ-IBKR-15, REQ-IBKR-13]
---

# Phase 4 Plan 09: Handbuch, Waechter und Operator-Abnahme Summary

Handbuch um `preview`, die Phase-4-Zustandstabelle, aktives Exit 5 und das D-14-Ergebnis erweitert, sechs neue statische Waechter eingefuehrt und den realen Trockenlauf `preview AAPL` gegen `fork/paper-log` vom Operator abnehmen lassen.

## Commits

- c620799 `test(04-09)`: RED, neue Waechter gegen das alte Handbuch
- bc5e301 `docs(04-09)`: GREEN, Handbuch (preview, Zustandstabelle, Exit 5 aktiv, D-14)
- a381f72 `docs(04-09)`: Schalterzeile (aus, 2026-10-12, nach D-14 Messung 2) in der Read-Only-Tabelle

## Task 1: Handbuch und Waechter

Neue Waechter: `test_handbook_exit_five_is_active`, `test_handbook_documents_preview`, `test_handbook_state_table_matches_decision_module`, `test_decision_modules_are_library_free`, `test_decision_module_takes_the_clock_as_a_parameter`, `test_no_market_data_in_execution_path`. Handbuch nennt die Client-Bibliothek nicht.

## Task 2: Operator-Abnahme (Checkpoint)

Operator antwortete "approved"; der Schalter "Read-Only API" ist aus (nach Messung 2 aus 04-08 wieder ausgeschaltet, wie D-14 Ergebnis (a) verlangt).

Realer Lauf `preview AAPL`:

- Konsole: `preview: AAPL skipped-hold (trade_date 2026-10-09)`, Exit **2** (D-16)
- Log: `ibkr-state=PREVIEW ticker=AAPL state=skipped-hold sha=7b4af23df6e823dff723f74f8925e807176160e0 detail='skipped: hold'`
- Kein orderStatus, kein Traceback; Gateway im Hold-Pfad nicht kontaktiert
- `preview.json`: `paper_log` = fork/paper-log, sha 7b4af23..., `sent` false, `run_state` null, intent/preview/budget/position/session/freshness null

Gesamtsuite: 2036 passed, 4 skipped, 1 bekannter Umgebungsfehler (yfinance-Cache unter dem Windows-Home, rot seit Basis 3fe0462); `ruff check .` sauber.

## Deviations from Plan

None am Plan selbst. Hinweis: Beim abschliessenden Lauf von `tests/test_ibkr_isolation.py` (22 passed, 2 failed) schlagen `test_adapter_has_at_most_ten_public_methods` und `test_no_market_data_in_execution_path` an. Ursache ist die nicht eingecheckte Operator-Aenderung an `scripts/ibkr_broker.py` (neuer Market-Data-Stream: `MarketTick`, `reqMktData`), nicht diese Plan-Arbeit; die Datei wurde nicht angefasst und nicht committet. Die Waechter schlagen damit erwartungsgemaess an, sobald Marktdaten in den Adapter kommen (REQ-68). Beim Einchecken dieser Aenderung muss der Operator entscheiden, ob REQ-68 bzw. die Waechter angepasst werden.

## Offen fuer 04-VERIFICATION

- SC2-Anpassung (D-14, 321 blockt whatIf) vom Operator zu bestaetigen
- Fehler-154-Luecke (A5) nicht messbar, nur ueber Codeliste und Fake-Test belegt

## Self-Check: PASSED

Commits c620799, bc5e301, a381f72 vorhanden; Handbuch enthaelt die neue Schalterzeile; nichts gepusht, STATE.md und ROADMAP.md unveraendert.
