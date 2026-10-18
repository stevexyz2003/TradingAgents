---
phase: 6
slug: die-erste-echte-order
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-10-18
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Quelle: `06-RESEARCH.md` §„Validation Architecture“ (Requirement-zu-Test-Map dort vollständig); Per-Task-Map unten aus den `<automated>`-Befehlen der Pläne 06-01 bis 06-10.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Config in `pyproject.toml`, Marker `unit`, `-m "not integration"`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_ledger.py tests/test_ibkr_guards.py tests/test_ibkr_decision.py -q` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` (+ `.venv/Scripts/python.exe -m pytest -q` vor dem Gate) |
| **Lint** | `.venv/Scripts/python.exe -m ruff check scripts tests` |
| **Estimated runtime** | ~30 seconds |

Bekannt rot vor der Phase: `test_yfinance_keeps_its_cache_out_of_the_users_home` (nicht der Phase anlasten).

---

## Sampling Rate

- **After every task commit:** betroffene Testdatei + `ruff check scripts tests`
- **After every plan wave:** Full suite command
- **Before `/gsd:verify-work`:** volle Suite grün, vom Orchestrator selbst nachgelaufen (nicht auf Agent-Selbstangabe verlassen)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Kurzform: `PY` = `.venv/Scripts/python.exe`, `LINT` = `&& PY -m ruff check scripts tests`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 06-01 | 1 | REQ-IBKR-47 | T-06-01..03 | execId-Korrektur `.02` ersetzt `.01`; `side` Pflicht in Fill-Zeilen | unit | `PY -m pytest tests/test_ibkr_ledger.py -q` LINT | ✅ | ⬜ pending |
| 6-01-02 | 06-01 | 1 | REQ-IBKR-47 | T-06-04..05 | vorzeichenbehaftete `filled_quantity` (BUY +, SELL −); Reconciliation je execId | unit | `PY -m pytest tests/test_ibkr_ledger.py tests/test_ibkr_guards.py tests/test_ibkr_execute.py -q` LINT | ✅ | ⬜ pending |
| 6-02-01 | 06-02 | 1 | REQ-IBKR-45 | T-06-06..08 | `rating_source == "jev"` fail-closed ausgeschlossen | unit | `PY -m pytest tests/test_ibkr_decision.py -q` LINT | ✅ | ⬜ pending |
| 6-02-02 | 06-02 | 1 | REQ-IBKR-45 | T-06-09 | Handbuchzeile `rating-jev` konsistent | unit | `PY -m pytest tests/test_ibkr_isolation.py -k "decision_module or client_library" -q` | ✅ | ⬜ pending |
| 6-03-01 | 06-03 | 1 | REQ-IBKR-10 | T-06-10..13 | `_OrderPermit` in der Socket-Sperre; Negativ-Kontrollen gegen die echte Client-Klasse inkl. Layout-Pin | unit | `PY -m pytest tests/test_ibkr_broker.py -q` LINT | ✅ (W0: neue `order_permit`-Fälle) | ⬜ pending |
| 6-03-02 | 06-03 | 1 | REQ-IBKR-10 | T-06-14..16 | `place_order` mit gemeinsamem `_build_order`, Fill-Warten ohne Storno; `FakeIB.placeOrder` + Attrappen-Konsistenz | unit | `PY -m pytest tests/test_ibkr_broker.py tests/test_ibkr_isolation.py tests/test_ibkr_preview.py -q` LINT | ✅ (W0: `tests/ibkr_fakes.py` erweitert) | ⬜ pending |
| 6-04-01 | 06-04 | 2 | REQ-IBKR-45, REQ-IBKR-65 | T-06-17..18 | neue States, Exit 9/10, Rang konsistent an allen Stellen | unit | `PY -m pytest tests/test_ibkr_guards.py tests/test_ibkr_isolation.py tests/test_ibkr_ledger.py tests/test_ibkr_execute.py -q` LINT | ✅ | ⬜ pending |
| 6-04-02 | 06-04 | 2 | REQ-IBKR-45 | T-06-19..20 | Frische-Neuprüfung vor dem `intent`; `rating_source` im `intent` | unit | `PY -m pytest tests/test_ibkr_execute.py -q` LINT | ✅ | ⬜ pending |
| 6-05-01 | 06-05 | 3 | REQ-IBKR-10, REQ-IBKR-48 | T-06-21 | `--live` je Lauf; Placer/Modus-Abgleich (`not-dry`/`not-live`); `RELEASE` Pflicht, `KILL` gewinnt | unit | `PY -m pytest tests/test_ibkr_execute.py -q` LINT | ✅ (W0: `_live_run` in `tests/test_ibkr_execute.py`) | ⬜ pending |
| 6-05-02 | 06-05 | 3 | REQ-IBKR-47, REQ-IBKR-48, REQ-IBKR-65 | T-06-22..27 | `intent` vor `placeOrder` auf Platte; Post-Order-Kontrolle → `alarm` + Exit 10; Fills im selben Lauf; genau eine `place_order`-Stelle (AST) | unit | `PY -m pytest tests/test_ibkr_execute.py -q` LINT | ✅ | ⬜ pending |
| 6-05-03 | 06-05 | 3 | REQ-IBKR-10, REQ-IBKR-65 | T-06-21 | Handbuch `--live`, Ledger je Modus, Read-Only nach Freischaltung (D-04) | unit | `PY -m pytest tests/test_ibkr_isolation.py -q` | ✅ | ⬜ pending |
| 6-06-01 | 06-06 | 4 | REQ-IBKR-48, REQ-IBKR-65, REQ-IBKR-10 | T-06-28..31 | `fill-timeout` ohne Storno; `place-rejected` schließt Key; 399 geparkt; Folgelauf gleicher Tag → `already-attempted`, späterer Tag → `foreign-open-order` | unit | `PY -m pytest tests/test_ibkr_execute.py -q` LINT | ✅ | ⬜ pending |
| 6-06-02 | 06-06 | 4 | REQ-IBKR-48 | T-06-32..33 | zweiter Lauf am selben Tag ohne zweite Order (SC4); Budget-Akzeptanz dokumentiert | unit | `PY -m pytest tests/test_ibkr_execute.py tests/test_ibkr_isolation.py -q` | ✅ | ⬜ pending |
| 6-07-01 | 06-07 | 5 | REQ-IBKR-48 | T-06-34..36 | `resolved`-Event, `--resolve KEY=never_sent --note TEXT` | unit | `PY -m pytest tests/test_ibkr_ledger.py tests/test_ibkr_never_sent.py tests/test_ibkr_execute.py -q` LINT | ❌ W0 (`tests/test_ibkr_never_sent.py` neu, 06-07) | ⬜ pending |
| 6-07-02 | 06-07 | 5 | REQ-IBKR-48 | T-06-37..38 | Handbuch und Isolationstest für `--resolve` | unit | `PY -m pytest tests/test_ibkr_isolation.py -q` | ✅ | ⬜ pending |
| 6-08-01 | 06-08 | 5 | REQ-IBKR-45, REQ-IBKR-10 | T-06-39, T-06-41..42 | Aufrufreihenfolge im `--live`-Pfad inkl. vier Abweichungen; positive Ordnung Menge → Größe → Handelszeit → Kill-Switch → whatIf → `intent` → `placeOrder` | unit | `PY -m pytest tests/test_ibkr_call_order.py -k "call_order or key_check_after_freshness" -q` | ❌ W0 (`tests/test_ibkr_call_order.py` neu, 06-08) | ⬜ pending |
| 6-08-02 | 06-08 | 5 | REQ-IBKR-45, REQ-IBKR-10 | T-06-40 | Negativ-Kontrollen `--live`: whatIf-Reject (D-12), Read-Only 321 (D-15), Größe, Sitzung, `KILL` | unit | `PY -m pytest tests/test_ibkr_call_order.py -q` LINT | ❌ W0 (06-08 Task 1) | ⬜ pending |
| 6-09-01 | 06-09 | 6 | REQ-IBKR-10 | T-06-43 | Vorprüfungen vor dem Messtag; Gateway-Checkpoint (Operator) | unit + checkpoint | `PY -m pytest tests/test_ibkr_call_order.py tests/test_ibkr_never_sent.py -q` | ❌ W0 (06-07, 06-08) | ⬜ pending |
| 6-09-02 | 06-09 | 6 | REQ-IBKR-10 | T-06-43..46, T-06-55 | Read-Only per Sonden-whatIf (`READ_ONLY_API`, 321) maschinell belegt VOR `RELEASE`; Ticker per `preview` ohne `--live`; `--live` mit genau einem Ticker | live-measurement | `grep -c "Messung 1: 321 im scharfen Pfad" .planning/ibkr-konto-befund.md && grep -c "Read-Only-Beleg vor RELEASE" .planning/ibkr-konto-befund.md` | ✅ (Befund-Datei existiert) | ⬜ pending |
| 6-09-03 | 06-09 | 6 | REQ-IBKR-10 | T-06-44 | Schalter wieder aus (Operator) | checkpoint | `grep -c "Messung 1: 321 im scharfen Pfad" .planning/ibkr-konto-befund.md` | ✅ | ⬜ pending |
| 6-10-01 | 06-10 | 7 | REQ-IBKR-10 | T-06-48 | Operator bereit, Messdatum = 06-09-Datum | checkpoint | `grep -c "Messung 1: 321 im scharfen Pfad" .planning/ibkr-konto-befund.md` | ✅ | ⬜ pending |
| 6-10-02 | 06-10 | 7 | REQ-IBKR-10, REQ-IBKR-47, REQ-IBKR-48, REQ-IBKR-65 | T-06-49..53 | erste echte Order, Kette `intent → placed → filled`, zweiter Lauf ohne zweite Order, execId-Fixture aus Rohform (D-13) | live-measurement | `grep -c "Messung 2: Erste echte Order" .planning/ibkr-konto-befund.md` | ✅ | ⬜ pending |
| 6-10-03 | 06-10 | 7 | REQ-IBKR-47, REQ-IBKR-48 | T-06-54 | Operator nimmt Fill, Position, Befund ab | checkpoint | `grep -c "## First live order" scripts/IBKR_EXECUTION.md` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Jeder Eintrag gehört dem Plan, der ihn anlegt; `wave_0_complete` kippt erst während der Ausführung auf `true`.

- [ ] `tests/ibkr_fakes.py` — `FakeIB.placeOrder` als echte Order (Trade-Attrappe mit steuerbarem Status: Filled / bleibt Submitted / `ValidationError` / `Cancelled`), Fills einspeisbar (`place_*`-Parameter) — **06-03 Task 2**
- [ ] Attrappen-Konsistenztest (`FakeIB.placeOrder`: Name über `client.placeOrder`, dann Nachricht über `client.sendMsg`) in `tests/test_ibkr_broker.py` — **06-03 Task 2**
- [ ] `tests/test_ibkr_broker.py` — `order_permit`-Negativkontrollen gegen die echte `ib_async`-Client-Klasse inkl. Layout-Pin — **06-03 Task 1**
- [ ] `execId`-Korrektur-Fixture (Platzhalter `0000e0d5.6710a3c5.01.01`/`.01.02`) in `tests/test_ibkr_ledger.py` — **06-01 Task 1** (Rohform aus der echten Order ersetzt den Platzhalter in **06-10 Task 2**, D-13)
- [ ] `_live_run(...)`-Helfer in `tests/test_ibkr_execute.py` (`--live`, `RELEASE`, Uhr/Sleep-Injektion für den 60-s-Timeout) — **06-05 Task 1**
- [ ] `tests/test_ibkr_never_sent.py` (neu) — **06-07 Task 1**
- [ ] `tests/test_ibkr_call_order.py` (neu) mit Ereignisstrom und Beobachtungs-Hooks (`plan_order`, `check_size`, Sitzungsprüfung, `check_switches`) — **06-08 Task 1**
- [x] Keine Framework-Installation nötig

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 321-Beleg frisch am Tag der ersten Order (`preview-read-only`, Exit 5, D-15) | REQ-IBKR-10 / SC1 | Echter Gateway-Schalter | 06-09: Read-Only an → Sonden-whatIf maschinell auf `READ_ONLY_API` + 321 geprüft (sonst Abbruch, kein `RELEASE`) → Ticker per `preview` ohne `--live` → `RELEASE` → `execute <TICKER> --live` mit genau einem Ticker → Exit 5 → `RELEASE` weg → Read-Only aus → Befund |
| Echte Markt-Order über einen Block, Kette `intent → placed → filled` | REQ-IBKR-47 / SC3 | Echtes Paper-Konto `DUQ634065` | 06-10, Operator nimmt Fill in TWS/Gateway ab |
| Zweiter Lauf am selben Tag ohne zweite Order | REQ-IBKR-48 / SC4 | Echtes Konto | 06-10: `execute <TICKER> --live` erneut, `placeOrder` nicht ausgelöst, Ledger prüfen |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-10-18 (Wave 0 offen bis zur Ausführung)
