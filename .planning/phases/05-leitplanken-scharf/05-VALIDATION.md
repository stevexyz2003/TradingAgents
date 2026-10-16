---
phase: 5
slug: leitplanken-scharf
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-16
---

# Phase 5 — Validierungsstrategie

> Validierungsvertrag pro Phase für die Rückkopplung während der Ausführung. Quelle: `05-RESEARCH.md` § Validation Architecture; Entscheidungen D-17 bis D-23 in `05-CONTEXT.md`.

---

## Test-Infrastruktur

| Eigenschaft | Wert |
|-------------|------|
| **Framework** | pytest 9.x (`--strict-markers`, Marker `unit`; `-m "not integration"` voreingestellt) |
| **Konfiguration** | `pyproject.toml [tool.pytest.ini_options]`, `tests/conftest.py` (blockt `socket.connect`) |
| **Schnelllauf** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_guards.py tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -x -q` |
| **Volllauf IBKR** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_contracts.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py tests/test_ibkr_resolve.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_ibkr_guards.py tests/test_ibkr_ledger.py tests/test_ibkr_execute.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_paper_summary_contract.py -q` |
| **Lint** | `.venv/Scripts/python.exe -m ruff check scripts tests` |
| **Laufzeit** | Basis ~11 s (424 passed), mit Phase 5 voraussichtlich < 30 s |
| **G3 per Befehl** | `.venv/Scripts/python.exe -m pytest -k g3 -q` (je G3-Nachweis ein Test mit `g3` im Namen) |

---

## Abtastrate

- **Nach jedem Task-Commit:** der jeweilige `-k`-Befehl aus der Zuordnung unten
- **Nach jeder Welle:** Volllauf IBKR + `ruff check scripts tests`
- **Vor `/gsd:verify-work`:** gesamte Suite grün (`.venv/Scripts/python.exe -m pytest -q`); Agentenaussagen „lint PASSED" selbst nachfahren
- **Maximale Rückkopplungslatenz:** 30 Sekunden

---

## Verifikationszuordnung pro Anforderung

> Task-IDs ergänzt der Planer; die Zeilen sind nach Anforderung/Erfolgskriterium vorbelegt.

| Req / SC | Plan/Task | Verhalten | Typ | Automatisierter Befehl | Datei existiert | Status |
|----------|-----------|-----------|-----|------------------------|-----------------|--------|
| SC1 / REQ-33, -64, D-17, D-20 | tbd | Freigabe fehlt · unlesbar · UTF-16 · abgelaufen · > 90 Tage · falsches Konto · Kill vorhanden · State nicht prüfbar → je Exit 4, kein Platzierungsaufruf, Schalterzustand im Ledger; Storno nur bei `KILL` | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "release or kill or fail_closed" -x` | ❌ W0 | ⬜ |
| SC2 / REQ-34, -66 | tbd | `KILL` zwischen zwei Orders → zweite Order entsteht nicht, kein `intent` für Ticker 2, Exit 4 | unit | `pytest tests/test_ibkr_execute.py -k "g3 and kill_between" -x` | ❌ W0 | ⬜ |
| SC3 / REQ-35, D-17 | tbd | Kill aktiv → `cancel_all` genau 1×, Nachlese `open_orders`, Exit 4; ohne `KILL` kein `reqGlobalCancel`; echte `Client`-Klasse: 58 nur im Permit | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_execute.py -k "cancel_all or global_cancel" -x` | ❌ W0 | ⬜ |
| SC4 / REQ-32 | tbd | Menge 3 abgelehnt (`size_cap`, Exit 5), nicht gekürzt; kein `whatIf`/`intent` | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "g3 and size" -x` | ❌ W0 | ⬜ |
| SC5 / REQ-46 | tbd | JSONL; State nicht in Git-Baum; `.lock` neben Ledger; `git status` vor = nach; Negativ-Kontrolle State im Git-Baum | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_isolation.py -k "ledger or git" -x` | ❌ W0 | ⬜ |
| SC6 / REQ-42, -43, D-19 | tbd | abgebrochener Lauf hinterlässt `intent`; Folgelauf löst über offene/erledigte/Executions auf; unauflösbar → Exit 6 mit eindeutiger Meldung, keine neue Order; torn tail toleriert | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -k "g3 and reconcil or write_ahead" -x` | ❌ W0 | ⬜ |
| SC7 / REQ-44 | tbd | zweiter gleichzeitiger Lauf → Exit 7, kein Ledger-Eintrag; `OSError` beim Sperren → Exit 7 ohne Traceback; `OSError` im Lauf bleibt Nicht-7 | unit | `pytest tests/test_ibkr_execute.py -k "lock" -x` | ❌ W0 | ⬜ |
| SC8 / REQ-39, -40, -41 | tbd | `orderRef == decision_key` an der `whatIf`-Order, `paper_log_sha` im `intent`; `decision_changed`; `already_attempted` | unit | `pytest tests/test_ibkr_execute.py tests/test_ibkr_broker.py -k "order_ref or decision_key or decision_changed or already_attempted" -x` | ❌ W0 | ⬜ |
| REQ-25 (Fenster) | tbd | außerhalb Fenster / erste 15 min / letzte 15 min / Halbtag / geschlossener Tag → `skipped outside_session` vor `whatIf`; `session-unknown` bleibt Ablehnung | unit | `pytest tests/test_ibkr_execute.py -k "g3 and session" -x` | ❌ W0 | ⬜ |
| REQ-36, D-21 | tbd | jeder Lauf schreibt Schalterzustand ins Ledger (Preflight nach Lock), auch bei Exit 0 und 4 | unit | `pytest tests/test_ibkr_execute.py -k "switch_state or preflight" -x` | ❌ W0 | ⬜ |
| REQ-63, D-18, D-22 | tbd | je ein Test mit auseinanderlaufenden Quellen: Konto (Lauf stoppt), Position (enge Regel), „schon ausgeführt?", Handelbarkeit (nur Ticker) | unit | `pytest tests/test_ibkr_guards.py tests/test_ibkr_execute.py -k "source_conflict" -x` | ❌ W0 | ⬜ |
| REQ-66 | tbd | je Schutz eine Negativ-Kontrolle (siehe RESEARCH-Tabelle) | unit | `pytest tests/test_ibkr_execute.py tests/test_ibkr_broker.py -k "negative_control" -x` | ❌ W0 | ⬜ |
| D-07 | tbd | `execute` zwangsweise trocken: nie `placeOrder`/`cancelOrder`; `ledger.jsonl` entsteht nie | unit | `pytest tests/test_ibkr_execute.py -k "nothing_sent or forced_dry" -x` | ❌ W0 | ⬜ |
| D-08 | tbd | Dry-Lauf schreibt `ledger-dryrun.jsonl`; echte Datei mit `mode:"dryrun"`-Zeile → Exit 6 | unit | `pytest tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -k "dryrun" -x` | ❌ W0 | ⬜ |
| Wächter | tbd | Adapter ≤ 10 öffentliche Methoden (exakte Menge); `cancel_all(` nur an einer Stelle; `ibkr_market_data.py` ohne `cancel_all`/`reqGlobalCancel`; neue Module bibliotheksfrei; Handbuch Exit 4/6/7 ohne „reserved" | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ (anpassen) | ⬜ |

*Status: ⬜ offen · ✅ grün · ❌ rot · ⚠️ instabil*

---

## Wave-0-Anforderungen

- [ ] `tests/test_ibkr_guards.py` — Schalter, Größe, Schlüssel, Quellenvergleich (REQ-32, -33, -39, -63, -64)
- [ ] `tests/test_ibkr_ledger.py` — Append-only, torn tail, Zustand je Schlüssel, Auflösung (REQ-40, -42, -43, -46)
- [ ] `tests/test_ibkr_execute.py` — Kette gegen `FakeIB` mit Placer-Naht (SC1–SC8, REQ-25, REQ-36)
- [ ] `tests/ibkr_fakes.py` — `FakeOrder.orderRef`, `completed_orders`/`executions`, `reqCompletedOrdersAsync`, `reqExecutionsAsync`, `reqGlobalCancel`
- [ ] Anpassung `tests/test_ibkr_isolation.py` (Kollision mit uncommittetem Operator-WIP beachten)
- Framework-Installation: keine (keine neue Abhängigkeit)

---

## Nur manuell prüfbar

| Verhalten | Anforderung | Warum manuell | Anleitung |
|-----------|-------------|---------------|-----------|
| Manuelle TWS-Order wird bei `KILL` storniert | SC3 / REQ-35 (D-06) | braucht Gateway + TWS Paper | Limit-Order weit vom Markt, gültige `RELEASE`, `KILL` anlegen, `execute`; Exit 4, Order storniert, `GLOBAL_CANCEL_SENT count=1`; „Read-Only API" aus |
| Rohform `reqCompletedOrders`/`reqExecutions` nach Storno | REQ-67 (A2) | nur am echten Gateway | `order_history()` einmal laufen lassen, Rohausgabe im Befund |
| `orderRef` mit `|` im `whatIf` | REQ-39 / REQ-67 (A3, A5) | nur am echten Gateway | `whatIf` mit `orderRef="2026-10-09|AAPL"`; bei Ablehnung Trenner `_` |
| PowerShell-Einzeiler für `RELEASE`/`KILL` | REQ-33 | Kodierung (UTF-16/BOM) nur real prüfbar | Handbuch-Einzeiler ausführen, Datei mit `execute` lesen lassen |

---

## Freigabe

- [ ] Alle Tasks haben `<automated>`-Verifikation oder Wave-0-Abhängigkeit
- [ ] Keine 3 aufeinanderfolgenden Tasks ohne automatische Prüfung
- [ ] Wave 0 deckt alle fehlenden Referenzen
- [ ] Keine Watch-Mode-Flags
- [ ] Rückkopplungslatenz < 30 s
- [ ] `nyquist_compliant: true` im Frontmatter

**Freigabe:** ausstehend
