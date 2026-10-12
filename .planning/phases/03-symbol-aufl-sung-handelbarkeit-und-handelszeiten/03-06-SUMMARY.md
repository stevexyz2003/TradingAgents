---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 06
subsystem: ibkr-handbook-uat
tags: [ibkr, handbook, resolve, uat, paper-gateway]
requires: ["03-04", "03-05"]
provides:
  - "scripts/IBKR_EXECUTION.md: Abschnitte resolve, contracts.json, New ticker, aktive Exit-2-Zeile, 10167/200 und neue Zustände"
  - "Handbuch-Tests (resolve dokumentiert, Exit 2 aktiv, 10167 gelistet)"
  - "Protokoll des ersten resolve-Laufs gegen das Paper-Gateway"
key-files:
  modified:
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_isolation.py
requirements-completed: [REQ-IBKR-26, REQ-IBKR-28, REQ-IBKR-29, REQ-IBKR-30, REQ-IBKR-37]
completed: 2026-10-12
---

# Phase 3 Plan 06: Handbuch und erster resolve-Lauf Summary

Das Betriebshandbuch beschreibt jetzt `resolve`, `contracts.json` und den Ablauf "neuer Ticker". Der erste echte Lauf gegen das Paper-Gateway (127.0.0.1:7497) hat SC1, SC2 und SC4 belegt und wurde vom Operator abgenommen.

## Commits

- `55e477b` docs(03-06): resolve, contracts.json und neuer-Ticker-Ablauf im Handbuch; Handbuch-Tests
- `7ca58e6` docs(03-06): Protokoll des ersten resolve-Laufs gegen das Paper-Gateway

## Aufgaben

1. Handbuch (resolve, `--init`, `--rebaseline`, `--contracts`, `--out`, Ergebniszustände, Schema, Historie, `## New ticker`, Commands) und drei Handbuch-Tests. Exit 2 ist aktiv, 10167 = `MARKET_DATA_DELAYED`, 154 bewusst nicht gemappt.
2. Erster Lauf gegen das Paper-Gateway, Protokoll im Handbuch.
3. Checkpoint "Operator nimmt den resolve-Lauf ab": vom Operator am 2026-10-12 mit "approved" bestätigt. Keine Dateiänderung.

## Ergebnis des echten Laufs (2026-10-12, 20:09 CEST / 14:09 New York)

Vorbedingungen: keine bestehende `contracts.json`, `.env` vorhanden, Gateway auf 7497.

- (a) `resolve --init AAPL MSFT NVDA`: Exit 0. AAPL 265598, MSFT 272093, NVDA 4815747, alle NASDAQ/USD. Handelbar bis 15:45 ET (15-Minuten-Puffer).
- (b) Zweiter Lauf mit `--out`: Exit 0, identisches Ergebnis, Historie bleibt bei 3 Zeilen, kein `CONTRACT_LEARNED`.
- (c) `resolve XYZQ ^GSPC XAUUSD+`: Exit 2 mit `not-mapped` / `not-allowed(IND)` / `not-allowed(CMDTY)`. Kein `CONNECTED` im Log, also keine Verbindung.
- (d) Drift auf einer Scratchpad-Kopie (AAPL conId 999999): Exit 2, `drift`, `CONTRACT_DRIFT` auf ERROR. SHA-256 der echten `contracts.json` unverändert.
- Verify-Ausgabe: `ok {'AAPL': 265598, 'MSFT': 272093, 'NVDA': 4815747}`.
- Log: dreimal `learned conId=`, 0 `orderStatus`/`newOrder`/`ReadOnlyViolation`, `MARKET_DATA_TYPE delayed (3)` bei jedem verbundenen Lauf, `FARM_OK` 2104/2158 als INFO.

## Abweichungen vom Plan

- (d) zeigt im Detail `seen=none` statt 265598, weil das Gateway für eine unbekannte conId `200 CONTRACT_NOT_FOUND` antwortet. Das Ergebnis bleibt `drift`/Exit 2. Im Handbuch dokumentiert.
- 10167 trat in diesen Läufen nicht auf, weil `resolve` keine Kurse anfordert. Der Beleg für SC8 bleibt der Unit-Test plus der Befund.
- Code 2107 (euhmds) ist nicht gemappt und erscheint als `UNKNOWN` auf WARNING. Kandidat für ein späteres INFO-Mapping, bewusst nicht geändert.

## Offen für die Phasenverifikation (nicht als erledigt behauptet)

- Samstagslauf (D-24 gegen D-29).
- Operator-Bestätigung der Änderungen an REQ-IBKR-31 und REQ-IBKR-37.

## Known Stubs

Keine.

## Self-Check: PASSED

Commits 55e477b und 7ca58e6 in `git log` vorhanden. STATE.md und ROADMAP.md nicht angefasst. Gegen das Gateway wurde in dieser Fortsetzung nichts mehr ausgeführt.
