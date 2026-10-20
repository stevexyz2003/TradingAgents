---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 03
subsystem: ibkr
tags: [calendar, git, ci-feed]
requires: []
provides:
  - second_last_close_utc (scripts/ibkr_decision.py)
  - GitPaperLog fetch_depth (scripts/ibkr_paperlog.py)
affects: [07-07]
key-files:
  modified:
    - scripts/ibkr_decision.py
    - tests/test_ibkr_decision.py
    - scripts/ibkr_paperlog.py
    - tests/test_ibkr_paperlog.py
requirements: [REQ-IBKR-52]
completed: 2026-10-20
---

# Phase 7 Plan 03: Gültigkeitsgrenze und flacher Fetch Summary

`second_last_close_utc` als reine Kalenderfunktion (D-06) und optionales `fetch_depth` im `GitPaperLog`.

## Ergebnis

- Task 1 (Commit 717c19f): `second_last_close_utc(now_utc, calendar, *, window_days=14)` liefert den Schluss der vorletzten geschlossenen Sitzung; weniger als zwei geschlossene Sitzungen im Fenster ergeben `CalendarRangeError`; naive Uhrzeit ergibt `ValueError`. Keine Uhrzeit-Literale, keine Modul-Level-Bibliotheksimporte. 8 neue Tests (inkl. echter XNYS-Kalender, Thanksgiving-Fall -> 2026-11-25 21:00 UTC).
- Task 2 (Commit 0f6e8bd): `GitPaperLog(..., fetch_depth=None)`; bei gesetztem Wert `--depth=N` nach `--quiet`; nur `int >= 1` (kein `bool`), sonst `ValueError`. Standard-argv unverändert. Modul-Docstring nachgezogen. `validate_blob_path` lässt `ledger.jsonl`/`portfolio.json` bereits zu, keine Änderung nötig. 4 neue Test-Funktionen (parametrisiert), inkl. echtem flachem Fetch über `file://` aus lokalem Repo (Tiefe 1 verifiziert).

## Verifikation (ausgeführt)

- `pytest tests/test_ibkr_paperlog.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py tests/test_ibkr_isolation.py -q`: 262 passed
- `pytest tests/test_ibkr_decision.py -k second_last`: 8 passed
- `ruff check scripts tests`: sauber
- `ruff format --check` meldet 2 Dateien als umformatierbar (nicht als Gate im Plan; nicht behoben, möglicherweise bereits vorher so).

## Abweichungen

Keine funktionalen. Der Worktree-HEAD lag nicht auf der erwarteten Basis und wurde per Vorgabe auf b346a33 zurückgesetzt.

## Self-Check: PASSED

Commits 717c19f und 0f6e8bd vorhanden; STATE.md/ROADMAP.md unverändert.
