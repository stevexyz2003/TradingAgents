---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 07
subsystem: ibkr-executor
tags: [preview, whatif, dry-run, paper-log, executor]
requires: [04-01, 04-03, 04-04, 04-05, 04-06]
provides:
  - "ibkr_executor.py preview TICKER...: Trockenlauf von paper-log bis zum beurteilten whatIf, sendet nichts"
  - "run_preview, _local_chain, _gateway_chain, _preview_payload (Trockenlauf-JSON mit paper_log.sha, sent=false)"
  - "Settings IBKR_PAPER_LOG_REMOTE/BRANCH (validiert), Lader fuer ibkr_decision/ibkr_paperlog/state_maintenance"
  - "main(..., paper_log_factory=, calendar=) als Injektionspunkte"
affects: [04-08, 04-09]
tech-stack:
  added: []
  patterns:
    - "Lokale Kette vor jedem Verbindungsaufbau; Gateway nur fuer uebrig gebliebene Ticker"
    - "_RunAbort fuer Lauf-Zustaende (paper-log-unavailable, log-finding, summary-schema/-contract, CONTRACTS_MISSING)"
    - "Zeilenzustand je Ticker mit EXIT_BY_STATE; Phase-3-Ablehnungen ohne Tabelleneintrag zaehlen als Exit 2"
key-files:
  created:
    - tests/test_ibkr_preview.py
  modified:
    - scripts/ibkr_executor.py
key-decisions:
  - "intent im JSON hat genau side/quantity/order_type/tif_sent; die Marke closed liegt in session.closed (Testvertrag des Plans)"
  - "CONTRACTS_MISSING ist ein Lauf-Zustand (run_state) mit Exit 2; bereits entschiedene Ticker bleiben im Protokoll"
  - "Ungueltige contracts.json -> ConfigError (Exit 1, CONFIG_INVALID), wie in resolve"
  - "Test-Datei pinnt per autouse-Fixture executor.load_decision_module/load_paperlog_module auf die eigenen Modulinstanzen (kein Verlass auf sys.modules-Identitaet)"
requirements-completed: [REQ-IBKR-13, REQ-IBKR-14, REQ-IBKR-15, REQ-IBKR-16, REQ-IBKR-17, REQ-IBKR-18, REQ-IBKR-19, REQ-IBKR-20, REQ-IBKR-21, REQ-IBKR-22, REQ-IBKR-23, REQ-IBKR-24, REQ-IBKR-25, REQ-IBKR-38, REQ-IBKR-61, REQ-IBKR-68, REQ-IBKR-69, REQ-IBKR-70, REQ-IBKR-37]
duration: 75min
completed: 2026-10-12
---

# Phase 4 Plan 07: Subkommando preview Summary

`ibkr_executor.py preview TICKER...` liest den `paper-log`-Branch (fetch, byte-genaue Kopie, `state_maintenance.verify`), prueft Vorbedingungen und Aktualitaet je Ticker lokal und kontaktiert das Gateway nur fuer Ticker, die das ueberleben. Dort folgen Aufloesung/Sitzung, Kalenderabgleich, Position nach `conId`, fremde offene Orders, Zielrechnung und eine `whatIf`-Vorschau mit Urteil. Ergebnis: eine Konsolenzeile und eine Logzeile je Ticker (SHA in jeder Zeile) und ein atomares Trockenlauf-JSON. Es wird nichts gesendet.

## Umgesetzt

- Task 1 (Verdrahtung): Subparser ohne Datumsoption (D-07), Usage "account, resolve, preview", `IBKR_PAPER_LOG_REMOTE`/`_BRANCH` mit Defaults `fork`/`paper-log` und `validate_ref_name` (`-upload-pack=x` -> Exit 1), `_load_script_module` und drei Lader, `default_preview_file`/`default_paper_log_copy`, `REPO_ROOT`, Injektion `paper_log_factory`/`calendar`, Trockenlauf-JSON (`schema_version`, `as_of`, `paper_log{remote,branch,sha}`, `run_state`, `sent:false`, `rows`), Docstring und Exit-Tabelle (Exit 2 inkl. Hold, Exit 5 nicht mehr reserviert).
- Task 2 (lokale Kette): fetch ohne Rueckfall (`paper-log-unavailable`), Blob-Kopie atomar, UTF-8, leere Datei = `log-finding`, `verify` auf leerem Temp-`cache_dir` mit `redirect_stdout` (Zeilen ins Log, `FAIL:` im Detail), Parser ueber `TradingMemoryLog`, neuester Eintrag je Ticker, Summary-Cache (`summary-schema`/`-contract` -> Exit 1), `evaluate_decision`, neueres Summary (`newer_summary_state`), `freshness`. Hold endet hier (SC1, auch gegen echtes XNYS).
- Task 3 (Gateway-Kette): `contracts.json` nur lesen (`CONTRACTS_MISSING`, `not-resolved-yet`), `resolve_all` im Lauf-Modus, `calendar_conflict`, `closed` als Marke, `positions()` einmal je Lauf, Ist-Menge ueber die aufgeloeste `conId` (andere `conId` gleichen Symbols als `POSITION_OTHER_CONID` gemeldet), `open_orders`, `plan_order` mit `block_qty` aus der Tabelle, `preview_order`, `judge_preview`; Exit je Lauf ueber `worst_exit`.

## Verifikation

- `tests/test_ibkr_preview.py`: 69 Tests (Wiring, SC1 Stub+XNYS, Vorbedingungen, Schema, Divergenz, Aktualitaet, Buy-flat, G2 ueber sechs Pfade, Toleranz, offene Order, Long-only, Budget, Halt, tif, closed, Kalenderkonflikt, Contracts-Zustaende, mehrere Ticker, `ReadOnlyViolation` -> Exit 3, Gateway nicht erreichbar -> Exit 3).
- Gesamtsuite (ohne `test_yfinance_keeps_its_cache_out_of_the_users_home`): 2030 gruen, 4 uebersprungen; `ruff check scripts tests` ohne Befund.
- Greps: `sub.add_parser("preview"` 1, `trade-date` 0, `paper_log_factory` 9, `EXIT_*` 10, "reserved for later phases" 3, `placeOrder|cancelOrder|reqMktData|reqTickers` 0, `commit_contracts` 1, `"report"` 0.

## Deviations from Plan

**1. [Rule 1 - Bug im Plan-Vertrag] `intent` ohne `closed`.** Der Plantext listet `closed` unter `intent`, der Testvertrag (SC2) verlangt `intent == {side, quantity, order_type, tif_sent}`. `closed` steht in `session.closed` (ebenfalls Testvertrag).
**2. [Rule 3] Test-Isolation gegen `sys.modules`.** Im Volllauf scheiterte `test_missing_calendar_library_is_exit_1`, weil eine andere Testdatei `ibkr_decision` unter demselben Namen neu registrierte. Eine autouse-Fixture pinnt `load_decision_module`/`load_paperlog_module` auf die Instanzen der Datei.
**3. [Rule 2] Zusatzzustaende.** `FixturePaperLog.read_calls` ist ein Zaehler; fuer die Pfadpruefung (REQ-18) gibt es in den Tests eine Unterklasse, die Pfade mitschreibt. Zusaetzlich getestet: fehlende/ungueltige `contracts.json`, `fractional-position`, ungueltiges UTF-8.

## Known Stubs

Keine.

## Offene Punkte

- Das Handbuch `scripts/IBKR_EXECUTION.md` beschreibt `preview` noch nicht; `.planning/ibkr-konto-befund.md` wurde nicht angefasst.
- Gegen ein echtes Gateway nicht gemessen (nur Fakes): Echo-Abgriff fuer tif, Code 154 (Annahmen aus 04-05).

## Commits

- 435d1d5: test(04-07): failing tests fuer die Verdrahtung
- 5d36b63: feat(04-07): Subkommando, Settings, Lader, Protokoll
- caf41ba: test(04-07): failing tests fuer die lokale Kette
- 1a43312: feat(04-07): lokale Kette ohne Gateway
- b94c3cd: test(04-07): failing tests fuer die Gateway-Kette
- 0fa669f: feat(04-07): Gateway-Kette

## Self-Check: PASSED
