---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
source: 07-REVIEW.md
fixed_at: 2026-10-20
scope: critical+warning
status: partial
findings_in_scope: 6
fixed: 4
skipped: 2
---

# Phase 7: Fix-Bericht zum Code-Review

Umfang: Critical + Warning (0 Critical, 6 Warning); Info-Befunde (IN-01..03) nicht im Umfang.

## Behoben

| Befund | Commit | Änderung | Tests |
|---|---|---|---|
| WR-01 | 11e259c | `load_published_portfolio`: bei `invalid-schema` nur noch Feldpfad und Fehlertyp (`errors(include_input=False)`), bei `unexpected-error` nur der Exception-Typname — keine Werte mehr im öffentlichen `summary.json` | 2 neue in `tests/test_daily_paper_run.py` |
| WR-04 | 7fce384 | `publish()`: nach dem Reset auf den Remote-Stand muss das lokale Ledger mit den veröffentlichten Bytes beginnen, sonst `PublishError("ledger-diverged")` → Exit 11, nichts veröffentlicht | neuer Test (verkürzt/abweichend); 5 bestehende Tests auf ein fortsetzendes Ledger (`LEDGER2`) umgestellt |
| WR-06 | 7fce384 (mit WR-04, gleiche Dateien) | `scrub_urls()` schwärzt `user:token@` in jedem `PublishError`-Detail; Executor schwärzt zusätzlich und ersetzt die URL nur, wenn nicht leer; `resolve_remote_url` lehnt leere URL oder führendes `-` ab | 3 neue in `tests/test_ibkr_publish.py` |
| WR-05 | 2518239 | Bericht: jede Zeile mit abgeleitetem Ziel trägt die Fußnote „target/held derived with today's block size, not the size on the trade date (D-20)“; Zahlen unverändert | 2 neue in `tests/test_ibkr_report.py` |

Nicht umgesetzt aus WR-06: Ablage der Fork-URL (ggf. mit Token) in `.git/config` des Publish-Klons — betrifft nur URLs mit eingebettetem Token; Empfehlung bleibt Credential-Helper (Doku-Punkt).

## Übersprungen (festgelegte Entscheidungen — Operator entscheidet)

| Befund | Grund |
|---|---|
| WR-02 | Gültigkeitsgrenze „nach dem Schluss der vorletzten regulären Sitzung“ ist in D-06 festgelegt; ein Freitagabend-Snapshot gilt damit am Dienstagmorgen. Eine engere Grenze wäre eine Verhaltensänderung. |
| WR-03 | Warn-only bei veraltetem Portfolio und Nicht-Löschen eines fehlenden `portfolio.json` sind in 07-RESEARCH.md (Pitfall 2) bewusst so gewählt; die CI beurteilt über `as_of`. Reihenfolge `execute` → `account` → `publish` nach D-19. |

## Verifikation (vom Orchestrator ausgeführt, PowerShell)

- Phasen-Testset (`test_ibkr_publish`, `_publish_cli`, `_report`, `test_state_maintenance`, `test_daily_paper_run`, `test_ibkr_paperlog`, `_decision`, `_isolation`, `_executor`, `test_paper_summary_contract`): **465 passed**
- `ruff check scripts tests`: sauber; `ruff format --check` auf den geänderten Publish-/Report-Dateien sauber

Hinweis: Der Fixer-Agent konnte wegen hängender Git-Bash (Speicherdruck) weder testen noch committen; Tests und Commits hat der Orchestrator nachgeholt. Die Änderungen sind noch nicht auf `fork/main` — für die CI wirkt WR-01 erst nach dem nächsten `git push fork main`.
