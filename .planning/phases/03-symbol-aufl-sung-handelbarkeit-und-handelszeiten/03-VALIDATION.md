---
phase: 3
slug: symbol-aufl-sung-handelbarkeit-und-handelszeiten
status: audited
nyquist_compliant: true
wave_0_complete: false
created: 2026-10-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Quelle: `03-RESEARCH.md` §„Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8 + pytest-subtests, Marker `unit` (`--strict-markers`, `-m "not integration"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py tests/test_ibkr_isolation.py -x -q` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest -q` |
| **Lint** | `.venv/Scripts/python.exe -m ruff check .` (wie CI-Job `lint`: „ruff (strict, full repo)“) |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Quick run command
- **After every plan wave:** zusätzlich `tests/test_ibkr_broker.py tests/test_ibkr_executor.py` + Lint
- **Before `/gsd:verify-work`:** Full suite + Lint grün, selbst nachgelaufen (nicht der Executor-SUMMARY glauben)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Task-IDs `03-PP-TT` = Plan PP, Task TT. Kommandos sind die `<automated>`-Befehle der Pläne (ohne die angehängten `ruff`/`grep`-Gates, die vollständig im Plan stehen). Jeder Task hat ein automatisiertes Verify; nirgends folgen drei Tasks ohne.

| Task ID | Plan | Wave | Requirement | Behavior (Kern) | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | REQ-IBKR-27, -28, -31 | Tabelle, Allow-List, `classify`, `check_tradable`, `identity_diff`, D-07-Verhaltenstest | unit (TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_contracts.py -q -k "table or classify or mapped or allow or tradable or identity or symbols or rejected"` | ❌ W0 (RED-Schritt legt an) | ✅ green |
| 03-01-02 | 01 | 1 | REQ-IBKR-37, SC6, SC7 | Parser beide Formate, CLOSED, Halbtag, Mitternacht, `;`, Puffer, `session-unknown`, Gegentest ib_async | unit (TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_contracts.py -q` + `! grep` auf Uhrzeit-/Uhr-Strings | ❌ W0 | ✅ green |
| 03-02-01 | 02 | 1 | REQ-IBKR-26 | Fakes erweitert, 10167/200, INFO-Level, `reqMarketDataType(3)` nach Guard | unit (FakeIB, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_executor.py -q` | ✅ (erweitert) | ✅ green |
| 03-02-02 | 02 | 1 | REQ-IBKR-29, -30 | `ContractInfo`, `search_contract`, `contract_details` mit Timeout; Methodenmenge | unit (FakeIB, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_broker.py tests/test_ibkr_isolation.py tests/test_ibkr_executor.py -q` | ✅ (erweitert) | ✅ green |
| 03-03-01 | 03 | 2 | REQ-IBKR-30 | `contracts.json` laden/schreiben, History append-only, Atomarität, Schema | unit (tmp_path, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_contracts.py -q -k "persist or contracts_file or history or atomic or schema or commit"` | ❌ W0 | ✅ green |
| 03-03-02 | 03 | 2 | REQ-IBKR-29, -30, -31, -37 | `resolve_all`: Lernen, Gegenprobe, Drift, Mehrdeutigkeit, Anker, rebaseline, Handelbarkeit, Sitzung | unit (Fake-Broker, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_contracts.py -q` + `! grep` auf Uhrzeit-/Uhr-Strings | ❌ W0 | ✅ green |
| 03-04-01 | 04 | 2 | REQ-IBKR-27, SC5, SC7 | AST-Guard ohne `symbols`/`tradingagents`, SC7-Uhrzeiten-Guard, Uhr-Injektion | unit/AST | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_isolation.py -q -k "library_free or normalizer or hard_coded_times or clock or client_library or public_methods"` | ✅ (erweitert) | ✅ green |
| 03-04-02 | 04 | 2 | REQ-IBKR-31, -37 | REQ-31 nach D-19; Halt-Teil REQ-37 an Phase 4 übergeben; keine Selbstabnahme | doc/grep | `grep`-Kette aus 03-04 Task 2 (`orderTypes`, `ibkr-konto-befund.md`, `D-20`, `Übergabe aus Phase 3`, keine `03-VERIFICATION.md`) | n/a | ✅ green |
| 03-05-01 | 05 | 3 | REQ-IBKR-28, D-12, D-14, D-26, D-27, SC2 | `resolve`-Parser, Argumentprüfung, Contracts-Datei, Connect-on-demand, `_guarded` | unit (FakeIB, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_resolve.py tests/test_ibkr_executor.py -q` | ❌ W0 | ✅ green |
| 03-05-02 | 05 | 3 | REQ-IBKR-26, -29, -30, -31, -37, D-28..D-30 | init, Lernen, Drift, Mehrdeutigkeit, rebaseline, Sitzung, Persistenz, `--out` | unit (FakeIB, TDD) | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_resolve.py tests/test_ibkr_executor.py tests/test_ibkr_contracts.py tests/test_ibkr_broker.py tests/test_ibkr_isolation.py -q && .venv/Scripts/python.exe -m ruff check .` | ❌ W0 | ✅ green |
| 03-06-01 | 06 | 4 | REQ-IBKR-26, -28, -30, -37 | Handbuch `resolve`, neuer Ticker, Codes; Handbuch-Tests | unit + grep | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_isolation.py -q` + `grep` auf Handbuch | ✅ (erweitert) | ✅ green |
| 03-06-02 | 06 | 4 | REQ-IBKR-29, -30, SC1 | Erster `resolve`-Lauf gegen das echte Paper-Gateway, Protokoll | integration (Gateway) | Python-Einzeiler aus 03-06 Task 2 (prüft `contracts.json`, Log `learned conId=`, keine Order-Spuren) | n/a | ⬜ pending |
| 03-06-03 | 06 | 4 | SC1..SC4 | Operator nimmt den Lauf ab | checkpoint:human-verify | `grep -q "## First resolve run" scripts/IBKR_EXECUTION.md` | n/a | ⬜ pending |

Requirement-Abdeckung (Rückwärtsblick):

| Requirement | Behavior | Tasks |
|-------------|----------|-------|
| REQ-IBKR-26 | `reqMarketDataType(3)` nach Paper-Guard; 10089/10090/10167 auf INFO | 03-02-01, 03-05-02, 03-06-01 |
| REQ-IBKR-27 | Resolver ohne `tradingagents.dataflows.symbols`; `XAUUSD+` → CMDTY, nie `GC=F` | 03-01-01, 03-04-01 |
| REQ-IBKR-28 | `XYZQ` not-mapped ohne Broker-Aufruf; `^GSPC`/`XAUUSD+` not-allowed | 03-01-01, 03-05-01 |
| REQ-IBKR-29 | 2+ Kandidaten → `ambiguous`, alle Kandidaten in unserer Logzeile | 03-02-02, 03-03-02, 03-05-02 |
| REQ-IBKR-30 | Lernen, Persistenz, Gegenprobe, Drift; fehlend/kaputt/Schema → Stopp; `--init`, `--rebaseline`, History | 03-03-01, 03-03-02, 03-05-01, 03-05-02, 03-06-02 |
| REQ-IBKR-31 | `not-tradable` bei VALUE-only, ohne SMART, ohne MKT/LMT; Anforderung nach D-19 | 03-01-01, 03-03-02, 03-04-02 |
| REQ-IBKR-37 | Parser, Puffer, `session-unknown`, kein Sitzungswert auf Platte, Gegentest, Zustand `halted` im Ergebnistyp; Halt-Teil (154) an Phase 4 | 03-01-02, 03-03-02, 03-04-02, 03-05-02 |
| SC7 | Keine hart kodierten Handelszeiten in `scripts/ibkr_*.py` | 03-01-02, 03-04-01 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

`wave_0_complete` bleibt `false` bis zur Ausführung: Es gibt keinen separaten Wave-0-Plan. Die Wave-0-Dateien entstehen jeweils im RED-Schritt der TDD-Tasks (03-01-01 legt `tests/test_ibkr_contracts.py` an, 03-02-01 erweitert `tests/ibkr_fakes.py`, 03-05-01 legt `tests/test_ibkr_resolve.py` an, 03-02-02/03-04-01 erweitern `tests/test_ibkr_isolation.py`); der Executor hakt sie beim jeweiligen RED-Commit ab.

- [ ] `tests/test_ibkr_contracts.py` — Tabelle, Parser, Zustände, Persistenz, Gegentest (RED in 03-01-01)
- [ ] `tests/test_ibkr_resolve.py` — `resolve`-Kommando, Exit-Codes, Ausgabe (RED in 03-05-01)
- [ ] `tests/ibkr_fakes.py` erweitern — `FakeContract` (+`primaryExchange`, `tradingClass`), `qualifyContractsAsync` (0/1/n), `reqContractDetailsAsync` je conId/Symbol, `reqMarketDataType` (03-02-01)
- [ ] `tests/test_ibkr_isolation.py` — Methodenmenge, AST-`symbols`, SC7, Handbuch-Exit-Tabelle (03-02-02, 03-04-01, 03-06-01)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Echte Auflösung + conId-Lernen | REQ-IBKR-30 / SC1 | braucht Paper-Gateway | `resolve --init AAPL MSFT NVDA`, dann zweiter Lauf `resolve AAPL MSFT NVDA` |
| Abweisung realer Sperr-Ticker | REQ-IBKR-28 / SC2 | Gateway-Lauf als Evidenz | `resolve XYZQ ^GSPC XAUUSD+` → Exit 2 |
| Drift real | REQ-IBKR-30 / SC4 | Datei manipulieren | conId in `contracts.json` ändern, `resolve AAPL` → drift, Exit 2 |
| Wochenend-/Feiertagslauf | REQ-IBKR-37 / D-24 vs D-29 (A5; RESEARCH Q1 RESOLVED: D-24 strikt) | nur am Wochenende messbar | Samstag `resolve AAPL` → erwartet `closed` + nächstes Fenster, Exit 0; zeigt er `session-unknown` (Exit 2), ist das ein Befund für den Operator, keine stille Codeänderung. Teilweise automatisiert: `tests/test_ibkr_resolve.py::TestRealWeekendLiquidHours` (echte Sonntags-Strings aus dem Befund 2026-10-11); der Live-Lauf am Samstag bleibt manuell |
| Anforderungstext-Änderung REQ-IBKR-31 (D-19) | REQ-IBKR-31 | Operator-Abnahme einer Textänderung, kein Verhalten | Operator liest die geänderte Anforderung in REQUIREMENTS.md und bestätigt sie |
| Anforderungstext-Änderung REQ-IBKR-37 (D-20, Halt-Teil an Phase 4) | REQ-IBKR-37 | Operator-Abnahme einer Textänderung, kein Verhalten | Operator bestätigt die Übergabe des Halt-Teils an Phase 4 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (über die RED-Schritte der TDD-Tasks)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (Ausnahme 03-06-02: echter Gateway-Lauf)
- [x] `nyquist_compliant: true` set in frontmatter
- [ ] `wave_0_complete: true` — erst nach den RED-Commits während der Ausführung

**Approval:** pending

---

## Validation Audit 2026-10-16

Quelle der Lücken: Codex-Audit `03-CODEX-REVIEW.md` sowie `03-VERIFICATION.md` (Human-Item 1, Samstagslauf, D-24 vs D-29).

| Metric | Count |
|--------|-------|
| Gaps found | 3 |
| Resolved | 2 |
| Escalated | 0 |
| Manual-only | 1 |

| Gap | Requirement | Ergebnis |
|-----|-------------|----------|
| 1. Echter `liquidHours`-String eines Nicht-Sitzungstags | REQ-IBKR-37 / D-24 vs D-29 | FILLED: `tests/test_ibkr_resolve.py::TestRealWeekendLiquidHours` (2 Tests, grün). Sonntag 2026-10-11 mit dem verbatim gemessenen AAPL-String (US/Eastern) ergibt `closed`, nächstes Fenster 2026-10-12T09:45-04:00 (09:30 plus 15 min Puffer), Exit 0, nicht `session-unknown`. Samstag 2026-10-10 steht nicht im String; dokumentiertes D-24-Verhalten ist `session-unknown`, Exit 2 (als Test festgehalten). Live-Samstagslauf bleibt manuell. |
| 2. Halt-Teil REQ-IBKR-37 (D-20) | REQ-IBKR-37 | Covered-by-Phase-4: `tests/test_ibkr_broker.py::test_preview_halted_code_154_is_its_own_state`, `tests/test_ibkr_preview.py::test_code_154_is_halted`. Kein neuer Test. |
| 3. Textänderungen D-19 / D-20 | REQ-IBKR-31, REQ-IBKR-37 | Manual-only (Operator-Abnahme), siehe Manual-Only. |

Lauf: 494 Tests der IBKR-Dateien grün, `ruff check .` sauber. Hinweis: Der Test fixiert das 15-Minuten-Puffer-Verhalten (09:45 statt 09:30 als „nächstes Fenster"). Offen bleiben 03-06-02/-03 (Gateway-Lauf, Operator-Abnahme).
