---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
verified: 2026-10-12T00:00:00Z
status: passed
score: 8/8 ROADMAP-Success-Criteria verifiziert; SC2 per Operator-Entscheidung 2026-10-16 umformuliert (321-Schalter blockt whatIf, Schutz ist die Socket-Sperre); 154 per Override; Sitzungsfenster aus REQ-IBKR-25 nach Phase 5 verschoben
overrides_applied: 1
overrides:
  - must_have: "REQ-IBKR-67 Fehlercode 154 (Halt) am echten Gateway gemessen"
    reason: "154 ist am Paper-Gateway nicht herbeiführbar (Annahme A5) und nur über die offizielle IBKR-Codeliste plus test_code_154_is_halted belegt. Der Code ist request-gebunden und wird in der whatIf-Vorschau ausgewertet, nicht im Lesefenster. Offen bis zur ersten Live-Gelegenheit."
    accepted_by: "Operator"
    accepted_at: "2026-10-16T19:27:26Z"
re_verification: "2026-10-16T19:27:26Z — alle 4 human_verification-Punkte vom Operator entschieden, siehe 04-HUMAN-UAT.md"
human_verification:
  - test: "D-14 / SC2-Anpassung bestätigen: Der ROADMAP-Satz zu 321 (\"ein versehentliches place scheitert an 321 – nur solange der Operator den Schreibschutz gesetzt hat\") wird ersetzt durch: Der Gateway-Schalter 'Read-Only API' blockt auch whatIf (321, 10 s Timeout), bleibt daher in Phase 4 AUS; der Schutz vor einem versehentlichen place ist allein die Socket-Sperre (Id 3 nur als STK-whatIf)."
    expected: "Operator bestätigt den Ersatzsatz und dass der Schalter AUS bleibt (Schalter-Stand AUS am 2026-10-12 ist laut Operator bestätigt). ROADMAP.md SC2 trägt den alten Satz noch."
    why_human: "Die Umformulierung eines Roadmap-Vertrags und die Akzeptanz, dass ein Schutz entfällt, ist eine Operator-Entscheidung (04-08-PLAN, D-14)."
  - test: "Fehler 154 (Halt) am Paper-Gateway: Lücke akzeptieren"
    expected: "Operator akzeptiert, dass 154 am Paper-Gateway nicht herbeiführbar ist (Annahme A5) und nur über die offizielle Codeliste plus Fake-Test (test_code_154_is_halted) belegt ist; offene REQ-67-Lücke bis zur ersten Live-Gelegenheit."
    why_human: "Eine echte Messung ist nicht möglich; die Akzeptanz der Restunsicherheit ist eine Operator-Entscheidung."
  - test: "Realer Trockenlauf 04-09 (bereits vom Operator abgenommen) in den Bericht übernehmen"
    expected: "`preview: AAPL skipped-hold (trade_date 2026-10-09)`, Exit 2, sha 7b4af23df6e823dff723f74f8925e807176160e0, sent=false. Der Lauf selbst ist nur aus SUMMARY/Operator-Aussage belegt, nicht vom Verifier wiederholbar (Gateway/Remote)."
    why_human: "Läuft gegen den echten Remote fork/paper-log; Verifier hat ihn nicht neu ausgeführt."
  - test: "REQ-IBKR-25, Teil 'konfiguriertes Fenster der regulären Sitzung (nicht Eröffnungsauktion, nicht Schlussminuten)'"
    expected: "Operator entscheidet, ob dieser Teil als Platzierungslogik in Phase 5/6 gehört (Phase 4 sendet nichts) oder ob ein Konfigurationsfenster schon jetzt gefordert war. Im Code gibt es kein Order-Fenster; Phase 4 erzeugt nur MKT/DAY-Vorschau, markiert 'closed' außerhalb der Sitzung und lässt whatIf trotzdem laufen (D-08)."
    why_human: "Auslegung des Requirement-Zuschnitts (ROADMAP-Traceability nennt REQ-25 für Phase 4)."
---

# Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum whatIf-Preview – Verifikationsbericht

**Phasenziel:** Aus der Entscheidung auf `paper-log` entsteht eine vollständig geprüfte, von IBKR vorab bewertete Order-Absicht – die der Lauf nachweislich nicht sendet.
**Verifiziert:** 2026-10-12
**Status:** human_needed
**Re-Verifikation:** Nein, Erstverifikation
**Verifizierter Stand:** committeter Stand HEAD 8b2593c im sauberen Worktree `head-check` (nicht der Arbeitsbaum des Main-Checkouts).

## Beobachtung zum Arbeitsbaum (kein Phase-4-Gap)

Der Main-Checkout enthält eine uncommittete Operator-Änderung an `scripts/ibkr_broker.py` (Marktdaten-Stream, `MarketTick`, `reqMktData`). Sie gehört nicht zu Phase 4 und lässt zwei Isolationswächter in `tests/test_ibkr_isolation.py` anschlagen (`test_adapter_has_at_most_ten_public_methods`, `test_no_market_data_in_execution_path`). Das ist der Konflikt mit REQ-IBKR-68 (keine Marktdaten im Order-Pfad). Beim Einchecken muss der Operator entscheiden, ob Anforderung oder Wächter angepasst wird. Der committete Stand ist sauber: `grep reqMktData|reqTickers|reqHistoricalData` in `scripts/ibkr_broker.py`, `ibkr_executor.py`, `ibkr_decision.py` findet nichts.

## Zielerreichung

### Beobachtbare Wahrheiten (ROADMAP Success Criteria)

| # | Wahrheit | Status | Evidenz |
|---|---|---|---|
| SC1 | Trockenlauf gegen den echten Branchstand 2026-10-09 (AAPL Hold) erzeugt keine Order, protokolliert `skipped: hold` | VERIFIZIERT | Eingefrorene Kopie `tests/fixtures/paper_log_71df89d/` (decision-log.md, runs/); `test_real_branch_hold_with_the_stub_calendar` und `..._xnys_calendar` grün; Executor kontaktiert das Gateway im Hold-Pfad nicht. Realer Lauf laut 04-09-SUMMARY und Operator: `skipped-hold`, Exit 2, sha 7b4af23…, sent false (siehe Human-Verification) |
| SC2 | Buy-Fixture + flache Position → "2 Blöcke kaufen", whatIf mit Margin/Kommission/rejectReason, nichts gesendet | VERIFIZIERT (Satz zu 321 offen) | `test_buy_flat_previews_two_blocks`: Intent BUY 2 MKT/DAY, `init_margin_change` 997.14, `commission` 1.00003 USD, `reject_reason` "", `sent` False; `_assert_nothing_sent` und parametrisierter `test_nothing_sent`. Barriere `scripts/ibkr_broker.py` (guarded_place, Z. ~427-450, Id 3 nur STK-whatIf; echte `Client`-Klasse getestet in 04-02). Der 321-Teil des ROADMAP-Satzes ist durch D-14 überholt, siehe unten |
| SC3 | Divergenz summary vs decision-log → Exit 2, Abweichung protokolliert, Log-Fassung gelesen | VERIFIZIERT | `test_log_and_summary_disagree`; `evaluate_decision` liefert `signal-divergence` mit der Log-Fassung als Rating; `EXIT_BY_STATE` = 2 |
| SC4 | Aktualität in XNYS-Sitzungen, vier Gegenproben | VERIFIZIERT | `test_freshness_cases` (parametrisiert über echten XNYS-Kalender und Stub): `tue_run_mon_decision` fresh, `sat_run_decision_on_monday` fresh + weekend_gap (3 Tage), `wed_missed_thu_catchup` stale-decision, `labor_day_monday_tuesday_run` fresh; zusätzlich Wochenende, Abend, Same-Day |
| SC5 | `null`, `REVIEW`, `status != ok`, `schema_version != 1`, `verify`-Befund → je eigener Zustand, keine Order | VERIFIZIERT | `test_review_rating`, `test_run_failed_for_the_log_date`, `test_newer_summary_with_a_null_signal`, `test_an_unknown_schema_version_is_exit_1` (Exit 1), `test_a_broken_tag_line_is_a_log_finding`, leere/fehlende/ungültige-UTF-8-Datei als `log-finding` |
| SC6 | Toleranzband; offene Orders gehen in die Differenz ein | VERIFIZIERT | `test_within_tolerance_needs_no_preview`, `test_a_foreign_open_order_stops_the_ticker` (fremde offene Order → `foreign-open-order`, Exit 2), `plan_order` Property-Test 5x6x3; `open_orders` über `reqAllOpenOrdersAsync` im Adapter |
| SC7 | Vertragstest hält gelesene `summary.json`-Felder fest, schlägt bei nicht-additiver Änderung an `daily_paper_run.py` fehl | VERIFIZIERT | `tests/test_paper_summary_contract.py` erzeugt `summary.json` mit dem echten Erzeuger, grün; Zusatzfeld bleibt grün (laut Plan, Test läuft in Suite) |
| SC8 | `Sell` ohne Bestand = protokollierte Nulloperation, kein Short | VERIFIZIERT | `test_long_only_noop_for_a_sell_without_holding` (Exit 0), `test_a_sell_with_holding_previews_a_sale`; nie SELL-Menge über Bestand |

**Score:** 8/8 Kriterien durch Code und Tests belegt; SC2-Teilsatz (321) wartet auf Operator-Bestätigung.

### Gate G2 / "nachweislich nicht gesendet"

| Prüfung | Ergebnis |
|---|---|
| Executor-Quelle enthält weder `placeOrder`, `cancelOrder`, `reqMktData`, `reqTickers` | VERIFIZIERT (`test_the_executor_knows_no_write_call`) |
| Fake zählt `placeOrder(whatIf)` getrennt von `placeOrder`; `whatIfOrder` (synchron) nie genutzt | VERIFIZIERT (`_assert_nothing_sent`) |
| Adapter sendet Vorschau nur über `whatIfOrderAsync` (`ibkr_broker.py:922`) | VERIFIZIERT |
| Socket-Sperre: Id 3 nur mit `whatIf` und STK; Ids 4/19/21/58, `cancelOrder`, `reqGlobalCancel`, `exerciseOptions` hart gesperrt | VERIFIZIERT (`_WRITE_CALLS`, guarded_place, Real-Client-Test) |
| Echte Messung D-14 (04-08): Vorschau mit Schalter aus OK (0,79 s, Margin 100,86 EUR, Kommission 1,000003 USD, tif DAY); danach `open_orders` leer, Positionen unverändert, Log ohne orderStatus/execDetails/ReadOnlyViolation | VERIFIZIERT per Befund-Dokument (`.planning/ibkr-konto-befund.md`, Abschnitt "whatIf-Vorschau und Read-Only-Schalter"), nicht neu gemessen |

### D-14 Ergebnis (a)

Messung 2 (Schalter an, 2026-10-12): `READ_ONLY_API`, Fehler 321, keine Margin-/Kommissionsdaten, 10,02 s Timeout. Der Schalter blockt whatIf. Folge: Phase 4 ist allein durch die Socket-Sperre geschützt, der Schalter bleibt aus; das Handbuch (`scripts/IBKR_EXECUTION.md`, Abschnitt "Gateway Read-Only switch") gibt das mit Datum wieder ("Rule for phase 4: the switch stays off"). Operator hat den Schalterzustand AUS am 2026-10-12 bestätigt. Die ROADMAP-SC2-Formulierung ist noch nicht angepasst (Operator-Bestätigung ausstehend, Punkt 1 der Human-Verification).

### Erforderliche Artefakte

| Artefakt | Erwartet | Status | Details |
|---|---|---|---|
| `scripts/ibkr_decision.py` (570 Z.) | Zustände, `EXIT_BY_STATE`, Vorbedingungen, `plan_order`, `judge_preview`, `freshness` | VERIFIZIERT | verdrahtet über `ctx.mods.decision` im Executor |
| `scripts/ibkr_paperlog.py` (169 Z.) | Leser ohne Checkout, fetch + cat-file | VERIFIZIERT | `test_ibkr_paperlog.py` grün |
| `scripts/ibkr_broker.py` | `preview_order`, `open_orders`, `con_id`, `AvailableFunds`, 154/10349, Schreibsperre | VERIFIZIERT | im committeten Stand |
| `scripts/ibkr_executor.py` (`run_preview`, Z. 1406) | Subkommando `preview` | VERIFIZIERT | Datenfluss: Paper-Log → Entscheidung → Plan → whatIf → Urteil → JSON mit `sent: false` |
| `scripts/ibkr_contracts.py` | `block_qty`, `session_day` | VERIFIZIERT | `CONTRACT_TABLE` |
| `tests/fixtures/paper_log_71df89d/` | byte-gleiche Kopie | VERIFIZIERT | `test_the_copy_is_byte_equal_with_the_blob` und Fixture-Tests |
| `scripts/IBKR_EXECUTION.md` | preview, Zustandstabelle, Exit 5 aktiv, D-14 | VERIFIZIERT | durch Wächter in 04-09 gepinnt |

### Schlüsselverbindungen

| Von | Nach | Via | Status |
|---|---|---|---|
| Executor `preview` | `ibkr_paperlog` | fetch `FETCH_HEAD`-SHA, in jeder Logzeile und `paper_log.sha` | WIRED |
| Executor | `state_maintenance.verify` | Kopie unter `%LOCALAPPDATA%`, leeres `cache_dir` | WIRED (REQ-15) |
| Executor | `ibkr_decision.EXIT_BY_STATE` | `ctx.mods.decision` (Z. 996, 1052) | WIRED |
| Executor | Adapter `preview_order` | `whatIfOrderAsync` | WIRED |
| Schreibsperre | `placeOrder` / Msg-Id 3 | `client.placeOrder`, `send`, `sendMsg` | WIRED |

### Verhaltens-Spotchecks

| Verhalten | Befehl (Worktree HEAD 8b2593c) | Ergebnis | Status |
|---|---|---|---|
| Phase-4-Suiten | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_ibkr*.py tests/test_paper_summary_contract.py` | 581 passed in 11,5 s | PASS |
| Gesamtsuite (Angabe des Auftraggebers) | `pytest -q -p no:cacheprovider` | 2036 passed, 4 skipped; bekannter Umgebungsfehler `test_yfinance_keeps_its_cache_out_of_the_users_home` (Windows, rot seit Basis 3fe0462) | PASS (Vorbefund, nicht Phase 4) |
| Schuldmarker | `grep TBD|FIXME|XXX` in `scripts/ibkr_*.py`, Phase-4-Tests, `IBKR_EXECUTION.md` | keine Treffer | PASS |

Probe-Ausführung (Step 7c): Phase deklariert keine `probe-*.sh`; übersprungen.

### Anforderungsabdeckung

Alle 16 Phasen-IDs sind in PLAN-Frontmatter beansprucht und in REQUIREMENTS.md vorhanden. Orphaned: keine. Zusätzlich beanspruchen Pläne REQ-IBKR-37, -69, -70 (Teil von Phase 3/Querschnitt, kein Mangel).

| Requirement | Plan(e) | Status | Evidenz |
|---|---|---|---|
| REQ-IBKR-13 | 01, 04, 07, 09 | ERFÜLLT | Lesen nur aus `decision-log.md` per `load_entries`, `summary.json` nur Vorbedingung; `test_only_log_and_summary_paths_are_read` |
| REQ-IBKR-14 | 01, 07 | ERFÜLLT | `schema_version != 1` → `summary-schema`, Exit 1 (Hinweis: Exit 1 laut Req und Test) |
| REQ-IBKR-15 | 07, 09 | ERFÜLLT | `verify` auf Kopie, Befund/leere Datei → `log-finding`, Exit 2 |
| REQ-IBKR-16 | 01, 07 | ERFÜLLT | `null`/`REVIEW`/`status != ok` je eigener Zustand |
| REQ-IBKR-17 | 01, 07 | ERFÜLLT | Divergenz, Exit 2 |
| REQ-IBKR-18 | 01, 04, 07 | ERFÜLLT | nie `runs[*].report` |
| REQ-IBKR-19 | 03, 06, 07 | ERFÜLLT | `freshness` in XNYS-Sitzungen, `stale-decision` Exit 2 |
| REQ-IBKR-20 | 06, 07 | ERFÜLLT | `weekend_gap` markiert (Phase-4-Protokoll; Ledger folgt Phase 5) |
| REQ-IBKR-21 | 01, 07, 09 | ERFÜLLT | Buy 2, Overweight 1, Underweight/Sell 0, Hold nie Order |
| REQ-IBKR-22 | 03, 07 | ERFÜLLT | `block_qty` als Code-Konstante je Ticker, keine Kursableitung |
| REQ-IBKR-23 | 01, 05, 07 | ERFÜLLT | `Ziel − Ist − offen`, Toleranzband |
| REQ-IBKR-24 | 01, 07 | ERFÜLLT | long-only, `long-only-noop` |
| REQ-IBKR-25 | 02, 05, 07 | TEILWEISE (Warnung) | MKT/DAY-Order, offene Orders in der Differenz erfüllt; "konfiguriertes Fenster (nicht Auktion/Schlussminuten)" nicht im Code, Entscheidung beim Operator (Human-Verification 4) |
| REQ-IBKR-38 | 01, 02, 05, 07, 08, 09 | ERFÜLLT (Phase-4-Teil) | whatIf vor jeder Absicht, Margin/Kommission/`reject_reason` protokolliert; Preview-Ablehnung verhindert Order. Vor jeder *echten* Order ist Phase 6 |
| REQ-IBKR-61 | 01, 05, 07 | ERFÜLLT | leere/unlesbare Vorschau → `preview-empty`, Exit 5 |
| REQ-IBKR-68 | 03, 05, 07, 09 | ERFÜLLT im committeten Stand | keine Marktdaten im Order-Pfad, Wächter `test_no_market_data_in_execution_path`; die uncommittete Operator-Änderung verletzt ihn lokal (siehe Beobachtung) |

### Anti-Patterns

Keine Schuldmarker, keine Stubs im Phase-4-Code gefunden. Die Zustandstabelle im Handbuch ist durch `test_handbook_state_table_matches_decision_module` gegen `EXIT_BY_STATE` gepinnt.

### Offene Punkte (Gaps)

Keine blockierenden Gaps. Warnungen: (1) ROADMAP-SC2 trägt noch den überholten 321-Satz, (2) Fehler 154 nur per Fake-Test, (3) REQ-25 Sitzungsfenster, (4) der reale Trockenlauf ist nur aus SUMMARY/Operator-Aussage belegt.

## Human-Verification (Zusammenfassung)

1. D-14: SC2-Satz zu 321 ersetzen und bestätigen; Schalter bleibt AUS (Stand AUS bestätigt 2026-10-12).
2. Fehler-154-Lücke (A5, REQ-67-bezogen) akzeptieren.
3. Realen Trockenlauf (sha 7b4af23…, Exit 2, sent false) als Operator-Nachweis festhalten.
4. REQ-25-Sitzungsfenster: Zuschnitt Phase 4 oder spätere Phase entscheiden.

---

_Verifiziert: 2026-10-12_
_Verifier: Claude (gsd-verifier)_
