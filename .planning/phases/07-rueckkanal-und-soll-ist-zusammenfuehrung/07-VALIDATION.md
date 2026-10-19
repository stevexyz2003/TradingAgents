---
phase: 7
slug: rueckkanal-und-soll-ist-zusammenfuehrung
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-19
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Quelle: `07-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Marker `unit`, `integration`, `smoke`; `--strict-markers`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish.py tests/test_ibkr_report.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_ibkr_isolation.py -x -q` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest -q` (bekannte phasenfremde Windows-Fehler: `test_yfinance_keeps_its_cache_out_of_the_users_home`, `test_chatgpt_auth` ×2, `test_cli_commands` ×1, `test_cli_updates` ×2) |
| **Estimated runtime** | Quick ~30 s, voll ~120 s |

---

## Sampling Rate

- **After every task commit:** betroffene Testdatei `-x -q` + `.venv/Scripts/python.exe -m ruff check <geänderte Dateien>`
- **After every plan wave:** Quick run + `tests/test_ibkr_execute.py tests/test_ibkr_ledger.py` (Regression)
- **Before `/gsd:verify-work`:** volle Suite grün bis auf die dokumentierten phasenfremden Fehler
- **Max feedback latency:** 60 s

---

## Per-Task Verification Map

Wird nach dem Planen mit Task-IDs gefüllt. Abdeckung je Success Criterion:

| Req/SC | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| SC1 / REQ-52 | `publish` pusht nur `ibkr-log` auf `fork`; Erstanlage; leerer Diff = kein Commit; Non-FF = Exit 11 ohne Force; Lock = Exit 7; kein `origin`/`paper-log` in Push-Argumenten; Bytes-Treue ohne `\r\n`; kein Gateway | integration-light (Bare-Repo als `fork`) + unit | `pytest tests/test_ibkr_publish.py -x` | ❌ W0 | ⬜ pending |
| SC1 | Handbuch nennt Invariante „ein Schreiber pro Branch“ | unit (Text-Guard) | `pytest tests/test_ibkr_isolation.py -k writer` | ✅ (Pin ❌) | ⬜ pending |
| SC2 / REQ-49 | Join `(trade_date, ticker)` mit allen SC2-Spalten und Zustandsspalte; liest zwei Branches per `fetch` + `cat-file`, ohne Checkout | unit + integration-light | `pytest tests/test_ibkr_report.py -k "join or real_git"` | ❌ W0 | ⬜ pending |
| SC3 / REQ-50 | Zwei getrennte Tabellen; Top-of-Book-Hinweis; Slippage-Vorzeichen; Fill-Quote 0 bei Timeout/Reject; leere Zelle + Fußnote bei Kursfehler | unit (`settlement.get_closes` gepatcht) | `pytest tests/test_ibkr_report.py -k "metrics or slippage or footnote"` | ❌ W0 | ⬜ pending |
| SC4 / REQ-51 | `backup --dry-run` listet Ledger, Contracts, Contracts-History; nicht `RELEASE`/`KILL`/Lock/Logs; Standardpfad = Executor-Pfad | unit | `pytest tests/test_state_maintenance.py -k "ibkr or dry_run"` | ✅ (Tests ❌) | ⬜ pending |
| SC5 / REQ-39/40 | Doppelte `(trade_date, ticker)` → eine Zeile, erste Fassung gewinnt | unit | `pytest tests/test_ibkr_report.py -k dedup` | ❌ W0 | ⬜ pending |
| SC6 | Gültiger Stand wird übergeben; jede Störung → kein `portfolio` + `portfolio_feed.reason`; lokales `--portfolio` unverändert | unit | `pytest tests/test_daily_paper_run.py -k "feed or published"` | ✅ (Tests ❌) | ⬜ pending |
| SC6 | `second_last_close_utc` an Wochenende/Feiertag | unit | `pytest tests/test_ibkr_decision.py -k second_last` | ✅ (Tests ❌) | ⬜ pending |
| SC6 | Workflow: nur neutrales Flag + Pip-Schritt; `paper-log`-Schritte unverändert; kein „IBKR“ im YAML | unit (Text-Pins) | `pytest tests/test_ibkr_isolation.py -k "workflow or ci"` | ✅ (Pins ❌) | ⬜ pending |
| Querschnitt | `ib_async` nur im Adapter; Exit-Tabelle inkl. 11 | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ anpassen | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ibkr_publish.py` — SC1; Fixtures: Bare-Repo als `fork`, Runner-Recorder, Ledger-Zeilen
- [ ] `tests/test_ibkr_report.py` — SC2/3/5; Fixtures aus `ibkr-konto-befund.md` (erste Live-Order) und `tests/fixtures/paper_log_71df89d`
- [ ] Autouse-Isolation von `LOCALAPPDATA` in `tests/test_state_maintenance.py`
- [ ] `tests/test_ibkr_isolation.py`: Exit-Tabelle inkl. 11, Reinheits- und Workflow-Pins

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Erster echter `publish` auf `fork` legt `ibkr-log` an | REQ-52 / SC1 | echter Remote, Credentials | `ibkr_executor.py publish`, danach `git ls-remote fork ibkr-log` und `git log fork/paper-log -1` unverändert |
| CI-Lauf übergibt das Portfolio | SC6 | GitHub Actions | `workflow_dispatch` nach einem `publish`; `summary.json` zeigt `portfolio_feed` |
| Bericht gegen die echten Branches | REQ-49/50 | echte Daten | `ibkr_report.py --out bericht.md`, Sichtprüfung gegen Ledger |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
