---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 04
subsystem: ibkr-executor
tags: [ibkr, executor, exit-codes, paper-guard, portfolio-json, logging, handbook]
requires:
  - "02-02: scripts/ibkr_broker.py (IbkrBroker, AccountSnapshot, AccountGuardViolation, GatewayUnavailable), tests/ibkr_fakes.py"
  - "02-01: tradingagents.portfolio.load_portfolio / PortfolioContext"
provides:
  - "scripts/ibkr_executor.py: Kommando `account`, Exit-Codes 0/1/2/3/4/5/6/7/8/20, REQUIRED_ENV, read_settings, validate_settings, setup_logging/close_logging, default_log_file, snapshot_to_portfolio, write_portfolio_atomic, run_account, main"
  - "scripts/IBKR_EXECUTION.md: Anfang des Betriebshandbuchs (REQ-IBKR-60)"
  - "Wächter: clientId im Handbuch, Exit-Tabelle Handbuch == Executor, Bibliotheksname nicht im Handbuch"
affects: [02-05, 02-06]
tech-stack:
  added: []
  patterns:
    - "FileHandler am Root-Logger, nur der eigene Handler wird ersetzt/geschlossen"
    - "Atomares Schreiben mit Validierung der Temp-Datei vor os.replace, danach Gegenprobe am Ziel"
    - "Fehlerabbildung: eine Logzeile + eine Konsolenzeile pro Exit-Code, Traceback nur in der Datei"
key-files:
  created:
    - scripts/ibkr_executor.py
    - tests/test_ibkr_executor.py
    - scripts/IBKR_EXECUTION.md
  modified:
    - tests/test_ibkr_isolation.py
decisions:
  - "write_portfolio_atomic(ctx, out, *, check=None): load_portfolio prüft die Temp-Datei vor dem os.replace, eine ungültige Datei ersetzt also nie die vorhandene; danach zusätzlich die Gegenprobe am Ziel wie im Plan"
  - "Schreib-/Validierungsfehler werden zu OutputError gebündelt (ibkr-state=OUTPUT_INVALID, Exit 1); so fängt main nicht pauschal jedes OSError/ValueError"
  - "run_account meldet über progress['connected'], ob eine Sitzung stand; unerwartete Fehler werden daraus zu Exit 3 bzw. 1"
  - "Tests filtern pytests eigenen devnull-FileHandler (_pytest.logging._FileHandler) aus der Root-Handler-Liste"
metrics:
  duration: "ca. 30 min"
  completed: 2026-10-12
  tasks: 3
  files: 4
---

# Phase 2 Plan 04: Executor-Kommando `account`, Exit-Code-Tabelle und Handbuch-Anfang Summary

`scripts/ibkr_executor.py account --out PATH` liest die `.env` über einen festen Pfad, prüft Port, Konto und Paper-Modus vor jeder Verbindung und verbindet über den Adapter. Danach prüft es Paper-Guard und Liveness, liest Positionen und Cash frisch und schreibt nach dem Trennen ein `PortfolioContext`-JSON. Das Schreiben ist atomar: Die Temp-Datei wird vor dem Verschieben von `load_portfolio()` geprüft, danach folgt eine Gegenprobe am Ziel. Jeder Fehlerpfad endet mit einem benannten Exit-Code, einer `ibkr-state=`-Logzeile und genau einer Konsolenzeile, nie mit einem Traceback auf der Konsole. Dazu kommt der Anfang von `scripts/IBKR_EXECUTION.md` mit clientId 20001, Exit-Tabelle, Zuständen, Schreibsperre und Read-Only-Protokoll.

## Tasks

| Task | Name | Commits | Dateien |
| ---- | ---- | ------- | ------- |
| 1 | Executor-Gerüst: Exit-Codes, `.env`, Konfigprüfung, UTF-8-Logdatei | 58ed50f (RED), 294ec58 (GREEN) | scripts/ibkr_executor.py, tests/test_ibkr_executor.py |
| 2 | `account`-Ablauf: Guard→8, Gateway→3, Snapshot→atomares JSON→Gegenprobe | 8f22994 (RED), ff23bd7 (GREEN) | scripts/ibkr_executor.py, tests/test_ibkr_executor.py |
| 3 | Betriebshandbuch und clientId-/Exit-Tabellen-Wächter | 7fc2b63 | scripts/IBKR_EXECUTION.md, tests/test_ibkr_isolation.py |

## TDD Gate Compliance

- Task 1: RED 58ed50f scheiterte an der Collection, weil `scripts/ibkr_executor.py` noch fehlte. GREEN 294ec58 brachte 21 grüne Tests und einen strikten `xfail` (Passwort-Test mit Fake-Broker, „account flow lands in task 2“).
- Task 2: RED 8f22994 mit 15 roten `TestAccount`-Tests gegen den Platzhalter. GREEN ff23bd7 macht alle 37 grün; der `xfail` ist entfernt (`grep -c xfail` = 0).
- Ein REFACTOR-Commit war nicht nötig.

## Nachweis je Anforderung / Kriterium

- **Kriterium 1 / REQ-IBKR-11** (JSON, das `load_portfolio` annimmt): `test_account_writes_portfolio_that_load_portfolio_accepts` läuft mit Exit 0. Ergebnis: `cash == 1005459.44`, `currency == "EUR"`, genau AAPL mit 3 Stück und `average_price is None`, keine `*.tmp`, `disconnect` aufgerufen, eine stdout-Zeile. `test_account_json_contains_only_schema_fields` zeigt: Die JSON-Schlüssel sind ⊆ `{cash, currency, positions}`, und `as_of=` steht nur im Log.
- **Fremdwährungsregel:** `test_foreign_currency_average_price_is_dropped`: Bei AAPL/USD ist der Preis `None`, mit einer WARNING-Zeile, die AAPL, USD und EUR nennt. SAP/EUR behält 120.0 und bekommt keine Warnung. Zusätzlich `test_non_stock_position_keeps_no_price`: FUT nutzt `local_symbol` und hat keinen Preis.
- **Kriterium 2 / REQ-IBKR-04** (Exit 8): Bei `["DU0000001"]` und bei der Obermenge `["DUQ634065","DU0000001"]` endet der Lauf mit Exit 8. `disconnect` wird aufgerufen, keiner der Aufrufe `placeOrder`/`cancelOrder`/`reqGlobalCancel`/`exerciseOptions`/`whatIfOrder` kommt vor, es entsteht keine `--out`-Datei, und das Log enthält `ACCOUNT_GUARD_VIOLATED` sowie `DU0000001`. `test_existing_out_file_survives_a_failed_run` zeigt: Eine vorhandene Datei bleibt unverändert.
- **Kriterium 3 / REQ-IBKR-09** (Exit 3/20, kein Traceback):
  - `ConnectionRefusedError` führt zu Exit 3. Das Log enthält `GATEWAY_UNREACHABLE`, `502` und „Gateway nicht erreichbar“; stderr hat genau eine Zeile ohne `Traceback`.
  - 326 + Timeout führt zu `CLIENT_ID_IN_USE`, eine hängende Probe zu `PROBE_TIMEOUT`. Beide enden mit Exit 3 und ohne Datei.
  - Ein `RuntimeError` in `positions()` endet ebenfalls mit Exit 3. Der Traceback steht nur in der Logdatei, stderr hat eine Zeile.
- **REQ-IBKR-55** (Exit-Tabelle): Es gibt zehn disjunkte Konstanten 0..8 und 20 (`grep -c "^EXIT_[A-Z_]* = "` = 10). Die Docstring-Tabelle wird per Regex gegengeprüft, die Handbuchtabelle per `test_handbook_exit_table_matches_executor`.
- **REQ-IBKR-05 / D-06** (Settings): Fehlende oder leere `IBKR_HOST`/`IBKR_PORT`/`IBKR_ACCOUNT_ID` und eine fehlende `.env` führen zu Exit 20. Log und stderr nennen dabei nur die Namen der Variablen. `IBKR_PORT=abc`, `70000`, `IBKR_ACCOUNT_ID=U1234567` und `IBKR_TRADING_MODE=live` führen zu Exit 1, und die Broker-Fabrik wird nie aufgerufen. Das Sollkonto kommt aus `EXPECTED_ACCOUNT`. `IBKR_PASSWORD`/`IBKR_USERNAME` werden nicht übernommen (`test_password_is_never_read_or_logged`, mit `s3cr3t-Ü`).
- **REQ-IBKR-08** (clientId): 20001 steht im Handbuch samt Begründung; der Wächter prüft `EXECUTOR_CLIENT_ID > 9999`.
- **REQ-IBKR-03** (read-only): Der Executor hat keinen Schreibpfad. Die Guard-Tests prüfen null Schreibaufrufe. Das Handbuch dokumentiert die Sperre und den Gateway-Schalter (Marker 321, Tabelle mit der Zeile vom 2026-10-11 20:27).
- **Logging:** Die Logdatei ist UTF-8 mit absolutem Pfad in der ersten Zeile, und Umlaute überstehen den Roundtrip. Es gibt einen FileHandler am Root und keinen `StreamHandler` und kein `propagate = False`. Ein fremder Logger (`thirdparty.client`) landet in der Datei, stderr bleibt leer. Nach `close_logging()` lässt sich die Datei löschen (Windows).
- **Kriterium 4:** `git grep -l -w ib_async -- 'tradingagents/*.py' 'scripts/*.py' 'cli/*.py'` liefert nur `scripts/ibkr_broker.py`, ebenso `git grep -l -w ib_async -- tradingagents scripts` (inkl. Handbuch).

## Fail-closed-Negativkontrollen (REQ-IBKR-66)

Jede Schutzmaßnahme hat einen Test, in dem sie auslösen muss:

| Schutz | Test |
|---|---|
| Guard (Exit 8) | `test_guard_violation_exits_8_without_writes[foreign/superset]` |
| fehlende Settings (Exit 20) | `test_missing_credentials_exit_20[4 Fälle]`, `test_missing_env_file_exit_20` |
| Gateway nicht erreichbar (Exit 3) | `test_unreachable_gateway_exits_3_with_named_state`, `test_client_id_in_use_exits_3`, `test_unhealthy_session_exits_3` |
| JSON-Gegenprobe | `test_failed_cross_check_exits_1`: `load_portfolio` erzwungen ungültig, Ergebnis Exit 1, `OUTPUT_INVALID`, keine Ziel- und keine Temp-Datei |
| nicht schreibbares Ziel | `test_unwritable_out_exits_1_and_leaves_no_temp` (`PermissionError` wird nicht geschluckt) |
| fehlendes Extra | `test_missing_extra_exits_1_with_hint` |

## Sicherheit beim Testen

Kein Test und kein Aufruf hat das echte Gateway auf 127.0.0.1:7497 erreicht. Alle `main`-Aufrufe bekommen `--env-file` und `--log-file` in `tmp_path` und eine injizierte `broker_factory`; der echte `IbkrBroker` läuft dabei immer gegen `FakeIB`. Die autouse-Fixture `block_real_ib_connect` sperrt den Connect der Bibliothek. `scripts/ibkr_executor.py account` wurde nicht ohne Fake ausgeführt, und die echte `.env` wurde weder gelesen noch ausgegeben. Der echte Lauf ist der Operator-Checkpoint in Plan 02-05.

## Verifikation

```
$ .venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py -q
104 passed
$ .venv/Scripts/python.exe -m pytest tests/test_ibkr_executor.py -q -k "writes_portfolio or guard or unreachable or client_id"
5 passed, 32 deselected
$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
$ git grep -l -w ib_async -- 'tradingagents/*.py' 'scripts/*.py' 'cli/*.py'
scripts/ibkr_broker.py
$ .venv/Scripts/python.exe -m pytest -q
1 failed, 1494 passed, 4 skipped, 1 deselected, 20 warnings, 101 subtests passed
  FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
```

Der eine Fehlschlag ist der bekannte Windows-Umgebungsfehler (yfinance-Cache) und bestand schon vor diesem Plan. Gegenüber der Basis (1454 passed) sind 40 Tests hinzugekommen: 37 in `tests/test_ibkr_executor.py` und 3 in `tests/test_ibkr_isolation.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test-Bug] pytest hängt einen eigenen FileHandler an den Root-Logger**
- **Found during:** Task 1 GREEN
- **Issue:** pytests Logging-Plugin hängt während jedes Tests einen `_pytest.logging._FileHandler` (devnull) an den Root-Logger. Die Prüfung „genau ein FileHandler“ hätte deshalb nie grün werden können.
- **Fix:** Der Test-Helfer `_own_file_handlers()` ignoriert Handler aus `_pytest.logging`. Der Code ist unverändert und entfernt weiterhin nur den eigenen Handler.
- **Commit:** 294ec58

**2. [Rule 2 - Fail-closed] Validierung der Temp-Datei vor dem Ersetzen**
- **Found during:** Task 2
- **Issue:** Laut Plan läuft die Gegenprobe erst nach `os.replace`. Eine Datei, die nicht validiert, hätte die vorhandene, gute Datei dann schon ersetzt.
- **Fix:** `write_portfolio_atomic(..., check=load_portfolio)` prüft die Temp-Datei vor dem Verschieben. Die Gegenprobe am Ziel bleibt wie geplant. Der Fehler wird als `OutputError` gemeldet: `ibkr-state=OUTPUT_INVALID`, Exit 1.
- **Commit:** ff23bd7

**3. [Rule 2 - Negativkontrollen] Zusätzliche Tests**
- Neu sind `test_failed_cross_check_exits_1`, `test_unwritable_out_exits_1_and_leaves_no_temp`, `test_non_stock_position_keeps_no_price`, `test_repeated_setup_keeps_one_file_handler`, `test_missing_env_file_exit_20`, `test_account_id_must_match_the_code_constant` und `test_default_env_file_is_the_repo_root`. Damit hat jede Schutzmaßnahme einen Test, in dem sie auslösen muss (REQ-IBKR-66).

**4. Handbuch-Befehl für den Paper-Lauf ergänzt:** `daily_paper_run.py` braucht zwingend `--tickers`, `--max-cost`, `--out` und `--state`. Der Befehlsblock nennt deshalb einen vollständigen Aufruf statt nur `--portfolio`.

**5. Kleinigkeiten:** Im Test für das fehlende Extra nennt die `ModuleNotFoundError`-Meldung die Bibliothek nicht beim Namen; geprüft wird nur der Installationshinweis. Der Exit-Tabellen-Wächter prüft strenger als geplant, nämlich `| <wert> | \`<NAME>\` |` statt nur `| <wert> |`.

## Known Stubs

Keine. Die Exit-Codes 2/4/5/6/7 sind absichtlich für spätere Phasen reserviert und im Docstring und im Handbuch so markiert.

## Threat Flags

Keine neue Angriffsfläche über das Threat-Register hinaus. T-02-13 bis T-02-18 sind wie geplant mitigiert und je mit Test belegt; T-02-16 ist durch die Validierung der Temp-Datei sogar strenger umgesetzt.

## Self-Check: PASSED

- FOUND: scripts/ibkr_executor.py, tests/test_ibkr_executor.py, scripts/IBKR_EXECUTION.md, tests/test_ibkr_isolation.py
- FOUND commits: 58ed50f, 294ec58, 8f22994, ff23bd7, 7fc2b63
