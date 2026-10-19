---
phase: 7
slug: rueckkanal-und-soll-ist-zusammenfuehrung
status: draft
nyquist_compliant: true
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

Task-IDs aus den Plänen 07-01..07-09 (`<plan>-<task>`). Jeder `auto`-Task hat einen automatisierten Befehl; nur die zwei Operator-Checkpoints in 07-09 sind manuell.

| Task ID | Plan | Wave | Req/SC | Behavior | Automated Command | Status |
|---------|------|------|--------|----------|-------------------|--------|
| 07-01-01 | 07-01 | 1 | REQ-52 / SC1 | `publish`-Modul: Erstanlage, Fortschreibung, leerer Diff, Non-FF, Bytes-Treue, kein origin/paper-log/--force | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish.py -x -q` | ⬜ pending |
| 07-02-01 | 07-02 | 1 | REQ-51 / SC4 | `backup --dry-run --ibkr-dir`, Allow-Liste, Default = Executor-Pfad, LOCALAPPDATA isoliert | `.venv/Scripts/python.exe -m pytest tests/test_state_maintenance.py -x -q` | ⬜ pending |
| 07-02-02 | 07-02 | 1 | REQ-51 / REQ-52 | Runbook: Backup und Verweis auf ibkr-log | `grep -c "ibkr-dir\|dry-run\|contracts-history.jsonl\|ibkr-log" scripts/STATE_OPERATIONS.md` | ⬜ pending |
| 07-03-01 | 07-03 | 1 | SC6 (D-06) | `second_last_close_utc` an Wochenende/Feiertag | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_decision.py -k second_last -x -q` | ⬜ pending |
| 07-03-02 | 07-03 | 1 | SC6 | `GitPaperLog(fetch_depth)` additiv, Docstring | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_paperlog.py -x -q` | ⬜ pending |
| 07-04-01 | 07-04 | 1 | REQ-49 / SC5 | Decision-Log-Dedup (synthetisches Dreifach), Ledger lesen | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_report.py -k "dedup or smoke or read_ledger" -x -q` | ⬜ pending |
| 07-04-02 | 07-04 | 1 | REQ-49 / SC2 | Join je `decision_key`, Zustandsspalte, Ziel/Ist aus Intent | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_report.py -k join -x -q` | ⬜ pending |
| 07-05-01 | 07-05 | 2 | REQ-50 / SC3 | Zwei Tabellen, Top-of-Book-Hinweis, Slippage-Vorzeichen, Fill-Quote, Fußnoten | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_report.py -k "metrics or slippage or footnote" -x -q` | ⬜ pending |
| 07-05-02 | 07-05 | 2 | REQ-49 / SC2 | CLI liest zwei Branches per fetch + cat-file, ohne Checkout; --since/--until/--out | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_report.py -k "real_git or cli" -x -q` | ⬜ pending |
| 07-06-01 | 07-06 | 2 | REQ-52 / SC1 | `publish`-Unterbefehl, Exit 0/1/6/7/11, kein Gateway, EXIT_NAMES/Docstring | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish_cli.py tests/test_ibkr_executor.py -x -q` | ⬜ pending |
| 07-06-02 | 07-06 | 2 | SC1 | Handbuch-Invariante „one writer per branch“, Exit-Tabelle 13, Reinheit `ibkr_publish.py` | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_isolation.py -x -q` | ⬜ pending |
| 07-07-01 | 07-07 | 2 | SC6 | Fail-open je Grund, `portfolio_feed`, lokales `--portfolio` unverändert | `.venv/Scripts/python.exe -m pytest tests/test_daily_paper_run.py -k "feed or published" -x -q` | ⬜ pending |
| 07-07-02 | 07-07 | 2 | SC6 | Workflow: Pip-Schritt + Flag, paper-log-Schritte byte-gleich, kein IBKR im YAML | `.venv/Scripts/python.exe -m pytest tests/test_daily_paper_run.py -k workflow -x -q` | ⬜ pending |
| 07-08-01 | 07-08 | 3 | REQ-49..52 | Handbuch: Bericht, Backup, CI-Rückkanal, D-17/D-18 | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_isolation.py -k handbook -q` | ⬜ pending |
| 07-08-02 | 07-08 | 3 | Querschnitt | Reinheit `ibkr_report.py`, Handbuch-Pins | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_isolation.py -x -q` | ⬜ pending |
| 07-09-01 | 07-09 | 4 | Vorbedingung | 06-10 erledigt, Ausgangslage, Suite selbst gelaufen | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish.py tests/test_ibkr_publish_cli.py tests/test_ibkr_report.py tests/test_daily_paper_run.py tests/test_state_maintenance.py tests/test_ibkr_isolation.py -q` | ⬜ pending |
| 07-09-02 | 07-09 | 4 | REQ-52 / SC6 | Erster echter publish, Push fork/main, CI-Lauf (Operator) | manuell (checkpoint:human-action) | ⬜ pending |
| 07-09-03 | 07-09 | 4 | SC1/SC2/SC5/SC6 | Nachprüfung ibkr-log, paper-log-Autoren, `portfolio_feed`, Bericht gegen echte Branches | `git ls-remote --exit-code --heads fork ibkr-log` | ⬜ pending |
| 07-09-04 | 07-09 | 4 | REQ-49/50 | Sichtprüfung Bericht gegen Ledger (Operator) | manuell (checkpoint:human-verify) | ⬜ pending |

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (neue Testdateien entstehen in 07-01, 07-04, 07-06; Isolation in 07-02)
- [x] No watch-mode flags
- [ ] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
