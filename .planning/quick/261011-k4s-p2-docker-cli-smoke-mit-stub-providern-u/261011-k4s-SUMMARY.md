---
phase: quick-261011-k4s
plan: 01
subsystem: ops-smoke-state
tags: [docker-smoke, stub-llm, threadinghttpserver, internal-network, sqlite-integrity, retention, backup, recovery, locking, runbook]
requires: [strand main a734955 (Upstream v0.6.0 + Strang), Docker Desktop 29.8.1, Git Bash MINGW64 bash 5.3.15]
provides:
  - scripts/smoke/docker_smoke.sh (End-to-End-Smoke durch das Image, lokal + CI, mit eingebauter Negativ-Kontrolle)
  - scripts/smoke/stub_llm.py (deterministischer OpenAI-kompatibler LLM-Stub, reine stdlib)
  - CI-Job docker-smoke in .github/workflows/ci.yml
  - scripts/state_maintenance.py (verify / prune / backup) + 18 Tests
  - scripts/STATE_OPERATIONS.md (Runbook-Kapitel mit file:line-Belegen)
  - MILESTONE-DoD ohne offene Checkbox
affects:
  - .github/workflows/ci.yml
  - scripts/PAPER_RUN.md
  - .planning/MILESTONE.md
tech-stack:
  added: []
  patterns:
    - "Smoke ohne Host-Python: alle Assertions über test/grep/docker exec, ein Skript für lokal und CI"
    - "Netzisolation statt Daten-Stubs: --internal-Netz + die vorhandene Fehler-Degradation (DATA_UNAVAILABLE) ist der Offline-Pfad"
    - "Negativ-Kontrolle im Smoke selbst, in eigenem Container, mit Exit != 0 UND != 125 UND Ursachen-Marker"
    - "Rollenerkennung eines LLM-Stubs über request[\"tools\"] statt über die URL"
    - "SQLite-Integrität über PRAGMA quick_check in try/except sqlite3.DatabaseError plus Schema-Prüfung, auf einer Temp-Kopie inkl. -wal/-shm"
    - "Decision-Log-Prüfung über nicht-leere Blöcke vs. load_entries(), nicht über Separator-Zählung"
    - "prune ist dry-run per Default; Löschen nur mit --apply, Report-Verzeichnisse nur bei Namensmuster"
key-files:
  created:
    - scripts/smoke/stub_llm.py
    - scripts/smoke/docker_smoke.sh
    - scripts/state_maintenance.py
    - tests/test_state_maintenance.py
    - scripts/STATE_OPERATIONS.md
  modified:
    - .github/workflows/ci.yml
    - scripts/PAPER_RUN.md
    - .planning/MILESTONE.md
decisions:
  - "Kein rotate-Unterkommando: die Retention-Entscheidung 'Decision-Log unbegrenzt' ist die spezifischere und verdrängt das Rotations-Detail aus CONTEXT:35-36; Rotation bleibt Operator-Opt-in im Code (memory_log_max_entries). Im Modul-Docstring und im Runbook als Entscheidung ausgesprochen."
  - "backup --state-dir ist verpflichtend, weil DEFAULT_CONFIG keinen state_dir-Schlüssel hat; Pflichtflags werden im Handler geprüft, damit main(argv) einen Rückgabewert liefert statt SystemExit."
  - "Interpreter-Argument des Stub-Containers wörtlich //stub_llm.py (MSYS-Pfadregel) — auf beiden Aufrufern korrekt."
  - "Das Wartungswerkzeug wird NICHT in den täglichen Paper-Lauf eingehängt (Produktivpfad unberührt)."
  - "Der .lock-Commit auf paper-log wird nur dokumentiert, nicht gefixt — ein Fix hieße daily-paper-run.yml anfassen."
requirements-completed: [MS-P2-07, MS-P2-10, MS-P2-11, MS-DOD-SMOKE, MS-DOD-STATE]
duration: ~100min
completed: 2026-10-11
---

# Quick Task 261011-k4s: P2 — Docker-/CLI-Smoke + State-Retention/Backup/Recovery — Summary

**Die beiden letzten offenen P2-DoD-Punkte sind geschlossen, mit Belegen statt Absichten: ein
reproduzierbarer CLI-Lauf durch das Docker-Image gegen einen Stub-LLM im `--internal`-Netz (9
Stub-Calls, Exit 0, eingebaute Negativ-Kontrolle) und ein getestetes State-Wartungswerkzeug plus
Runbook-Kapitel, in dem jede Aussage eine `file:line`-Quelle trägt.**

## Performance

- **Duration:** ~100 min (erster Commit 15:53:49, letzter 16:04:53; davor Recherche-Lesen,
  Implementierung und 6 vollständige Smoke-Läufe)
- **Tasks:** 3 von 3
- **Commits:** 4 (atomar, englisch)
- **Dateien:** 5 neu, 3 geändert

## Task Commits

| Task | Inhalt | Commit | Typ |
|---|---|---|---|
| Task 1 | LLM-Stub + Docker-Smoke-Skript + CI-Job | `12ed32d` | feat |
| Task 2 | `scripts/state_maintenance.py` + 18 Tests | `28f4a75` | feat |
| Task 3 A+B | `scripts/STATE_OPERATIONS.md` + `PAPER_RUN.md`-Verweis | `e32c6a4` | docs |
| Task 3 C | `.planning/MILESTONE.md` DoD nachgezogen | `86ac1ae` | docs |

`.planning/quick/261011-k4s-…` (PLAN/CONTEXT/RESEARCH/SUMMARY) bleibt **uncommittet** — das macht
der Orchestrator. `.planning/STATE.md` und `ROADMAP.md` wurden nicht angefasst.

## Gates — wörtliche Ausgaben

Kein Gate wurde übersprungen; kein Gate ist fehlgeschlagen.

### 1. Bewertendes Test-Gate (Suite ohne Regress, Exit 0)

```
$ PYTHONPATH=. .../tex-v060/Scripts/python.exe -m pytest -q \
    --deselect tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
1374 passed, 4 skipped, 2 deselected, 20 warnings, 101 subtests passed in 29.49s
rc=0
```

Nullmessung des Plans ohne Task 2: `1356 passed, 4 skipped, 2 deselected` — die 18 neuen Tests
kommen obendrauf (1356 + 18 = 1374). Deselektiert wurde genau der **eine** nachgemessene
vorbestehende Knoten, nie eine ganze Datei; der Knoten entspricht dem im Plan genannten.

### 2. Ungefilterte Suite (nur Beleg, nicht bewertend)

```
$ PYTHONPATH=. .../tex-v060/Scripts/python.exe -m pytest -q
FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
1 failed, 1374 passed, 4 skipped, 1 deselected, 20 warnings, 101 subtests passed in 31.12s
```

Der eine Fehler ist der vorbestehende `test_suite_isolation`-Knoten (Windows-`TEMP` liegt unter
`Path.home()`). Er wurde **nicht** „repariert" und ist laut Plan nicht bewertend. **Kein zweiter
Fehler** — also kein Regress.

### 3. Lint

```
$ .venv/Scripts/ruff.exe check .
All checks passed!
```

(ruff 0.15.12, strict select `E,W,F,I,B,UP,C4,SIM`, ganzes Repo. Die Projekt-`.venv` wurde nur als
Linter benutzt, nichts hineininstalliert.)

### 4. Docker-Smoke, zweimal hintereinander grün

```
$ bash scripts/smoke/docker_smoke.sh; echo "rc1=$?"
SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)
rc1=0

$ bash scripts/smoke/docker_smoke.sh; echo "rc2=$?"
SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)
rc2=0
```

Laufzeiten: zweiter Lauf **11 s** (Image vorhanden). Ein Lauf nach `docker rmi tex-smoke:local`
bei warmem Build-Cache: **49 s** (dominiert vom Image-Export). Der erste Lauf der Sitzung enthielt
den Build und wurde nicht separat gestoppt.

### 5. W1-Gate (Checker-Addendum): Idempotenz nach `SMOKE_KEEP=1` beweisen

Der Plan behauptete Idempotenz „auch nach `SMOKE_KEEP=1` oder Ctrl-C", aber kein Gate konnte das
sehen — nach einem grünen Lauf hat die `trap` schon aufgeräumt. Dieses Gate lässt den ersten Lauf
absichtlich Reste stehen:

```
$ SMOKE_KEEP=1 bash scripts/smoke/docker_smoke.sh && bash scripts/smoke/docker_smoke.sh
SMOKE_KEEP is set — containers and network are kept for inspection.
...
SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)
...
SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)
rc_w1_chain=0
```

Und mit Zwischenbeleg, dass die Reste real waren:

```
keep_run_rc=0
leftovers_after_keep_run:
  container tex-smoke-neg (Exited (1) Less than a second ago)
  container tex-smoke-run (Exited (0) 5 seconds ago)
  container tex-smoke-stub (Up 8 seconds)
  network tex-smoke-net
SMOKE OK (9 stub calls, exit 0, negative control exit 1 via APIConnectionError)
second_run_rc=0
leftovers_after_second_run:
(none above = clean)
```

Das Pre-Flight-Teardown räumt also drei Container **und** das Netz weg, und der zweite Lauf ist
trotzdem grün. Nebenbei belegt die Zeile `tex-smoke-neg (Exited (1) …)`, dass die Negativ-Kontrolle
wirklich mit **Exit 1** endet.

### 6. Negativ-Kontrolle — Exit-Code und Marker-Zeilen

```
$ docker inspect -f '{{.State.ExitCode}}' tex-smoke-neg
1

$ docker logs tex-smoke-neg 2>&1 | grep -nE 'APIConnectionError|Connection refused|Failed to establish a new connection'
155:ConnectError: [Errno 111] Connection refused
292:ConnectError: [Errno 111] Connection refused
366:│ ❱ 1183 │   │   │   │   raise APIConnectionError(request=request) from err    │
371:APIConnectionError: Connection error.
718:│    743 │   if isinstance(e, openai.APIConnectionError):                      │
```

Alle drei verpflichtenden Assertions greifen: `NEG_RC=1` (≠ 0), `≠ 125` (kein Namenskonflikt — die
Kontrolle läuft im eigenen Container `tex-smoke-neg`), und der Ursachen-Marker ist vorhanden; das
Skript nennt in der Abschlusszeile den zuerst gefundenen (`APIConnectionError`).

### 7. Struktur-Gates

```
$ grep -q -- 'python -I //stub_llm.py' … && grep -q 'tex-smoke-neg' … && \
  grep -Eq 'APIConnectionError|Connection refused' … && grep -q 'State.Running' …
BLOCKER_GATES_PRESENT

$ grep -q 'ThreadingHTTPServer' scripts/smoke/stub_llm.py && \
  grep -q 'network create --internal' scripts/smoke/docker_smoke.sh && \
  grep -q 'bash scripts/smoke/docker_smoke.sh' .github/workflows/ci.yml
GATES_PRESENT

$ for s in "Where state lives" Sidecars Retention Rotation Backup Recovery Concurrency \
           state_maintenance.py docker_smoke.sh; do grep -qF "$s" scripts/STATE_OPERATIONS.md …
SECTIONS_OK
PAPER_RUN_LINKED

$ ! grep -q '^- \[ \]' .planning/MILESTONE.md
DOD_GATE_OK (no open checkbox)

$ test -z "$(git status --porcelain -- scripts .github .planning/MILESTONE.md tests)"
TREE_CLEAN_OK

$ PYTHONPATH=. … scripts/state_maintenance.py prune --help >/dev/null && \
  test "$(grep -v '^#' scripts/state_maintenance.py | grep -c 'quick_check')" -ge 1
PRESENCE_SMOKE_OK
```

### 8. Stub-Call-Log (Beweis der Rollenerkennung)

```
STUB listening on port 8000
STUB call 1 model=stub-quick tools=['get_stock_data', 'get_indicators', 'get_verified_market_snapshot'] -> text
STUB call 2 model=stub-quick tools=[] -> text
STUB call 3 model=stub-quick tools=[] -> text
STUB call 4 model=stub-deep tools=['ResearchPlan'] -> ResearchPlan
STUB call 5 model=stub-quick tools=['TraderProposal'] -> TraderProposal
STUB call 6 model=stub-quick tools=[] -> text
STUB call 7 model=stub-quick tools=[] -> text
STUB call 8 model=stub-quick tools=[] -> text
STUB call 9 model=stub-deep tools=['PortfolioDecision'] -> PortfolioDecision
```

Genau 9 Calls, exakt das von RESEARCH A2/A3 vorhergesagte Muster. Die drei Entscheider bekamen je
genau ein Schema-Tool und wurden mit einer Tool-Call-Antwort bedient; kein Entscheider musste
nachfragen (sonst wären es > 9 Calls gewesen) — der Zähler ist damit gleichzeitig Schema- und
Graph-Form-Sensor.

## Was der Smoke NICHT beweist

**Keine inhaltliche Analysequalität.** Im `--internal`-Netz erreicht kein Datenvendor sein Ziel;
`route_to_vendor` verwandelt jeden Vendor-Fehler in einen Sentinel-String, also liefern **alle
Vendoren `DATA_UNAVAILABLE` / `NO_DATA_AVAILABLE`**. Die Reports sind strukturell vollständig und
inhaltlich leer, das Rating (`Overweight`) kommt aus den fest verdrahteten Stub-Argumenten. Der
Smoke ist ein **Plumbing-Test**: Image-Build, Entrypoint, Pfade/Permissions im Container,
unattended-Gap-Check, die LLM-Client-Kette bis zu einem `openai_compatible`-Endpunkt, das Schreiben
aller Artefakte und die Decision-Log-Zeile. Er ist **kein** Modell-, Vendor- oder Qualitätstest.

Außerdem nicht bewiesen:
- **Der CI-Job ist lokal nachgewiesen, nicht auf `ubuntu-latest` gelaufen.** Das Skript wurde 6×
  lokal grün gefahren (Docker Desktop 29.8.1, Git Bash MINGW64); der Job `docker-smoke` wird erst
  beim nächsten Push/PR zum ersten Mal auf dem Runner laufen. Die bekannten Runner-Risiken sind im
  Skript adressiert (kein Host-Bind-Mount wegen der uid-Falle 1001 vs. 1000, kein `setup-python`,
  `timeout-minutes: 10`), aber ungetestet ist ungetestet.
- **Der `social`-Analyst** bleibt außerhalb des Smokes (RESEARCH, offener Punkt 1: holt
  Reddit/Stocktwits eager vor dem Modellaufruf, ohne Netz ungetestet).
- **Checkpoints im Smoke:** der Lauf nutzt `--checkpoint` nicht, also prüft der Smoke den
  Checkpoint-Pfad nicht. Das tun die Unit-Tests und `state_maintenance.py verify`.

## Die 11 Verhaltenstests aus Task 2 (`tdd="true"`)

RED zuerst beobachtet, vor jeder Implementierungszeile:

```
$ PYTHONPATH=. … -m pytest tests/test_state_maintenance.py -q
E   FileNotFoundError: [Errno 2] No such file or directory:
    'C:\\Users\\admin\\PycharmProjects\\TradingEngineX\\scripts\\state_maintenance.py'
ERROR tests/test_state_maintenance.py - FileNotFoundError: [Errno 2] No such ...
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.70s
rc=2
```

GREEN danach:

```
$ PYTHONPATH=. … -m pytest tests/test_state_maintenance.py -q
18 passed in 0.84s
rc=0
```

| # (Plan) | Verhalten | Testfunktion | Ergebnis |
|---|---|---|---|
| 1 | `verify` gesunde Checkpoint-DB → 0, Ausgabe nennt `AAPL.db` und `ok` | `test_verify_accepts_a_healthy_checkpoint_db` | PASS |
| 2 | `verify` korrupte DB (ab Offset 4096 Müll) → 2, Befund nennt `malformed` | `test_verify_flags_a_corrupt_checkpoint_db` | PASS |
| 3 | `verify` Müll-Header → 2, Befund nennt `file is not a database` | `test_verify_flags_a_file_that_is_not_a_database` | PASS |
| 4 | `verify` DB ohne Tabelle `writes` → 2 | `test_verify_flags_a_db_with_a_missing_table` | PASS |
| 5a | zwei wohlgeformte Einträge mit Abschluss-Separator → 0 | `test_verify_accepts_a_well_formed_decision_log` | PASS |
| 5b | zweite Tag-Zeile auf 3 Felder verkürzt → 2, Meldung nennt `1/2` | `test_verify_flags_an_entry_the_parser_drops_silently` | PASS |
| 5c | intaktes Log **ohne** Abschluss-Separator → 0 | `test_verify_accepts_an_intact_log_without_a_trailing_separator` | PASS |
| 5d | defekter Eintrag **ohne** Abschluss-Separator → 2 | `test_verify_flags_a_broken_entry_without_a_trailing_separator` | PASS |
| 6 | `prune` ohne `--apply` löscht nichts, listet Kandidaten | `test_prune_without_apply_deletes_nothing` | PASS |
| 7 | `prune --apply` nimmt `-wal`/`-shm` mit, lässt den 1-Tag-Satz stehen | `test_prune_apply_removes_old_checkpoints_with_their_sidecars` | PASS |
| 8 | `prune --apply --checkpoint-days 0` lässt das Decision-Log byte-identisch | `test_prune_never_touches_the_decision_log` | PASS |
| 9 | Report-Verzeichnis nach Namens-Stamp löschen, `notareport` bleibt | `test_prune_apply_removes_old_report_directories_by_stamp` | PASS |
| 10 | `backup` packt die Allow-List, kein `*.db`, kein `*.lock` | `test_backup_packs_the_allow_list_and_nothing_else` | PASS |
| 11 | Usage-Fehler → Rückgabe 1 (unbekanntes Kommando, `backup` ohne `--out`, ohne `--state-dir`) | `test_unknown_subcommand_returns_one`, `test_backup_without_out_returns_one`, `test_backup_without_state_dir_returns_one` | PASS |

Drei Tests obendrauf (nicht aus `<behavior>`, als Härtung ergänzt): leeres Decision-Log → ok
(`test_verify_accepts_an_empty_decision_log`), kein Unterkommando → 1
(`test_no_subcommand_returns_one`) — plus im Backup-Test die Gegenprobe, dass eine `secrets.env`
und eine `decision-log.tmp` im State-Verzeichnis **nicht** mitwandern und alle Mitglieder unter
genau einem Top-Level-Verzeichnis liegen.

Test 2 ist belegbar der echte `sqlite3.DatabaseError`-Pfad: das Wort `malformed` kommt
ausschließlich aus dem Exception-Text (`database disk image is malformed`) — die
Decision-Log-Meldung des Werkzeugs vermeidet dieses Wort bewusst, damit die Assertion nicht
versehentlich anderswo erfüllt wird.

Manuelle CLI-Gegenprobe (das Werkzeug läuft auch als Skript, nicht nur über `main()`):

```
$ … scripts/state_maintenance.py verify --cache-dir <demo>/cache --memory-log <demo>/state/decision-log.md
ok: AAPL.db
ok: decision-log.md
verify: 2 object(s) checked, 0 finding(s)
verify_rc=0

$ … scripts/state_maintenance.py prune --cache-dir <demo>/cache --results-dir <demo>/logs
prune (dry run)
  keep AAPL.db (0.0 d old, limit 7 d)
  would delete AAPL_20250101_120000/ (name stamp: 2025-01-01, limit 90 d)
decision log: kept (unlimited retention by operator decision)
nothing was deleted - pass --apply to carry this out
prune_rc=0

$ … scripts/state_maintenance.py backup --out <demo>/out --state-dir <demo>/state --memory-log …
backup: …\tex-state-20261011T135928Z.tar.gz (4 member(s) under tex-state-20261011T135928Z/)
  decision-log.md
  index.md
  runs/2026-10-09/summary.json
  cli/decision-log.md
checkpoints are not in the backup: they are 7-day resume points, not a record
backup_rc=0
```

Die mitangelegte `decision-log.md.lock` tauchte im Archiv nicht auf.

## Abweichungen vom Plan / von RESEARCH.md

### Vom Checker vorgegeben und umgesetzt (W1–H4)

1. **W1 (Pflicht):** zusätzliches Gate
   `SMOKE_KEEP=1 bash … && bash …` aufgenommen und gefahren — Ergebnis wörtlich oben unter Gate 5.
2. **H2 (Pflicht):** `${SMOKE_KEEP:-}` statt `$SMOKE_KEEP`. Unter `set -u` hätte die ungeschützte
   Form jeden Lauf ohne gesetzte Variable gesprengt.
3. **H3 (Pflicht):** `trap teardown INT TERM EXIT` statt nur `EXIT`, und
   `docker start tex-smoke-stub >/dev/null || { docker logs …; exit 1; }` — sonst hätte `set -e`
   bei einem fehlgeschlagenen `docker start` **vor** der Logausgabe abgebrochen.
4. **H4 (Kür, umgesetzt):** die Fehlermeldung des Readiness-Abbruchs behauptet keine Fixrichtung
   mehr. Sie lautet jetzt „…the interpreter argument is expected to arrive as `/stub_llm.py` inside
   the container, received: `<docker inspect .Args>`" und gibt zusätzlich `docker logs` und
   `.Args` aus — bei umgekehrtem Fehlschlag also nicht irreführend.

### Abweichungen von RESEARCH.md (mit Beleg)

5. **Bereits im Plan dokumentiert und bestätigt:** RESEARCH A4 zeigt
   `python -I /stub/stub_llm.py`; in Git Bash schreibt MSYS dieses Argument um. Die vom Plan
   vorgeschriebene Form `python -I //stub_llm.py` läuft hier nachweislich (6 grüne Läufe), der
   Stub-Prozess startet, `{{.State.Running}}` ist `true` und die Readiness-Sonde antwortet sofort.
6. **`files.py`-Zeilennummern in RESEARCH sind falsch** (Rule 1, Beleg beigefügt). RESEARCH B5/B7
   zitieren `files.py:136` für die `<name>.<uuid32>.tmp`-Erzeugung und `files.py:148-200` /
   `:158` für `locked`. Die Datei hat insgesamt **88 Zeilen**; gemessen gilt:
   `replace_file` = `files.py:14-32` mit der Temp-Namensbildung in **`files.py:24`**, `locked` =
   **`files.py:37-88`** (`fcntl.flock` :57, `msvcrt.locking` :74). `scripts/STATE_OPERATIONS.md`
   trägt die **gemessenen** Nummern, nicht die aus RESEARCH.
7. **`trading_graph.py`-Zustandslog:** RESEARCH nennt `527-531`, gemessen liegt
   `log_path = directory / f"full_states_log_{trade_date}.json"` auf **`:530`** — innerhalb der
   Spanne, im Runbook präzisiert.
8. **`daily_paper_run.py`:** der Plan nennt in `<interfaces>` einmal `:218` für
   `memory_log_path = <state_dir>/decision-log.md`; gemessen ist es **`:223`** (so auch an anderer
   Stelle im Plan). `index.md` wird in `:490` geschrieben (von RESEARCH nicht zitiert).

Alle übrigen `[V]`- und `[C]`-Angaben aus RESEARCH haben sich in der Umsetzung bestätigt,
insbesondere: 9 LLM-Calls bei `--analysts market` mit 1/1 Runden, Rollenerkennung über
`request["tools"]`, `ThreadingHTTPServer` als Pflicht, `--internal`-Netz als Offline-Pfad,
`docker cp` statt Bind-Mount, `APIConnectionError` + Exit 1 für die Negativ-Kontrolle,
`PRAGMA quick_check` wirft bei Korruption, `clear_checkpoint` löscht Zeilen statt der Datei.

### Keine Rule-4-Fälle

Es war keine architektonische Entscheidung nötig; kein Paket wurde installiert (stdlib +
vorhandenes `tradingagents`), also griff auch keine Package-Legitimacy-Prüfung. Es gab keine
Auth-Gates — der Smoke braucht per Konstruktion keinen Key.

## Known Stubs

Keine Implementierungs-Stubs. `scripts/smoke/stub_llm.py` **ist** ein absichtliches Test-Double
und das Lieferergebnis von Task 1, kein Platzhalter: er ist vollständig, deterministisch und
dokumentiert. Die festen Antwort-Argumente (`Overweight` / `Buy`) sind der Zweck, nicht eine
unfertige Stelle.

## Threat Flags

Keine neue sicherheitsrelevante Oberfläche außerhalb des Threat-Registers des Plans. Der
HTTP-Listener des Stubs ist ausdrücklich abgedeckt (T-k4s-03): er läuft nur auf einem
`--internal`-Docker-Netz, **ohne jedes `-p`/Port-Publishing**, und Pre-Flight-Teardown plus `trap`
entfernen ihn. `state_maintenance.py` setzt T-k4s-01 (dry-run per Default, Namensmuster,
Symlink-Schutz, aufgelöster Pfad unterhalb des Cache-Verzeichnisses) und T-k4s-02 (Allow-List,
`*.lock`/`*.tmp`/`*.db` ausgeschlossen, `--state-dir` verpflichtend) wie vorgesehen um; Tests 8
und 10 belegen beides.

## Aufräumarbeiten

Alle erzeugten Docker-Objekte sind entfernt: Container `tex-smoke-stub` / `tex-smoke-run` /
`tex-smoke-neg`, Netz `tex-smoke-net`, Image `tex-smoke:local` (`docker rmi` → `Untagged`,
`Deleted`). Das vorbestehende Basis-Image `python:3.13-slim` bleibt stehen. Der Build-Cache wurde
**nicht** geprunt (das hätte Operator-Zustand jenseits dieser Aufgabe getroffen). Der Arbeitsbaum
ist außerhalb von `.planning/quick/` sauber.

## Was der Operator entscheiden muss

1. **`.gitattributes` für `*.sh` (optional, pre-existing).** Das Repo hat keine `.gitattributes`
   und `core.autocrlf=true`. `scripts/smoke/docker_smoke.sh` liegt — wie das vorhandene
   `scripts/graphify.sh` — mit **LF im Index** (geprüft via `git show HEAD:…| od -c`), also läuft
   CI auf `ubuntu-latest` korrekt. Ein *frischer* Clone auf Windows bekäme jedoch CRLF, und
   `bash` stolpert dann über `\r`. Das betrifft `graphify.sh` identisch und ist damit kein neuer
   Zustand. Fix wäre eine Zeile `*.sh text eol=lf` in einer neuen `.gitattributes` — bewusst
   nicht gemacht, weil das über den Task-Umfang hinausgeht.
2. **Erster CI-Lauf des Jobs `docker-smoke` beobachten.** Er ist lokal nachgewiesen, aber noch
   nicht auf einem GitHub-Runner gelaufen. Falls er dort hängt oder scheitert, sind die
   wahrscheinlichen Stellen der Pull von `python:3.13-slim` und der Image-Build (Zeitlimit
   10 min, lokal 49 s bei warmem Cache).
3. **`SMOKE_EXPECTED_CALLS` nach dem nächsten Upstream-Rebase.** Ändert Upstream die Graph-Form,
   ändert sich der Zähler. Die Anpassung ist bewusst eine Einzeiler-Entscheidung
   (`SMOKE_EXPECTED_CALLS=<n>`) — und der Zähler ist genau deshalb ein Sensor, nicht nur eine
   Behauptung.
4. **`decision-log.md.lock` liegt committet auf `paper-log`** (Ursache: `git add -A .` in
   `daily-paper-run.yml:203`). Als „open, cosmetic" im Runbook dokumentiert, per
   Operator-Entscheidung **nicht** gefixt. Fix wäre ein `.gitignore` im State-Dir oder ein Exclude
   — beides hieße den Produktivpfad anfassen.

## Self-Check: PASSED

Dateien (alle vorhanden):
`scripts/smoke/stub_llm.py` (186 Zeilen, Mindestmaß 90) · `scripts/smoke/docker_smoke.sh`
(258 Zeilen, Mindestmaß 110) · `scripts/state_maintenance.py` (415 Zeilen, Mindestmaß 180) ·
`tests/test_state_maintenance.py` (391 Zeilen, Mindestmaß 150) · `scripts/STATE_OPERATIONS.md`
(265 Zeilen, Mindestmaß 90) · `.github/workflows/ci.yml` (Job `docker-smoke`, YAML geparst) ·
`scripts/PAPER_RUN.md` (verlinkt) · `.planning/MILESTONE.md` (keine offene Checkbox).

Commits (alle in `git log` vorhanden): `12ed32d`, `28f4a75`, `e32c6a4`, `86ac1ae` — keiner enthält
eine Dateilöschung (`git diff --diff-filter=D HEAD~1 HEAD` → leer, pro Commit geprüft).
