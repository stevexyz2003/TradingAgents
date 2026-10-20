# Stack-Recherche: M3 Vorhersage-Engine (Europa)

**Domäne:** kalibrierte Alpha-Prognose (5 und 20 Handelstage) für europäische Aktien, hybrid aus statistischem Modell und LLM-Merkmalen, mit point-in-time-Daten, Walk-forward-Validierung und Go/No-Go-Gate
**Recherchiert:** 2026-10-20
**Gesamtvertrauen:** MITTEL. Die Bibliotheksversionen sind auf PyPI geprüft (HOCH). Preise und Abdeckung der Datenanbieter stammen von Anbieterseiten und Sekundärquellen (MITTEL). Ob es echte point-in-time-Fundamentaldaten und eine STOXX-600-Historie im Budget gibt, ist nur teilweise belegt (NIEDRIG bis MITTEL, siehe unten).

Nicht neu recherchiert, weil schon validiert: LLM-Pipeline, `ib_async==2.1.0`, yfinance, stockstats, pandas 3, pip/venv, Python 3.11–3.14.

---

## Kernaussagen (das Wichtigste vorab)

1. **Datenanbieter: EODHD ist im Budget praktisch die einzige Wahl.** Norgate (nur US/AU/CA), Tiingo (US/China), MarketParquet (US) und Sharadar (US) decken keine europäischen Aktien ab. FMP verlangt für Europa den teuersten Plan. LSEG/Refinitiv ist institutionell bepreist. Über IBKR gibt es keine Fundamentaldaten mehr: `reqFundamentalData` ist aus der TWS-API entfernt.
2. **Point-in-time-Fundamentaldaten zu kaufen, gelingt im Budget nur näherungsweise.** EODHD liefert für Europa Quartals- und Jahresabschlüsse seit etwa 2000 mit `filing_date` je Bericht. Ob Restatements alte Werte überschreiben, ist nicht dokumentiert. Echte PIT entsteht erst ab jetzt durch eigene, datierte Snapshots.
3. **Eine historische Zusammensetzung des STOXX Europe 600 ist im Budget nicht käuflich.** EODHD führt historische Mitgliedschaften nur für S&P- und Dow-Jones-Indizes, das Add-on kostet 29,99 €/Monat. Empfehlung: ein **regelbasiertes eigenes Universum** aus Marktkapitalisierung und Liquidität je Stichtag, gebildet aus EODHD-Kursen einschließlich delisteter Titel. Den STOXX 600 nur als Benchmark-Zeitreihe verwenden.
4. **Modellierung schlank halten:** scikit-learn 1.9.1 (Logistik-Baseline und Kalibrierung), LightGBM 4.7.0, statsmodels 0.15.0, scipy und `arch` 8.0.0 (Block-Bootstrap, SPA/StepM). Purged Walk-forward **selbst implementieren**, etwa 80 Zeilen mit Tests. mlfinlab ist kostenpflichtig, timeseriescv seit 2018 tot, purgedcv im Alpha-Stadium, skfolio zieht cvxpy und plotly nach.
5. **Neues optionales Extra `forecast`**, nach dem Muster von `ibkr`, und `ci = [dev,ibkr,forecast]`. Speicherung in DuckDB 1.5.6 und Parquet. Die Label-UI baut auf `questionary` und `rich`, die bereits Abhängigkeiten sind. Kein Streamlit.

---

## Empfohlener Stack

### Kerntechnologien (neu)

| Technologie | Version (geprüft) | Zweck | Warum |
|---|---|---|---|
| **EODHD „Historian“ (EOD All-World)** | Abo, 19,99 €/Monat bzw. 199,90 €/Jahr | EOD-Kurse Europa (XETRA, LSE, PA, AS, SW …), 30+ Jahre, Dividenden und Splits, **delistete Titel** über `exchange-symbol-list?delisted=1` | Einzige bezahlbare Quelle mit delisteten EU-Titeln. EODHD meldete im September 2026 9.587 delistete Symbole an der Börse Frankfurt und 4.077 an der LSE. 100.000 Calls pro Tag. |
| **EODHD „Equity analyst“ (Fundamentals)** | 59,99 €/Monat, **nur in einzelnen Monaten buchen** | Bilanz, GuV und Cashflow quartalsweise und jährlich, Europa seit etwa 2000, `filing_date` je Bericht, `Earnings.History.reportDate` | Enthält **keine** EOD-Kurse, Dividenden oder Splits, daher nur zusammen mit Historian sinnvoll. Mindestlaufzeit 1 Monat, jederzeit kündbar. Einmal für den Backfill buchen (aus dem 300-€-Topf), danach einen Monat pro Quartal nach der Berichtssaison. So entsteht ein eigenes, datiertes PIT-Archiv. |
| **scikit-learn** | 1.9.1 (2026-09-10, Python ≥3.11) | Logistische Regression als Baseline, `CalibratedClassifierCV` (sigmoid/isotonic), `FrozenEstimator`, `brier_score_loss`, `log_loss`, `calibration_curve` | Standard. `cv="prefit"` ist entfernt, stattdessen `CalibratedClassifierCV(FrozenEstimator(m), method=...)` auf einem **zeitlich getrennten** Kalibrierfenster verwenden. |
| **LightGBM** | 4.7.0 (2026-07-18, Python ≥3.10) | Gradient Boosting auf Kurs-, Fundamental- und Textmerkmalen | Schnell auf Tabellendaten, kommt mit fehlenden Werten nativ zurecht, Windows-x64-Wheel vorhanden (benötigt die MSVC-Runtime). Wird nur eingesetzt, wenn es die logistische Baseline OOS schlägt. |
| **statsmodels** | 0.15.0 (2026-08-27, Python ≥3.10) | Cluster-robuste Standardfehler (Zeit × Titel), `multipletests` (Benjamini-Hochberg, Holm), HAC/Newey-West für überlappende 20-Tage-Renditen | Gate-Statistik: Das 90-%-Konfidenzintervall muss die Abhängigkeit über Zeit und Titel abbilden. |
| **arch** | 8.0.0 (2025-10-21) | `StationaryBootstrap`/`MovingBlockBootstrap` für Alpha-Konfidenzintervalle, `SPA`/`StepM`/`MCS` gegen Data Snooping | Liefert genau die Mehrfachtest-Kontrolle über Modell- und Prompt-Varianten (VAL-05), die sonst selbst gebaut werden müsste. Abhängigkeiten: numpy, scipy, pandas, statsmodels. |
| **scipy** | 1.18.1 (2026-08-21) erfordert **Python ≥3.12** | Verteilungen und Tests | Vorsicht: Die CI-Matrix testet 3.11. Untergrenze `scipy>=1.15` setzen, dann löst pip auf 3.11 eine ältere 1.x-Version auf. Ob die Auflösung auf py3.11 klappt, ist im CI-Lauf zu prüfen. |
| **DuckDB** | 1.5.6 (2026-09-28, Python ≥3.10) | Abfrage-Engine über Parquet-Archive (Kurse, Fundamentaldaten, News, Merkmale, Prognosen) | Eingebettet, keine Server-Komponente, schreibt Parquet selbst (`COPY … TO … (FORMAT parquet)`). As-of-Joins (`ASOF JOIN`) passen genau zur PIT-Logik. |
| **exchange_calendars** | 4.13.2 (2026-03-10), bereits installiert | Kalender XETR, XPAR, XAMS, XBRU, XLIS, XLON, XSWX, XMIL, XMAD, XSTO, XCSE, XHEL, XOSL, XDUB, XWBO | Alle geforderten Börsen sind vorhanden (PyPI-Seite). Im installierten Quelltext geprüft: XETR führt Heiligabend und Silvester als Feiertage, XLON hat Handelszeiten 08:00–16:30 und Sonderschlüsse. |

### Unterstützende Bibliotheken

| Bibliothek | Version | Zweck | Wann |
|---|---|---|---|
| pyarrow | 26.0.0 (2026-10-09, Python ≥3.11) | `pandas.read_parquet`/`to_parquet`, Arrow-Austausch mit DuckDB | Ist heute **nicht** in der venv installiert. Wird gebraucht, sobald pandas Parquet lesen oder schreiben soll. |
| feedparser | 6.0.14 (2026-07-30) | RSS/Atom-Archivierer (Investegate/RNS, Unternehmens-IR-Feeds, Euronext-Live-Feeds je Titel) | Für den News-Archivierer (DATA-01). Abrufe über `requests` mit dem AVG-CA-Bundle, danach `feedparser.parse(bytes)`. Den eingebauten urllib-Abruf von feedparser nicht nutzen, er umgeht die TLS-Konfiguration. |
| requests (vorhanden) | ≥2.32.4 | Alle HTTP-Abrufe (EODHD, GDELT, Feeds) | **Kein** Anbieter-SDK verwenden (`eodhd`, `finnhub-python`). Ein dünner eigener Client hält TLS, Retry und Fixture-Tests in einer Hand. |
| questionary und rich (vorhanden) | 2.1.0 / ≥14 | Label-Oberfläche im Terminal für etwa 50 Meldungen im Monat | Null neue Abhängigkeiten, siehe Abschnitt f. |
| purgedcv | 0.1.11 (2026-10-16, MIT, Alpha) | **Nur** zum Gegenprüfen des eigenen Splitters in einem Test, falls gewünscht | Nicht als Laufzeitabhängigkeit: Alpha-Status, 58 Sterne. |

### Entwicklungswerkzeuge

| Werkzeug | Zweck | Hinweise |
|---|---|---|
| pytest-Fixtures mit eingefrorenen JSON- und Parquet-Antworten | Tests ohne Netz | Echte EODHD- und GDELT-Antworten einmal von Hand aufnehmen, unter `tests/fixtures/eodhd/` ablegen und in den Fixtures **Lizenzdaten auf wenige Titel und Tage kürzen** (öffentliches Fork-Repo). Netztests nur mit `-m integration`. |
| pip-audit (vorhanden, security-audit.yml) | CVE-Prüfung | Prüft das neue Extra automatisch mit, wenn es in `ci` steckt. |

---

## (a) Datenanbieter: Kurse, Fundamentaldaten, Kapitalmaßnahmen (Europa)

| Anbieter | Europa | Delistete Titel | PIT-Fundamentaldaten | STOXX-600-Historie | Preis | Urteil |
|---|---|---|---|---|---|---|
| **EODHD** | Ja, rund 70 Börsen, 150.000+ Ticker | **Ja** (`delisted=1`, nach Anbieterangabe an allen Börsen; Startjahr je Börse nicht dokumentiert) | **Teilweise:** `filing_date` je Bericht, Europa seit etwa 2000. Umgang mit Restatements undokumentiert. | **Nein.** Historische Mitgliedschaften nur S&P 500 (im Fundamentals-Feed) bzw. S&P/DJ (Marketplace-Add-on 29,99 €/Monat, bis 12 Jahre). „CBOE Europe indices“ im Fundamentals-Plan ohne Historie. Historische Marktkapitalisierung nur US. | Historian 19,99 €, Fundamentals 59,99 €, All-in-One 99,99 € (Jahresabo 83,33 €/Monat), jeweils Privatnutzung | **Empfohlen** |
| Financial Modeling Prep | Erst im obersten Plan „global“; Basic/Starter nur US, Premium US+UK+CA | Endpunkt „Delisted Companies“ vorhanden, für welche Pläne unklar | Nein (keine Angabe) | Nein, nur S&P 500, Dow Jones, Nasdaq | Ultimate laut Sekundärquelle etwa 149 $/Monat (offizielle Seite antwortet mit 403, **nicht verifiziert**) | Nicht empfohlen: Europa sprengt mit den LLM-Kosten das Budget, kein Mehrwert gegenüber EODHD |
| Tiingo | Nein (Abdeckung US und CN) | – | – | – | – | Ungeeignet |
| Norgate Data | Nein, nur Aktien US/AU/CA (Herstellerangabe) | US ja | – | US ja | – | Ungeeignet |
| LSEG/Refinitiv (Workspace, Datastream) | Ja, mit Historie `0#.STOXX(YYYYMMDD)` | Ja | Ja | Ja | institutionell (vierstellig pro Monat, nicht veröffentlicht) | Außerhalb des Budgets |
| IBKR | Nur Kurse über Marktdaten-Abo; keine delisteten Titel | Nein | **Nein:** `reqFundamentalData` ist aus der TWS-API entfernt (laut Bericht zu TWS API 10.47) | Nein | Euronext L1 nicht-professionell etwa 5 €/Monat (IBKR-Tabelle, Stand unklar) | Nur für Ausführung und Live-Kurse, nicht für Historie |
| STOXX/Qontigo direkt | Ja | – | – | Ja, kostenpflichtig, kein Listenpreis gefunden | Anfrage nötig | Optional: einmalige Anfrage für eine historische Kompositionsdatei (Ergebnis offen) |

**Empfohlene Konstellation im Budget:**

| Posten | Kosten | Wann |
|---|---|---|
| EODHD Historian (Jahresabo) | 16,66 €/Monat | dauerhaft |
| EODHD Fundamentals, 1 Monat Backfill | 59,99 € einmalig | Phase Datenbasis (aus dem 300-€-Topf) |
| EODHD Fundamentals, 1 Monat pro Quartal (Mai, Aug, Nov, Feb nach der Berichtssaison) | etwa 20 €/Monat im Mittel | dauerhaft, erzeugt eigene datierte Snapshots |
| IBKR Euronext/Xetra-L1, falls für Paper nötig | etwa 5–10 €/Monat (nicht verifiziert) | Betriebsphase |
| **Summe Daten** | **etwa 40–50 €/Monat** | |
| Verbleibt für LLM-Kosten | etwa 100 €/Monat | Bei etwa 0,18 $ je Ticker und Lauf (Memory-Notiz) reicht das für rund 25–28 Titel × 21 Tage mit **einem** Lauf je Titel. Mit PRED-04 (k=5 Läufe) geht das nur stichprobenweise. **Budgetkonflikt im Roadmap-Schritt klären.** |

**Universum ohne STOXX-Historie (Empfehlung):** Das Universum je Stichtag t wird so gebildet: Aktien der Börsen XETR, XPAR, XAMS, XBRU, XMIL, XMAD, XLON und XSWX, in der Primärlinie, einschließlich delisteter Titel. Gefiltert wird nach dem Median-Euro-Umsatz über 60 Tage bis t-1. Die Marktkapitalisierung wird berechnet als Kurs(t-1) × `commonStockSharesOutstanding` aus dem letzten Bericht mit `filing_date` < t. Daraus werden die Top N gewählt (etwa 200–300) und quartalsweise neu gebildet. Das ist reproduzierbar, frei von Survivorship-Bias im Rahmen der EODHD-Abdeckung und gut dokumentierbar. Als Benchmark dient der STOXX Europe 600 (Net Return) als Zeitreihe, nicht als Mitgliederliste. Vertrauen: MITTEL. Methodisch üblich, die Datenvollständigkeit der Aktienanzahl in EODHD Europa ist **nicht verifiziert** und muss im Backfill-Monat stichprobenhaft geprüft werden.

**Pflichtprüfungen im Backfill-Monat** (Recherche-Flag für die Datenphase):
- Startjahr der delisteten Historie je Börse; Ticker-Wiederverwendung (alter gegen neuen Emittenten) über ISIN abgleichen.
- `filing_date` in Europa gefüllt? Bei 10–20 Titeln mit bekannten Restatements prüfen, ob alte Werte überschrieben wurden.
- Ob Dividenden und Splits für delistete EU-Titel vollständig sind, wichtig für die Total-Return-Rechnung.
- Bewertung von Firmenwechseln wie Fusionen und Squeeze-outs: Liefert EODHD einen letzten Kurs oder einen Barabfindungswert?

## (b) Europäische News und Meldungen archivieren

| Quelle | Zugang | Kosten | Einschätzung |
|---|---|---|---|
| **GDELT DOC 2.0 API** | HTTP, kein Schlüssel; nur die letzten 3 Monate, max. 250 Artikel pro Abfrage | 0 € | **Primärquelle für breite Presseabdeckung (Metadaten, URL, Ton).** Laut GDELT-About frei für akademische, kommerzielle und behördliche Nutzung, mit Quellenangabe. Wegen des 3-Monats-Fensters **täglich** abrufen. Mit dem eigenen Client über `requests` arbeiten; `gdeltdoc` 1.12.0 (April 2025) ist optional und wird nicht gebraucht. |
| **EQS News (früher DGAP)**, Ad-hoc nach Art. 17 MAR | Webseite mit den Kategorien Ad-hoc, Corporate, Stimmrechte, Directors' Dealings. Ein öffentlicher RSS-Feed war **nicht auffindbar**. | 0 € | Für DACH-Emittenten die wichtigste Quelle. HTML-Liste schonend abrufen (1 Abruf alle 15 Minuten). Nutzungsbedingungen von EQS vor dem Start lesen (eqs.com/about-eqs/terms-and-conditions). Fallback: IR-Seiten der Emittenten, denn Art. 17 Abs. 1 MAR verpflichtet sie, Insiderinformationen mindestens 5 Jahre auf der eigenen Website vorzuhalten (Regelungsinhalt aus dem Gedächtnis, MITTEL). |
| **RNS (LSE)** | Offizielle Lizenz bei LSEG; „Other Application“ umfasst ausdrücklich Sentiment und LLM-Nutzung (RNS Pricing and Policy 2026) | Lizenz, Preis nicht gefunden | Für UK-Titel Investegate-RSS als frei lesbaren Spiegel (Existenz der Seite belegt, aktuelle Feed-URLs **nicht verifiziert**). Nur Überschrift, Zeit, Emittent und Link archivieren, nicht den Volltext. |
| **Euronext Live**, „Regulated news“ je Titel | Seite je Instrument mit Abo-Funktion; Feeds erzeugt der Emittent | 0 € | Feed-URLs je Titel einmal ermitteln (nicht verifiziert). |
| NewsAPI.org | Developer-Plan kostenlos, aber **nur für Entwicklung**, 24 h Verzögerung, 1 Monat Rückblick; Business 449 $/Monat | – | **Nicht verwenden:** Produktionsnutzung ist erst ab 449 $/Monat erlaubt. |
| Finnhub Company News | Gratis-Tier nach Sekundärquellen im Wesentlichen US; internationale Daten ab einem bezahlten Tier | ab etwa 12 $/Monat (nicht verifiziert) | Nicht empfohlen, unklarer Mehrwert für die EU. |
| ESAP (EU Single Access Point) | Start Juli 2027; MAR-Meldungen erst ab Phase 2 (Januar 2028) | 0 € | Für M3 zu spät. Als künftige, offizielle Quelle vormerken. |

**Rechtliches** (keine Rechtsberatung, Vertrauen MITTEL):
- § 44b UrhG (Text- und Data-Mining) erlaubt Vervielfältigungen rechtmäßig zugänglicher Werke für die automatisierte Analyse. Die Kopien sind zu **löschen, sobald sie dafür nicht mehr erforderlich sind**. Ein Nutzungsvorbehalt gilt nur in **maschinenlesbarer** Form (etwa robots.txt oder TDM-Reservation). Folge: robots.txt und TDM-Vorbehalte je Quelle prüfen und die Prüfung im Archiv vermerken.
- **Kritisch für dieses Repo:** Der Fork ist öffentlich. Volltexte, EODHD-Rohdaten und News-Archive dürfen **nie** ins Repo, in die Paper-Log-Branches oder in CI-Artefakte. EODHD-Pläne sind Privatnutzung ohne Weitergabe. Ablage lokal außerhalb des Repos (etwa `%LOCALAPPDATA%\tradingenginex\archive\`) oder unter einem gitignorierten Pfad, mit Backup.
- Archivieren: Überschrift, Quelle, URL, Emittent oder ISIN, `published_at` (Quelle), `fetched_at` (eigene Uhr, UTC), Hash, Sprache und den LLM-Merkmalswert. Volltext nur, wo die Lizenz es erlaubt (Ad-hoc-Pflichtmeldungen über die Emittenten-IR sind am unkritischsten).

## (c) Modellierung, Statistik, Kalibrierung, Walk-forward

**Empfehlung:**
- **Modelle:** zuerst `LogisticRegression` mit wenigen, gut verstandenen Merkmalen (Momentum 1/3/12 Monate, Volatilität, Größe, Bewertung, Umsatz-Gap, LLM-Sentiment als Zahl). LightGBM nur als Herausforderer. Ziel: P(Alpha nach Kosten > 0) für die Horizonte 5 und 20 Tage, je eigenes Modell.
- **Kalibrierung:** `CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")` auf dem letzten Teil jedes Trainingsfensters (zeitlich getrennt, mit Embargo). Isotonic erst ab etwa 1.000 Kalibrierfällen (sklearn-Doku), bei 300 Gate-Fällen also sigmoid. Bericht: `brier_score_loss`, `log_loss`, `calibration_curve` (Reliability-Tabelle) plus der eigene ECE-Wert.
- **Walk-forward mit Purging und Embargo:** **selbst implementieren** als `PurgedWalkForward(train_days, test_days, horizon, embargo)` mit sklearn-kompatiblem `split()`. Purging entfernt Trainingsfälle, deren Label-Fenster [t, t+h] in das Testfenster hineinreicht; das Embargo beträgt mindestens h Handelstage. Grundlage ist der Handelstag-Index aus `exchange_calendars`, damit h=5/20 echte Handelstage sind. Begründung: Etwa 80 Zeilen sind voll testbar, bringen keine neue Abhängigkeit und lassen sich an Mehrbörsen-Kalender anpassen.
  - `sklearn.model_selection.TimeSeriesSplit(gap=...)` reicht nicht: `gap` ist nur Abstand, kein Purging überlappender Labels und kein Embargo.
  - mlfinlab: kommerziell lizenziert, raus. timeseriescv 0.2: letztes Release 2018-09-07, „Alpha“, raus. purgedcv 0.1.11: MIT, aktiv (2026-10-16), aber Alpha mit 58 Sternen, höchstens als Test-Orakel. skfolio 1.9.6 (BSD): hat `WalkForward`/`CombinatorialPurgedCV`, zieht aber cvxpy-base, clarabel und plotly nach. Für ein Portfolio-Optimierungsprojekt sinnvoll, hier überdimensioniert.
- **Gate-Statistik:**
  - Alpha-Konfidenzintervall (90 %) per `arch.bootstrap.StationaryBootstrap` auf der täglichen Portfolio-Alpha-Reihe nach Kosten (20 bp je Seite).
  - Gegenprobe: OLS-Achsenabschnitt mit HAC-Fehlern (statsmodels) und Cluster-Fehlern nach Datum.
  - Mehrfachtests über Varianten: `arch.bootstrap.SPA`/`StepM` gegen die Baseline-Varianten, zusätzlich `statsmodels.stats.multitest.multipletests(method="fdr_bh")` für Merkmals- und Musterzellen.
  - „Effektiv unabhängige Fälle“: nicht überlappende Fenster je Titel, Korrektur über die Querschnittskorrelation (Design-Effekt). Das ist eigene Logik, keine Bibliothek.

## (d) Börsenkalender

`exchange_calendars` 4.13.2 deckt alle benötigten Börsen ab: XETR, XPAR, XAMS, XLON, XSWX sowie XBRU, XMIL, XMAD, XSTO, XCSE, XHEL, XOSL, XDUB, XWBO, XLIS. Das Paket steckt heute **nur im Extra `ibkr`** (Pin `>=4.13,<5`, wegen XNYS). Für M3 wird es zusätzlich ins Extra `forecast` aufgenommen, mit demselben Bereich. Abhängigkeit `tzdata>=2025.2` ist verträglich mit der `ib_async`-Obergrenze `tzdata<2026.0`. **Keine** M3-Abhängigkeit darf `tzdata>=2026` verlangen, sonst ist `ci` nicht mehr auflösbar.

Hinweise:
- Ein Mehrbörsen-Universum braucht einen **Union- und einen Intersection-Kalender**. Der Horizont „5 Handelstage“ wird je Titel an dessen Primärbörse gezählt, das Rebalancing läuft an Tagen, an denen alle relevanten Börsen offen sind. Das ist eigene Logik.
- XETR schließt Heiligabend und Silvester (im installierten Quelltext geprüft). Das deckt sich mit dem Deutsche-Börse-Status „Holiday“.
- `pandas_market_calendars` nicht zusätzlich aufnehmen: Es baut auf exchange_calendars auf und bringt nichts Neues.

## (e) Speicherung von Archiven und Merkmalen

- **Parquet-Dateien, partitioniert** (`source=…/date=YYYY-MM-DD/part.parquet`), plus **DuckDB 1.5.6** als Abfrageschicht. Eine `.duckdb`-Katalogdatei enthält Views und `ASOF JOIN`s für die PIT-Abfrage „Fundamentaldaten bekannt am Tag t“.
- **Nur anhängen** (append-only): Jeder Abruf schreibt eine neue Partition mit `fetched_at`; nichts wird überschrieben. Restatements werden so als neue Versionen sichtbar, das ist der eigentliche PIT-Mechanismus.
- Im Repo landen nur **abgeleitete, nicht lizenzpflichtige Ergebnisse**: Prognosen je Titel und Tag, Gate-Berichte, Kalibrierungstabellen.
- DuckDB lädt **nichts über httpfs** (eigener TLS-Stack, läuft vermutlich in die AVG-Interception, nicht verifiziert). Alle Downloads laufen über `requests` mit dem AVG-Bundle, DuckDB liest nur lokale Dateien.
- Den vorhandenen Weg über SQLite (`langgraph-checkpoint-sqlite`) nicht für Zeitreihen missbrauchen.

## (f) Label-Oberfläche (etwa 50 Meldungen pro Monat)

**Empfehlung: ein CLI-Labeler** `scripts/label_news.py`, gebaut auf `questionary` und `rich`, die beide schon Kernabhängigkeiten sind. Er zieht 50 zufällige Meldungen mit festem Seed aus dem Archiv, zeigt Titel, Auszug, Emittent und die Jev- oder LLM-Einschätzung **verdeckt**, um Anker-Effekte zu vermeiden, und fragt Relevanz, Richtung (−1/0/+1) und Sicherheit ab. Die Ergebnisse schreibt er als JSONL bzw. Parquet mit `labeler`, `labeled_at` und `seed`. Begründung: null neue Abhängigkeiten, testbar ohne Netz und ohne Browser, passt zum bestehenden `cli`-Stil.

Alternative, falls ein Browser gewünscht ist: eine **statische HTML-Datei**, die ein Skript erzeugt. Sie enthält eine eingebettete JSON-Liste, speichert über `localStorage` und lädt das Ergebnis als JSON herunter. Ebenfalls keine Abhängigkeit, kein Server.

Streamlit 1.66.0 (2026-10-14) funktioniert, ist für 50 Klicks im Monat aber überdimensioniert. Es bringt tornado, altair, protobuf, pyarrow und einen lokalen Webserver mit und braucht einen eigenen Pflegepfad in pip-audit.

---

## Installation

```bash
# Windows, venv (nicht uv). AVG-TLS: CA-Bundle-Variablen aus .env (scripts/PAPER_RUN.md) vorher setzen,
# pip >= 24.2 nutzt zusätzlich truststore.
.venv/Scripts/python.exe -m pip install -e ".[forecast]"
.venv/Scripts/python.exe -m pip install -e ".[ci]"      # dev + ibkr + forecast für die Tests
```

Vorschlag für `pyproject.toml`:

```toml
[project.optional-dependencies]
# Forecast engine (milestone M3): statistical model, validation, PIT archive.
# Optional so the core install and upstream CI stay lean: pip install ".[forecast]".
forecast = [
    "scikit-learn>=1.8,<2",      # FrozenEstimator-based calibration; cv="prefit" is gone
    "lightgbm>=4.6,<5",
    "statsmodels>=0.14.4",
    "scipy>=1.15",               # 1.18 needs py>=3.12; floor keeps py3.11 CI resolvable
    "arch>=7.2",                 # stationary bootstrap, SPA/StepM
    "duckdb>=1.4,<2",
    "pyarrow>=18",
    "feedparser>=6.0.11",
    "exchange_calendars>=4.13,<5",  # same range as the ibkr extra (tzdata cap of ib_async)
]
ci = [
    "tradingagents[dev,ibkr,forecast]",
]
```

Integrationspunkte:
- Module unter `tradingagents/forecast/` (Modell, Splitter, Kalibrierung, Gate) und `tradingagents/dataflows/vendors/eodhd.py` plus `…/archive/`. Import der Extra-Pakete **nur** in diesen Modulen. Tests mit `pytest.importorskip` und den Mustern aus `tests/test_ci_optional_deps.py` absichern, damit die Kerninstallation ohne das Extra grün bleibt.
- `tests/test_ci_optional_deps.py` um das Extra `forecast` erweitern (sonst werden Tests still übersprungen).
- Der EODHD-API-Key gehört in `.env` (Variable `EODHD_API_KEY`), in CI nur als Secret. Der tägliche Lauf in GitHub Actions braucht den Key nur, wenn dort Merkmale gerechnet werden. Empfehlung: Archiv und Merkmale **lokal**, CI rechnet nur Berichte aus abgeleiteten Daten.

## Betrachtete Alternativen

| Empfohlen | Alternative | Wann die Alternative besser ist |
|---|---|---|
| EODHD Historian + Fundamentals-Monate | EODHD All-in-One (99,99 €/Monat bzw. 83,33 € im Jahresabo) | Wenn News-Sentiment von EODHD oder Intraday-Daten benötigt werden; kostet aber etwa 40–60 € mehr pro Monat als die Splittung. |
| Eigenes Größen- und Liquiditätsuniversum | Gekaufte STOXX-600-Historie (STOXX direkt oder LSEG) | Wenn die Index-Treue für das Gate zwingend ist und ein Einmalpreis unter etwa 200 € zu bekommen ist (Anfrage, Ergebnis offen). |
| Eigener Purged-Walk-forward | skfolio 1.9.6 | Wenn später echte Portfolio-Optimierung (Mean-Variance, Risk Parity) gebraucht wird. Dann bringt skfolio Splitter und Optimierer zusammen mit. |
| LogReg + LightGBM | XGBoost / CatBoost | Kein Vorteil auf dieser Datengröße; LightGBM ist schneller und auf Windows unkompliziert. |
| CLI-Labeler | Streamlit 1.66 | Wenn mehrere Personen labeln oder Bilder und PDFs gezeigt werden müssen. |
| GDELT + Emittenten-IR + EQS | Kommerzielle Newsfeeds (Dow Jones, Bloomberg, RavenPack) | Nur mit deutlich höherem Budget; historischer Backfill wäre dann kaufbar. |

## Was NICHT verwenden

| Vermeiden | Warum | Stattdessen |
|---|---|---|
| mlfinlab | Kommerzielle Lizenz | eigener Splitter, `arch` für Bootstrap und SPA |
| timeseriescv | Seit 2018 unverändert, Alpha | eigener Splitter |
| `CalibratedClassifierCV(cv="prefit")` | In sklearn ≥1.8 entfernt | `FrozenEstimator` |
| Isotonische Kalibrierung bei <1.000 Fällen | Überanpassung (sklearn-Doku) | sigmoid (Platt) |
| `TimeSeriesSplit(gap=…)` als „Purging“ | Keine Label-Überlappungs-Entfernung, kein Embargo | eigener `PurgedWalkForward` |
| yfinance-Historien für Backtests | Rückwirkend adjustiert, keine delisteten Titel (N-04, H-12) | EODHD roh plus eigene Adjustierung aus Splits und Dividenden |
| NewsAPI.org Developer | Produktionsnutzung verboten, 24 h Verzögerung | GDELT, Emittenten-IR, EQS |
| FMP für Europa | Nur im teuersten Plan, Preis nicht verifiziert | EODHD |
| Norgate, Tiingo, MarketParquet, Sharadar | Keine europäischen Aktien | EODHD |
| IBKR als Historienquelle | Keine delisteten Titel, Fundamentaldaten-API entfernt, Pacing-Limits | nur Ausführung und Live-Kurse |
| Anbieter-SDKs (`eodhd`, `finnhub-python`, `fmpsdk`) | Eigener HTTP-Stack, TLS und Retry kaum steuerbar, Mocking schwer | dünner Client über `requests` |
| DuckDB `httpfs` / `read_parquet('https://…')` | Eigener TLS-Pfad an AVG vorbei (Risiko) | Download über `requests`, lokal lesen |
| Streamlit, Dash, Jupyter als Laufzeitabhängigkeit | Schwer, eigene Angriffsfläche in pip-audit | CLI oder statische HTML-Seite |
| Volltexte oder Lizenzdaten im Repo | Öffentlicher Fork; EODHD nur zur Privatnutzung; § 44b UrhG verlangt Löschung nach Zweckerfüllung | lokales Archiv außerhalb von git |

## Varianten

**Falls der Backfill-Monat zeigt, dass EODHD `filing_date` für EU-Titel lückenhaft ist:**
- Fundamentaldaten konservativ verzögern: verfügbar ab `period_end + 90 Tage` (Quartal) bzw. `+120 Tage` (Jahr) oder ab `Earnings.History.reportDate`, je nachdem was später ist.
- Begründung: Lieber verspätet als ein Look-ahead. Die Annahme kommt ins Validierungsprotokoll.

**Falls das Budget für LLM-Läufe nicht reicht:**
- Das LLM nur für Merkmale auf Meldungstagen einsetzen (ereignisgetrieben), nicht täglich je Titel.
- Begründung: Ad-hoc-Tage sind selten, das Kursmodell läuft ohne LLM-Kosten.

**Falls US später dazukommt (nicht M3):**
- EODHD deckt US mit ab; die S&P-500-Historie ist im Fundamentals-Feed enthalten. Norgate wäre dann die Alternative mit höherer Qualität.

## Versionsverträglichkeit

| Paket | Verträglich mit | Hinweis |
|---|---|---|
| scipy 1.18.1 | Python ≥3.12 | CI testet 3.11, daher Untergrenze statt Pin; die Auflösung auf 3.11 im CI-Lauf belegen. |
| scikit-learn 1.9.1 | Python ≥3.11, numpy 2.x | venv hat numpy 2.3.0 |
| exchange_calendars 4.13.2 | tzdata ≥2025.2 | `ib_async 2.1.0` deckelt `tzdata<2026.0`; installiert ist tzdata 2025.2 |
| pandas 3.0.6 (vorhanden) | pyarrow ≥… optional | pyarrow ist heute nicht installiert, Parquet über pandas braucht es |
| lightgbm 4.7.0 | Windows x64 | MSVC-Runtime nötig; Wheel ist `py3-none`, damit auch auf 3.14 |
| statsmodels 0.15.0, duckdb 1.5.6 | Python 3.14 | Klassifikatoren listen 3.14; das Wheel für cp314/win_amd64 ist **nicht einzeln geprüft**, die CI-Matrix ist der Beleg |
| arch 8.0.0 | statsmodels, scipy | Das Release liegt ein Jahr zurück; mit pandas 3 nicht getestet (**prüfen**) |

## Quellen

- EODHD Preise (abgerufen 2026-10-20): https://eodhd.com/pricing (HOCH für Preise und Planinhalte)
- EODHD Fundamentals-Doku (filing_date, Europa seit 2000, historische Indexmitglieder nur S&P 500): https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds (MITTEL)
- EODHD delistete Titel: https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours, https://eodhd.com/financial-apis/review-delisted-stock-companies-data (MITTEL)
- EODHD S&P/DJ Historical Constituents (29,99 $/€ pro Monat, bis 12 Jahre): https://eodhd.com/financial-apis/sp-and-dow-jones-indices-historical-constituents-data-api, https://eodhd.com/lp/spglobal (MITTEL)
- Ticker-Wiederverwendung bei EODHD: https://incoherency.co.uk/notes/20260507.html (NIEDRIG)
- FMP-Pläne (offizielle Seite 403): https://site.financialmodelingprep.com/es/pricing-plans, https://datarade.ai/data-providers/financial-modeling-prep/profile (NIEDRIG); historische Mitglieder nur S&P/DJ: https://site.financialmodelingprep.com/de/developer/docs/stable/historical-sp-500
- Norgate Abdeckung: https://norgatedata.com/ (MITTEL); Tiingo: https://marketparquet.com/vs/tiingo (NIEDRIG); MarketParquet: https://marketparquet.com/vs/norgate
- LSEG STOXX-600-Historie: https://community.developers.lseg.com/discussion/109569/how-to-get-data-on-companies-that-have-been-listed-on-the-stoxx-europe-600-from-2015-2022
- IBKR Fundamentaldaten entfernt: https://fxnewsgroup.com/?p=41289, https://support.quantrocket.com/t/no-longer-able-to-collect-reuters-estimates-from-ibkr/1709 (MITTEL); Marktdatenpreise: https://www.interactivebrokers.com/ibis/marketData.php (NIEDRIG)
- RNS-Lizenz 2026: https://www.lseg.com/content/dam/lseg/en_us/documents/rns/rns-pricing-and-policy-guidelines-2026.pdf; Investegate: https://www.investegate.co.uk/rss, https://stockopedia.com/content/rns-rss-feed-346608
- EQS News: https://www.eqs-news.com/ (kein RSS gefunden)
- Euronext-Feeds: https://help.presspage.com/hc/en-us/articles/8068809777436
- GDELT: https://www.gdeltproject.org/about.html, https://github.com/kepler471/gdelt-doc-api, https://pypi.org/project/gdeltdoc/
- NewsAPI: https://newsapi.org/pricing (MITTEL)
- Finnhub: https://help.bindtuning.com/en/articles/344526-stocks-ticker-web-part-is-blank-finnhub-and-third-party-data-provider-changes (NIEDRIG)
- ESAP-Zeitplan: https://www.regnology.net/en/resources/regulatory-topics/european-single-access-point-esap/, https://www.dfsa.dk/financial-themes/capital-market/esap
- § 44b UrhG: https://www.gesetze-im-internet.de/urhg/__44b.html (HOCH für den Gesetzestext)
- scikit-learn Kalibrierung: https://scikit-learn.org/stable/modules/calibration.html (HOCH)
- PyPI (Versionen und Daten, HOCH): scikit-learn, lightgbm, statsmodels, scipy, duckdb, pyarrow, streamlit, feedparser, exchange-calendars, arch, skfolio, purgedcv, timeseriescv, gdeltdoc unter https://pypi.org/project/<name>/
- Purged-CV-Alternativen: https://github.com/eslazarev/purged-cross-validation, https://pypi.org/project/timeseriescv
- exchange_calendars XETR/XLON: lokal geprüft in `.venv/Lib/site-packages/exchange_calendars/exchange_calendar_xetr.py` (Z. 59–126) und `exchange_calendar_xlon.py` (Z. 193–195); Deutsche Börse Kalender: https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours

---
*Stack-Recherche für: M3 Vorhersage-Engine (Europa)*
*Recherchiert: 2026-10-20*
