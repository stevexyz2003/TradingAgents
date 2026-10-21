# News- und Meldungsarchiv Europa (M3-Vorlauf)

Betriebshandbuch für `scripts/news_archive.py`. Quick-Task 261020-v6g.

## Zweck

M3 braucht prospektive LLM-Evidenz: Nachrichten und Pflichtmeldungen, die zum
Entscheidungszeitpunkt tatsächlich vorlagen. GDELT reicht nur etwa 3 Monate zurück, deshalb
läuft das Archiv schon jetzt, vor M3. Jeder Tag ohne Archiv fehlt später als Evidenz.

Leitregel aus den PITFALLS: **Lücke ≠ keine News.** Deshalb hat jeder Tag je Quelle einen
Qualitätsstatus (`ok` / `partial` / `missing`), und ein Tag ohne Statusdatei gilt als
`missing`, nie als „leer“.

## Quellen und Lizenzen

| Quelle | Inhalt | Lizenz / Regel |
|---|---|---|
| GDELT DOC 2.0 (`api.gdeltproject.org/api/v2/doc/doc`) | nur Metadaten: URL, Titel, seendate, Domain, Sprache, Land | Quellenangabe „GDELT Project“. Keine Artikel-Volltexte. |
| AMF via DILA Opendata (`echanges.dila.gouv.fr/OPENDATA/AMF/`) | Pflichtmeldungen (info-financière), XML-Metadaten + Inhaltsdatei | Licence Ouverte 2.0, Volltext erlaubt. **Rohdaten nur lokal**: Directors' Dealings enthalten Personendaten (DSGVO). Nie in den öffentlichen Fork, nie auf einen public Branch. |

### Ausgeschlossen (Follow-ups für eine Lizenzentscheidung des Operators)

- **EQS-News:** Die Legal Notice verbietet Text- und Data-Mining. Weg: Lizenzanfrage bei
  EQS News-Sales.
- **Investegate:** kein RSS, Privatanleger-Klausel. Entweder streichen oder eine
  LSEG-RNS-Lizenz prüfen.
- **IR-Seiten, Euronext, Unternehmensregister, BaFin** gehören nach P1, nicht in diesen
  Vorlauf.

## Ablage

Alles liegt unter `%LOCALAPPDATA%\TradingEngineX\archive\`, nie im Repo:

```
archive\
  meta.json                        archive_start (einmalig gesetzt)
  heartbeat.json                   letzter Lauf (started/finished/last_finished_at, exit_code)
  index.sqlite                     Dedupe-Index (record_hash UNIQUE, story_key indiziert)
  run.lock                         Lockfile (PID + Zeitstempel)
  gdelt\YYYY\MM\YYYY-MM-DD.jsonl   append-only, eine Zeile je Record
  amf\YYYY\MM\YYYY-MM-DD.jsonl
  raw\amf\amf-gz_….tar.gz          Original-Lieferungen (nur lokal!)
  status\gdelt\YYYY-MM-DD.json     Tagesstatus je Quelle
  status\amf\YYYY-MM-DD.json
  checkpoints\backfill_gdelt.json  Backfill-Fortschritt (fester Anker)
  checkpoints\amf_seen.json        verarbeitete / fehlgeschlagene / aufgegebene Tarballs
  logs\news_archive.log            rotierend, 5 MB × 5
  seed_universe.csv                optional: gebauter Seed (siehe unten)
  smoke\                           getrennter Bereich des Smoke-Laufs (eigener Index + JSONL)
```

Status, Heartbeat und Checkpoints werden atomar geschrieben (tmp + fsync + `os.replace`).

### Record-Felder

`source, url, title, day (UTC-Datum = Datei), published_at, published_at_kind
(crawl|source|delivery), published_at_raw, first_seen_ts, issuer_query, issuer_isin,
match_alias, match_confidence (title_alias|query_only), language, country, domain,
backfilled, run_id, collector_version, dedupe_key, extra, record_hash, story_key`.

- GDELT: `published_at` ist die **Crawl-Zeit** (`seendate`, Annahme A2), nicht die
  Veröffentlichungszeit; daher `published_at_kind = crawl`.
- AMF: `source`, wenn im XML ein Datum gefunden wird, sonst `delivery` (Lieferzeit aus dem
  Dateinamen, Paris-Ortszeit → UTC).

### Dedupe

- `record_hash = sha256(source|dedupe_key)`, UNIQUE in `index.sqlite`. Re-Runs legen keine
  Dubletten an.
- GDELT: `dedupe_key = kanonische URL | ISIN` (Fallback: Seed-Schlüssel). Derselbe Artikel
  kann also **je Emittent einmal** vorkommen: Ein Artikel über zwei Emittenten ist Evidenz
  für beide.
- `story_key` (normalisierter Titel) gruppiert dieselbe Geschichte emittentenübergreifend.
  Cluster werden nur indiziert, nie gelöscht.
- AMF: `amf:<Dokument-ID>`, sonst `dila-amf:<tarball>/<member>`.
- Bricht ein Lauf zwischen Zeilenschreiben und Index-Commit ab, kann eine Zeile doppelt in
  der JSONL stehen; Leser deduplizieren nach `record_hash` (bewusst: keine Zeile geht
  verloren).

## Statuslogik

**GDELT je UTC-Tag:**

- Zuerst eine Canary-Abfrage (`"European Central Bank"`, 1 Call, maxrecords 10). Liefert sie
  0 Treffer, ist der Tag höchstens `partial`, weil dann nicht unterscheidbar ist, ob GDELT
  geliefert hat.
- Dann eine Query je Emittent. `missing`, wenn alle Queries fehlschlagen; `partial`, wenn
  (fehlgeschlagen + abgelehnt) / Queries > 10 %; sonst `ok`.
- **`truncated`**: Zahl der 1-h-Fenster, die trotz Halbierung noch 250 Treffer (das
  API-Maximum) lieferten. Dort fehlen Artikel. Der Tag bleibt trotzdem `ok`, solange die
  Fehlerquote stimmt; `truncated > 0` steht im Status und muss bei der Auswertung beachtet
  werden.

**AMF je UTC-Tag:**

- Listing-Fehler → alle angefragten Tage `missing`.
- Listing ohne einen einzigen erkannten Dateinamen → `missing` mit `listing_no_matches`
  (Hinweis auf geänderte Dateinamen).
- Keine Lieferung in den letzten 5 Werktagen → `partial` mit `listing_stale`.
- Eine unparsebare Datei wird nicht als gesehen markiert und beim nächsten Lauf erneut
  versucht, nach 3 Fehlversuchen steht sie unter `gave_up` (Tag bleibt `partial`).
  Zurücksetzen: Namen aus `gave_up`/`failed` in `checkpoints\amf_seen.json` entfernen.

**Fehlende Statusdatei = `missing`.**

### Versuchslimit und Zurücksetzen

- Ein Tag wird höchstens **3-mal** versucht. Ein Versuch zählt höchstens **einmal je
  UTC-Kalendertag**: Mehrere Läufe am selben Tag (z. B. manuell nachgestartet) verbrauchen
  keinen weiteren Versuch.
- Ein Lauf, der an `--max-runtime` endet, zählt keinen Versuch.
- Tage mit `attempts >= 3`, die nicht `ok` sind, gelten als **aufgegeben**: Der Catch-up
  fasst sie nicht mehr an. `status` listet sie unter „GAVE UP (aufgegeben)“ samt Pfad.
- **Zurücksetzen:** die Statusdatei des Tages löschen, z. B.
  `Remove-Item "$env:LOCALAPPDATA\TradingEngineX\archive\status\gdelt\2026-10-19.json"`.
  Der nächste `run` versucht den Tag dann wieder (sofern er im 89-Tage-Fenster liegt).

## Befehle

Alle Befehle aus dem Repo-Wurzelverzeichnis:

```powershell
.\.venv\Scripts\python.exe scripts\news_archive.py run --catch-up [--start YYYY-MM-DD] [--sources gdelt,amf] [--max-days 3] [--max-runtime 150] [--seed PATH] [--limit-issuers N]
.\.venv\Scripts\python.exe scripts\news_archive.py status --days 14
.\.venv\Scripts\python.exe scripts\news_archive.py backfill --source gdelt [--max-calls N] [--max-runtime 150]
.\.venv\Scripts\python.exe scripts\news_archive.py backfill --source amf --since YYYY-MM-DD
.\.venv\Scripts\python.exe scripts\news_archive.py smoke --issuers 2
```

### `run`

Catch-up ist immer aktiv. Ablauf: Lock → `archive_start` setzen (beim ersten Lauf `--start`
oder gestern UTC) → Heartbeat „started“ → je Quelle die offenen Tage → Heartbeat „finished“.
Eine abgestürzte Quelle schreibt für ihre Tage `missing`, die andere läuft weiter.

| Exit | Bedeutung |
|---|---|
| 0 | alle bearbeiteten Tage ok |
| 1 | mindestens ein Tag `partial` |
| 2 | mindestens ein Tag `missing` |
| 3 | ein anderer Lauf hält das Lock |
| 4 | Konfigurationsfehler (CA-Bundle fehlt) |

Lock: Gilt als gehalten, solange die PID lebt oder der Zeitstempel jünger als 30 min ist.
Ist der Zeitstempel älter als 6 h, wird das Lock in jedem Fall übernommen (PID-Wiederverwendung,
hängender Prozess). Ein laufender Lauf erneuert den Zeitstempel je Query, Fenster und Datei.

### `status`

Tabelle Tag × Quelle (Status, attempts, neue/doppelte Records, truncated, Canary-Treffer bzw.
Dateien), archive_start, letzter Heartbeat, Heartbeat-Alter (ab dem letzten fertigen Lauf, ein
hängender Lauf maskiert also nichts), Backfill-Fortschritt, aufgegebene Tage.

| Exit | Bedingung (in dieser Reihenfolge) |
|---|---|
| 2 | kein fertiger Lauf oder letzter `finished_at` älter als 36 h |
| 1 | mindestens ein Tag `partial`/`missing` |
| 0 | sonst |

### `backfill`

- `--source gdelt`: manuell; siehe unten. Exit 0, wenn kein Fenster mehr offen ist, sonst 1;
  4 ohne archive_start (erst `run`, ggf. mit `--start`).
- `--source amf --since D`: holt die Tage `[D, archive_start)` mit `backfilled=true`. Tage ab
  archive_start gehören dem täglichen `run` und werden abgeschnitten.

### `smoke`

Eine GDELT-Query (Aliase der ersten N Seed-Emittenten in einer OR-Gruppe, gestern UTC) plus
ein DILA-Listing. Schreibt nur nach `archive\smoke\` (eigener Index), nie in Produktionsindex,
Produktions-JSONL, Status, meta.json oder heartbeat.json. Exit 0 nur, wenn beides ok ist.

## Laufzeitrechnung

GDELT verlangt etwa 1 Request je 5 s (Annahme A1); der Collector hält 6 s Abstand.

- Je GDELT-Tag: (Emittenten + 1 Canary) × 6 s. Bei 60 Emittenten ≈ 6,1 min/Tag; mit
  `--max-days 3` ≈ 18 min, plus Retries und Splits.
- Bei 400 Emittenten ≈ 40 min/Tag, also 3 Tage ≈ 2 h.
- Deshalb `--max-runtime 150` (Minuten) unter dem ExecutionTimeLimit des Tasks von 3 h. Bei
  Ablauf endet der Lauf sauber: laufender Tag `partial` mit `max_runtime` (ohne
  Versuchszählung), Heartbeat geschrieben, Lock freigegeben.

### Catch-up

Höchstens `--max-days 3` Tage je Lauf, davon 2 Plätze für die neuesten offenen Tage (ein langer
Rückstand verdrängt nie den aktuellen Tag), der Rest für die ältesten. Nur Tage im
GDELT-Fenster von 89 Tagen und nicht vor archive_start. Ein verpasster Lauf (PC aus) wird
durch den nächsten täglichen Lauf aufgeholt; der Task hat deshalb keinen Neustart-Automatismus.

## GDELT-Backfill

- Manuell starten. Laufzeit bei 60 Emittenten ≈ 13 Wochen × 60 × 6 s ≈ 78 min, bei 400
  Emittenten ≈ 9 h. Mit `--max-runtime`/`--max-calls` in Etappen möglich.
- Fortsetzbar: Der Anker (`heute − 89 Tage` beim ersten Aufruf) steht fest im Checkpoint; die
  Wochenfenster laufen von alt nach neu und enden exklusiv bei archive_start.
- Fenster, die bis zum Weiterlauf aus dem 89-Tage-Horizont gefallen sind, werden als
  `expired` gezählt — diese Daten sind verloren. Teilweise herausgefallene Fenster werden
  geclippt.
- Records tragen `backfilled=true`. **Backfill-Records zählen nie fürs LLM-Gate**, weil sie
  nicht prospektiv gesammelt wurden.
- Es werden keine Tagesstatusdateien geschrieben.

## Seed-Universum

- `tradingagents/forecast/archive/seed_universe_provisional.csv`: **provisorisch**, ~60 von
  Hand gewählte liquide Large Caps DE/FR/NL/IT/ES/CH/UK; Einzelfakten, keine
  Indexliste, nicht aus ESMA-Daten. Eine leere ISIN heißt: nicht sicher bekannt (GDELT sucht
  ohnehin über Aliase). `country` ist das Sitzland laut ISIN-Präfix (UK für GB).
- Ersetzt wird er durch `scripts/build_seed_universe.py`, das lokal heruntergeladene
  ESMA-Dateien verarbeitet und nach `archive\seed_universe.csv` schreibt (wird automatisch
  bevorzugt):

  ```powershell
  .\.venv\Scripts\python.exe scripts\build_seed_universe.py --fitrs FULECR_….zip --firds FULINS_E_….zip --top 400 --manual uk_rows.csv [--gleif]
  ```

- Download: FITRS `FULECR` (Equity Transparency, Jahresrechnung) und FIRDS `FULINS_E` über
  `registers.esma.europa.eu` laut ESMA65-8-5240 (Download Instructions). **Datei- und
  Feldnamen sind Annahme A3 und vor dem ersten echten Lauf gegen ESMA65-8-5240 zu prüfen.**
- UK (nicht mehr in ESMA-Daten) kommt von Hand über `--manual` im Seed-Schema.
- `--gleif` ergänzt rechtliche Namen aus GLEIF (CC0, Annahme A4).
- Eine ESMA-abgeleitete Datei kommt erst nach Operator-Prüfung und mit Quellenvermerk ins
  Repo.

## CA-Bundle

HTTP läuft über `requests` mit dem CA-Bundle aus `.env` (`REQUESTS_CA_BUNDLE`). Das Skript lädt
`REPO\.env` per absolutem Pfad, weil der Aufgabenplaner ohne Shell-Umgebung startet. Ein
gesetzter, aber fehlender Bundle-Pfad bricht mit Exit 4 ab (kein stiller Fallback). Bundle
bauen: siehe `scripts/PAPER_RUN.md` (AVG-HTTPS-Interception).

## Scheduler

`scripts\news_archive_task.ps1` legt die Aufgabe `\TradingEngineX\NewsArchive` an: täglich
06:30 (Ortszeit der Maschine = Europe/Berlin), `StartWhenAvailable`, `MultipleInstances
IgnoreNew`, ExecutionTimeLimit 3 h, Arbeitsverzeichnis = Repo, Aufruf
`scripts\news_archive.py run --catch-up`. Kein Neustart bei Fehlern (der nächste Tageslauf holt
nach). Nicht „unabhängig von der Benutzeranmeldung“.

Registrierung erst nach Operator-OK:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\news_archive_task.ps1            # nur anzeigen
powershell -ExecutionPolicy Bypass -File scripts\news_archive_task.ps1 -Register  # registrieren
schtasks /query /tn "\TradingEngineX\NewsArchive" /xml                           # prüfen
```

## Offene Annahmen (Research)

| # | Annahme | Folge, wenn falsch |
|---|---|---|
| A1 | GDELT-Limit ~1 Request/5 s | 429-Stürme; Backoff fängt ab |
| A2 | `seendate` = Crawl-Zeit UTC | Fehldeutung als Publikationszeit |
| A3 | Datei-/Feldnamen FITRS `FULECR`/FIRDS `FULINS_E` | Seed-Builder anpassen |
| A4 | GLEIF ist CC0 | nur Sekundärquellen |
| A5 | Schema des AMF-tar.gz (XML + Inhaltsdatei), UTF-8 | Tag-Kandidatenlisten in `amf.py` anpassen; ist das XML nicht UTF-8, scheitert jede Datei und landet nach 3 Versuchen in `gave_up` |
| A6 | rechtliche Einordnung (§ 44b UrhG, Datenbankrecht) | keine Rechtsberatung, Operator entscheidet |

## Ausblick

O4: Ein späteres privates Begleit-Repo mit GitHub Actions löst den lokalen Betrieb ab.
