---
phase: 4
slug: entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-12
audited: 2026-10-16
---

# Phase 4 — Validierungsstrategie

> Validierungsvertrag pro Phase für die Rückkopplung während der Ausführung. Quelle: `04-RESEARCH.md` § Validierungsarchitektur.

---

## Test-Infrastruktur

| Eigenschaft | Wert |
|-------------|------|
| **Framework** | pytest 9.0.3 (`-m "not integration"`, `--strict-markers`, Marker `unit`) |
| **Konfiguration** | `pyproject.toml [tool.pytest.ini_options]`, `tests/conftest.py` (blockt Python-Sockets) |
| **Schnelllauf** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_ibkr_preview.py tests/test_paper_summary_contract.py -x -q` |
| **Volllauf IBKR** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_contracts.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py tests/test_ibkr_resolve.py tests/test_ibkr_preview.py tests/test_ibkr_decision.py tests/test_ibkr_paperlog.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_paper_summary_contract.py -q` |
| **Lint** | `.venv/Scripts/python.exe -m ruff check scripts tests` |
| **Laufzeit** | ~10 Sekunden (Basislinie 419 passed in 7,2 s) |

---

## Abtastrate

- **Nach jedem Task-Commit:** der jeweilige `-k`-Befehl aus der Zuordnung unten
- **Nach jeder Welle:** Volllauf IBKR + `ruff check scripts tests`
- **Vor `/gsd:verify-work`:** gesamte Suite grün (`.venv/Scripts/python.exe -m pytest -q`)
- **Maximale Rückkopplungslatenz:** 30 Sekunden

---

## Verifikationszuordnung pro Task

> Task-IDs werden vom Planer ergänzt; die Zeilen sind nach Anforderung/Erfolgskriterium vorbelegt.

| Req / SC | Plan/Task | Verhalten | Typ | Automatisierter Befehl | Datei existiert | Status |
|----------|-----------|-----------|-----|------------------------|-----------------|--------|
| SC1 / REQ-21 | 04-07 T2, 04-09 T2 | Echter Branchstand (AAPL Hold 10-09, eingefrorene Kopie von `71df89d`) → `skipped-hold`, kein Gateway-Kontakt | unit/E2E-Fake | `pytest tests/test_ibkr_preview.py -k real_branch_hold -x` | ✅ | ✅ |
| SC2 / REQ-38, -25 (MKT/DAY; Sitzungsfenster → Phase 6) | 04-07 T3 | Buy + flache Position → „BUY 2", `whatIf` MKT/DAY, Log Margin/Kommission/Ablehnungsgrund, nichts gesendet | unit | `pytest tests/test_ibkr_preview.py -k buy_flat -x` | ✅ | ✅ |
| SC2 / D-13 | 04-02 T1/T2 | Schreibsperre: nur Id 3 mit `whatIf` passiert; `placeOrder` ohne `whatIf` → `ReadOnlyViolation` (echte `Client`-Klasse) | unit | `pytest tests/test_ibkr_broker.py -k "whatif_barrier or place_order_refused" -x` | ✅ | ✅ |
| SC3 / REQ-17 | 04-01 T1, 04-07 T2 | Divergenz Log vs. Summary → Exit 2, `signal-divergence`, Log-Fassung gelesen | unit | `pytest tests/test_ibkr_decision.py -k divergence -x` | ✅ | ✅ |
| SC4 / REQ-19, -20 | 04-06 T1 | Vier Gegenproben in XNYS-Sitzungen mit injizierter Uhr | unit | `pytest tests/test_ibkr_decision.py -k freshness -x` | ✅ | ✅ |
| SC5 / REQ-14, -15, -16 | 04-01 T1, 04-07 T2 | `null`/`REVIEW`/`status!=ok`/`schema_version!=1`/`verify`-Befund → eigener Zustand, kein `whatIf` | unit | `pytest tests/test_ibkr_decision.py tests/test_ibkr_preview.py -k "preconditions or schema or verify" -x` | ✅ | ✅ |
| SC6 / REQ-23 | 04-01 T2, 04-07 T3 | Toleranzband `Ziel − Ist − offen`; fremde offene Order | unit | `pytest tests/test_ibkr_decision.py -k "tolerance or open_order" -x` | ✅ | ✅ |
| SC7 / REQ-14, -18 | 04-01 T1 | Vertragstest gegen echten Erzeuger inkl. Negativ-Kontrolle | unit | `pytest tests/test_paper_summary_contract.py -x` | ✅ | ✅ |
| SC8 / REQ-24 | 04-01 T2, 04-07 T3 | Sell ohne Bestand → `long-only-noop`, nie Short | unit | `pytest tests/test_ibkr_decision.py -k long_only -x` | ✅ | ✅ |
| REQ-13 | 04-01 T1, 04-04 T2 | Parser = `TradingMemoryLog`; neuester Eintrag je Ticker | unit | `pytest tests/test_ibkr_decision.py -k log_entries -x` | ✅ | ✅ |
| REQ-22 | 04-03 T3 | `block_qty > 0` je handelbarem Eintrag; keine Preisableitung | unit | `pytest tests/test_ibkr_contracts.py -k block_qty -x` | ✅ | ✅ |
| REQ-61 | 04-05 T2, 04-07 T3 | leere/unvollständige Vorschau → `preview-empty` | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_preview.py -k "empty_preview or empty_answer" -x` | ✅ | ✅ |
| REQ-37 (Halt) | 04-05 T2 | Fehler 154 am `whatIf` → `halted` (nur Codeliste + Fake; live nicht herbeiführbar, siehe unten) | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_preview.py -k "halted or 154" -x` | ✅ | ✅ |
| REQ-68 | 04-09 T1 (+04-05 Fake-Falle) | kein Marktdatenabruf im Pfad (Fake wirft, AST-Wächter) | unit | `pytest tests/test_ibkr_isolation.py -k no_market_data -x` | ✅ | ✅ |
| D-02/D-04 | 04-04 T1, 04-07 T2 | `paper-log` nicht abrufbar → `paper-log-unavailable`, kein Rückfall | unit | `pytest tests/test_ibkr_paperlog.py -x` | ✅ | ✅ |
| G2 | 04-07 T3 | über alle Pfade nie `placeOrder`/`cancelOrder` | unit | `pytest tests/test_ibkr_preview.py -k nothing_sent -x` | ✅ | ✅ |
| Wächter | 04-05, 04-09 T1 | Isolations-/Exit-Tabellen-Wächter angepasst | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ | ✅ |
| REQ-24 / WR-04 | 04-REVIEW-FIX | Short-Bestand (`held < 0`) → `short-position`, Exit 2, keine Vorschau | unit | `pytest tests/test_ibkr_decision.py -k short -x` | ✅ | ✅ |
| D-13 / WR-01 | 04-REVIEW-FIX | Mit `CI` gesetzt: fehlendes `ib_async`/`exchange_calendars` ist ein Fehler, kein Skip (die Sperr-Tests am echten Client laufen in der CI) | unit | `pytest tests/test_ci_optional_deps.py -x` | ✅ | ✅ |

*Status: ⬜ offen · ✅ grün · ❌ rot · ⚠️ instabil*

---

## Wave-0-Anforderungen

- [x] `tests/test_ibkr_decision.py`, `tests/test_ibkr_paperlog.py`, `tests/test_ibkr_preview.py`, `tests/test_paper_summary_contract.py`
- [x] `tests/ibkr_fakes.py`: `whatIfOrderAsync` steuerbar (OrderState / `[]` / Fehler 154, 10349, 321), `reqAllOpenOrdersAsync`, `position(..., conId)`, `AvailableFunds`
- [x] Fixture: eingefrorene Kopie von `decision-log.md` + `runs/2026-10-09/summary.json` aus `71df89d`
- [x] Kalender: `exchange_calendars` (XNYS) — Install nach `checkpoint:human-verify` (Paketprüfung scheiterte an SSL)

---

## Nur manuell prüfbar

| Verhalten | Anforderung | Warum manuell | Anleitung |
|-----------|-------------|---------------|-----------|
| Gateway „Read-Only API" an + `whatIf`-Sonde | D-14 / REQ-67 | nur am echten Gateway messbar | **Erledigt 2026-10-12** (04-08): Schalter aus → OK, an → 321 + 10 s Timeout; Schalter bleibt aus (Operator bestätigt). Offen: Operator-Bestätigung des angepassten SC2-Satzes in `04-VERIFICATION.md` |
| Fehler 154 (Halt) am echten Gateway | REQ-37 / REQ-67 (A5) | am Paper-Gateway nicht herbeiführbar | Nur über offizielle Codeliste + Fake-Test belegt; Operator akzeptiert die Lücke in `04-VERIFICATION.md` |
| Operator-Handlauf gegen echten `paper-log` | SC1 | Branchstand zeitabhängig | **Erledigt 2026-10-12** (04-09): `preview: AAPL skipped-hold`, Exit 2, sha `7b4af23…`, `sent: false`, vom Operator abgenommen |
| CI-Lauf mit Extra `ci` auf der Linux-Matrix | WR-01 | lokal nur Windows/py3.13 aufgelöst | Nach dem nächsten Push prüfen, dass `test_ci_optional_deps.py` grün ist und die Sperr-Tests nicht übersprungen werden |

---

## Freigabe

- [x] Alle Tasks haben `<automated>`-Verifikation oder Wave-0-Abhängigkeit
- [x] Keine 3 aufeinanderfolgenden Tasks ohne automatische Prüfung
- [x] Wave 0 deckt alle fehlenden Referenzen
- [x] Keine Watch-Mode-Flags
- [x] Rückkopplungslatenz < 30 s
- [x] `nyquist_compliant: true` im Frontmatter

**Freigabe:** automatisiert vollständig (2026-10-16); manuelle Restpunkte siehe oben

---

## Validation Audit 2026-10-16

Quellen: `04-CODEX-REVIEW.md` (Codex, statisch; Sandbox blockte pytest), `04-REVIEW.md` + `04-REVIEW-FIX.md`, `04-VERIFICATION.md`. Alle Befehle der Zuordnung auf HEAD `1e05622` einzeln ausgeführt und grün; Gesamtsuite 2091 passed, 4 skipped (bekannter Windows-Env-Fehler `test_yfinance_keeps_its_cache_out_of_the_users_home` deselektiert).

| Metrik | Anzahl |
|--------|--------|
| Gaps found | 3 (WR-01 CI-Skip der Sperr-Tests, WR-04 Short-Bestand, Kommando REQ-61 wählte 0 Tests) |
| Resolved | 3 |
| Escalated | 0 |
| Manual-only | 4 (davon 2 erledigt) |

REQ-IBKR-25: Sitzungsfenster per Operator-Entscheid 2026-10-16 nach Phase 6 verschoben (ROADMAP-Traceability); Phase 4 deckt MKT/`DAY` und die Differenz mit offenen Orders.
