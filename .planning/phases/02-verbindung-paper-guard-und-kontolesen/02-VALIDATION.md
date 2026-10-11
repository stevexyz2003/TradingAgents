---
phase: 2
slug: verbindung-paper-guard-und-kontolesen
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-11
---

# Phase 2 — Validierungsstrategie

> Validierungsvertrag je Phase: wie während der Ausführung Rückmeldung gesammelt wird.
> Quelle: `02-RESEARCH.md` → „Validation Architecture“.

---

## Test-Infrastruktur

| Eigenschaft | Wert |
|----------|-------|
| **Framework** | pytest (≥ 8.0) + `pytest-subtests` |
| **Konfig** | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `-m "not integration"`), `tests/conftest.py` |
| **Schnelllauf** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py tests/test_ibkr_isolation.py -q` |
| **Volllauf** | `.venv/Scripts/python.exe -m pytest -q` und `ruff check .` |
| **Geschätzte Laufzeit** | Schnelllauf ~10 s, Volllauf ~3–5 min |

---

## Sampling-Rate

- **Nach jedem Task-Commit:** Schnelllauf + `ruff check scripts tests`
- **Nach jeder Wave:** Volllauf `pytest -q` + `ruff check .`, vom Orchestrator **selbst** ausgeführt (die Selbstauskünfte der Executor-Agenten werden nicht übernommen)
- **Vor `/gsd:verify-work`:** Volllauf grün, beide Operator-Checkpoints abgeschlossen
- **Maximale Rückmeldelatenz:** 30 s (Schnelllauf)

---

## Nachweis je Kriterium / Anforderung

| Kriterium / REQ | Verhalten | Typ | Automatischer Befehl | Datei existiert? |
|---|---|---|---|---|
| K1 / REQ-IBKR-11 | Fake-Snapshot → JSON → `load_portfolio()` ok, Exit 0 | unit | `pytest tests/test_ibkr_executor.py -k "writes_portfolio" -q` | ❌ W0 |
| K1 (echt) | gegen das laufende Gateway: JSON + Exit 0 | manuell | `python scripts/ibkr_executor.py account --out <pfad>`; danach `echo $?` | Operator-Checkpoint |
| K2 / REQ-IBKR-04 | Fremdkonto oder Obermenge → Exit 8, `disconnect` aufgerufen, kein einziger Schreibaufruf | unit | `pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py -k "guard" -q` | ❌ W0 |
| REQ-IBKR-03 | `connectAsync(readonly=True)`, feste `clientId`, Host/Port aus `.env`; die Schreibsperre wirft `ReadOnlyViolation` | unit | `pytest tests/test_ibkr_broker.py -k "readonly or barrier" -q` | ❌ W0 |
| K3 / REQ-IBKR-09/55 | Gateway nicht erreichbar → Exit 3, Logzeile mit benanntem Zustand + `502`, kein Traceback | unit | `pytest tests/test_ibkr_executor.py -k "unreachable or client_id" -q` | ❌ W0 |
| K3 / REQ-IBKR-55 | fehlende `IBKR_*`-Variablen → Exit 20; ungültige Konfiguration → Exit 1 | unit | `pytest tests/test_ibkr_executor.py -k "credentials or config" -q` | ❌ W0 |
| REQ-IBKR-55 | Logdatei in UTF-8, absoluter Pfad, Umlaute bleiben erhalten | unit | `pytest tests/test_ibkr_executor.py -k "log_file" -q` | ❌ W0 |
| REQ-IBKR-55 | Exit-Codes disjunkt und vollständig; die Docstring-Tabelle stimmt mit den Konstanten überein | unit | `pytest tests/test_ibkr_executor.py -k "exit_codes" -q` | ❌ W0 |
| K4 / REQ-IBKR-07 | genau ein Modul importiert `ib_async`; höchstens 10 öffentliche Methoden | unit | `pytest tests/test_ibkr_isolation.py -q` + `git grep -l -w ib_async -- tradingagents scripts` (genau 1 Datei) | ❌ W0 |
| K5 / REQ-IBKR-09 | „Socket oben, Session tot“ → `health()` nicht gesund; ungesund nach 1100, gesund nach 1102 | unit | `pytest tests/test_ibkr_broker.py -k "health" -q` | ❌ W0 |
| REQ-IBKR-09 | jeder Code der Tabelle → erwarteter benannter Zustand; 2104/2106/2158 sind kein Fehler | unit (parametrisiert) | `pytest tests/test_ibkr_broker.py -k "state_map" -q` | ❌ W0 |
| REQ-IBKR-08 | `clientId` ist eine Konstante und steht im Handbuch; keine hart kodierte `orderId` | unit | `pytest tests/test_ibkr_isolation.py -k "client_id" -q` | ❌ W0 |
| REQ-IBKR-12 | zwei `positions()`-Aufrufe → zwei Broker-Abfragen, kein Rücklesen aus dem JSON | unit | `pytest tests/test_ibkr_broker.py -k "fresh" -q` | ❌ W0 |
| K6 / REQ-IBKR-06 | Pin + Kommentar deklariert; positive Auflösung; mit `tzdata>=2026.1` unauflösbar | check (Netz) + unit | `python -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"` (≠ 0) bzw. mit `"tzdata>=2025.2,<2026.0"` (= 0); tomllib-Test auf Pin + Kommentar | ❌ W0 |
| K7 / REQ-IBKR-11 | `--portfolio` reicht `PortfolioContext` durch; der Report zeigt den Block; ungültige Datei → Exit 1 | unit | `pytest tests/test_daily_paper_run.py -k portfolio -q`, `pytest tests/test_reporting.py -k portfolio -q` | Dateien ✅, Tests ❌ |
| K7 (echt) | lokaler Paper-Lauf mit dem erzeugten JSON, Block im Report | manuell (kostet LLM) | `python scripts/daily_paper_run.py --tickers AAPL ... --portfolio <json>` → Block-Grep im `complete_report.md` | Operator-Checkpoint |
| K8 / REQ-IBKR-05 | `.env` nicht getrackt; keine `IBKR`-Referenz in `.github/workflows` | unit | `pytest tests/test_ibkr_isolation.py -k "ci or env" -q` + `git ls-files .env` (leer) | ❌ W0 |

*Status: ⬜ offen · ✅ grün · ❌ rot · ⚠️ instabil*

---

## Wave-0-Anforderungen

- [ ] `.venv` auffrischen: `.venv/Scripts/python.exe -m pip install -e ".[dev,ibkr]"` (setzt das Extra `ibkr` voraus)
- [ ] `tests/test_ibkr_broker.py`, `tests/test_ibkr_executor.py`, `tests/test_ibkr_isolation.py` neu
- [ ] Gemeinsames Fake-`IB` + session-skopierte Loop-Fixture + Sperre für echtes `connectAsync` (Pitfalls 4/5: Die Netzsperre hält unter Windows eine Loopback-Verbindung zu 127.0.0.1 nicht auf)

---

## Nur manuell prüfbar

| Verhalten | Anforderung | Warum manuell | Anleitung |
|----------|-------------|------------|-------------------|
| Echter Kontolauf gegen `DUQ634065` | REQ-IBKR-03/04/11 | braucht das laufende Gateway | Kommando `account` ausführen, Exit 0, JSON per `load_portfolio()` laden |
| Echter lokaler Paper-Lauf mit Portfolio-JSON | REQ-IBKR-11 (K7) | kostet LLM-Aufrufe | `daily_paper_run.py --portfolio …`, Block im Report suchen |
| Auflösungsnachweis des Pins | REQ-IBKR-06 (K6) | braucht Netz (SSL-Workaround auf dieser Maschine) | beide `pip --dry-run`-Varianten, Exit-Codes notieren |

---

## Freigabe der Validierung

- [ ] Jeder Task hat einen `<automated>`-Nachweis oder hängt an Wave 0
- [ ] Sampling-Kontinuität: keine 3 Tasks in Folge ohne automatischen Nachweis
- [ ] Wave 0 deckt alle fehlenden Referenzen ab
- [ ] Keine Watch-Mode-Flags
- [ ] Rückmeldelatenz < 30 s
- [ ] `nyquist_compliant: true` im Frontmatter gesetzt

**Freigabe:** offen
