---
phase: 05-leitplanken-scharf
fixed_at: 2026-10-17
review_path: .planning/phases/05-leitplanken-scharf/05-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 12
deferred: 1
skipped: 0
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-10-17
**Source review:** .planning/phases/05-leitplanken-scharf/05-REVIEW.md
**Iteration:** 1

**Zusammenfassung:**
- Befunde im Umfang: 13 (3 Critical, 7 Warning, 3 Info)
- Behoben: 12 (CR-01..03, WR-01..06, IN-01..03), jeweils mit Regressionstest, der vor dem
  Fix rot und danach grün ist (geprüft per `git stash` der Quelländerung)
- Zurückgestellt: 1 (WR-07, wie beauftragt, als Todo für Phase 6)
- Gearbeitet direkt auf `main`, ein Commit je Befund (IN-01..03 als ein gemeinsamer Commit)

Vorab (Schritt 0, Sicherheit): Ein autouse-Fixture in `tests/conftest.py` setzt
`LOCALAPPDATA` für **jeden** Test auf ein eigenes tmp-Verzeichnis. `_ibkr_base` liest
`LOCALAPPDATA` auf jeder Plattform zuerst und fällt nur ohne die Variable auf das
Home-Verzeichnis zurück, damit deckt das Fixture auch Nicht-Windows ab. Kein Test kann mehr
den echten State-Ordner `%LOCALAPPDATA%\TradingEngineX\ibkr` lesen oder schreiben.
Nachweis: `tests/test_suite_isolation.py::test_a_test_without_a_fixture_of_its_own_gets_its_own_ibkr_state_folder`
(ohne Fixture rot). Commit `6bdc6bc`.

## Übersicht

| Befund | Ergebnis | Commit | Regressionstest(s) |
|---|---|---|---|
| (0) State-Ordner-Isolation | behoben | `6bdc6bc` | `test_suite_isolation.py::test_a_test_without_a_fixture_of_its_own_gets_its_own_ibkr_state_folder` |
| CR-01 | behoben | `55e3433` | `test_ibkr_ledger.py::test_ledger_malformed_record_is_ledger_error` (23 Fälle), `test_ibkr_execute.py::TestFailClosed::test_kill_with_a_malformed_seq_still_cancels_with_exit_4`, `..._intent_missing_its_order_fields_still_cancels`, `..._unreadable_ledger_still_cancels_with_exit_4`, `test_an_unreadable_ledger_without_kill_is_exit_6` |
| CR-02 | behoben | `40374f2` | `test_ibkr_execute.py::TestTickerEnds::test_a_ticker_without_a_valid_decision_key_stops_only_itself[^GSPC / XAUUSD+]` |
| CR-03 | behoben | `b6b7d73` | `test_ibkr_ledger.py::test_reconcile_cancelled_after_a_partial_fill_is_partial`, `test_reconcile_cancelled_with_a_full_fill_is_contradiction`, `test_ibkr_execute.py::TestReconcile::test_g3_reconcile_resolves_before_any_new_order[cancelled-after-partial-fill]` |
| WR-01 | behoben | `45ebe0e` | `test_ibkr_ledger.py::test_ledger_append_after_a_half_written_line_seals_it`, `..._after_a_failed_fsync_keeps_the_landed_line`, `..._after_a_line_cut_just_before_its_newline`, `test_ledger_failed_append_on_a_torn_tail_keeps_the_seal`, `test_ibkr_execute.py::TestOrderRefAndIntent::test_a_half_written_intent_does_not_corrupt_the_ledger`, `test_a_run_end_that_cannot_be_written_is_refused_cleanly` |
| WR-02 | behoben | `d4fc651` | `test_ibkr_ledger.py::test_reconcile_dry_intent_without_trace_is_never_sent`, `test_ibkr_execute.py::TestReconcile::test_g3_reconcile_dry_intent_without_trace_is_never_sent`, `TestOrderRefAndIntent::test_the_second_size_check_runs_before_the_intent_line`, `TestSizeCap::test_negative_control_only_chain_check_removed_placer_still_refuses` (angepasst) |
| WR-03 | behoben | `3000d58` | `test_ibkr_guards.py::test_kill_active_for_a_kill_file_with_an_ending_or_another_case`, `test_kill_absent_for_names_that_only_look_alike`, `test_kill_unreadable_when_the_folder_cannot_be_listed`, `test_ibkr_execute.py::TestFailClosed::test_a_kill_txt_from_explorer_stops_and_cancels` |
| WR-04 | behoben | `02ec5c7` | `test_ibkr_guards.py::test_source_conflict_order_ref_echo_mismatch`, `..._missing_or_same_echo_is_clean`, `test_ibkr_execute.py::TestSourceConflict::test_source_conflict_order_ref_echo_stops_only_that_ticker`, `..._same_or_empty_is_not_a_conflict` |
| WR-05 | behoben | `39c4eac` | `test_ibkr_execute.py::TestSessionWindow::test_the_window_closing_during_the_run_stops_before_the_intent` (+ Negativ-Kontrolle), `test_ibkr_contracts.py::test_window_open_applies_the_buffer_at_both_ends` |
| WR-06 | behoben | `351c978` | `test_ibkr_broker.py::test_order_history_open_list_drops_finished_orders_like_open_orders`, `test_ibkr_ledger.py::test_reconcile_finished_order_in_both_answers_is_no_contradiction`, `..._only_in_the_open_answer_counts_as_completed`, `test_reconcile_two_orders_under_one_order_ref_are_a_collision` |
| WR-07 | zurückgestellt | `adc411c` (Todo) | – (Todo `.planning/todos/pending/05-wr07-signed-fills.md`, `resolves_phase: 6`) |
| IN-01 | behoben | `9d34fa9` | `test_ibkr_guards.py::test_decision_key_rejects_bad_parts["AAPL\n", "2026-10-09\n", Vollbreiten-Ziffern]`, `test_release_date_with_a_trailing_newline_is_invalid` |
| IN-02 | behoben | `9d34fa9` | – (nur Docstring/Kommentar) |
| IN-03 | behoben | `9d34fa9` | – (Kommentar und Handbuch) |

## Fixed Issues

### CR-01: Ledger-Lesefehler außerhalb von `LedgerError` umgehen Kill-Pfad und Exit 4

**Files modified:** `scripts/ibkr_ledger.py`, `scripts/ibkr_executor.py`, `tests/test_ibkr_ledger.py`, `tests/test_ibkr_execute.py`
**Commit:** `55e3433`
**Applied fix:** `_check` prüft jetzt das Schema vollständig über `_schema_problem`: `seq` ist ein
`int` (kein `bool`) > 0, `ts` und `run_id` sind Text, `decision_key` ist Text, ein `intent` hat
`decision_key`, `ticker`, `rating`, `paper_log_sha`, `side` ∈ {BUY, SELL}, `quantity` > 0 (Zahl,
kein `bool`), `con_id` (`int`) und optional `order_ref`; `filled`/`partial` haben ein numerisches
`filled_qty`, `skipped` einen Grund aus `REASONS`. Jeder Verstoß ist `LedgerError`. Der
Ausführer behandelt jeden Fehler beim Öffnen des Ledgers (inkl. `PermissionError`/`OSError`)
wie ein korruptes Ledger: Exit 6 bei offenen Schaltern, sonst Meldung, bei `KILL` Storno und
Exit 4. `Ledger.__init__` liest `seq` ohne `int()`-Konvertierung.

### CR-02: Nicht-Aktien-Ticker der Vertragstabelle lassen den ganzen `execute`-Lauf abstürzen

**Files modified:** `scripts/ibkr_guards.py`, `scripts/ibkr_ledger.py`, `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_execute.py`, `tests/test_ibkr_ledger.py`
**Commit:** `40374f2`
**Applied fix:** Neuer benannter Zustand `invalid-decision-key` (guards, Exit 2), im Ledger als
`skipped` mit Grund `not_tradable`. `_check_attempts` fängt den `ValueError` von
`decision_key` und beendet nur diesen Ticker; die übrigen Ticker laufen weiter (D-11).
`EXIT_BY_STATE`, `REASON_BY_STATE` und die Zustandstabelle im Handbuch sind konsistent
(der Handbuch-Abgleich in `tests/test_ibkr_isolation.py` ist grün); die Liste der
Ticker-Endzustände in `test_ibkr_ledger.py` ist ergänzt.

### CR-03: Reconciliation stuft „teilgefüllt, dann storniert" als `not_filled` ein

**Files modified:** `scripts/ibkr_ledger.py`, `tests/test_ibkr_ledger.py`, `tests/test_ibkr_execute.py`
**Commit:** `b6b7d73`
**Applied fix:** Ein `Cancelled`/`ApiCancelled`/`Inactive`-Auftrag mit `0 < filled < quantity`
ist `partial` mit der gefüllten Menge (der Ausführer schreibt `partial` mit `filled_qty`);
`filled >= quantity` bei einem stornierten Auftrag ist `contradiction`. Der Hinweis des
Reviews zu mehreren `completed`-Einträgen unter einer `orderRef` ist mit WR-06 umgesetzt
(verschiedene `permId` → `collision`).

### WR-01: Ein fehlgeschlagener Append kann das Ledger dauerhaft korrumpieren

**Files modified:** `scripts/ibkr_ledger.py`, `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_ledger.py`, `tests/test_ibkr_execute.py`
**Commit:** `45ebe0e`
**Applied fix:** Scheitert `write`/`flush`/`fsync`, verbraucht der Append seine `seq` und
markiert das Dateiende als unbekannt. Der nächste Append prüft zuerst das Ende der Datei:
Ist die Zeile vollständig gelandet, wird sie in `records` übernommen; ist sie abgeschnitten,
beginnt der nächste Append mit einem Zeilenumbruch und versiegelt die Zeilennummer über den
bestehenden `seals_torn_line`-Mechanismus. Hat nur der Umbruch eines älteren Torn-Tails die
Platte erreicht, bleibt dessen Siegel erhalten. Das `run_end` des Fehlerpfads wird so
versiegelt; scheitert auch dieser Append, protokolliert der Ausführer `LEDGER_APPEND_FAILED`
und wirft den ursprünglichen Fehler weiter. Verbleibende Grenze (nicht abgedeckt): Bricht ein
Append auf einem bereits vorhandenen
Torn-Tail **nach** dem Umbruch **mitten** in der neuen Zeile ab, stehen zwei kaputte Zeilen
hintereinander; ein Siegel deckt nur eine davon ab, der nächste Lauf meldet dann Exit 6
(fail-closed, kein stilles Weiterlaufen).

### WR-02: Ein verwaister Trocken-`intent` erzeugt dauerhaft Exit 6

**Files modified:** `scripts/ibkr_ledger.py`, `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_ledger.py`, `tests/test_ibkr_execute.py`
**Commit:** `d4fc651`
**Applied fix:** `resolve_entry(..., dry=True)` liefert für einen offenen Trocken-`intent` ohne
jede Broker-Spur das eigene Ergebnis `never_sent`. `_reconcile` schreibt die
`reconcile`-Zeile mit `outcome=never_sent`, schließt den Eintrag mit `rejected
state=never-sent source=reconcile`, protokolliert `RECONCILE_NEVER_SENT` und läuft ohne Exit 6
weiter; der Schlüssel bleibt verbraucht (`already-attempted`). Der Broker wird dabei weiter
gefragt (fail-closed): Eine Spur mit dieser `orderRef` bleibt `collision`/`contradiction`
(Exit 6). Im Live-Ledger bleibt `no_trace` → Exit 6 unverändert. Der zweite Größencheck sitzt
jetzt unmittelbar vor dem `intent`-Append (statt in `DryPlacer.complete`) und endet sauber als
`size-cap` ohne offenen `intent`.
**Hinweis G3:** Die G3-Reconciliation-Tests liefen bisher über einen Trocken-`no_trace`. Sie
belegen Exit 6 jetzt so: `no_trace` → Exit 6 auf einem Live-Ledger (direkter Aufruf von
`_reconcile`, zweimal, Eintrag bleibt offen), und „blockiert jeden weiteren Lauf" über
`main` mit widersprüchlicher Broker-Historie (`contradiction`). Die Negativ-Kontrolle
„Reconciliation entfernt → neuer `intent`" nutzt ebenfalls diese Historie. Kein Konflikt mit
einer gesperrten Entscheidung: D-08 begründet gerade, dass ein Trocken-`intent` sonst jeden
Lauf mit Exit 6 beenden würde; D-19 (Exit 6 bei unauflösbarem `intent`) gilt weiter für
echte unauflösbare Fälle.

### WR-03: Fail-open bei `KILL.txt`

**Files modified:** `scripts/ibkr_guards.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_guards.py`, `tests/test_ibkr_execute.py`
**Commit:** `3000d58`
**Applied fix:** Nach dem exakten `os.stat` auf `KILL` listet `read_kill` den State-Ordner:
Jeder Eintrag, dessen Name ohne Beachtung der Groß-/Kleinschreibung `KILL` ist oder mit
`KILL.` beginnt (`KILL.txt`, `kill.TXT`), ist `kill-active` (mit Namen im Detail). `KILLER`,
`KILL_old` usw. zählen nicht. Ein Ordner, der sich nicht listen lässt, ist
`kill-unreadable`. `RELEASE` bleibt exakt. Das Handbuch (Abschnitt „RELEASE and KILL",
englisch) beschreibt die Regel; der Einzeiler zum Aufheben entfernt jetzt `KILL` und alle
`KILL.*`.

### WR-04: Das Echo der `orderRef` wird nie mit dem Schlüssel verglichen

**Files modified:** `scripts/ibkr_guards.py`, `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/ibkr_fakes.py`, `tests/test_ibkr_guards.py`, `tests/test_ibkr_execute.py`
**Commit:** `02ec5c7`
**Applied fix:** `guards.order_ref_conflict`: Ist ein Echo vorhanden und weicht es vom
Schlüssel ab, endet der Ticker als `source-conflict` („orderRef echo … differs") vor jedem
`intent`, mit Logzeile `ORDER_REF_CONFLICT`. Ein fehlendes oder leeres Echo bleibt erlaubt
(D-22). Der Fake-Gateway kann ein abweichendes Echo liefern (`whatif_echo_order_ref`).

### WR-05: Sitzungsfenster wird mit dem Startzeitpunkt des Laufs bewertet

**Files modified:** `scripts/ibkr_contracts.py`, `scripts/ibkr_executor.py`, `scripts/IBKR_EXECUTION.md`, `tests/test_ibkr_contracts.py`, `tests/test_ibkr_execute.py`
**Commit:** `39c4eac`
**Applied fix:** Neben der letzten Schalterprüfung prüft `_execute_ticker` das aufgelöste
Fenster erneut mit `ctx.clock()`. Die Pufferregel steht an genau einer Stelle
(`contracts.window_open`, von `evaluate_session` mitbenutzt, gleiche Konstante
`SESSION_BUFFER_MINUTES`); ein geschlossenes Fenster ergibt `outside-session`. Der
Test-Helfer `_run_execute` akzeptiert dafür auch eine laufende Uhr. Die Frische
(`stale`) wird weiterhin mit dem Startzeitpunkt bewertet; das Review nennt sie, der Auftrag
umfasste nur das Sitzungsfenster.

### WR-06: `order_history` filtert erledigte Status nicht

**Files modified:** `scripts/ibkr_broker.py`, `scripts/ibkr_ledger.py`, `tests/test_ibkr_broker.py`, `tests/test_ibkr_ledger.py`
**Commit:** `351c978`
**Applied fix:** `order_history` nimmt erledigte Status (`Filled`, `Cancelled`, `ApiCancelled`,
`Inactive`) aus der Open-Liste wie `open_orders`. Eine erledigte Zeile, deren
`permId`/Menge der Completed-Read noch nicht kennt, wird als `completed` behalten statt
verworfen (die Reads sind nicht atomar, der Beleg bleibt). `resolve_entry` macht dasselbe:
gleiche `permId` und Menge in „open (erledigt)" und „completed" ist ein Auftrag, kein
Widerspruch; zwei verschiedene `permId` unter einer `orderRef` sind `collision`.

### IN-01: `$` in den Whitelist-Regexen lässt ein abschließendes `\n` durch

**Files modified:** `scripts/ibkr_guards.py`, `tests/test_ibkr_guards.py`
**Commit:** `9d34fa9`
**Applied fix:** Release-Datum, Handelsdatum und Ticker werden mit `fullmatch` und
ASCII-Ziffernklassen (`[0-9]` statt `\d`) geprüft.

### IN-02: Ein gezählter Cancel kann bei Drosselung nur eingereiht sein

**Files modified:** `scripts/ibkr_broker.py`
**Commit:** `9d34fa9`
**Applied fix:** Docstring von `cancel_all` und Kommentar an `permit.sent`: „gesendet"
heißt „einmal an `sendMsg` der Client-Bibliothek übergeben"; den Beweis liefert der Re-Read
der offenen Orders.

### IN-03: Rang-Kommentar „The kill switch always wins" stimmt nicht für alle Pfade

**Files modified:** `scripts/ibkr_guards.py`, `scripts/IBKR_EXECUTION.md`
**Commit:** `9d34fa9`
**Applied fix:** Kommentar auf die im Lauf kombinierten Exits eingeschränkt; Ausnahmen
(Lock 7 vor dem Preflight, Kontowächter 8 beim Verbinden auch mit `KILL`, unerwarteter
Fehler 1/3) im Kommentar und im Handbuch (Abschnitt „Exit codes") genannt.

## Deferred Issues

### WR-07: `filled_quantity` summiert auch Verkäufe; ein Ticker blockiert dauerhaft

**File:** `scripts/ibkr_ledger.py:325-332`, `scripts/ibkr_guards.py:351-359`
**Reason:** Laut Auftrag zurückgestellt. In Phase 5 gibt es keine echten Fills (erzwungen
trocken, echtes Ledger leer); die Schärfung gehört zum Placer von Phase 6 (D-18).
Festgehalten als `.planning/todos/pending/05-wr07-signed-fills.md` (`resolves_phase: 6`,
Commit `adc411c`) mit Problem und Lösung aus dem Review (Seite in `filled`/`partial`,
vorzeichenbehaftete Summe, Test mit Kauf + Verkauf).
**Original issue:** `filled_quantity` addiert `filled_qty` aller `FILLED`/`PARTIAL` einer
`conId` ohne `side`; nach einem Verkauf gilt `ledger_filled_qty > broker_held` und der Ticker
endet dauerhaft als `source-conflict`.

## Verifikation

- Volle Suite: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` →
  `1 failed, 2511 passed, 4 skipped, 1 deselected, 101 subtests passed`. Der eine Fehler ist
  der bekannte, vorbestehende `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`.
- `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`
- Formatierung: Nur berührte Dateien ohne Vorlast wurden mit `ruff format` formatiert.
  `scripts/ibkr_executor.py`, `scripts/ibkr_broker.py`, `tests/test_ibkr_broker.py`,
  `tests/ibkr_fakes.py` und `tests/test_suite_isolation.py` haben vorbestehende
  Format-Abweichungen und wurden nicht umformatiert; die neuen Hunks entsprechen dem
  Formatter.
- Kein Kontakt zum echten Gateway, kein Zugriff auf `%LOCALAPPDATA%\TradingEngineX`.

---

_Fixed: 2026-10-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
