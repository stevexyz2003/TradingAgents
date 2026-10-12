---
status: partial
phase: 02-verbindung-paper-guard-und-kontolesen
source: [02-VERIFICATION.md]
started: 2026-10-12T14:30:00Z
updated: 2026-10-12T14:40:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. K1 erneut am echten Gateway — `account` mit dem Code nach den Review-Fixes
expected: Exit 0; `portfolio.json` enthält `as_of`; Log ohne `WRITE_REFUSED`, `UNEXPECTED` und Traceback. Grund: Seit dem Lauf vom 2026-10-12 13:26 wurde der Verbindungsweg an vier Stellen geändert (Sperre auf `send`/`sendMsg`, Cache-Leerung des Kontosummary, Settle-Fenster, Event-Loop-Behandlung).
result: passed — 2026-10-12 16:34:17 (lokal), Exit 0, Code nach den Review-Fixes (HEAD 0178678). `portfolio.json` = cash 1005459.44 EUR, 0 Positionen, `as_of` 2026-10-12T14:34:17.921620+00:00; vorher „previous portfolio removed“ (CR-02). Log: CONNECTED account=DUQ634065 clientId=20001 readonly=True, 0 Treffer für WRITE_REFUSED/UNEXPECTED/Traceback/placeOrder/ReadOnlyViolation. Gemessene Codes: 2104, 2158 (FARM_OK), 2107 (UNKNOWN, Hinweis IN-*).

### 2. K7 erneut — die `&&`-Kette aus `scripts/IBKR_EXECUTION.md` mit Anthropic-Konfiguration
expected: Exit 0; Block „Portfolio at the analysis date:“ in `complete_report.md`. Das alte JSON ohne `as_of` wird inzwischen mit Exit 1 abgelehnt, die Kette ist nach den Fixes also noch nicht am echten System gelaufen. Test 1 und 2 lassen sich in einem Lauf erledigen (kostet ca. 0,13 $ LLM).
result: passed — gleiche `&&`-Kette direkt danach, Anthropic aus `.env` (provider=anthropic deep=claude-sonnet-5-5 quick=claude-haiku-5-5), Exit 0, AAPL Hold, 0,1300 $; `complete_report.md` Z. 10–12: „Portfolio at the analysis date:“ / „No current position in AAPL“ / „Cash available: 1,005,459.44 EUR“. Scratch: `%TEMP%/tex-phase2-uat`, Repo unverändert.

### 3. REQ-IBKR-67 — Codes 1100/1101/1102/1300/2110 am echten Gateway messen oder per Override akzeptieren
expected: Entweder eine datierte Messung (z. B. Netzverbindung kurz trennen und den Code im Log ablesen), oder eine begründete Override-Notiz in VERIFICATION.md. Der Schutz aus CR-01 baut auf diesen Codes auf, gemessen sind bisher nur 321, 2104, 2158 und 2107.
result: [pending]

### 4. Gateway-Einstellung „Allow connections from localhost only“
expected: Gesetzt, oder bewusst abgelehnt und im Handbuch begründet. Das Gateway lauscht auf `:::7497`, also auf allen Interfaces.
result: [pending]

## Summary

total: 4
passed: 2
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
