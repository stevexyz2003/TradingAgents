---
phase: 3
slug: symbol-aufl-sung-handelbarkeit-und-handelszeiten
status: draft
nyquist_compliant: false
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
| **Quick run command** | `UV_OFFLINE=1 uv run pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py tests/test_ibkr_isolation.py -x -q` |
| **Full suite command** | `UV_OFFLINE=1 uv run pytest -q` |
| **Lint** | `UV_OFFLINE=1 uv run ruff check scripts tests` (reales Kommando gegen `.github/workflows/ci.yml` prüfen) |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Quick run command
- **After every plan wave:** zusätzlich `tests/test_ibkr_broker.py tests/test_ibkr_executor.py` + Lint
- **Before `/gsd:verify-work`:** Full suite + Lint grün, selbst nachgelaufen (nicht der Executor-SUMMARY glauben)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Wird nach dem Planen mit konkreten Task-IDs gefüllt. Requirement-Abdeckung:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| REQ-IBKR-26 | `reqMarketDataType(3)` nach Paper-Guard; 10089/10090/10167 auf INFO | unit (FakeIB) | `pytest tests/test_ibkr_broker.py -k "market_data or info_codes" -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-27 | Resolver importiert kein `tradingagents.dataflows.symbols`; `XAUUSD+` → CMDTY, nie `GC=F` | unit/AST | `pytest tests/test_ibkr_isolation.py -k symbols -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-28 | `XYZQ` not-mapped ohne Broker-Aufruf; `^GSPC`/`XAUUSD+` not-allowed | unit | `pytest tests/test_ibkr_contracts.py -k "mapped or allow" -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-29 | 2+ Kandidaten → `ambiguous`, alle Kandidaten in unserer Logzeile | unit (FakeIB, caplog) | `pytest tests/test_ibkr_resolve.py -k ambiguous -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-30 | Lernen, Persistenz, Gegenprobe, manipulierter conId → drift; fehlend/kaputt/Schema → Stopp; `--init`, `--rebaseline`, History | unit (tmp_path) | `pytest tests/test_ibkr_contracts.py tests/test_ibkr_resolve.py -k "persist or drift or init or rebaseline" -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-31 | `not-tradable` bei VALUE-only, ohne SMART, ohne MKT/LMT | unit | `pytest tests/test_ibkr_contracts.py -k tradable -x` | ❌ W0 | ⬜ pending |
| REQ-IBKR-37 | Parser (beide Formate, CLOSED, Halbtag, Mitternacht, `;`), Puffer, `session-unknown`, kein Sitzungswert auf Platte, Gegentest ib_async, Zustand `halted` im Ergebnistyp | unit | `pytest tests/test_ibkr_contracts.py -k "session or parse" -x` | ❌ W0 | ⬜ pending |
| SC7 | Keine hart kodierten Handelszeiten in `scripts/ibkr_*.py` | unit | `pytest tests/test_ibkr_isolation.py -k hard_coded_times -x` | ❌ W0 | ⬜ pending |
| D-26..D-30 | Exit 0/1/2, eine Konsolenzeile/Ticker, `--out` atomar, kein Ticker-Default | unit (FakeIB) | `pytest tests/test_ibkr_resolve.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_contracts.py` — Tabelle, Parser, Zustände, Persistenz, Gegentest
- [ ] `tests/test_ibkr_resolve.py` — `resolve`-Kommando, Exit-Codes, Ausgabe
- [ ] `tests/ibkr_fakes.py` erweitern — `FakeContract` (+`primaryExchange`, `tradingClass`), `qualifyContractsAsync` (0/1/n), `reqContractDetailsAsync` je conId/Symbol, `reqMarketDataType`
- [ ] `tests/test_ibkr_isolation.py` — Methodenmenge, AST-`symbols`, SC7, Handbuch-Exit-Tabelle

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Echte Auflösung + conId-Lernen | REQ-IBKR-30 / SC1 | braucht Paper-Gateway | `resolve --init AAPL MSFT NVDA`, dann zweiter Lauf `resolve AAPL MSFT NVDA` |
| Abweisung realer Sperr-Ticker | REQ-IBKR-28 / SC2 | Gateway-Lauf als Evidenz | `resolve XYZQ ^GSPC XAUUSD+` → Exit 2 |
| Drift real | REQ-IBKR-30 / SC4 | Datei manipulieren | conId in `contracts.json` ändern, `resolve AAPL` → drift, Exit 2 |
| Wochenend-/Feiertagslauf | REQ-IBKR-37 / D-24 vs D-29 | nur am Wochenende messbar | Samstag `resolve AAPL` → erwartet `closed` + nächstes Fenster, Exit 0 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
