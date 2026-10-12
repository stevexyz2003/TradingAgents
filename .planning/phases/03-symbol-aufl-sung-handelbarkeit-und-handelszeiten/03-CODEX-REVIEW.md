---
source: codex exec (codex-cli 0.137.0, sandbox read-only)
scope: committed HEAD 8b2593c
date: 2026-10-12
note: static analysis only; the Codex sandbox blocked pytest. The orchestrator ran the full suite on the same HEAD: 2036 passed, 4 skipped (known env failure deselected).
---

# Phase 03, Codex validation audit

**Hinweis zur Ausführung:** Der erlaubte Pytest-Befehl wurde vom Sandbox-Policy-Filter blockiert, bevor Python starten konnte. Ich habe daher statisch geprüft. Kein Netzwerk, kein Gateway, keine Dateiänderung.

**Requirement-To-Test Map**

| Requirement / Kriterium | Testdatei::Testname(n) | Status | Grund |
|---|---|---:|---|
| REQ-IBKR-26 delayed Marktdaten / 10089/10090/10167 INFO | `tests/test_ibkr_broker.py::test_market_data_type_is_set_once_after_the_guard`, `::test_market_data_type_is_not_sent_on_a_guard_violation`, `::test_state_map`, `::test_market_data_codes_log_at_info` | COVERED | `reqMarketDataType(3)` nach Guard in `scripts/ibkr_broker.py:643`; INFO-Codes in `scripts/ibkr_broker.py:139`. |
| REQ-IBKR-27 Roh-Ticker-Pfad ohne `normalize_symbol()` | `tests/test_ibkr_contracts.py::test_symbols_resolver_and_vendor_normalizer_are_separate_paths`, `tests/test_ibkr_isolation.py::test_resolver_does_not_use_the_vendor_normalizer` | COVERED | Verhaltenstest assertet `XAUUSD+ -> CMDTY/XAUUSD` und Vendor-Normalizer separat `GC=F`; Isolationstest verhindert Import. |
| REQ-IBKR-28 Allow-List `{STK}`, nicht gemappt/nicht erlaubt ohne Durchprobieren | `tests/test_ibkr_contracts.py::test_classify_non_stock_is_not_allowed`, `::test_resolve_all_local_rejections_need_no_broker`, `tests/test_ibkr_resolve.py::test_locally_rejected_tickers_need_no_env_and_no_gateway` | COVERED | `classify()` rejectet exakt und lokal in `scripts/ibkr_contracts.py:125-139`; `needs_broker()` nur für lokal OK in `scripts/ibkr_contracts.py:614-616`. |
| REQ-IBKR-29 Eindeutigkeit, 0/n Treffer, Kandidatenliste im Log | `tests/test_ibkr_broker.py::test_search_contract_many_matches`, `tests/test_ibkr_contracts.py::test_resolve_ambiguous_logs_all_candidates_in_one_record`, `::test_resolve_ambiguous_with_21_candidates_is_not_truncated`, `tests/test_ibkr_resolve.py::test_ambiguous_candidates_all_land_in_the_log` | COVERED | Resolver erzwingt `len(cands)==1`; ambiguous loggt `_candidate_line()` in `scripts/ibkr_contracts.py:713-719` und `:804-810`. |
| REQ-IBKR-30 Persistenz, Gegenprobe, Drift | `tests/test_ibkr_contracts.py::test_persist_roundtrip_and_exact_schema`, `::test_history_lines_after_two_commits`, `::test_commit_with_expected_bytes_aborts_on_concurrent_change`, `::test_resolve_second_run_checks_by_conid_and_cross_checks_by_search`, `::test_resolve_manipulated_conid_is_drift_and_others_continue`, `tests/test_ibkr_resolve.py::test_init_creates_the_file_and_history`, `::test_second_run_reads_by_con_id_and_changes_nothing`, `::test_drift_is_reported_and_the_file_stays` | COVERED | Persistenz und Driftpfad sind in `scripts/ibkr_contracts.py:512-563`, `:785-831`; `run_resolve()` schreibt erst nach Disconnect in `scripts/ibkr_executor.py:621-642`. |
| REQ-IBKR-31 Handelbarkeit via `validExchanges`/`orderTypes` | `tests/test_ibkr_contracts.py::test_check_tradable_accepts_a_normal_stock`, `::test_check_tradable_rejects_fail_closed`, `tests/test_ibkr_resolve.py::test_value_only_listing_is_not_tradable` | PARTIAL | Funktional gedeckt (`scripts/ibkr_contracts.py:149-164`, `:841-844`), aber die Anforderungsänderung nach D-19 ist laut `03-VERIFICATION.md` noch operatorseitig offen. |
| REQ-IBKR-37 Liquid-hours, Puffer, kein harter Zeitcode, Halt verhindert Order | `tests/test_ibkr_contracts.py::test_parse_*`, `::test_buffer_boundaries_are_exact`, `::test_closed_day_is_closed_not_session_unknown`, `::test_parser_agrees_with_ib_async_on_new_format`, `tests/test_ibkr_isolation.py::test_no_hard_coded_trading_times_in_execution_code` | PARTIAL | Sitzungsteil gedeckt (`scripts/ibkr_contracts.py:266-330`); Halt-Teil ist explizit nicht Phase-3-implementiert: `HALTED` ist “Never set in phase 3” in `scripts/ibkr_contracts.py:58-60`. |
| SC1 echter Init-Lauf AAPL/MSFT/NVDA | `03-06-SUMMARY.md`/Handbuch-Protokoll, nicht Unit-Test | MANUAL | Braucht Paper-Gateway; dokumentiert, aber in diesem Audit nicht wiederholbar. |
| SC2 Sperr-Ticker ohne Gateway | Tests siehe REQ-28 | COVERED | Fake/CLI-Test assertet keine Env/Gateway-Nutzung. |
| SC3 künstliche Mehrdeutigkeit | Tests siehe REQ-29 | COVERED | Fake-Broker mit 21 Kandidaten, Log nicht gekürzt. |
| SC4 manipuliertes `conId` | Tests siehe REQ-30 | COVERED | Drift mit unveränderter Datei assertet. |
| SC5 separater Normalizer-Pfad | Tests siehe REQ-27 | COVERED | Verhalten + Import-Guard. |
| SC6 Sessionparser gegen `ib_async` | `tests/test_ibkr_contracts.py::test_parser_agrees_with_ib_async_on_new_format`, `::test_old_format_is_rejected_by_ib_async_but_parsed_here` | COVERED | Test ist real gegen installierte Library konditional via `pytest.importorskip`. |
| SC7 keine harten Handelszeiten | `tests/test_ibkr_isolation.py::test_no_hard_coded_trading_times_in_execution_code` | COVERED | Statischer Guard über `scripts/ibkr_*.py`. |
| SC8 delayed Marktdaten / erwartete Codes | Tests siehe REQ-26 | COVERED | 10167 real laut Summary nicht beobachtet, aber Mapping/Loglevel testet Codepfad. |
| 03-01 Must-haves: Tabelle, classify, Handelbarkeit, Identität, Parser | `tests/test_ibkr_contracts.py` Tabelle/Parser/Identity-Tests | COVERED | Assertions prüfen Verhalten, nicht nur Namen. |
| 03-02 Must-haves: Adapter-Lesemethoden und delayed data | `tests/test_ibkr_broker.py` search/details/market-data Tests | COVERED | Prüft Aufrufe und Fake-Ergebnisse. |
| 03-03 Must-haves: Persistenz, History, Resolver-Kette | `tests/test_ibkr_contracts.py` Persistenz- und Resolver-Tests | COVERED | Deckt atomar, History, Drift, Ambiguous, Session. |
| 03-04 Must-haves: statische Guards, Req-Änderungen | `tests/test_ibkr_isolation.py`; Doku-Greps in Plan | PARTIAL | Guards gedeckt; Operator-Abnahme der Req-Änderungen offen. |
| 03-05 Must-haves: `resolve` CLI, Exit 2, `--out` | `tests/test_ibkr_resolve.py` | COVERED | Prüft CLI-Pfade mit FakeIB und tmp paths. |
| 03-06 Must-haves: Handbuch + erster echter Lauf | `tests/test_ibkr_isolation.py::test_handbook_documents_resolve`, echte Läufe laut Summary | MANUAL | Gateway-Läufe und Operator-Approval sind nicht automatisiert reproduzierbar. |

**Gaps**

| Gap | Vorgeschlagener Test |
|---|---|
| REQ-IBKR-37 Halt-Teil in Phase 3 nicht gedeckt | `tests/test_ibkr_contracts.py::test_resolve_rejects_halted_contract_signal`: Stub/Fake um Halt-Signal erweitern, `resolve_all()` muss `state == halted`, `rejected is True`, keine OK-Result-Zeile liefern. Alternativ Phase-3-Scope offiziell reduzieren und nur Phase-4-Test als Abdeckung zählen. |
| Samstagslauf / echtes `liquidHours`-Wochenende offen | `tests/test_ibkr_resolve.py::test_real_saturday_fixture_is_closed_not_unknown`: mit im Repo dokumentiertem realen AAPL-Samstags-`liquidHours`-Fixture über `FakeIB.contract_detail()` assertet Exit 0, `closed`, `next_open`. Live-Gateway bleibt MANUAL. |
| REQ-IBKR-31 / REQ-IBKR-37 Operator-Abnahme fehlt | `tests/test_ibkr_isolation.py::test_phase03_verification_records_required_operator_decisions`: liest `03-VERIFICATION.md` und assertet `accepted_by`/`accepted_at` für beide Abweichungen, sobald entschieden. |
| Audit-Pytest nicht ausgeführt | Sandbox-Policy beheben oder Befehl außerhalb dieses read-only Audits ausführen: `C:/Users/admin/PycharmProjects/TradingEngineX/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_ibkr_contracts.py tests/test_ibkr_broker.py tests/test_ibkr_resolve.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py`. |

**Correctness Findings**

- WARNING: REQ-IBKR-37 ist nicht vollständig erfüllt. `HALTED` ist zwar ein Reject-State, wird aber laut Codekommentar in Phase 3 nie gesetzt (`scripts/ibkr_contracts.py:58-60`). `resolve_all()` prüft nach Handelbarkeit direkt `evaluate_session()` (`scripts/ibkr_contracts.py:841-847`) und hat keinen Halt-Abfragepfad. Szenario: Instrument ist halted, aber `validExchanges/orderTypes` und Session sind OK; Phase 3 liefert `ok`. Keine Order in Phase 3, aber die Phase beansprucht REQ-37 nur teilweise.

- INFO: Keine Evidenz für einen Order-Write-Bypass in den geprüften Pfaden. Die Barriere ersetzt `placeOrder` und verweigert alles ohne `whatIf` bzw. ohne `STK` (`scripts/ibkr_broker.py:424-450`), blockiert `cancelOrder`, `reqGlobalCancel`, `exerciseOptions` (`scripts/ibkr_broker.py:452-459`) und fängt Wire-IDs `{3,4,19,21,58}` über `send`/`sendMsg` ab (`scripts/ibkr_broker.py:469-489`). Tests decken direkte und Wire-Pfade ab (`tests/test_ibkr_broker.py:132`, `:144`, `:156`, `:955`, `:1033`, `:1042`).

- INFO: `resolve` selbst sendet keine Orders. Der Phase-3-Pfad nutzt `search_contract()` und `contract_details()` (`scripts/ibkr_contracts.py:709`, `:731`, `:787-788`), der Adapter ruft dafür `qualifyContractsAsync(..., returnAll=True)` und `reqContractDetailsAsync` (`scripts/ibkr_broker.py:787-832`). `whatIfOrderAsync` existiert erst im Preview-Pfad (`scripts/ibkr_broker.py:856-922`), nicht in `resolve`.

**Verdict:** `nyquist_compliant false`