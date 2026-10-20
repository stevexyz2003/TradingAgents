---
phase: 06-die-erste-echte-order
verified: 2026-10-20T00:00:00Z
status: passed
score: 7/7 Roadmap-SCs verifiziert (davon SC1 und SC7 mit dokumentierter Abweichung, Zielerreichung mit Operator-Overrides D-03 und D-15)
overrides_applied: 2
overrides:
  - must_have: "Die erste Order kommt aus dem, was der Paper-Log am Tag hergibt: die jüngste frische Entscheidung, die eine BUY-Order ergibt; gibt es keine, wird keine Entscheidung künstlich erzeugt (D-03, 06-09-Truth 2)"
    reason: "20 von 20 Engine-Entscheidungen für trade_date 2026-10-16 ohne BUY. Der Operator hat D-03 gelockert: die erste Order ist ein markierter Pipeline-Test (Branch fork/paper-log-pipeline-test @ 8453e76, Eintrag 'OPERATOR-APPROVED PIPELINE TEST, NOT AN ENGINE DECISION'), Executor-Code unverändert, paper-log unverändert. Bewiesen ist die Order-Pipeline, NICHT eine Engine-getriebene Order."
    accepted_by: "operator"
    accepted_at: "2026-10-19T15:27:00Z"
  - must_have: "Am Tag der ersten Order ist der gesperrte Zustand im scharfen Pfad frisch belegt: mit eingeschaltetem Read-Only API endet execute <TICKER> --live an der Vorschau mit preview-read-only (321), Exit 5 (D-15, 06-09-Truth 3)"
    reason: "Gemessen endet der Lauf früher, bei reqCompletedOrders mit 321 (reqId -1) und REQUEST_TIMEOUT Exit 3; fail-closed, kein intent, 321 im Log, Sonde READ_ONLY_API maschinell geprüft. Abweichung in Handbuch und Befund dokumentiert. Genauere Diagnose als Todo: .planning/todos/pending/06-read-only-321-in-read-window.md"
    accepted_by: "operator"
    accepted_at: "2026-10-20T15:00:00Z"
human_verification_resolved:
  - "pytest tests -k ibkr: 1357 passed; ruff check .: sauber (2026-10-20, vom Orchestrator nachgefahren)"
  - "D-15-Abweichung vom Operator per Override akzeptiert (2026-10-20)"
  - "Commit dieser Datei: 8a325e2"
---

# Phase 6: Die erste echte Order — Verifikationsbericht

**Phasenziel:** Eine echte Markt-Order gegen `DUQ634065` wird platziert, gefüllt und vollständig im Ledger wiedergefunden — und ein zweiter Lauf am selben Tag erzeugt keine zweite.
**Verifiziert:** 2026-10-20
**Status:** passed (nach Operator-Entscheidung zur D-15-Abweichung am 2026-10-20; pytest/ruff nachgefahren)
**Re-Verifikation:** Nein, Erstverifikation

**Vorbemerkung zur Methode:** Die Bash-Shell war während der gesamten Verifikation unbenutzbar (jeder Aufruf lief in den Timeout, auch `echo ok`). Belegt wurde deshalb über direktes Lesen von Code, Tests, Handbuch, Befund, dem echten Live-Ledger (`%LOCALAPPDATA%\TradingEngineX\ibkr\ledger.jsonl`, nur gelesen) und `.git/logs/HEAD` (Commit-Zeitstempel). pytest, ruff und der Commit dieser Datei stehen aus (siehe „Human Verification“).

**Hinweis:** Die Roadmap führt **sieben** Success Criteria (SC1–SC7), nicht sechs. Alle sieben sind unten geprüft.

## Zielerreichung

### Einordnung des Pipeline-Tests (D-03, Operator-Override)

Die erste Order kam **nicht** aus einer Engine-Entscheidung. Nach 20/20 Engine-Entscheidungen ohne BUY (AAPL/MSFT/NVDA vom 17.10., 17 weitere Ticker aus zwei `workflow_dispatch`-Runs am 19.10.) hat der Operator D-03 gelockert. Die Entscheidung `[2026-10-16 | AAPL | Overweight | pending]` stammt vom markierten Branch `fork/paper-log-pipeline-test` (`8453e76`), der Text trägt „OPERATOR-APPROVED PIPELINE TEST, NOT AN ENGINE DECISION“. Der Executor-Code blieb unverändert, der Branch wurde nur per `--env-file` mit `IBKR_PAPER_LOG_BRANCH` eingespeist.

**Urteil:** Das Phasenziel lautet „eine echte Markt-Order wird platziert, gefüllt und im Ledger wiedergefunden; ein zweiter Lauf erzeugt keine zweite“. Es ist zur Order-**Pipeline** formuliert, nicht zur Herkunft der Entscheidung. Die Roadmap sagt ausdrücklich: „Die Mechanik ist tickerunabhängig“ und „ein Durchstich genügt“. Die ganze Prüfkette (paper-log-Abruf, `summary.json`-/Jev-Abgleich, Frische, Auflösung, Größe, Sitzung, Schalter, whatIf, `intent`, Senden, Kontrolle nach der Order, Fills) lief unverändert durch. Damit ist das Ziel erreicht. Was diese Order **nicht** beweist: dass eine echte Engine-Entscheidung bis zur Order durchkommt. Diese Lücke ist als Operator-Override in der Frontmatter erfasst, nicht stillschweigend als Pass gewertet.

Folge-Unschärfe: Das Ledger trägt beim `intent` `rating_source: "engine"` (Zeile seq 5), weil nur `engine` gehandelt wird. Die Herkunft „Pipeline-Test“ ist im Ledger selbst nicht erkennbar, nur über `paper_log_sha` `8453e764…`, `preview.json` und den Befund. Siehe Warnungen.

### Observable Truths (Roadmap-Success-Criteria)

| # | Truth | Status | Evidenz |
|---|-------|--------|---------|
| SC1 | Freischaltung mit Datum, Grund, Vorher/Nachher im Handbuch; gesperrter Zustand vorher über 321 belegt | ✓ VERIFIED (mit Abweichung D-15, siehe unten) | `scripts/IBKR_EXECUTION.md` Z. 49–50: „2026-10-19 17:28 MESZ on … before: off“ und „17:36 MESZ off … before: on. API write access enabled for the first live order (REQ-10); stays off afterwards, D-04“. Commit `698cffe` („record the API write enable“) laut Reflog um 15:37:00 UTC, also vor `ORDER_SENT` 15:37:12 UTC. 321-Beleg: Sonde `READ_ONLY_API` mit `[321, …]` um 15:28:37 UTC, maschinelle Prüfung Exit 0; im `--live`-Lauf um 15:30:14 UTC `Warning 321, reqId -1` und `ibkr-state=READ_ONLY_API code=321` im Log; Live-Ledger seq 1–2: `run_start` und `run_end outcome=error`, kein `intent` |
| SC2 | Prüfkette an genau einer Stelle, Reihenfolgetest gegen Stub-Broker mit den vier Abweichungen | ✓ VERIFIED | `tests/test_ibkr_call_order.py::test_live_call_order_follows_req45_with_four_deviations` prüft die Aufrufreihenfolge als Teilfolge eines Ereignisstroms (lock → kill → run_start → open/completed/executions → reconcile → fetch → contract_details/qualify → positions → quantity → size → session → kill → whatIf → switch_check → intent → disk → placeOrder → placed → filled), die Abweichungen 1–3 einzeln; `test_live_call_order_key_check_after_freshness` deckt Abweichung 4 ab; `test_live_call_order_pins_quantity_size_session_kill_before_whatif` pinnt `quantity < size < session < kill < whatif < intent < place`. Genau eine Sendestelle: AST-Test `test_place_order_called_at_one_site` (`test_ibkr_execute.py:2787`) |
| SC3 | Echte Markt-Order über einen Block; Ledger zeigt `intent → placed → filled` mit `orderId`, `permId`, `orderRef == decision_key`, `execId`, `filled_qty`, `avg_price` | ✓ VERIFIED (Feldname-Vorbehalt) | Live-Ledger seq 5 `intent` (BUY 1, `order_ref` = `decision_key` = `2026-10-16\|AAPL`), seq 6 `placed` (`order_id` 18, `perm_id` 717633249, Filled), seq 7 `filled` (`exec_id` `0000e0d5.6ad60c69.01.01`, `filled_qty` 1.0, `price` 342.86, `order_ref` = Key). **Vorbehalt:** die Live-Zeile trägt `price`, nicht `avg_price`. Grund: der erste Lauf lief wegen des Fehlalarms über den Alarmpfad (`_deviation`, `fills_booked: true`), der nur `fill_records` schreibt; `avg_price`/`completed_status` setzt nur der saubere Pfad (`ibkr_executor.py:1307-1308`). Bei einer einzigen Execution ist `price` gleich dem Durchschnittspreis, und `ibkr_report._fills` rechnet den Durchschnitt aus `price`. Danach folgt seq 8 `alarm` (`post-order-mismatch`), ein Fehlalarm, der als historische Zeile stehen bleibt |
| SC4 | Position = Ziel der Leiter; zweiter Lauf am selben Tag ohne zweite Order; Toleranzband, Ledger-Guard und Reconciliation greifen zusammen | ✓ VERIFIED | Live: seq 10–12 `run_start`, `skipped reason=already_attempted`, `run_end exit 2`; kein zweites `placed`; Historie danach open 0 / completed 1 / executions 1; Position AAPL 1.0 = Overweight = 1 Block (Befund Messung 4). Live wirkte nur der Ledger-Guard. Die Reconciliation hatte nichts Offenes (Eintrag durch `filled` geschlossen, daher keine `reconcile`-Zeile), das Toleranzband wurde nicht erreicht. Das Zusammenspiel ist per Test belegt: `TestSecondRun::test_live_second_run_same_day_places_no_second_order` und `test_live_second_run_next_day_is_within_tolerance` (Folgetag: `within-tolerance`, kein `source-conflict`, kein Exit 6, kein `placeOrder`) sowie `test_fills_are_persisted_in_the_same_run_for_the_next_day` |
| SC5 | execId-Korrekturregel: `.02` ersetzt `.01` | ✓ VERIFIED (Fixture, D-13) | Live keine Korrektur (nur `.01.01`). Fixture-Familie `0000e0d5.6710a3c5` hat dieselbe Form wie die echte execId `0000e0d5.6ad60c69.01.01`. Tests: `test_ibkr_ledger.py::test_exec_id_correction_replaces_the_earlier_execution`, `test_exec_id_correction_does_not_double_the_resolved_quantity` (2 + 2 als `.01`/`.02` ergibt 2, nicht 4), `test_signed_filled_quantity_counts_a_correction_once`, `test_ibkr_execute.py::test_reconcile_correction_writes_one_fill_row_for_the_corrected_execution` |
| SC6 | Executions und abgeschlossene Orders am selben Tag persistiert | ✓ VERIFIED | Execution: Live-Ledger seq 7 um 15:37:12 UTC, im selben Lauf. Abgeschlossene Order: auf dem Live-Lauf in `alarm.seen` (`status` Filled, `filled` 1.0, `perm_id`, `order_ref`); auf dem sauberen Pfad als `completed_status`/`completed_filled` in der `filled`-Zeile. Rohform zusätzlich im Befund (Messung 3). Test: `test_fills_are_persisted_in_the_same_run_for_the_next_day` (Folgetag mit leerer Broker-Historie, Ledger allein kennt die Fills, `filled_quantity == 2`) |
| SC7 | whatIf mit Reject verhindert die Order im scharfen Pfad, Exit 5 | ✓ VERIFIED (per D-12 via Stub) | `test_ibkr_call_order.py::test_live_whatif_reject_blocks_the_order`: Fehler 201 während des whatIf ergibt `EXIT_REJECTED`, `rejected` mit `preview-rejected`, kein `intent`, kein `placeOrder`. D-12 klärt vorab, dass kein echter IBKR-Reject provoziert wird (`MAX_QTY_PER_ORDER = 2` stoppt vorher) und dass das keine Lücke ist |

**Score:** 7/7 Roadmap-SCs verifiziert. D-03 gilt per Operator-Override. Die D-15-Abweichung braucht eine Entscheidung (siehe unten).

### Bewertung der D-15-Abweichung (321-Beleg mit Exit 3 statt Exit 5)

- **Erwartet (D-15, 06-09-Truth 3):** Mit Read-Only an endet `execute --live` am whatIf als `preview-read-only`, Exit 5.
- **Gemessen:** Die Sperre greift früher. `reqCompletedOrders` (Startup-Reconciliation) bekommt eine 321 mit `reqId -1` und keine Antwort. Das Lesefenster läuft nach 10 s ab, der Lauf endet mit `REQUEST_TIMEOUT`, Exit 3.
- **Ursache im Code:** `scripts/ibkr_broker.py:162-172` führt 321 in `WINDOW_BENIGN_CODES` („read-only API, owned by the preview“). Eine 321 ohne Request-Bezug im Lesefenster wird also ignoriert, und das Fenster läuft in den Timeout. Nicht geändert.
- **Urteil:** SC1 verlangt, dass der gesperrte Zustand vorher **über Fehler 321 belegt** ist. Das ist erfüllt: die Sonde misst `READ_ONLY_API`/321 maschinell geprüft, und die 321 steht im Log des `--live`-Laufs. Kein `intent`, kein `placeOrder`, fail-closed. Die Sicherheitseigenschaft gilt also. Nicht erfüllt ist der **Wortlaut** der Plan-Truth (Exit 5, `preview-read-only`). Außerdem ist die Diagnose ungenau: Exit 3 sagt dem Operator „Gateway nicht verfügbar“ statt „Read-Only an“. Handbuch (Z. 52–59, 70–73, 1002–1004) und Befund dokumentieren die Abweichung.
- **Zusätzlich:** `tests/test_ibkr_call_order.py:357-365` (`test_live_read_only_ends_at_the_preview`) modelliert ein Gateway, das die 321 erst am whatIf meldet. Der Kommentar sagt „This is the state measured on the day of the first order (06-09)“, und das ist nach der Messung falsch. Der Test prüft weiter einen gültigen Pfad (321 am whatIf, z. B. über `preview`), bildet aber den gemessenen `--live`-Ablauf nicht ab.
- **Einstufung:** WARNING, keine BLOCKER. Override-Vorschlag:

```yaml
overrides:
  - must_have: "Am Tag der ersten Order ist der gesperrte Zustand im scharfen Pfad frisch belegt: mit eingeschaltetem Read-Only API endet execute <TICKER> --live an der Vorschau mit preview-read-only (321), Exit 5"
    reason: "Gemessen endet der Lauf früher, bei reqCompletedOrders mit 321 (reqId -1) und REQUEST_TIMEOUT Exit 3; fail-closed, kein intent, 321 im Log, Sonde READ_ONLY_API maschinell geprüft. Abweichung in Handbuch und Befund dokumentiert."
    accepted_by: "{operator}"
    accepted_at: "{ISO timestamp}"
```

### Fehlalarm nach der Order: Fixes `28ef33a` und `46c432b`

| Prüfung | Ergebnis |
|---|---|
| Commits existieren, Reihenfolge | `.git/logs/HEAD`: `28ef33a` um 15:57:45 UTC („ignore the zero order size the gateway reports on completed orders“), `46c432b` um 15:58:06 UTC („accept a zero quantity on completed orders in the reconciliation“), beide vor dem zweiten Lauf (15:59:10 UTC) |
| Prüfung nach der Order | `scripts/ibkr_executor.py:1522-1526`: `if order.quantity and float(order.quantity) != want`. Eine 0 gilt als unbekannt, eine andere Menge ungleich 0 alarmiert weiter. Die Größe tragen `order.filled` (Z. 1527) und die Summe der effektiven Executions (Z. 1542-1544). Die Prüfung ist also nicht aufgeweicht, sondern verlagert |
| Reconciliation | `scripts/ibkr_ledger.py:653-676`: Twin-Erkennung `finished.get(perm_id) not in (0.0, float(order.quantity))` und Kollision `size_differs = bool(order.quantity) and …` |
| Tests, positiv | `test_ibkr_execute.py:2573` `test_completed_order_with_zero_quantity_is_a_clean_fill` (quantity 0, orderId 0, kein Alarm, Kette intent→placed→filled); `test_ibkr_ledger.py:655` `…zero_quantity_is_filled_out`, `:662` `…zero_quantity_twin_in_both_answers_is_one_order` |
| Tests, negativ (Schärfe erhalten) | `test_ibkr_ledger.py:671` `test_reconcile_finished_twin_with_another_size_is_a_collision`, `:705` Kollision bei `qty=5.0`; `test_ibkr_execute.py:2629` `test_post_order_mismatch_stops_the_whole_run` mit Fall `order-quantity` und `order-short` |
| Handbuch | `IBKR_EXECUTION.md:619-623` und 999-1001 beschreiben die Regel |
| Review | Die beiden Fixes liegen **nach** dem Code-Review (06-REVIEW vom 2026-10-19 deckt `1d2e28c..HEAD` vor 15:57) und sind nicht gereviewt. Sie sind klein und getestet. INFO |

Urteil: Die Fixes sind korrekt, minimal und in beide Richtungen getestet. Ausgeführt wurden die Tests vom Verifier nicht (Shell).

### Required Artifacts

| Artefakt | Erwartet | Status | Details |
|---|---|---|---|
| `scripts/ibkr_executor.py` | `--live`, `LivePlacer`, Kontrolle nach der Order, Exits 9/10 | ✓ VERIFIED | `EXIT_POST_ORDER = 10` (Z. 111), `_read_back`/`_compare`/`_fills_are_final`, eine Sendestelle; Live-Ledger belegt den echten Durchlauf |
| `scripts/ibkr_ledger.py` | Korrekturregel, signierte Fills, `alarm`, Reconciliation | ✓ VERIFIED | `effective_executions`, `filled_quantity` signiert, `fill_records`, `resolve_entry` mit 0-Mengen-Regel |
| `scripts/ibkr_broker.py` | Order-Permit, `place_order` | ✓ VERIFIED | Review-Befunde CR-01, WR-01, IN-01 als behoben vermerkt, Commits im Reflog vorhanden |
| `scripts/IBKR_EXECUTION.md` | Freischaltung, `--live`, First live order | ✓ VERIFIED | Abschnitte „Gateway Read-Only switch“, „execute“, „After the order is sent“, „First live order“ |
| `.planning/ibkr-konto-befund.md` | Messungen 1–4 Phase 6 | ✓ VERIFIED | Z. 500–791 |
| `ledger.jsonl` (live) | Kette und zweiter Lauf | ✓ VERIFIED | 12 Zeilen, siehe oben |
| Tests `test_ibkr_call_order.py`, `test_ibkr_execute.py`, `test_ibkr_ledger.py` | SC2, SC4–SC7, Fix-Tests | ✓ vorhanden / ? nicht ausgeführt | Statisch gelesen; Ausführung offen |

### Key Link Verification

| Von | Nach | Via | Status |
|---|---|---|---|
| `execute --live` | `LivePlacer.complete` → `broker.place_order` | Placer-Naht nach `intent` (fsync) | ✓ WIRED (Test `test_intent_before_place`, Live seq 5 → 6) |
| `LivePlacer` | `order_history()` → `_compare` → `alarm`/`fill_records` | `_read_back` | ✓ WIRED (Live seq 7–8) |
| zweiter Lauf | Ledger-Guard `already_attempted` | Schlüsselprüfung nach Frische | ✓ WIRED (Live seq 11) |
| Startup | `_reconcile` → `resolve_entry` | offene Einträge | ✓ WIRED (Test; live nichts offen) |
| `summary.json` | `rating_source` → `intent` | D-05/D-07 | ✓ WIRED (Live seq 5 `rating_source`) |

### Behavioral Spot-Checks

| Verhalten | Befehl | Ergebnis | Status |
|---|---|---|---|
| ibkr-Suite grün | `.venv/Scripts/python.exe -m pytest tests -k ibkr` | nicht ausführbar, Shell hängt | ? SKIP → Human |
| Lint | `.venv/Scripts/python.exe -m ruff check .` | nicht ausführbar | ? SKIP → Human |
| Echte Order im Ledger | Live-Ledger gelesen | Kette und zweiter Lauf wie erwartet | ✓ PASS |
| Handbuch-Commit vor Order | `.git/logs/HEAD` | `698cffe` 15:37:00 < `ORDER_SENT` 15:37:12 | ✓ PASS |

### Probe Execution

Keine `scripts/*/tests/probe-*.sh` für diese Phase deklariert. Die Sonde `scripts/smoke/ibkr_order_probe.py` braucht das Gateway und wurde gemäß Auftrag nicht ausgeführt. Ihre Ergebnisse stehen im Befund.

### Requirements Coverage

| Requirement | Quell-Plan | Beschreibung | Status | Evidenz |
|---|---|---|---|---|
| REQ-IBKR-10 | 06-09, 06-10 | Schreibrecht als dokumentierte Einmalhandlung, vorher 321 | ✓ SATISFIED | Handbuch-Tabelle, Commit vor der Order, 321 per Sonde und im Live-Log (Exit-Abweichung siehe D-15) |
| REQ-IBKR-45 | 06-04, 06-08 | Prüfkette an einer Stelle, Reihenfolge getestet | ✓ SATISFIED | `test_ibkr_call_order.py` |
| REQ-IBKR-47 | 06-01, 06-05 | Fills pro execId, Dedup, Korrekturregel | ✓ SATISFIED | Ledger-Tests, Live seq 7 |
| REQ-IBKR-48 | 06-05, 06-06, 06-10 | Executions und abgeschlossene Orders am selben Tag | ✓ SATISFIED | Live seq 7–8, Persistenz-Test |
| REQ-IBKR-65 | 06-05, 06-10 | Zustand nach der Order lesen und vergleichen, Abweichung = Alarm | ✓ SATISFIED | `_compare`, Live-Alarm hat real ausgelöst (Fehlalarm, korrigiert, Schärfe erhalten) |

Keine verwaisten Requirements. REQUIREMENTS.md ordnet Phase 6 genau diese fünf IDs zu.

### Anti-Patterns

| Datei | Zeile | Muster | Schwere | Wirkung |
|---|---|---|---|---|
| `scripts/ibkr_*.py` (5 Dateien) | — | TBD/FIXME/XXX/TODO/HACK | — | keine Treffer |
| `tests/test_ibkr_call_order.py` | 358-359 | Kommentar behauptet gemessenen Zustand, der der Messung widerspricht | ⚠️ Warning | irreführend für spätere Leser |
| `scripts/ibkr_broker.py` | 162-172 | 321 als „benign“ im Lesefenster | ⚠️ Warning | Read-Only im `--live`-Pfad wird als Exit 3 statt Exit 5 diagnostiziert |
| Live-Ledger | seq 8 | historische `alarm`-Zeile (Fehlalarm) | ℹ️ Info | bleibt append-only stehen; Phase-7-Bericht sollte sie nicht als echte Abweichung werten |

### Warnungen (nicht blockierend, nicht als Todo erfasst)

1. **321 mit `reqId -1` im Lesefenster → `REQUEST_TIMEOUT` (Exit 3) statt `READ_ONLY_API` (Exit 5).** Sicher, aber falsche Diagnose; der zugehörige Test modelliert die Realität nicht. Unter `.planning/todos/pending/` gibt es kein Todo dafür.
2. **Herkunft im Ledger:** Der Pipeline-Test trägt `rating_source: engine`; ein Marker wie `pipeline_test` fehlt im Ledger. Phase 7 (Soll/Ist-Bericht) wertet die Order sonst als Engine-Order. Kein Todo.
3. **`summary.json` wird bei einem zweiten Paper-Run auf dasselbe `trade_date` überschrieben** (Befund 06-09), fail-closed `summary-missing`. Kein Todo.
4. **SC3-Feldname:** Die Live-`filled`-Zeile hat `price` statt `avg_price` (Alarmpfad). Inhaltlich gleichwertig bei einer Execution. Der saubere Pfad ist per Test belegt, aber nicht live gelaufen.
5. **Fixes `28ef33a`/`46c432b` nach dem Code-Review, nicht gereviewt.** INFO.

### Human Verification Required

### 1. Testsuite und Lint

**Test:** `.venv/Scripts/python.exe -m pytest tests -k ibkr` und `.venv/Scripts/python.exe -m ruff check .`
**Erwartet:** ibkr-Tests grün, ruff sauber; in der vollen Suite nur die 6 bekannten Fehler (`test_yfinance_keeps_its_cache_out_of_the_users_home` plus 5 Windows-bedingte in `test_chatgpt_auth.py`, `test_cli_commands.py`, `test_cli_updates.py`)
**Warum Mensch:** Die Verifier-Shell war tot; Tests nur statisch gelesen.

### 2. D-15-Abweichung entscheiden

**Test:** Override (Vorschlag oben) eintragen oder Gap-Closure-Todo anlegen (321/`reqId -1` im Lesefenster zuordnen, `test_live_read_only_ends_at_the_preview` korrigieren bzw. um den gemessenen Fall ergänzen)
**Erwartet:** bewusste Entscheidung statt stiller Akzeptanz
**Warum Mensch:** Abweichung vom Wortlaut eines Plan-Must-haves, die bisher keine ausdrückliche Operator-Abnahme hat.

### 3. Commit nachholen

**Test:** `git add .planning/phases/06-die-erste-echte-order/06-VERIFICATION.md` und `git commit -m "docs(06): add phase verification"` mit der Co-Authored-By-Zeile
**Warum Mensch:** Die Verifier-Shell konnte nicht committen.

### Gaps Summary

Das Phasenziel ist im Code und am Konto erreicht. Eine echte Markt-Order (BUY 1 AAPL, orderId 18, permId 717633249, 342.86 USD) wurde platziert, gefüllt und mit der vollständigen Kette `intent → placed → filled` im Live-Ledger wiedergefunden. Der zweite Lauf am selben Tag endete mit `already-attempted` und ohne zweite Order. Die Position entspricht der Leiter. Der Fehlalarm nach der Order ist ursächlich verstanden. Der Fix ist korrekt, eng und in beide Richtungen getestet.

Zwei Einschränkungen sind ausdrücklich zu benennen. Erstens kam die Order per Operator-Override D-03 aus einem markierten Pipeline-Test, nicht aus der Engine: bewiesen ist die Order-Pipeline, nicht eine Engine-getriebene Order. Zweitens endete der 321-Beleg im `--live`-Pfad mit Exit 3 statt Exit 5. Das ist fail-closed und belegt den Zustand, weicht aber vom Plan-Wortlaut ab und ist diagnostisch ungenau. Dazu kommen vier nicht erfasste Warnungen (Diagnose 321, Herkunftsmarker im Ledger, Überschreiben von `summary.json`, `avg_price` auf dem Alarmpfad). Keine davon blockiert das Phasenziel. Status `human_needed`, weil Tests und Lint vom Verifier nicht ausgeführt werden konnten und die D-15-Abweichung eine Entscheidung braucht.

---

_Verifiziert: 2026-10-20_
_Verifier: Claude (gsd-verifier)_
