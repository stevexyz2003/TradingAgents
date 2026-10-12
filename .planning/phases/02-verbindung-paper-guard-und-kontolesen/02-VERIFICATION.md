---
phase: 02-verbindung-paper-guard-und-kontolesen
verified: 2026-10-12T13:55:00Z
status: passed
score: 8/8 Roadmap-Kriterien belegt (6 automatisch; K1 und K7 am 2026-10-12 16:34 am echten System mit dem Code nach den Review-Fixes, HEAD 0178678); REQ-IBKR-67 per Override
overrides_applied: 1
overrides:
  - must_have: "REQ-IBKR-67 Fehlercodes gemessen, nicht angenommen (Link-Codes 1100/1101/1102/1300/2110)"
    reason: "Offiziell dokumentierte IBKR-Codes, von ib_async selbst behandelt; eine Messung erfordert eine absichtliche Störung des Gateways und folgt mit Phase 8 K6 (1100-Fehlerbild). Fail-closed bleibt gewahrt: Ein unerwarteter Code lässt die Liveness-Probe weiter scheitern, ein Snapshot nach Verbindungsabbruch gilt also nicht als gesund."
    accepted_by: "Operator"
    accepted_at: "2026-10-12T14:50:00Z"
re_verification: "2026-10-12T14:50:00Z — alle 4 human_verification-Punkte erledigt, siehe 02-HUMAN-UAT.md"
human_verification:
  - test: "K1 erneut am echten Gateway, mit dem Code-Stand nach den Fixes (HEAD 54eed3f): `python scripts/ibkr_executor.py account --out \"%LOCALAPPDATA%\\TradingEngineX\\ibkr\\portfolio.json\"`"
    expected: "Exit 0; das JSON enthält `cash`, `currency`, `positions` UND `as_of` (UTC, ISO 8601); `load_portfolio()` liest es; im Log kein `WRITE_REFUSED`, kein `UNEXPECTED`, kein Traceback, kein `placeOrder`/`orderStatus`"
    why_human: "Braucht das laufende Paper-Gateway. Der echte Lauf vom 2026-10-12 13:26 (4eb3695) lief VOR a1e4283..fdee790. Danach hat sich der Verbindungsweg geändert: Schreibsperre auch auf `send`/`sendMsg`, Leeren von `wrapper.acctSummary`, 0,05 s Settle-Fenster mit Link-Code-Prüfung, neue Loop-Behandlung. Das ist bisher nur gegen FakeIB und das unverbundene `ib_async`-Objekt belegt. Die echte Datei hat kein `as_of` (selbst geprüft: Schlüssel `cash`, `currency`, `positions`)."
  - test: "K7 erneut als verkettete Kette aus dem Handbuch (`scripts/IBKR_EXECUTION.md:251`): `ibkr_executor.py account ... && daily_paper_run.py --tickers AAPL --max-cost 0.50 ... --portfolio <json>`, mit `TRADINGAGENTS_LLM_PROVIDER=anthropic` und den CI-Modellvariablen"
    expected: "Beide Exit 0; `complete_report.md` enthält „Portfolio at the analysis date:“ und „Cash available: … EUR“; die Konsole nennt `as_of checked against 60 min`"
    why_human: "Kostet LLM-Aufrufe und braucht das Gateway. Der Lauf aus 02-06 nutzte das JSON ohne `as_of`. Mit dem heutigen Code lehnt `daily_paper_run.py` genau diese Datei ab (selbst geprüft: `--preflight` mit der echten Datei endet mit Exit 1, „has no as_of timestamp“). Die Kette nach den Fixes ist am echten System also noch nicht gelaufen."
  - test: "REQ-IBKR-67: Entscheidung, ob die Link-Codes 1100/1101/1102/1300/2110, auf die CR-01 jetzt baut, am echten Gateway gemessen werden müssen oder per Override akzeptiert werden"
    expected: "Entweder eine datierte Messung (z. B. Netz des Gateway-Rechners kurz trennen und die Codes im Log notieren), oder ein Override-Eintrag mit Begründung (offiziell dokumentierte Codes, `ib_async` behandelt 1100/1101/1102 selbst, Phase-8-Kriterium 6 notiert das 1100-Fehlerbild)"
    why_human: "REQ-IBKR-67 verlangt: Codes, auf die eine Sicherung baut, sind vorher am realen Gateway gemessen. Gemessen sind 321 (2026-10-11), 2104/2158/2107 (2026-10-12) und das Ausbleiben von 326 mit clientId 20001. Die Link-Codes und das Verhalten von 326 als TimeoutError sind nur aus Doku bzw. Bibliotheks-Quelltext abgeleitet. Fällt der Code am echten Gateway anders aus, greift die Snapshot-Verwerfung nicht (fail-open)."
  - test: "Gateway-Einstellung „Allow connections from localhost only“ prüfen (Beobachtung 2 aus 02-05: Gateway lauscht auf `:::7497`)"
    expected: "Häkchen gesetzt und mit Datum im Handbuch notiert, oder die Ausnahme ist bewusst begründet"
    why_human: "Einstellung in der Gateway-GUI, aus dem Repo nicht lesbar. Der Adapter beschränkt `IBKR_HOST` nicht auf Loopback (IN-07 nicht umgesetzt)."
---

# Phase 2: Verbindung, Paper-Guard und Kontolesen – Verifikationsbericht

**Phasenziel:** Ein lokaler Prozess verbindet sich reproduzierbar gegen `DUQ634065`, beweist beim Verbinden, dass es das Paper-Konto ist, und legt Bestand und freies Kapital als `PortfolioContext`-JSON ab, ohne Schreibrecht.
**Verifiziert:** 2026-10-12T13:55:00Z
**Status:** human_needed
**Re-Verifikation:** Nein, Erstprüfung

Geprüft wurde der Code auf HEAD `54eed3f`, also nach CR-01, CR-02 und WR-01..07. Den Snapshot aus den SUMMARYs habe ich nicht übernommen.

## Zielerreichung

### Beobachtbare Wahrheiten (ROADMAP-Erfolgskriterien)

| # | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | Kommando liest Positionen und Cash gegen das laufende Gateway und schreibt JSON, das `load_portfolio()` validiert; Exit 0 | ? REAL NUR VOR DEN FIXES | Real: 02-05, Lauf 2026-10-12 13:26, Exit 0, `load_portfolio` ok (Code-Stand 4eb3695). Heute: `run_account` schreibt atomar mit `check=load_portfolio` und prüft danach gegen (`scripts/ibkr_executor.py:337-340`); `test_account_writes_portfolio_that_load_portfolio_accepts` ist grün. Der Wortlaut des Kriteriums ist damit real gezeigt, weil `load_portfolio` `as_of` ignoriert. Der Verbindungsweg hat sich nach dem Lauf aber geändert, und die echte Datei hat kein `as_of`. Ein erneuter Lauf ist nötig (human item 1). |
| 2 | Stub mit abweichender Kontomenge → Exit 8, Trennung, kein Platzierungsaufruf | ✓ VERIFIED | Guard `accounts != [EXPECTED_ACCOUNT]` direkt nach `connectAsync`, mit `_disconnect()` (`ibkr_broker.py:372-380`). Exit 8 im Executor (`:433-435`). Tests: `test_guard_violation_exits_8_without_writes` (fremd und Obermenge: `disconnect` in calls, keine verbotenen Calls, keine Datei) und `test_guard_rejects_anything_but_the_paper_account` (9 Fälle: leer, Duplikat, Groß/Klein, Leerraum, Präfix, länger). Nach WR-05 kann die Prüfung auf verbotene Calls tatsächlich scheitern. |
| 3 | Ohne Gateway Exit 3 mit benannter Logzeile (502 / „Gateway nicht erreichbar“), kein Traceback; fehlende Zugangsdaten → Exit 20 | ✓ VERIFIED | Selbst ausgeführt, mit dem echten `ib_async` gegen `127.0.0.1:1`: Exit 3, stderr genau eine Zeile `ibkr-state=GATEWAY_UNREACHABLE code=502 detail="Gateway nicht erreichbar: 127.0.0.1:1 (ConnectionRefusedError)"`, kein Traceback. Die Bibliotheks-Logs landen in der Logdatei, und eine alte `--out`-Datei wurde entfernt. Fehlende `.env` → Exit 20. Falsches Konto → Exit 1. |
| 4 | `ib_async`-Suche in `tradingagents/` und `scripts/` nennt genau eine Datei; Adapter ≤ 10 öffentliche Methoden | ✓ VERIFIED | `git grep -l -w ib_async -- 'tradingagents/*.py' 'scripts/*.py' 'cli/*.py'` → nur `scripts/ibkr_broker.py`. Auch ohne Dateityp-Filter (inkl. `IBKR_EXECUTION.md`) nur diese Datei. `IbkrBroker` hat genau `connect`, `positions`, `health` (AST-Test `test_adapter_has_at_most_ten_public_methods`). Einziger Import in `_default_ib_factory` (`:185`). |
| 5 | Liveness hängt an einer echten Probe-Antwort; „Socket oben, Session tot“ → nicht gesund | ✓ VERIFIED | `health()` gibt `ok=True` nur bei genau einer Antwort mit `conId == 265598` (`:403-432`). `test_health_socket_up_session_dead` prüft: Probe hängt, `isConnected()` ist True, Ergebnis `PROBE_TIMEOUT`, `ok=False`, < 1 s. Dazu prüft der Code nach CR-01 Link-Ereignisse während der Probe. |
| 6 | `ib_async==2.1.0` + `tzdata>=2025.2,<2026.0` lösen auf; mit `tzdata>=2026.1` → `ResolutionImpossible` | ✓ VERIFIED | Heute selbst ausgeführt: `pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"` → `ERROR: ResolutionImpossible`, Exit 1. Das gepinnte Paar → Exit 0. `.venv`: ib_async 2.1.0, tzdata 2025.2. Extra `ibkr` in `pyproject.toml:44-50` mit Begründungskommentar; Kern-`dependencies` ohne ib_async. |
| 7 | Lokaler `daily_paper_run.py`-Lauf mit dem erzeugten JSON zeigt den `PortfolioContext.render()`-Block im Report | ? REAL NUR VOR DEN FIXES | Verdrahtung heute: `--portfolio` → `load_fresh_portfolio` (`daily_paper_run.py:137-176`) → `run_ticker(..., portfolio=)` → `graph.propagate(..., portfolio=)` (`:365-366`) → `trading_graph.py:327` `portfolio.render()` → `final_state["portfolio_context"]` → `reporting._header` (`reporting.py:47-49`). Real: 02-06, Exit 0, Block in Zeilen 10-12. Dieser Lauf nutzte ein JSON ohne `as_of`. Mit dem heutigen Code endet der Preflight mit genau dieser Datei mit Exit 1 (selbst geprüft). Die Kette nach den Fixes ist real noch nicht gelaufen (human item 2). |
| 8 | `git ls-files .env` leer; keine IBKR-Secret-Referenz in `.github/workflows/` | ✓ VERIFIED | `git ls-files .env` → leer. `grep -rni ibkr .github/workflows/` → kein Treffer. Seit `43ae64c` kein Diff unter `.github/workflows/`. Als Tests abgesichert: `test_env_file_is_not_tracked`, `test_ci_workflows_reference_no_ibkr_secret`. |

**Score:** 6/8 automatisch verifiziert. 2/8 sind real belegt, aber nur mit dem älteren Code-Stand, und warten auf einen erneuten Lauf. Kein Kriterium ist FAILED.

### Plan-Wahrheiten (must_haves aus 02-01..02-06), zusätzlich zu den Roadmap-Kriterien

| Plan | Wahrheit (gekürzt) | Status | Beleg |
|---|---|---|---|
| 02-01 | Extra `ibkr` mit Pin und Kommentar; Kern unverändert | ✓ | `pyproject.toml:42-50`, `test_ibkr_extra_pins_the_client_library_exactly`, `test_tzdata_cap_carries_its_reason` |
| 02-01 | ROADMAP-K6 und REQ-06-Nachweis umformuliert | ✓ | `ROADMAP.md:96`, `REQUIREMENTS.md:48` |
| 02-02 | `readonly=True`, clientId 20001, `fetchFields=StartupFetchNONE` | ✓ | `ibkr_broker.py:318-327`, `test_connect_uses_readonly_fixed_client_id_and_no_startup_fetch` |
| 02-02 | Schreibsperre vor `connectAsync` | ✓ (verstärkt) | `_arm_write_barrier` (`:200-240`) vor `connectAsync` (`:314`). Seit WR-01 auch auf Drahtebene (IDs 3/4/19/21/58). Mit dem Bibliotheks-Quelltext abgeglichen: Die gedrosselte Wiederholung `loop.call_at(..., self.sendMsg, None)` (`client.py:346`) läuft durch den Wrapper und wird bei `None` durchgelassen. Der Handshake geht über `conn.sendMsg` und ist nicht betroffen. |
| 02-02 | Kontomenge ≠ genau `['DUQ634065']` → Trennung und `AccountGuardViolation` | ✓ | siehe K2 |
| 02-02 | `health()`-Regeln inkl. eines vor dem Aufruf in der Loop wartenden 1100 | ✓ | `test_health_sees_1100_queued_before_the_call` und die Tests danach |
| 02-02 | Jeder Request unter `asyncio.wait_for` | ✓ | `_call` (`:550-557`). Connect-Grenze 15 s, im Handbuch benannt (WR-04). Hängender Connect getestet: `test_hanging_connect_ends_at_the_outer_bound` |
| 02-02 | `positions()` fragt jedes Mal neu, filtert Konto und Menge ≠ 0 | ✓ | `reqPositionsAsync` und `accountSummaryAsync` nach `acctSummary.clear()` (`:459-465`, WR-02). `test_positions_fresh_each_call`, `test_the_library_answers_the_summary_from_its_cache` (am echten IB-Objekt), `test_positions_filters_account_and_zero` |
| 02-02 | Genau ein Importort, ≤ 10 Methoden | ✓ | siehe K4 |
| 02-03 | `--portfolio` lädt vor dem Graph-Bau und reicht an `propagate` durch; ohne `--portfolio` unverändert; ungültige Datei → Exit 1, auch unter `--preflight` | ✓ | Tests `test_portfolio_is_passed_to_propagate`, `test_without_portfolio_propagate_gets_no_portfolio_kwarg`, `test_invalid_portfolio_fails_preflight_too`. Hinweis: Der Key-Link-Pattern `load_portfolio(` passt nicht mehr wörtlich. `load_fresh_portfolio` ruft `PortfolioContext.model_validate` auf der gleichen Datei auf, was inhaltlich dasselbe ist wie `load_portfolio`. Ein Test hält die Gleichheit fest (`ctx == load_portfolio(out)`). |
| 02-03 | Report-Block an/aus | ✓ | `test_report_shows_portfolio_block_when_present`, `test_report_has_no_portfolio_block_without_context` |
| 02-04 | Fremdwährungs-Position → `average_price=null` und WARNING | ✓ | `snapshot_to_portfolio` (`ibkr_executor.py:227-262`), `test_foreign_currency_average_price_is_dropped` |
| 02-04 | Exit 20 / Exit 1 nach Konfigurationsfehler; `IBKR_PASSWORD` nie gelesen oder geloggt | ✓ | `read_settings` übernimmt nur die 3+1 Schlüssel (`:142-143`). `test_password_is_never_read_or_logged`. Spot-Checks: Exit 20 und Exit 1 |
| 02-04 | 10 disjunkte Exit-Codes = Docstring = Handbuch | ✓ | `:52-61`, `test_exit_codes_are_disjoint_and_complete`, `test_handbook_exit_table_matches_executor` |
| 02-04 | UTF-8-Logdatei, absoluter Pfad, erste Zeile nennt sich selbst; Bibliotheks-Logs in der Datei, nicht auf stderr | ✓ | Spot-Check: erste Zeile `log file: C:\...\b.log`, `ib_async.client`-Zeilen in der Datei, Konsole nur eine Zeile |
| 02-04 | Handbuch: clientId 20001, Exit-Tabelle, Zustände, Sperre, Read-Only-Schalter, ohne Bibliotheksnamen | ✓ | `scripts/IBKR_EXECUTION.md`, `test_client_id_is_documented_in_the_handbook`, `test_handbook_does_not_name_the_client_library` |
| 02-05 | Read-Only-Schalter vor dem ersten Lauf an; Paper-User bestätigt; Exit 0; kein 326; Log nennt DUQ634065, kein `placeOrder` | ✓ (real, alter Code-Stand) | 02-05-SUMMARY. Operator-Bestätigung 08:45, Logzeile `ibkr-state=CONNECTED account=DUQ634065 clientId=20001 readonly=True`. Einschränkung: Ein gesunder Health-Probe steht nicht ausdrücklich im Log (Beobachtung 3), er ist nur indirekt belegt. |
| 02-06 | Preflight akzeptiert das echte JSON; Report-Block; kein Schreiben in `paper-log` oder Repo | ⚠ heute nicht mehr wahr für das damalige JSON | Der Preflight mit der echten Datei endet heute mit Exit 1, weil `as_of` fehlt. Das ist so gewollt (CR-02), widerlegt aber die erste Wahrheit von 02-06 für den aktuellen Stand, bis K1 neu läuft. |

### Erforderliche Artefakte

| Artefakt | Erwartet | Status | Details |
|---|---|---|---|
| `scripts/ibkr_broker.py` | Adapter, ≥ 180 Zeilen | ✓ VERIFIED | 598 Zeilen, alle geforderten Exporte vorhanden, verdrahtet über `load_broker_module` im Executor |
| `scripts/ibkr_executor.py` | Kommando `account`, ≥ 200 Zeilen | ✓ VERIFIED | 468 Zeilen, Spot-Checks laufen |
| `scripts/IBKR_EXECUTION.md` | Handbuch, enthält 20001 und `## First real run` | ✓ VERIFIED | 332 Zeilen; verkettete `&&`-Zeile `:251` |
| `tests/ibkr_fakes.py` / `test_ibkr_broker.py` / `test_ibkr_executor.py` / `test_ibkr_isolation.py` | Fakes und Tests | ✓ VERIFIED | 239 / 692 / 624 / 182 Zeilen, alle grün |
| `pyproject.toml` | `ib_async==2.1.0` | ✓ VERIFIED | `:46` |
| `tradingagents/reporting.py` | Block in `_header` | ✓ VERIFIED | `:47-49` |
| `scripts/daily_paper_run.py` | `--portfolio` | ✓ VERIFIED | `:419-456`, plus Frischeprüfung |

### Prüfung der Key Links

| Von | Nach | Über | Status |
|---|---|---|---|
| `ibkr_executor.py` | `ibkr_broker.py` | `spec_from_file_location(Path(__file__).with_name("ibkr_broker.py"))` (`:77`, `:108`) | ✓ WIRED |
| `ibkr_executor.py` | `load_portfolio` | `check=load_portfolio` und Gegenprobe (`:339-340`) | ✓ WIRED |
| `ibkr_broker.py` | `ib.client` | `_arm_write_barrier(ib.client)` vor `connectAsync` (`:314`) | ✓ WIRED |
| `ibkr_broker.py` | `ib.managedAccounts()` | erste Prüfung nach dem Handshake (`:373`) | ✓ WIRED |
| `daily_paper_run.py` | `graph.propagate(..., portfolio=)` | nur wenn nicht None (`:365-366`) | ✓ WIRED |
| `trading_graph.py` | `final_state["portfolio_context"]` | `portfolio.render(company_name)` (`:327`) | ✓ WIRED |
| `reporting._header` | `complete_report.md` | `if final_state.get("portfolio_context")` | ✓ WIRED |
| Executor-JSON | Paper-Run-Frischeprüfung | `AS_OF_KEY == PORTFOLIO_AS_OF_KEY == "as_of"`; `test_written_file_passes_the_paper_runs_freshness_check` | ✓ WIRED (Unit), real ? |

### Datenfluss (Level 4)

| Artefakt | Variable | Quelle | Echte Daten | Status |
|---|---|---|---|---|
| `portfolio.json` | `cash` / `positions` | `reqPositionsAsync` und `accountSummaryAsync` (`TotalCashValue`) live vom Gateway | ja, 1005459.44 EUR am 2026-10-12 (alter Stand) | ✓ FLOWING (alter Stand), Re-Run offen |
| `complete_report.md` Block | `portfolio_context` | `PortfolioContext.render()` aus `--portfolio` | ja, Zeilen 10-12 im Lauf aus 02-06 | ✓ FLOWING (alter Stand), Re-Run offen |

### Behavioral Spot-Checks

| Verhalten | Kommando | Ergebnis | Status |
|---|---|---|---|
| Testsuite | `.venv/Scripts/python.exe -m pytest -q` | 1 failed, 1553 passed, 4 skipped. Fehlschlag nur `test_suite_isolation::test_yfinance_keeps_its_cache_out_of_the_users_home` (bekannt, Windows, upstream-identisch) | ✓ PASS |
| Lint | `ruff check .` | All checks passed | ✓ PASS |
| Importort | `git grep -l -w ib_async -- 'tradingagents/*.py' 'scripts/*.py' 'cli/*.py'` | `scripts/ibkr_broker.py` | ✓ PASS |
| `.env` / CI | `git ls-files .env`; `grep -rni ibkr .github/workflows/` | leer / leer | ✓ PASS |
| Pin-Deckel | `pip install --dry-run ... "tzdata>=2026.1"` | `ResolutionImpossible`, Exit 1; gepinntes Paar Exit 0 | ✓ PASS |
| Exit 20 | `account --env-file <fehlt>` | Exit 20, eine Zeile | ✓ PASS |
| Exit 3 ohne Traceback (echte Bibliothek, Port ohne Listener) | `account` mit `IBKR_PORT=1` | Exit 3, `GATEWAY_UNREACHABLE code=502 … Gateway nicht erreichbar`, alte Datei entfernt | ✓ PASS |
| Exit 1 falsches Konto | `IBKR_ACCOUNT_ID=U1234567` | Exit 1 | ✓ PASS |
| Frischeprüfung gegen die echte, alte Datei | `daily_paper_run.py --portfolio <echt> --preflight` | Exit 1, „has no as_of timestamp“ | ✓ PASS (Sperre wirkt), zeigt zugleich: K7-Kette muss neu laufen |

### Probe-Ausführung

Step 7c: übersprungen. Die Phase deklariert keine `scripts/*/tests/probe-*.sh`, und es gibt keine.

### Abdeckung der Anforderungen

Alle 12 IDs aus ROADMAP Phase 2 sind in mindestens einem PLAN beansprucht. Die Rückverfolgungstabelle in `REQUIREMENTS.md` ordnet genau diese 12 der Phase 2 zu. Es gibt keine verwaisten IDs.

| Anforderung | Plan | Beschreibung | Status | Beleg |
|---|---|---|---|---|
| REQ-IBKR-03 | 02-02, 02-04, 02-05 | Gateway Paper, Host/Port aus `.env`, Paper-Username, `readonly=True` | ✓ SATISFIED | `readonly=True` fest im Code; Host/Port aus `.env`; Paper-User vom Operator bestätigt (2026-10-12) |
| REQ-IBKR-04 | 02-02, 02-04, 02-05 | Paper-Guard, exakte Kontonummer | ✓ SATISFIED | K2 |
| REQ-IBKR-05 | 02-01, 02-04, 02-06 | Credentials nur lokal, CI frei | ✓ SATISFIED | K8 |
| REQ-IBKR-06 | 02-01 | Pin und Begründung | ✓ SATISFIED | K6, heute selbst gemessen |
| REQ-IBKR-07 | 02-02 | ein Adapter, ≤ 10 Methoden, einziger Importort | ✓ SATISFIED | K4 |
| REQ-IBKR-08 | 02-02, 02-04, 02-05 | fester clientId im Handbuch; keine harte Order-ID | ✓ SATISFIED (Phase-2-Umfang) | 20001 im Code und Handbuch, real ohne 326 angenommen. `nextValidId` erst mit Orders (Phase 6); Literal-Test gegen `orderId=` |
| REQ-IBKR-09 | 02-02, 02-04, 02-05 | benannte Zustände, Liveness per Probe | ✓ SATISFIED | `STATE_BY_CODE` enthält alle geforderten Codes, Probe-Liveness, CR-01-Fenster. Lücke: 2107 → `UNKNOWN` (Info) |
| REQ-IBKR-11 | 02-03, 02-04, 02-05, 02-06 | `PortfolioContext`-JSON, Analyse sieht Position | ✓ SATISFIED (Code) / ? real neu | K1 und K7 |
| REQ-IBKR-12 | 02-02, 02-05 | Ist-Position bei jedem Lauf frisch | ✓ SATISFIED | kein Lesen aus dem Cache, Summary-Cache wird geleert; zusätzlich: alte Datei wird vor jedem Lauf gelöscht, Verbraucher verlangt `as_of` |
| REQ-IBKR-55 | 02-04 | disjunkte Exit-Codes, UTF-8-Log | ✓ SATISFIED | Tests und Spot-Checks |
| REQ-IBKR-62 | 02-02 | Timeout auf jedem Aufruf, benannter Zustand | ✓ SATISFIED | `wait_for` überall; Tests für hängende Probe, Request und Connect |
| REQ-IBKR-67 | 02-02 | Codes vor der Nutzung real gemessen | ? NEEDS HUMAN (teilweise) | Gemessen: 321, 2104/2158/2107, kein 326 bei 20001. Nicht gemessen: 1100/1101/1102/1300/2110 (Grundlage von CR-01) und 326 → TimeoutError (aus dem Quelltext abgeleitet). Human item 3 |

### Gefundene Anti-Patterns

| Datei | Zeile | Muster | Schwere | Wirkung |
|---|---|---|---|---|
| alle Phasen-Dateien | – | `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` | – | keine Treffer |
| `scripts/ibkr_broker.py` | 507 | `float(cash.value)` ohne `isfinite` (IN-02) | ℹ️ Info | NaN-Cash würde als `cash=null` mit Exit 0 enden; nicht umgesetzt |
| `scripts/ibkr_executor.py` | 150-170 | `IBKR_HOST` nicht auf Loopback beschränkt (IN-07) | ⚠️ Warning | zusammen mit `:::7497` relevant; human item 4 |
| `scripts/ibkr_executor.py` | 321-327 | gesunder Health-Probe wird nicht geloggt (Beobachtung 3) | ℹ️ Info | Nachweis im Log nur indirekt |
| `scripts/ibkr_broker.py` | 71-94 | 2107 fehlt in `STATE_BY_CODE` (IN-04) | ℹ️ Info | erscheint als `UNKNOWN`/WARNING |
| `scripts/ibkr_executor.py` | 227-251 | doppelte Ticker möglich (IN-03) | ℹ️ Info | bis Phase 3 |

### Einordnung der offenen Beobachtungen aus 02-05

| # | Beobachtung | Einordnung |
|---|---|---|
| 1 | Kein 321 beim Connect trotz Read-Only an | **Keine Lücke im Phasenziel.** „Ohne Schreibrecht“ trägt in Phase 2 die Client-Sperre (jetzt auch auf Drahtebene) zusammen mit `readonly=True`. Ob der Gateway-Schalter wirkt, gehört zu REQ-IBKR-10 (Phase 4 K2, Phase 6 K1: „gesperrter Zustand vorher über 321 belegt“). |
| 2 | Gateway lauscht auf `:::7497` | **Warnung, keine Ziellücke.** Betriebssicherheit; human item 4. Kein späteres Roadmap-Kriterium deckt es ausdrücklich ab. |
| 3 | HEALTHY und Scharfschalten der Sperre nicht geloggt | Info, Folgeplan. Beim Re-Run von K1 ist der Probe weiterhin nur indirekt belegt. |
| 4 | 2107 → `UNKNOWN` | Info (IN-04). |
| 5 | `TotalCashValue` ≠ `NetLiquidation` um 428.88 EUR | Info; betrifft die Mengenrechnung ab Phase 4, nicht das Kontolesen. |
| 6 | Reale Negativ-Gegenprobe K3 fehlt | **Geschlossen durch diese Verifikation:** mit dem echten `ib_async` gegen einen Port ohne Listener Exit 3 mit benannter Zeile, ohne Traceback (gegen kein Gateway, ohne Seiteneffekt). |

### Menschliche Verifikation erforderlich

#### 1. K1 neu am echten Gateway (Code-Stand nach den Fixes)

**Test:** `python scripts/ibkr_executor.py account --out "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json"`
**Erwartet:** Exit 0. JSON mit `as_of`, `load_portfolio()` ok. Im Log kein `WRITE_REFUSED`, `UNEXPECTED` oder Traceback, kein Link-Code im Snapshot-Fenster.
**Warum menschlich:** Braucht das Gateway. Der Verbindungsweg wurde nach dem einzigen echten Lauf an vier Stellen geändert (Drahtsperre, Cache-Leeren, Settle-Fenster, Loop-Handling).

#### 2. K7 neu als verkettete Kette

**Test:** die `&&`-Zeile aus `scripts/IBKR_EXECUTION.md:251`, mit Anthropic-Konfiguration
**Erwartet:** beide Exit 0, Block „Portfolio at the analysis date:“ mit EUR-Cash im `complete_report.md`
**Warum menschlich:** Kostet LLM und braucht das Gateway. Das damalige JSON wird heute zu Recht abgelehnt (Exit 1 im Preflight).

#### 3. REQ-IBKR-67: Link-Codes messen oder Override

**Test:** Messung von 1100/1101/1102 (und wenn möglich 2110/1300) am Gateway, mit Datum, oder bewusste Annahme per Override
**Erwartet:** datierter Befund oder Override-Eintrag
**Warum menschlich:** Dafür muss der Operator die Verbindung des Gateways absichtlich stören.

Override-Vorschlag, falls akzeptiert:

```yaml
overrides:
  - must_have: "REQ-IBKR-67 Fehlercodes gemessen, nicht angenommen (Link-Codes 1100/1101/1102/1300/2110)"
    reason: "Offiziell dokumentierte IBKR-Codes, von ib_async selbst behandelt; Messung erfordert absichtliche Störung und folgt mit Phase 8 K6 (1100-Fehlerbild)"
    accepted_by: "<name>"
    accepted_at: "<ISO timestamp>"
```

#### 4. Gateway „Allow connections from localhost only“

**Test:** Einstellung in der Gateway-GUI prüfen und im Handbuch notieren
**Erwartet:** gesetzt, mit Datum
**Warum menschlich:** GUI-Einstellung, aus dem Repo nicht lesbar.

### Zusammenfassung der Lücken

Es gibt keine blockierende Lücke im Code. Alle Bausteine des Phasenziels sind vorhanden, substanziell und verdrahtet: Verbindung mit `readonly=True` und clientId 20001, eine Schreibsperre auf Methoden- und Drahtebene vor dem ersten Byte, der exakte Paper-Guard mit Trennung und Exit 8, Liveness über eine echte Probe-Antwort, ein frischer Snapshot mit Verwerfung bei Link-Ereignissen, atomares JSON mit `as_of`, das `load_portfolio()` liest, sowie die Weitergabe bis in den Report. Testsuite und Lint sind grün, bis auf den bekannten Windows-Fehlschlag. Die Kriterien 2 bis 6 und 8 sind automatisch belegt, K6 sogar heute neu gemessen.

Offen ist allein der Nachweis am echten System für den **finalen** Code. Die beiden echten Läufe (K1, K7) liefen vor den Review-Fixes. Nach den Fixes lehnt der Paper-Run das damals erzeugte JSON ab, und der geänderte Verbindungsweg hat das Gateway noch nie gesehen. Daher `human_needed`: ein erneuter verketteter Lauf (Items 1 und 2) schließt beides zugleich. Dazu kommen zwei Operator-Entscheidungen: Link-Code-Messung für REQ-IBKR-67 und die Localhost-Einstellung des Gateways.

---

_Verifiziert: 2026-10-12T13:55:00Z_
_Verifier: Claude (gsd-verifier)_

## Nachtrag 2026-10-12: menschliche Prüfpunkte erledigt → `passed`

| Punkt | Ergebnis |
|---|---|
| 1. K1 erneut | **bestanden.** 16:34:17 lokal, Exit 0, HEAD `0178678`. `portfolio.json` mit `as_of` 2026-10-12T14:34:17.921620+00:00, 1005459.44 EUR, 0 Positionen; vorher „previous portfolio removed“. Log: `CONNECTED account=DUQ634065 clientId=20001 readonly=True`, 0 Treffer für WRITE_REFUSED/UNEXPECTED/Traceback/placeOrder/ReadOnlyViolation. |
| 2. K7 erneut | **bestanden.** `&&`-Kette direkt im Anschluss, Provider `anthropic` aus `.env`, Exit 0, AAPL Hold, 0,13 $; `complete_report.md` Z. 10–12 zeigen den Portfolio-Block mit „Cash available: 1,005,459.44 EUR“. |
| 3. REQ-IBKR-67 Link-Codes | **Override** durch den Operator (siehe Frontmatter `overrides`), Messung folgt mit Phase 8 K6. |
| 4. Localhost-only | **bestätigt.** Der Operator hat am 2026-10-12 nachgesehen: „Allow connections from localhost only“ war im Gateway bereits gesetzt. Dass `netstat` `:::7497` zeigt, widerspricht dem nicht, weil das Gateway entfernte Verbindungen beim Annehmen abweist und nicht schon beim Binden. |
