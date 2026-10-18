---
phase: 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
verified: 2026-10-12T19:00:00Z
status: passed
score: 8/8 Roadmap-Kriterien belegt (SC1, SC2, SC4 zusätzlich am echten Paper-Gateway; SC3, SC5-SC8 durch Tests und Code); beide Operator-Entscheidungen per Override angenommen, Wochenend-Lauf am echten Gateway bestanden (2026-10-18)
overrides_applied: 2
overrides:
  - must_have: "REQ-IBKR-31 Handelbarkeit über ineligibilityReasonList geprüft"
    reason: "ineligibilityReasonList existiert in ib_async 2.1.0 nicht (Kontobefund §4), der alte Wortlaut war nicht prüfbar. Ersatz: validExchanges ohne reines VALUE und mit SMART, orderTypes mit MKT und LMT, leere Felder gelten als nicht handelbar (D-19); letzte Schicht ist das whatIf-Preview aus Phase 4."
    accepted_by: "Operator"
    accepted_at: "2026-10-18T12:36:39Z"
  - must_have: "REQ-IBKR-37 HALTED-Tick bzw. Fehler 154 verhindert die Order (Halt-Teil)"
    reason: "Verzögerte Daten liefern am Paper-Konto keinen Halt-Tick (03-RESEARCH.md). Der Halt-Teil ist an die whatIf-Vorschau in Phase 4 übergeben (D-20): Zustand halted, test_code_154_is_halted; die 154-Messlücke ist dort per Override angenommen. Phase 3 liefert den Zustand halted in der Ergebnisschnittstelle."
    accepted_by: "Operator"
    accepted_at: "2026-10-18T12:36:39Z"
re_verification: "2026-10-18T12:39:09Z — alle 3 human_verification-Punkte erledigt (2 Overrides, 1 echter Wochenend-Lauf), siehe 03-HUMAN-UAT.md"
human_verification:
  - test: "Samstagslauf: `python scripts/ibkr_executor.py resolve AAPL` an einem Tag ohne US-Sitzung (Samstag oder Sonntag)"
    expected: "Exit 0, Zeile `resolve: AAPL closed` mit dem nächsten Fenster (Montag, Öffnung plus 15 Minuten Puffer); kein `session-unknown`, kein Exit 2"
    why_human: "Braucht das Gateway an einem Wochenende. D-24 (Tag ohne Eintrag = `session-unknown`) und D-29 (geschlossen = Exit 0) greifen an derselben Stelle. Der Unit-Test `test_resolve_closed_outside_window_is_not_a_rejection` und `test_closed_day_is_closed_not_session_unknown` belegen das nur mit Fake-Strings. Ob das reale `liquidHours` eines Samstags einen `CLOSED`-Eintrag trägt (Befund §5 sagt ja), ist am echten Gateway noch nicht gelaufen."
  - test: "Operator-Bestätigung der Änderung von REQ-IBKR-31 (D-19): `ineligibilityReasonList` entfällt, Ersatz sind `validExchanges`/`orderTypes` (`REQUIREMENTS.md` Z. 131-134)"
    expected: "Override-Eintrag im Frontmatter dieser Datei mit `accepted_by` und `accepted_at`, oder Rückmeldung, dass der alte Wortlaut bleiben soll"
    why_human: "Die Anforderung wurde in dieser Phase geändert. Eine Selbstabnahme durch Executor oder Verifier ist ausgeschlossen. Sachlich belegt: das Feld fehlt in ib_async 2.1.0 (`.planning/ibkr-konto-befund.md` §4)."
  - test: "Operator-Bestätigung der Übergabe des Halt-Teils von REQ-IBKR-37 (Fehler 154 / `HALTED`-Tick) an Phase 4 (D-20; `REQUIREMENTS.md` Z. 161, `ROADMAP.md` Z. 186 und Z. 401)"
    expected: "Override-Eintrag mit `accepted_by` und `accepted_at`, oder die Entscheidung, den Halt-Teil in Phase 3 nachzuziehen"
    why_human: "REQ-IBKR-37 verlangt wörtlich, dass ein `HALTED`-Tick bzw. Fehler 154 die Order verhindert. Phase 3 liefert dafür nur den Zustand `halted` in der Ergebnisschnittstelle (`ibkr_contracts.py:60`, `REJECTED_STATES`), keine Erkennung. Das ist eine bewusste, dokumentierte Scope-Verschiebung, aber eine Abweichung vom Anforderungstext. Die Messung (verzögerte Daten liefern am Paper-Konto keinen Halted-Tick) steht in `03-RESEARCH.md`."
---

# Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten – Verifikationsbericht

**Phasenziel:** Jeder Roh-Ticker wird auf genau einen IBKR-Contract aufgelöst oder begründet abgewiesen, und „ist jetzt Sitzung?" wird aus den Contract-Daten beantwortet statt aus einer hart kodierten Uhrzeit.
**Verifiziert:** 2026-10-12T19:00:00Z
**Status:** human_needed
**Re-Verifikation:** Nein, Erstprüfung

Geprüft wurde der Code auf dem Arbeitsstand `main` (HEAD `69f961e`, 36 Commits seit `efdb93f`). Die SUMMARY-Aussagen habe ich nicht übernommen, sondern gegen `scripts/ibkr_contracts.py`, `scripts/ibkr_broker.py`, `scripts/ibkr_executor.py` und die Tests gelesen.

## Zielerreichung

### Beobachtbare Wahrheiten (ROADMAP-Erfolgskriterien)

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | AAPL/MSFT/NVDA lösen auf genau einen Contract auf, Identität stimmt mit dem Befund, `conId` wird persistiert und ab dem zweiten Lauf benutzt | ✓ VERIFIED | Code: `resolve_all` lernt im Lernzweig (`ibkr_contracts.py:641-710`, genau ein Treffer erzwungen, Identität aus den Details), im Run-Zweig läuft `contract_details(stored.con_id, ...)` plus Gegenprobe per Suche (`:711-751`). Tabelle ohne `conId`/`localSymbol` (`ContractSpec`, `:71-79`). Real (Operator-abgenommen, 2026-10-12 20:09 CEST): AAPL 265598, MSFT 272093, NVDA 4815747, alle NASDAQ/USD; zweiter Lauf über `conId` ohne neues `CONTRACT_LEARNED`, Historie bleibt bei 3 Zeilen. AAPL deckt sich mit dem Befund und mit `PROBE_CON_ID`. Der Anker (`--init` bricht bei AAPL ≠ 265598 ab) ist als `AnchorMismatch` umgesetzt (`:786-789`). |
| 2 | `XYZQ` abgewiesen ohne „SMART/USD zu probieren"; `^GSPC`/`XAUUSD+` mit Verweis auf die Allow-List abgewiesen | ✓ VERIFIED | `classify` (`:110-124`): exakter, case-sensitiver Lookup, nicht gemappt = `not-mapped`, secType außerhalb `{STK}` = `not-allowed` mit Text „not in the allow-list {STK}". `needs_broker(["XYZQ","^GSPC","XAUUSD+"]) is False` (Test `:654`): keine Verbindung. Real: Exit 2, `not-mapped` / `not-allowed(IND)` / `not-allowed(CMDTY)`, kein `CONNECTED` im Log. |
| 3 | Künstlich mehrdeutiger Request → Abbruch, Kandidatenliste steht im eigenen Log | ✓ VERIFIED | Lern- und Run-Zweig melden bei `len(cands) > 1` den Zustand `ambiguous` mit allen Kandidaten (`conId`, `primaryExchange`, `localSymbol`, `currency`, `tradingClass`) in einer Zeile über den Phasen-Logger (`:646-653`, `:724-731`). Adapter ruft `qualifyContractsAsync(..., returnAll=True)` (`ibkr_broker.py:598`). Test `test_ambiguous_candidates_all_land_in_the_log`. Echte Evidenz nur der ES-Befund aus Phase 1 (D-31); ein echter Mehrdeutigkeitslauf wurde bewusst nicht gefahren. |
| 4 | Manipulierter persistierter `conId` → Meldung, keine Auflösung | ✓ VERIFIED | Run-Zweig: Details-Abfrage per gespeicherter `conId`, Gegenprobe per Symbol; Abweichung = `drift` mit „check, then resolve --rebaseline" (`:744-751`), `continue`, kein Ergebnis mit Identität; Datei bleibt unverändert (Rebaseline nur explizit, `:631-635`). Tests `test_drift_is_reported_and_the_file_stays`, `test_resolve_manipulated_conid_is_drift_and_others_continue`. Real (Scratchpad-Kopie, AAPL conId 999999): Exit 2, `drift`, `CONTRACT_DRIFT` auf ERROR, SHA-256 der echten Datei unverändert. Die Diagnose zeigt dabei `seen=none` statt der Gegenzahl (siehe WR-01 unten), das Ergebnis bleibt fail-closed. |
| 5 | Auflösung setzt am Roh-Ticker an; `XAUUSD+` wird nicht über `normalize_symbol()` zu `GC=F`; zwei getrennte Pfade | ✓ VERIFIED | Doppelter Nachweis (D-07): AST-Tests `test_resolver_is_library_free` und `test_resolver_does_not_use_the_vendor_normalizer` (`test_ibkr_isolation.py:240-254`) und Verhaltenstest `test_symbols_resolver_and_vendor_normalizer_are_separate_paths` (`test_ibkr_contracts.py:92-97`): Resolver liefert CMDTY/XAUUSD, `normalize_symbol("XAUUSD+")` liefert `GC=F`. In `ibkr_contracts.py` kommt weder `symbols` noch `normalize_symbol` vor. |
| 6 | „Ist jetzt Sitzung?" aus `liquidSessions()`-Daten; Tests für `CLOSED`, Halbtag, beide Datumsformate; Cache ≤ 1 Handelstag | ✓ VERIFIED | Eigener Parser `parse_liquid_hours`/`evaluate_session` (`:250-316`), Uhr als Parameter (`now_utc`), Test `test_resolver_takes_the_clock_as_a_parameter`. Tests: `CLOSED`-Tag (`test_parse_new_format_with_closed_day`, `test_closed_day_is_closed_not_session_unknown`), Halbtag (`test_half_day_is_a_shorter_window_without_special_case`), Altformat (`test_parse_old_format_end_takes_the_start_date`), Gegentest gegen das echte `ib_async.liquidSessions()` auf den Neuformat-Strings (`test_parser_agrees_with_ib_async_on_new_format`, läuft mit installiertem Extra). `test_old_format_is_rejected_by_ib_async_but_parsed_here` belegt, dass das Altformat nur der eigene Parser versteht. Cache: es gibt keinen (D-22); `test_out_file_schema_and_no_session_values` belegt, dass kein Sitzungswert auf Platte landet, damit gilt „höchstens ein Handelstag" konstruktiv. Der Wortlaut „aus `liquidSessions()`" ist durch Parser plus Gegentest erfüllt, nicht durch einen direkten Aufruf (bewusste Abweichung D-23, nicht abgelehnt). |
| 7 | Suche nach `13:30`/`14:30`/`09:30`/`16:00` im Ausführungscode leer | ✓ VERIFIED | Selbst ausgeführt: `grep -n -E "13:30|14:30|09:30|16:00" scripts/ibkr_*.py` → keine Treffer. Dauerhaft gesichert durch `test_no_hard_coded_trading_times_in_execution_code`; laut 03-04-SUMMARY wurde die Gegenprobe (temporäres `# 09:30` macht den Test rot) gefahren. Die Fenster-Tests tragen die Uhrzeiten nur in Testdaten. |
| 8 | `reqMarketDataType(3)` gesetzt; 10089/10090 im Log als erwarteter Zustand, nicht Fehler | ✓ VERIFIED | `ibkr_broker.py:447-454`: nach bestandenem Paper-Guard, genau einmal, mit INFO-Zeile. `INFO_CODES` enthält 10089, 10090, 10167 (`:103`), Labels `MARKET_DATA_NOT_SUBSCRIBED`/`MARKET_DATA_DELAYED`. Tests `test_market_data_type_is_set_once_after_the_guard`, `test_market_data_type_is_not_sent_on_a_guard_violation`, Code-Mapping-Tests (`test_ibkr_broker.py:349-377`). Real: `MARKET_DATA_TYPE delayed (3)` bei jedem verbundenen Lauf. 10167 wurde in den echten Läufen **nicht** beobachtet, weil `resolve` keine Kurse anfordert; der Beleg für 10089/10090/10167 ist der Unit-Test plus der Befund, nicht eine reale Beobachtung. |

**Score:** 8/8 Kriterien erfüllt. Kein Kriterium ist FAILED. Offen sind nur die unten genannten menschlichen Punkte.

### Plan-Wahrheiten (must_haves aus 03-01..03-06), zusätzlich zu den Roadmap-Kriterien

| Plan | Wahrheit (gekürzt) | Status | Beleg |
|---|---|---|---|
| 03-01 | Tabelle als Code-Konstante im bibliotheksfreien Modul, nur Suchschlüssel | ✓ | `ibkr_contracts.py:71-97` (`MappingProxyType`, kein `conId`); `set(CONTRACT_TABLE) == {AAPL, MSFT, NVDA, ^GSPC, XAUUSD+}` getestet |
| 03-01 | Handelbarkeit fail-closed: leer, nur `VALUE`, ohne `SMART`, ohne `MKT`/`LMT` | ✓ | `check_tradable` (`:134-149`), parametrisierter Test `test_check_tradable_rejects_fail_closed`, `test_value_only_listing_is_not_tradable` |
| 03-02 | Adapter: zwei Lesemethoden, ≤ 10 öffentliche Methoden, Schreibsperre lässt Message-IDs 9 und 59 durch, gegen die installierte Bibliothek abgeglichen | ✓ | `search_contract`/`contract_details` (`ibkr_broker.py:580`, `:607`); `test_adapter_has_at_most_ten_public_methods`, `test_contract_details_and_market_data_type_heads_match_the_installed_library` |
| 03-03 | `contracts.json` mit Schema-Version, atomar; History append-only; fehlende Datei = Exit 2, kaputte Datei stoppt den Lauf; `--init` überschreibt nie | ✓ | `commit_contracts`, `load_contracts_file`, `ContractsFileMissing`/`ContractsFileError`; Tests `test_missing_contracts_file_is_exit_2`, `test_invalid_contracts_file_is_exit_1`, `test_init_refuses_an_existing_file`, `test_anchor_mismatch_writes_nothing` |
| 03-04 | Vier statische Guards (Resolver bibliotheksfrei, kein Normalizer, SC7, Uhr-Injektion) | ✓ | `test_ibkr_isolation.py:240-277`, alle grün |
| 03-05 | Subkommando `resolve` mit Exit 2, Connect-on-demand, `--init`/`--rebaseline`/`--out`; Ticker Pflicht | ✓ | `test_ibkr_resolve.py` (Fehler- und Erfolgspfade, 30+ Tests grün); lokal abgewiesene Ticker brauchen weder `.env` noch Gateway |
| 03-06 | Handbuch dokumentiert `resolve`, Schema, „neuer Ticker"; echter Lauf; Operator-Abnahme | ✓ | `scripts/IBKR_EXECUTION.md`, drei Handbuch-Tests; Abnahme „approved" am Checkpoint (Angabe des Orchestrators, im Repo nicht gegenprüfbar) |

### Erforderliche Artefakte

| Artefakt | Erwartet | Status | Details |
|---|---|---|---|
| `scripts/ibkr_contracts.py` | Fachmodul, bibliotheksfrei | ✓ VERIFIED | 790 Zeilen, substanziell, vom Executor geladen, keine Platzhalter |
| `scripts/ibkr_broker.py` | `search_contract`, `contract_details`, `reqMarketDataType(3)` | ✓ VERIFIED | 724 Zeilen, Methoden vorhanden und über den Resolver genutzt |
| `scripts/ibkr_executor.py` | Subkommando `resolve` | ✓ VERIFIED | 765 Zeilen, `run_resolve`, Exit 2 aktiv |
| `scripts/IBKR_EXECUTION.md` | Abschnitte `resolve`, Schema, neuer Ticker | ✓ VERIFIED | mit WR-06 als Textfehler |
| `tests/ibkr_fakes.py`, `test_ibkr_contracts.py`, `test_ibkr_resolve.py`, `test_ibkr_broker.py`, `test_ibkr_isolation.py` | Tests | ✓ VERIFIED | 321 Tests der IBKR-Dateien grün (selbst ausgeführt) |

### Prüfung der Key Links

| Von | Nach | Über | Status |
|---|---|---|---|
| `ibkr_executor.run_resolve` | `ibkr_contracts.resolve_all` | geladenes Modul (`contracts_mod`) | ✓ WIRED |
| `resolve_all` | Adapter | `broker.search_contract(spec)`, `broker.contract_details(con_id, exchange)` | ✓ WIRED |
| Adapter | Bibliothek | `qualifyContractsAsync(returnAll=True)`, `reqContractDetailsAsync`, beide unter `asyncio.wait_for` | ✓ WIRED |
| `connect()` | `reqMarketDataType(3)` | erst nach `accounts == [EXPECTED_ACCOUNT]` | ✓ WIRED |
| `resolve_all` | `evaluate_session` | `detail_info.liquid_hours`, `time_zone_id`, `now_utc` vom Aufrufer | ✓ WIRED |
| `ResolveOutcome` | Platte | `commit_contracts` erst nach dem Disconnect (`test_contracts_are_written_after_the_session_closed`) | ✓ WIRED |

### Datenfluss (Level 4)

| Artefakt | Variable | Quelle | Echte Daten | Status |
|---|---|---|---|---|
| `contracts.json` | Identität je Ticker | `reqContractDetailsAsync` am Paper-Gateway | ja: 265598 / 272093 / 4815747 im echten Lauf | ✓ FLOWING |
| Ergebniszeile | Sitzung offen/geschlossen, nächstes Fenster | `liquidHours`/`timeZoneId` der Details, Uhr vom Aufrufer | ja: „handelbar bis 15:45 ET" im echten Lauf | ✓ FLOWING (Samstag offen, Human 1) |

### Behavioral Spot-Checks

| Verhalten | Kommando | Ergebnis | Status |
|---|---|---|---|
| Volle Suite | `.venv/Scripts/python.exe -m pytest -q` | 1 failed, 1722 passed, 4 skipped; Fehlschlag nur `test_suite_isolation::test_yfinance_keeps_its_cache_out_of_the_users_home` (vorbestehend, rot schon bei `efdb93f`, unabhängig) | ✓ PASS |
| IBKR-Tests | `pytest tests/test_ibkr_{contracts,resolve,broker,isolation,executor}.py -q` | 321 passed | ✓ PASS |
| Lint | `ruff check .` | All checks passed | ✓ PASS |
| SC7 | `grep -n -E "13:30\|14:30\|09:30\|16:00" scripts/ibkr_*.py` | leer | ✓ PASS |
| Schuldmarker | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK"` in `scripts/ibkr_*.py`, `tests/test_ibkr_*.py`, `tests/ibkr_fakes.py` | keine Treffer | ✓ PASS |

### Probe-Ausführung

Step 7c: übersprungen. Die Phase deklariert keine `scripts/*/tests/probe-*.sh`, und es gibt keine.

### Abdeckung der Anforderungen

Alle 7 IDs aus ROADMAP Phase 3 sind in mindestens einem PLAN beansprucht (26: 03-02/05/06; 27: 03-01/04/05; 28: 03-01/05/06; 29: 03-02/03/05/06; 30: 03-02/03/05/06; 31: 03-01/03/04/05; 37: 03-01/03/04/05/06). `REQUIREMENTS.md` führt keine Rückverfolgungstabelle mit Phasenzuordnung; maßgeblich ist `ROADMAP.md` Z. 137. Verwaiste IDs gibt es nicht.

| Anforderung | Plan | Beschreibung | Status | Beleg |
|---|---|---|---|---|
| REQ-IBKR-26 | 03-02, 03-05, 03-06 | `reqMarketDataType(3)`; 10089/10090 erwartet | ✓ SATISFIED | SC8; 10167 nicht real beobachtet |
| REQ-IBKR-27 | 03-01, 03-04, 03-05 | zweiter Pfad vom Roh-Ticker, kein `normalize_symbol()` | ✓ SATISFIED | SC5 |
| REQ-IBKR-28 | 03-01, 03-05, 03-06 | Allow-List `{STK}`, nichts „durchprobiert" | ✓ SATISFIED | SC2, real bestätigt |
| REQ-IBKR-29 | 03-02, 03-03, 03-05, 03-06 | genau ein Treffer, Kandidatenliste im Log | ✓ SATISFIED | SC3 (Fake-Test, ES-Befund) |
| REQ-IBKR-30 | 03-02, 03-03, 03-05, 03-06 | `conId` persistiert, geprüft, Drift → Meldung | ✓ SATISFIED (Phase-3-Umfang) | SC1, SC4, real. „Geordert über `conId`+`exchange`" ist die Lookup-Form; die Order selbst ist Phase 6 |
| REQ-IBKR-31 | 03-01, 03-03, 03-04, 03-05 | Handelbarkeit abgefragt | ? NEEDS HUMAN | Code erfüllt den **geänderten** Text (D-19). Die Änderung braucht die Operator-Bestätigung (Human 2) |
| REQ-IBKR-37 | 03-01, 03-03, 03-04, 03-05, 03-06 | Sitzungsfenster aus `ContractDetails`, kein hart kodiertes Zeitfenster, Cache ≤ 1 Tag, Halt verhindert die Order | ? NEEDS HUMAN (teilweise) | Sitzungsteil erfüllt (SC6, SC7). Halt-Teil bewusst an Phase 4 übergeben (D-20); Bestätigung offen (Human 3). Zusätzlich fehlt der Samstagslauf (Human 1) |

### Gefundene Anti-Patterns

| Datei | Zeile | Muster | Schwere | Wirkung |
|---|---|---|---|---|
| alle Phasen-Dateien | – | `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` | – | keine Treffer, kein Blocker nach dem Schuldmarker-Gate |
| `scripts/ibkr_contracts.py` | 716-720, 665-670 | WR-01: Gateway-Fehler (leere Liste) wird als `drift` mit Rebaseline-Empfehlung gemeldet | ⚠️ Warning | fail-closed, aber falsche Diagnose; SC4 bleibt erfüllt (keine Auflösung, Meldung) |
| `scripts/ibkr_executor.py` / `ibkr_contracts.py` | 442-449, 350 | WR-02: `--init` ignoriert vorhandene History; Konsole empfiehlt `--init AAPL MSFT NVDA` nach Dateiverlust | ⚠️ Warning | kann D-12 („keine stille Neu-Lernung") aushebeln; kein Roadmap-Kriterium betroffen |
| `scripts/ibkr_contracts.py` | 489-495, 446-451 | WR-03: kein `fsync` der Temp-Datei vor `os.replace` | ⚠️ Warning | Crash-Festigkeit der Baseline, Folgerisiko über WR-02 |
| `scripts/ibkr_executor.py` | 441, 497-499 | WR-04: Read-Modify-Write ohne Lock | ⚠️ Warning | Lost Update bei Parallellauf; heute ein Operator-Prozess, relevant erst mit Phase 4 |
| `scripts/ibkr_executor.py` | 497-500 | WR-05: `ContractsFileError` beim Commit endet als Exit 3 und ohne Ergebniszeilen | ⚠️ Warning | falsche Fehlerklasse; ein vorhandener Test `test_commit_failure_is_exit_1_without_traceback` deckt nur den `OSError`-Pfad |
| `scripts/IBKR_EXECUTION.md` | 277 | WR-06: `^GSPC`/`XAUUSD+` stehen unter `not-mapped` statt `not-allowed` | ⚠️ Warning | Handbuchfehler, widerspricht D-04 und dem realen Lauf im selben Dokument |
| `scripts/ibkr_contracts.py` | 754-763 | WR-07: `tradingClass`/`longName` werden im Run-Modus praktisch nie geloggt (D-09) | ⚠️ Warning | die `ResolveResult`-Zeile trägt die Felder, die Ausgabe in der Konsole nicht |
| `scripts/ibkr_contracts.py` | 239-246 | IN-01: Altformat über Mitternacht → `session-unknown` | ℹ️ Info | fail-closed; D-23 nennt Fenster über Mitternacht, im Neuformat unterstützt |

Einordnung der Review-Warnungen gegen die Must-haves: Keine der sieben Warnungen widerlegt ein Roadmap-Kriterium. WR-01 betrifft die Qualität der Meldung bei SC4, nicht die Abweisung. WR-02 bis WR-04 betreffen die Haltbarkeit der Identitäts-Baseline und sind ein Risiko für den Betrieb, kein Defekt der acht Kriterien. Sie sollten vor Phase 4 (Heartbeat ruft `resolve_all` auf) entschieden werden, ob sie vorher geschlossen werden.

### Menschliche Verifikation erforderlich

#### 1. Samstagslauf (D-24 gegen D-29)

**Test:** `python scripts/ibkr_executor.py resolve AAPL` an einem Wochenende
**Erwartet:** Exit 0, `closed` mit nächstem Fenster, nicht `session-unknown`
**Warum menschlich:** Braucht das Gateway an einem Tag ohne Sitzung; bisher nur mit Fake-Strings belegt.

#### 2. REQ-IBKR-31: Operator-Bestätigung der Textänderung (D-19)

**Test:** Änderung `REQUIREMENTS.md` Z. 131-134 prüfen
**Erwartet:** `overrides`-Eintrag mit `accepted_by`/`accepted_at` oder Gegenentscheidung
**Warum menschlich:** Anforderungsänderung braucht eine menschliche Freigabe; ich trage `accepted_by` nicht selbst ein.

#### 3. REQ-IBKR-37: Operator-Bestätigung der Übergabe des Halt-Teils an Phase 4 (D-20)

**Test:** Änderung `REQUIREMENTS.md` Z. 161 und `ROADMAP.md` Z. 186/401 prüfen
**Erwartet:** `overrides`-Eintrag mit `accepted_by`/`accepted_at` oder Gegenentscheidung
**Warum menschlich:** Abweichung vom Anforderungstext (Halt verhindert die Order), bewusste Scope-Verschiebung.

Vorschläge für die Overrides, falls akzeptiert (nicht eingetragen):

```yaml
overrides:
  - must_have: "REQ-IBKR-31 Handelbarkeit über ineligibilityReasonList"
    reason: "Das Feld existiert in ib_async 2.1.0 nicht (ibkr-konto-befund.md §4); Ersatz validExchanges/orderTypes, letzte Schicht whatIf (Phase 4)"
    accepted_by: "<name>"
    accepted_at: "<ISO timestamp>"
  - must_have: "REQ-IBKR-37 HALTED-Tick bzw. Fehler 154 verhindert die Order (in Phase 3)"
    reason: "Verzögerte Daten liefern am Paper-Konto keinen Halted-Tick (03-RESEARCH.md D-20); Erkennung über 154 am whatIf in Phase 4, Phase 3 führt nur den Zustand halted"
    accepted_by: "<name>"
    accepted_at: "<ISO timestamp>"
```

### Zusammenfassung

Das Phasenziel ist im Code erreicht. Es gibt eine bibliotheksfreie Entscheidungskette (Tabelle, Allow-List, Eindeutigkeit, Identität mit Drift-Abweisung, Handelbarkeit, Sitzung aus `liquidHours`), die der Executor als `resolve` mit Exit 2 für Abweisungen bereitstellt. Alle acht Kriterien sind durch Tests und Code belegt. SC1, SC2 und SC4 sind zusätzlich am echten Paper-Gateway gelaufen. Die Suite ist bis auf den vorbestehenden, unabhängigen Fehlschlag grün, `ruff` ist sauber, es gibt keine Schuldmarker.

Der Status ist `human_needed` und nicht `passed`, weil drei Punkte ohne Operator nicht schließbar sind: der Samstagslauf und die beiden Änderungen an Anforderungstexten (REQ-IBKR-31 nach D-19, Halt-Teil von REQ-IBKR-37 nach D-20). Die Einschränkungen zu den Belegen: 10167 wurde real nicht beobachtet (SC8 stützt sich dort auf Unit-Test und Befund), und die Mehrdeutigkeit (SC3) ist nur per Fake-Test und ES-Befund belegt. Die sieben Review-Warnungen sind kein Blocker für die Kriterien, WR-01 bis WR-04 sollten aber vor Phase 4 entschieden werden.

---

_Verifiziert: 2026-10-12T19:00:00Z_
_Verifier: Claude (gsd-verifier)_
