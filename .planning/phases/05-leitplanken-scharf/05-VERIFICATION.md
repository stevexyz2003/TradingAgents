---
phase: 05-leitplanken-scharf
verified: 2026-10-17T14:00:00Z
status: passed
score: 8/8 Success Criteria verifiziert
overrides_applied: 0
gaps: []
human_verification: []
---

# Phase 5: Leitplanken scharf - Verifikationsbericht

**Ziel:** Die vier Pflicht-Leitplanken sind scharf und ohne eine einzige Order bewiesen.
**Verifiziert:** 2026-10-17
**Status:** passed
**Re-Verifikation:** Nein, Erstverifikation

## Eigene Läufe (nicht aus den SUMMARYs übernommen)

| Prüfung | Ergebnis |
|---|---|
| `pytest tests -k ibkr` | 956 passed |
| `pytest -k "g3 or negative_control"` | 29 passed |
| Gesamtsuite (ohne bekannten Altfehler `test_yfinance_keeps_its_cache_out_of_the_users_home`) | 2425 passed, 4 skipped |
| `ruff check .` | All checks passed |
| `git status --porcelain` | nur `?? .planning/debug/` (Operator-Stand, nicht Teil der Phase) |
| Marker `TBD`/`FIXME`/`XXX` in `ibkr_guards.py`, `ibkr_ledger.py`, `ibkr_executor.py`, `ibkr_broker.py`, `ibkr_order_probe.py` | 0 Treffer |
| `placeOrder` in `scripts/ibkr_executor.py` | 0 Treffer; `EXECUTE_FORCED_DRY = True` (Zeile 131), `DryPlacer` |

## Success Criteria

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| SC1 | Fail-closed in drei Varianten, Exit 4, kein Platzierungsaufruf, Schalterzustand protokolliert | VERIFIZIERT | `_check_switches` (executor:1237) liest `RELEASE`/`KILL` bei jedem Aufruf neu; Matrix-Tests in `test_ibkr_execute.py` (fehlend, Verzeichnis, UTF-16, abgelaufen, falsches Konto, `os.stat` wirft); `test_preflight_switch_state_is_logged_when_blocked`; `run_start` enthält `release`/`kill`. Auch live gemessen: `SWITCHES release=release-ok kill=kill-active`. |
| SC2 | Kill zwischen zwei Orders verhindert die zweite | VERIFIZIERT | `_check_switches` vor whatIf (executor:2132) und vor `intent` (2193); `test_g3_kill_between_two_orders` plus Negativ-Kontrolle `test_negative_control_kill_between_checked_once_per_run`. |
| SC3 | `reqGlobalCancel` bei Kill, gegen Stub und einmal am Broker mit manueller Order | VERIFIZIERT | Einzige `cancel_all`-Stelle `_kill_path` (executor:1288, AST-Test); Einmal-Permit im Adapter. Live in `ibkr-konto-befund.md` (Abschnitt "Kill-Storno ...", 2026-10-17): manuelle TWS-Order `permId 1440521754`, `execute AAPL` mit `KILL` ergibt Exit 4, `GLOBAL_CANCEL_SENT count=1`, `KILL_CANCEL remaining=0`, Historie zeigt `Cancelled`. |
| SC4 | Über `MAX_QTY_PER_ORDER` wird abgelehnt und gemeldet, nicht gekürzt | VERIFIZIERT | `MAX_QTY_PER_ORDER = 2` (guards:303), `check_size` vor dem whatIf (executor:2111) und im `DryPlacer` ein zweites Mal; `test_size_cap_sell_above_cap_is_rejected_not_trimmed`, Negativ-Kontrolle `..._removed_would_send_three`, Sentinel koppelt `BLOCKS x block_qty` an die Grenze. |
| SC5 | Ledger JSONL, außerhalb jedes Git-Baums, `git status` unverändert, kein Lock-Sidecar im Baum | VERIFIZIERT | `ensure_outside_git` vor `mkdir` (executor:1181), Exit 1 `STATE_IN_GIT_TREE`; `test_execute_run_leaves_git_status_unchanged` (isolation:454) vergleicht vorher/nachher und prüft die fünf State-Pfade; Sidecar `ledger.jsonl.lock` liegt im State-Ordner. Gemäß der Klarstellung vom 2026-10-17 (porcelain gleich vor/nach) geprüft. |
| SC6 | Write-Ahead und Reconciliation gegen drei Quellen, Exit 6 bei unauflösbarem `intent` | VERIFIZIERT | `intent` mit fsync vor `placer.complete`; `_reconcile` (executor:1483) vor `paper_log_factory`; `order_history()` liest `reqAllOpenOrders`, `reqCompletedOrders`, `reqExecutions`; Tests `test_g3_reconcile_*`, `test_write_ahead_negative_control_*`, `test_negative_control_reconcile_removed_would_create_new_intent`. Torn-Tail-Siegel (8eefa43) gesehen und durch `test_write_ahead_torn_tail_tolerated_at_cli` gedeckt. |
| SC7 | Zweiter Lauf Exit 7; `OSError` beim Sperrversuch gleich "nicht ausführen" | VERIFIZIERT | `locked(..., wait=False)` (executor:1200) als äußerste Klammer; `test_lock_held_second_run_exit_seven`, `test_lock_oserror_is_exit_seven_without_traceback`; `OSError` im Lauf wird bewusst nicht als Exit 7 gewertet (`test_lock_oserror_inside_the_run_is_not_exit_seven`). |
| SC8 | `decision_key` als `orderRef`, SHA als Provenienz, abweichende Fassung protokolliert und nicht ausgeführt | VERIFIZIERT | `order_ref=key` an whatIf/intent (executor:2144, 2209); `_check_attempts` mit `already-attempted` / `decision-changed` inkl. `paper_log_sha` und `first_paper_log_sha`; Tests `test_decision_changed_second_version_is_logged_not_executed`, `test_already_attempted_*`. Live bestätigt: `orderRef` mit `|` wird angenommen, Echo identisch, Konto im Echo. |

## Anforderungsabdeckung

| ID | Status | Beleg |
|---|---|---|
| REQ-IBKR-25 (Sitzungsfenster) | ERFÜLLT | `CLOSED` aus `evaluate_session` mit Puffer wird zu `outside-session` vor dem whatIf (05-06) |
| REQ-IBKR-32 | ERFÜLLT | SC4 |
| REQ-IBKR-33 | ERFÜLLT | SC1 |
| REQ-IBKR-34 | ERFÜLLT | SC2 |
| REQ-IBKR-35 | ERFÜLLT | SC3 |
| REQ-IBKR-36 | ERFÜLLT | `run_start`/`run_end` tragen Schalterzustand in jedem Lauf (auch inaktiv) |
| REQ-IBKR-39 | ERFÜLLT | `decision_key` ohne SHA, `DECISION_KEY_SEPARATOR = "|"`, live bestätigt |
| REQ-IBKR-40 | ERFÜLLT | SC8, `Ledger.attempt_of` |
| REQ-IBKR-41 | ERFÜLLT | SC8 |
| REQ-IBKR-42 | ERFÜLLT | Write-Ahead, `REASON_BY_STATE`, jedes `skipped` mit Grund |
| REQ-IBKR-43 | ERFÜLLT | SC6 |
| REQ-IBKR-44 | ERFÜLLT | SC7 |
| REQ-IBKR-46 | ERFÜLLT | SC5 |
| REQ-IBKR-63 | ERFÜLLT | Zwei-Quellen-Vergleiche (Konto Exit 8, Position, "schon ausgeführt", Kalender) in 05-07 |
| REQ-IBKR-64 | ERFÜLLT | SC1/SC2, Prüfung vor jeder Order |
| REQ-IBKR-66 | ERFÜLLT | Negativ-Kontrollen zu Kill, Größe, Write-Ahead, Reconciliation (29 Tests grün) |

Alle 16 IDs aus der Phasenvorgabe sind in den Plänen (Frontmatter `requirements-completed`) und in REQUIREMENTS.md auffindbar. Verwaiste Anforderungen: keine.

## Gate G3

Alle vier Nachweise (Kill-, Größen-, Sitzungs-, Reconciliation-Test) laufen ohne Gateway grün (`-k g3`: 14 Tests). Das Schreibrecht bleibt gesperrt: `EXECUTE_FORCED_DRY`, kein `placeOrder`, Nachricht 58 nur über das Einmal-Permit von `cancel_all`.

## Hinweise (keine Lücken)

1. SC3 wurde über TWS Paper (Port 7497) statt IB Gateway gemessen, weil pro Benutzer nur eine Sitzung läuft. Die API ist dieselbe (Serverversion 178); die Abweichung ist im Befund offen dokumentiert. Das Storno wurde zusätzlich serverseitig über das Gateway abgenommen (Historie `Cancelled`). Als erfüllt gewertet.
2. Bekannte Grenze aus 05-05: Erscheint `KILL` erst nach einem Halt durch einen Freigabefehler, storniert derselbe Lauf nicht mehr; der Folgelauf holt es nach. Im Handbuch vermerkt, für Phase 6 zu beachten.
3. Der Gesamtsuite-Fehler `test_yfinance_keeps_its_cache_out_of_the_users_home` besteht schon vor der Phase und ist phasenfremd.
4. Die PowerShell-Einzeiler (05-09 nur teilweise prüfbar) wurden im Operator-Checkpoint 05-10 wörtlich am echten Pfad ausgeführt (`release-ok`, `kill-active`, UTF-8 ohne BOM); der offene Punkt ist damit geschlossen.

## Menschliche Prüfung

Keine offenen Punkte. Die Operator-Messungen sind im Befund dokumentiert.

## Fazit

Das Phasenziel ist erreicht: Die vier Leitplanken (Kill-Switch, Größe, Sitzung, Reconciliation) sowie Lock und Ledger sind im Code verdrahtet, durch Negativ-Kontrollen abgesichert und ohne eine einzige gesendete Order bewiesen.

---

_Verifiziert: 2026-10-17_
_Verifier: Claude (gsd-verifier)_

## Nachtrag nach dem Code-Review (2026-10-17)

Nach dieser Verifikation hat das Code-Review (`05-REVIEW.md`) 3 kritische Befunde, 7 Warnungen
und 3 Infos ergeben. 12 davon sind behoben, jeweils mit Regressionstest (`05-REVIEW-FIX.md`,
Commits `6bdc6bc` bis `e783072`). WR-07 (Fills mit Vorzeichen) ist als Todo für Phase 6
zurückgestellt, zusammen mit der erneuten Frische-Prüfung vor dem `intent`.

Folgen für die Nachweise oben:

- **G3 Reconciliation:** Laut WR-02 wird ein Trocken-`intent` ohne Broker-Spur jetzt als
  `never_sent` aufgelöst (`test_g3_reconcile_dry_intent_without_trace_is_never_sent`). Exit 6 bei
  Unauflösbarem belegt jetzt `test_g3_reconcile_unresolved_intent_aborts_with_exit_six`
  (Live-Ledger), das erneute Blockieren
  `test_g3_reconcile_unresolved_stays_unresolved_on_the_next_run`.
- **Neue Leitplanken:** `KILL.*` zählt als Kill (WR-03). Weicht das orderRef-Echo ab, ergibt das
  `source-conflict` (WR-04). Das Sitzungsfenster wird vor dem `intent` neu geprüft (WR-05). Ein
  ungültiger Schlüssel beendet nur seinen Ticker, als `invalid-decision-key` (CR-02).
- **Testsuite:** Ein autouse-Fixture setzt `LOCALAPPDATA` für jeden Test auf ein eigenes
  tmp-Verzeichnis. Kein Test erreicht mehr den echten State-Ordner.

Vom Orchestrator nachgefahren: volle Suite 2511 passed, 1 failed (der bekannte, schon vor der
Phase rote yfinance-Test). `ruff check .` ist sauber. `-k g3` ergibt 16 passed. Der Status bleibt
**passed**.
