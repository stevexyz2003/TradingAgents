---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 04
subsystem: reporting
tags: [ibkr, ledger, decision-log, soll-ist, join]

requires:
  - phase: 06-die-erste-echte-order
    provides: Live-Ledger mit intent/placed/filled/alarm-Ereignissen
provides:
  - "scripts/ibkr_report.py: Decision, ReportRow, parse_decisions, read_ledger, build_rows, NO_RUN"
  - "Join je decision_key aus Decision-Log und Live-Ledger, nur lesend"
affects: [07-05 (Darstellung, Metriken, CLI auf demselben Modul)]

tech-stack:
  added: []
  patterns:
    - "Datenschicht rein: Text/Bytes rein, Zeilen raus, keine Uhr, tradingagents-Import nur in Funktionen"
    - "Ziel/Ist nur aus dem intent; fehlende Werte bleiben leer mit Hinweis (D-20)"

key-files:
  created: [scripts/ibkr_report.py, tests/test_ibkr_report.py]
  modified: []

key-decisions:
  - "Erste Fassung je (Datum, Ticker) gewinnt, verworfene Duplikate werden gezählt (D-12)"
  - "Ohne intent bleiben Ziel/Ist leer, Hinweis statt Schätzung; `detail` wird nie geparst (D-16, D-20)"

requirements-completed: [REQ-IBKR-49]

duration: ~25min
completed: 2026-10-20
---

# Phase 7 Plan 04: Datenschicht des Soll-Ist-Berichts Summary

**`scripts/ibkr_report.py` liest Decision-Log-Text und Live-Ledger-Bytes und liefert je Entscheidung genau eine Berichtszeile (Zustand, Ziel, Ist vorher/nachher, Order-/Fill-Menge, Durchschnittspreis, Abweichung, Hinweise).**

## Umgesetzt

- Task 1 (`858082d`): `parse_decisions` (über `TradingMemoryLog.load_entries` auf Temp-Kopie, Dedup erste Fassung, Zähler für unlesbare Blöcke und Duplikate), `read_ledger` (`Ledger.open` mit `MODE_LIVE`, Uhr wirft; Dry-Run-Ledger und kaputte Mitte lösen `LedgerError` aus), `Decision`/`ReportRow`.
- Task 2 (`9be1bd2`): `build_rows` mit Zustand aus dem letzten Lifecycle-Ereignis, `fill-timeout` aus Alarm am `placed`, korrektur-bewusste Fills via `effective_executions`, Plausibilitätsprüfung für `held_before`, Ledger-Keys ohne Log-Eintrag in zweiter Rückgabeliste.

## Verifikation (tatsächlich ausgeführt)

- `pytest tests/test_ibkr_report.py tests/test_ibkr_ledger.py`: 132 passed (davon 23 in `test_ibkr_report.py`, 14 mit `-k join`).
- `pytest tests/test_ibkr_isolation.py`: 34 passed.
- `ruff check scripts tests`: sauber; `ruff format` angewandt.
- `grep -c 'datetime.now|time.time(|date.today|get("detail")' scripts/ibkr_report.py` = 0.

## Deviations from Plan

- TDD-Reihenfolge: Das Modul wurde vollständig vor den Tests geschrieben; es gibt keinen separaten `test(...)`-RED-Commit vor `feat(...)`. Task 1 enthält bereits `build_rows`, Task 2 committet nur dessen Tests. Verhalten und Abdeckung entsprechen dem Plan.
- Die Lazy-Zugriffe `_contracts()` und `_paperlog()` wurden nicht angelegt, da das Modul sie nicht braucht (`block_qty_of` wird injiziert; 07-05 kann sie ergänzen).

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche; Modul liest nur, Temp-Dateien liegen in `TemporaryDirectory`.

## Self-Check: PASSED

- `scripts/ibkr_report.py` und `tests/test_ibkr_report.py` vorhanden; Commits `858082d` und `9be1bd2` in `git log`.
- STATE.md und ROADMAP.md nicht angefasst.
