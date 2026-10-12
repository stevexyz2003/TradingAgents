---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 03
subsystem: ibkr-contracts
tags: [ibkr, persistence, resolver, drift, history]
requires: ["03-01", "03-02"]
provides:
  - "scripts/ibkr_contracts.py: StoredContract, HistoryEvent, load_contracts_file, contracts_payload, write_json_atomic, commit_contracts, contracts_history_path, ContractsFileMissing/-Error, AnchorMismatch, ResolveResult, ResolveOutcome, needs_broker, resolve_all"
affects: [03-04, 03-05]
key-files:
  modified:
    - scripts/ibkr_contracts.py
    - tests/test_ibkr_contracts.py
requirements-completed: [REQ-IBKR-29, REQ-IBKR-30, REQ-IBKR-31, REQ-IBKR-37]
completed: 2026-10-12
---

# Phase 3 Plan 03: Persistenz und Resolver Summary

`contracts.json` (strikt validiert, atomar) mit append-only `contracts-history.jsonl` sowie die bibliotheksfreie Kette `resolve_all` (Mapping, Allow-List, Lernen/Gegenprobe/Drift, Handelbarkeit, Sitzung) mit injiziertem Broker und injizierter Uhr.

## Tasks

| Task | Commits |
|------|---------|
| 1: Persistenz, History, Atomarität | RED `c75eb8a`, GREEN `76f0752` |
| 2: resolve_all | RED `a7c5c83`, GREEN `5e22c24` |

## Ergebnis

- Laden wirft `ContractsFileMissing` (Datei fehlt, Hinweis `resolve --init`) bzw. `ContractsFileError` (nicht UTF-8, kein JSON, falsche Version, bool/Nicht-int/<=0 als `conId`, Fehl- oder Zusatzfelder). Nie stilles Neu-Lernen.
- `commit_contracts`: History-Zeilen werden mit `flush` + `os.fsync` VOR `os.replace` geschrieben; bei Fehlschlag folgt `<event>-aborted`, Fehler wird erneut ausgelöst, temp-Datei wird entfernt. Ein Test belegt die Reihenfolge per Spion auf `os.replace`.
- Keine Sitzungswerte in Datei oder History (Test).
- `resolve_all`: Lernen (genau 1 Treffer, Suchschlüssel- und Details-Abgleich), Zweitlauf mit Abfrage per conId plus Gegenprobe per Suche, `drift` je Ticker (gespeicherter Wert bleibt, andere Ticker laufen weiter), `ambiguous` mit einer Logzeile über alle Kandidaten (21-Kandidaten-Test), `rebaseline` nur für den genannten Ticker mit alt/neu, `init` mit Anker-Prüfung (`AnchorMismatch`), `not-tradable`, `closed` (keine Abweisung), `session-unknown` (Abweisung).
- `pytest tests/test_ibkr_contracts.py tests/test_ibkr_broker.py`: 224 passed; `pytest tests -k ibkr`: 283 passed. `ruff check .` und `ruff format --check` auf beiden Dateien: ohne Befund (selbst ausgeführt). Greps auf Uhrzeit-Literale, `datetime.now`, `time.time(`, `date.today`, `normalize_symbol` und auf Bibliotheks-Importe im Modul: leer.

## Deviations from Plan

- Worktree-Basis stand auf 1394a3f; vor jeder Arbeit auf a5de0fe zurückgesetzt, wie in der Startvorgabe vorgesehen.
- [Rule 1 - Lint] `ruff` B023 (Schleifenvariable in Hilfsfunktion): `ticker` wird per Default-Argument gebunden. Kein Verhaltenseffekt.
- Sonst keine Abweichungen. Die nicht zugehörige Suite-Isolation (yfinance-Cache) wurde nicht angefasst.

## Known Stubs

Keine.

## Self-Check: PASSED

Dateien vorhanden, Commits c75eb8a, 76f0752, a7c5c83, 5e22c24 vorhanden; STATE.md/ROADMAP.md unverändert.
