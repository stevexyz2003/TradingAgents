---
status: complete
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
source: [04-VERIFICATION.md]
started: 2026-10-16T19:27:26Z
updated: 2026-10-16T19:27:26Z
---

## Current Test

[testing complete]

## Tests

### 1. D-14 / SC2-Anpassung: Read-Only-Schalter und 321
expected: Operator bestätigt den Ersatzsatz für SC2 und dass der Gateway-Schalter „Read-Only API" aus bleibt.
result: passed — 2026-10-16, vom Operator entschieden. Gemessen am 2026-10-12: Der Schalter blockt auch `whatIf` (321, 10 s Timeout, keine Margin- und Kommissionsdaten); er bleibt deshalb aus. Den Schutz vor einem versehentlichen `place` trägt allein die Socket-Sperre des Adapters (Nachricht 3 nur als STK-`whatIf`; 4/19/21/58, `cancelOrder`, `reqGlobalCancel`, `exerciseOptions` hart gesperrt), mehrfach getestet einschließlich Real-Client-Test. SC2 in ROADMAP.md ist umformuliert.

### 2. Fehler 154 (Halt) am Paper-Gateway
expected: Operator akzeptiert, dass 154 am Paper-Gateway nicht herbeiführbar ist und nur über die offizielle Codeliste plus Fake-Test belegt ist.
result: passed (Override) — 2026-10-16, Lücke akzeptiert bis zur ersten Live-Gelegenheit; Begründung im `overrides:`-Eintrag der VERIFICATION-Frontmatter. 154 ist request-gebunden und wird in der Vorschau ausgewertet; die Lesefenster-Lücke, die d344433 geschlossen hat, betrifft ihn nicht.

### 3. Realer Trockenlauf 04-09
expected: `preview: AAPL skipped-hold (trade_date 2026-10-09)`, Exit 2, sha 7b4af23df6e823dff723f74f8925e807176160e0, sent=false, in den Bericht übernommen.
result: passed — vom Operator bereits abgenommen (04-09-SUMMARY), hiermit übernommen. Der Lauf ist aus SUMMARY und Operator-Aussage belegt, nicht vom Verifier wiederholbar.

### 4. REQ-IBKR-25, Teil Sitzungsfenster
expected: Operator entscheidet, wohin das konfigurierte Fenster der regulären Sitzung (nicht Eröffnungsauktion, nicht Schlussminuten) gehört.
result: passed — 2026-10-16, nach Phase 5 verschoben. Phase 4 sendet nichts und kann ein Platzierungsfenster nicht erfüllen; erfüllt sind hier MKT/`DAY` und die Berücksichtigung offener Orders. Das Fenster ist eine Leitplanke: Gate G3 verlangt einen Sitzungs-Test vor der Freigabe des Schreibrechts, und das Schnittprinzip verlangt alle Leitplanken scharf vor der ersten Order. In ROADMAP.md steht REQ-IBKR-25 (Teil Sitzungsfenster) jetzt zusätzlich unter Phase 5.

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
