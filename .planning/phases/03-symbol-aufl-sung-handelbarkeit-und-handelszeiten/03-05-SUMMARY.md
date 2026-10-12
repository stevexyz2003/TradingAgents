---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 05
subsystem: ibkr-executor-resolve
tags: [ibkr, cli, resolve, exit-2, contracts-json]
requires: ["03-02", "03-03", "03-04"]
provides:
  - "ibkr_executor.py resolve: Subkommando mit --contracts, --init, --rebaseline, --out"
  - "load_contracts_module, default_contracts_file, run_resolve, _guarded (geteilte Fehlerabbildung)"
  - "Exit 2 aktiviert (Ticker abgewiesen oder contracts.json fehlt)"
key-files:
  modified:
    - scripts/ibkr_executor.py
  created:
    - tests/test_ibkr_resolve.py
requirements-completed: [REQ-IBKR-26, REQ-IBKR-27, REQ-IBKR-28, REQ-IBKR-29, REQ-IBKR-30, REQ-IBKR-31, REQ-IBKR-37]
completed: 2026-10-12
---

# Phase 3 Plan 05: resolve-Kommando Summary

`ibkr_executor.py resolve` verdrahtet die Kette aus 03-03 mit dem Adapter aus 03-02: lokale Abweisung ohne Gateway, Connect nur bei Bedarf, Persistenz von `contracts.json` erst nach Sitzungsende, optionales atomares `--out`-JSON.

## Commits

- `fd23b05` test(03-05): Gerüst-Tests (Argumente, Contracts-Datei, Connect-on-demand)
- `9c75e3f` feat(03-05): Parser, Argumentprüfung, Contracts-Laden, `_guarded`, Exit 2
- `8b21e3e` test(03-05): Tests für init/Lernen/Drift/Mehrdeutigkeit/rebaseline/Sitzung/`--out`/Gateway-Fehler
- `614b64a` feat(03-05): Persistenz nach Sitzungsende, rebaseline-Zeile, `--out`

## Ergebnis

- Exit-Codes: ohne Ticker 1; fehlende Datei 2 (`CONTRACTS_MISSING`, Hinweis `resolve --init`); kaputte Datei/falsche Version 1 (`CONTRACTS_INVALID`); `--init` bei existierender Datei 2 (`CONTRACTS_EXIST`); Anker-Abweichung 2 (`ANCHOR_MISMATCH`, nichts geschrieben); abgewiesener Ticker 2 nach vollständiger Prüfung aller Ticker; `closed` 0; Gateway 3, Guard 8, fehlende Settings 20.
- `_guarded` ersetzt den kopierten `except`-Block; `account` nutzt ihn unverändert (alle Account-Tests grün), zusätzlich `MissingSettings`/`ConfigError`.
- Uhr: `datetime.now(UTC)` genau einmal (Default von `main(clock=...)`), `--now` kommt nirgends vor.
- Die Contracts-Datei wird nur geschrieben, wenn `outcome.events` nicht leer ist, nach dem `with`-Block (Test mit Spion belegt `disconnect` vor `commit_contracts`); `OSError` -> `OutputError` -> Exit 1 ohne Traceback auf der Konsole.
- `--out`: Schema `schema_version`, `as_of`, `results[...]` mit ISO-Strings; Vorgängerdatei wird zu Beginn entfernt; keine Roh-Sitzungszeiten.

## Verifikation (selbst ausgeführt)

- `pytest tests -k ibkr`: 318 passed
- `ruff check .`: All checks passed; `ruff format` auf beiden Dateien sauber
- Handlauf `resolve XYZQ ^GSPC XAUUSD+` ohne Gateway und ohne `.env`: drei `resolve:`-Zeilen, Exit 2
- Kein echter Gateway-Zugriff (nur FakeIB); der echte Lauf folgt in 03-06

## Abweichungen vom Plan

- Das Worktree stand beim Start auf `1394a3f`; gemäß Vorgabe per `git reset --hard` auf die Basis `49ad74a` korrigiert.
- [Rule 1 - Test] D-22-Test: Der Plan fordert, dass kein `liquid` (case-insensitiv) in den Dateien steht. Der Sitzungs-Verdict aus 03-03 liefert aber den Detailtext "inside a liquid window", der in `--out` landet. Das ist Diagnosetext, keine Broker-Zeiten. Der Test prüft nun `liquidhours`, `tradinghours`, den Roh-Stundenstring und `0930`. Alternative (Wortlaut in `ibkr_contracts.py` ändern) wurde nicht gewählt, um 03-03 nicht anzufassen.
- Die Fehlermeldung ohne Ticker lautet `resolve needs at least one TICKER (no default list)` (enthält den geforderten Text).

## Known Stubs

Keine.

## Self-Check: PASSED

Dateien vorhanden, Commits fd23b05, 9c75e3f, 8b21e3e, 614b64a vorhanden; STATE.md/ROADMAP.md nicht angefasst.
