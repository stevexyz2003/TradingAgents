---
phase: 05-leitplanken-scharf
plan: 10
subsystem: ibkr-operator-checkpoint
tags: [ibkr, operator-checkpoint, kill-switch, paper-account]
requires: [05-09]
provides:
  - ".planning/ibkr-konto-befund.md: Abschnitt „Kill-Storno, Orderhistorie und orderRef (Phase 5, D-06)“ mit Abnahme"
affects: [06]
key-files:
  created: []
  modified:
    - .planning/ibkr-konto-befund.md
key-decisions:
  - "Gemessen über TWS Paper statt IB Gateway: pro Benutzer ist nur eine Sitzung möglich, die API ist dieselbe (Serverversion 178)"
  - "Die Abnahme in Task 3 lief serverseitig über das Gateway (Historie und whatIf), weil die TWS-Sitzung durch den Gateway-Neustart getrennt war"
  - "„Read-Only API“ bleibt aus (Phase 6 sendet)"
requirements-completed: [REQ-IBKR-33, REQ-IBKR-35, REQ-IBKR-39, REQ-IBKR-41, REQ-IBKR-43]
completed: 2026-10-17
---

# Phase 5 Plan 10: Kontobefund am echten Paper-Konto Summary

Die Messung am echten Paper-Konto `DUQ634065` am 2026-10-17 bestätigt alle Annahmen. `execute AAPL` mit `KILL` endet mit Exit 4 nach genau einem globalen Storno (`sent=1`, `remaining=0`). Das Storno nimmt auch eine manuell in TWS angelegte Order zurück (`permId 1440521754`, `client_id 0`). Ein `orderRef` mit `|` wird angenommen und samt Konto im Echo zurückgegeben.

## Ergebnis

| Messung | Ergebnis |
|---|---|
| 1 Einzeiler | `RELEASE` ergibt `release-ok`, `KILL` ergibt `kill-active`, die Datei ist UTF-8 ohne BOM |
| 2 Kill-Storno (SC3) | Exit 4; `GLOBAL_CANCEL_SENT count=1`; `KILL_CANCEL remaining=0 rechecks=2`; im Ledger stehen `run_start`, `kill_cancel` und `run_end` |
| 3 Historie (A2) | Die Order steht unter `completed` mit `status Cancelled` und `filled 0.0`, `executions` ist leer |
| 4 orderRef (A3, A5) | `2026-10-09|AAPL` ergibt `state OK`, `echo_order_ref` ist identisch, `echo_account DUQ634065` |

Folgen: A1 ist bestätigt, `resolve_entry` (`Cancelled` → `not_filled`) passt zur Messung, `DECISION_KEY_SEPARATOR` bleibt `|`, und das Echo-Konto ist vorhanden (D-22). Es gibt **keine Abweichung** und damit auch keine Lücke für Gap-Closure.

## Vorprüfungen (vom Orchestrator selbst ausgeführt)

- `ruff check .`: All checks passed
- `pytest -k g3 -q`: 14 passed
- Volle Suite: 2425 passed, 1 failed. Der Fehler ist der bekannte, schon vor der Phase rote Test `test_yfinance_keeps_its_cache_out_of_the_users_home`.
- Im State-Ordner lagen vorher weder `KILL` noch `RELEASE`. Nachher gilt dasselbe, neu sind `ledger-dryrun.jsonl` und `ledger.jsonl.lock`.

## Abweichungen

- **TWS statt Gateway:** Das Anmelden in TWS hat das Gateway getrennt, weil pro Benutzer nur eine Sitzung erlaubt ist. In TWS musste der Operator die API („ActiveX- und Socket-Clients aktivieren“) erst einschalten. Bis dahin endete der erste Versuch mit `GATEWAY_UNREACHABLE`, Exit 3.
- **Abnahme serverseitig:** Der Operator konnte TWS nach dem Gateway-Neustart nicht mehr einsehen. Das Storno und den Schalterzustand habe ich deshalb über das Gateway geprüft: Die Historie zeigt `Cancelled`, und der whatIf liefert `OK`, also ist „Read-Only API“ aus.

## Commits

- docs(05-10): record kill cancel, order history and orderRef on the paper account
- 8a76308 docs(05-10): record the server-side acceptance of the kill cancel

## Self-Check: PASSED
