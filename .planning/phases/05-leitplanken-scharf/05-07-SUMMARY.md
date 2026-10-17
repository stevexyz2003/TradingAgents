---
phase: 05-leitplanken-scharf
plan: 07
subsystem: ibkr-executor
tags: [ibkr, execute, reconciliation, write-ahead, source-conflict, account-guard, tdd]
requires: [05-01, 05-02, 05-03, 05-05, 05-06]
provides:
  - "_history(ctx), _reconcile(ctx), _fill_quantity: Startup-Reconciliation vor dem paper-log, Exit 6"
  - "Quellenvergleiche in _execute_ticker: Position, schon ausgefuehrt (je Ticker), Konto (ganzer Lauf, Exit 8)"
affects: [05-08, 05-09, 05-10]
key-files:
  modified: [scripts/ibkr_executor.py, tests/test_ibkr_execute.py]
key-decisions:
  - "Reconciliation steht in _run_locked nach der Schalterentscheidung und vor paper_log_factory/fetch: ein aktiver Kill gewinnt vor Exit 6 (D-21)"
  - "Offener Eintrag mit Befund 'open': placed nur, wenn der letzte Lebenszyklus-Eintrag noch intent ist (keine Wiederholung je Lauf)"
  - "Der Kontovergleich nutzt den frisch gelesenen Schalterstand vor dem whatIf (release.account), nicht den Preflight-Stand"
requirements-completed: [REQ-IBKR-43, REQ-IBKR-63, REQ-IBKR-42, REQ-IBKR-66]
completed: 2026-10-17
---

# Phase 5 Plan 07: Reconciliation und Zwei-Quellen-Pruefungen Summary

Offene Ledger-Eintraege werden vor jeder neuen Order ueber offene Orders, erledigte Orders und Executions aufgeloest (Unaufloesbares: Exit 6); Konto-, Positions- und "schon ausgefuehrt"-Widersprueche stoppen nach D-11 den Lauf bzw. nur den Ticker.

## Ergebnis

- **Reconciliation (SC6, REQ-43):** `_reconcile` laeuft nach Preflight/Kill und vor `paper_log_factory`/`fetch`. Ohne offenen Eintrag kein Gateway-Kontakt. Je Eintrag ein `reconcile`-Ereignis (`outcome`, `open`, `completed`, `executions`, `detail`); aufgeloeste Faelle schreiben `placed` / `filled` / `partial` (mit `filled_qty`, `con_id`) / `rejected` (`state:"not-filled"`), alle mit `source:"reconcile"`. `no_trace`, `collision`, `contradiction` -> WARNING `ibkr-state=RECONCILE_UNRESOLVED key=... outcome=... open=0 completed=0 executions=0`, Konsole mit Verweis auf "IBKR_EXECUTION.md, Ledger and reconciliation", `_ExecuteStop(EXIT_RECONCILE)`; `run_end` `exit:6`, `state:"reconcile-unresolved"`. Ein `reconcile`-Ereignis schliesst den Eintrag nicht: Folgelaeufe stoppen erneut.
- **Konto (D-11, REQ-63):** nach dem whatIf `account_conflict(EXPECTED_ACCOUNT, release.account, echo_account)`; Widerspruch -> `ibkr-state=ACCOUNT_CONFLICT` mit beiden Konten, Exit 8, `run_end` `state:"account-conflict"`, kein `intent`, kein weiterer Ticker. Fehlendes/leeres Echo ist kein Widerspruch (D-22).
- **Position (D-18) und "schon ausgefuehrt?":** direkt nach `_position_and_orders`; `skipped`/`source_conflict` fuer diesen Ticker (Detail `position: ledger has 2 filled, broker holds 1` bzw. `executed: ...`), vor dem whatIf; die uebrigen Ticker laufen weiter. Die Historie wird einmal je Lauf gelesen (`_history`).
- **Handelbarkeit:** der bestehende Kalenderabgleich (`calendar-conflict`, Grund `source_conflict`) ist die Zwei-Quellen-Pruefung; Kommentar zu Status 399 (Phase 6) ergaenzt.
- **G3:** `pytest -k g3` = 14 passed (Kill, Groesse, Sitzung, Reconciliation: alle vier Nachweise).

## Commits

- 3410c81 test(05-07): startup reconciliation, write-ahead abort and sources
- 9df7fb8 feat(05-07): startup reconciliation before the paper-log
- 2ee8a7b test(05-07): source conflicts per fact and their reach
- ac3d163 feat(05-07): two sources per fact in the execute chain

## Verifikation (tatsaechliche Ausgabe)

- IBKR-Volllauf laut Plan (broker, contracts, executor, isolation, resolve, preview, decision, paperlog, guards, ledger, execute, state_maintenance, daily_paper_run, paper_summary_contract): `1014 passed`.
- `ruff check scripts tests`: All checks passed. `ruff format` nur auf `tests/test_ibkr_execute.py` (unveraendert); `scripts/ibkr_executor.py` nicht als Ganzes umformatiert (vorhandene Format-Abweichung).
- `-k "g3 and reconcil"`: 6 passed; `-k "reconcil or write_ahead"`: 15 passed; `-k source_conflict` (execute + guards): 25 passed.
- Greps: `resolve_entry(` = 1, `order_history()` = 1, `executed_conflict(` = 1, `position_conflict(` = 1, `account_conflict(` = 1, `RECONCILE_UNRESOLVED` >= 1.

## Deviations from Plan

**1. [Rule 1 - Anpassung bestehender Test]** `test_already_attempted_after_crash_is_not_a_second_intent` (05-06) erwartete nach einem Absturz Exit 2 `already_attempted`. Seit der Reconciliation trifft der Folgelauf zuerst den offenen `intent` ohne Spur und endet mit Exit 6; der Test prueft jetzt Exit 6, genau einen `intent` und kein whatIf.

**2. [Hinweis] Test-/Feat-Reihenfolge.** Der Code wurde vor den Tests geschrieben; die Tests sind je Aufgabe als `test(...)`-Commit vor dem `feat(...)`-Commit eingecheckt, ein rotes Zwischenergebnis wurde nicht beobachtet. Die Empfindlichkeit belegen die Negativ-Kontrollen (Reconciliation, Position, schon ausgefuehrt, Konto jeweils entfernt -> Verhalten kippt).

**3. [Praezisierung]** Bei Befund `open` wird `placed` nur geschrieben, wenn der Eintrag noch auf `intent` steht; sonst entstuende je Lauf eine weitere `placed`-Zeile.

**4. [Testfall Handelbarkeit]** Der Kalender-Widerspruch ist pro Lauf, nicht pro Ticker, steuerbar. "Der andere Ticker laeuft weiter" ist daher mit einem MSFT belegt, dessen `liquidHours` den Feiertag bestaetigen; er endet eigenstaendig als `outside_session` (nicht als Konflikt), nicht bei `intent`.

**5. [Hinweis] Worktree-Basis** laut Startpruefung auf 9e520e9 zurueckgesetzt (Branch `worktree-agent-*`, nichts verloren).

## Bekannte Grenzen

- Der Ticker, bei dem der Kontowiderspruch auftritt, erhaelt kein eigenes Ledger-Ende (der Lauf endet mit `run_end` `account-conflict`; `account-conflict` ist bewusst nicht in `REASON_BY_STATE`).
- REQ-45-Abweichung fuer Phase-6-Reihenfolgetest: Positions- und "schon ausgefuehrt"-Pruefung laufen nach der Aufloesung (benoetigen `conId`), im Code kommentiert.
- Die Aufloesung per `--resolve` bleibt Phase 6; das Handbuch (IBKR_EXECUTION.md) beschreibt den Ablauf (Plan 05-09).

## Known Stubs

Keine.

## Threat Flags

Keine neue Flaeche ueber T-05-38..43 hinaus.

## Self-Check: PASSED

- scripts/ibkr_executor.py, tests/test_ibkr_execute.py vorhanden; Commits 3410c81, 9df7fb8, 2ee8a7b, ac3d163 im Log.
