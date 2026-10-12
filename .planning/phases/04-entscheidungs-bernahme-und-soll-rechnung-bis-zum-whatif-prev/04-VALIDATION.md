---
phase: 4
slug: entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-12
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
| SC1 / REQ-21 | 04-07 T2, 04-09 T2 | Echter Branchstand (AAPL Hold 10-09, eingefrorene Kopie von `71df89d`) → `skipped-hold`, kein Gateway-Kontakt | unit/E2E-Fake | `pytest tests/test_ibkr_preview.py -k real_branch_hold -x` | ❌ W0 | ⬜ |
| SC2 / REQ-38, -25 | 04-07 T3 | Buy + flache Position → „BUY 2", `whatIf` MKT/DAY, Log Margin/Kommission/Ablehnungsgrund, nichts gesendet | unit | `pytest tests/test_ibkr_preview.py -k buy_flat -x` | ❌ W0 | ⬜ |
| SC2 / D-13 | 04-02 T1/T2 | Schreibsperre: nur Id 3 mit `whatIf` passiert; `placeOrder` ohne `whatIf` → `ReadOnlyViolation` (echte `Client`-Klasse) | unit | `pytest tests/test_ibkr_broker.py -k "whatif_barrier or place_order_refused" -x` | ❌ W0 | ⬜ |
| SC3 / REQ-17 | 04-01 T1, 04-07 T2 | Divergenz Log vs. Summary → Exit 2, `signal-divergence`, Log-Fassung gelesen | unit | `pytest tests/test_ibkr_decision.py -k divergence -x` | ❌ W0 | ⬜ |
| SC4 / REQ-19, -20 | 04-06 T1 | Vier Gegenproben in XNYS-Sitzungen mit injizierter Uhr | unit | `pytest tests/test_ibkr_decision.py -k freshness -x` | ❌ W0 | ⬜ |
| SC5 / REQ-14, -15, -16 | 04-01 T1, 04-07 T2 | `null`/`REVIEW`/`status!=ok`/`schema_version!=1`/`verify`-Befund → eigener Zustand, kein `whatIf` | unit | `pytest tests/test_ibkr_decision.py tests/test_ibkr_preview.py -k "preconditions or schema or verify" -x` | ❌ W0 | ⬜ |
| SC6 / REQ-23 | 04-01 T2, 04-07 T3 | Toleranzband `Ziel − Ist − offen`; fremde offene Order | unit | `pytest tests/test_ibkr_decision.py -k "tolerance or open_order" -x` | ❌ W0 | ⬜ |
| SC7 / REQ-14, -18 | 04-01 T1 | Vertragstest gegen echten Erzeuger inkl. Negativ-Kontrolle | unit | `pytest tests/test_paper_summary_contract.py -x` | ❌ W0 | ⬜ |
| SC8 / REQ-24 | 04-01 T2, 04-07 T3 | Sell ohne Bestand → `long-only-noop`, nie Short | unit | `pytest tests/test_ibkr_decision.py -k long_only -x` | ❌ W0 | ⬜ |
| REQ-13 | 04-01 T1, 04-04 T2 | Parser = `TradingMemoryLog`; neuester Eintrag je Ticker | unit | `pytest tests/test_ibkr_decision.py -k log_entries -x` | ❌ W0 | ⬜ |
| REQ-22 | 04-03 T3 | `block_qty > 0` je handelbarem Eintrag; keine Preisableitung | unit | `pytest tests/test_ibkr_contracts.py -k block_qty -x` | ❌ W0 | ⬜ |
| REQ-61 | 04-05 T2, 04-07 T3 | leere/unvollständige Vorschau → `preview-empty` | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_preview.py -k preview_empty -x` | ❌ W0 | ⬜ |
| REQ-37 (Halt) | 04-05 T2 | Fehler 154 am `whatIf` → `halted` | unit | `pytest tests/test_ibkr_broker.py -k halted -x` | ❌ W0 | ⬜ |
| REQ-68 | 04-09 T1 (+04-05 Fake-Falle) | kein Marktdatenabruf im Pfad (Fake wirft, AST-Wächter) | unit | `pytest tests/test_ibkr_isolation.py -k no_market_data -x` | ❌ W0 | ⬜ |
| D-02/D-04 | 04-04 T1, 04-07 T2 | `paper-log` nicht abrufbar → `paper-log-unavailable`, kein Rückfall | unit | `pytest tests/test_ibkr_paperlog.py -x` | ❌ W0 | ⬜ |
| G2 | 04-07 T3 | über alle Pfade nie `placeOrder`/`cancelOrder` | unit | `pytest tests/test_ibkr_preview.py -k nothing_sent -x` | ❌ W0 | ⬜ |
| Wächter | 04-05, 04-09 T1 | Isolations-/Exit-Tabellen-Wächter angepasst | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ (anpassen) | ⬜ |

*Status: ⬜ offen · ✅ grün · ❌ rot · ⚠️ instabil*

---

## Wave-0-Anforderungen

- [ ] `tests/test_ibkr_decision.py`, `tests/test_ibkr_paperlog.py`, `tests/test_ibkr_preview.py`, `tests/test_paper_summary_contract.py`
- [ ] `tests/ibkr_fakes.py`: `whatIfOrderAsync` steuerbar (OrderState / `[]` / Fehler 154, 10349, 321), `reqAllOpenOrdersAsync`, `position(..., conId)`, `AvailableFunds`
- [ ] Fixture: eingefrorene Kopie von `decision-log.md` + `runs/2026-10-09/summary.json` aus `71df89d`
- [ ] Kalender: `exchange_calendars` (XNYS) — Install nach `checkpoint:human-verify` (Paketprüfung scheiterte an SSL)

---

## Nur manuell prüfbar

| Verhalten | Anforderung | Warum manuell | Anleitung |
|-----------|-------------|---------------|-----------|
| Gateway „Read-Only API" an + `whatIf`-Sonde | D-14 / REQ-67 | nur am echten Gateway messbar | Operator setzt Schalter, Sonde senden, Ergebnis mit Datum im Befund |
| Operator-Handlauf gegen echten `paper-log` | SC1 | Branchstand zeitabhängig | Trockenlauf, Protokoll `skipped-hold` prüfen |

---

## Freigabe

- [ ] Alle Tasks haben `<automated>`-Verifikation oder Wave-0-Abhängigkeit
- [ ] Keine 3 aufeinanderfolgenden Tasks ohne automatische Prüfung
- [ ] Wave 0 deckt alle fehlenden Referenzen
- [ ] Keine Watch-Mode-Flags
- [ ] Rückkopplungslatenz < 30 s
- [ ] `nyquist_compliant: true` im Frontmatter

**Freigabe:** ausstehend
