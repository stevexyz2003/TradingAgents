---
phase: 05-leitplanken-scharf
plan: 04
subsystem: ibkr-executor
tags: [ibkr, execute, forced-dry, ledger, write-ahead, order-ref, tdd]
requires: [05-01, 05-02, 05-03]
provides:
  - "ibkr_executor.py execute (zwangsweise trocken), run_execute, DryPlacer, _ExecuteStop"
  - "default_release_file/default_kill_file/default_ledger_file/default_dryrun_ledger_file, load_guards_module, load_ledger_module"
  - "_session, _execute_gateway_chain, _execute_ticker, _ledger_row_finished, _position_and_orders"
affects: [05-05, 05-06, 05-07, 05-08]
key-files:
  created: [tests/test_ibkr_execute.py]
  modified: [scripts/ibkr_executor.py, tests/test_ibkr_preview.py]
key-decisions:
  - "run_end wird in run_execute geschrieben (nicht in _abort_run); _abort_run ist nur additiv erweitert (Label, ctx.out optional)"
  - "Gateway-Kette von execute oeffnet bei Restbestand immer die Sitzung (kein needs_broker-Zweig ohne Broker)"
requirements-completed: [REQ-IBKR-39, REQ-IBKR-41, REQ-IBKR-42, REQ-IBKR-46, REQ-IBKR-66]
completed: 2026-10-17
---

# Phase 5 Plan 04: execute-Durchstich Summary

`ibkr_executor.py execute TICKER...` laeuft als zwangsweise trockenes Subkommando bis zum Write-Ahead-`intent` (`orderRef == decision_key`, SHA als Provenienz) mit Trocken-Abschluss `dry_complete`; alle Ticker-Enden stehen mit Grund (`skipped`) oder Urteil (`rejected`) in `ledger-dryrun.jsonl`.

## Ergebnis

- Subkommando ohne jede Option fuer live/Freigabe/Datum; `EXECUTE_FORCED_DRY = True`; ein Placer mit `dry` ungleich `True` endet vor jedem Dateizugriff mit Exit 1 (`ibkr-state=NOT_DRY`).
- State-Ordner: `ensure_outside_git` vor `mkdir` (Exit 1 `STATE_IN_GIT_TREE`); defekter oder modus-fremder Ledger: Exit 6 (`LEDGER_CORRUPT`), kein Gateway. `ledger.jsonl` entsteht nie.
- `ctx` wird vor `Ledger.open` vollstaendig gebaut (Felder laut Plan, plus `remote`, `branch`, `stored` in der Gateway-Kette).
- `run_start` vor jeder Entscheidung, `run_end` mit `exit` (via `worst_run_exit`) und ggf. `state`; unerwartete Ausnahme: `run_end` mit `outcome:"error"` und Ausnahmetyp, danach `_guarded`.
- Write-Ahead: `ledger.append(INTENT)` (fsync) vor `placer.complete`; `DryPlacer` prueft `check_size` ein zweites Mal und schreibt `dry_complete`.
- `_ledger_row_finished`: `REJECTED_STATES` vor `REASON_BY_STATE`; unbekannter Zustand faellt auf `skipped`/`review` mit `unmapped_state:true` und WARNING `LEDGER_REASON_UNMAPPED` zurueck.
- `preview` unveraendert: `_finish_row`/`_abort_run` nur additiv (Label, Exit-Suche in Guards-Tabelle, Hook), `_position_and_orders` ohne Verhaltensaenderung herausgeloest.
- Gleichheitstest `guards._EXIT_*` gegen Executor-Konstanten in `tests/test_ibkr_execute.py` (Hinweis aus 05-01 erledigt).

## Commits

- aaaf1c7 test(05-04): Rahmen (RED)
- 40bc55c feat(05-04): Rahmen
- fbfefe4 test(05-04): Gateway-Kette (RED)
- 6430cad feat(05-04): Gateway-Kette

## Verifikation (tatsaechliche Ausgabe)

- IBKR-Volllauf (broker, contracts, executor, isolation, resolve, preview, decision, paperlog, guards, ledger, execute): `849 passed`.
- `tests/test_ibkr_execute.py`: 44 Tests; `-k "forced_dry or dryrun or git or ledger_corrupt"`: 15 passed; `-k "order_ref or decision_key or write_ahead or nothing_sent or forced_dry"`: 11 passed; `exit_literals_match`/`reason_fallback`: je grün.
- `ruff check scripts tests`: All checks passed. `ruff format` nur auf `tests/test_ibkr_execute.py`; `scripts/ibkr_executor.py` hat bereits vorhandene Format-Abweichungen ausserhalb dieses Plans, nicht angefasst.
- Greps: `placeOrder|cancelOrder|whatIfOrder|reqMktData|reqTickers` = 0; `cancel_all(` = 0; `placer.complete(` = 1; `order_ref=key` = 2; `EXIT_*`-Konstanten = 10; `reserved for later phases` = 0; `"--live"|"--wet"|"--real"` = 0.

## Deviations from Plan

**1. [Hinweis] `run_end` fuer Abbrueche in `run_execute` statt in `_abort_run`.** Der Plan nennt "fuer execute haengt `_abort_run` `run_end` mit `state` an". Umgesetzt: `_abort_run` meldet nur (Log, Konsole, Code); `run_execute` schreibt genau ein `run_end` mit `exit` und `state` fuer alle Pfade (vermeidet doppeltes `run_end`).

**2. [Hinweis] `needs_broker`-Zweig entfallen.** Bei Restbestand oeffnet `_execute_gateway_chain` stets die Sitzung; ein Pfad mit `broker=None` waere fuer die Position/whatIf-Kette ohnehin nicht nutzbar.

**3. [Hinweis] Zwei Tests an die Umgebung angepasst.** Der Loader-Test prueft Dateinamen statt Objektgleichheit, weil `tests/test_ibkr_guards.py` und `tests/test_ibkr_ledger.py` eigene Instanzen unter demselben Modulnamen registrieren koennen.

Sonst: Plan wie geschrieben ausgefuehrt. Worktree-Basis wurde laut Anweisung auf c3f1aac zurueckgesetzt. STATE.md und ROADMAP.md nicht angefasst.

## Bekannte Grenzen / Hinweise fuer Folgeplaene

- Ein Abbruch in der lokalen Kette verliert die bis dahin fertigen Zeilen fuer den Run-Exit (nur `_abort_run`-Code zaehlt); deren Exits sind dort 0/2/1 und ueberstimmen den Abbruchcode nicht.
- `closed` (Markt zu) wird in `execute` nur vermerkt; die Ablehnung kommt mit 05-06.
- Schalter/Lock/Kill (05-05) setzen an `ctx.switches`, `ctx.cancelled`, `ctx.halted` und `ctx.state_dir` an; die Sitzung kommt aus `_session(ctx)`.

## Known Stubs

Keine.

## Threat Flags

Keine neue Flaeche ueber das Threat-Register (T-05-21..26) hinaus.

## Self-Check: PASSED

- scripts/ibkr_executor.py, tests/test_ibkr_execute.py vorhanden; Commits aaaf1c7, 40bc55c, fbfefe4, 6430cad im Log.
