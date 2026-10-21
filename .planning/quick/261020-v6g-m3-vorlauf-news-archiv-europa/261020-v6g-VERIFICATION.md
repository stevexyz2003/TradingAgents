---
phase: quick-261020-v6g
plan: 01
verified: 2026-10-21
status: passed
commits:
  - 7b8eea5
  - 3b9a869
  - 55f47f4
  - c15d77c
tests: 87 passed
ruff: clean
---

# 261020-v6g — Verifikation: M3-Vorlauf News- und Meldungsarchiv Europa

## Ergebnis

**passed.** Alle 11 must_have-Truths, die Artefakte, die Key-Links und die verbindlichen
Ergänzungen A–E sind im Code umgesetzt und durch Tests abgedeckt. Die Spot-Checks sind ohne
Befund. Offen sind nur Dinge, die laut Plan der Operator erledigt (Scheduler registrieren,
erster `run`, Backfill, ESMA-Seed, AMF-Schema an einem echten Tarball). Dazu kommen zwei
kleine Doku-Hinweise (siehe unten). Keiner davon blockiert.

## Automatische Prüfungen (selbst ausgeführt)

| Prüfung | Ergebnis |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_news_archive_{store,seed,gdelt,amf,cli}.py tests/test_layering.py` | **87 passed** (3,2 s) |
| `ruff check` auf alle 16 neuen .py-Dateien (explizite Liste) | **All checks passed!** |
| `ruff format --check` (Paket + 2 Skripte) | 10 files already formatted |
| `.extractall(` / `extract(` in archive/*, news_archive.py, build_seed_universe.py | 0 Treffer |
| `verify=False` in den neuen Dateien | 0 Treffer |
| `os.kill` | nur im POSIX-Zweig von `pid_alive` (store.py:110) und im Docstring |
| Secrets (`sk-…`, `API_KEY=`) in den neuen Repo-Dateien | 0 Treffer |
| `Get-ScheduledTask -TaskPath '\TradingEngineX\'` | nichts registriert |
| Archivdaten im Repo (`git ls-files` auf .jsonl / index.sqlite / amf-gz_ / heartbeat.json) | 0 Treffer |

## Commits und Done-Gates (Ergänzung C: nur der eigene Commit)

| Commit | Dateien | Bewertung |
|---|---|---|
| 7b8eea5 (Task 1) | 7: Paket-Init ×2, models, store, status, http, test_news_archive_store | = Erlaubt-Liste Task 1 |
| 3b9a869 (Task 2) | 8: gdelt, amf, seed, provisional CSV, build_seed_universe, 3 Tests | = Erlaubt-Liste Task 2 |
| 55f47f4 (Task 3) | 4: news_archive.py, news_archive_task.ps1, NEWS_ARCHIVE.md, test_news_archive_cli | = Erlaubt-Liste Task 3 |
| c15d77c (Orchestrator) | 1: http.py, Connect-Timeout `(10, 60)` → `(30, 60)` mit Begründungskommentar | sauber, minimaler Diff |

Arbeitsbaum: nur `?? .planning/debug/` (fremd) und das noch nicht committete SUMMARY.

## must_haves (Truths)

| # | Truth | Status | Beleg |
|---|---|---|---|
| 1 | `run` schreibt GDELT + AMF append-only als JSONL je Quelle/UTC-Tag unter `%LOCALAPPDATA%\TradingEngineX\archive\`, nie ins Repo | ✓ | `store.archive_base`, `ArchiveStore.day_path` = `<source>/YYYY/MM/YYYY-MM-DD.jsonl`, Append-Modus + fsync; Test `test_run_collects_three_days_then_nothing`; keine Archivdatei im Repo |
| 2 | Zweiter Lauf erzeugt keine Dubletten (SQLite UNIQUE record_hash) | ✓ | `records.record_hash PRIMARY KEY`, `INSERT OR IGNORE`, Zeile nur bei rowcount 1; `test_append_dedupes_across_store_instances`, `test_collect_day_ok_and_idempotent` |
| 3 | GDELT-dedupe_key = `canonical_url\|issuer_isin`, Fallback `issuer_query`; story_key gruppiert, ohne zu löschen | ✓ | gdelt.py:235 `f"{canonical_url(url)}\|{isin or issuer_query}"`; `test_same_url_for_two_issuers_gives_two_records` (2 Records, gleicher story_key); Index auf story_key, kein Delete |
| 4 | Fehlende Statusdatei = `missing`; `status --days 14` mit ok/partial/missing, Heartbeat-Alter ab letztem finished_at, Exit 1 bzw. 2 | ✓ | `read_day_status` → `missing` + `no status file`; `heartbeat_age` nimmt max(last_finished_at, finished_at); `cmd_status` prüft 2 vor 1; Tests `test_heartbeat_age`, `test_status_without_finished_run_is_2`, `test_failed_day_is_reported_and_caught_up` |
| 5 | Catch-up: max. 3 Versuche je Tag, 2 Plätze für die neuesten Tage, 89-Tage-Fenster, ohne `backfilled`; `--max-runtime` endet sauber | ✓ | `days_needing_work` (Reservierung + Versuchslimit), `collect_day(backfilled=False)`, Deadline → `partial`/`max_runtime` mit `count_attempt=False`; `test_days_needing_work_window_attempts_and_reservation`, `test_max_runtime_ends_cleanly` (Lock weg, Logdatei löschbar) |
| 6 | GDELT-Backfill in Wochenfenstern auf fixem Anker, älteste zuerst, exklusiv bis archive_start, `backfilled=true`, setzt an späterem Tag fort | ✓ | Anker einmalig im Checkpoint; Fenster `min(ws+step, archive_start)`, `q_end = we 00:00 − 1 s`; Resume-Test ruft mit `today + 1 Tag`, prüft gleichen Anker und Clip auf `today+1−89` (`test_backfill_resumes_on_fixed_anchor_and_clips`); `expired`-Test vorhanden |
| 7 | Status/Heartbeat/Checkpoints atomar; zweiter Lauf scheitert am Lockfile | ✓ | `atomic_write_json` (tmp + fsync + os.replace, PermissionError-Retry); `RunLock` mit O_EXCL; Exit 3 in `test_run_with_held_lock_is_3`; Lock-Tests (siehe B) |
| 8 | HTTP über requests mit CA-Bundle aus REPO/.env (absolut); gesetzter, fehlender Pfad bricht laut ab | ✓ | `load_dotenv(REPO / ".env", override=False)`; `resolve_ca_bundle` → `CaBundleMissing` → Exit 4 (`test_missing_ca_bundle_is_4`) |
| 9 | `smoke` schreibt nur unter `archive/smoke/` | ✓ | `ArchiveStore(ctx.base / "smoke")`, kein Status/Heartbeat/meta; Test prüft Abwesenheit von index.sqlite, gdelt, amf, status, heartbeat.json, meta.json in der Basis. **Auf der Platte bestätigt:** unter `%LOCALAPPDATA%\TradingEngineX\archive\` liegen nur `smoke\` und `logs\` |
| 10 | Scheduler-Skript registriert nur mit `-Register`, im Task nicht registriert | ✓ | `Register-ScheduledTask` nur in `if ($Register)`; Test `test_scheduler_script_registers_only_with_switch`; `Get-ScheduledTask` liefert nichts |
| 11 | Tests ohne Netz und synthetisch; Smoke ehrlich protokolliert | ✓ | conftest `_no_network`, alle Fixtures im Test gebaut; der erste Smoke-Lauf (Timeout) steht wörtlich im SUMMARY, der zweite Lauf siehe unten |

## Verbindliche Ergänzungen A–E

| | Vorgabe | Status | Beleg |
|---|---|---|---|
| A | Ein Versuch zählt höchstens einmal je UTC-Tag; kein RestartCount | ✓ | `write_day_status` mit `last_attempt_date`; `test_attempts_count_once_per_utc_day`, `test_two_failed_runs_on_the_same_day_are_one_attempt`, `test_broken_day_gives_up_after_three_days_of_attempts`; PS1 ohne `RestartCount`/`RestartInterval` |
| B | Lock-Übernahme nach 6 h auch bei lebender PID; Access denied = lebt | ✓ | `RunLock._is_held`: `age >= takeover_after` → frei; `pid_alive`: `ERROR_ACCESS_DENIED` → True; `test_live_pid_with_timestamp_older_than_six_hours_is_taken_over` |
| C | Done-Gates prüfen nur den eigenen Commit | ✓ | siehe Commit-Tabelle |
| D | AMF-Backfill endet vor archive_start | ✓ | `cmd_backfill`: `end = min(start, today)`, Tage `[since, end)`; `test_amf_backfill_stops_before_archive_start` |
| E | `status` listet aufgegebene Tage mit Reset-Anleitung | ✓ | `given_up_days` + Ausgabe „GAVE UP (aufgegeben …)“ mit `reset: delete <Statusdatei>`; `test_given_up_days_lists_exhausted_days`; Handbuch Z. 114–115 |

## Spot-Checks

- **Dedupe-Schlüssel GDELT:** `canonical_url|issuer` (ISIN bei Titeltreffer, sonst `issuer.key`), Test prüft beide Varianten (`…|DE0007164600`, `…|name:gamma plc`). ✓
- **Smoke-Isolation:** im Code, im Test und auf der Platte bestätigt. Einzige Datei außerhalb von `smoke\` ist `logs\news_archive.log`; das ist kein Produktions-Datenbestand und laut Plan erlaubt. ✓
- **Backfill-Anker und Fortsetzung mit today+1:** Anker = `today − 89` beim ersten Aufruf, danach fix. Das älteste offene Fenster wird auf den neuen Horizont geclippt, ein ganz herausgefallenes Fenster wird `expired`. ✓
- **tar/XML-Limits:** MAX_TARBALL_BYTES 200 MiB (vor dem Parsen und beim Download), MAX_MEMBERS 5000, MAX_MEMBER_BYTES 50 MiB (zusätzlich `read(MAX+1)`), MAX_TOTAL_BYTES 500 MiB. Nur `extractfile` in den Speicher, kein `.extractall(`. Erst strikte UTF-8-Dekodierung, dann Prüfung auf DOCTYPE/ENTITY. Der Dateiname des Rohdownloads stammt aus der Regex `amf-gz_\d{8}_\d{4}.tar.gz`, also ist keine Path Traversal möglich. ✓
- **Keine GDELT-Volltexte:** Records enthalten nur URL, Titel, seendate, Domain, Sprache, Land und Zuordnungsfelder; `extra` ist leer. In der echten Smoke-JSONL: 98 Zeilen, längster Titel 253 Zeichen. ✓
- **AMF-Rohdaten außerhalb des Repos:** `base/raw/amf/<name>` unter LOCALAPPDATA; im Repo keine Archivdatei. ✓
- **Kein `verify=False`.** ✓
- **Scheduler:** nur mit `-Register`; derzeit nicht registriert. ✓
- **Provisorischer Seed:** 62 Zeilen; DE 9, FR 9, NL 9, CH 9, UK 10, IT 8, ES 8; jede Zeile hat `source=hand-curated-provisional`; der Header beginnt mit `# PROVISIONAL hand-curated seed (quick 261020-v6g)`; ISIN-Prüfung und Präfix=Land werden getestet. ✓
- **Secrets:** keine. ✓

## Smoke (Netz)

- Der erste Lauf des Executors: GDELT mit Connect-Timeout (10 s), DILA ok (16 631 Tarballs). Das steht wörtlich im SUMMARY.
- Der Orchestrator hat einen TLS-Handshake von ~10,2 s gemessen (AVG). c15d77c setzt den Connect-Timeout auf 30 s.
- Der zweite Smoke-Lauf endete laut Orchestrator mit Exit 0: GDELT 98 Artikel für 2026-10-20, AMF-Listing 16 631 Dateien.
- **Auf der Platte gegengeprüft:** `smoke\gdelt\2026\10\2026-10-20.jsonl` hat 98 Zeilen, geschrieben am 21.10.2026 um 08:07. Das passt zu den Angaben.

## Hinweise (nicht blockierend)

1. **SUMMARY ist veraltet:** Frontmatter `smoke: gdelt_timeout_amf_ok`, Abschnitt „GDELT … noch nicht grün“ und Follow-up 1 („Connect-Timeout erhöhen“) spiegeln weder c15d77c noch den grünen zweiten Smoke-Lauf. Der Orchestrator sollte das SUMMARY vor dem Commit nachziehen.
2. **Handbuch:** `scripts/NEWS_ARCHIVE.md` erwähnt den 30-s-Connect-Timeout bzw. den ~10-s-AVG-Handshake nicht. Ein Satz im Abschnitt CA-Bundle/AVG würde helfen.
3. **AMF-Download-Größe:** `requests` lädt den Body vollständig (`response.content`), bevor die 200-MiB-Grenze greift. Es wird nicht gestreamt. Bei den echten DILA-Tarballs ist das unkritisch, als Härtung wäre `stream=True` mit Abbruch nach Content-Length denkbar.
4. **Bereits im SUMMARY offengelegt:** AMF-Fehlversuche je Datei zählen je Lauf, nicht je Kalendertag (anders als Ergänzung A für Tage). Mehrere Läufe am selben Tag können eine Datei daher schneller nach `gave_up` bringen. Ein Reset über `checkpoints\amf_seen.json` ist dokumentiert.

## Operator-Schritte (laut Plan außerhalb des Scopes)

Scheduler mit `-Register` erst nach OK, danach der erste `run --catch-up --start <Datum>`, der GDELT-Backfill (zeitkritisch, jeder Tag Verzug macht ein Fenster `expired`), der ESMA-Seed, die Prüfung des AMF-Schemas und des Encodings an einem echten Tarball (A5) und die Lizenzentscheidung EQS/Investegate.
