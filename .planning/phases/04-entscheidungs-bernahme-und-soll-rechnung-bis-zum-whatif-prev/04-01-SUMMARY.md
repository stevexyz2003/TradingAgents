---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 01
subsystem: ibkr-decision
tags: [ibkr, decision-logic, summary-contract, whatif]
requires: []
provides:
  - scripts/ibkr_decision.py (Zustände, EXIT_BY_STATE, read_summary, latest_entries, evaluate_decision, plan_order, judge_preview)
affects: [04-05, 04-06, 04-07]
tech-stack:
  added: []
  patterns: [bibliotheksfreies Fachmodul, Frozen-Ergebniswerte, eine Exit-Tabelle]
key-files:
  created:
    - scripts/ibkr_decision.py
    - tests/test_ibkr_decision.py
    - tests/test_paper_summary_contract.py
  modified: []
key-decisions:
  - "Gebrochener Bestand wird vor dem Toleranzband geprüft (fractional-position), sonst würde 1.5 bei Ziel 2 als within-tolerance durchgehen."
  - "Unbekannter Vorschau-Zustand wird fail-closed als preview-empty behandelt."
requirements-completed: [REQ-IBKR-13, REQ-IBKR-14, REQ-IBKR-16, REQ-IBKR-17, REQ-IBKR-18, REQ-IBKR-21, REQ-IBKR-23, REQ-IBKR-24, REQ-IBKR-38, REQ-IBKR-61, REQ-IBKR-70]
duration: ~15min
completed: 2026-10-12
---

# Phase 4 Plan 01: Entscheidungslogik Summary

Bibliotheksfreies Fachmodul `scripts/ibkr_decision.py` mit Konsumentenvertrag für `summary.json`, Vorbedingungen inkl. Divergenz, Zielrechnung mit Toleranzband/long-only und Vorschau-Urteil mit Budgetprüfung.

## Ergebnis

- Task 1: Zustände, `EXIT_BY_STATE` (D-16 wörtlich), `read_summary`, `latest_entries`, `evaluate_decision`, `newer_summary_state`, Vertragstest gegen den echten Erzeuger `daily_paper_run.py`.
- Task 2: `BLOCKS`, `plan_order`, `judge_preview`, Property-Test über 5 x 6 x 3 Kombinationen.
- Commits: `9d33dc9` (RED, Tests), `ceca077` (GREEN, Modul). Beide Tasks wurden je in einem RED- und einem GREEN-Commit zusammengefasst statt je Task getrennt.
- Verifikation: 100 Tests grün (`test_ibkr_decision`, `test_paper_summary_contract`, `test_daily_paper_run`), `test_ibkr_isolation` grün, `ruff check scripts tests` sauber.

## Deviations from Plan

**1. [Rule 1 - Bug] Reihenfolge Bruchbestand vs. Toleranz in plan_order**
- Found during: Task 2 (Testfall Bestand 1.5, Ziel 2)
- Issue: In der geplanten Reihenfolge fing das Toleranzband den Fall ab, `fractional-position` wäre nie erreicht worden.
- Fix: Bruchprüfung vor dem Toleranzband.
- Commit: ceca077

**2. Commit-Granularität:** RED/GREEN-Commits über beide Tasks gemeinsam (siehe oben); inhaltlich unverändert.

## Known Stubs

Keine.

## Threat Flags

Keine.

## Self-Check: PASSED

Dateien `scripts/ibkr_decision.py`, `tests/test_ibkr_decision.py`, `tests/test_paper_summary_contract.py` vorhanden; Commits 9d33dc9 und ceca077 vorhanden.
