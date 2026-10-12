---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 02
subsystem: ibkr-adapter
tags: [ibkr, adapter, paper-guard, write-barrier, liveness, read-only, fake-ib]
requires:
  - "02-01: Extra `ibkr` (ib_async 2.1.0) im .venv, tests/test_ibkr_isolation.py"
provides:
  - "scripts/ibkr_broker.py: IbkrBroker (connect, positions, health), IbHandles, AccountSnapshot, BrokerPosition, Health, ReadOnlyViolation, AccountGuardViolation, GatewayUnavailable, state_for_code, STATE_BY_CODE, INFO_CODES, EXPECTED_ACCOUNT, EXECUTOR_CLIENT_ID, PROBE_CON_ID"
  - "tests/ibkr_fakes.py: FakeIB, FakeEvent, FakeContract, position, account_value, make_handles, load_broker, session_loop, block_real_ib_connect"
  - "Isolationswächter: genau ein Importort der Client-Bibliothek, <= 10 öffentliche Methoden, keine orderId-Literale"
affects: [02-03, 02-04, 02-05, 02-06]
tech-stack:
  added: []
  patterns:
    - "Injizierbare ib_factory + Lazy-Import der Bibliothek im Funktionskörper"
    - "Schreibsperre per setattr auf ib.client vor connectAsync"
    - "Jeder Request über _call (asyncio.wait_for in run_until_complete)"
    - "Session-skopierte Event-Loop-Fixture vor der funktionsskopierten Netzsperre"
    - "Modul einmal unter dem Namen ibkr_broker in sys.modules laden (geteilte Ausnahmeklassen)"
key-files:
  created:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
  modified:
    - tests/test_ibkr_isolation.py
decisions:
  - "make_handles(fake) liefert die ib_factory (Callable, das IbHandles zurückgibt), damit es direkt als ib_factory= übergeben werden kann"
  - "health() und positions() bilden auch ConnectionError auf NOT_CONNECTED ab (zusätzlich zu Timeouts), damit ein gestorbener Socket keinen Traceback wirft"
  - "connect() trennt auch bei unerwarteten Ausnahmen (except BaseException: _disconnect(); raise)"
metrics:
  duration: "ca. 25 min"
  completed: 2026-10-12
  tasks: 2
  files: 4
---

# Phase 2 Plan 02: IBKR-Adapter mit Schreibsperre, Paper-Guard, Probe-Liveness und frischem Kontolesen Summary

Einziger IBKR-Adapter `scripts/ibkr_broker.py`: verbindet `readonly=True` mit festem `clientId` 20001 und `StartupFetchNONE`, sperrt die vier Schreibaufrufe auf `ib.client` vor dem ersten Byte, trennt bei jeder Kontoliste außer exakt `["DUQ634065"]`, meldet Liveness nur bei echter Probe-Antwort (conId 265598) und liest Positionen und `TotalCashValue` bei jedem Aufruf frisch — alles unter `asyncio.wait_for`, alles gegen ein Fake-IB getestet, echte Verbindungen in den Tests gesperrt.

## Tasks

| Task | Name | Commits | Dateien |
| ---- | ---- | ------- | ------- |
| 1 | Fakes + Adapter-Gerüst mit Schreibsperre, Paper-Guard und Zustandstabelle | ed8c868 (RED), 35cb648 (GREEN) | tests/ibkr_fakes.py, tests/test_ibkr_broker.py, scripts/ibkr_broker.py |
| 2 | Liveness-Probe, frisches Konto-Lesen und Isolations-Wächter | 922203c (RED), 5f8f1a9 (GREEN) | tests/test_ibkr_broker.py, tests/test_ibkr_isolation.py, scripts/ibkr_broker.py |

TDD-Gates: Task 1 RED scheiterte an der Collection (`scripts/ibkr_broker.py` fehlte), Task 2 RED mit 17 roten Tests (fehlende `health`/`positions`, Methodenmenge `{connect}` ≠ `{connect, positions, health}`). Beide GREEN-Commits danach vollständig grün. Kein REFACTOR-Commit nötig.

## Nachweis je Anforderung

- **REQ-IBKR-03** (nur Paper, `readonly=True`): `connectAsync(..., readonly=True, clientId=20001, fetchFields=StartupFetchNONE)`; weil `readonly=True` in 2.1.0 nicht sperrt (ib.py:780-813, 2057-2063), setzt `_arm_write_barrier` `placeOrder`/`cancelOrder`/`reqGlobalCancel`/`exerciseOptions` vor `connectAsync` auf eine `ReadOnlyViolation`-Funktion. Belegt am Fake (`barrier_armed_at_connect`) und am echten `IB()`-Objekt ohne Verbindung (`ib.placeOrder(...)`, `ib.reqGlobalCancel()` → `ReadOnlyViolation`). Kein `place`/`preview`/`cancel_all` im Adapter, auch nicht als Stub.
- **REQ-IBKR-04** (Paper-Guard): exakter Listenvergleich gegen die Code-Konstante `EXPECTED_ACCOUNT = "DUQ634065"` (kein `.env`, kein `os.environ`); Fremdkonto, Obermenge und leere Liste → ERROR-Log `ibkr-state=ACCOUNT_GUARD_VIOLATED accounts_seen=[...]`, `disconnect`, `AccountGuardViolation(accounts_seen)`, null Schreibaufrufe.
- **REQ-IBKR-07** (ein Adapter, ≤ 10 Methoden): AST-Test findet genau `["scripts/ibkr_broker.py"]` als Importeur der Client-Bibliothek über `tradingagents/`, `cli/`, `scripts/`; `git grep -l -w ib_async -- "tradingagents/*.py" "cli/*.py" "scripts/*.py"` → genau `scripts/ibkr_broker.py`; öffentliche Methoden genau `{connect, positions, health}`.
- **REQ-IBKR-08** (fester `clientId`, keine Order-IDs): `EXECUTOR_CLIENT_ID = 20001` außerhalb 0..9999; Quelltext ohne `orderId=`/`.orderId =` (Test).
- **REQ-IBKR-09** (benannte Zustände, echte Liveness): `STATE_BY_CODE` mit allen Zeilen aus Research Muster 5, `state_for_code` mit Default `UNKNOWN`, 2104/2106/2158 auf INFO; 502/504/507/326/Timeout aus Ausnahmen abgebildet. `health()` pumpt erst einen Loop-Tick (`asyncio.sleep(0)`), prüft dann `isConnected`, 1100/2110/1300 (ohne Probe), sonst Probe — „Socket oben, Session tot“ → `PROBE_TIMEOUT` in < 1 s; ein in der Loop wartendes 1100 wird als `CONNECTIVITY_LOST` erkannt.
- **REQ-IBKR-12** (frisch lesen): `positions()` ruft bei jedem Aufruf `reqPositionsAsync` und `accountSummaryAsync(EXPECTED_ACCOUNT)` (Test zählt je 2 bei 2 Aufrufen; der Fake-Cache `positions()` würde `AssertionError` werfen); Filter Konto + Menge ≠ 0; Cash = genau eine `TotalCashValue`-Zeile mit Währung, sonst `SNAPSHOT_INCOMPLETE`. Keine Order-Abfragen.
- **REQ-IBKR-62** (Timeout auf jedem API-Aufruf, benannter Fehlerzustand): Jeder Bibliotheksaufruf läuft über `_call` → `asyncio.wait_for` mit endlichem Timeout (Connect `connect_timeout + 5`, Requests `REQUEST_TIMEOUT_S = 10`, Probe `PROBE_TIMEOUT_S = 5`). Ablauf wird benannt: `CONNECT_TIMEOUT` bzw. `CLIENT_ID_IN_USE` (wenn 326 gesehen), `REQUEST_TIMEOUT`, `PROBE_TIMEOUT`. Tests mit hängender Probe und hängenden Positionen enden in < 1 s.
- **REQ-IBKR-67** (Fehlercodes gemessen, nicht angenommen): Der Read-Only-Marker ist **321** (`READ_ONLY_API`), wie in `.planning/ibkr-konto-befund.md` (Korrektur 1: Gateway 10.50.1 liefert 321 statt des dokumentierten 10015) gemessen; der Kommentar in `STATE_BY_CODE` zitiert den Befund. 10015 bleibt als `TRADING_NOT_ALLOWED` nur der Vollständigkeit halber in der Tabelle. 502/504/507 sind als „kein Event in ib_async“ markiert und werden aus den gemessenen Ausnahmen (Research Pitfall 3, am 2.1.0-Quelltext geprüft) abgeleitet.

## Sicherheit beim Testen

Kein Test und kein Skript hat eine echte Verbindung aufgebaut. Alle Adapter-Tests nutzen `make_handles(FakeIB(...))`; die autouse-Fixture `block_real_ib_connect` ersetzt `ib_async.IB.connectAsync` und `ib_async.client.Client.connectAsync` durch eine sofort scheiternde Funktion, belegt durch `test_real_connect_is_blocked_in_this_module` (Port 1, nie 7497).

## Verifikation

```
$ .venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_isolation.py -q
64 passed in 1.20s
$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
$ git grep -l -w ib_async -- "tradingagents/*.py" "cli/*.py" "scripts/*.py"
scripts/ibkr_broker.py
$ .venv/Scripts/python.exe -m pytest -q
1 failed, 1446 passed, 4 skipped, 1 deselected, 20 warnings, 101 subtests passed in 24.09s
  FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
```

Der eine Fehlschlag ist der bekannte, bereits vor diesem Plan bestehende Windows-Umgebungsfehler (siehe 02-01-SUMMARY), nicht durch diesen Plan verursacht. Gegenüber 02-01 (1386 passed) sind 60 Tests hinzugekommen.

Grep-Akzeptanzkriterien: kein Bibliotheksimport auf Modulebene, genau ein `from ib_async import`; `readonly=True` im `connectAsync`-Aufruf; keine `def place`/`def preview`/`def cancel_all`/`orderId=`; kein `os.environ`/`dotenv`; keine `reqAllOpenOrders`/`reqCompletedOrders`/`reqExecutions`/`.positions()`/`accountSummary()`; `TotalCashValue` vorhanden, `BuyingPower` nicht im Adapter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Robustheit] ConnectionError in `health()`/`positions()` benannt**
- **Found during:** Task 2
- **Issue:** Ein zwischen Connect und Request gestorbener Socket lässt die Bibliothek `ConnectionError("Not connected")` werfen — der Plan nannte dafür in `health`/`positions` nur Timeouts.
- **Fix:** `health()` → `Health(False, "NOT_CONNECTED")`, `positions()` → `GatewayUnavailable("NOT_CONNECTED", 504)` über den Helfer `_request`.
- **Files modified:** scripts/ibkr_broker.py
- **Commit:** 5f8f1a9

**2. [Rule 2 - Sicherheit] Trennen auch bei unerwarteten Ausnahmen im Connect**
- **Found during:** Task 1
- **Fix:** `except BaseException: self._disconnect(); raise` nach den benannten Fällen, damit keine halb offene Sitzung zurückbleibt.
- **Commit:** 35cb648

**3. Kleine Schnittstellenpräzisierung:** `make_handles(fake)` liefert die Fabrik (Callable → `IbHandles`), nicht das `IbHandles` selbst — passend zum Key-Link „`make_handles(FakeIB(...))` als `ib_factory`“. Die Guard-Tests sind als ein parametrisierter Test (`foreign`/`superset`/`empty`) statt drei Einzeltests umgesetzt; zusätzlich Tests für 507/504/OSError, Kontextmanager und nicht verbundenen Zustand.

`ruff format` wurde auf die neuen Dateien angewendet (kein Gate, nur Konsistenz).

## Known Stubs

Keine. `place`/`preview`/`cancel_all` fehlen absichtlich (D-01, D-08), nicht als Stub.

## Threat Flags

Keine neue Angriffsfläche über das Threat-Register hinaus (T-02-04 bis T-02-09 sind wie geplant mitigiert).

## Self-Check: PASSED

- FOUND: scripts/ibkr_broker.py, tests/ibkr_fakes.py, tests/test_ibkr_broker.py, tests/test_ibkr_isolation.py
- FOUND: Commits ed8c868, 35cb648, 922203c, 5f8f1a9
