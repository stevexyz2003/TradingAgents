# Quick 261019-o31 — Research Teil A: Anforderungsmatrix

**Stand:** 2026-10-19, Branch `main`, HEAD `b0989aa` (Commit-Zeit 2026-10-19 17:21:29 +0200). Upstream-Basis `origin/main` = v0.7.0 `e8f5503`.
**Phase 6 läuft parallel:** 8/10 Pläne ausgeführt (06-01..06-08 mit SUMMARY vom 2026-10-19). 06-09 und 06-10 (Operator-Checkpoints, erste echte Order) sind am 2026-10-19 verschoben, weil alle drei Ticker auf Hold standen (STATE.md, `ibkr-konto-befund.md` §„Erste echte Order“, `035af86`). Anforderungen aus Phase 6 haben deshalb den Status „teilweise (Phase 6 läuft)“: Der Code und die Tests sind da, die echte Order fehlt.
**Belegquellen:** `0x-VERIFICATION.md` (Phasen 2 bis 5, alle `passed`), `06-0x-SUMMARY.md` (`requirements-completed`), ROADMAP-Coverage-Tabelle, MILESTONE-DoD, Quick-SUMMARYs, Code und Tests am HEAD. Commit-SHAs aus der Zeit vor einem Rebase sind mit „(vor Rebase)“ markiert; am HEAD heißen die Commits anders, der Beleg ist dann die Datei.

<user_constraints>
Gesperrte Entscheidungen aus `261019-o31-CONTEXT.md`, die diese Matrix betreffen: Umfang ist M1 (P1/P2), M2 (REQ-IBKR-xx) und Upstream. Statuswerte sind umgesetzt / teilweise / offen / verworfen-override. Jeder Status ist belegt und nicht geraten. Der Stand wird mit Datum und HEAD-SHA ausgewiesen. Die Seite ist deutsch.
</user_constraints>

## Statuswerte

| Wert | Bedeutung |
|---|---|
| umgesetzt | im Code oder in einem Artefakt vorhanden und belegt (VERIFICATION `passed`, DoD `[x]`, Test vorhanden) |
| umgesetzt (Override) | erfüllt in einem geänderten Wortlaut, den der Operator per Override abgenommen hat |
| teilweise | ein Teil ist belegt, ein benannter Rest fehlt |
| teilweise (Phase 6 läuft) | Code und Tests sind da, der reale Nachweis (06-09/06-10) steht aus |
| offen | nicht begonnen oder bewusst offen gelassen |
| verworfen-override | bewusst nicht umgesetzt, durch eine Entscheidung ersetzt |

Für die Zählung wird „umgesetzt (Override)“ als umgesetzt gezählt.

## Komponentenkatalog

| # | Komponente | Beschreibung | Herkunft | Hauptpfade |
|---|---|---|---|---|
| K01 | Analysten | vier LLM-Analysten (Markt/Technik, Sentiment/Social, News, Fundamentals), laufen parallel | Upstream | `tradingagents/agents/analysts/`, `tradingagents/graph/analyst_execution.py`, `tradingagents/agents/post_screen.py` |
| K02 | Debatte | Bull/Bear-Debatte und Research Manager (structured) | Upstream | `tradingagents/agents/researchers/`, `agents/managers/research_manager.py` |
| K03 | Trader/Risiko/PM | Trader (3 Stufen), drei Risiko-Debattierer, Portfolio Manager (5 Stufen), Portfolio-Kontext | Upstream (+ Strang-Retry) | `agents/trader/`, `agents/risk_mgmt/`, `agents/managers/portfolio_manager.py`, `agents/structured.py`, `agents/rating.py`, `tradingagents/portfolio.py` |
| K04 | Graph/Orchestrierung | LangGraph-Aufbau, Routing, Checkpoint-Resume, Reports | Upstream (+ Strang-Budget-Hooks) | `tradingagents/graph/`, `reporting.py`, `report_html.py` |
| K05 | Memory/Settlement | Decision-Log, Settlement (Return, Alpha), Reflexion | Upstream (+ Strang-Fixes h63) | `tradingagents/memory/log.py`, `settlement.py`, `reflection.py` |
| K06 | Backtest | Ticker×Datum-Gitter, Bewertung je Rating | Upstream (+ Strang-Fix #5) | `tradingagents/backtest.py` |
| K07 | Datenquellen | Vendor-Router: yfinance, Alpha Vantage, SEC EDGAR, FRED, Polymarket, StockTwits, Reddit; Point-in-time-Schutz | Upstream | `tradingagents/dataflows/`, `dataflows/vendors/` |
| K08 | LLM-Provider | Provider-Registry (über 18 Einträge), Tier-Provider, Fail-fast-Keys | Upstream (+ Strang-Fail-fast) | `tradingagents/llm_clients/` |
| K09 | CLI | interaktiv und headless, `backtest`-Subkommando, Docker | Upstream (+ Strang-Exit-Pfade) | `cli/`, `Dockerfile`, `docker-compose.yml` |
| K10 | Jev | Run-Review mit REVIEW-Fallback und Shadow-Checks (Strang); Social-Post-Screening (Upstream, eigener Key) | Strang (+ Upstream post_screen) | `tradingagents/jev/`, `agents/post_screen.py` |
| K11 | Patterns | sechs Muster ohne Look-ahead, Wilson-95-%, MIN_N; nur Nachauswertung | Strang | `tradingagents/patterns/`, `scripts/pattern_eval.py` |
| K12 | Budget/Kosten | hartes Kosten-/Token-Limit pro Run, Ratentabelle | Strang | `tradingagents/budget.py`, `scripts/paper_run_rates.json` |
| K13 | Paper-Lauf (GitHub Actions) | Cron Di–Sa 06:30 UTC, AAPL/MSFT/NVDA, Cap $1.50/Ticker, schreibt `paper-log` | Strang | `.github/workflows/daily-paper-run.yml`, `scripts/daily_paper_run.py`, `scripts/PAPER_RUN.md`, Branch `paper-log` |
| K14 | CI/Smoke | pytest py3.11–3.14, strict ruff, Clean-Install-Smoke, Docker-Smoke mit Stub-LLM | Upstream-CI + Strang-Job | `.github/workflows/ci.yml`, `scripts/smoke/docker_smoke.sh`, `scripts/smoke/stub_llm.py` |
| K15 | State/Ops | verify/prune/backup, Runbook, Retention | Strang | `scripts/state_maintenance.py`, `scripts/STATE_OPERATIONS.md` |
| K16 | IBKR-Ausführer | lokaler Prozess: `account`/`resolve`/`preview`/`execute`, Prüfkette, Entscheidungsübernahme aus `paper-log` | Strang | `scripts/ibkr_executor.py`, `ibkr_decision.py`, `ibkr_paperlog.py`, `scripts/IBKR_EXECUTION.md` |
| K17 | IB Gateway/Adapter | einziger `ib_async`-Importort, Paper-Guard, Socket-Sperre, Contract-Auflösung, Sitzungen | Strang | `scripts/ibkr_broker.py`, `ibkr_contracts.py`, `ibkr_market_data.py`, `scripts/smoke/ibkr_order_probe.py` |
| K18 | Leitplanken | RELEASE/KILL fail-closed, Größengrenze, Idempotenz, Ledger, Lock, Reconciliation | Strang | `scripts/ibkr_guards.py`, `scripts/ibkr_ledger.py` |
| K19 | Rückkanal/Betrieb | eigener Branch, Soll-Ist-Bericht, Heartbeat, Scheduler (Phasen 7/8) | Strang (geplant) | noch kein Code |

## Zählung je Quelle

| Quelle | Einträge | umgesetzt | teilweise | davon Phase 6 läuft | offen | verworfen-override |
|---|---|---|---|---|---|---|
| M1 Produktionsreife (P1/P2) | 11 | 6 | 2 | 0 | 2 | 1 |
| M1 Zusatz (P3 #12, Betriebszweck) | 2 | 2 | 0 | 0 | 0 | 0 |
| M2 IBKR Paper Execution | 70 | 52 (davon 2 Override) | 9 | 6 | 9 | 0 |
| Upstream TradingAgents | 35 | 34 | 0 | 0 | 1 | 0 |
| Strang-Zusätze außerhalb M1/M2 | 8 | 7 | 1 | 1 | 0 | 0 |

M2 hat 70 IDs (`-01`…`-70`). Der Kopf von REQUIREMENTS.md und Teile der ROADMAP sagen noch „68“; die Coverage-Tabelle der ROADMAP führt aber alle 70, weil `-69` und `-70` nachträglich dazukamen. Die ROADMAP-Statustabelle (Z. 48) führt Phase 5 noch als „offen“, obwohl Phase 5 am 2026-10-17 abgenommen wurde (Phasenliste Z. 37, `05-VERIFICATION.md passed`). Beides ist ein Pflegefehler in der ROADMAP, kein Widerspruch im Status.

## 1. M1 Produktionsreife (`.planning/MILESTONE.md`, abgeschlossen 2026-10-11)

| ID | Kurztitel | Herkunft | Status | Phase/Quick | Komponente | Nachweis |
|---|---|---|---|---|---|---|
| M1-P1-1 | Release v0.2.5 schnüren | Strang | verworfen-override | 260814-k1j | CI/Smoke | DoD: „obsolet durch Rebase-Strategie“; Tag `v0.2.5-tex` existiert (letzter eigener Tag), Release-Commit cf351de beim Rebase 2026-08-18 gedroppt, #618 in Upstreams v0.2.5 |
| M1-P1-2 | CI-Paket: Tests, Lint, Security-Scan | Strang | teilweise | 260814-k1j | CI/Smoke | `ci.yml`: py3.11–3.14, strict ruff, smoke-install, `[dev]`-Extra. **Kein** Dependency-/Security-Scan: `pip-audit` aus 6bce117 (vor Rebase) beim Rebase 2026-08-18 gedroppt, kein Dependabot in `.github/` |
| M1-P1-3 | Kosten-Budget pro Run erzwingen | Strang | umgesetzt | 260814-k1j, Rebase-Ports | Budget/Kosten | `tradingagents/budget.py` (`max_cost_per_run`), `tests/test_budget.py`; Reflexions-Calls zählen seit v0.5.0-Rebase mit |
| M1-P1-4 | Schema-Fehler nicht abbrechen (#583) | Strang | umgesetzt | 260814-k1j | Trader/Risiko/PM | `agents/structured.py` `invoke_structured` (Retry mit Fehlerkontext, dann Prosa), `92481f0`, `tests/test_structured_agents.py` |
| M1-P1-5 | Secrets-Doku und Fail-fast-Keys | Strang | umgesetzt | 260814-k1j | LLM-Provider | `llm_clients/factory.py` `_validate_credentials`, `e92e6c1`, README „Secrets & configuration for production“, `tests/test_api_key_failfast.py` |
| M1-P2-6 | Observability/Alerting für Dauerbetrieb | Strang | offen | — (M2 Ph. 8 teilweise geplant) | Paper-Lauf (GitHub Actions) | MILESTONE „Bewusst offen (Operator 2026-10-11)“; Ausführungsseite soll mit REQ-IBKR-53/54 kommen (offen), Analyseseite bleibt ohne Metriken |
| M1-P2-7 | State-Betrieb: Retention/Backup/Locking | Strang | umgesetzt | 261011-k4s | State/Ops | `scripts/state_maintenance.py` (verify/prune/backup), `scripts/STATE_OPERATIONS.md`, `tests/test_state_maintenance.py`; 28f4a75/e32c6a4 (vor Rebase), HEAD-Stand `14fd390` |
| M1-P2-8 | Provider-Ausfall-/Quota-Policy technisch | Strang | offen | — | LLM-Provider | MILESTONE „bewusst offen“; nur Upstream-Bausteine vorhanden (`llm_max_retries`, `tests/test_llm_max_retries.py`), keine Degradationsstrategie |
| M1-P2-9 | Release-Reproduzierbarkeit / Lockfile | Strang | umgesetzt | Rebase 2026-08-18 | CI/Smoke | DoD `[x]`: Upstream hat `uv.lock` entfernt (0b61eff), CI installiert per pip; keine eigene Publish-Prozedur nötig, weil keine eigenen Tags mehr |
| M1-P2-10 | Docker-/CLI-E2E-Smoke mit Stub | Strang | umgesetzt | 261011-k4s | CI/Smoke | `scripts/smoke/docker_smoke.sh`, `stub_llm.py`, CI-Job `docker-smoke` (`ci.yml:57`); 12ed32d (vor Rebase), HEAD `952a5e6` |
| M1-P2-11 | Betriebs-Runbook (Rest: Vendor-Quota) | Strang | teilweise | 261011-k4s | State/Ops | Checkpoint-Hygiene, Memory-Log-Pflege, Recovery in `STATE_OPERATIONS.md`; Vendor-Quota-Verhalten offen, hängt an #8 |
| M1-P3-12 | Repo-Hygiene lokaler Tool-Artefakte | Strang | umgesetzt | — | State/Ops | 4c1769b (vor Rebase); `CLAUDE.md`, `AGENTS.md`, `scripts/graphify.sh` committet; `git status` am HEAD nur `.planning/debug/` untracked |
| M1-Z | Täglicher Paper-Lauf trägt sich | Strang | umgesetzt | Heartbeat 2026-08-21 | Paper-Lauf (GitHub Actions) | `daily-paper-run.yml` (Cron `30 6 * * 2-6`), seit 2026-10-11 Entscheidungen; erster Lauf AAPL Hold $0.18, `paper-log:runs/2026-10-09/summary.json` |

## 2. M2 IBKR Paper Execution (`.planning/REQUIREMENTS.md`)

Phase laut ROADMAP-Coverage. Alle Einträge Herkunft „Strang“.

| ID | Kurztitel | Status | Phase | Komponente | Nachweis |
|---|---|---|---|---|---|
| REQ-IBKR-01 | Konto-Messung: fünf Fragen schriftlich | umgesetzt | 1 | IB Gateway/Adapter | `.planning/ibkr-konto-befund.md` §1–5 mit Rohausgabe; Gate G1 (8f4b6ea) |
| REQ-IBKR-02 | 2FA-Ausgang bestimmt Betriebsform | umgesetzt | 1 | IB Gateway/Adapter | `ibkr-konto-befund.md` §1: „Zweitfaktor? NEIN“ |
| REQ-IBKR-03 | Gateway Paper, Paper-User, read-only | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION Z. 133 SATISFIED |
| REQ-IBKR-04 | Paper-Guard: genau `{DUQ634065}` | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION K2 (Exit 8, kein Platzierungsaufruf) |
| REQ-IBKR-05 | Credentials nur lokal, CI frei | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION K8; `tests/test_ibkr_isolation.py::test_ci_workflows_reference_no_ibkr_secret` |
| REQ-IBKR-06 | `ib_async==2.1.0` + `tzdata`-Pin | umgesetzt | 2 | IB Gateway/Adapter | `test_ibkr_isolation.py::test_ibkr_extra_pins_the_client_library_exactly`, `::test_tzdata_cap_carries_its_reason` |
| REQ-IBKR-07 | Ein Adapter, ≤ 10 Methoden | umgesetzt | 2 | IB Gateway/Adapter | `test_ibkr_isolation.py::test_only_the_adapter_imports_the_client_library`, `::test_adapter_has_at_most_ten_public_methods` |
| REQ-IBKR-08 | Fester `clientId`, Order-IDs ab `nextValidId` | teilweise (Phase 6 läuft) | 2 | IB Gateway/Adapter | clientId 20001 belegt (02-VERIFICATION Z. 138); „`nextValidId` erst mit Orders (Phase 6)“ |
| REQ-IBKR-09 | Benannte Betriebszustände, Probe-Liveness | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION Z. 139 (`STATE_BY_CODE`); Lücke 2107 → UNKNOWN (Info) |
| REQ-IBKR-10 | Schreibrecht als dokumentierte Einmalhandlung | teilweise (Phase 6 läuft) | 6 | IB Gateway/Adapter | 321-Beleg am 2026-10-19 (Sonde, `READ_ONLY_API`, `035af86`); Freischaltung und Handbuchvermerk in 06-10 offen; Code 06-03/-05/-06/-08 |
| REQ-IBKR-11 | Kontolesen füllt `PortfolioContext` | umgesetzt | 2 | IBKR-Ausführer | 02-VERIFICATION K1/K7 (real 2026-10-12); CI-Verdrahtung ist ROADMAP Phase 7 SC6 (offen) |
| REQ-IBKR-12 | Ist-Position je Lauf frisch | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION Z. 141 |
| REQ-IBKR-13 | Lesequelle nur `decision-log.md` | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION; `test_only_log_and_summary_paths_are_read` |
| REQ-IBKR-14 | `schema_version == 1` + Vertragstest | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION; `tests/test_paper_summary_contract.py` |
| REQ-IBKR-15 | `state_maintenance verify` als Vorbedingung | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION (`log-finding`, Exit 2) |
| REQ-IBKR-16 | Nur `status ok` + fünf Stufen | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION (null/REVIEW/status je eigener Zustand) |
| REQ-IBKR-17 | Querprobe Log-Rating vs. Summary | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION SC3 (Divergenz, Exit 2) |
| REQ-IBKR-18 | Kein Zugriff auf `runs[*].report` | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION |
| REQ-IBKR-19 | Aktualität in Sitzungen | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION SC4 (XNYS-Kalender, `stale-decision`) |
| REQ-IBKR-20 | Fr→Mo als `weekend_gap` | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION; Ledger-Feld ab Phase 5 |
| REQ-IBKR-21 | Zielpositions-Leiter, Hold nie Order | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION SC1 (real AAPL Hold → `skipped: hold`) |
| REQ-IBKR-22 | Block = feste Stückzahl | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION (`block_qty` in `CONTRACT_TABLE`) |
| REQ-IBKR-23 | `Ziel − Ist − offen`, Toleranzband | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION SC6 |
| REQ-IBKR-24 | Long-only, Sell ohne Bestand = Nulloperation | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION SC8 (`long-only-noop`) |
| REQ-IBKR-25 | Markt-Order im Sitzungsfenster, Limit nur `DAY` | umgesetzt | 4+5 | Leitplanken | 04-VERIFICATION (MKT/DAY) + 05-VERIFICATION Z. 47 (Fenster, `outside-session`) |
| REQ-IBKR-26 | Marktdaten außerhalb Order-Pfad | umgesetzt | 3 | IB Gateway/Adapter | 03-VERIFICATION SC8 (`reqMarketDataType(3)`) |
| REQ-IBKR-27 | Auflösung vom Roh-Ticker | umgesetzt | 3 | IB Gateway/Adapter | 03-VERIFICATION SC5 |
| REQ-IBKR-28 | Allow-List `{STK}` | umgesetzt | 3 | IB Gateway/Adapter | 03-VERIFICATION SC2, real bestätigt |
| REQ-IBKR-29 | Genau ein Contract-Treffer | umgesetzt | 3 | IB Gateway/Adapter | 03-VERIFICATION SC3 |
| REQ-IBKR-30 | `conId` persistiert + Identitätsprüfung | umgesetzt | 3 | IB Gateway/Adapter | 03-VERIFICATION SC1/SC4 (`contracts.json`) |
| REQ-IBKR-31 | Handelbarkeit abgefragt | umgesetzt (Override) | 3 | IB Gateway/Adapter | Override D-19 (2026-10-18): `ineligibilityReasonList` fehlt in ib_async 2.1.0, Ersatz `validExchanges`/`orderTypes` |
| REQ-IBKR-32 | [L1] Harte Obergrenze je Order | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC4; `ibkr_guards.py` |
| REQ-IBKR-33 | [L2] Kill-Switch fail-closed (RELEASE+KILL) | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC1 (Exit 4) |
| REQ-IBKR-34 | [L2] Prüfung vor jeder Order | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC2 |
| REQ-IBKR-35 | [L2] `reqGlobalCancel` bei Kill | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC3; real 2026-10-17 (`ibkr-konto-befund.md` „Kill-Storno“) |
| REQ-IBKR-36 | [L2] Schalterzustand je Lauf protokolliert | umgesetzt | 5 | Leitplanken | 05-VERIFICATION (`run_start`/`run_end`) |
| REQ-IBKR-37 | [L3] Sitzung aus `ContractDetails`, Halt | umgesetzt (Override) | 3 (+4) | IB Gateway/Adapter | 03-VERIFICATION SC6/SC7; Halt-Teil per Override D-20 an whatIf/154 (Phase 4) |
| REQ-IBKR-38 | `whatIf` vor jeder Order | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION (Phase-4-Teil); scharfer Pfad im Code (06-05), realer Lauf mit 06-10 |
| REQ-IBKR-39 | [L4] `decision_key` ohne SHA | umgesetzt | 5 | Leitplanken | 05-VERIFICATION; `orderRef` mit Pipe-Zeichen live bestätigt |
| REQ-IBKR-40 | [L4] Ein Versuch je Schlüssel | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC8 (`Ledger.attempt_of`) |
| REQ-IBKR-41 | [L4] `orderRef` = Schlüssel, SHA = Provenienz | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC8 |
| REQ-IBKR-42 | [L4] Write-Ahead, `skipped` mit Grund | umgesetzt | 5 | Leitplanken | 05-VERIFICATION (`REASON_BY_STATE`) |
| REQ-IBKR-43 | [L4] Startup-Reconciliation, drei Quellen | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC6 (Exit 6) |
| REQ-IBKR-44 | [L4] Nicht-blockierender Lauf-Lock | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC7 (Exit 7) |
| REQ-IBKR-45 | Prüfkette an einer Stelle, Reihenfolge getestet | teilweise (Phase 6 läuft) | 6 | IBKR-Ausführer | 06-02/-04/-08 SUMMARY; `tests/test_ibkr_call_order.py`; keine Phase-6-VERIFICATION |
| REQ-IBKR-46 | Ledger JSONL außerhalb Git | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC5; `scripts/ibkr_ledger.py` |
| REQ-IBKR-47 | `execId`-Dedup mit Korrekturregel | teilweise (Phase 6 läuft) | 6 | Leitplanken | 06-01/-05 SUMMARY (`2e8ab05`); gegen Fixture, echte Fills fehlen |
| REQ-IBKR-48 | Executions tagesgleich persistiert | teilweise (Phase 6 läuft) | 6 | Leitplanken | 06-05/-06/-07 SUMMARY; realer Handelstag fehlt |
| REQ-IBKR-49 | Soll-Ist-Join beim Lesen | offen | 7 | Rückkanal/Betrieb | ROADMAP Phase 7 „Plans: TBD“ |
| REQ-IBKR-50 | Ausführungs- vs. Entscheidungsmetriken getrennt | offen | 7 | Rückkanal/Betrieb | ROADMAP Phase 7 TBD |
| REQ-IBKR-51 | Backup-Allow-Liste + Ledger/Contract-Cache | offen | 7 | State/Ops | `state_maintenance.py` nennt weder Ledger noch `contracts.json` (grep leer) |
| REQ-IBKR-52 | Eigener Branch, ein Schreiber je Branch | offen | 7 | Rückkanal/Betrieb | ROADMAP Phase 7 TBD |
| REQ-IBKR-53 | Heartbeat bei jedem Lauf | offen | 8 | Rückkanal/Betrieb | ROADMAP Phase 8 TBD; kein Push im Ausführer |
| REQ-IBKR-54 | CI-Cron prüft Heartbeat-Alter | offen | 8 | Rückkanal/Betrieb | kein solcher Workflow in `.github/workflows/` |
| REQ-IBKR-55 | Disjunkte Exit-Codes + UTF-8-Log | umgesetzt | 2 | IBKR-Ausführer | 02-VERIFICATION; `test_ibkr_isolation.py::test_handbook_exit_table_matches_executor` |
| REQ-IBKR-56 | Task-Scheduler-Einstellungen | offen | 8 | Rückkanal/Betrieb | `IBKR_EXECUTION.md` enthält kein Scheduler-Kapitel (grep leer) |
| REQ-IBKR-57 | Vorbedingungen selbst prüfen | teilweise | 8 | IBKR-Ausführer | Aktualität (REQ-19) und Sitzung (REQ-25/37) prüft der Ausführer schon selbst; Scheduler-Kontext fehlt |
| REQ-IBKR-58 | Task-History aktiviert, dokumentiert | offen | 8 | Rückkanal/Betrieb | kein Handbuchabschnitt |
| REQ-IBKR-59 | Gateway-Dauerbetrieb + Wochenlogin | offen | 8 | IB Gateway/Adapter | Handbuch ohne Auto-Restart/`ClosedownAt`/Wochenlogin (grep leer) |
| REQ-IBKR-60 | Betriebshandbuch `IBKR_EXECUTION.md` | teilweise | 8 | IBKR-Ausführer | Datei existiert (1011 Zeilen: Exit-Codes, RELEASE/KILL, Ledger); Scheduler, Wochenlogin, Soll-Ist-Bericht fehlen |
| REQ-IBKR-61 | Leeres `whatIf` = Ablehnung | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION (`preview-empty`, Exit 5) |
| REQ-IBKR-62 | Timeout auf jedem API-Aufruf | umgesetzt | 2 | IB Gateway/Adapter | 02-VERIFICATION Z. 143 |
| REQ-IBKR-63 | Zwei Quellen je kritischem Fakt | umgesetzt | 5 | Leitplanken | 05-VERIFICATION (05-07) |
| REQ-IBKR-64 | Kill-Switch fail-closed vor jeder Order | umgesetzt | 5 | Leitplanken | 05-VERIFICATION SC1/SC2 |
| REQ-IBKR-65 | Nach der Order gegen IBKR verifizieren | teilweise (Phase 6 läuft) | 6 | IBKR-Ausführer | 06-04/-05/-06 SUMMARY (Post-Order-Kontrolle, `alarm`); keine reale Order |
| REQ-IBKR-66 | Negativ-Kontrolle je Schutzmaßnahme | umgesetzt | 5 | Leitplanken | 05-VERIFICATION (29 Tests); für `--live` zusätzlich 06-08 |
| REQ-IBKR-67 | Fehlercodes real gemessen | teilweise | 2 | IB Gateway/Adapter | Override 2026-10-12: 321/2104/2158/2107 gemessen; 1100/1101/1102/1300/2110 erst mit Phase 8 K6 |
| REQ-IBKR-68 | Keine geschätzte Größe ohne Kurs | umgesetzt | 4 | IBKR-Ausführer | 04-VERIFICATION; `test_no_market_data_in_execution_path` |
| REQ-IBKR-69 | `tif` explizit setzen und zurücklesen | umgesetzt | 4 | IB Gateway/Adapter | 04-05/04-08 SUMMARY `requirements-completed` |
| REQ-IBKR-70 | Budget über `initMarginChange` | umgesetzt | 4 | IBKR-Ausführer | 04-05/04-08 SUMMARY |

Hinweis zu REQ-69/-70: Sie stehen nicht in der Anforderungstabelle von 04-VERIFICATION, nur in den SUMMARY-Frontmattern. Der Beleg ist deshalb schwächer als bei den übrigen Phase-4-IDs.

## 3. Upstream TradingAgents (v0.7.0, `e8f5503`)

Status bedeutet hier: im Code am HEAD vorhanden. „Im Paper-Lauf“ sagt, ob der tägliche Lauf die Funktion benutzt (`daily-paper-run.yml`, `daily_paper_run.py`; Analysten-Default `("market","social","news","fundamentals")`, `trading_graph.py:65`).

| ID | Kurztitel | Herkunft | Status | Phase/Quick | Komponente | Nachweis |
|---|---|---|---|---|---|---|
| U-01 | Markt-/Technik-Analyst (Indikatoren) | Upstream | umgesetzt | — | Analysten | `analysts/market_analyst.py`; im Paper-Lauf |
| U-02 | Sentiment-Analyst (News, StockTwits, Reddit) | Upstream | umgesetzt | — | Analysten | `analysts/sentiment_analyst.py`, `vendors/stocktwits.py`, `reddit.py`; `test_social_lookahead.py`; im Paper-Lauf |
| U-03 | News-Analyst (Firma + Makro) | Upstream | umgesetzt | — | Analysten | `analysts/news_analyst.py`, `test_news_analyst_prompt.py`; im Paper-Lauf |
| U-04 | Fundamentals-Analyst (Bilanzen, Insider) | Upstream | umgesetzt | — | Analysten | `analysts/fundamentals_analyst.py`, `test_fundamentals_lookahead.py`; im Paper-Lauf |
| U-05 | Parallele Analysten | Upstream | umgesetzt | — | Analysten | `graph/analyst_execution.py`, `test_analyst_execution.py` (v0.5.2) |
| U-06 | Social-Post-Screening via Jev | Upstream | umgesetzt | — | Jev | `agents/post_screen.py` (`TYPESAFE_API_KEY`), `test_post_screen.py`; **im Paper-Lauf inaktiv** (Workflow setzt keinen `TYPESAFE_API_KEY`) |
| U-07 | Bull/Bear-Debatte | Upstream | umgesetzt | — | Debatte | `researchers/bull_researcher.py`, `bear_researcher.py`; `max_debate_rounds=1`; `test_debate_opening.py` |
| U-08 | Research Manager (structured, 5 Stufen) | Upstream | umgesetzt | — | Debatte | `managers/research_manager.py`, `test_structured_agents.py` |
| U-09 | Trader (3 Stufen, Preisbezug) | Upstream | umgesetzt | — | Trader/Risiko/PM | `trader/trader.py` |
| U-10 | Risiko-Debatte (3 Debattierer) | Upstream | umgesetzt | — | Trader/Risiko/PM | `risk_mgmt/` (aggressive, conservative, neutral); `max_risk_discuss_rounds=1`; `test_risk_router_path_map.py` |
| U-11 | Portfolio Manager (5 Stufen) | Upstream | umgesetzt | — | Trader/Risiko/PM | `managers/portfolio_manager.py` |
| U-12 | Structured Output Entscheider-Trio | Upstream (+ Strang-Retry) | umgesetzt | 260814-k1j (Retry) | Trader/Risiko/PM | `agents/structured.py`, `schemas.py`; `test_structured_agents.py` |
| U-13 | Rating-Extraktion deterministisch | Upstream | umgesetzt | — | Trader/Risiko/PM | `agents/rating.py` (`extract_rating`, `parse_rating`, `run_rating`); `test_rating_integrity.py`, `test_signal_processing.py` |
| U-14 | Portfolio-Kontext (Bestand) | Upstream | umgesetzt | M2 Ph. 2 (Befüllung) | Trader/Risiko/PM | `tradingagents/portfolio.py`, `test_portfolio_context.py`; im CI-Paper-Lauf nicht übergeben (Phase 7) |
| U-15 | Decision-Log (Memory) | Upstream (+ Strang h63) | umgesetzt | 261019-h63 | Memory/Settlement | `memory/log.py`, `test_memory_log.py`; `paper-log:decision-log.md` |
| U-16 | Settlement: Return + Alpha, Haltefenster | Upstream (+ Strang h63) | umgesetzt | 261019-h63 | Memory/Settlement | `memory/settlement.py` (`holding_period_days=5`), `d90408e`, `test_memory_pointintime.py` |
| U-17 | Reflexion (Lessons an PM) | Upstream | umgesetzt | — | Memory/Settlement | `memory/reflection.py`; `_memory_step` in `trading_graph.py` |
| U-18 | Backtest über Ticker×Datum-Gitter | Upstream (+ Strang-Fix) | umgesetzt | 261018-kof (#5) | Backtest | `backtest.py`, `test_backtest.py`; Strang-Patch `33767b3` |
| U-19 | Checkpoint-Resume (SQLite je Ticker) | Upstream | umgesetzt | — | Graph/Orchestrierung | `graph/checkpointer.py`, `test_checkpoint_resume.py`; im Paper-Lauf aus (`daily_paper_run.py:280`) |
| U-20 | LangGraph-Aufbau und Routing | Upstream | umgesetzt | — | Graph/Orchestrierung | `graph/setup.py`, `conditional_logic.py`, `propagation.py`; `test_graph_end_to_end.py` |
| U-21 | Reports (Markdown + HTML-Seite) | Upstream | umgesetzt | — | Graph/Orchestrierung | `reporting.py`, `report_html.py`, `test_report_html.py` |
| U-22 | CLI interaktiv + headless | Upstream (+ Strang-Exits) | umgesetzt | — | CLI | `cli/main.py`, `cli/run.py`; `test_cli_headless.py` |
| U-23 | CLI `backtest`-Subkommando | Upstream | umgesetzt | — | CLI | README „Evaluating decisions over time“, `test_cli_commands.py` (1 Test unter Windows rot, STATE) |
| U-24 | Update-Hinweis beim Start | Upstream | umgesetzt | — | CLI | `cli/updates.py`; `test_cli_updates.py` 2× rot unter Windows (STATE Blockers) |
| U-25 | Docker-Image | Upstream | umgesetzt | — | CLI | `Dockerfile`, `docker-compose.yml`; per Strang-Smoke geprüft |
| U-26 | Provider-Registry (über 18 Provider) | Upstream | umgesetzt | — | LLM-Provider | `llm_clients/api_key_env.py`, `model_catalog.py`; `test_provider_registry.py`; Paper-Lauf: anthropic |
| U-27 | Provider je Tier (quick/deep) | Upstream (+ Strang-Fail-fast) | umgesetzt | — | LLM-Provider | `default_config.py` `*_think_provider`, `test_tier_providers.py` |
| U-28 | ChatGPT-Plan-Anmeldung | Upstream | umgesetzt | — | LLM-Provider | `llm_clients/chatgpt_auth.py`; `test_chatgpt_auth.py` 2× rot unter Windows (`0o600`) |
| U-29 | Vendor-Router mit Fallback | Upstream | umgesetzt | — | Datenquellen | `dataflows/router.py`, `test_vendor_routing.py`; Defaults yfinance, Alpha Vantage optional |
| U-30 | SEC EDGAR „as filed“ | Upstream | umgesetzt | — | Datenquellen | `vendors/sec_edgar.py`, `test_sec_edgar.py` |
| U-31 | FRED-Makrodaten | Upstream | umgesetzt | — | Datenquellen | `vendors/fred.py`, `test_fred.py`; braucht `FRED_API_KEY` (Workflow reicht Secret durch, ob gesetzt: unklar) |
| U-32 | Polymarket-Prognosemärkte | Upstream | umgesetzt | — | Datenquellen | `vendors/polymarket.py`, `test_polymarket.py` |
| U-33 | Point-in-time / Look-ahead-Schutz | Upstream | umgesetzt | — | Datenquellen | `dataflows/date_window.py`; `test_news_lookahead.py`, `test_tool_date_enforcement.py` |
| U-34 | Ticker-Validierung, Symbol-Normalisierung | Upstream (+ Strang-CLI) | umgesetzt | — | Datenquellen | `dataflows/symbols.py`; `test_safe_ticker_component.py`, `test_symbols.py` |
| U-35 | Order an simulierte Börse (README) | Upstream | offen | — (Ersatz: M2) | IBKR-Ausführer | README „order will be sent to the simulated exchange“; im Code keine Ausführung (`backtest.py:9` „not a portfolio simulator“). Der Strang ersetzt das durch den IBKR-Ausführer |

## 4. Strang-Zusätze außerhalb M1/M2 (für Diagramm und Methodenteil)

| ID | Kurztitel | Herkunft | Status | Phase/Quick | Komponente | Nachweis |
|---|---|---|---|---|---|---|
| S-01 | Jev-Run-Review: REVIEW-Fallback + Shadow-Checks | Strang | umgesetzt | 261012-t8w | Jev | `tradingagents/jev/hooks.py`, `client.py`; `test_jev_hooks.py`, `test_jev_client.py`; HEAD `a7af62d` |
| S-02 | Jev im täglichen Paper-Lauf | Strang | umgesetzt | 261012-uth | Paper-Lauf (GitHub Actions) | `daily-paper-run.yml:88,102` (`TRADINGAGENTS_JEV_ENABLED`, `JEV_API_KEY`); Live-Lauf 38301659963 |
| S-03 | Jev-Fallback-Rating in IBKR-Kette erkennen | Strang | teilweise (Phase 6 läuft) | 06-02, Todo 2026-10-16 | IBKR-Ausführer | 06-02 SUMMARY (State `rating-jev` über `summary.json`); Todo noch in `todos/pending/` |
| S-04 | Muster-Auswertung (6 Muster, Wilson, MIN_N) | Strang | umgesetzt | 261018-kof | Patterns | `tradingagents/patterns/`, `scripts/pattern_eval.py`, `test_patterns_*.py`; Ergebnis: alle Zellen `insufficient` (1 von 16 abgerechnet); nur Nachauswertung |
| S-05 | Settlement-Folgefixes (Exit-Bar, Ties, `SETTLEMENT:`) | Strang (Upstream-Kandidat) | umgesetzt | 261019-h63 | Memory/Settlement | `ea055f5`, `b1fa2a4`, `d90408e` |
| S-06 | Backtest: unlesbares Alpha nicht als pending | Strang (Upstream-Kandidat) | umgesetzt | 261018-kof | Backtest | `33767b3`, `test_backtest.py` |
| S-07 | Rebase-Kadenz auf Upstream-Releases | Strang | umgesetzt | 260922-iz5, 261010-raj, 261017-r7x | CI/Smoke | Basis v0.7.0 `e8f5503`, Backup-Branch `backup/pre-rebase-v0.7.0` |
| S-08 | Fail-closed-Prinzip (S-01..S-08 → REQ-61..68) | Strang | umgesetzt | 261012-ap2 | Leitplanken | in REQUIREMENTS §7 übernommen; Status je ID siehe Tabelle 2 |

## Unklare Punkte

- **REQ-IBKR-38:** gezählt als „umgesetzt“ (Phase 4 verifiziert). Ob ein gesetztes `rejectReason` auch im scharfen Pfad greift (Phase 6 SC7), ist nur durch Tests in 06-08 belegt und nicht real.
- **U-31 FRED / M1-P2-6:** Ob `FRED_API_KEY` und `ALPHA_VANTAGE_API_KEY` als Secrets im Fork gesetzt sind, lässt sich aus dem Repo nicht sehen. Die Funktion ist da, ihr Einsatz im Paper-Lauf ist unklar.
- **M1-P2-9:** Als „umgesetzt“ gezählt, weil die DoD es abhakt. Inhaltlich hat sich der Punkt dadurch erledigt, dass Upstream `uv.lock` entfernt hat, nicht durch eine eigene Policy.
- **REQ-IBKR-07:** Der Test für „höchstens zehn öffentliche Methoden“ existiert am HEAD und ist nicht als rot gemeldet. Eine eigene Testausführung in dieser Recherche gab es nicht.
