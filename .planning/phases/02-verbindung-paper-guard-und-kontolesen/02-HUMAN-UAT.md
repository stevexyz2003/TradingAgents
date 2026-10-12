---
status: partial
phase: 02-verbindung-paper-guard-und-kontolesen
source: [02-VERIFICATION.md]
started: 2026-10-12T14:30:00Z
updated: 2026-10-12T14:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. K1 erneut am echten Gateway — `account` mit dem Code nach den Review-Fixes
expected: Exit 0; `portfolio.json` enthält `as_of`; Log ohne `WRITE_REFUSED`, `UNEXPECTED` und Traceback. Grund: Seit dem Lauf vom 2026-10-12 13:26 wurde der Verbindungsweg an vier Stellen geändert (Sperre auf `send`/`sendMsg`, Cache-Leerung des Kontosummary, Settle-Fenster, Event-Loop-Behandlung).
result: [pending]

### 2. K7 erneut — die `&&`-Kette aus `scripts/IBKR_EXECUTION.md` mit Anthropic-Konfiguration
expected: Exit 0; Block „Portfolio at the analysis date:“ in `complete_report.md`. Das alte JSON ohne `as_of` wird inzwischen mit Exit 1 abgelehnt, die Kette ist nach den Fixes also noch nicht am echten System gelaufen. Test 1 und 2 lassen sich in einem Lauf erledigen (kostet ca. 0,13 $ LLM).
result: [pending]

### 3. REQ-IBKR-67 — Codes 1100/1101/1102/1300/2110 am echten Gateway messen oder per Override akzeptieren
expected: Entweder eine datierte Messung (z. B. Netzverbindung kurz trennen und den Code im Log ablesen), oder eine begründete Override-Notiz in VERIFICATION.md. Der Schutz aus CR-01 baut auf diesen Codes auf, gemessen sind bisher nur 321, 2104, 2158 und 2107.
result: [pending]

### 4. Gateway-Einstellung „Allow connections from localhost only“
expected: Gesetzt, oder bewusst abgelehnt und im Handbuch begründet. Das Gateway lauscht auf `:::7497`, also auf allen Interfaces.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
