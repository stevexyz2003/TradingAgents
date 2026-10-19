# Phase 7: Rückkanal und Soll-Ist-Zusammenführung - Research

**Researched:** 2026-10-19
**Domain:** Git-basierter Veröffentlichungskanal (Windows, Subprozess-`git`), fail-open CI-Eingang, Lese-Join Soll/Ist aus Ledger + Decision-Log, Backup-Allow-Liste
**Confidence:** HIGH (Code, Tests und Git-Verhalten am Repo und am echten `fork`-Remote geprüft); MEDIUM bei Kursquelle (yfinance, nicht im Test erreichbar)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Veröffentlichungsbranch (REQ-52, SC1)**
- **D-01:** Der Branch heißt **`ibkr-log`**. Der Ausführer ist sein einziger Schreiber; die Invariante „ein Schreiber pro Branch“ steht im Handbuch (`scripts/IBKR_EXECUTION.md`) ausdrücklich als Invariante, nicht als Gewohnheit, zusammen mit `paper-log` (Schreiber: CI) als Gegenstück.
- **D-02:** Inhalt: **`ledger.jsonl` als vollständige Kopie** (der Live-Ledger, nicht `ledger-dryrun.jsonl`), **`portfolio.json`** (der frische Stand aus dem Lauf, Form wie `portfolio_json()` in `scripts/ibkr_executor.py` mit `as_of`) und die **Contract-Datei** (`contracts.json`). Keine abgeleitete Zweitdarstellung: der Bericht joint gegen den echten Ledger.
- **D-03:** Gepusht wird über einen **eigenen Befehl `ibkr_executor.py publish`**, getrennt vom Orderlauf. Ein Git- oder Netzfehler kann `execute` nie beeinflussen, und die Exit-Codes von `execute` bleiben unverändert. Phase 8 hängt `publish` an den Zeitplan.
- **D-04:** Der Git-Arbeitsbaum ist ein **eigener Klon nur dieses Branches im State-Ordner** (`%LOCALAPPDATA%\TradingEngineX\ibkr\...`), nie ein Worktree des Entwicklungs-Repos und nie im Code-Checkout. Gepusht wird ausschließlich auf den Remote `fork` (stevexyz2003/TradingAgents), nie auf `origin`.

**Portfolio-Rückkanal (SC6)**
- **D-05:** Nur der **CI-Lauf** (`.github/workflows/daily-paper-run.yml`) liest `portfolio.json` von `ibkr-log`, rein lesend, und übergibt es an die Analyse. Lokale Läufe behalten das heutige `--portfolio` mit 60 Minuten Höchstalter (`DEFAULT_PORTFOLIO_MAX_AGE`) unverändert.
- **D-06:** Gültigkeit in CI: ein Stand ist gültig, wenn sein `as_of` **nach dem Schluss der vorletzten regulären Sitzung** liegt (also aus dem letzten Handelstag stammt). Keine feste Stundenzahl; Wochenenden und Feiertage ergeben sich aus dem Börsenkalender.
- **D-07:** **Fail-open mit Vermerk** in jedem Fehlerfall: Datei oder Branch fehlt, Stand veraltet, JSON kaputt, `as_of` fehlt oder liegt in der Zukunft → der Lauf läuft exakt wie heute ohne Portfolio, und `summary.json` vermerkt den Grund (additives Feld). Der Pfad über `ibkr-log` darf keinen neuen Fehler in den Produktivpfad bringen; das heutige fail-closed von `load_fresh_portfolio` für lokales `--portfolio` bleibt unberührt.

**Berichtsform (REQ-49, SC2, SC5)**
- **D-08:** Ausgabe als **Markdown auf stdout**, mit `--out <datei>` zusätzlich als Datei. Kein CSV, kein HTML.
- **D-09:** Standard-Zeitraum ist **alles**, filterbar mit `--since`/`--until` (trade_date, inklusiv).
- **D-10:** Die Ausführungstabelle hat **eine Zeile pro Entscheidung** `(trade_date, ticker)` aus `decision-log.md`, auch Hold und Tage ohne Order; der Zustand aus dem Ledger steht in einer eigenen Spalte (z. B. `skipped-hold`, `filled`, `fill-timeout`, `place-rejected`, „kein Lauf“). Spalten laut SC2: Rating, Zielposition, Ist-Position, Ordermenge, Fill-Menge, Durchschnittspreis, Abweichung Ziel↔Ist, `weekend_gap`.
- **D-11:** Der Bericht läuft **nur lokal**. Er liest `fork/paper-log` und `fork/ibkr-log` per `git fetch` + `git show` (ohne Checkout, ohne Schreibzugriff); kein neuer CI-Job.
- **D-12:** Duplikate werden beim Lesen dedupliziert: eine Zeile pro `decision_key = "<trade_date>|<ticker>"`, **erste Fassung gewinnt** (REQ-39/-40, wie `log.py:47-55`). Der Fall `2026-10-09 | AAPL` (dreifach in `index.md`) muss eine Zeile ergeben.

**Metriken und Slippage (REQ-50, SC3)**
- **D-13:** Zwei **getrennte Tabellen**: Ausführung (Slippage, Fill-Quote, Abweichung Ziel↔Ist) und Entscheidung (realisierter Return, Alpha aus `settlement.py`). Nie in dieselbe Spalte. Der Bericht trägt den Hinweis, dass Paper-Fills aus Top-of-Book-Simulation stammen und systematisch nach oben verzerrt sind (Test der Mechanik, keine Messung der Ausführungsqualität).
- **D-14:** Slippage-Referenz ist der **Schlusskurs am `trade_date`**, geholt beim Lesen aus derselben Kursquelle wie `tradingagents/memory/settlement.py` (`get_closes`). Beschriftet als „Entscheidungskurs → Fill“, ausdrücklich inklusive Übernacht-Gap. Vorzeichen so, dass „schlechter als Referenz“ für BUY und SELL gleich gerichtet ist.
- **D-15:** Fill-Quote = **`filled_quantity / intent.quantity` je Order**, im Kopf als Summe über den Zeitraum. Fill-Timeout ohne Fill und bestätigte Ablehnung zählen als 0.
- **D-16:** Fehlende Kursinformation: **Zelle leer, Fußnote mit Grund**. Der Bericht scheitert nie an der Kursquelle, und es wird nichts geschätzt (S-08 / REQ-IBKR-68).

### Claude's Discretion
- Backup (REQ-51, SC4): wie `state_maintenance.py backup` Ledger (`ledger.jsonl`, auch `ledger-dryrun.jsonl`?) und `contracts.json`/`contracts-history.jsonl` aufnimmt — vermutlich eine eigene Option bzw. ein Default auf den IBKR-State-Ordner, da diese Dateien nicht unter `--state-dir` liegen. `--dry-run` muss sie listen.
- Verhalten von `publish` bei Push-Fehlern, leerem Diff (kein Commit) und fehlendem Remote-Branch (Erstanlage); Commit-Message-Format; Lock gegen parallelen `execute`.
- Wie CI `ibkr-log` liest (z. B. `git fetch --depth=1 origin ibkr-log` + `git show`), solange es rein lesend bleibt und den `paper-log`-Schritt nicht berührt.
- Name und Ort des Berichtsskripts (z. B. `scripts/ibkr_report.py`), Spaltenformat, Rundung.
- Wie Ist-Position und Zielposition je Zeile aus Ledger/Portfolio rekonstruiert werden.

### Deferred Ideas (OUT OF SCOPE)
- Eröffnungskurs als zweite Referenz (Gap und Ausführung getrennt) — erst sinnvoll mit Live-Fills.
- CSV-/HTML-Ausgabe und ein CI-Job für den Bericht.
- Laufprotokoll je Lauf auf `ibkr-log` → Heartbeat in Phase 8 (REQ-53).
- `publish` automatisch nach `execute` → Zeitplan in Phase 8.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-IBKR-49 | Soll-Ist-Bericht entsteht beim Lesen, Join über `(trade_date, ticker)` aus `paper-log:decision-log.md` und Fill-Ledger | Abschnitt „Bericht“: zwei `GitPaperLog`-Leser, `Ledger.open` auf Blob-Kopie, Zeilenrekonstruktion aus Intent (Ziel/Ist exakt ableitbar), Zustandsspalte aus Ledger-Events |
| REQ-IBKR-50 | Ausführungs- und Entscheidungsmetriken getrennt, Hinweis zu Paper-Fills | Zwei Tabellen; Entscheidungsmetriken stehen schon im Settled-Tag des Logs (kein Netz nötig); Slippage nur mit `settlement.get_closes`, fail-soft |
| REQ-IBKR-51 | `state_maintenance.py backup` nimmt Ledger und Contract-Cache auf | Abschnitt „Backup“: `--ibkr-dir` + `--dry-run` (existiert heute NICHT), Allow-Liste inkl. `contracts-history.jsonl`, Test-Isolation gegen echten `%LOCALAPPDATA%` |
| REQ-IBKR-52 | Ausführer veröffentlicht auf eigenem Branch, ein Schreiber pro Branch | Abschnitt „Publish“: `ibkr_executor.py publish`, eigener Ein-Branch-Klon, Push nur `fork`, ohne `--force`, Lock, Erstanlage per `git init -b` |
</phase_requirements>

## Summary

Die Phase besteht aus vier unabhängigen Bausteinen: (1) `publish` (Git-Schreibweg, nur Ausführer), (2) ein fail-open Lesepfad in `daily_paper_run.py` für CI, (3) ein lokales Berichtsskript, (4) die Backup-Allow-Liste. Alle vier lassen sich ohne Gateway-Verbindung und ohne neue Fremdpakete bauen; die Git- und Ledger-Bausteine existieren bereits (`GitPaperLog`, `Ledger.open`, `effective_executions`, `XnysSessions`, `locked`). Neu ist vor allem Klebecode plus Tests.

Fünf Befunde ändern den Plan gegenüber dem, was CONTEXT.md annimmt, und müssen in Pläne bzw. Rückfragen einfließen:
(a) **`portfolio.json` entsteht heute nur durch den manuellen `account`-Befehl** (`ibkr_executor.py:507-548`), nicht durch `execute`; `publish` darf nach D-03 kein Gateway brauchen, kann den Stand also nur kopieren, nicht frisch erzeugen. „Der frische Stand aus dem Lauf“ (D-02) setzt voraus, dass `account` vor `publish` läuft.
(b) **`state_maintenance.py backup` hat kein `--dry-run`** (`state_maintenance.py:437-442`); SC4 verlangt es, also muss es neu hinzukommen, nicht nur die Allow-Liste.
(c) **`tests/test_ibkr_isolation.py:82-88` lässt „IBKR“ in keinem Workflow-File zu (case-insensitiv)**: weder `ibkr-log` noch `scripts/ibkr_*.py` dürfen in `daily-paper-run.yml` stehen. Branch-Name und Logik gehören in Python, der Workflow bekommt nur ein neutrales Flag.
(d) **`exchange_calendars` ist nur im Extra `ibkr`** (`pyproject.toml:53`), die CI macht `pip install .` ohne Extra (`daily-paper-run.yml:122`). Für D-06 braucht die CI einen zusätzlichen Pip-Schritt; ohne ihn greift fail-open („calendar-unavailable“) und das Portfolio kommt nie an.
(e) **Das Repo `stevexyz2003/TradingAgents` ist öffentlich** (`gh repo view`: PUBLIC). `ledger.jsonl` (Konto-ID `DUQ634065` in `run_start.release_account`, `orderRef`, permId, Preise), `portfolio.json` (Cash, Positionen, Einstandspreise) und `contracts.json` werden damit öffentlich. Das ist durch D-02 festgelegt; es ist ein bewusst zu bestätigender Punkt (Open Question 1), keine Abweichung.

**Primary recommendation:** Neues reines Modul `scripts/ibkr_publish.py` (Git über injizierbaren Runner, Ein-Branch-Klon unter `ibkr\publish\`, `git init -b ibkr-log` + `fetch fork`, Commit nur bei Diff, Push `HEAD:refs/heads/ibkr-log` ohne Force), im Executor als Unterbefehl `publish` mit neuem `EXIT_PUBLISH = 11` und Lock-Nutzung wie `execute`; neues `scripts/ibkr_report.py` (nur lesend); in `daily_paper_run.py` ein Flag `--portfolio-from-published`, das intern alles fängt und `summary["portfolio_feed"]` additiv schreibt; in `state_maintenance.py` `--ibkr-dir` und `--dry-run`.

## Project Constraints (from CLAUDE.md)

- Code, Kommentare, Commits englisch; `.planning/` deutsch (Memory: Antworten auf Deutsch).
- Graphify und Serena sind reine Navigationswerkzeuge, kein Build-/Merge-Gate.
- Auf dieser Maschine kein `uv run`: Tests mit `.venv/Scripts/python.exe -m pytest`, Lint mit `.venv/Scripts/python.exe -m ruff` (Memory `env_uv_ssl_workaround`).
- AVG-TLS-Interception betrifft Python/npm/uv; `git` nutzt `http.sslbackend=schannel` (Windows-Zertifikatsspeicher) und erreichte `fork` ohne Zusatzkonfiguration [VERIFIED: `git ls-remote fork`, `git push --dry-run fork` gelaufen].
- Nie ein echtes Gateway kontaktieren; Tests nur gegen Fakes; `tests/conftest.py:60-71` sperrt Sockets in jedem Test (Git-Subprozesse gegen lokale Pfade bleiben möglich).
- Keine Commits durch den Forscher; nur diese Datei wurde geschrieben.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ledger/Portfolio/Contracts nach `ibkr-log` veröffentlichen | Lokaler Operator-Prozess (`ibkr_executor.py publish`) | Git-Remote `fork` | Einziger Schreiber (D-01); Quelle der Wahrheit liegt im State-Ordner |
| Portfolio in die CI-Analyse einspeisen | CI-Prozess (`daily_paper_run.py`) | Git-Remote (nur Lesen) | Fail-open, additiv; berührt `paper-log`-Schritt nicht |
| Gültigkeit „nach vorletzter Sitzung“ | Börsenkalender (`ibkr_decision.SessionCalendar`) | — | Wochenende/Feiertag aus Kalender, keine Stundenzahl (D-06) |
| Soll-Ist-Join und Metriken | Lokales Berichtsskript (Lesezeit) | Kursquelle (yfinance, fail-soft) | Join nur beim Lesen (REQ-49); kein Schreiben in fremde Branches |
| Backup von Ledger und Contract-Cache | `state_maintenance.py` (lokal) | — | Dateien liegen außerhalb `--state-dir` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `git` (CLI via `subprocess`) | 2.56.0.windows.1 [VERIFIED: `git --version`] | Klon, Commit, Push, Fetch, `cat-file` | Bereits Muster in `ibkr_paperlog.py` (injizierbarer `run`) |
| Python stdlib (`subprocess`, `json`, `tempfile`, `os.replace`) | 3.12/3.13 | Kopieren, Atomizität | Keine neue Abhängigkeit |
| `exchange_calendars` | 4.13.2 lokal, Pin `>=4.13,<5` [VERIFIED: `pyproject.toml:53`, `.venv` Import] | Vorletzte Sitzung in CI | Schon von `XnysSessions` genutzt (`ibkr_decision.py:469-531`) |
| `tradingagents.dataflows.files.locked` | repo-intern | Lock `ledger.jsonl.lock` | Gleicher Lock wie `execute` (`ibkr_executor.py:1669, 1920`) |
| `tradingagents.memory.settlement.get_closes` (Yahoo) | repo-intern, yfinance 1.7.0 | Schlusskurs am `trade_date` | Vorgabe D-14; Patch-Muster `monkeypatch.setattr(settlement, "get_closes", ...)` (`tests/test_graph_end_to_end.py:317`) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tradingagents.memory.log.TradingMemoryLog` | repo-intern | `load_entries()` auf Kopie von `decision-log.md` | Bericht und (unverändert) Executor (`ibkr_executor.py:2521`) |
| `scripts/ibkr_ledger.py` (`Ledger.open`, `effective_executions`) | repo-intern | Ledger lesen/validieren, Fills korrektur-bewusst | Bericht und `publish`-Validierung |
| `tests/calendar_stub.py::WeekdayCalendar` | repo-intern | Kalender ohne `exchange_calendars` | Tests der Cutoff-Funktion |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `git init -b ibkr-log` + `fetch` | `git clone --single-branch --branch ibkr-log` | Scheitert bei der Erstanlage (Branch fehlt auf `fork`, [VERIFIED: `ls-remote --exit-code` Exit 2]); `init`+`fetch` deckt beide Fälle mit einem Pfad ab |
| Eigene Kalenderlogik | `XnysSessions` | Duplikat; Feiertage/Halbtage bereits abgedeckt |
| Workflow-Shell-Schritt für Fetch | Fetch in Python | Shell-Schritt würde „ibkr-log“ in die YAML tragen und `test_ci_workflows_reference_no_ibkr_secret` brechen |

**Installation:** keine neuen Pakete im Repo. CI: ein zusätzlicher Schritt `pip install "exchange_calendars>=4.13,<5"` (gleiche Spanne wie `pyproject.toml:53`).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| exchange_calendars | PyPI | etablierte Bibliothek, bereits in `pyproject.toml` (Extra `ibkr`) und lokal installiert (4.13.2) | n/a (nicht neu eingeführt) | github.com/gerrymanoim/exchange_calendars | nicht gelaufen (kein neues Paket) | Approved: bestehende, gepinnte Abhängigkeit; die CI übernimmt dieselbe Spanne |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
Diese Phase führt **kein** neues externes Paket ein; slopcheck war daher nicht nötig. Der CI-Pip-Schritt wiederholt nur den vorhandenen Pin.

## Architecture Patterns

### System Architecture Diagram

```
 LOKAL (Operator, Windows)                                   GITHUB (fork, öffentlich)            CI (Linux, 06:30 UTC)
 ──────────────────────────                                  ─────────────────────────           ─────────────────────
 account --out portfolio.json  (Gateway, manuell/Phase 8)
 execute --live  ── schreibt ledger.jsonl (+ .lock) ──┐
                                                       │  [Lock wait=False; Exit 7 wenn execute läuft]
 publish ──► Snapshot lesen (ledger/portfolio/contracts, Bytes)
        ──► Ledger.open(Snapshot) validieren (sonst Exit 6)
        ──► ibkr\publish\ (Ein-Branch-Klon)
              git ls-remote --exit-code fork ibkr-log ──rc 2──► Erstanlage (orphan, kein reset)
              git fetch fork ibkr-log ; reset --hard FETCH_HEAD
              Dateien binär überschreiben, git add, Diff leer? ──► "nothing to publish", Exit 0
              git commit ; git push fork HEAD:refs/heads/ibkr-log (kein --force)
                                                        └────────────► fork/ibkr-log ◄── (einziger Schreiber)
                                                                          ▲   ▲
 ibkr_report.py (lesend)                                                  │   │ git fetch + cat-file (kein Checkout)
   fork/paper-log ──► decision-log.md ─┐                                  │   │
   fork/ibkr-log  ──► ledger.jsonl ────┼─► Join je decision_key ─► Markdown (stdout / --out)
                        portfolio.json ┘   (erste Fassung gewinnt)
   settlement.get_closes (Netz, fail-soft) ──► Slippage-Spalte                      │
                                                                                    │
 daily_paper_run.py --portfolio-from-published (nur Schritt "Run the analysis") ◄───┘ fetch + cat-file portfolio.json
   Fehlerfall jeder Art ──► portfolio=None (wie heute) + summary["portfolio_feed"]={status:"skipped", reason}
   Erfolg ──► load_published_portfolio(as_of > Schluss der vorletzten Sitzung) ──► graph.propagate(..., portfolio=p)
 CI-Commit-Schritt auf paper-log: UNVERÄNDERT (fetch --depth=1 → reset --hard → push)
```

### Recommended Project Structure
```
scripts/
├── ibkr_executor.py        # + Unterbefehl `publish`, default_publish_dir(), load_publish_module(), EXIT_PUBLISH=11
├── ibkr_publish.py         # NEU, rein: Snapshot -> Klon -> Commit -> Push (Git-Runner injizierbar)
├── ibkr_report.py          # NEU, nur lesend: Join, Tabellen, Markdown
├── ibkr_decision.py        # + pure Funktion second_last_close_utc(now_utc, calendar)
├── daily_paper_run.py      # + --portfolio-from-published, load_published_portfolio(), summary["portfolio_feed"]
├── state_maintenance.py    # + --ibkr-dir, --dry-run, IBKR-Allow-Liste
└── IBKR_EXECUTION.md       # + Invariante "ein Schreiber pro Branch", publish, Report, Backup
tests/
├── test_ibkr_publish.py    # NEU
├── test_ibkr_report.py     # NEU
├── test_daily_paper_run.py # + Feed-Tests
├── test_state_maintenance.py # + IBKR-Backup-Tests, autouse-Isolation
└── test_ibkr_isolation.py  # Exit-Tabelle 12 -> 13, Modul-Reinheit, Workflow-Pins
```

### Pattern 1: `publish` (D-01..D-04)

**Wo er hängt:** Neuer Unterparser in `build_parser()` (`ibkr_executor.py:771-829`); `main()` meldet bei fehlendem Befehl die Liste „account, resolve, preview, execute“ (`:886`), die um `publish` zu ergänzen ist (Test `test_ibkr_executor` prüft ggf. den Text). Kein `--env-file`: `read_settings` verlangt `IBKR_HOST/PORT/ACCOUNT_ID` (`:113, :322-338`), die `publish` nicht braucht und nie lesen soll. Remote `fork` und Branch `ibkr-log` sind **Konstanten**, kein Env-Override (D-04: „nie `origin`“); `validate_ref_name` (`ibkr_paperlog.py:42-51`) trotzdem anwenden.

**Pfade:** Klon unter `_ibkr_base()/"publish"` (`:263-268`). Nicht `paper-log` nennen: `ibkr\paper-log\decision-log.md` ist die Verify-Kopie (`default_paper_log_copy`, `:296-298`), kein Git-Baum. `ensure_outside_git(state_dir)` (`ibkr_ledger.py:718-730`, genutzt `:1653`) prüft nur `state_dir` und dessen Eltern auf `.git`; ein Klon als **Unterordner** stört das nicht. Auf den Klon selbst darf es nicht angewandt werden.

**Ablauf (alle Git-Aufrufe mit `-c core.autocrlf=false`, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, Timeout):**
1. Lock: `locked(default_ledger_file(), wait=False)` wie `run_resolve_entry` (`:1667-1685`). Gehalten → `EXIT_LOCKED` (7, „clean exit“), nichts kopiert. Das Lock nur für das Snapshot-Lesen halten, **vor** dem Netz freigeben (ein hängender Push darf `execute` nie blockieren; D-03).
2. Snapshot: Bytes von `ledger.jsonl`, `portfolio.json` (optional), `contracts.json` (optional, `contracts-history.jsonl` nicht, D-02) in den Speicher lesen. Ledger-Bytes mit `Ledger.open(<Temp-Kopie>, mode="live", ...)` validieren; `LedgerError` → Exit 6, nichts veröffentlicht (der Klon behält den letzten guten Stand). Ein Torn-Tail ist erlaubt (`ibkr_ledger.py:335-343`).
3. Klon bereitstellen: fehlt `.git`: `git init -q -b ibkr-log <dir>`; `git remote add fork <url>` bzw. `set-url`. URL kommt aus dem Entwicklungs-Repo: `git -C REPO_ROOT remote get-url fork` (`REPO_ROOT` `ibkr_executor.py:130`). Verweigern, wenn `fork`-URL == `origin`-URL oder `fork` fehlt (Exit 1). Lokal setzen: `core.autocrlf=false`, `remote.fork.fetch=+refs/heads/ibkr-log:refs/remotes/fork/ibkr-log` und `--no-tags` (ein-Branch-Klon).
4. Remote-Zustand: `git ls-remote --exit-code --heads fork ibkr-log`. Exit 0 → `git fetch --no-tags fork +refs/heads/ibkr-log:refs/remotes/fork/ibkr-log`, dann `git reset -q --hard refs/remotes/fork/ibkr-log` (der Klon ist wegwerfbar; Quelle der Wahrheit ist der State-Ordner). Exit 2 → Erstanlage: nichts holen, der erste Commit wird Root-Commit des neuen Branches (unverwandte Historie, gewollt) [VERIFIED: Exit 2 bei fehlendem Branch, am echten `fork`]. Exit 128/Timeout → `EXIT_PUBLISH`.
5. Dateien **binär** schreiben (`write_bytes` über Temp+`os.replace`), nie `write_text` (CRLF). Beim ersten Commit zusätzlich `.gitattributes` mit `* -text`, damit Windows-`core.autocrlf=true` (System-Config, [VERIFIED: `git config --show-origin`]) keine Bytes verändert.
6. `git add -A`; leerer Diff (`git diff --cached --quiet` rc 0) → „publish: nothing to publish“, Exit 0, kein Commit, kein Push (Muster wie CI-Schritt `daily-paper-run.yml:211-215`).
7. Commit mit **fester Identität** über `-c user.name=... -c user.email=...` (z. B. `TradingEngineX publish` / `noreply`), damit weder die globale Firmen-E-Mail (`admin@scharfegmbh.de`) noch ein fehlender `user.*` ins öffentliche Log gelangt. Nachrichtenformat: `ibkr-publish: <UTC-Zeitstempel> (<n> ledger line(s))` mit Hinweis auf letzte `seq`.
8. `git push fork HEAD:refs/heads/ibkr-log` — **ohne `--force`**. Abgelehnt (Non-Fast-Forward) = die Invariante ist verletzt: Exit `EXIT_PUBLISH`, Klartext „ibkr-log moved; one writer per branch“, nichts erzwingen. Der nächste Lauf holt neu und setzt hart zurück, ein verpasster Stand heilt sich selbst.
9. Fremd-Commit-Erkennung (Entwickler pusht versehentlich): Vor dem Überschreiben die Autor-E-Mail der Remote-Spitze mit der festen Identität vergleichen; Abweichung wird im Log als `ibkr-state=PUBLISH_FOREIGN_COMMIT` vermerkt und im Bericht als Fußnote gezeigt, der Lauf geht weiter (Empfehlung; kein Sperren, weil `ibkr-log` keinen zweiten Leser mit Konfliktfolge hat wie `paper-log`).

**Portfolio-Frische (Befund a):** `account` löscht beim Start die alte `--out`-Datei (`_discard_previous`, `:946-956`) und schreibt nur bei Exit 0. `publish` kopiert, was im State-Ordner liegt. Fehlt die Datei, wird `portfolio.json` auf dem Branch **nicht** gelöscht; die CI beurteilt über `as_of` (D-06), nicht über Anwesenheit. Der Operator-/Phase-8-Ablauf muss `account` zwischen `execute` und `publish` legen; das gehört ins Handbuch (Open Question 2 für eine Alternative).

**Exit-Code:** Neuer `EXIT_PUBLISH = 11` (frei: belegt sind 0-10 und 20, `ibkr_executor.py:98-109`). `test_handbook_exit_table_matches_executor` erzwingt `len(codes) == 12` und eine Handbuchzeile je Code (`tests/test_ibkr_isolation.py:183-193`): Test auf 13 anheben und die Handbuchzeile `| 11 | \`EXIT_PUBLISH\` |` ergänzen. Wiederverwendet werden 0, 1 (Konfig), 6 (Ledger kaputt), 7 (Lock). `execute` bleibt unverändert (D-03).

**Reinheit:** `ibkr_publish.py` ohne `ib_async`, ohne `tradingagents`-Import auf Modulebene, ohne `datetime.now` (Uhr als Parameter, Muster `test_decision_modules_are_library_free`, `test_decision_module_takes_the_clock_as_a_parameter`, `:524-546`). Das Lock gehört in den Executor-Wrapper, das Modul bekommt Bytes. Lazy-Loader `load_publish_module()` nach dem Muster `_load_script_module` (`:223-260`). Die Modul-Liste in den Reinheitstests um `ibkr_publish.py` und `ibkr_report.py` erweitern. Vorsicht: `test_no_hard_coded_trading_times_in_execution_code` (`:267-281`) verbietet in `scripts/ibkr_*.py` die Literale `13:30`, `14:30`, `09:30`, `16:00` (auch in Docstrings/Beispielzeitstempeln).

### Pattern 2: CI-Portfolio fail-open (D-05..D-07)

**Heute:** `daily_paper_run.py` lädt `--portfolio` mit `load_fresh_portfolio` (fail-closed, `:137-176`), Konstanten `PORTFOLIO_AS_OF_KEY` (`:50`), `DEFAULT_PORTFOLIO_MAX_AGE` (`:53`), `PORTFOLIO_CLOCK_SKEW` 5 min (`:55`); `run_ticker` reicht `portfolio` nur bei Vorhandensein an `propagate` weiter (`:365-368`); `main` lädt es vor dem Preflight (`:453-460`). Die CI übergibt nie `--portfolio` (`daily-paper-run.yml:176-181`).

**Empfohlen:**
- Neues Flag `--portfolio-from-published` (store_true, schließt sich mit `--portfolio` aus: argparse-Gruppe oder `ConfigError`). Konstanten `PUBLISHED_STATE_REMOTE = "origin"`, `PUBLISHED_STATE_BRANCH = "ibkr-log"` in Python (nicht im Workflow, Befund c). Das Flag wird **nur im Schritt „Run the analysis“** (`daily-paper-run.yml:171-184`) ergänzt, nicht im Preflight-Schritt; `--preflight` ignoriert es (kein Netz im Preflight).
- Neue Funktion `load_published_portfolio(repo, now, calendar_loader=..., reader=...) -> (PortfolioContext | None, dict)`; **fängt `Exception` komplett** (D-07) und liefert `(None, {"status":"skipped","reason":...})`. Gründe als feste Kennungen: `branch-unavailable` (Fetch scheitert; fehlender Branch und Netzfehler sind hier nicht unterscheidbar, der Roh-Fehlertext kommt gekürzt in `detail`), `file-missing`, `invalid-json`, `invalid-schema`, `as-of-missing`, `as-of-invalid`, `as-of-in-future` (> 5 min, `PORTFOLIO_CLOCK_SKEW`), `stale`, `calendar-unavailable` (ImportError/`CalendarRangeError`/weniger als zwei Sitzungen). Erfolg: `{"status":"used","as_of":...,"cutoff":...,"sha":...,"positions":n}` (keine Beträge ins Summary, es landet öffentlich auf `paper-log`).
- Lesen über die vorhandene `GitPaperLog(repo, "origin", "ibkr-log")` (`ibkr_paperlog.py:80-171`, `fetch()` holt in eine eigene Ref und löscht sie, `read("portfolio.json")` per `cat-file`): rein lesend gegenüber dem Remote, ändert nur lokalen Ref-Namensraum `refs/tengx/...` im Workspace-Checkout, **nicht** das `STATE_DIR`-Repo des `paper-log`-Schritts (`daily-paper-run.yml:105-169`). Das Modul wird per `importlib` aus dem Dateipfad geladen (Tests laden `daily_paper_run` per `spec_from_file_location`, `tests/test_daily_paper_run.py:27-28`; ein Top-Level-`import ibkr_paperlog` wäre dort nicht auflösbar). `GitPaperLog.fetch` kennt kein `--depth`; ein optionaler Parameter `depth` (additiv) hält den Abruf klein.
- Cutoff: neue reine Funktion `second_last_close_utc(now_utc, calendar)` in `ibkr_decision.py`, nur über das `SessionCalendar`-Protokoll (`:454-466`): lokales Datum via `_calendar_today` (`:534-537`), `sessions_between(today-14d, today)` rückwärts, Sitzungen mit `session_close_utc(d) <= now_utc` sammeln, die zweite ist der Cutoff. Fenster 14 Tage deckt jede Feiertagskette. Gültig, wenn `as_of > cutoff` (und nicht in der Zukunft). Beispiel Di 06:30 UTC: letzte geschlossene Sitzung Mo, vorletzte Fr → ein Stand von Mo-Nachmittag oder Fr-Abend ist gültig, einer von Do nicht. Testbar mit `tests/calendar_stub.py::WeekdayCalendar`.
- CI-Workflow: ein Schritt vor „Run the analysis“: `pip install "exchange_calendars>=4.13,<5"` (Befund d). Der Schritt trägt kein „ibkr“-Wort. Schritte `:152-169` und `:202-219` bleiben byteweise unverändert; ein Test pinnt das (Text des Commit-Schritts enthält weiter `git push -q origin "HEAD:$STATE_BRANCH"`, und `test_ci_workflows_reference_no_ibkr_secret` bleibt grün).
- `summary.json`: additives Top-Level-Feld `portfolio_feed` im Summary-Dict (`daily_paper_run.py:511-525`). `SUMMARY_SCHEMA_VERSION` bleibt 1, weil der Konsument nur `schema_version, trade_date, status, runs` liest (`ibkr_decision.py:130-136, 190-227`) und kein Test die Top-Level-Schlüssel exakt pinnt [VERIFIED: Grep in `test_daily_paper_run.py`, `test_paper_summary_contract.py`, `test_ibkr_decision.py`]. Feld nur schreiben, wenn das Flag gesetzt war, sonst bleibt das Summary byte-gleich wie heute. `test_without_portfolio_propagate_gets_no_portfolio_kwarg` (`tests/test_daily_paper_run.py:460-463`) ist die Vorlage für den Fail-open-Beleg: `graph.portfolios == ["<absent>"]`.

**Wirkung auf den Produktivpfad (nicht in CONTEXT, planungsrelevant):** Mit Portfolio-Kontext **überspringt die Jev-Prüfung** (`tradingagents/jev/hooks.py:112-113`); in CI (Jev standardmäßig an) entfallen dann der REVIEW-Fallback und die Shadow-Checks an Tagen mit gültigem Portfolio. Außerdem fließt `portfolio.render()` (Cash, Positionen, Einstandspreise) in den Prompt, und die archivierten Berichte `runs/<date>/<ticker>.md` (`_archive`, `:387-395`) gehen auf den öffentlichen `paper-log` (Warnung bereits in `IBKR_EXECUTION.md:890-898` für lokale Läufe). Das ist die in SC6 benannte „einzige Berührung des Produktivpfads“; die Planung muss es als bewusste Folge dokumentieren (Handbuch, `PAPER_RUN.md`).

### Pattern 3: Bericht `scripts/ibkr_report.py` (D-08..D-16)

**Quellen lesen:** zwei `GitPaperLog`-Instanzen auf `REPO_ROOT` mit Remote `fork` und Branches `paper-log` bzw. `ibkr-log` (Optionen `--paper-log-branch`, damit auch der Pipeline-Test-Branch `paper-log-pipeline-test` lesbar ist: die erste Live-Order entstand dort). Pfade `decision-log.md`, `ledger.jsonl`, `portfolio.json` bestehen `validate_blob_path`. `decode_utf8` für Text, Ledger-Bytes unverändert.

**Decision-Log parsen:** `TradingMemoryLog.load_entries()` liest nur aus einer Datei (`tradingagents/memory/log.py:89-100`): Blob in ein Temp-Verzeichnis schreiben und `TradingMemoryLog({"memory_log_path": tmp}).load_entries()` (Muster `ibkr_executor.py:2491-2521` ohne `verify`). Felder je Eintrag: `date, ticker, rating, pending, raw, alpha, holding, resolved` (`log.py:339-348`). Nicht parsbare Blöcke fallen still weg (`_parse_entry` gibt `None`): in der Fußnote zählen (Block-Anzahl gegen Entry-Anzahl).

**Dedup (D-12), Befund zur Quelle:** Die Zeile `2026-10-09 | AAPL` steht dreifach (plus zwei `failed`-Zeilen) in **`index.md`** (`fork/paper-log:index.md` Zeilen 41-47), aber **genau einmal** in `decision-log.md` [VERIFIED: `git show fork/paper-log:decision-log.md`, Zählung 1]; denn `store_decision` verweigert Doppel schon beim Schreiben (`log.py:60-68`). `log.py:47-55` aus CONTEXT zeigt auf eine ältere Fassung; im aktuellen Stand steht der Guard bei `:60-68`, und `load_entries` dedupliziert **nicht**. Die Berichtszeile je `decision_key` entsteht aus `decision-log.md`; `index.md` wird nicht gelesen (nicht nötig). Beim Lesen trotzdem defensiv „erste Fassung gewinnt“ in Dateireihenfolge. Der Test muss ein Decision-Log mit Doppel **roh** schreiben (der Produzent `store_decision` lässt kein Doppel zu) und zusätzlich die echten Bytes des Fixtures `tests/fixtures/paper_log_71df89d` als Gegenprobe verwenden. Mehrfach-Läufe im Ledger zum selben Key sind kein Doppel der Zeile.

**Ledger lesen:** Blob in Temp-Datei, `Ledger.open(path, mode="live", clock=..., run_id="report")` (`ibkr_ledger.py:308-350`) liefert validierte `records`, toleriert Torn-Tail, wirft `LedgerError` bei kaputter Mitte → Bericht bricht mit klarer Meldung ab (der Ledger ist Wahrheitsquelle; nur die Kursquelle ist fail-soft, D-16). `ledger.jsonl` und `ledger-dryrun.jsonl` haben verschiedene `mode`; nur `live` wird veröffentlicht.

**Je `decision_key` aus den Ledger-Events ableiten:**

| Feld | Herleitung | Beleg |
|------|-----------|-------|
| Zustand (Spalte) | Hat der Key einen `intent`: letztes Lifecycle-Event (`LIFECYCLE_EVENTS`, `ibkr_ledger.py:80`): `filled`/`partial` → so; `rejected` → dessen `state` (z. B. `place-rejected`); `resolved` → `outcome`; `placed` mit `alarm` `state=fill-timeout` → `fill-timeout`; `dry_complete` darf im Live-Ledger nicht vorkommen. Ohne `intent`: `state` des **letzten** `skipped`/`rejected` (z. B. `skipped-hold`, `within-tolerance`, `outside-session`); ohne jede Zeile: „kein Lauf“ | Felder `state`, `detail`, `trade_date`, `weekend_gap` stehen auf `skipped`/`rejected` (`ibkr_executor.py:1830-1864`) |
| Zielposition | `BLOCKS[rating] * block_qty` (`ibkr_decision.py:323`, `block_qty` aus `CONTRACT_TABLE[ticker]`, `ibkr_contracts.py:80-100`); Hold hat kein Ziel (`—`). **Rating aus dem Intent**, wenn vorhanden (sonst Log-Rating) | `plan_order` `ibkr_decision.py:336-372` |
| Ist-Position (vorher) | Nur mit Intent exakt: `plan_order` setzt `quantity = |target - held|`, Seite nach Vorzeichen, also `held_vorher = target - (±intent.quantity)`. Ohne Intent steht `held` nur im Freitext `detail` (z. B. „target 1 held 0 block 1“) und im Ledger **nicht** strukturiert: Zelle leer + Fußnote, kein Parsen von Freitext | `_execute_ticker` `:2994-3006`; Ledger kennt kein `held`/`target` |
| Ist-Position (nachher) | `held_vorher + Σ signierte effektive Fills` | `Ledger.filled_quantity` `:481-510` als Vorlage |
| Ordermenge | `intent.quantity` (+ `side`) | `intent_record` `:513-540` |
| Fill-Menge, Ø-Preis | Effektive Executions je `exec_id`-Familie (höchste Korrektur gewinnt) über `effective_executions` (`:575-587`, Objekte mit `.exec_id/.shares`: Records in `SimpleNamespace` wickeln), Ø = Σ(qty·price)/Σqty. Zeilen ohne `exec_id` (nur Aggregat) zählen wie in `filled_quantity` einmalig | `fill_records` `:590-625` |
| `weekend_gap` | `intent.weekend_gap`, sonst `skipped.weekend_gap` | Handbuch `:738-740` |
| Abweichung Ziel↔Ist | Ziel − Ist(nachher), nur wo beide bekannt | SC2 |

Das Fixture dafür liefert `ibkr-konto-befund.md:704-712` (reale Form der ersten Live-Order: `intent → placed → filled → alarm(post-order-mismatch, fills_booked) → run_end`).

**Entdeckte Randfälle für den Bericht:**
- Die erste Live-Order (Key `2026-10-16|AAPL`, Rating **Overweight** im Intent) stammt vom Branch `paper-log-pipeline-test`; der echte `paper-log` führt dort **Hold** (`fork/paper-log` `[2026-10-16 | AAPL | Hold | pending]`). Ein Bericht gegen `paper-log` zeigt Log-Rating ≠ Ledger-Rating. Soll sichtbar werden: Markierung „Ledger-Rating ≠ Log-Rating“ plus `paper_log_sha` des Intents als Fußnote. Das ist ein echter Testfall.
- `block_qty` ist heute im Code (`CONTRACT_TABLE`) und „changing it is a commit“ (`ibkr_contracts.py:89-90`). Historische Zeilen werden mit dem **heutigen** Blockwert berechnet. Plausibilitätsprüfung: `held_vorher` muss ganzzahlig und ≥ 0 sein, sonst Fußnote „Blockgröße geändert?“.
- Der Ledger hat nach dem Fehlalarm (`post-order-mismatch`, `fills_booked: true`) letztes Lifecycle-Event `filled`; die Zeile soll den `alarm` zusätzlich als Vermerk zeigen (Spalte „Hinweis“).
- Fill-Quote (D-15): Nenner nur Keys mit `intent`; Keys ohne Order zählen nicht ins Verhältnis.

**Metriken getrennt (D-13):**
- *Ausführung:* Slippage je Order, Fill-Quote, Abweichung. Slippage = `side_sign · (Ø_Fill − Close(trade_date)) / Close · 1e4` in Basispunkten, `side_sign` = +1 BUY, −1 SELL, damit „schlechter als Referenz“ immer positiv ist. Spaltenname z. B. „Entscheidungskurs → Fill (inkl. Gap), bp“. Währungen müssen gleich sein (USD-Aktie, Fill in USD); sonst Zelle leer + Fußnote.
- *Entscheidung:* **kein Netz nötig.** Der Tag eines abgerechneten Eintrags trägt Raw und Alpha schon (`[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]`, `log.py:271-284, 339-348`); `pending` bleibt „offen“. `settlement.fetch_returns` (`settlement.py:68-125`) liefert für offene Einträge ohnehin `None`, bis das Haltefenster gehandelt ist; ein Nachrechnen im Bericht würde die Pipeline duplizieren und von ihr abweichen können. Empfehlung: Entscheidungsmetriken aus dem Log-Tag lesen, `settlement` nur für den Kurs.
- *Kurs:* `settlement.get_closes(ticker, trade_date, trade_date+1 Tag)` (Enddatum exklusiv, `tradingagents/dataflows/vendors/yahoo/market.py:268-272`), **über das Modulattribut** `settlement.get_closes` aufrufen, damit die vorhandene Patch-Technik (`monkeypatch.setattr(settlement, "get_closes", ...)`) greift. Jede Ausnahme, leere Serie oder Kurs ≤ 0 → Zelle leer, Fußnote mit Grund (D-16); nichts schätzen. Ein Schalter `--no-prices` überspringt den Abruf (reproduzierbar offline). Kursabruf je `(ticker, trade_date)` einmalig cachen.
- Pflichttext: Hinweis zu Top-of-Book-Simulation (REQ-50) im Kopf des Berichts; auch Tests prüfen ihn.

**Rundung/Format:** Mengen mit `:g`, Preise 2 Nachkommastellen, bp 1 Nachkommastelle, Prozent wie im Log (String übernehmen).

### Pattern 4: Backup (REQ-51, SC4)

**Befund:** `backup` kennt heute nur `--out`, `--state-dir`, `--memory-log` (`state_maintenance.py:437-442`), packt immer ein Archiv (`:399-405`) und hat **kein `--dry-run`**. SC4 setzt eines voraus („`backup --dry-run` listet Ledger und Contract-Cache“).

**Empfehlung:**
- Neue Option `--dry-run` (listet Mitglieder im selben Format wie heute, schreibt kein Archiv, legt `--out` nicht an). `--out` bleibt für den echten Lauf Pflicht; im Dry-Run optional, sonst widerspricht die Pflichtprüfung (`:366-368`) dem Zweck.
- Neue Option `--ibkr-dir` (Default: `%LOCALAPPDATA%\TradingEngineX\ibkr`, sonst `~/.tradingenginex/ibkr`, gleiche Regel wie `_ibkr_base`, `ibkr_executor.py:263-268`). Die Regel in `state_maintenance.py` **duplizieren** (der Executor lädt dieses Modul per `load_state_maintenance_module`, `:248-250`; ein Rückimport wäre zirkulär) und per Test gleichsetzen (`default_ledger_file().parent == tool.default_ibkr_dir()`).
- Allow-Liste unter dem Archivpfad `ibkr/`: `ledger.jsonl`, `ledger-dryrun.jsonl`, `contracts.json`, `contracts-history.jsonl`. `contracts-history.jsonl` gehört dazu: fehlt `contracts.json` bei vorhandener Historie, verweigert `resolve --init` (`ibkr_executor.py:604-611`), die Historie ist also Teil des Zustands. **Nicht** aufnehmen: `RELEASE` (ein Restore darf die Freigabe nie still wieder scharf schalten), `KILL`, `portfolio.json`/`preview.json`/`resolve.json` (abgeleitet, kurzlebig), `logs/`, `*.lock` (schon über `BACKUP_EXCLUDED_SUFFIXES`, `:68`), den Klon `publish/`.
- Fehlt der IBKR-Ordner oder eine Datei, ist das kein Fehler (Hinweiszeile); `if not members` (`:395-397`) bleibt für den Gesamtfall.
- Kein Lock beim Backup: `tar.add` liest einen gerade angehängten Ledger höchstens mit Torn-Tail, den `Ledger.open` toleriert; im Handbuch erwähnen.
- **Testfalle:** `test_backup_packs_the_allow_list_and_nothing_else` (`tests/test_state_maintenance.py:543-588`) ruft `backup` ohne IBKR-Argument; mit Default-on würde es den **echten** `%LOCALAPPDATA%` des Entwicklers packen. Darum autouse-Fixture, die `LOCALAPPDATA` (und `HOME`/`USERPROFILE`) auf `tmp_path` setzt.

### Anti-Patterns to Avoid
- **`git push --force` oder `--force-with-lease` in `publish`:** versteckt eine Verletzung der Ein-Schreiber-Invariante statt sie laut zu machen.
- **Worktree des Entwicklungs-Repos oder Klon im Code-Checkout (D-04):** `git add -A` würde Code mitnehmen; State muss außerhalb jedes Code-Baums bleiben.
- **`write_text` auf Windows für die Kopien:** CRLF. Immer Bytes.
- **Fetch/Branch-Name im Workflow-YAML:** bricht den Secret-Guard und trägt Logik in den Produktivpfad.
- **Entscheidungsmetriken im Bericht neu rechnen:** dupliziert die Pipeline.
- **Freitext `detail` parsen, um Ist-Positionen zu holen:** fragil; lieber leer lassen (D-16-Geist) oder Ledger additiv erweitern (Open Question 3).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Branch ohne Checkout lesen | eigene `git show`-Wrapper | `GitPaperLog` (`ibkr_paperlog.py`) | Whitelist für Ref/Pfad, private Fetch-Ref gegen `FETCH_HEAD`-Rennen, `BlobMissing` vs. `PaperLogUnavailable` |
| Ledger parsen/validieren | eigener JSONL-Reader | `Ledger.open` | Torn-Tail-Siegel, Schema, Modus-Prüfung |
| Fill-Korrekturen (`.01` → `.02`) | eigene Deduplizierung | `effective_executions` | Höchste Korrektur gewinnt, REQ-47 |
| Schreiber-Sperre | eigener Lockfile | `locked(ledger_path, wait=False)` | Windows `msvcrt`/POSIX `flock`, gleiche Sperre wie `execute` |
| Börsenkalender | Wochentag-Logik | `XnysSessions` / `SessionCalendar` | Feiertage, Halbtage |
| Decision-Log parsen | Regex auf `decision-log.md` | `TradingMemoryLog.load_entries` | Trennzeichen `ENTRY_END`, Settlement-Zeile |
| Atomares Schreiben | `open(...,"w")` auf Zielpfad | Temp + `os.replace` (Muster `write_portfolio_atomic`, `:483-504`) | Kein halber Stand sichtbar |
| Ziel/Ist-Leiter | eigene Tabelle | `BLOCKS` + `CONTRACT_TABLE[...].block_qty` | Eine Quelle der Wahrheit |

**Key insight:** Alles Heikle (Git-Whitelisting, Ledger-Korrektheit, Kalender, Lock) ist schon gelöst; die Phase soll es wiederverwenden und nur Klebecode und Tests ergänzen.

## Common Pitfalls

### Pitfall 1: „IBKR“ im Workflow bricht den Secret-Guard
**What goes wrong:** `tests/test_ibkr_isolation.py:82-88` prüft `"IBKR" in text.upper()` über alle `.github/workflows/*.yml`; `ibkr-log`, `scripts/ibkr_*.py` oder `IBKR_` lösen den Fehler aus.
**How to avoid:** Branch-Konstante und Fetch in `daily_paper_run.py`; Workflow nur `--portfolio-from-published`. Alternative (Planerentscheidung): Guard auf `secrets.IBKR`/`IBKR_(HOST|PORT|ACCOUNT)` verengen — ändert aber ein Sicherheitsnetz.
**Warning signs:** roter Isolationstest direkt nach der YAML-Änderung.

### Pitfall 2: `portfolio.json` auf dem Branch ist älter als der Lauf
**What goes wrong:** `execute` schreibt kein Portfolio; `publish` kopiert nur. Ohne vorheriges `account` trägt der Branch den Stand eines früheren Tags; die CI weist ihn per D-06 korrekt zurück, die Soll-Ist-Wirkung (SC6) bleibt dann still aus.
**How to avoid:** Handbuch-Reihenfolge `execute` → `account` → `publish`; `publish` loggt `as_of` und warnt, wenn `as_of` älter als der letzte Ledger-`ts` ist.

### Pitfall 3: Fehlende Credentials / interaktiver Prompt
**What goes wrong:** Nicht-interaktiver Push hängt am Git Credential Manager.
**How to avoid:** `GIT_TERMINAL_PROMPT=0` (steht in `GitPaperLog._git`, `ibkr_paperlog.py:99-106`) **und** `GCM_INTERACTIVE=never` (`never`/`false`/`0` zulässig) [CITED: github.com/git-ecosystem/git-credential-manager docs/environment.md]; Timeout pro Git-Aufruf. Auf dieser Maschine funktioniert Push-Auth ohne Eingabe [VERIFIED: `git push --dry-run fork HEAD:refs/heads/<neu>` meldete `[new branch]`, `credential.helper=manager`].

### Pitfall 4: CRLF durch `core.autocrlf=true`
**What goes wrong:** System-Config setzt `core.autocrlf=true` [VERIFIED]; Text-Schreiben oder Autocrlf kann Zeilenenden verändern, `Ledger.open` und Diffs werden unruhig.
**How to avoid:** Bytes schreiben, `-c core.autocrlf=false`, `.gitattributes` `* -text` im ersten Commit; Test: gelesenes Blob == Quellbytes, kein `\r\n` hineinkopiert (Vorbild `test_real_git_fetch_without_checkout`, `tests/test_ibkr_paperlog.py:186-211`).

### Pitfall 5: Teilgeschriebene Kopie / Torn-Tail
**What goes wrong:** `execute` hängt gerade an; Kopie schneidet die letzte Zeile ab.
**How to avoid:** Lock (Wait=False) um das Snapshot-Lesen; trotzdem `Ledger.open` auf dem Snapshot. Der Ledger-Append ist ein einzelner Write + fsync (`ibkr_ledger.py:394-403`), ein Torn-Tail bleibt tolerierbar.

### Pitfall 6: Kein neuer Branch bei der Erstanlage
**What goes wrong:** `git fetch fork ibkr-log` schlägt beim ersten Mal mit „couldn't find remote ref“ fehl und wird mit einem Netzfehler verwechselt.
**How to avoid:** Vorab `git ls-remote --exit-code --heads fork ibkr-log`; Exit 2 = Erstanlage (aktuell der Fall: Branch existiert nicht [VERIFIED]), Exit 128 = Fehler.

### Pitfall 7: `exchange_calendars` fehlt in CI
**What goes wrong:** `pip install .` ohne Extra → `ImportError` → fail-open `calendar-unavailable`, Portfolio kommt nie an, nur ein Summary-Vermerk verrät es.
**How to avoid:** Pip-Schritt in der YAML; Test, der den Pip-Pin gegen `pyproject.toml:53` vergleicht; Betriebsprüfung: erste CI-Läufe zeigen `portfolio_feed.status == "used"`.

### Pitfall 8: Jev entfällt, öffentliche Berichte tragen Cash
**What goes wrong:** Mit gültigem Portfolio wird die Jev-Prüfung übersprungen (`hooks.py:112-113`) und der Report enthält Cash/Positionen auf dem öffentlichen `paper-log`.
**How to avoid:** Als bewusste Folge dokumentieren, in Verifikation prüfen; Planerfrage 4.

### Pitfall 9: Kursquelle: bereinigte Schlusskurse
**What goes wrong:** `get_closes` ruft `yf.Ticker(...).history(start, end)` mit Defaults (`market.py:271`); yfinance bereinigt standardmäßig um Dividenden/Splits (Default `auto_adjust=True`) [ASSUMED], sodass alte Schlusskurse leicht vom damaligen Rohkurs abweichen. Für frische Trades vernachlässigbar, für ältere Zeilen eine Fußnote wert („bereinigter Schlusskurs der Quelle“).
**How to avoid:** Fußnote; Referenz nie als Fehler werten.

### Pitfall 10: Versehentlicher Push eines Entwicklers auf `ibkr-log`
**What goes wrong:** Verletzt die Invariante; ein späterer `publish` überschreibt die Dateien ohne Meldung.
**How to avoid:** Fremd-Autor-Erkennung (Pattern 1, Schritt 9), Handbuch als **Invariante** mit Gegenstück `paper-log` (Schreiber CI) und Hinweis, dass GitHub-Branchschutz diese Regel zusätzlich erzwingen kann (nicht geprüft, LOW).

## Code Examples

### Erstanlage vs. Fortschreibung (Skizze, Git über Runner)
```python
# Source: eigene Skizze; Git-Verhalten am echten fork geprüft (ls-remote Exit 2 = Branch fehlt)
def sync_clone(git, branch="ibkr-log", remote="fork"):
    probe = git(["ls-remote", "--exit-code", "--heads", remote, branch])
    if probe.returncode == 0:
        git(["fetch", "--no-tags", "--quiet", remote,
             f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"], check=True)
        git(["reset", "-q", "--hard", f"refs/remotes/{remote}/{branch}"], check=True)
        return "existing"
    if probe.returncode == 2:
        return "first-publish"  # initialer Commit wird Root-Commit
    raise PublishError(f"ls-remote failed: {probe.stderr!r}")
```

### Cutoff „Schluss der vorletzten Sitzung“
```python
# Source: eigene Skizze über das SessionCalendar-Protokoll (scripts/ibkr_decision.py:454-466)
def second_last_close_utc(now_utc, calendar, window_days=14):
    today = _calendar_today(now_utc, calendar)
    days = calendar.sessions_between(today - timedelta(days=window_days), today)
    closed = [d for d in reversed(days) if calendar.session_close_utc(d) <= now_utc]
    if len(closed) < 2:
        raise CalendarRangeError("fewer than two closed sessions in the window")
    return calendar.session_close_utc(closed[1])
```

### Fail-open Schale
```python
def load_published_portfolio(repo, now, *, reader, calendar_loader):
    try:
        ...  # fetch, read, parse, cutoff, as_of check
    except Exception as exc:  # D-07: no new failure in the production path
        return None, {"status": "skipped", "reason": _reason_of(exc)}
```

### Slippage-Vorzeichen
```python
sign = 1 if side == "BUY" else -1
slippage_bp = sign * (avg_fill - close) / close * 1e4  # > 0: worse than the reference
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Alle Prozesse schreiben in `paper-log` | Je Branch genau ein Schreiber (`paper-log`: CI, `ibkr-log`: Ausführer) | REQ-52, Phase 7 | Kein Non-Fast-Forward-Verlust eines Entscheidungstags |
| Lokales `--portfolio` mit 60-min-Frische | Zusätzlich CI-Pfad nach Sitzungsschluss, fail-open | Phase 7 | Analyse sieht echte Position, ohne Produktivrisiko |

**Deprecated/outdated:** der Verweis `log.py:47-55` in CONTEXT/REQ (Guard steht heute bei `:60-68`).

## Runtime State Inventory

Phase ist keine Rename-Phase; **ausgelassen**. Relevanter neuer Laufzeitzustand: Klon `%LOCALAPPDATA%\TradingEngineX\ibkr\publish\` (wegwerfbar, Quelle der Wahrheit bleibt der State-Ordner); Remote-Branch `ibkr-log` (existiert noch nicht, [VERIFIED: `ls-remote`]).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | yfinance-`history` bereinigt standardmäßig Schlusskurse (`auto_adjust=True`) | Pitfall 9 | Slippage-Referenz leicht anders; nur Fußnote nötig |
| A2 | Operator-/Phase-8-Ablauf legt `account` zwischen `execute` und `publish` | Pattern 1 | Branch-Portfolio meist zu alt, CI lehnt per D-06 ab (fail-open, kein Schaden, aber SC6 ohne Wirkung) |
| A3 | 14-Tage-Fenster reicht für zwei geschlossene Sitzungen (längste Feiertagskette) | Pattern 2 | Selten `calendar-unavailable`, fail-open |
| A4 | Fremd-Commit nur warnen, nicht blockieren, ist richtig | Pattern 1 Schritt 9 | Strenger (Exit) wäre Alternative; Benutzerentscheidung |
| A5 | GitHub-Branchschutz könnte die Schreiber-Invariante zusätzlich erzwingen | Pitfall 10 | Nicht geprüft; nur Hinweis |

## Open Questions

1. **Öffentliche Sichtbarkeit von Ledger/Portfolio (Entscheidung des Operators bestätigen)**
   - Known: Fork ist PUBLIC; `ledger.jsonl` enthält `release_account: DUQ634065`, Preise, permIds; `portfolio.json` Cash (~1.005.000 EUR Paper) und Positionen.
   - Unclear: Ob die Kontonummer/Positionen eines Paper-Kontos öffentlich sein dürfen.
   - Recommendation: D-02 gilt (Papierkonto); vor der ersten Veröffentlichung kurze Bestätigung des Operators einholen und im Handbuch als Hinweis führen. Kein Code-Umbau nötig; Alternative wäre ein privates Repo (außerhalb der Phase).
2. **Soll `publish` das Portfolio selbst frisch holen (Gateway) oder weiter nur kopieren?**
   - Known: D-03 verlangt, dass ein Git-/Netzfehler `execute` nie beeinflusst; „publish braucht kein Gateway“ (Auftrag).
   - Recommendation: Nur kopieren; `account` bleibt eigener Schritt, Phase 8 legt die Reihenfolge fest.
3. **Ledger additiv um `held`/`target` auf `skipped` erweitern?**
   - Known: Ist-Position ist ohne Intent nicht strukturiert im Ledger (nur Freitext `detail`).
   - Recommendation: Phase 7 liest rein ableitend (Intent-Zeilen exakt, sonst leer + Fußnote); eine additive Erweiterung von `_ledger_row_finished` (`ibkr_executor.py:1830-1864`) wäre Phase-6-Code und gehört nicht hierher, kann aber später die Lücken schließen. Planer bestätigt.
4. **Jev-Entfall und Cash im öffentlichen Report akzeptiert?** (Pitfall 8) — Folge von SC6, bitte im Handbuch festhalten.
5. **`EXIT_PUBLISH = 11` oder Wiederverwendung von 3/5?** Empfehlung 11 (eigener Fehlerraum, Tabelle und Test mitziehen).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| git | publish, Bericht, CI-Lesepfad | ✓ | 2.56.0.windows.1 | — |
| Remote `fork` erreichbar (Fetch/Push-Auth ohne Prompt) | publish, Bericht | ✓ | `credential.helper=manager`, `schannel` | `GCM_INTERACTIVE=never` verhindert Hänger |
| `exchange_calendars` lokal | Cutoff-Tests (echter Kalender), Executor | ✓ | 4.13.2 | `tests/calendar_stub.py::WeekdayCalendar` |
| `exchange_calendars` in CI | D-06 | ✗ (kein Extra bei `pip install .`) | — | Pip-Schritt; sonst fail-open |
| yfinance / Netz für Kurse | Slippage | ✓ lokal, in Tests gesperrt | 1.7.0 | `--no-prices`, Fußnote (D-16) |
| `.venv/Scripts/python.exe` | Tests/Lint | ✓ | — | `uv run` geht auf dieser Maschine nicht |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** `exchange_calendars` in CI (Pip-Schritt).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (Markers `unit`, `integration`, `smoke`; `-m "not integration"` Default, `--strict-markers`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`:75-85`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest tests/test_ibkr_publish.py tests/test_ibkr_report.py tests/test_state_maintenance.py tests/test_daily_paper_run.py tests/test_ibkr_isolation.py -x -q` |
| Full suite command | `.venv/Scripts/python.exe -m pytest -q` (bekannte, phasenfremde Windows-Fehler: `test_yfinance_keeps_its_cache_out_of_the_users_home`, `test_chatgpt_auth` ×2, `test_cli_commands` ×1, `test_cli_updates` ×2, siehe STATE.md) |

Fakes/Muster: `tests/ibkr_fakes.py` (Gateway-Fakes, hier **nicht** nötig: kein Gateway), `tests/paper_log_fixture.py` (`FixturePaperLog`, `write_paper_log`), `tests/calendar_stub.py`, Real-Git gegen lokales Verzeichnis als „Remote“ (`tests/test_ibkr_paperlog.py:186-211`), autouse `_no_network` (`tests/conftest.py:60-71`), Patch von `settlement.get_closes`.

### Phase Requirements → Test Map
| Req/SC | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC1/REQ-52 | `publish` pusht nur `ibkr-log` auf `fork`; `paper-log` bleibt unverändert; Erstanlage; leerer Diff = kein Commit; Non-FF = Exit 11 ohne Force; Lock gehalten = Exit 7; kaputter Ledger = Exit 6 | integration-light (echtes `git` gegen lokale Bare-Repos als `fork`) + unit (Runner-Fake) | `pytest tests/test_ibkr_publish.py -x` | ❌ Wave 0 |
| SC1 | Kein Push-Argument enthält `origin` oder `paper-log`; Handbuch nennt Invariante „ein Schreiber pro Branch“ | unit (Runner-Aufzeichnung, Text-Guard) | `pytest tests/test_ibkr_publish.py tests/test_ibkr_isolation.py -k "writer or publish"` | ❌ Wave 0 |
| SC1 | Bytes-Treue: Blob == Quelle, kein `\r\n` | integration-light | `pytest tests/test_ibkr_publish.py -k bytes` | ❌ Wave 0 |
| SC2/REQ-49 | Join über `(trade_date, ticker)`: Spalten Rating, Ziel, Ist, Ordermenge, Fill, Ø-Preis, Abweichung, `weekend_gap`; Zustand `skipped-hold`/`filled`/`fill-timeout`/`place-rejected`/„kein Lauf“ | unit (Ledger-Zeilen in Form des Befundes `ibkr-konto-befund.md:704-712`) | `pytest tests/test_ibkr_report.py -k join` | ❌ Wave 0 |
| SC2 | Bericht liest zwei Branches per `fetch`+`cat-file`, keine Checkout-Dateien, `fork/paper-log` unverändert | integration-light | `pytest tests/test_ibkr_report.py -k real_git` | ❌ Wave 0 |
| SC3/REQ-50 | Zwei getrennte Tabellen; Hinweistext Top-of-Book; Slippage-Vorzeichen BUY/SELL gleich gerichtet; Fill-Quote Timeout/Reject = 0; Zelle leer + Fußnote bei Kursfehler (D-16) | unit (`settlement.get_closes` gepatcht) | `pytest tests/test_ibkr_report.py -k "metrics or slippage or footnote"` | ❌ Wave 0 |
| SC4/REQ-51 | `backup --dry-run` listet `ledger.jsonl`, `contracts.json`, `contracts-history.jsonl` (+ dryrun), kein Archiv; `RELEASE`/`KILL`/`.lock`/`logs` nicht enthalten; Standardpfad == Executor-Pfad | unit | `pytest tests/test_state_maintenance.py -k "ibkr or dry_run"` | ✅ Datei vorhanden, Tests ❌ |
| SC5/REQ-39/40 | `2026-10-09 | AAPL` mehrfach im Quelltext → eine Zeile, erste Fassung gewinnt; echte Bytes `tests/fixtures/paper_log_71df89d` als Gegenprobe | unit | `pytest tests/test_ibkr_report.py -k dedup` | ❌ Wave 0 |
| SC6 | Gültiger Stand (`as_of` nach vorletzter Sitzung) wird übergeben; jede Störung (Branch/Datei fehlt, JSON kaputt, `as_of` fehlt/alt/Zukunft, Kalender fehlt) → `propagate` ohne `portfolio`-Kwarg (`<absent>`) + `portfolio_feed.reason`; lokales `--portfolio` unverändert fail-closed | unit | `pytest tests/test_daily_paper_run.py -k "feed or published"` | ✅ Datei, Tests ❌ |
| SC6 | `second_last_close_utc` an Wochenende/Feiertag mit `WeekdayCalendar` | unit | `pytest tests/test_ibkr_decision.py -k second_last` | ✅ Datei, Tests ❌ |
| SC6 | Workflow: nur ein Flag in „Run the analysis“ + Pip-Schritt; `paper-log`-Schritte byte-unverändert; kein „IBKR“ im YAML | unit (Text-Pins) | `pytest tests/test_ibkr_isolation.py -k "workflow or ci"` | ✅ Datei, Pins ❌ |
| Querschnitt | `ib_async` nur im Adapter; neue Module rein (keine Lib, keine Uhr, keine Handelszeit-Literale); Exit-Tabelle 13 Zeilen inkl. 11 | unit | `pytest tests/test_ibkr_isolation.py -x` | ✅ anpassen |
| Querschnitt | `publish` braucht kein Gateway (Broker-Factory wird nie aufgerufen; `block_real_ib_connect`) | unit | `pytest tests/test_ibkr_publish.py -k no_gateway` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** der jeweils betroffene Testfile (`-x -q`), plus `ruff check` auf geänderte Dateien (`.venv/Scripts/python.exe -m ruff check <dateien>`).
- **Per wave merge:** Quick-Run oben komplett + `tests/test_ibkr_execute.py tests/test_ibkr_ledger.py` (Regression Ledger/Executor).
- **Phase gate:** volle Suite grün bis auf die dokumentierten phasenfremden Windows-Fehler; `UV_OFFLINE=1 make ci-local-lint` wird im Strang nicht genutzt, Lint über `.venv`-ruff.

### Wave 0 Gaps
- [ ] `tests/test_ibkr_publish.py` — SC1, Fixtures: Bare-Repo als `fork`, Runner-Recorder, Ledger-Zeilen
- [ ] `tests/test_ibkr_report.py` — SC2/3/5, Fixtures aus `ibkr-konto-befund.md:704-712` und `tests/fixtures/paper_log_71df89d`
- [ ] Autouse-Isolation `LOCALAPPDATA` in `tests/test_state_maintenance.py` (Pitfall: echter State-Ordner)
- [ ] `tests/test_ibkr_isolation.py`: Exit-Tabelle auf 13, neue Reinheits-/Workflow-Pins
- [ ] Framework-Install: keiner (pytest vorhanden)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein (Git-Credentials liegen im Credential Manager, nie im Code/Log) | `credential.helper=manager`; keine Tokens in URLs |
| V3 Session Management | nein | — |
| V4 Access Control | ja (Ein-Schreiber-Invariante, nie `origin`, nie `paper-log`) | Konstante Remote/Branch, `validate_ref_name`, Push-Refspec fest, Test auf Argumentliste |
| V5 Input Validation | ja (Pfade, Ref-Namen, JSON aus dem Branch) | `validate_blob_path`, `PortfolioContext.model_validate`, Fail-open-Schale, Größenlimit für den gelesenen Blob (Empfehlung) |
| V6 Cryptography | nein | TLS über Git/Schannel, nichts selbst gebaut |

### Known Threat Patterns for {Git-Publish + CI-Lesepfad}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Preisgabe von Konto-ID/Cash/Positionen auf öffentlichem Fork | Information Disclosure | Bewusste Entscheidung D-02 + Operator-Bestätigung (Open Question 1); nur Papierkonto; Handbuchhinweis; Fremdkonten nie |
| Manipulierter `portfolio.json` auf `ibkr-log` beeinflusst die CI-Analyse (Prompt-Inhalt) | Tampering | Strikte Schema-Validierung, `as_of`-Prüfung, Fail-open, Branch nur vom Ausführer beschrieben (Fremd-Commit-Erkennung); Ergebnis fließt in Prompt, nicht in Orders |
| Versehentlicher Push auf `origin`/`paper-log` | Tampering | Konstanten, `fork≠origin`-Prüfung, kein `--force`, Test auf Argumentliste |
| Prompt-/Terminal-Hänger durch Credential-Dialog | Denial of Service | `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, Timeouts |
| Öffentliche Commit-Identität verrät Firmen-E-Mail | Information Disclosure | Feste Commit-Identität per `-c` |
| Kaputter/hostiler Ledger-Blob im Bericht | Tampering | `Ledger.open` strikt, Abbruch statt Teilbericht |
| Zeitlich frisches, aber falsches Portfolio (Replay) | Spoofing | `as_of` nach vorletzter Sitzung, nicht in der Zukunft |

## Sources

### Primary (HIGH confidence)
- Repo-Code, Zeilenstände dieser Sitzung: `scripts/ibkr_executor.py` (Konstanten `:98-136`, `_ibkr_base` `:263-268`, `run_account` `:507-548`, Parser `:771-829`, `main` `:866-943`, Locks `:1667-1685`, `_ledger_row_finished` `:1830-1864`, `_read_log_entries` `:2491-2521`, `_execute_ticker` `:2840-3030`), `scripts/ibkr_ledger.py`, `scripts/ibkr_paperlog.py`, `scripts/ibkr_decision.py` (`:323-372, :454-617`), `scripts/ibkr_contracts.py` (`:71-100`), `scripts/daily_paper_run.py`, `scripts/state_maintenance.py`, `.github/workflows/daily-paper-run.yml`, `tradingagents/memory/log.py`, `tradingagents/memory/settlement.py`, `tradingagents/dataflows/vendors/yahoo/market.py:268-272`, `tradingagents/dataflows/files.py:37-87`, `tradingagents/jev/hooks.py:112-113`, `pyproject.toml`, `tests/test_ibkr_isolation.py`, `tests/conftest.py`
- `.planning/ibkr-konto-befund.md` §„Erste echte Order (Phase 6)“ (reale Ledger-/Historienform vom 2026-10-19)
- Live-Prüfungen: `git ls-remote --exit-code --heads fork ibkr-log` (Exit 2), `git push --dry-run fork HEAD:refs/heads/…` (Auth ohne Prompt), `git config --show-origin core.autocrlf` (true, System), `gh repo view` (PUBLIC), `git show fork/paper-log:decision-log.md` / `index.md`
- github.com/git-ecosystem/git-credential-manager `docs/environment.md` (`GCM_INTERACTIVE`)

### Secondary (MEDIUM confidence)
- Keine.

### Tertiary (LOW confidence)
- yfinance-`auto_adjust`-Default (A1), GitHub-Branchschutz als Zusatz (A5)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — alles bestehender Repo-Code, keine neuen Pakete
- Architecture: HIGH — Git-Verhalten am echten Remote geprüft; Entscheidungen aus CONTEXT eindeutig
- Pitfalls: HIGH für Test-/Workflow-/CRLF-/Lock-Fallen (am Code belegt); MEDIUM für Kursquelle

**Research date:** 2026-10-19
**Valid until:** 2026-11-18 (der Code ändert sich bis 06-10 noch im Ledger-Format: vor der Planung `ibkr_ledger.py`/`ibkr_executor.py` erneut abgleichen)
