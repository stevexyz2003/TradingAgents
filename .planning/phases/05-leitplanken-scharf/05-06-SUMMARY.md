---
phase: 05-leitplanken-scharf
plan: 06
subsystem: ibkr-executor
tags: [ibkr, execute, size-cap, session-window, decision-key, tdd]
requires: [05-01, 05-02, 05-05]
provides:
  - "Groessengrenze (check_size) in _execute_ticker: size-cap, Exit 5, nie kuerzen"
  - "Sitzungsfenster als Ablehnung outside-session (Exit 2) vor dem whatIf"
  - "_check_attempts: already-attempted / decision-changed vor der Gateway-Kette"
affects: [05-07]
key-files:
  modified: [scripts/ibkr_executor.py, tests/test_ibkr_execute.py]
key-decisions:
  - "Keine eigene Zeitlogik: CLOSED aus evaluate_session (mit SESSION_BUFFER_MINUTES) wird zu outside-session"
  - "Schluesselpruefung nach der lokalen Kette (trade_date ist erst dann bekannt)"
requirements-completed: [REQ-IBKR-25, REQ-IBKR-32, REQ-IBKR-40, REQ-IBKR-42, REQ-IBKR-66]
completed: 2026-10-17
---

# Phase 5 Plan 06: Groesse, Sitzungsfenster, ein Versuch je Schluessel Summary

Reihenfolge im Ticker jetzt Zielrechnung, Groesse, Handelszeit, Schalter, whatIf, Schalter, `intent`; je `decision_key` gibt es hoechstens einen `intent`, die erste Fassung gewinnt.

## Ergebnis

- **Groesse (SC4, REQ-32):** `guards.check_size(plan.quantity)` direkt nach `plan_order`. Zu gross: Ledger `skipped` (`size_cap`), Exit 5, WARNING `ibkr-state=SIZE_CAP`, kein whatIf, kein `intent`, nie gekuerzt. `DryPlacer` behaelt die Zweitpruefung.
- **Sitzung (REQ-25):** `row["session"]["closed"]` (aus `result.state == CLOSED`) wird zu `outside-session` (`outside_session`, Exit 2) vor dem whatIf. Halbtage verkuerzen das Fenster ueber `liquidHours`. `session-unknown` bleibt `not_tradable`. `preview` unveraendert.
- **Schluessel (REQ-40, SC8):** `_check_attempts` (nach `_local_chain`, vor `_execute_gateway_chain`) nutzt `Ledger.attempt_of`. Gleiche Fassung: `already-attempted` (Detail mit `run_id`/`ts`); anderes Rating: `decision-changed` mit `rating`, `first_rating`, `paper_log_sha`, `first_paper_log_sha` im Ledger. Ohne Restticker keine Broker-Sitzung. Ein fruehes `skipped` verbraucht den Schluessel nicht.

## Commits

- 715ff8a test(05-06): size cap and session window (RED)
- 93e45ea feat(05-06): size cap and session window in the execute chain
- f5f017a test(05-06): one attempt per decision_key (RED)
- a339a3f feat(05-06): one attempt per decision_key, first version wins

## Verifikation (tatsaechliche Ausgabe)

- IBKR-Volllauf (broker, contracts, executor, isolation, resolve, preview, decision, paperlog, guards, ledger, execute): `900 passed`.
- `ruff check scripts tests`: All checks passed. `ruff format` nur auf `tests/test_ibkr_execute.py`.
- `pytest -k g3`: 8 passed (Kill-, Groessen- und Sitzungstests).
- Greps: `attempt_of(` = 1, `DECISION_CHANGED` = 2, `SESSION_BUFFER_MINUTES *=` = 0.

## Deviations from Plan

**1. [Hinweis] Worktree-Basis** laut Startpruefung auf 4ab60c4 zurueckgesetzt (Branch `worktree-agent-*`, nichts verloren).

**2. [Testanpassung]** Der Fall "nach Handelsschluss" (16:10 ET) wurde aus der Sitzungs-Parametrisierung gestrichen: dort greift schon die Frische-Pruefung (`stale-decision`, naechste Sitzung), nicht das Sitzungsfenster. Die Negativ-Kontrolle "nur Ketten-Check umgangen" prueft Exit != 0 und zwei `check_size`-Aufrufe, weil `_guarded` den `ValueError` des Placers in einen Exit-Code umsetzt.

**3. [Hinweis] REQ-45-Abweichung** (Schluesselpruefung nach der Frische) ist im Code kommentiert, fuer den Phase-6-Reihenfolgetest.

## Known Stubs

Keine.

## Threat Flags

Keine neue Flaeche ueber T-05-33..37 hinaus.

## Self-Check: PASSED

- scripts/ibkr_executor.py, tests/test_ibkr_execute.py vorhanden; Commits 715ff8a, 93e45ea, f5f017a und a339a3f im Log.
