---
phase: quick-261011-k4s
verified: 2026-10-11T14:25:00Z
status: human_needed
score: 10/10 must-haves verified (3 runtime confirmations outstanding, all Docker-bound)
overrides_applied: 0
re_verification: null
human_verification:
  - test: "`bash scripts/smoke/docker_smoke.sh`; echo rc=$? — zweimal hintereinander, danach `SMOKE_KEEP=1 bash scripts/smoke/docker_smoke.sh && bash scripts/smoke/docker_smoke.sh`"
    expected: "Beide Male rc=0 und die Zeile `SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)`; die Kette nach SMOKE_KEEP=1 ebenfalls grün"
    why_human: "Braucht einen laufenden Docker-Daemon; der Verifier darf/kann hier keine Container starten (Operator fährt den Lauf parallel). Struktur, Assertions und Stub-Verhalten sind statisch bzw. ohne Docker nachgewiesen (siehe Behavioral Spot-Checks)."
  - test: "Ersten CI-Lauf des Jobs `docker-smoke` auf `ubuntu-latest` beobachten (nächster Push/PR)"
    expected: "Job grün innerhalb der 10 Minuten; `//stub_llm.py` kommt dort unverändert an, Linux kollabiert den doppelten Slash"
    why_human: "Noch nie auf einem GitHub-Runner gelaufen — Runner-uid, Image-Pull und Build-Zeit sind lokal nicht beobachtbar. Im SUMMARY selbst als ungetestet benannt."
  - test: "Im gebauten Image prüfen: `docker run --rm --entrypoint sh tex-smoke:local -c 'command -v sqlite3 || echo none'`"
    expected: "`none` — das `sqlite3`-Binary fehlt im Image (Grundlage der „kein `.recover`\"-Begründung)"
    why_human: "Die Workstation-Hälfte der Behauptung ist verifiziert (kein `sqlite3` im PATH); die Image-Hälfte braucht Docker."
warnings:
  - id: W-1
    item: "Retention-Kapitel deckt nur 4 der 9 in „Where state lives\" gelisteten State-Orte ab"
    files:
      - "scripts/STATE_OPERATIONS.md:83-88 (Retention-Tabelle) gegen scripts/STATE_OPERATIONS.md:39-48 (Pfad-Tabelle)"
      - "scripts/state_maintenance.py:144,202 (nur <cache>/checkpoints), scripts/state_maintenance.py:226 (nur <results_dir>/reports)"
    detail: "Ohne Fristenangabe und ohne Prune-Abdeckung bleiben: per-Run-Reports `logs/<TICKER>/<date>/reports/*.md`, `message_tool.log`, `TradingAgentsStrategy_logs/full_states_log_<date>.json`, die Daten-Caches `~/.tradingagents/cache/` und `cli_prefs.json`. Die Operator-Entscheidung nannte nur drei Klassen (Log/Checkpoints/Reports), insofern kein Verstoß — aber die Retention-Tabelle sagt nicht, dass „Report directories 90 d\" ausschließlich den konsolidierten Baum `<results_dir>/reports/<T>_<stamp>/` meint und der per-Run-Baum nie beschnitten wird. Entscheidung des Operators nötig: Satz nachtragen oder bewusst so lassen."
---

# Quick Task 261011-k4s: P2 — Docker-/CLI-Smoke + State-Retention/Backup/Recovery — Verification Report

**Task-Ziel:** Die beiden letzten offenen P2-Punkte des Meilensteins schließen — (1) „Docker-/CLI-Smoke mit Stub-Providern läuft reproduzierbar", (2) „State-Retention/Backup/Recovery (Decision-Log, Checkpoints) dokumentiert", letzteres per Operator-Entscheidung als Runbook PLUS ausführbares Wartungswerkzeug mit Tests.
**Verifiziert:** 2026-10-11T14:25:00Z
**Status:** human_needed — keine Lücke gefunden; drei Bestätigungen brauchen Docker bzw. den Runner
**Re-Verification:** Nein — erste Verifikation (kein `*-VERIFICATION.md` vorhanden)

Methodik: zielrückwärts gegen den Code, nicht gegen das SUMMARY. Alles unten Behauptete wurde in dieser Sitzung selbst gemessen; wo das nicht möglich war (Docker), steht es als Human-Item und nicht als „verifiziert".

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | `bash scripts/smoke/docker_smoke.sh` → Exit 0, ohne API-Key, ohne Internet | ✓ VERIFIED (Code) / human-confirm (Laufzeit) | Skript existiert, 258 Zeilen, `bash -n` sauber. Kein Key gesetzt: `openai_compatible` ist `key_optional=True, require_base_url=True` (`tradingagents/llm_clients/openai_client.py:231-233`). Kein Internet: `docker network create --internal` (`docker_smoke.sh:95`). Entrypoint-/Pfad-Passung geprüft: `Dockerfile:28` `ENTRYPOINT ["tradingagents"]`, `Dockerfile:21-22` legt `/home/appuser/.tradingagents` an — genau der Pfad in `docker_smoke.sh:170`. Alle 8 verwendeten `TRADINGAGENTS_*`-Variablen existieren in `default_config.py:10-34`. Laufzeit → Human-Item 1 |
| 2 | Zweiter Lauf direkt danach grün, auch nach `SMOKE_KEEP=1` / Ctrl-C | ✓ VERIFIED (Code) / human-confirm (Laufzeit) | Pre-Flight-Teardown läuft vor allem anderen (`docker_smoke.sh:67-77`), Reihenfolge Container→Netz; `trap teardown INT TERM EXIT` erst danach registriert und nur wenn `SMOKE_KEEP` leer (`:81-85`), mit `${SMOKE_KEEP:-}` unter `set -u` sicher. Alle drei Containernamen in beiden Teardowns. Laufzeit → Human-Item 1 |
| 3 | Negativ-Kontrolle: eigener Container, Exit != 0 UND != 125 UND Verbindungsfehler-Marker | ✓ VERIFIED | Eigener Container `tex-smoke-neg` (`:223`), Port 9999 (`:228`), `TRADINGAGENTS_LLM_MAX_RETRIES=0` (`:229`). Alle drei Assertions vorhanden und jede mit eigenem `fail`: Exit != 0 (`:235-238`), Exit != 125 (`:239-242`), Marker-Grep (`:243-247`). Bei jedem Fehlschlag wird `$NEG_OUT` ausgegeben. Der Name ist der Grund, dass 125 nicht eintreten kann — `tex-smoke-run` existiert zu dem Zeitpunkt noch (`:170`). Kein „grün durch Konstruktion" |
| 4 | Jeder Push auf main und jeder PR fährt denselben Smoke als eigenen Job mit Zeitlimit | ✓ VERIFIED | `ci.yml` YAML-geparst: Jobs `['test','smoke-install','docker-smoke','lint']`, Trigger `push.branches=['main','v[0-9]+.[0-9]+.[0-9]+']` + `pull_request`, `docker-smoke.timeout-minutes=10`, Steps genau `['actions/checkout@v7', 'bash scripts/smoke/docker_smoke.sh']` — kein `setup-python`. Erster echter Runner-Lauf → Human-Item 2 |
| 5 | Der Smoke beweist „kein echter LLM-Call": Isolation ist der Beweis, Zähler == 9 die Kontrolle | ✓ VERIFIED | `--internal`-Netz (`:95`), Zähler-Assertion gegen `SMOKE_EXPECTED_CALLS` (`:210-213`) über `GET /__count` **im** Stub-Container. Zähler-Semantik eigenhändig ohne Docker nachgemessen (Spot-Check 1): 5 GET-Sonden → `calls=0`; nur `POST …/chat/completions` zählt; 404-Routen zählen nicht. Die konkrete `9` ist Laufzeit → Human-Item 1 |
| 6 | `state_maintenance.py verify`: korrupte Checkpoint-DB → Exit 2, intakte → ok | ✓ VERIFIED | Eigener CLI-Lauf (Spot-Check 3): gesund → `rc=0`, `ok: AAPL.db`; nach Müll ab Offset 4096 → `rc=2`, `FAIL: AAPL.db: quick_check failed: database disk image is malformed`. Das ist belegbar der `sqlite3.DatabaseError`-Pfad (`state_maintenance.py:90-93`), kein Rückgabevergleich; zusätzlich Schema-Prüfung auf `checkpoints`+`writes` (`:100-108`) und Prüfung auf einer Temp-Kopie inkl. Sidecars (`:76-81`) |
| 7 | `prune --apply` löscht abgelaufene Checkpoints inkl. `-wal`/`-shm`, Decision-Log unangetastet | ✓ VERIFIED | Sidecar-Glob `cp_dir.glob(f"{db.name}-*")` (`:215`) — identisch zu `checkpointer.py:80`. Eigener CLI-Lauf: `--apply --checkpoint-days 0` löschte die DB und ließ das Decision-Log **byte-identisch**, Ausgabe `decision log: kept (unlimited retention by operator decision)`. Dry-run (ohne `--apply`) löschte nachweislich nichts. Kein Code-Pfad im Werkzeug schreibt oder löscht je am Memory-Log |
| 8 | `backup` erzeugt ein Archiv mit Decision-Log und ohne jede Checkpoint-DB | ✓ VERIFIED | Eigener CLI-Lauf (Spot-Check 4): 4 Mitglieder unter einem Top-Level-Verzeichnis — `decision-log.md`, `index.md`, `runs/2026-10-09/summary.json`, `cli/trading_memory.md`. Nicht im Archiv: die untergeschobene `runs/2026-10-09/AAPL.db`, `decision-log.md.lock`, `decision-log.tmp` und `secrets.env`. Allow-List statt Sweep (`:319-331`), Suffix-Ausschluss `.lock/.tmp/.db` (`:58,288-289`) |
| 9 | Runbook: wo jeder State liegt, wie lange gehalten, wie Recovery läuft, welche Locking-Lücken existieren | ✓ VERIFIED (mit W-1) | `scripts/STATE_OPERATIONS.md`, 265 Zeilen, alle vier Themen als eigene Kapitel: Where state lives (`:16-52`), Retention (`:81-101`), Backup (`:118-143`), Recovery (`:145-197`), Concurrency and locking mit **fünf** numerierten Lücken (`:199-235`). 24 von 24 geprüften `file:line`-Verweisen korrekt oder vertretbar (Tabelle unten). Einschränkung W-1: die Retention-Tabelle nennt nur 4 der 9 gelisteten State-Orte |
| 10 | Beide offenen P2-DoD-Punkte mit Belegen abgehakt; P2 #6/#8 bleiben sichtbar offen | ✓ VERIFIED | `grep '^- \[ \]' .planning/MILESTONE.md` → **kein Treffer** (rc=1). Beide Haken tragen Belege: Smoke (`:130-140`: Skriptpfade, CI-Jobname, `SMOKE OK`-Zeile, Negativ-Kontrolle, Zähler) und State (`:144-153`: Runbook, Werkzeug, 18 Tests, Suite-Zeile). P2 #7 und #10 durchgestrichen mit `28f4a75`/`e32c6a4` bzw. `12ed32d` — alle vier Hashes existieren (`git cat-file -t` → commit). #11 auf „Restumfang: Vendor-Quota-Verhalten" reduziert, **nicht** abgehakt. #6 und #8 unverändert offen, dazu ein expliziter Blockquote (`MILESTONE.md:85-92`) |

**Score:** 10/10 Truths verifiziert — 3 Laufzeitbestätigungen (Docker/Runner) stehen aus und sind als Human-Items ausgewiesen, nicht als „verifiziert" gezählt-und-vergessen.

### Die fünf Prüfaufträge im Detail

**1. Erfüllen die Retention-Defaults die Operator-Entscheidung? — JA, im Code nachgelesen und nachgemessen.**

| Operator-Entscheidung (CONTEXT:43-50) | Code | Überschreibbar | Nachgemessen |
|---|---|---|---|
| Decision-Log: unbegrenzt, nie automatisch beschnitten | kein Prune-Pfad; Ausgabezeile `state_maintenance.py:277-279`; kein `rotate`-Unterkommando (`:355-382`) | — (bewusst kein Flag) | `prune --apply --checkpoint-days 0` ließ das Log byte-identisch; `rotate` → rc=1 |
| Checkpoints: 7 Tage | `DEFAULT_CHECKPOINT_DAYS = 7` (`state_maintenance.py:60`), gebunden in `:369` | `--checkpoint-days` | Default-Dry-Run: `limit 7 d`; mit `--checkpoint-days 30`: `keep AAPL.db (10.0 d old, limit 30 d)` |
| Reports: 90 Tage | `DEFAULT_REPORT_DAYS = 90` (`state_maintenance.py:61`), gebunden in `:370` | `--report-days` | Default-Dry-Run: `limit 90 d`; mit `--report-days 1`: `would delete AAPL_20250101_120000/ … limit 1 d` |

Keine Rotation des Decision-Logs implementiert — das ist die im PLAN/`<objective>` ausgesprochene Auflösung des CONTEXT-Widerspruchs (CONTEXT:35-36 vs. :45-46) und steht als Entscheidung im Modul-Docstring (`state_maintenance.py:18-23`) und im Runbook (`STATE_OPERATIONS.md:113-116`). Keine Lücke.

**2. Ist `state_maintenance.py` wirklich nicht in den täglichen Paper-Lauf eingehängt? — JA, nachgewiesen abwesend.**

`grep -n "state_maintenance" scripts/daily_paper_run.py .github/workflows/daily-paper-run.yml` → **rc=1, kein Treffer.** Repo-weit referenzieren das Werkzeug nur: `scripts/STATE_OPERATIONS.md`, `scripts/PAPER_RUN.md:114`, `tests/test_state_maintenance.py`, `.planning/MILESTONE.md` und die eigene Datei. `git diff a734955..86ac1ae --stat` fasst **weder** `scripts/daily_paper_run.py` **noch** `.github/workflows/daily-paper-run.yml` an (8 Dateien, keine davon im Produktivpfad). Die Entscheidung GEGEN die dritte Option ist eingehalten und an zwei Stellen ausgesprochen (`STATE_OPERATIONS.md:253-255`, `MILESTONE.md:85-92`).

**3. Hat der Smoke Beweiskraft? — Ja, die Negativ-Kontrolle ist nicht „grün durch Konstruktion".**

Eigener Container (`docker_smoke.sh:223`), alle drei Assertions verpflichtend und je mit eigenem `fail` (`:235-247`), `$NEG_OUT` wird bei jedem Fehlschlag ausgegeben. Der 125-Ausschluss ist genau der Scheinbeleg-Pfad, den der PLAN benannt hat. Ergänzend gegen Selbstbetrug geprüft: der Stub-Start wird hart über `docker inspect -f '{{.State.Running}}'` geprüft — vor der Readiness-Schleife **und in jeder Iteration** (`:113-129`), mit `docker logs` + `.Args` bei Fehlschlag.
Zwei Hinweise ohne Blocker-Charakter: (a) der Marker-Satz enthält `Failed to establish a new connection` (`:244`), was `urllib3` auch bei einem **DNS**-Fehler eines Datenvendors im isolierten Netz ausgibt — die Zuordnung trägt hier der Exit-Code-Kontrast zum identisch konfigurierten Positivlauf (nur Port verschieden, Exit 0) und das beobachtete `ECONNREFUSED`; (b) `docker cp` (`:170`) steht vor Assertion (a) (`:175`), ein Lauf ohne Container stirbt also an `docker cp` statt mit der passenden Meldung — nicht-null bleibt nicht-null, kein Falsch-Positiv.

**4. Deckt das Runbook die vier Themen, und stimmen die Datei:Zeile-Verweise? — Ja; alle vom Executor als korrigiert gemeldeten Nummern stimmen.**

| Behauptung im Runbook/SUMMARY | Nachgemessen | Status |
|---|---|---|
| `files.py` hat 88 Zeilen | `wc -l` → **88** | ✓ |
| `replace_file`-Temp-Name auf `files.py:24` | `:24` `temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")` | ✓ |
| `locked` = `files.py:37-88`, `fcntl.flock` :57, `msvcrt.locking` :74 | `def locked` auf **:37** (Dekorator :36), `_hold_posix` 52-64 mit `fcntl.flock` auf **:57**, `_hold_windows` 67-88 mit `msvcrt.locking` auf **:74** | ✓ (Spanne ist der Mechanismus inkl. beider Helfer, nicht die Funktion allein — INFO-1) |
| `log.py:198` `with_suffix(".tmp")` ersetzt die Endung | `:198` `tmp_path = self._log_path.with_suffix(".tmp")`, zweite Stelle `:252` | ✓ |
| `log.py:46,156,211` nehmen den Lock | alle drei `with locked(self._log_path):` | ✓ |
| `log.py:72` Settlement-Lock, `:273-308` Rotation, `:310-341` `_parse_entry`, `:46-55` Idempotenz | je zutreffend | ✓ |
| `checkpointer.py:80` Sidecar-Glob, `:45` `check_same_thread=False`, `:51` `conn.close()`, `:68-82`, `:28-38`, `:19-25`, `:3`, `:93` | alle zutreffend | ✓ |
| `default_config.py:85` cache, `:86` memory_log_path, `:90` `memory_log_max_entries: None`, `:10-34` `_ENV_OVERRIDES` (ohne Rotations-Key) | alle zutreffend; `memory_log_max_entries` fehlt in `_ENV_OVERRIDES` | ✓ |
| `daily_paper_run.py:223` (statt RESEARCH `:218`), `:226` `checkpoint_enabled = False`, `:323-331` `_archive`, `:490` `index.md`, `:210-227` `build_config` | alle zutreffend — die SUMMARY-Korrektur auf `:223` ist richtig | ✓ |
| `trading_graph.py:307` Report-Baum, `:530` (statt RESEARCH `:527-531`) Zustandslog, `:343` `settle_all_pending(wait=False)` | alle zutreffend — `:530` ist richtig | ✓ |
| `daily-paper-run.yml:101` STATE_DIR, `:144` Restore, `:192` `retention-days: 90`, `:194-211` Commit, `:203` `git add -A .` | alle zutreffend | ✓ |
| `cli/run.py:153`, `:180-193`; `cli/prefs.py:28,57`; `cli/main.py:41-43,75-78`; `settlement.py:120,165`; `tests/test_memory_log.py:322-368` | alle zutreffend | ✓ |
| „`decision-log.md.lock` liegt committet auf `paper-log`, `.settle.lock` nicht" | `git ls-tree -r refs/remotes/fork/paper-log` → `decision-log.md.lock` vorhanden, kein `.settle.lock`; `runs/` ab 2026-09-24 dauerhaft | ✓ |
| „kein `sqlite3`-Binary auf dieser Workstation" | `command -v sqlite3` → nicht gefunden | ✓ (Image-Hälfte → Human-Item 3) |
| `daily-paper-run.yml:58-59` für die `concurrency`-Gruppe | `concurrency:` auf :58, `group: daily-paper-run` erst auf :61 | ✓ vertretbar (INFO-4) |

**5. Die DoD-Haken in `.planning/MILESTONE.md` — nur dort gesetzt, wo es Belege gibt.**

Zwei Haken gesetzt, beide mit prüfbaren Belegen (siehe Truth 10). Die Beleg-Zeile des State-Punkts (`1374 passed, 4 skipped, 2 deselected, …, rc=0`) deckt sich mit der unabhängigen Messung des Operators in diesem Auftrag. Die Smoke-Beleg-Zeile ist formatidentisch mit der Ausgabe aus `docker_smoke.sh:258` und steht unter Human-Item 1. Nichts wurde abgehakt, was im Repo nicht existiert: `#11` blieb bewusst ohne Haken, `#6`/`#8` sind unverändert offen.

### Required Artifacts

| Artifact | Erwartet | Exists | Substanz | Verdrahtet | Status |
|---|---|---|---|---|---|
| `scripts/smoke/stub_llm.py` | Stub, `ThreadingHTTPServer`, Rollenerkennung über `tools`, `GET /__count` | ✓ 186 Z. (min 90) | ✓ `ThreadingHTTPServer` `:179` mit `daemon_threads` `:180` und Begründungs-Kommentar `:172-178`; `log_message` stumm `:129`; Rollenerkennung `_tool_names`/`_reply_for` `:79-107` | ✓ `docker cp` + `python -I //stub_llm.py` (`docker_smoke.sh:101-103`) | ✓ VERIFIED |
| `scripts/smoke/docker_smoke.sh` | Teardown, Build, isoliertes Netz, Stub, Lauf, Assertions a–f, Negativ-Kontrolle, Teardown | ✓ 258 Z. (min 110) | ✓ `--internal` `:95`; Assertions a–f `:175-213`; Negativ-Kontrolle `:221-254`; `bash -n` sauber | ✓ `ci.yml:65` | ✓ VERIFIED |
| `.github/workflows/ci.yml` | Job `docker-smoke` | ✓ 80 Z. | ✓ YAML geparst, `timeout-minutes: 10`, kein `setup-python` | ✓ ruft genau das Skript | ✓ VERIFIED |
| `scripts/state_maintenance.py` | `prune`/`backup`/`verify`, `quick_check` | ✓ 415 Z. (min 180) | ✓ `quick_check` in `try/except sqlite3.DatabaseError` `:90-93`; `main(argv) -> int` `:385`; Exit-Codes dokumentiert `:25-29`; T-k4s-01/02-Schutz (`:176-186`, `:207`, `:234`, `:55`, `:319-331`) | ✓ Tests + Runbook + `PAPER_RUN.md:114`; **bewusst nicht** im Produktivpfad | ✓ VERIFIED |
| `tests/test_state_maintenance.py` | Tests aller drei Unterbefehle inkl. Korruption, Sidecars, fehlender Separator | ✓ 391 Z. (min 150) | ✓ **18** Testfunktionen gezählt (= Behauptung); Modul-Laden per `importlib` wie `test_daily_paper_run.py`; alle Pfade aus `tmp_path`, kein `~` | ✓ Operator-Messung: 18 passed | ✓ VERIFIED |
| `scripts/STATE_OPERATIONS.md` | Pfade, Retention, Rotation, Backup, Recovery, Locking-Lücken | ✓ 265 Z. (min 90) | ✓ alle Kapitel vorhanden, `file:line`-Belege geprüft | ✓ `PAPER_RUN.md:18,113`; rückwärts `state_maintenance.py:9` | ✓ VERIFIED (mit W-1) |
| `scripts/PAPER_RUN.md` | Verweis auf das State-Kapitel | ✓ | ✓ Kopftabellen-Zeile `:18` + Absatz `:112-114` | ✓ | ✓ VERIFIED |
| `.planning/MILESTONE.md` | DoD-Haken mit Belegen | ✓ | ✓ keine offene Checkbox, Belege statt Absichten | ✓ | ✓ VERIFIED |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `.github/workflows/ci.yml` | `scripts/smoke/docker_smoke.sh` | `run: bash scripts/smoke/docker_smoke.sh` | ✓ WIRED | `ci.yml:65`, YAML-geparst |
| `docker_smoke.sh` | `stub_llm.py` | `docker cp` + `python -I //stub_llm.py` | ✓ WIRED | `:101-103`; zwei Slashes wörtlich vorhanden; Index/Worktree LF (`git ls-files --eol` → `i/lf w/lf`), auf `ubuntu-latest` also lauffähig |
| `docker_smoke.sh` | Stub-Call-Zähler | `docker exec … GET /__count` vs. `SMOKE_EXPECTED_CALLS` | ✓ WIRED | `:210-213`; Sonde seiteneffektfrei nachgemessen |
| `docker_smoke.sh` | Negativ-Kontrolle | `tex-smoke-neg` + Ursachen-Assertion | ✓ WIRED | `:68,223,235-247` |
| `state_maintenance.py` | `checkpointer.py:80` | gleiche Sidecar-Glob-Logik `f"{db.name}-*"` | ✓ WIRED | `:215` (prune) und `:79` (verify-Kopie); `checkpointer.py:80` gegengelesen |
| `state_maintenance.py` | `TradingMemoryLog._SEPARATOR` | Blockvergleich gegen `load_entries()` | ✓ WIRED | `:129-131`; `_SEPARATOR` aus der Klasse gelesen (`log.py:15`), nicht neu getippt |
| `STATE_OPERATIONS.md` | `state_maintenance.py` | Kommando-Abschnitt | ✓ WIRED | `:237-255`, alle drei Unterbefehle + Dry-run-Hinweis |

### Data-Flow Trace (Level 4)

| Artifact | Daten | Quelle | Echte Daten? | Status |
|---|---|---|---|---|
| `stub_llm.py` → Entscheider-Parser | `SCHEMA_ARGS` | hartverdrahtet (Zweck des Test-Doubles) | ✓ alle drei Payloads gegen die **echten** Pydantic-Modelle instanziiert: `ResearchPlan`, `TraderProposal`, `PortfolioDecision` → VALID (Spot-Check 2) | ✓ FLOWING |
| `stub_llm.py` → Analysten | `PLAIN_TEXT` | Repo-Kanon `tests/test_graph_end_to_end.py:32` | ✓ Antwort an Analysten enthält **kein** `tool_calls` und `finish_reason=stop` (Spot-Check 1) — sonst Endlos-Tool-Schleife (`graph/setup.py:48-50`) | ✓ FLOWING |
| `state_maintenance.py` Defaults | `DEFAULT_CONFIG["data_cache_dir"|"results_dir"|"memory_log_path"]` | `default_config.py:84-86` | ✓ Schlüssel existieren; `verify`/`prune` ohne Flags laufen | ✓ FLOWING |
| `verify` → Befund | `PRAGMA quick_check` + `sqlite_master` | echte SQLite-Datei (Temp-Kopie inkl. Sidecars) | ✓ echte Korruption erzeugt → echter Befund; kein statischer Rückgabewert | ✓ FLOWING |
| `backup` → Archiv | Allow-List-Dateien | echtes Dateisystem | ✓ 4 echte Mitglieder, Ausschlüsse greifen | ✓ FLOWING |

### Behavioral Spot-Checks

Alle vom Verifier selbst ausgeführt (nicht aus dem SUMMARY übernommen), ohne Docker, ohne pytest.

| # | Behavior | Command | Result | Status |
|---|---|---|---|---|
| 1 | `GET /__count` ist seiteneffektfrei; nur gezählte POSTs erhöhen; 404 zählt nicht; Rollenerkennung | Stub per `importlib` geladen, eigener `ThreadingHTTPServer` auf Port 0, 5 GET-Sonden + 2 POSTs + 2 Fehlrouten | `after 5 GET probes, calls = 0` · decider → `finish_reason=tool_calls`, `tool=PortfolioDecision` · analyst → `stop`, kein `tool_calls`, Text `Report.\n\n**Rating**:…` · `calls after 2 POSTs = 2` · 404/404 · `calls after the 404s = 2` | ✓ PASS |
| 2 | Stub-Argumente erfüllen die echten Entscheider-Schemata | `ResearchPlan(**SCHEMA_ARGS[...])` usw. gegen `tradingagents.agents.schemas` | alle drei VALID (`recommendation=Overweight`, `action=Buy`, `rating=Overweight`) | ✓ PASS |
| 3 | `verify`/`prune`-Verhalten + Retention-Defaults + Usage-Codes | `scripts/state_maintenance.py` als Skript, echte Checkpoint-DB über `get_checkpointer`, Korruption ab Offset 4096 | gesund `rc=0`; korrupt `rc=2` + `database disk image is malformed`; Dry-run löschte nichts, zeigte `limit 7 d`/`limit 90 d`; Flags überschreiben (`30 d`/`1 d`); `--apply --checkpoint-days 0` löschte die DB, Log byte-identisch; `backup` ohne `--out` → 1, ohne `--state-dir` → 1; unbekanntes Kommando → 1; `rotate` → 1 | ✓ PASS |
| 4 | `backup`-Allow-List | echtes State-Dir mit `.lock`, `.tmp`, `secrets.env`, `runs/**/AAPL.db` | 4 Mitglieder, ein Top-Level-Verzeichnis, kein `.db`/`.lock`/`.tmp`/`secrets.env` | ✓ PASS |
| 5 | Shell-Syntax des Smoke-Skripts | `bash -n scripts/smoke/docker_smoke.sh` | `BASH_SYNTAX_OK` | ✓ PASS |
| 6 | CI-Workflow ist valides YAML und ruft genau das Skript | `yaml.safe_load` + Job-Introspektion | Jobs, Trigger, Timeout, Steps wie oben | ✓ PASS |
| 7 | Zeilenenden des Skripts im Git-Objekt (sonst stirbt es auf `ubuntu-latest` an `\r`) | `git cat-file blob HEAD:… \| tr -cd '\r' \| wc -c`, `git ls-files --eol` | 0 CR-Bytes, 258 LF; `i/lf w/lf` | ✓ PASS |
| 8 | Zwei Container-Vollläufe des Smokes + Negativ-Kontrolle live | `bash scripts/smoke/docker_smoke.sh` | nicht ausgeführt — Docker-gebunden, Operator fährt es parallel | ? SKIP → Human-Item 1 |

Nicht erneut gefahren (ausdrücklich außerhalb des Auftrags, vom Operator unmittelbar vorher selbst gemessen): `pytest` (`1374 passed, 4 skipped, 2 deselected, rc=0`), `ruff check .` (clean), `tests/test_state_maintenance.py` (18 passed).

### Probe Execution

| Probe | Command | Result | Status |
|---|---|---|---|
| — | `find scripts -path '*/tests/probe-*.sh'` | kein Treffer; der PLAN deklariert keine Probe-Skripte (Gates sind pytest/ruff/Docker) | N/A — nicht anwendbar |

### Requirements Coverage

`.planning/REQUIREMENTS.md` existiert in diesem Projekt nicht; die IDs des PLAN-Frontmatters sind auf `.planning/MILESTONE.md` gemünzt und werden dort gegengeprüft.

| Requirement | Bedeutung | Status | Evidence |
|---|---|---|---|
| MS-P2-10 | End-to-End-Smoke in Docker mit Stub-Providern | ✓ SATISFIED (Laufzeit → Human-Item 1) | `MILESTONE.md:67-75` durchgestrichen mit `12ed32d`; Artefakte + CI-Job verifiziert |
| MS-P2-07 | State-Betrieb: Retention/Backup/Locking/Recovery | ✓ SATISFIED | `MILESTONE.md:60-66` durchgestrichen mit `28f4a75`, `e32c6a4`; Runbook + Werkzeug + 18 Tests verifiziert |
| MS-P2-11 | Betriebs-Runbook | ✓ SATISFIED (reduziert, bewusst nicht abgehakt) | `MILESTONE.md:76-82`: Checkpoint-Hygiene/Memory-Log/Recovery abgedeckt, Vendor-Quota offen bei #8 — ehrlich reduziert statt abgehakt |
| MS-DOD-SMOKE | DoD „Docker-/CLI-Smoke läuft reproduzierbar" | ✓ SATISFIED (Laufzeit → Human-Item 1) | `MILESTONE.md:130-140` |
| MS-DOD-STATE | DoD „State-Retention/Backup/Recovery dokumentiert" | ✓ SATISFIED | `MILESTONE.md:144-153`; Suite-Zeile deckt sich mit der Operator-Messung |

Keine orphaned Requirements: der CONTEXT grenzt P2 #6 und #8 explizit aus, und beide bleiben im MILESTONE sichtbar offen.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| — | — | `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` in allen 8 berührten Dateien gesucht | — | **Kein Treffer.** Kein Debt-Marker, also keine unauditierbare Restschuld |
| — | — | `return null`/`return {}`/`=> {}`/leeres `pass` in `state_maintenance.py`, `stub_llm.py` | — | Kein Treffer |
| `scripts/smoke/stub_llm.py` | gesamt | hartverdrahtete Antwortwerte | ℹ️ Info | Beabsichtigtes Test-Double, nicht Platzhalter — die Werte sind gegen die echten Schemata validiert (Spot-Check 2) |
| `scripts/smoke/docker_smoke.sh` | 170 vs. 175 | `docker cp` vor der Exit-Code-Assertion | ℹ️ Info | Fehlender Container ⇒ Abbruch an `docker cp` statt mit der passenden Meldung; Exit bleibt nicht-null, kein Falsch-Positiv |
| `scripts/smoke/docker_smoke.sh` | 244 | Marker `Failed to establish a new connection` auch bei Vendor-DNS-Fehlern möglich | ℹ️ Info | Zuordnung trägt der Exit-Kontrast zum Positivlauf; der beobachtete Marker war `APIConnectionError` plus `ECONNREFUSED` |
| `scripts/STATE_OPERATIONS.md` | 60, 205, 207, 222 | Spannen-/Funktionsgrenzen leicht unscharf (INFO-1/2/3/4) | ℹ️ Info | `files.py:37` statt `:46` für den `.lock`-Namen; `:14-32` statt `:14-33`; `:37-88` = Mechanismus statt Funktion; `yml:58-59` statt `:61` für `group:`. Alle Verweise zeigen auf die richtige Stelle, keiner ist falsch |
| Repo | — | kein `.gitattributes`, `core.autocrlf=true` | ℹ️ Info | Vorbestehend, identisch für `scripts/graphify.sh`; Blob und Worktree sind LF, CI unbetroffen. Im SUMMARY als Operator-Entscheidung benannt |

### Warnings

**W-1 — Die Retention-Tabelle beantwortet „wie lange wird er gehalten" nur für 4 der 9 gelisteten State-Orte.**

`scripts/STATE_OPERATIONS.md:39-48` listet neun State-Orte; `:83-88` nennt Fristen für vier davon (Decision-Log, Checkpoints, Report-Verzeichnisse, Workflow-Artefakt). Ohne Frist und ohne Prune-Abdeckung bleiben: `logs/<TICKER>/<date>/reports/*.md`, `logs/<TICKER>/<date>/message_tool.log`, `logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json`, die Daten-Caches `~/.tradingagents/cache/` und `cli_prefs.json`. Im Code ist das eindeutig: `prune` fasst ausschließlich `<cache>/checkpoints` (`scripts/state_maintenance.py:144,202`) und die direkten Kinder von `<results_dir>/reports` (`:226,231`) an — die Zeile „Report directories | **90 days**" meint also nur den konsolidierten Baum `<results_dir>/reports/<T>_<stamp>/`, nicht den per-Run-Baum, und das sagt das Runbook nicht.

Kein Verstoß gegen die Operator-Entscheidung (die nannte nur drei Retention-Klassen) und kein funktionaler Defekt — deshalb Warnung, nicht Lücke. Das Runbook ist an anderer Stelle vorbildlich ehrlich über genau so eine Einschränkung (die `runs/`-Dauerhaftigkeit, `:95-101`); diese eine fehlt. **Operator-Entscheidung nötig:** einen Satz nachtragen („der per-Run-Baum unter `logs/<TICKER>/<date>/` und die Caches werden nicht beschnitten") — oder bewusst so lassen.

### Human Verification Required

### 1. Docker-Smoke live, zweimal plus Idempotenz-Kette

**Test:** `bash scripts/smoke/docker_smoke.sh; echo rc=$?` zweimal hintereinander, dann `SMOKE_KEEP=1 bash scripts/smoke/docker_smoke.sh && bash scripts/smoke/docker_smoke.sh`
**Erwartet:** jedes Mal `rc=0` und `SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)`
**Warum Mensch:** braucht einen laufenden Docker-Daemon; Container-Starts liegen außerhalb dessen, was dieser Verifier tut (der Operator fährt den Lauf parallel). Struktur, Assertions, Zähler-Semantik und Stub-Payloads sind ohne Docker nachgewiesen (Spot-Checks 1–2, 5).

### 2. Erster CI-Lauf des Jobs `docker-smoke` auf `ubuntu-latest`

**Test:** nächsten Push/PR beobachten
**Erwartet:** Job grün in < 10 min; `//stub_llm.py` kommt unverändert an und wird vom Kernel auf `/stub_llm.py` aufgelöst; kein uid-Problem (kein Host-Mount im Skript)
**Warum Mensch:** noch nie auf einem Runner gelaufen — Image-Pull, Build-Zeit und Runner-uid sind lokal nicht beobachtbar. Das SUMMARY benennt es selbst als ungetestet; die bekannten Risiken sind im Skript adressiert.

### 3. `sqlite3`-Binary im Image

**Test:** `docker run --rm --entrypoint sh tex-smoke:local -c 'command -v sqlite3 || echo none'`
**Erwartet:** `none`
**Warum Mensch:** die Workstation-Hälfte der Runbook-Behauptung (`STATE_OPERATIONS.md:159-162`) ist verifiziert, die Image-Hälfte braucht Docker.

### Gaps Summary

**Keine Lücke.** Die Falsifikationsversuche sind gescheitert: Das Wartungswerkzeug ist nicht in den Produktivpfad eingehängt (grep leer, Diff fasst keine Produktivdatei an), die Retention-Defaults im Code sind exakt die drei Operator-Fristen und per Flag überschreibbar, die Negativ-Kontrolle hat ihren eigenen Container und assertiert die Ursache statt nur „irgendein Fehler", und die vom Executor als korrigiert gemeldeten Zeilennummern stimmen alle — `files.py` hat tatsächlich 88 Zeilen, der Temp-Name steht auf :24, `fcntl.flock` auf :57 und `msvcrt.locking` auf :74. Die DoD-Haken tragen prüfbare Belege; nichts ist abgehakt, was nicht existiert.

Offen bleibt genau das, was ohne Docker-Daemon und ohne GitHub-Runner prinzipiell nicht zu sehen ist — drei Laufzeitbestätigungen, davon zwei bereits unterwegs. Hinzu kommt eine Dokumentations-Warnung (W-1) über die Retention-Stille bei fünf nachrangigen State-Orten, die eine Operator-Entscheidung braucht, aber keine Nacharbeit erzwingt.

---

_Verified: 2026-10-11T14:25:00Z_
_Verifier: Claude (gsd-verifier) — goal-backward, adversarial stance_
