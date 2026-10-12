---
source: codex exec (codex-cli 0.137.0, sandbox read-only)
scope: committed HEAD 8b2593c
date: 2026-10-12
note: static analysis only; the Codex sandbox blocked pytest. The orchestrator ran the full suite on the same HEAD: 2036 passed, 4 skipped (known env failure deselected).
---

# Phase 04, Codex validation audit

**Hinweis:** Ich konnte pytest nicht ausführen; die Sandbox-Policy hat den Python-Aufruf blockiert. Status unten ist daher statische Nyquist-Abdeckung anhand von Code und Tests am committed HEAD.

**Requirement-to-Test Map**

| Requirement / Kriterium | Test(s) | Status | Grund |
|---|---|---:|---|
| REQ-IBKR-13 paper-log, `TradingMemoryLog`, neuester Eintrag | `tests/test_ibkr_decision.py::test_log_entries_latest_per_ticker_wins`, `::test_log_entries_roundtrip_with_memory_log`, `tests/test_ibkr_paperlog.py::test_fetch_commands_and_env`, `tests/test_ibkr_preview.py::test_only_log_and_summary_paths_are_read` | COVERED | Liest `decision-log.md`, nutzt `TradingMemoryLog`, prüft latest-per-ticker und keine Reports. Code: `scripts/ibkr_executor.py:1092`, `:1122`, `:1159`. |
| REQ-IBKR-14 summary schema | `tests/test_ibkr_decision.py::test_schema_version_other_than_one_raises_schema_error`, `tests/test_paper_summary_contract.py::test_contract_schema_version_matches_producer`, `::test_contract_breaking_change_fails`, `tests/test_ibkr_preview.py::test_an_unknown_schema_version_is_exit_1` | COVERED | Schema-Version und Vertragsbruch werden asserted. Code: `scripts/ibkr_decision.py:179`, `scripts/ibkr_executor.py:1141`. |
| REQ-IBKR-15 state maintenance verify | `tests/test_ibkr_preview.py::test_a_broken_tag_line_is_a_log_finding`, `::test_an_empty_log_is_a_log_finding`, `::test_the_copy_is_byte_equal_with_the_blob` | COVERED | Byte-Kopie und `verify(cache_dir=<temp>, memory_log=<copy>)` werden geprüft. Code: `scripts/ibkr_executor.py:1103`, `:1114`. |
| REQ-IBKR-16 null/REVIEW/status | `tests/test_ibkr_decision.py::test_preconditions_review`, `::test_preconditions_run_not_ok`, `::test_preconditions_signal_null`, `tests/test_ibkr_preview.py::test_review_rating`, `::test_run_failed_for_the_log_date` | COVERED | Eigene Zustände, Exit 2, kein Gatewaykontakt in Preview-Tests. |
| REQ-IBKR-17 Divergenz | `tests/test_ibkr_decision.py::test_divergence_log_version_wins`, `tests/test_ibkr_preview.py::test_log_and_summary_disagree` | COVERED | Assertet `signal-divergence`, Log-Rating bleibt erhalten. |
| REQ-IBKR-18 Reports nicht lesen | `tests/test_ibkr_decision.py::test_schema_extra_fields_are_tolerated_and_report_is_not_exposed`, `tests/test_ibkr_preview.py::test_only_log_and_summary_paths_are_read` | COVERED | `RunRecord` hat kein `report`; gelesene Pfade werden geprüft. |
| REQ-IBKR-19 Freshness | `tests/test_ibkr_decision.py::test_freshness_cases`, `::test_freshness_stale_detail_names_the_closed_session`, `tests/test_ibkr_preview.py::test_a_decision_with_a_closed_session_in_between_is_stale` | COVERED | Geschlossene Sitzung zwischen Trade-Date und Ausführung wird `stale-decision`. |
| REQ-IBKR-20 weekend gap | `tests/test_ibkr_decision.py::test_freshness_cases`, `tests/test_ibkr_preview.py::test_a_closed_market_still_previews` | COVERED | Wochenendlücke bleibt fresh und wird markiert. Code: `scripts/ibkr_decision.py:517`. |
| REQ-IBKR-21 Zielposition / Hold nie Order | `tests/test_ibkr_decision.py::test_preconditions_hold_is_skipped`, `::test_plan_hold_never_orders`, `tests/test_ibkr_preview.py::test_real_branch_hold_with_the_stub_calendar`, `::test_real_branch_hold_with_the_xnys_calendar` | COVERED | Hold endet lokal ohne Gateway. Code: `scripts/ibkr_executor.py:1151`. |
| REQ-IBKR-22 block_qty, keine Preisableitung | `tests/test_ibkr_contracts.py::test_block_qty_*`, `tests/test_ibkr_isolation.py::test_no_market_data_in_execution_path` | COVERED | Feste `block_qty`; keine `reqMktData`/`reqTickers` im Pfad. Code: `scripts/ibkr_contracts.py:80`, `:103`. |
| REQ-IBKR-23 Ziel-Ist-offen / offene Orders | `tests/test_ibkr_decision.py::test_tolerance_band`, `::test_open_order_is_foreign`, `tests/test_ibkr_preview.py::test_within_tolerance_needs_no_preview`, `::test_a_foreign_open_order_stops_the_ticker` | COVERED | Phase-4-Entscheid D-12: jede offene Order stoppt als fremd; Toleranzband getestet. |
| REQ-IBKR-24 long-only | `tests/test_ibkr_decision.py::test_long_only_noop_and_sells`, `::test_long_only_property_never_oversell`, `tests/test_ibkr_preview.py::test_long_only_noop_for_a_sell_without_holding` | COVERED | Kein Short, Sell-Menge nie größer Bestand. |
| REQ-IBKR-25 MKT/DAY | `tests/test_ibkr_broker.py::test_preview_sends_one_whatif_market_order_with_explicit_tif_and_account`, `tests/test_ibkr_preview.py::test_buy_flat_previews_two_blocks` | COVERED | Assertet `orderType="MKT"`, `tif="DAY"`. Code: `scripts/ibkr_broker.py:902`. |
| REQ-IBKR-37 Halt 154 | `tests/test_ibkr_broker.py::test_preview_halted_code_154_is_its_own_state`, `tests/test_ibkr_preview.py::test_code_154_is_halted` | PARTIAL | Unit/Fake abgedeckt; reale Gateway-Messung laut `04-08-SUMMARY.md` nicht herbeiführbar. |
| REQ-IBKR-38 whatIf vor echter Order | `tests/test_ibkr_broker.py::test_whatif_barrier_real_client_passes_whatif`, `::test_whatif_barrier_real_client_refuses_real_order`, `tests/test_ibkr_preview.py::test_buy_flat_previews_two_blocks`, `::test_nothing_sent` | COVERED | Executor ruft nur `preview_order`; Barrier lässt Id 3 nur STK-whatIf durch. Code: `scripts/ibkr_broker.py:436`, `:469`, `:478`; `scripts/ibkr_executor.py:1281`. |
| REQ-IBKR-61 leere/unvollständige Preview | `tests/test_ibkr_broker.py::test_preview_empty_answer_has_no_numbers`, `::test_preview_unset_margin_is_none`, `tests/test_ibkr_preview.py::test_an_empty_preview_is_exit_5` | COVERED | Leere/Unset-Felder werden `preview-empty`, Exit 5. |
| REQ-IBKR-67 reale Codes messen | D-14: `.planning/ibkr-konto-befund.md:279`, `:324`; `04-08-SUMMARY.md` | PARTIAL | 321/10349/whatIf real gemessen; 154 explizit nicht messbar und nur Fake-Test. |
| REQ-IBKR-68 keine Kurse/FX | `tests/test_ibkr_isolation.py::test_no_market_data_in_execution_path`, `tests/test_ibkr_broker.py::test_the_fake_forbids_market_data`, `tests/test_ibkr_decision.py::test_budget_and_currency` | COVERED | Keine Marktdatenaufrufe; Budget direkt gegen Kontowährung. |
| REQ-IBKR-69 explizites und effektives TIF | `tests/test_ibkr_broker.py::test_preview_effective_tif_comes_from_the_echo`, `tests/test_ibkr_decision.py::test_preview_tif_checks`, `tests/test_ibkr_preview.py::test_code_10349_is_tif_overridden`, `::test_a_missing_tif_echo_is_unconfirmed` | COVERED | `sent_tif=DAY`; Echo wird ausgewertet, Override/fehlendes Echo fail-closed. |
| REQ-IBKR-70 Budget via `initMarginChange` | `tests/test_ibkr_decision.py::test_budget_and_currency`, `tests/test_ibkr_preview.py::test_over_budget_is_exit_5`, `::test_funds_in_another_currency_are_a_mismatch` | COVERED | Kein FX-Code; Vergleich `initMarginChange >= AvailableFunds`. |

**Success Criteria**

| Kriterium | Test(s) | Status | Grund |
|---|---|---:|---|
| SC1 echter Branch/Frozen AAPL Hold | `tests/test_ibkr_preview.py::test_real_branch_hold_with_*`; Operatorlauf in `04-09-SUMMARY.md` | COVERED | Unit + manuelle Abnahme: `skipped-hold`, kein Gateway. |
| SC2 Buy flat → BUY 2 + whatIf + nichts gesendet | `tests/test_ibkr_preview.py::test_buy_flat_previews_two_blocks`, `::test_nothing_sent`; Barrier-Tests in `tests/test_ibkr_broker.py:955-1082` | COVERED | Assertions auf MKT/DAY, Margin/Kommission, nur `placeOrder(whatIf)`. |
| SC3 Divergenz | siehe REQ-IBKR-17 | COVERED | Kein Gateway, Exit 2. |
| SC4 Freshness-Gegenproben | `tests/test_ibkr_decision.py::test_freshness_cases` | COVERED | Stub und XNYS-Kalender parametrisiert. |
| SC5 Vorbedingungen | siehe REQ-IBKR-14/15/16 | COVERED | Eigene Zustände, kein whatIf. |
| SC6 Toleranz/offene Order | siehe REQ-IBKR-23 | COVERED | Toleranz ohne Preview; fremde Order stoppt. |
| SC7 Summary-Vertrag | `tests/test_paper_summary_contract.py:71-111` | COVERED | Echter Produzent, Negativ-Kontrolle, Zusatzfeld tolerant. |
| SC8 Long-only | siehe REQ-IBKR-24 | COVERED | Property-Test gegen Oversell. |

**Gaps**

| Item | Vorschlag |
|---|---|
| REQ-IBKR-37 / REQ-IBKR-67 Fehler 154 | Kein Unit-Test-Gap, aber Nyquist-Gap zur realen Messbarkeit bleibt. Beibehalten als dokumentierte MANUAL/PARTIAL-Ausnahme; falls IBKR später Halt real auslösbar macht: Scratchpad-Sonde analog 04-08, dann Befund mit Datum ergänzen. |
| Externe Laufverifikation durch mich | Sandbox blockte pytest. Lokal nachziehen: `C:/Users/admin/PycharmProjects/TradingEngineX/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_ibkr_broker.py tests/test_ibkr_contracts.py tests/test_ibkr_preview.py tests/test_paper_summary_contract.py tests/test_ibkr_isolation.py`. |

**Correctness Findings**

Keine BLOCKER/WARNING-Findings am committed HEAD.

Zur Schreibbarriere: Ich finde keinen belegten Pfad, der eine echte Order past die Barrier senden kann. `placeOrder` wird auf Aufrufebene auf `order.whatIf is True` und `contract.secType == "STK"` geprüft (`scripts/ibkr_broker.py:436-448`), auf Feldebene für Msg-Id 3 erneut geprüft (`:469-476`) und auf String-Ebene erneut geprüft (`:478-486`). `cancelOrder`, `reqGlobalCancel`, `exerciseOptions` bleiben gesperrt (`:452-459`), ebenso Msg-Ids 4/19/21/58 (`:474-485`). Der Executor ruft für Phase 4 nur `broker.preview_order(...)` auf (`scripts/ibkr_executor.py:1281-1289`), und `preview_order` nutzt `whatIfOrderAsync` (`scripts/ibkr_broker.py:922`), nicht IB-Level `placeOrder`.

**Verdict**

`nyquist_compliant false` wegen nicht ausgeführter Tests in dieser Sandbox und der dokumentierten REQ-67-Lücke für realen Fehler 154; funktional/statisch ist die Phase ansonsten abgedeckt.