---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 08
subsystem: ibkr-gateway-messung
tags: [whatif, read-only, D-14, SC2, messung]
requires: [04-05]
provides:
  - "Gemessen: Gateway-Schalter 'Read-Only API' blockt whatIf (321 + Timeout)"
  - "Reale whatIf-Vorschau mit Schalter aus (A2, A3, A4 geklaert)"
affects: [04-09, 04-VERIFICATION]
key-files:
  modified:
    - .planning/ibkr-konto-befund.md
decisions:
  - "SC2 Variante (a): Schalter blockt whatIf; Phase 4 schuetzt allein die Socket-Sperre, Schalter bleibt aus"
metrics:
  completed: 2026-10-12
  tasks: 3
requirements: [REQ-IBKR-38, REQ-IBKR-69, REQ-IBKR-70]
---

# Phase 4 Plan 08: whatIf-Messung und Read-Only-Schalter Summary

Reale whatIf-Vorschau am Paper-Gateway gemessen: mit Schalter aus vollstaendige Antwort, mit Schalter an Fehler 321 und 10 s Timeout (Variante a).

## Messung 1: Schalter aus (Commit 4d578e3)

- state OK, initMarginChange 100.86 EUR, maintMarginChange 91.69, commission 1.000003 USD
- effective_tif DAY (A3: Echo funktioniert), warningText leer (A2), errors [] , Contract-Felder reichen (A4)
- open_orders vorher/nachher leer, Positionen 0/0, Log ohne orderStatus/execDetails/ReadOnlyViolation
- Antwortzeit 0.79 s; Gateway 10.50.1 auf 127.0.0.1:7497

## Messung 2: Schalter an (Commit 7c905cc)

- state READ_ONLY_API, Margin/Kommission None, effective_tif None, sent_tif DAY
- errors: 321 "...Die API befindet sich im schreibgeschuetzten Modus."
- Dauer 10.02 s (Timeout)
- open_orders vorher/nachher leer, Positionen 0/0, Log (190 Zeilen) ohne orderStatus/execDetails/ReadOnlyViolation

## Folge fuer SC2

Variante (a): Der Schalter blockt whatIf. Phase 4 schuetzt allein die Socket-Sperre (Id 3 nur STK-whatIf, 04-02); der Gateway-Schalter bleibt waehrend Phase 4 aus. SC2-Satz zu 321 wird angepasst; Bestaetigung durch den Operator im 04-VERIFICATION.md (D-14). Der Operator muss "Read-Only API" wieder ausschalten (Bestaetigung holt 04-09 ein).

## Nicht messbar

Fehler 154 (Halt) ist am Paper-Gateway nicht herbeifuehrbar (A5); offene REQ-67-Luecke, nur ueber Codeliste und Fake-Test belegt.

## Deviations from Plan

None - plan executed exactly as written. Es wurde keine Datei unter scripts/ oder tests/ geaendert; die Sonde liegt nur im Scratchpad.

## Self-Check: PASSED

Commits 4d578e3 und 7c905cc vorhanden; Befund enthaelt Messung 1, Messung 2, Folge fuer SC2 und Nicht messbar.
