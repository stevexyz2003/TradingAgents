---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 04
subsystem: ibkr-guards-und-anforderungen
tags: [ast-guard, sc7, req-ibkr-31, req-ibkr-37]
requires: ["03-01", "03-02"]
provides:
  - statische Guards für Resolver-Reinheit, Vendor-Normalizer-Verbot, SC7 und Uhr-Injektion
  - REQ-IBKR-31 nach D-19 umformuliert, Halt-Übergabe REQ-IBKR-37 an Phase 4
key-files:
  modified:
    - tests/test_ibkr_isolation.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
decisions:
  - "REQ-IBKR-37 bleibt Phase 3 zugeordnet; Halt-Teil (Fehler 154 am whatIf) in Phase 4 vermerkt"
metrics:
  completed: 2026-10-12
  tasks: 2
---

# Phase 3 Plan 04: Isolations-Guards und Anforderungsumformulierung Summary

Vier dauerhafte Guards (Resolver bibliotheksfrei, kein Vendor-Normalizer in `ibkr_contracts.py`/`ibkr_executor.py`, keine hart kodierten Handelszeiten in `scripts/ibkr_*.py`, keine Uhr im Resolver) sowie REQ-IBKR-31 nach D-19 und die Halt-Übergabe von REQ-IBKR-37 an Phase 4.

## Commits

- `a412125` test(03-04): Guards in `tests/test_ibkr_isolation.py` (4 neue Tests, 15 grün)
- `71eeb30` docs(03-04): REQUIREMENTS.md/ROADMAP.md (nur die planbestimmten Inhaltszeilen)

## Gegenprobe SC7

Temporär `# 09:30` an `scripts/ibkr_contracts.py` angehängt: `test_no_hard_coded_trading_times_in_execution_code` wurde rot. Anschließend per `git checkout -- scripts/ibkr_contracts.py` zurückgesetzt, nicht committet.

## Verifikation

- `tests/test_ibkr_isolation.py`: 15 passed
- `ruff check .`: All checks passed; `ruff format --check` auf der Testdatei: sauber (selbst nachgeprüft)
- Plan-Verify für Task 2 (grep-Kette): OK; kein `03-VERIFICATION.md`, kein `accepted_by`
- `ibkr-marktdaten-befund.md` und `.planning/debug/` nicht gestaged

## Abweichungen

- Das Worktree stand beim Start auf `1394a3f`; gemäß Vorgabe per `git reset --hard` auf die Basis `a5de0fe` korrigiert (Branch `worktree-agent-*`, nicht geschützt).
- Der Testmuster-Guard nutzt zusätzlich `ruff format` (Zeilenumbruch der Mustertabelle); inhaltlich unverändert.
- Der volle Testlauf der Suite wurde nicht ausgeführt, nur `test_ibkr_isolation.py` (bekannter Vorfehler `test_suite_isolation` nicht berührt).

## Offen für die Verifikation

Operator-Bestätigung der Änderungen an REQ-IBKR-31 und REQ-IBKR-37 im Verifikationsbericht der Phase 3 (bewusst keine Selbstabnahme). Änderungsnotizen verweisen darauf.

## Known Stubs

Keine.

## Self-Check: PASSED

Commits `a412125` und `71eeb30` vorhanden; geänderte Dateien existieren.
