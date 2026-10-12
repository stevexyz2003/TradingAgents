---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 06
subsystem: ibkr-decision
tags: [ibkr, freshness, exchange_calendars, xnys, calendar-conflict]
requires: [04-01, 04-03]
provides:
  - scripts/ibkr_decision.py (SessionCalendar, XnysSessions, load_xnys_calendar, execution_session, Freshness, freshness, calendar_conflict, CalendarRangeError)
  - tests/calendar_stub.py (WeekdayCalendar)
affects: [04-07]
key-files:
  created: [tests/calendar_stub.py]
  modified: [scripts/ibkr_decision.py, tests/test_ibkr_decision.py]
key-decisions:
  - "Alle Kalenderfehler (Grenzen) sind fail-closed: freshness -> stale-decision, calendar_conflict -> True."
  - "XnysSessions fängt DateOutOfBounds, NotSessionError und RequestedSessionOutOfBounds und übersetzt sie in CalendarRangeError."
requirements-completed: [REQ-IBKR-19, REQ-IBKR-20]
metrics:
  tasks: 2
  completed: 2026-10-12
---

# Phase 4 Plan 06: Aktualität in Sitzungen Summary

Reine, kalender- und uhrinjizierte Funktionen `execution_session`, `freshness` und `calendar_conflict` mit XNYS-Hülle (lazy Import) und Stub-Kalender; alle vier SC4-Gegenproben plus D-08-Fälle laufen gegen den echten XNYS und den Stub mit identischem Ergebnis.

## Ergebnis

- `freshness`: geschlossene Sitzung strikt zwischen `trade_date` und E -> `stale-decision`; Lücke > 1 Kalendertag ohne geschlossene Sitzung -> `weekend_gap`; `trade_date >= E` -> `future-decision`; Kalendergrenze -> `stale-decision` statt Absturz; naive Uhr -> `ValueError`.
- `execution_session`: heute bei offener Sitzung, sonst nächste Sitzung mit `in_session_day=False`.
- `calendar_conflict`: Vergleich Kalender vs. `session_day` für den NY-Kalendertag; `None` -> False; Grenzfehler -> True.
- Verifikation: 90 Tests grün (`test_ibkr_decision`, `test_ibkr_isolation`), 18+ freshness- und 14 calendar_conflict-Tests ohne Skip; `ruff check scripts tests` sauber; keine Uhrzeit-Literale und keine Bibliotheksimporte auf Modulebene.

## Deviations from Plan

**1. Commit-Granularität:** Beide Tasks in je einem gemeinsamen RED-Commit (`f60381f`) und GREEN-Commit (`feat(04-06)`), wie in 04-01; inhaltlich unverändert.

**2. [Rule 3] `ruff check --fix`** hat Importstil (UTC-Alias) korrigiert; `ruff format` wird nicht erzwungen und wurde nicht angewandt.

## Known Stubs

Keine.

## Threat Flags

Keine.

## Self-Check: PASSED

scripts/ibkr_decision.py, tests/calendar_stub.py und tests/test_ibkr_decision.py vorhanden; Commit f60381f (RED) und der GREEN-Commit vorhanden. STATE.md und ROADMAP.md nicht angefasst.
