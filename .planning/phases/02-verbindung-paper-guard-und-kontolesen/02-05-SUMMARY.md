---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 05
subsystem: ibkr-executor
tags: [ibkr, executor, paper-guard, read-only, first-real-run, handbook, operator-checkpoint]
requires:
  - "02-04: scripts/ibkr_executor.py (Kommando `account`, Exit-Codes), scripts/IBKR_EXECUTION.md (Handbuch-Anfang)"
  - "02-02: scripts/ibkr_broker.py (IbkrBroker, Schreibsperre, Paper-Guard)"
  - "02-01: tradingagents.portfolio.load_portfolio"
provides:
  - "Nachweis Kriterium 1 gegen das laufende Paper-Gateway (DUQ634065): Exit 0, JSON lädt über load_portfolio()"
  - "Befund A2: clientId 20001 wird vom Gateway angenommen (kein 326)"
  - "scripts/IBKR_EXECUTION.md: Read-Only-Protokollzeile 2026-10-12 08:45 und Abschnitt `## First real run`"
affects: [02-06]
tech-stack:
  added: []
  patterns:
    - "Genau ein echter Lauf gegen das Gateway, kein Retry, keine Sondierung (T-02-21)"
    - "Offene Beobachtungen werden als offen protokolliert, nicht wegerklärt (fail-closed, REQ-IBKR-66/67)"
key-files:
  created:
    - .planning/phases/02-verbindung-paper-guard-und-kontolesen/02-05-SUMMARY.md
  modified:
    - scripts/IBKR_EXECUTION.md
decisions:
  - "Fehlende 321-Meldung beim Connect wird NICHT als Beweis für einen wirksamen Gateway-Read-Only-Schalter gewertet; die Client-Schreibsperre bleibt die tragende Barriere"
  - "Negativ-Gegenprobe Kriterium 3 am echten System (IBKR_PORT=4002 → Exit 3) nicht ausgeführt, weil der Plan genau einen Lauf erlaubt; abgedeckt nur durch Unit-Tests"
  - "Nach der Abnahme kein weiterer Lauf gegen das Gateway"
metrics:
  duration: "ca. 4 h 45 min Wanduhr (Checkpoint 08:45 bis Lauf 13:26 und Abnahme), Lauf selbst ca. 2 s"
  completed: 2026-10-12
  tasks: 3
  files: 1
---

# Phase 2 Plan 05: Erster echter `account`-Lauf gegen DUQ634065 Summary

Der Executor hat sich am 2026-10-12 einmal mit dem laufenden Paper-Gateway verbunden. Dabei waren `readonly=True` und die Client-Schreibsperre aktiv, die clientId war 20001. Der Lauf hat Konto `DUQ634065` als Paper-Konto bestätigt, Cash und Positionen frisch gelesen und ein `PortfolioContext`-JSON geschrieben, das `load_portfolio()` annimmt. Ergebnis: Exit 0, 0 Positionen, 1005459.44 EUR Cash. Vorher hatte der Operator den Gateway-Schalter „Read-Only API“ eingeschaltet und den Login mit dem separaten Paper-Benutzer bestätigt. Danach hat er den Lauf abgenommen. Einige Beobachtungen bleiben offen (siehe unten); vor allem beweist dieser Lauf **nicht**, dass der Gateway-Schalter tatsächlich wirkt.

## Tasks

| Task | Name | Commit | Ergebnis |
| ---- | ---- | ------ | -------- |
| 1 | Gateway „Read-Only API“ einschalten, Paper-Benutzer bestätigen (D-02, REQ-IBKR-03) | — (Handarbeit) | Operator: „read-only on 08:45, paper user“ (2026-10-12); Port-Gate 7497 Listen = Exit 0 |
| 2 | Echter `account`-Lauf, JSON-Gegenprobe, Handbuch | 4eb3695 | Exit 0; Read-Only-Zeile und `## First real run` in `scripts/IBKR_EXECUTION.md` |
| 3 | Operator-Abnahme (D-10, Teil 1) | — | „approved“ (2026-10-12) |

## Laufnachweis

- **Zeit:** 2026-10-12, 13:26:30 bis 13:26:32 Ortszeit. Es gab genau einen Lauf, ohne Wiederholung.
- **Kommando:** `.venv/Scripts/python.exe scripts/ibkr_executor.py account --out "$LOCALAPPDATA/TradingEngineX/ibkr/portfolio.json"`
- **Exit-Code:** 0
- **stdout:** `account: 0 position(s), cash 1005459.44 EUR -> C:\Users\admin\AppData\Local\TradingEngineX\ibkr\portfolio.json`
- **Gateway:** 10.50.1; im Log steht `Logged on to server version 178`. Die Sitzung lief 333 ms auf dem Socket, mit 6 gesendeten und 103 empfangenen Nachrichten.
- **clientId 20001 angenommen:** Es kam kein Code 326. Damit ist **Annahme A2 bestätigt** (D-07).
- **Paper-Guard bestanden:** Logzeile `ibkr-state=CONNECTED account=DUQ634065 clientId=20001 readonly=True`. `DUQ634065` ist das einzige verwaltete Konto.
- **JSON** unter `%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json`: `cash` = 1005459.44, `currency` = EUR, 0 Positionen. Die Gegenprobe mit `load_portfolio()` ist ok: `{'cash': 1005459.44, 'currency': 'EUR', 'positions': []}`.
- **Log:** Kein Traceback, kein `placeOrder`, kein `ReadOnlyViolation`. Der Orchestrator hat das selbst nachgezählt: 0 Treffer. Auch `orderStatus` und `newOrder` kommen nicht vor.
- **Beobachtete Zustände:**
  - `FARM_OK code=2104` (eufarm) und `code=2158` (secdefeu), beide INFO.
  - `UNKNOWN code=2107` (euhmds), WARNING.
- **Repo:** JSON und Log liegen außerhalb des Repos. Der Commit 4eb3695 ändert nur `scripts/IBKR_EXECUTION.md`.

## Nachweis je Anforderung / Kriterium

- **REQ-IBKR-03 (separater Paper-Benutzer):** Der Operator hat den Login in Task 1 bestätigt („paper user“). Der Benutzername steht nirgends.
- **REQ-IBKR-04 / Paper-Guard:** Die Guard-Prüfung ist für `DUQ634065` bestanden. Ein Exit 8 kam nicht vor.
- **REQ-IBKR-08 / REQ-IBKR-09 (Verbindung, clientId, Zustände):** Die Verbindung lief mit clientId 20001 und `readonly=True`. Die `ibkr-state=`-Zeilen sind benannt (Ausnahme: 2107, siehe Beobachtung 4).
- **REQ-IBKR-11 / Kriterium 1 (JSON lädt über `load_portfolio`):** Gegen das echte Gateway erfüllt.
- **REQ-IBKR-12 (keine Schreibaufrufe):** Im Log steht kein Schreibaufruf. Die Client-Sperre war aktiv; dass sie scharfgeschaltet wurde, steht allerdings nicht im Log (Beobachtung 3).
- **D-02:** Der Read-Only-Schalter ist vom Operator auf „on“ gesetzt und im Handbuch protokolliert. Ob er wirkt, ist offen (Beobachtung 1).

## Offene Beobachtungen (nicht gelöst)

1. **Kein 321 beim Connect, obwohl Read-Only an ist.** In Phase 1 kamen bei eingeschaltetem Schalter zwei 321-Meldungen beim Connect. Dieser Lauf zeigt keine. Wahrscheinliche Erklärung: Mit `StartupFetchNONE` entfällt der Order-Sync, der damals die 321 ausgelöst hat. Nach der fail-closed-Regel (REQ-IBKR-66/67) **beweist dieser Lauf nicht, dass der Gateway-Schalter wirkt**. Die clientseitige Schreibsperre hält unabhängig davon.
2. **Das Gateway lauscht auf `:::7497`**, also auf allen Interfaces. Ob „Allow connections from localhost only“ gesetzt ist, ist nicht bestätigt; das Handbuch behauptet es nicht.
3. **HEALTHY-Ergebnis und Scharfschalten der Sperre werden nicht geloggt.** `health()` gibt `HEALTHY` ohne Logzeile zurück (`scripts/ibkr_broker.py:345`). Der Health-Probe ist deshalb nur indirekt belegt: Eine ungesunde Sitzung hätte vor dem Snapshot mit Exit 3 geendet. Für einen Folgeplan vorgemerkt.
4. **Code 2107 fehlt in `STATE_BY_CODE`.** Er erscheint deshalb als `UNKNOWN` mit WARNING. Die Meldung ist harmlos und sollte als INFO abgebildet werden.
5. **`TotalCashValue` (1005459.44) und `NetLiquidation` (1005888.32) liegen 428.88 EUR auseinander**, obwohl keine Position offen ist. Vermutlich aufgelaufene Zinsen o. Ä.; nicht untersucht.
6. **Die Negativ-Gegenprobe für Kriterium 3 am echten System fehlt** (`IBKR_PORT=4002` → Exit 3, `GATEWAY_UNREACHABLE code=502`). Der Plan erlaubt genau einen Lauf; die Probe ist daher nur durch Unit-Tests abgedeckt.

## Deviations from Plan

Keine. Der Plan wurde wie geschrieben ausgeführt. Optionaler Schritt 4 aus Task 3 (Gegenprobe Kriterium 3) ist bewusst entfallen, siehe Beobachtung 6. Nach der Abnahme lief nichts mehr gegen das Gateway.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: network-exposure | IB Gateway (extern, kein Repo-File) | API-Port 7497 lauscht auf allen Interfaces (`:::7497`); Localhost-only-Einstellung unbestätigt (Beobachtung 2) |

## Known Stubs

Keine.

## Self-Check: PASSED

- `scripts/IBKR_EXECUTION.md` enthält `## First real run` und die Read-Only-Zeile vom 2026-10-12 08:45.
- Commit 4eb3695 ist vorhanden.
