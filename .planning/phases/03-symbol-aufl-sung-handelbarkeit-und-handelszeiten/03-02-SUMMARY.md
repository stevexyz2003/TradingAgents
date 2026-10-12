---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
plan: 02
subsystem: ibkr-adapter
tags: [ibkr, adapter, contract-resolution, delayed-market-data]
requires: []
provides:
  - "IbkrBroker.search_contract(spec) -> tuple[ContractInfo, ...]"
  - "IbkrBroker.contract_details(con_id, exchange) -> tuple[ContractInfo, ...]"
  - "reqMarketDataType(3) nach dem Paper-Guard"
affects: [03-03, 03-05]
key-files:
  modified:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
    - tests/test_ibkr_isolation.py
requirements-completed: [REQ-IBKR-26, REQ-IBKR-29, REQ-IBKR-30]
duration: ~25min
completed: 2026-10-12
---

# Phase 3 Plan 02: Adapter-Lesemethoden und Delayed-Marktdaten Summary

Der Adapter kann Contracts per Symbolsuche (`returnAll=True`, 0/1/n Treffer) und per conId+exchange (inkl. Sitzungsfelder) lesen, setzt nach dem Paper-Guard `reqMarketDataType(3)` und loggt Delayed-Codes auf INFO.

## Ergebnis

- `ContractInfo` (frozen, broker-neutral), `search_contract`, `contract_details`; beide über den gemeinsamen Helfer `_read` (Timeout, offenes Link-Ereignis vor der Anfrage und Link-Ereignis während der Anfrage führen zu `GatewayUnavailable`; ohne Sitzung `NOT_CONNECTED`). `search_contract` baut den Contract pro Aufruf frisch im Lambda.
- `STATE_BY_CODE`: `10167 -> MARKET_DATA_DELAYED`, `200 -> CONTRACT_NOT_FOUND`; 10089/10090 unverändert; 154 bewusst nicht gemappt. `INFO_CODES` enthält 10089, 10090, 10167.
- `connect()` ruft `reqMarketDataType(3)` genau einmal nach dem Guard auf (nie bei Guard-Verletzung).
- Schreibsperre unverändert; Tests belegen, dass Kopf-Ids 9 und 59 (gegen installierten ib_async-Quelltext) durchgelassen werden.
- Fakes: `FakeContract` erweitert, `stk_contract`, `contract_detail`, `qualifyContractsAsync`, `reqContractDetailsAsync` je conId, `reqMarketDataType`.
- Isolationstest: genau 5 öffentliche Methoden.

## Commits

- 68c3585 test(03-02): Tests und Fakes Task 1 (RED)
- b61315e feat(03-02): Delayed-Typ, Codes, INFO (GREEN)
- d0c27eb test(03-02): Tests Task 2 (RED)
- 0e56a9f feat(03-02): search_contract / contract_details (GREEN)

## Verifikation

- `pytest tests -k ibkr`: 176 passed.
- `ruff check .`: All checks passed (selbst ausgeführt).
- `ruff format --check` meldet viele Dateien repoweit (CRLF im Arbeitsbaum, vorbestehend, nicht Teil dieses Plans).

## Deviations from Plan

- Worktree-Basis stand auf 1394a3f statt dem erwarteten Commit; gemäß Anweisung auf efdb93f zurückgesetzt.
- Der Fake merkt Details-Aufrufe in `details_calls` (nicht im Plan benannt), damit Tests conId/exchange prüfen können. Sonst keine Abweichungen.

## Known Stubs

Keine.

## Self-Check: PASSED

Alle vier Commits vorhanden, Tests und Lint grün, STATE.md/ROADMAP.md unverändert.
