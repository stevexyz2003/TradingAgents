---
phase: quick-261020-v6g
plan: 01
status: complete
requirements:
  - M3-VORLAUF-ARCHIV
commits:
  - 7b8eea5 feat(archive): add append-only news archive core (store, dedupe, status, http)
  - 3b9a869 feat(archive): add GDELT and AMF/DILA collectors and provisional seed universe
  - 55f47f4 feat(archive): add news archive CLI, scheduler script and handbook
  - c15d77c fix(archive): allow 30 s to connect so the AVG-slowed TLS handshake completes (Orchestrator)
smoke: gdelt_ok_amf_ok (2. Lauf nach c15d77c; 1. Lauf gdelt_timeout_amf_ok)
---

# 261020-v6g — M3-Vorlauf: News- und Meldungsarchiv Europa

## Ergebnis

Das Archiv ist gebaut und ohne Netz getestet: Paket `tradingagents/forecast/archive/`
(Modelle, Store mit SQLite-Dedupe, Status/Heartbeat/Lücken, HTTP mit CA-Bundle, GDELT- und
AMF/DILA-Collector, Seed), CLI `scripts/news_archive.py` (run/backfill/status/smoke),
Seed-Builder `scripts/build_seed_universe.py`, provisorischer Seed (62 Emittenten),
Scheduler-Skript `scripts/news_archive_task.ps1` (nicht registriert) und Handbuch
`scripts/NEWS_ARCHIVE.md` (deutsch).

Der erste echte Smoke-Lauf brachte **DILA ok, GDELT mit Timeout** (siehe unten).

**Nachtrag Orchestrator (2026-10-21):** Die Ursache für den Timeout ist gemessen. Der TLS-Handshake zu `api.gdeltproject.org` dauert an diesem Rechner konstant etwa 10,2 s, weil die AVG-HTTPS-Prüfung dazwischenhängt. Mit `curl.exe` ergab sich `connect=0.14 s`, `appconnect=10.21 s`. Das alte Connect-Limit von 10 s brach deshalb jeden Aufruf ab, und die Meldung `read timeout=10` stammt aus dem Handshake. Fix `c15d77c` erhöht das Connect-Limit auf 30 s; die Session hält die Verbindung offen, der Handshake fällt also nur einmal an. GDELT antwortete beim Messen zusätzlich mit HTTP 429 („one every 5 seconds“); das fängt der vorhandene Retry mit Backoff ab.

**Zweiter Smoke-Lauf nach dem Fix: Exit 0.**
- **GDELT** für 2026-10-20 (SAP und Siemens): `http_ok: true`, 98 Artikel, 98 neu, 0 abgelehnt, 0 abgeschnitten.
- **AMF-Listing:** `listing_ok: true`, 16 631 Dateien, die neueste ist `amf-gz_20102026_2300.tar.gz`.

Geschrieben wurde nur nach `archive\smoke\`.

## Commits

| Task | START | Commit | Dateien |
|---|---|---|---|
| 1 Archivkern | 848feb0 | `7b8eea5` | 7 (Paket-Init ×2, models, store, status, http, test_news_archive_store) |
| 2 Quellen + Seed | 7b8eea5 | `3b9a869` | 8 (gdelt, amf, seed, provisional CSV, build_seed_universe, 3 Tests) |
| 3 CLI/Scheduler/Handbuch | 3b9a869 | `55f47f4` | 4 (news_archive.py, news_archive_task.ps1, NEWS_ARCHIVE.md, test_news_archive_cli) |

Done-Gates: `git show --name-only --format= <SHA>` war für jeden der drei Commits genau die
Erlaubt-Liste des Tasks. `git diff --name-only 848feb0..HEAD` = exakt die 19 Dateien aus
`files_modified`. Fremdstand vor Task 1 und nach Task 3 identisch (`?? .planning/debug/`);
in der Zwischenzeit kamen keine Fremd-Commits. Kein Regex-Fix-Commit nötig.

## Tests

`pytest tests/test_news_archive_store.py tests/test_news_archive_seed.py
tests/test_news_archive_gdelt.py tests/test_news_archive_amf.py tests/test_news_archive_cli.py
tests/test_layering.py -q` → **87 passed** (3,0 s).

| Datei | Tests |
|---|---|
| test_news_archive_store.py | 35 |
| test_news_archive_seed.py | 9 |
| test_news_archive_gdelt.py | 18 |
| test_news_archive_amf.py | 13 |
| test_news_archive_cli.py | 11 |
| test_layering.py | 1 |

Alle ohne Netz (conftest `_no_network`), nur synthetische Fixtures, LOCALAPPDATA isoliert.

## Ruff

`ruff check` auf alle 16 neuen .py-Dateien (explizite Liste): **All checks passed!**
Zusätzlich `ruff format` auf die neuen Dateien angewandt. `.extractall(`-Gate auf amf.py:
Exit 0. Review-grep: kein `verify=False`; `os.kill` nur im POSIX-Zweig von `pid_alive`.
tzdata-Check: `zoneinfo.ZoneInfo('Europe/Paris')` funktioniert.

## Smoke-Lauf (genau einmal, echtes Netz)

Archivordner existierte vorher nicht. Befehl:
`.\.venv\Scripts\python.exe scripts\news_archive.py smoke --issuers 2` → **Exit 1**

Ausgabe wörtlich:

```
2026-10-21 08:02:35,004 WARNING tradingagents.forecast.archive.gdelt: GDELT call failed for ("SAP SE" OR "Siemens AG" OR "Siemens"): timeout: HTTPSConnectionPool(host='api.gdeltproject.org', port=443): Read timed out. (read timeout=10)
{
  "gdelt": {
    "query": "(\"SAP SE\" OR \"Siemens AG\" OR \"Siemens\")",
    "day": "2026-10-20",
    "http_ok": false,
    "articles": 0,
    "new": 0,
    "duplicate": 0,
    "rejected": 0,
    "truncated": 0,
    "error": "timeout: HTTPSConnectionPool(host='api.gdeltproject.org', port=443): Read timed out. (read timeout=10)"
  },
  "amf": {
    "listing_ok": true,
    "files": 16631,
    "newest": "amf-gz_20102026_2300.tar.gz",
    "newest_delivered_at": "2026-10-20T21:00:00Z",
    "error": null
  }
}
SMOKE EXIT: 1
```

Bewertung:
- **DILA:** Listing per HTTPS mit dem CA-Bundle aus `.env` erreichbar; 16 631 Tarballs
  erkannt. Das Dateinamensformat `amf-gz_DDMMYYYY_HHMM` ist bestätigt (20.10.2026 23:00 Paris
  = 21:00Z). Keine Regex-Anpassung nötig.
- **GDELT:** 3 Versuche (mit Backoff 5 s/10 s), jeder mit Timeout. „read timeout=10“ ist der
  Connect-Wert des Tupels `(10, 60)`; urllib3 meldet einen hängenden TLS-Handshake so. Es gab
  keine Zertifikatsfehlermeldung (kein SSLError), sondern ein Timeout beim Verbindungsaufbau.
  Ursache offen: GDELT-Server langsam/überlastet oder AVG-Interception verzögert den Handshake
  (siehe `scripts/PAPER_RUN.md`). Nicht wiederholt (laut Plan).
- Smoke schrieb nur `archive\smoke\index.sqlite` und `archive\logs\news_archive.log`; kein
  Produktionsindex, keine JSONL, kein `status\`, kein `meta.json`, kein `heartbeat.json`.

Danach informativ `status --days 3` → **Exit 2** (erwartet, noch kein `run`): „archive_start:
not set“, „heartbeat: none“, „never finished“.

Scheduler: `Get-ScheduledTask -TaskPath "\TradingEngineX\"` liefert nichts → nicht
registriert. Das PS1 lief einmal ohne `-Register` (nur Anzeige, „not registered; rerun with
-Register after operator approval“).

## Abweichungen vom Plan

Verbindliche Ergänzungen A–E aus dem finalen Plan-Check sind umgesetzt:

- **A Versuchszählung:** `DayStatus.last_attempt_date` (UTC-Datum); `attempts` steigt höchstens
  einmal je UTC-Kalendertag (`write_day_status(..., now=...)`). Der Plan-Fall „zweimal schreiben
  → attempts 2“ ist deshalb ersetzt durch: zwei Schreibvorgänge am selben Tag = 1, am Folgetag
  = 2. Tests: `test_attempts_count_once_per_utc_day`,
  `test_two_failed_runs_on_the_same_day_are_one_attempt`, CLI
  `test_broken_day_gives_up_after_three_days_of_attempts` (zwei Läufe am selben Tag = 1 Versuch,
  nach 3 Kalendertagen nicht mehr angefasst). `RestartCount`/`RestartInterval` aus dem PS1
  entfernt (Test prüft deren Abwesenheit).
- **B Lock:** `RunLock(takeover_after=6 h)`: ältere Zeitstempel werden auch bei lebender PID
  übernommen; `pid_alive` wertet `ERROR_ACCESS_DENIED` von `OpenProcess` als lebend. Test
  `test_live_pid_with_timestamp_older_than_six_hours_is_taken_over`.
- **C Done-Gates:** nur der eigene Commit geprüft (siehe oben); fremde Pfade nur berichtet.
- **D AMF-Backfill:** `--since` wird auf `[since, archive_start)` geclippt; Test
  `test_amf_backfill_stops_before_archive_start`.
- **E Aufgegebene Tage:** `status` listet nicht-ok-Tage mit `attempts >= 3` unter „GAVE UP
  (aufgegeben …)“ mit `reset: delete <Statusdatei>`; das Handbuch wiederholt das
  (`status.given_up_days`, `status.status_file`).

Weitere kleine Abweichungen:
- Collector-Funktionen (`fetch_window`, `fetch_canary`, `collect_day`, `backfill`,
  `amf.collect`) und `main()` haben zusätzlich einen `sleep`-Parameter (Backoff in Tests ohne
  echtes Warten); `amf.collect` zusätzlich `limiter`; `main()` zusätzlich `pid_alive`
  (Test d). `now` wird in den Collectors als Callable oder datetime akzeptiert.
- `amf.collect` hat keinen `deadline`-Parameter (Task-2-Vertrag). Die CLI prüft die Deadline vor
  der AMF-Phase und schreibt bei Ablauf `partial`/`max_runtime` ohne Versuchszählung.
- `environ` in `main()` steuert nur das CA-Bundle; die Archivbasis kommt immer aus dem
  Prozess-LOCALAPPDATA (sonst läge das Archiv in Tests mit `environ={}` unter `~`).
- `backfill --source gdelt` endet mit Exit 0, wenn kein Fenster mehr offen ist, sonst 1 (Plan
  nannte keine Codes); ohne archive_start Exit 4.
- `seed.py` bekam zusätzlich `dump_seed` (CSV-Schreiber für den Builder) und `isin_country`.
- AMF: Die Fehlversuche einer Datei zählen je Lauf (nicht je Kalendertag); bei mehreren Läufen
  am selben Tag kann eine Datei also schneller in `gave_up` landen als der Tag sein
  Versuchslimit erreicht. Zurücksetzen über `checkpoints\amf_seen.json` (im Handbuch).

## Follow-ups (Operator)

1. ~~GDELT-Erreichbarkeit klären~~ **Erledigt** mit `c15d77c`; der zweite Smoke-Lauf ist grün (siehe Ergebnis).
2. **Scheduler registrieren** nach Operator-OK (exakter Befehl, im Repo-Wurzelverzeichnis):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\news_archive_task.ps1 -Register
   ```

   Prüfen: `schtasks /query /tn "\TradingEngineX\NewsArchive" /xml`.
3. **Erster Lauf:** `.\.venv\Scripts\python.exe scripts\news_archive.py run --catch-up --start <YYYY-MM-DD>`.
4. **GDELT-Backfill** starten (`backfill --source gdelt`, ≈ 78 min bei 60 Emittenten; in Etappen
   mit `--max-runtime`). Jeder Tag Verzug lässt ein Wochenfenster `expired` werden.
5. **ESMA-Seed bauen:** FITRS FULECR + FIRDS FULINS_E laut ESMA65-8-5240 laden, Feldnamen
   (A3) prüfen, `scripts/build_seed_universe.py` ausführen; UK-Zeilen per `--manual`.
   ESMA-abgeleitete Datei erst nach Prüfung und mit Quellenvermerk ins Repo.
6. **AMF-Schema und Encoding an einem echten Tarball verifizieren (A5):** Tag-Kandidatenlisten
   in `amf.py` prüfen. Ist das XML nicht UTF-8, scheitert jede Datei und landet nach 3
   Versuchen in `gave_up`.
7. **Lizenzentscheidung EQS / Investegate:** EQS-News (TDM-Verbot → Lizenzanfrage EQS
   News-Sales), Investegate (kein RSS, Privatanleger-Klausel → streichen oder LSEG-RNS-Lizenz).
