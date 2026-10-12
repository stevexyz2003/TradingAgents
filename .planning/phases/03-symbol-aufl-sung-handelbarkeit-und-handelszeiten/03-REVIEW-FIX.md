---
phase: 03
fixed_at: 2026-10-12T00:00:00Z
review_path: .planning/phases/03-symbol-aufl-sung-handelbarkeit-und-handelszeiten/03-REVIEW.md
iteration: 1
findings_in_scope:
  - WR-01
  - WR-02
  - WR-03
  - WR-04
  - WR-05
  - WR-06
  - WR-07
fixed:
  - WR-01
  - WR-02
  - WR-03
  - WR-04
  - WR-05
  - WR-06
  - WR-07
skipped: []
status: all_fixed
---

# Review-Fix Phase 03

Alle WARNING-Findings WR-01 bis WR-07 wurden behoben. Zusaetzlich wurden die trivial sicheren INFO-Punkte IN-02, IN-04, IN-06 und IN-07 mitgenommen.

## WR-01

- Status: fixed
- Dateien: `scripts/ibkr_broker.py`, `tests/test_ibkr_broker.py`
- Test: `test_resolution_request_error_code_is_not_reported_as_empty_result`, `test_contract_not_found_code_200_stays_an_empty_result`
- Erklaerung: Der Adapter markiert das Request-Fenster jetzt ueber `_seen_codes`. Nicht-informative Request-Fehler ausser Code 200 werden als `GatewayUnavailable(REQUEST_FAILED, code, ...)` gemeldet, statt als leere Ergebnisliste im Resolver zu landen. Code 200 bleibt der explizite not-found-Pfad.
- **Korrektur durch den Orchestrator (Claude):** Codex' erste Fassung wertete *jeden* Code im Fenster, auch System-/Farm-Meldungen mit `reqId=-1` (z. B. 2107, die im echten Lauf 03-06 auftrat). Das haette gesunde Laeufe als `REQUEST_FAILED` abgebrochen. Jetzt zaehlen nur Fehler mit `reqId >= 0` (`_request_errors`). Regressionstest: `test_system_notice_without_request_id_does_not_fail_the_read` (2103/2105/2107/2108).

## WR-02

- Status: fixed
- Dateien: `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_resolve.py`
- Test: `test_missing_contracts_file_with_history_does_not_suggest_init`, `test_init_refuses_history_without_contracts_file`
- Erklaerung: Konservative Entscheidung: Wenn `contracts.json` fehlt, aber `contracts-history.jsonl` Eintraege enthaelt, bricht `--init` mit Exit 2 ab und fordert manuelle Wiederherstellung. Damit wird keine neue Identitaets-Baseline aus History-Verlust gelernt.

## WR-03

- Status: fixed
- Dateien: `scripts/ibkr_contracts.py`, `tests/test_ibkr_contracts.py`
- Test: `test_write_json_atomic_fsyncs_temp_before_replace`
- Erklaerung: Temp-Dateien fuer JSON- und Contract-Commits werden jetzt per `open(..., newline="\n")`, `flush()` und `os.fsync()` geschrieben, bevor validiert und per `os.replace()` ersetzt wird.

## WR-04

- Status: fixed
- Dateien: `scripts/ibkr_contracts.py`, `scripts/ibkr_executor.py`, `tests/test_ibkr_contracts.py`
- Test: `test_commit_with_expected_bytes_aborts_on_concurrent_change`, `test_commit_lock_file_aborts`
- Erklaerung: Konservative Entscheidung: Der Commit nimmt eine exklusive `.lock`-Datei und vergleicht danach den aktuellen Dateistand mit den Bytes vom Laufbeginn. Bei Lock-Konflikt oder geaenderter Datei wird abgebrochen statt gemerged.
- Restrisiko (Orchestrator): Eine nach hartem Prozessabbruch liegengebliebene `.lock`-Datei blockiert alle weiteren Writes (Exit 1, fail-closed). Das Handbuch beschreibt jetzt, dass sie nach Pruefung von Hand geloescht wird.

## WR-05

- Status: fixed
- Dateien: `scripts/ibkr_contracts.py`, `scripts/ibkr_executor.py`, `tests/test_ibkr_contracts.py`, `tests/test_ibkr_resolve.py`
- Test: `test_resolve_learn_with_incomplete_identity_is_not_found`, `test_commit_validation_failure_is_exit_1_without_traceback`
- Erklaerung: Der Lernpfad weist unvollstaendige Identitaeten vor dem Persistieren ab. Commit-Validierungsfehler werden im Executor als `OutputError` auf Exit 1 gemappt, nicht mehr als unerwarteter Gateway-Fehler.

## WR-06

- Status: fixed
- Dateien: `scripts/IBKR_EXECUTION.md`
- Test: bestehender Handbuch-Guard `test_handbook_documents_resolve`
- Erklaerung: Die Doku ordnet `^GSPC` und `XAUUSD+` jetzt der `not-allowed`-Zeile zu, passend zu D-04 und zum implementierten Allow-List-Pfad.

## WR-07

- Status: fixed
- Dateien: `scripts/ibkr_contracts.py`, `scripts/ibkr_executor.py`, `tests/test_ibkr_contracts.py`
- Test: `test_resolve_logs_trading_class_and_long_name_on_every_ok`
- Erklaerung: `tradingClass` und `longName` werden jetzt bei jedem erfolgreichen Run-Modus-Ergebnis geloggt und zusaetzlich in der `RESOLVED`-Logzeile ausgegeben. Sie bleiben reine Info und werden nicht fuer Drift verglichen.

## Zusaetzlich erledigt

- IN-02: Das Handbuch dokumentiert jetzt, dass die History nach einem Prozessabbruch eine Obermenge sein kann und `contracts.json` massgeblich bleibt.
- IN-04: Die alte Output-Datei wird neutral als `previous output removed` geloggt.
- IN-06: Kandidatenlisten mit `None` werden im Adapter als `REQUEST_FAILED` abgewiesen statt gefiltert.
- IN-07: Die fehlenden Lernpfad-Zweige fuer Details-Diff und mehrere Detailzeilen sind jetzt getestet.

## Verifikation

Die lokale `.venv` in diesem Workspace fehlte; verwendet wurde der vorgegebene Fallback-Python aus `C:/Users/admin/PycharmProjects/TradingEngineX/.venv/Scripts/python.exe`. Pytest musste wegen lokaler Windows-Temp-ACLs mit Workspace-Basetemp und einem prozesslokalen `os.mkdir`-Wrapper gestartet werden; die Testlogik selbst blieb unveraendert.

```
335 passed, 1407 deselected in 7.47s
All checks passed!
```

Nach der Orchestrator-Korrektur (selbst nachgelaufen, `tests -k ibkr`):

```
339 passed, 1407 deselected in 7.27s
All checks passed!
```
