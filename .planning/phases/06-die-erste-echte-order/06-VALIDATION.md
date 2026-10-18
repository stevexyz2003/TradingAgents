---
phase: 6
slug: die-erste-echte-order
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-18
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Quelle: `06-RESEARCH.md` §„Validation Architecture“ (Requirement-zu-Test-Map dort vollständig).

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

*Wird vom Planner/Executor je Task befüllt; die Requirement-zu-Test-Zuordnung steht in `06-RESEARCH.md` Z. ~506–529.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-xx-xx | — | — | REQ-IBKR-10/45/47/48/65 | — | siehe RESEARCH | unit | siehe RESEARCH | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/ibkr_fakes.py` — `FakeIB.placeOrder` als echte Order (Trade-Attrappe mit steuerbarem Status: Filled / bleibt Submitted / `ValidationError`), Fills einspeisbar, `execId`-Korrektur-Fixture
- [ ] `tests/test_ibkr_broker.py` — Order-Permit-Negativkontrollen gegen die echte `ib_async`-Client-Klasse inkl. Layout-Pin
- [ ] `tests/test_ibkr_execute.py` — `_live_run(...)`-Helfer (`--live`, `RELEASE`, Uhr/Sleep-Injektion für 60-s-Timeout), Ereignisstrom für Reihenfolgetest
- [ ] Selbstkonsistenz-Test der `FakeIB`-Attrappe
- [ ] Keine Framework-Installation nötig

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 321-Beleg frisch am Tag der ersten Order (`preview-read-only`, Exit 5, D-15) | REQ-IBKR-10 / SC1 | Echter Gateway-Schalter | Read-Only an → `execute --live` → Exit 5 → Read-Only aus → Handbuch-Eintrag |
| Echte Markt-Order über einen Block, Kette `intent → placed → filled` | REQ-IBKR-47 / SC3 | Echtes Paper-Konto `DUQ634065` | Checkpoint-Plan nach 05-10, Operator nimmt Fill in TWS/Gateway ab |
| Zweiter Lauf am selben Tag ohne zweite Order | REQ-IBKR-48 / SC4 | Echtes Konto | `execute --live` erneut, `placeOrder` nicht ausgelöst, Ledger prüfen |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
