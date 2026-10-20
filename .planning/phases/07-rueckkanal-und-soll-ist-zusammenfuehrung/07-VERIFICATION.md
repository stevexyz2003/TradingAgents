---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
verified: 2026-10-20T00:00:00Z
status: passed
score: 6/6 Erfolgskriterien belegt
overrides_applied: 0
---

# Phase 7: Rückkanal und Soll-Ist-Zusammenführung – Verifikationsbericht

**Ziel:** Soll und Ist stehen in einem Bericht nebeneinander, ohne dass ein Prozess in den Branch eines anderen schreibt.
**Status:** passed (keine Lücke gefunden; der zunächst offene Testlauf und die Remote-Gegenprobe wurden vom Orchestrator nachgeholt, siehe unten)

## Nachtrag Orchestrator (2026-10-20)

Die in der ursprünglichen Fassung offenen Punkte wurden per PowerShell ausgeführt:

- `pytest tests/test_ibkr_publish.py tests/test_ibkr_publish_cli.py tests/test_ibkr_report.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_ibkr_paperlog.py tests/test_ibkr_decision.py tests/test_ibkr_isolation.py tests/test_ibkr_executor.py -q`: **447 passed**
- `git fetch fork`; `git ls-tree --name-only fork/ibkr-log` = `.gitattributes`, `contracts.json`, `ledger.jsonl`, `portfolio.json`; Tip `c141694` von `TradingEngineX publish`
- `fork/paper-log:runs/2026-10-19/summary.json` enthält `portfolio_feed` mit `"status": "used"` und `sha c141694523a40fff…` (= Publish-SHA)
- Volle Suite (07-09 Task 1, nach 07-08): 3034 passed, 5 bekannte Fremdfehler

Die Code-Review-Befunde (07-REVIEW.md: 0 Critical, 6 Warning, 3 Info) betreffen Härtung, keine Erfolgskriterien.

## Einschränkung dieser Verifikation

Das Shell-Werkzeug war in dieser Sitzung nicht benutzbar (jeder Aufruf, auch `echo`, lief in den Timeout). Daher wurden **keine** Tests ausgeführt, kein `git fetch fork` und kein `git show` gegen die Remote-Branches. Die Prüfung stützt sich auf das Lesen des Codes und der Doku per Datei-/Grep-Werkzeug sowie auf die Abnahmenachweise aus 07-09-SUMMARY.md (dort ausdrücklich als nachprüfbar gegen den Remote beschrieben, hier nicht neu nachgeprüft). Die Datei wurde deshalb auch nicht committet.

## Beobachtbare Wahrheiten (ROADMAP-Erfolgskriterien)

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | Eigener Branch, ein Schreiber pro Branch, Invariante im Handbuch | VERIFIED (Code), Remote laut 07-09 | `scripts/ibkr_publish.py`: `PUBLISH_REMOTE="fork"`, `PUBLISH_BRANCH="ibkr-log"`, Push nur `git push --porcelain fork <HEAD:refs/heads/ibkr-log>` (Z. 244), Prüfung `remote-is-origin`/`remote-missing`, kein `--force`. `ibkr_executor.py`: Subcommand `publish`, `EXIT_PUBLISH = 11`. `scripts/IBKR_EXECUTION.md` Z. 1068 „Invariante: one writer per branch“, Exit 11 in der Tabelle (Z. 165). Abnahme 07-09: `ibkr-log` @ c141694, `paper-log` nur Commits von github-actions[bot]. |
| 2 | Berichtsskript, Tabelle über (trade_date, ticker) mit allen Spalten | VERIFIED (Code), Lauf laut 07-09 | `scripts/ibkr_report.py` vorhanden, Tests `tests/test_ibkr_report.py`; 07-09: Zeile `2026-10-16 \| AAPL` mit Rating, Ziel, Ist vorher/nachher, Order, Fill, Preis, weekend_gap. Join beim Lesen; Schreibzugriff laut 07-09 nicht vorhanden (`git status --porcelain` unverändert). |
| 3 | Zwei getrennte Tabellen + Paper-Fill-Hinweis | VERIFIED | `ibkr_report.py` Z. 311-313: „Paper fills are simulated from the top of the book … systematically biased upward“; Abschnitte Execution/Decision laut 07-09 sichtbar. |
| 4 | `backup --dry-run` listet Ledger und Contract-Cache | VERIFIED (Code) | `state_maintenance.py` Z. 79-84 `IBKR_BACKUP_FILES` (ledger, ledger-dryrun, contracts, contracts-history), `--ibkr-dir`; RELEASE/KILL/portfolio/preview/resolve/logs ausdrücklich ausgeschlossen. |
| 5 | Deduplizierung beim Lesen | VERIFIED laut 07-09 | Genau eine Zeile `2026-10-09 \| AAPL`, obwohl `index.md` den Tag 5× führt (D-12, erste Fassung gewinnt). |
| 6 | CI liest Portfolio-JSON vom Veröffentlichungsbranch, fail-open | VERIFIED | `daily_paper_run.py`: `PORTFOLIO_FEED_KEY="portfolio_feed"`, jede Ausnahme → `skipped` mit Grund (Z. 216, 285-286), Lauf ohne `portfolio`-Kwarg. Workflow Z. 186 `--portfolio-from-published`, kein „IBKR“ in der YAML. CI-Lauf 39411116928: `portfolio_feed.status == used`. |

## Anforderungsabdeckung

| ID | Plan(s) | Status |
|---|---|---|
| REQ-IBKR-49 (Join beim Lesen) | 07-04, 07-05, 07-08, 07-09 | SATISFIED |
| REQ-IBKR-50 (Metriken getrennt, Paper-Hinweis) | 07-05, 07-08, 07-09 | SATISFIED |
| REQ-IBKR-51 (Backup-Allow-Liste) | 07-02, 07-08 | SATISFIED |
| REQ-IBKR-52 (ein Schreiber pro Branch) | 07-01, 07-03, 07-06, 07-07, 07-08, 07-09 | SATISFIED |

Alle vier IDs aus ROADMAP und REQUIREMENTS.md sind in mindestens einem PLAN-Frontmatter beansprucht; keine verwaisten IDs.

## Nicht blockierende Beobachtungen (aus 07-09)

1. Ein manueller Dispatch mit gleichem `trade_date` überschreibt den Tagesordner auf `paper-log` – Verhalten vor Phase 7, nicht Teil dieser Phase.
2. Ohne `--since/--until` steht kosmetisch `Period: start .. end`.
3. Fußnote 1 nennt den Log-Stand der Order (Pipeline-Test-Branch) auch im Bericht gegen `paper-log`.

## Lücken

Keine festgestellt. Offen bleibt allein der Nachlauf der Tests und der Remote-Gegenprobe in einer funktionierenden Shell (siehe Frontmatter).
