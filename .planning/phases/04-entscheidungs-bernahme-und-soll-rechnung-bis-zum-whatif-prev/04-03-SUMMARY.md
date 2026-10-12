---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 03
subsystem: ibkr-contracts
tags: [exchange_calendars, block_qty, session_day, ibkr]
requires: []
provides:
  - exchange_calendars im Extra ibkr (installiert im .venv)
  - ContractSpec.block_qty und table_problems()
  - SessionVerdict.session_day und ResolveResult.session_day
affects: [04-06, 04-07, 04-09]
tech-stack:
  added: [exchange_calendars 4.13.2, korean_lunar_calendar 0.4.0, pyluach 2.3.0, toolz 1.2.0]
  patterns: [Mengen als Code-Konstante, reines Zusatzfeld ohne Änderung bestehender Zweige]
key-files:
  modified: [pyproject.toml, scripts/ibkr_contracts.py, tests/test_ibkr_contracts.py]
key-decisions:
  - "block_qty ist Code-Konstante (1 für AAPL/MSFT/NVDA, 0 für nicht handelbare Einträge), nie aus einem Kurs abgeleitet"
  - "session_day: Fenster heute -> True, heute :CLOSED -> False, kein Eintrag -> None"
metrics:
  tasks: 3
  completed: 2026-10-12
---

# Phase 4 Plan 03: Mengen- und Kalendergrundlagen Summary

`exchange_calendars>=4.13,<5` im Extra `ibkr`, `block_qty` je Tabelleneintrag mit Prüffunktion `table_problems()` und `session_day` in `SessionVerdict`/`ResolveResult`.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Paket-Legitimitäts-Checkpoint (kein Code, kein Commit) | - |
| 2 | Abhängigkeit eintragen und installieren | 444b8e4 |
| 3 | block_qty und session_day (RED) | 11e6165 |
| 3 | block_qty und session_day (GREEN) | a862e1f |

## Task 1 (Checkpoint)

Vom Orchestrator erledigt: Wheel `exchange_calendars-4.13.2-py3-none-any.whl`, SHA-256 `fc5a2ad0d61b5c3a6539a3061cd4cbb55c59f4a903455cec7926e4b798919996`. Der Operator hat exchange_calendars, korean_lunar_calendar, pyluach und toolz mit "approved" freigegeben. Keine Dateien, kein Commit.

## Ergebnis

- `pip install -e ".[ibkr]"` ohne Zertifikatsfehler; `pip check` sauber; tzdata bleibt 2025.2 (< 2026.0). XNYS: 2026-09-07 keine Sitzung, 2026-10-12 Sitzung.
- `ib_async==2.1.0`, tzdata-Deckel und Kommentar unverändert.
- 227 Tests grün (contracts, resolve, isolation, executor); 12 neue Tests `block_qty`/`session_day`; ruff sauber.

## Deviations from Plan

**1. [Rule 3 - Blocking] Bestehende Tabellentests angepasst**
- **Issue:** `test_table_stock_entries` und `test_table_has_no_con_id_or_local_symbol_field` kodierten die alte Feldmenge von `ContractSpec` und scheiterten am neuen Feld.
- **Fix:** Erwartung um `block_qty=1` bzw. das Feld `block_qty` ergänzt.
- **Commit:** a862e1f

Sonst: Plan wie geschrieben ausgeführt. Bei Ablehnungs-/Fehlerfällen gab es keine Auth-Gates.

## Known Stubs

Keine.

## Threat Flags

Keine.

## Self-Check: PASSED

pyproject.toml, scripts/ibkr_contracts.py, tests/test_ibkr_contracts.py geändert; Commits 444b8e4, 11e6165, a862e1f vorhanden. STATE.md und ROADMAP.md nicht angefasst.
