# Quick 261020-v6g: M3-Vorlauf News- und Meldungsarchiv Europa – Research

**Recherchiert:** 2026-10-20 · **Domäne:** Append-only-Collector (GDELT, regulatorische Meldungen), Windows-Betrieb · **Vertrauen:** MITTEL (Quellenlage und Recht verifiziert, GDELT-Rate-Limit und Dateischemata teils angenommen)
**Hinweis:** Die Bash-Shell hing in dieser Session, daher gab es keine Live-Tests mit `python`/`requests`. Alle Web-Befunde stammen aus WebFetch/WebSearch.

## Kernergebnis (für den Planer)

1. **EQS-News ist nicht erlaubt.** Die Legal Notice verbietet ausdrücklich TDM „even if bots … are not blocked“ und erlaubt die „storage in databases“ nur mit schriftlicher Zustimmung [CITED: eqs-news.com/legal-notice]. Damit ist die Annahme aus SUMMARY.md, ein schonendes Polling sei möglich, widerlegt. Ersatz: AMF/DILA-Opendata (FR, offene Lizenz), IR-Seiten der Emittenten (Art. 17 MAR) und später eine Lizenzanfrage bei EQS (Operator).
2. **Investegate: kein RSS, kein Polling im Vorlauf.** `/rss` liefert 404, auf der Startseite gibt es keine Feed-Links [VERIFIED: WebFetch]. Die Terms sagen „for Private Investors only“, kein kommerzieller Gebrauch und keine Reproduktion ohne Zustimmung [CITED: investegate.co.uk/terms-of-use, /acceptable-use-policy]. → Zurückstellen. Das ist eine Operator-Entscheidung, weil die LLM-Abrechnung über die GmbH läuft und der Privatanleger-Status deshalb fraglich ist.
3. **GDELT DOC 2.0 bleibt die Primärquelle und ist erlaubt.** Gespeichert werden nur Metadaten (URL, Titel, seendate, Domain, Sprache, Land). Artikel-Volltexte werden nicht geholt.
4. **Neue, beste Gratisquelle mit Volltext:** AMF-Pflichtmeldungen (info-financiere) über DILA unter `https://echanges.dila.gouv.fr/OPENDATA/AMF/`. Lizenz ist die Licence Ouverte 2.0 [CITED: data.gouv.fr/datasets/info-financiere]. Die Lieferung kommt als `amf-gz_DDMMYYYY_HHMM.tar.gz` mehrmals täglich mit XML-Metadaten und Inhaltsdatei [VERIFIED: Verzeichnislisting].
5. **Kein neues Paket nötig.** GDELT liefert JSON, AMF liefert tar.gz/XML (stdlib), `requests` ist vorhanden. `feedparser` entfällt im Vorlauf, weil es keine nutzbare RSS-Quelle gibt.

## 1. Quellen, Endpunkte, Status

| Quelle | Endpunkt / Form | Status |
|---|---|---|
| **GDELT DOC 2.0** | `GET https://api.gdeltproject.org/api/v2/doc/doc?query=…&mode=ArtList&format=json&maxrecords=250&sort=DateAsc&startdatetime=YYYYMMDDHHMMSS&enddatetime=YYYYMMDDHHMMSS` | **Erlaubt (Metadaten)**. Nutzung „academic, commercial, governmental“ mit Quellenangabe [CITED: STACK.md → gdeltproject.org/about] |
| **AMF info-financiere (DILA)** | `https://echanges.dila.gouv.fr/OPENDATA/AMF/` (Verzeichnis-Listing, tar.gz; Doku unter `0 Presentation et documentation flux AMF/`) | **Erlaubt inkl. Volltext** (Licence Ouverte 2.0). Achtung: Die Daten enthalten personenbezogene Daten (Directors' Dealings), DSGVO-Hinweis von DILA |
| EQS-News | Liste nur über die Startseite (`#realtime-news`), Item-URL `…/news/{ad-hoc|corporate|voting-rights}/{slug}/{GUID}_{de|en}`; kein RSS; robots.txt sperrt KI-Bots per User-Agent, `*` ist erlaubt | **Nicht erlaubt**: TDM- und DB-Vorbehalt in der Legal Notice |
| Investegate (RNS-Spiegel) | kein RSS (404); HTML-Item `…/announcement/{src}/{company--tidm}/{slug}/{id}` | **Nicht im Vorlauf** (Privatanleger-Klausel, kein kommerzieller Gebrauch) |
| IR-Seiten der Emittenten (Art. 17 MAR) | je Emittent unterschiedlich | **Metadaten erlaubt, Volltext prüfen** je Seite (robots/TDM). Gehört nach P1, nicht in den Vorlauf |
| Euronext „Regulated news“, Unternehmensregister, BaFin-DD-Datenbank | URLs und Terms in dieser Session nicht verifiziert | **Offen**, gehört nach P1 |
| NewsAPI / Finnhub / ESAP | siehe STACK.md | nicht verwenden (ESAP-MAR-Daten gibt es erst ab 2028) |

### GDELT-Details
- **Syntax** [CITED: blog.gdeltproject.org/gdelt-doc-2-0-api-debuts]: Phrase in `"…"`, OR nur in Klammern `("Siemens Energy" OR "Siemens Gamesa")` und nicht verschachtelt. Operatoren stehen im `query`-Wert: `sourcelang:german`, `sourcecountry:germany` (FIPS-Code oder Name ohne Leerzeichen), `domain:`/`domainis:`, Ausschluss mit `-`. `maxrecords` ist höchstens 250 (Default 75). `timespan` kennt `min|h|d|w|m`. `startdatetime`/`enddatetime` haben das Format `YYYYMMDDHHMMSS` (UTC) und müssen **innerhalb der letzten 3 Monate** liegen.
- **Antwortform:** `{"articles":[{url, url_mobile, title, seendate, socialimage, domain, language, sourcecountry}]}` [CITED: gdeltdoc api_client docstring]. **Ohne Treffer kommt `{}`** [VERIFIED: Live-Abruf lieferte `{}`]. **Ungültige Query: HTTP 200 mit `text/html`-Fehlertext** [CITED: gdeltdoc]. Bei Rate-Limit kommt 429 [CITED: gdeltdoc errors.py]. `seendate` hat das Format `YYYYMMDDTHHMMSSZ` (UTC) und ist die Crawl-Zeit von GDELT, **nicht** die Veröffentlichungszeit [ASSUMED].
- **Rate-Limit:** Es gibt kein offizielles Dokument. In der Praxis meldet GDELT „Please limit requests to one every 5 seconds“ [ASSUMED]. → Der Client hält **mindestens 6 s Abstand**, bei 429/5xx/Timeout folgt exponentielles Backoff (3 Versuche) mit `timeout=(10, 60)`.
- **Abfrageform pro Emittent:** eine Query je Emittent und Fenster: `("Alias1" OR "Alias2") (sourcelang:english OR sourcelang:german OR sourcelang:french …)`. Bei sehr kurzen oder mehrdeutigen Namen (SAP, Shell, Orange, Next, Total) gilt: Phrase mit Rechtsform („SAP SE“) plus Negativterme aus dem Seed. GDELT weist zu kurze oder zu häufige Begriffe mit HTML-Fehler ab [ASSUMED] → Status `partial` mit Grund `query_rejected`.
- **Fensterung und 250er-Kappung:** Bei genau 250 Treffern wird das Fenster halbiert und rekursiv bis minimal 1 h erneut abgefragt. Ist das Fenster dann immer noch voll, wird `truncated` vermerkt.
- **Täglicher Lauf:** Abgefragt wird der vorige **UTC-Tag** `00:00:00–23:59:59` je Emittent. Bei 400 Emittenten und 6 s sind das ≈ 40 min.
- **Backfill (3 Monate, `backfilled=true`):** Wochenfenster je Emittent ergeben ≈ 13 × 400 = 5 200 Calls, bei 6 s also ≈ 9 h, plus Splits. **Die ältesten Wochen kommen zuerst**, weil das Fenster täglich schrumpft. Der Backfill muss fortsetzbar sein (Checkpoint je Emittent und Fenster) und läuft als separater, manuell gestarteter Lauf. Backfill-Einträge zählen nie für das LLM-Gate (PITFALLS Nr. 1, Nr. 14).
- **Option für später:** Die GDELT-GKG-15-Minuten-Rohdateien reichen bis 2015 zurück (URLs und Organisationen, ohne Titel). Sie werden im Vorlauf nicht gebraucht [ASSUMED].

## 2. Seed-Universum (~300–600 liquide EU-Large-Caps)

**Empfehlung: ESMA FITRS plus FIRDS plus GLEIF.** Die Quellen sind amtlich bzw. CC0 und dürfen deshalb mit Quellenvermerk ins Repo.
- **ESMA FITRS `FULECR`** (Equity Transparency Results) liefert je ISIN das Liquiditäts-Flag, die Methodik und den durchschnittlichen Tagesumsatz (ADT). Die Jahresrechnung vom 27.02.2026 gilt ab 06.04.2026; der Most Relevant Market ist Teil der Rechnung [CITED: esma.europa.eu News 2026; ESMA65-8-5240 Download Instructions]. Filter: `liquid=true`, Top-N nach ADT, Aktien (CFI `ES*`).
- **FIRDS `FULINS_E`** ergänzt Name, Emittenten-LEI und Handelsplatz-MIC [ASSUMED: Dateiname und Felder laut Download-Instructions prüfen]. Abruf über das Solr-Dateiverzeichnis `registers.esma.europa.eu/solr/esma_registers_fitrs_files/select?…` bzw. `…firds_files…` [ASSUMED: genaue Query aus ESMA65-8-5240].
- **GLEIF** liefert den rechtlichen Namen zum LEI, Lizenz CC0 [ASSUMED: nur Sekundärquellen].
- **Lizenz:** Weiterverwendung ist mit Quellenangabe erlaubt; transformierte Daten müssen als solche gekennzeichnet werden [CITED: registers.esma.europa.eu/publication/legalNoticePage]. → Die Datei `tradingagents/forecast/archive/seed_universe.csv` darf ins Repo, mit Header-Kommentar „derived from ESMA FITRS/FIRDS, transformed“.
- **Lücke UK:** Seit dem Brexit steht das UK nicht mehr bei ESMA; zuständig sind FCA-FITRS/FIRDS mit eigenen, ungeprüften Terms. Für den Vorlauf werden **UK-Titel (FTSE 100) von Hand nachgetragen**: Name, ISIN, XLON. Einzelne Fakten sind nicht schutzfähig, aber **keine Komplettkopie von STOXX- oder FTSE-Konstituentenlisten** (sui-generis-Datenbankrecht) [ASSUMED, keine Rechtsberatung].
- **Spalten:** `isin, name, country, primary_mic, lei, adt_eur, aliases (|-getrennt), negative_terms, gdelt_langs, source, as_of`. Die Aliase sind Handarbeit für die ~100 mehrdeutigsten Namen.
- **Fallback, falls die ESMA-Aufbereitung im Quick-Task zu groß wird:** Eine provisorische Handliste (Euro Stoxx 50 + DAX 40 + CAC 40 + FTSE 100 + SMI + AEX + IBEX + FTSE MIB + OMXS30, dedupliziert, ≈ 350) **außerhalb des Repos** unter `%LOCALAPPDATA%\TradingEngineX\archive\seed_universe.csv`. Im Repo liegt dann nur das Schema mit 3 Beispielzeilen.

## 3. Ablage (außerhalb des Repos)

```
%LOCALAPPDATA%\TradingEngineX\archive\
  gdelt\2026\10\2026-10-19.jsonl      # 1 Zeile = 1 Record, Datei nach UTC-Fenstertag
  amf\2026\10\2026-10-19.jsonl
  status\gdelt\2026-10-19.json        # {"status":"ok|partial|missing","queries":n,"failed":k,"truncated":t,"run_id":…}
  checkpoints\backfill_gdelt.json
  heartbeat.json                      # letzter Lauf: start/end/exit/counts je Quelle
  index.sqlite                        # UNIQUE(record_hash) zur Dedupe (stdlib sqlite3)
  raw\amf\amf-gz_…tar.gz              # Original, weil die Lizenz es erlaubt
  logs\news_archive_YYYY-MM.log
```
- Die Basis wird wie bei `_ibkr_base` in `scripts/ibkr_executor.py:274` aus `LOCALAPPDATA` abgeleitet (Fallback `~/.tradingenginex/archive`). Die autouse-Fixture in `tests/conftest.py:98` legt LOCALAPPDATA je Test um, **Tests isolieren sich dadurch automatisch**.
- **Record:** `record_hash = sha256(source|canonical_url)` (URL ohne Query-Tracking-Parameter, ohne Fragment, Host in Kleinbuchstaben). Dazu kommt `story_key = sha256(normalisierter Titel)` für die Erkennung quellenübergreifender Dubletten. **Nicht löschen, nur clustern.** Weitere Felder: `published_at` (Quelle; bei GDELT seendate mit `published_at_kind="crawl"`), `first_seen_ts` (eigene UTC-Uhr), `source`, `url`, `title`, `issuer_isin` (Matching-Treffer oder null), `match_alias`, `language`, `backfilled`, `run_id`, `collector_version`.
- **Format:** Im Vorlauf JSONL, append-only. Parquet-Kompaktierung kommt später in P1 mit DuckDB. Eine Zeile wird als ganzer String mit `\n` geschrieben, danach `flush()` und `os.fsync()`. Der Leser ignoriert eine abgeschnittene letzte Zeile.
- **Atomar (Status, Heartbeat, Checkpoint):** Zuerst in `name.tmp` im selben Ordner schreiben, `fsync`, dann `os.replace()` (auf Windows im selben Volume atomar). Bei `PermissionError` (Virenscanner oder Indexer hält die Datei) 5× mit 200 ms wiederholen.
- **Single-Instance:** Lockfile über `os.open(..., O_CREAT|O_EXCL)` mit PID und Stale-Erkennung nach 6 h. Dazu `MultipleInstances IgnoreNew` im Scheduler.

## 4. Windows-Scheduler (Registrierung erst nach Operator-OK)

Wie in ROADMAP Z. 410: **nicht** „Run whether user is logged on or not“, aber „Do not start a new instance“.
```powershell
$repo = "C:\Users\admin\PycharmProjects\TradingEngineX"
$act  = New-ScheduledTaskAction -Execute "$repo\.venv\Scripts\python.exe" `
          -Argument "scripts\news_archive.py run --catch-up" -WorkingDirectory $repo
$trg  = New-ScheduledTaskTrigger -Daily -At 06:30
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
          -ExecutionTimeLimit (New-TimeSpan -Hours 3) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 30) `
          -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "TradingEngineX\NewsArchive" -Action $act -Trigger $trg -Settings $set `
          -Description "M3 news archive (append-only), quick 261020-v6g"
# Prüfen/Export: schtasks /query /tn "TradingEngineX\NewsArchive" /xml
```
- **CA-Variablen:** Der Scheduler startet ohne `.env`. Das Skript ruft deshalb `load_dotenv(REPO/.env)` mit absolutem Pfad auf, bevor es `requests` nutzt; auf `find_dotenv(usecwd=True)` aus `tradingagents/__init__.py` verlässt es sich nicht allein. Danach übergibt es `verify=os.environ["REQUESTS_CA_BUNDLE"]` explizit an die Session. Ist die Variable gesetzt, die Datei aber nicht vorhanden, bricht es laut ab. Ist die Variable nicht gesetzt, greift der certifi-Default mit Log-Warnung [CITED: scripts/PAPER_RUN.md:156-181].
- **Catch-up liegt in der Logik, nicht im Scheduler.** `StartWhenAvailable` holt nur den *einen* verpassten Start nach. Das Skript arbeitet deshalb bei jedem Lauf **alle Tage ohne `ok`-Status seit Archivstart** ab, die noch im GDELT-3-Monats-Fenster liegen (älteste zuerst). Solche nachgeholten Tage sind **nicht** `backfilled`, aber `first_seen_ts` zeigt die Verspätung.
- **Logging:** Das Skript schreibt selbst über `logging` und einen RotatingFileHandler nach `archive\logs\`. Die Ausgabe des Scheduler-Tasks wird nicht umgeleitet. Exit-Code ≠ 0 bei jeder Quelle mit `missing`.

## 5. Integration in den Bestand

- **Paket** `tradingagents/forecast/__init__.py` + `tradingagents/forecast/archive/{__init__,http,gdelt,amf,store,status,seed}.py`. Das Strang-Skript `scripts/news_archive.py` ist ein dünnes CLI (`run`, `backfill`, `gaps`, `heartbeat`) mit argparse wie die übrigen `scripts/*.py`.
- **HTTP:** Eine eigene `requests.Session` in `archive/http.py` mit `User-Agent: TradingEngineX-archive/0.1 (+contact)`, Timeout, Backoff und der Fetch-Funktion als **injizierbarem Parameter**. `tradingagents/dataflows/net.py` (`get_scrubbed`) zielt auf Secret-Scrubbing; hier gibt es keine Keys, daher keine Wiederverwendung nötig.
- **Extras:** Es kommen **keine neuen Abhängigkeiten** dazu. Wird später ein Extra gebraucht, heißt es `forecast = ["feedparser>=6.0.11"]` nach dem Muster von `ibkr` in `pyproject.toml:46` (das Extra erst einführen, wenn eine RSS-Quelle freigegeben ist).
- **Tests:** `tests/test_news_archive_*.py`. Netz ist durch die autouse-Fixture `_no_network` (conftest.py:59) ohnehin blockiert. Fixtures liegen unter `tests/fixtures/news_archive/`: gekürzte, **synthetische** GDELT-JSONs (`{}`, 3 Artikel, genau 250 Artikel per Generator, HTML-Fehler, 429) und ein Mini-AMF-tar.gz, das im Test aus XML-Strings gebaut wird. Echte Volltexte oder Titel gehören nicht in das öffentliche Repo. Der Live-Smoke-Test läuft nur mit `@pytest.mark.integration`. Mock-Muster: `monkeypatch.setattr(module.session, "get", fake)` wie in `tests/test_alpha_vantage_hardening.py`.
- **Lokale Ausführung:** `.venv/Scripts/python.exe -m pytest tests/test_news_archive_*.py` und `… -m ruff check` (MEMORY: kein `uv run`).

## 6. Pitfalls

| Pitfall | Gegenmaßnahme |
|---|---|
| GDELT `{}` ist mehrdeutig: kein Treffer oder stummer Fehler | Täglich eine **Canary-Query** (z. B. `"European Central Bank"`). Liefert sie 0, ist der Tag `partial`, nicht `ok` |
| GDELT-HTML-Fehler bei HTTP 200 | `Content-Type` prüfen und als `query_rejected` loggen, nicht als „0 Treffer“ |
| Timeouts und 429 bei GDELT | ≥ 6 s Abstand, Backoff, Retries. Ist die Fehlerquote > 10 % der Queries, wird der Tag `partial`; scheitern alle Queries oder der ganze Lauf, wird er `missing` |
| 250er-Kappung | Fenster rekursiv splitten, `truncated` zählen |
| Zeitzonen | Intern alles UTC (`datetime.now(timezone.utc)`). Quellzeiten werden mit `zoneinfo` (Europe/Paris, Europe/London) normalisiert, `published_at_raw` bleibt erhalten. Dateien und Status je **UTC-Tag**. Den DST-Test (letzter So. März/Okt.) aus PITFALLS Nr. 21 übernehmen |
| Lücke als „keine News“ gelesen (PITFALLS Nr. 14) | **Fehlende Statusdatei = `missing`**. `gaps` iteriert alle Kalendertage ab `archive_start` und meldet sie. Heartbeat älter als 36 h → Exit 2 und laute Meldung. Ein Test simuliert einen Ausfalltag |
| Dubletten über Quellen und Läufe | `record_hash` UNIQUE (Re-Run ist idempotent), `story_key`-Cluster statt Löschen |
| Namenskollisionen (Shell, Orange, Next, Total) | Aliase plus `negative_terms` im Seed; `issuer_isin` nur bei Alias-Treffer im Titel, sonst `null` mit `match_confidence` |
| HTML-Änderungen | Im Vorlauf entfällt HTML-Scraping, weil EQS und Investegate ausfallen. Bei AMF ändert sich höchstens das XML-Schema → Parser-Fehler macht `partial`, und die Rohdatei bleibt erhalten |
| Lizenzdaten im öffentlichen Fork | Archivpfad liegt nie im Repo; Tests nutzen synthetische Daten; `.gitignore` bleibt unberührt, weil der Pfad außerhalb liegt |
| DSGVO bei AMF-Directors'-Dealings | Nur lokal, kein Upload; Löschpflichten aus den DILA-Forum-Hinweisen beachten (Operator) |

## Assumptions Log

| # | Annahme | Risiko |
|---|---|---|
| A1 | GDELT-Limit ~1 Request/5 s | zu schnell → 429-Stürme; der Backoff fängt das ab |
| A2 | `seendate` ist Crawl-Zeit in UTC | Fehlinterpretation als Publikationszeit |
| A3 | Datei- und Feldnamen von FITRS `FULECR`/FIRDS `FULINS_E` sowie Solr-Pfad | der Seed-Bau braucht einen Blick in ESMA65-8-5240 |
| A4 | GLEIF ist CC0 | nur Sekundärquellen |
| A5 | Schema des AMF-tar.gz (XML plus Inhaltsdatei) | Doku-Ordner `0 Presentation…` vor dem Parserbau lesen |
| A6 | Rechtliche Einordnung (§ 44b UrhG, Datenbankrecht, Investegate-Privatanleger) | keine Rechtsberatung, Operator entscheidet |

## Offene Fragen an den Operator
1. Soll bei EQS eine Lizenz angefragt werden (News-Sales)? Bis dahin bleibt DACH-Ad-hoc ohne Quelle, außer über GDELT und die IR-Seiten.
2. Investegate endgültig streichen oder eine Lizenz bei LSEG (RNS „Other Application“) prüfen?
3. Startzeit 06:30 Europe/Berlin? Ein zweiter Trigger am Abend würde die `first_seen`-Latenz für AMF-Meldungen senken.

## Quellen
- [GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) · [gdeltdoc api_client/errors/filters](https://github.com/alex9smith/gdelt-doc-api)
- [EQS Legal Notice](https://www.eqs-news.com/legal-notice/) · [eqs-news robots.txt](https://www.eqs-news.com/robots.txt) · [EQS T&C](https://www.eqs.com/about-eqs/terms-and-conditions/)
- [Investegate Terms](https://www.investegate.co.uk/terms-of-use) · [Acceptable Use](https://www.investegate.co.uk/acceptable-use-policy) · [robots.txt](https://www.investegate.co.uk/robots.txt) · [Stockopedia-Thread RNS-RSS](https://stockopedia.com/content/rns-rss-feed-346608)
- [data.gouv info-financiere](https://www.data.gouv.fr/datasets/info-financiere/) · [DILA OPENDATA/AMF](https://echanges.dila.gouv.fr/OPENDATA/AMF/)
- [ESMA Transparenzrechnung Equity](https://www.esma.europa.eu/press-news/esma-news/esma-publishes-results-annual-transparency-calculations-equity-and-equity-3) · [ESMA65-8-5240 Download Instructions](https://www.esma.europa.eu/sites/default/files/2023-12/ESMA65-8-5240_FIRDS_Transparency_Download_Instructions.pdf) · [ESMA Registers Legal Notice](https://registers.esma.europa.eu/publication/legalNoticePage)
- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api)
- Repo: `tests/conftest.py`, `scripts/ibkr_executor.py:274`, `scripts/PAPER_RUN.md:156-181`, `pyproject.toml`, `.planning/research/m3-vorhersage-engine/{STACK,PITFALLS,SUMMARY}.md`, `.planning/ROADMAP.md:410`
