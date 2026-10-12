---
status: partial
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
source: [03-VERIFICATION.md]
started: 2026-10-12T19:00:00Z
updated: 2026-10-12T19:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Samstagslauf `resolve AAPL` (D-24 vs. D-29)
expected: An einem Samstag liefert `.venv/Scripts/python.exe scripts/ibkr_executor.py resolve AAPL` den Zustand `closed` mit nächstem Fenster und Exit 0. Ergibt sich stattdessen `session-unknown` (Exit 2), weil `liquidHours` für den Tag keinen Eintrag hat, ist das ein Befund für den Operator (D-24 lockern oder nicht) — keine stille Codeänderung.
result: [pending]

### 2. Operator-Bestätigung REQ-IBKR-31 (D-19)
expected: Der Operator bestätigt die Textänderung von REQ-IBKR-31 (Ersatzsignale statt `ineligibilityReasonList`, Befund `.planning/ibkr-konto-befund.md` §4) und trägt `accepted_by`/`accepted_at` im Override-Block von `03-VERIFICATION.md` ein.
result: [pending]

### 3. Operator-Bestätigung Halt-Teil REQ-IBKR-37 → Phase 4 (D-20)
expected: Der Operator bestätigt, dass HALTED-Tick/154 nicht in Phase 3 geprüft wird (delayed Daten liefern keinen Halt-Tick), sondern am `whatIf` in Phase 4, und trägt `accepted_by`/`accepted_at` im Override-Block von `03-VERIFICATION.md` ein.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
