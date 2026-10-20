# Recherche-Zusammenfassung: M3 Vorhersage-Engine (Europa)

**Projekt:** TradingEngineX, Meilenstein M3 (vorbereitet, noch nicht aktiv; M2-Phase 6 läuft)
**Domäne:** kalibrierte Wahrscheinlichkeitsprognose P(Titel schlägt Benchmark nach Kosten), 5 und 20 Handelstage, europäische Aktien; hybrid aus statistischem Modell und LLM-Merkmalen/Veto; Walk-forward-Validierung, Sizing, Paper-Betrieb über IBKR, vorregistriertes Go/No-Go-Gate
**Recherchiert:** 2026-10-20
**Gesamtvertrauen:** MITTEL (Methodik und Code-Integration HOCH; Anbieterabdeckung, Steuersätze, LLM-Kosten und Effektgrößen MITTEL bis NIEDRIG)
**Grundlage:** `.planning/MILESTONE-CONTEXT.md`, `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` (alle in diesem Ordner)

---

## Executive Summary

M3 baut keinen Handelsroboter, sondern eine **Nachweismaschine**. Ein schlankes statistisches Modell (regularisierte Logit-Regression, LightGBM nur als gezählter Herausforderer) gibt je Titel und Horizont eine kalibrierte Wahrscheinlichkeit aus. Ein billiger LLM-Extraktor liefert dazu je Meldung strukturierte Merkmale. Die volle Agenten-Pipeline läuft nur noch für eine kleine Shortlist und darf dort ein Veto einlegen, das nur verkleinern kann. Danach folgen Kosten, Sizing und Risiko, das Ergebnis geht als `targets.json` an den IBKR-Ausführer. So bauen Fachleute das: zuerst point-in-time-Daten, **dann der Messrahmen und erst dann das Modell**. Dazu gehören Purged Walk-forward mit Embargo, Baselines in derselben Kostenpipeline, ein Variantenregister mit Deflated Sharpe sowie Block-Bootstrap-Konfidenzintervalle nach Stichtag. Das Ganze steht in einem eigenen Strang-Paket `tradingagents/forecast/` und braucht **keine zwingende Änderung am Upstream-Kern**.

Die Recherche zeigt: Mehrere gesetzte Operator-Entscheidungen sind **so, wie sie formuliert sind, nicht umsetzbar** oder gefährden die Aussagekraft. Das betrifft vor allem das Gate. Bei 20 Tagen Horizont und realistischer Querschnittskorrelation (ρ = 0,05–0,10) sind 300 *effektiv unabhängige* prospektive Fälle in 6 Monaten mathematisch nicht erreichbar, egal wie groß das Universum ist: Die Untergrenze liegt bei 14–29 Monaten. Die pauschalen 20 bp pro Seite unterschätzen Käufe in UK, IE, FR, IT und ES um 20–100 bp. Die volle LLM-Pipeline über das Universum sprengt das Budget ab etwa 40 Titeln. Eine historische STOXX-600-Zusammensetzung ist im Budget nicht zu kaufen. Gekaufte Daten und News-Texte dürfen nicht in den öffentlichen Fork. Für jeden Punkt gibt es eine konkrete Anpassung (Abschnitt „Konflikte mit gesetzten Entscheidungen“). Diese Anpassungen gehören **vor** Beginn der Datenarbeit in ein Präregistrierungsdokument (P0), sonst entsteht später die Versuchung, das Gate nach Sichtung der Daten umzudefinieren.

Das wahrscheinlichste Ergebnis ist ein **ehrliches No-Go**. Die Teststärke-Rechnung verlangt eine Netto-Überrendite von etwa 13,5 % brutto p. a. bei 20 Tagen bzw. 37 % bei 5 Tagen. Das liegt über allem, was die Literatur für Long-only-Signale europäischer Large Caps nach Kosten belegt. Der Plan muss No-Go als regulären Ausgang behandeln und einen **frühen, billigen Abbruchpunkt** einbauen: den historischen Walk-forward-Bericht des Statistikmodells ohne LLM-Kosten. Der einzige wirklich zeitkritische Schritt ist der **sofortige Start des News-Archivs**. Jeder Tag ohne Archiv fehlt unwiederbringlich als prospektive LLM-Evidenz, weil LLM-Merkmale auf historischen News durch das Trainingswissen des Modells kontaminiert sind.

---

## Wichtigste Befunde

### Empfohlener Stack

Datenanbieter ist im Budget praktisch nur **EODHD**: Norgate, Tiingo, Sharadar und MarketParquet decken Europa nicht ab, FMP verlangt den teuersten Plan, LSEG ist institutionell bepreist, und IBKR hat `reqFundamentalData` entfernt. Echte PIT-Fundamentaldaten entstehen nur näherungsweise über `filing_date` und ab jetzt durch eigene, datierte Snapshots. Modellierung und Statistik laufen über bewährte Bibliotheken. Den Purged-Walk-forward-Splitter baut das Projekt selbst (etwa 80 Zeilen), weil mlfinlab kommerziell ist und die freien Alternativen tot oder im Alpha-Stadium sind. Alles kommt in ein neues optionales Extra `forecast` nach dem Muster von `ibkr`.

**Kerntechnologien:**
- **EODHD Historian** (Jahresabo 16,66 €/Monat): EOD-Kurse Europa inklusive delisteter Titel; einzige bezahlbare Quelle mit EU-Delistings
- **EODHD Fundamentals** (59,99 €, nur einzelne Monate buchen): Backfill einmalig aus dem 300-€-Topf, danach ein Monat pro Quartal nach der Berichtssaison (Mittel etwa 20 €/Monat)
- **scikit-learn 1.9.1**: Logit-Baseline, Kalibrierung über `CalibratedClassifierCV(FrozenEstimator(m), method="sigmoid")` (`cv="prefit"` ist entfernt); isotonic erst ab etwa 1.000 Kalibrierfällen
- **LightGBM 4.7.0**: nur als gezählte Herausfordererin, wenn Logit OOS Auflösung zeigt
- **statsmodels 0.15 + arch 8.0**: HAC- und Cluster-Fehler, `multipletests`, StationaryBootstrap, SPA/StepM (Mehrfachtest-Kontrolle)
- **DuckDB 1.5.6 + pyarrow + Parquet**: append-only, bitemporale Ablage mit `ASOF JOIN`; kein `httpfs` (AVG-TLS)
- **exchange_calendars 4.13.2** (vorhanden): alle EU-MICs; Pin `>=4.13,<5` wegen der `tzdata<2026`-Obergrenze von `ib_async`
- **feedparser + requests**: News-Archivierer mit eigenem TLS-Pfad (AVG-Bundle); keine Anbieter-SDKs
- **questionary + rich** (vorhanden): Label-Oberfläche im Terminal, null neue Abhängigkeiten

**Versionsfallen:** scipy 1.18 braucht Python ≥3.12, die CI testet 3.11, deshalb Untergrenze statt Pin. `arch` 8.0 ist mit pandas 3 ungetestet.

### Erwartete Funktionen

**Pflicht (ohne sie ist jede Gate-Aussage wertlos):**
- Versionierte Label-Spezifikation `y_h = 1[r_i − r_B − 2·c_i > 0]` mit **Kosten je Titel/Land**, Total Return, einheitlicher Währung (EUR) und fester Einstiegskonvention
- PIT-Datenbasis mit Universum je Stichtag, Delisting-Renditen und Kapitalmaßnahmen
- Purged Walk-forward mit Embargo ≥ h in Handelssitzungen je Primärbörse
- Sechs Baselines in derselben Kostenpipeline: Benchmark, Klimatologie, Zufall (≥1000×), Momentum 12-1, Kurzfrist-Reversal, bestehende LLM-Engine
- Block-Bootstrap-KI nach Stichtag, Variantenregister ab dem ersten Experiment, Deflated Sharpe
- Fallzahl in drei Formen berichtet: roh, nicht überlappend, effektiv nach Designeffekt
- Kalibrierungsbericht: Brier mit Murphy-Zerlegung, BSS gegen Klimatologie, Log-Loss, Reliability-Diagramm mit Bootstrap-Bändern, Slope und Intercept; ECE nur ergänzend
- Sizing: Vol-Targeting, Edge über Break-even mit Hysterese, Kelly nur als Deckel (¼–½), Notional-Limits, Drawdown- und Tagesverlust-Kill, Modell-Gesundheitsstopp
- Vorregistriertes Go/No-Go-Protokoll mit Teststärke-Rechnung und binären Prüfpunkten

**Differenzierend (für Entscheidung 3 und 8 nötig):**
- LLM-Extraktor je Meldung mit festem JSON-Schema (Relevanz, Ereignistyp aus ≤12 Klassen, Sentiment, Konfidenz, Neuheit), Temperatur 0, gepinnter Snapshot, Cache
- Aggregation mit Abklingen (τ ≈ 3 d bzw. 10 d) zu 3–5 Textmerkmalen je Titel und Tag
- Gepaarte Ablation mit und ohne LLM auf denselben Fällen, dazu Veto im Schattenmodus mit Kontrafaktum
- Blindes Labeling (~50 Meldungen/Monat, stratifiziert, 10 % Wiederholungen für Intra-Rater-κ); nur zur Evaluation, nie zum Training
- Datenqualitätsstatus je Tag und Quelle, mit Sperre neuer Positionen
- Entity-Masking als gezählte Variante

**Zurückstellen:** PEAD mit Konsensdaten (über Budget), Boosting und PBO erst nach Logit-Auflösung, Beta-Hedge über Future (v2), US-Universum (Entscheidung 1), Analystenrevisionen aus Lizenzdaten.

**Bewusst nicht bauen:** LLM als direkter Prognosegeber, historischer Backtest von LLM-Merkmalen, Accuracy oder AUC als Erfolgsmaß, Feature-Mining ohne Register, Kelly als Treiber, enge Einzeltitel-Stops (schädlich bei Reversal), Schwelle „Brier 5 % besser“ (realistisch sind 0–2 % BSS), Verlängern der OOS-Periode, „bis es reicht“.

### Architektur

Zwei getrennte Messreihen. Das Upstream-Settlement (`decision-log.md`, `next_close`, yfinance, ohne Kosten) bleibt unverändert die Lernschleife des LLM. Die Gate-Abrechnung läuft in einem eigenen Forecast-Ledger: EUR, netto, 5 und 20 Tage, `next_open`, Kurse aus dem PIT-Store. Die Pipeline ist als reiner Kern mit dünnen I/O-Rändern gebaut, wie im IBKR-Strang. Damit fahren Backtest und Live-Lauf denselben Code. Gerechnet wird abends (~20:40–22:00 UTC) in GitHub Actions eines **privaten Begleit-Repos**, ausgeführt wird lokal am nächsten Morgen nach der Eröffnungsauktion.

**Hauptkomponenten:**
1. `forecast/archive/` + `scripts/news_archive.py`: append-only Archiv mit `published_ts`, `first_seen_ts`, Hash und Tagesstatus
2. `forecast/universe.py`, `calendars.py`, `ingest.py`, `store.py`: Universum je Stichtag (ISIN, MIC, Währung), Kalender je MIC, bitemporaler Feature-Store (`knowledge_ts <= cutoff`)
3. `forecast/labels.py`, `costs.py`, `settle.py`, `walkforward.py`, `baselines.py`, `gate.py`: Messrahmen, **vor** dem Modell gebaut
4. `forecast/model.py` + `registry.py`: unveränderliche Artefakte ohne Pickle, `ACTIVE.json` im Gate-Zeitraum eingefroren
5. `forecast/llm_features.py` + `veto.py`: Extraktor mit Cache; Veto aus der Shortlist-Pipeline, nur verkleinernd
6. `forecast/sizing.py`, `risk.py`, `decide.py`, `scripts/forecast_daily.py`: Zielstückzahlen in `targets.json` (`schema_version: 1`), kontrafaktisches Logging je Stufe
7. Ausführer-Erweiterung im Strang: `ibkr_targets.py` (`plan_target`: Ziel − Ist − offen, schließt N-07), Kalender je MIC, ISIN- und Primärbörsen-Auflösung, Notional-Cap, gestaffelter Abbaupfad (schließt N-08), Währungsregel

**Feste Regeln:** Den Schlüssel `entry` in der SETTLEMENT-Zeile nie umdeuten, sonst bleibt der Eintrag dauerhaft `pending`. Neue Schlüssel nur additiv mit eigenem Namen. Kein Sizing im Ausführer (REQ-IBKR-68). Kein stilles Nachtrainieren im Gate-Zeitraum.

### Kritische Fallstricke

1. **LLM-Wissensleck.** Historische LLM-Läufe „erinnern“ sich an spätere Ausgänge. *Gegenmittel:* LLM-Merkmale zählen nur prospektiv, für News nach dem Cutoff des gepinnten Snapshots. Snapshot-ID und Cutoff stehen in jedem Datensatz, Merkmale werden nie neu extrahiert. Ein Ära-Konzept regelt den Modell-Ruhestand (Anthropic garantiert nur 60 Tage Vorlauf).
2. **Falsches N und ein unerreichbares Gate.** Bei 20 Tagen sind 95 % der täglichen Stichproben überlappend, die Titel am selben Stichtag korrelieren. *Gegenmittel:* „unabhängig“ vorab rechnerisch definieren (Titel × nicht überlappendes Fenster, korrigiert um den Designeffekt mit geschätztem ρ), Poweranalyse in P0, historischen Walk-forward anrechnen.
3. **Kostenunterschätzung.** FTT und Stempelsteuer kommen hinzu, ebenso Mindestgebühren: Der erste Paper-Fill kostete 29 bp einseitig. *Gegenmittel:* Kostenmodell je Titel und Seite als einzige Quelle der Wahrheit für Label, Simulator und Sizing; 20 bp nur als Untergrenze, dazu eine ×2-Sensitivität.
4. **Survivorship und PIT-Verletzungen.** Dazu zählen heutige Indexmitglieder, rückwirkend adjustierte Yahoo-Kurse, Fundamentaldaten nach Periodenende statt nach Veröffentlichung und GBp/GBP. *Gegenmittel:* eigenes Universum je Stichtag einschließlich Delistings, unbereinigte Kurse plus eine Tabelle der Kapitalmaßnahmen, Abnahmetest mit drei bekannten Delistings und einer Bezugsrechtsemission, Rekonstruktionstest mit 20 bitgleichen Entscheidungen.
5. **Mehrfachtests und Versionsdrift.** Bei 20 Varianten besteht mit 88 % Wahrscheinlichkeit mindestens eine zufällig. Parallele Sessions und Upstream-Rebases mischen Prompt-Stände. *Gegenmittel:* Präregistrierung mit Hash, den CI prüft; Variantenregister; jede Prognose trägt Code-, Modell-, Prompt- und Kalibrierer-Hash; der Prognosepfad liegt außerhalb des Upstream-Kerns.

Weitere relevante Fallstricke: Paper ist ein Mechaniktest, kein Kostentest (keine Auktionsorders, keine Steuern; Schattenbuch nötig). Der Drawdown über 6 Monate ist eine einzige Pfadrealisation. Archivlücken dürfen nicht als „keine News“ gelesen werden (`missing` ist ein eigener Wert). Prompt-Injection über News-Texte. DST-Verschiebung bei UTC-Cron.

---

## Konflikte mit gesetzten Entscheidungen

Die folgenden Punkte zeigen, wo eine gesetzte Operator-Entscheidung (MILESTONE-CONTEXT, 1–8) so, wie sie formuliert ist, nicht trägt. Jede Anpassung gehört in das Präregistrierungsdokument (P0), **bevor** Daten gesichtet werden.

### K1: Gate „≥ 300 unabhängige Fälle und ≥ 6 Monate OOS“ (Entscheidung 6)

**Befund:**
- Bei 20 Tagen Horizont zählen je Titel nur 21/20 = 1,05 nicht überlappende Fenster pro Monat.
- Querschnittskorrelation der Residualrenditen ρ = 0,05–0,10 (Annahme, in P2 zu schätzen). Der Designeffekt begrenzt die effektiven Fälle auf höchstens 21/(h·ρ) pro Monat, unabhängig von der Universumsgröße.

| Horizont | U = 30, ρ = 0,05 | U = 100, ρ = 0,05 | U → ∞, ρ = 0,05 | U → ∞, ρ = 0,10 |
|---|---|---|---|---|
| 20 T | 23,3 Monate | 17,0 Monate | **14,3 Monate** | **28,6 Monate** |
| 5 T | 5,8 Monate | 4,3 Monate | 3,6 Monate | 7,1 Monate |

- Zählen nur *gehandelte* Positionen (Top-5), braucht 20 T selbst ohne Korrelation **57 Monate**.
- 6 Monate bei 20 T enthalten nur **6,3 unabhängige Zeitperioden**. Ein nach Stichtag geclustertes KI hat dann etwa 5 Freiheitsgrade (t = 2,015 statt 1,645).
- Nachweisbare Mindestgröße bei N_eff = 300 (σ_idio 25 % p. a.): **0,67 % netto je 20-T-Fall, ≈ 13,5 % brutto p. a.** Bei 5 T sind es 0,33 % netto je Fall, ≈ 37 % brutto p. a. Beides liegt über der Literaturevidenz.
- Jede weitere Variante kostet: Bonferroni bei 20 Varianten verlangt etwa 2,9-mal so viele Fälle.

**Empfehlung:**
1. „Unabhängiger Fall“ wird in P0 rechnerisch definiert: (Titel × nicht überlappendes Fenster) über **alle Prognosen des Universums**, nicht nur über Trades. Die effektive Zahl ergibt sich nach dem Kish-Designeffekt mit empirisch geschätztem ρ. Berichtet werden immer roh, nicht überlappend und effektiv.
2. **Der historische, präregistrierte Walk-forward zählt auf das Gate** als Hauptbeleg für das Statistikmodell: mehrere Jahre, mit unberührter Holdout-Periode, die nur einmal ausgewertet wird. Die 6 Monate prospektiv dienen der **Bestätigung**: kein signifikanter Bruch, Kalibrierung stabil, Ausführung sauber.
3. Das LLM-Inkrement wird **gepaart** auf denselben prospektiven Fällen getestet (Brier- bzw. Alpha-Differenz, Diebold-Mariano bzw. Bootstrap). Ist es nach 6 Monaten nicht entscheidbar, lautet das Ergebnis „unentschieden“, nicht „kein Effekt“.
4. Präregistriert wird auch die Gewichtung der Horizonte. Mein Vorschlag: 5 T wird prospektiv gegatet, 20 T wird prospektiv berichtet.
5. Eine Verlängerungsregel wird vorab festgelegt. Eine Verlängerung ist eine neue, getrennt ausgewertete Periode, kein optional stopping.

### K2: Kosten „20 bp pro Seite“ (Entscheidung 6)

**Befund:** Kaufseitige Abgaben kommen zu Kommission und Spread hinzu:

| Land | Abgabe auf Käufe | Konfidenz |
|---|---|---|
| UK (Stamp Duty/SDRT) | 0,5 % | HOCH |
| Irland | 1 % | MITTEL |
| Frankreich (FTT, Large Caps > 1 Mrd €, Liste 2026: 121 Titel) | 0,4 % seit 04/2025 | MITTEL |
| Italien (FTT) | 0,2 % seit 01/2026 | MITTEL |
| Spanien (FTT, > 1 Mrd €) | 0,2 % | MITTEL |
| Belgien (TOB) | ungeprüft | NIEDRIG |

- Ein 5-T-Roundtrip in einer UK-Aktie kostet damit **> 70 bp** statt 40 bp.
- Mindestgebühren: Der erste Paper-Fill kostete 1,00 USD auf 342,86 USD, also **29 bp einseitig**.
- Bei vollem Umschlag mit 5 T entstehen schon mit 20 bp pro Seite etwa **1,6 % Kosten pro Monat**.
- Mit Pauschalkosten lernt das Modell „Land“ statt Signal, weil die Basisrate des Labels je Land unterschiedlich ist.

**Empfehlung:**
- **Kostenmodell je Titel und Seite:** IBKR-Tarif mit Minimum auf die tatsächliche Ordergröße, halber Spread nach Liquiditätsklasse, Steuer nach Land, Sitz und Jahresliste (FR: BOFiP, IT: Consob; ein Test schlägt fehl, wenn eine Liste älter als 13 Monate ist), FX-Kosten.
- Label, Simulator, Baselines und Sizing nutzen dieselbe Quelle. 20 bp bleiben die Untergrenze, der Bericht weist zusätzlich ×2 aus.
- Eine Mindestgröße je Order sorgt dafür, dass die Kommission ≤ 10 bp bleibt.
- Alternative (Operator-Entscheidung, siehe O2): Das Kaufuniversum wird auf Länder ohne Kaufabgabe beschränkt (DE, NL, CH; Nordics nur mit FX-Lösung). Dann ist der Benchmark anzupassen.

### K3: Budget 150 €/Monat (Entscheidung 4) vs. Multi-Agenten-LLM je Ticker (Entscheidung 3)

**Befund:**
- Die bestehende Pipeline kostet ≈ 0,18 USD je Ticker und Lauf und braucht etwa 2 min.
- Daten (EODHD Historian + Fundamentals-Monate + ggf. IBKR-L1) kosten etwa 40–50 €/Monat, für LLM bleiben ≈ 100 €.

| Variante (21 Handelstage) | Kosten pro Monat |
|---|---|
| Vollgraph 30 Ticker | ≈ 113 USD |
| Vollgraph 50 Ticker | ≈ 189 USD (sprengt allein das Budget) |
| Vollgraph 100 Ticker | ≈ 378 USD |
| Haiku-Klasse-Extraktor, 100 Ticker | ≈ 10 USD |
| Haiku-Klasse-Extraktor, 600 Ticker | ≈ 59 USD (mit Batch-API ≈ 29 USD) |
| Extraktor 600 Ticker, k = 5 flächendeckend (PRED-04) | ≈ 293 USD |

- Bekannter Code-Befund N-05: Das Budget prüft nur verbuchte Kosten, parallele Calls überschreiten die Grenze.

**Empfehlung:**
- **LLM-Merkmale über einen billigen, gepinnten Extraktor:** ein Call je Meldung, Deduplizierung vor dem Call, Prompt-Caching, Batch-API in der Nacht.
- **Der Vollgraph läuft nur für eine Shortlist** (≤ 5 Kandidaten/Tag; ≈ 19 USD/Monat) als Veto und Begründung.
- PRED-04 (k = 5) wird nur auf einer Stichprobe von 10 % gemessen.
- Das Budget reserviert Kosten vor dem Call (schließt N-05), dazu kommt ein hartes Spend-Limit beim Anbieter.
- Ein Monatsbericht trennt Daten, Extraktion, Veto und Backtest-Topf.
- Erwartete Summe: ≈ 80–110 €/Monat. Das passt ins Budget.

### K4: Daten „point-in-time kaufen“ (Entscheidung 5), STOXX-600-Universum

**Befund:**
- Eine historische Zusammensetzung des STOXX Europe 600 ist im Budget **nicht käuflich**. EODHD führt historische Mitglieder nur für S&P und Dow Jones (Add-on 29,99 €/Monat). FMP ebenso. LSEG kostet einen vierstelligen Betrag pro Monat. Bei STOXX/Qontigo direkt gibt es keinen Listenpreis, nur auf Anfrage.
- Mit heutigen Mitgliedern entsteht Survivorship-Bias, der Momentum und Quality überschätzt.
- PIT-Fundamentaldaten gibt es nur näherungsweise: Bei EODHD ist dokumentiert, dass `filing_date` existiert. Wie Restatements behandelt werden, ist nicht dokumentiert.

**Empfehlung:**
- **Eigenes regelbasiertes Universum je Stichtag:**
  - Börsen XETR, XPAR, XAMS, XBRU, XMIL, XMAD, XLON, XSWX, Primärlinie, **einschließlich delisteter Titel**;
  - Filter nach Median-Euro-Umsatz über 60 Tage bis t−1;
  - Marktkapitalisierung = Kurs(t−1) × Aktienzahl aus dem letzten Bericht mit `filing_date` < t;
  - Top 200–300, quartalsweise neu gebildet.
- Den STOXX Europe 600 Net Return **nur als Benchmark-Zeitreihe** verwenden.
- Fehlt `filing_date`, konservativ verzögern (Periodenende + 90 bzw. 120 Tage).
- Abnahmetests im Backfill-Monat: Startjahr der Delistings je Börse, Ticker-Wiederverwendung (über ISIN abgleichen), Restatements bei 10–20 Titeln, Dividenden und Splits delisteter Titel, Bewertung von Abfindungen.
- Der verbleibende Bias wird im Bericht beziffert.
- Eine einmalige Anfrage bei STOXX ist optional; sie lohnt sich nur bei einem Einmalpreis unter etwa 200 €.

### K5: Betriebsort, öffentlicher Fork (implizit in Entscheidung 5 und 7)

**Befund:**
- Forks öffentlicher Repos sind auf GitHub **zwingend öffentlich**, **Actions-Logs eingeschlossen**.
- EODHD-Pläne erlauben nur Privatnutzung ohne Weitergabe.
- § 44b UrhG erlaubt Text- und Data-Mining, verlangt aber die Löschung nach Zweckerfüllung.
- Der heutige Paper-Lauf läuft in den Actions des öffentlichen Forks. Dort dürfen weder Rohdaten noch News-Texte noch Merkmale aus Lizenzdaten liegen.

**Empfehlung:**
- **Privates Begleit-Repo** für Ingest, Archiv, Merkmale, Prognose und Shortlist-LLM:
  - GitHub Free: 2.000 private Minuten/Monat, Bedarf etwa 440;
  - Checkout des Fork-Codes an einem gepinnten SHA bzw. Tag;
  - Branch `forecast-log` mit einem einzigen Schreiber.
- Ausführung **lokal** am Morgen.
- Notpfad: vollständig lokaler Lauf mit identischem Code.
- Im öffentlichen Fork liegen nur Code, Tests mit **gekürzten** Fixtures und abgeleitete, nicht lizenzpflichtige Ergebnisse.
- Ein CI-Check prüft Datendateien und `.gitignore`. Der Secret-Scan läuft weiter.

### K6: FX, `CURRENCY_MISMATCH` auf dem USD-Paper-Konto (Entscheidung 1)

**Befund:**
- `ibkr_decision.judge_preview` lehnt ab, wenn die Funds-Währung ≠ Kontowährung ist (`CURRENCY_MISMATCH`, `scripts/ibkr_decision.py:430`). Jeder Kauf in EUR, GBP oder CHF auf dem Paper-Konto mit USD-Basis scheitert dort.
- Ohne explizite Konvertierung entstehen Fremdwährungs-Negativsalden mit Sollzinsen (SEK, DKK, NOK, PLN sind besonders betroffen).
- `settlement.fetch_returns` rechnet „each in its own currency“. Bei GBP- oder CHF-Titeln gegen einen EUR-Benchmark steckt FX im Alpha.
- `PortfolioContext` (Upstream) kennt nur eine Cash-Währung.

**Empfehlung:**
- Alpha und Labels **in EUR** (Total Return, FX aus dem Store).
- Das Universum wird zunächst auf **EUR, GBP und CHF** begrenzt.
- Im Ausführer wird die Prüfung ersetzt: „Währung auf Whitelist **und** ausreichender Cash-Saldo in dieser Währung“. Die Konvertierung erfolgt explizit über FX-Orders mit Kosten im Kostenmodell, statt Auto-FX bzw. Negativsaldo.
- Das Sizing liest NAV und Salden je Währung aus `ibkr-log:portfolio.json`, nicht aus `PortfolioContext`.
- Ob die Basiswährung des Paper-Kontos auf EUR umstellbar ist, ist **nicht verifiziert**. Das wird in P6 geprüft (siehe O5).

### K7: LLM-Wissensleck (Entscheidung 3, „Beiträge getrennt messen“)

**Befund:**
- Datumsfilter begrenzen nur die Eingabe, nicht das, was das Modell aus dem Training weiß. Hinzu kommt der Distraction-Effekt über Firmennamen.
- Die Literatur ist uneins über die Stärke (ChronoGPT moderat; DatedGPT, Look-Ahead-Bench und FinCAD substanziell). Für ein Gate heißt „umstritten“: nicht anrechenbar.
- Anthropic garantiert nur **60 Tage** Vorlauf vor einer Abschaltung. Ein erzwungener Wechsel auf ein Modell mit späterem Cutoff kontaminiert das bisherige Archiv für das neue Modell.

**Empfehlung:**
- **LLM-Merkmale zählen ausschließlich prospektiv**, für News mit `published_at` nach dem dokumentierten Cutoff des gepinnten Snapshots. Der Gate-Code filtert das automatisch. Historische LLM-Läufe sind höchstens Smoke-Tests, markiert als „kontaminiert“.
- **Ära-Konzept:** Eine Ära ist ein Snapshot mit Cutoff und Prompt-Hash. Merkmale werden eingefroren und nie neu extrahiert. Ein Modell- oder Prompt-Wechsel startet eine neue Ära mit eigener Uhr, die Ären werden getrennt berichtet.
- Bei jedem Wechsel läuft eine Memorization-Probe. Dazu kommt Entity-Masking als gezählte Variante.
- Der historische Walk-forward nutzt nur Kurs- und Fundamentalmerkmale.

### Weitere Spannungen (nachrangig, aber vorab in P0 festzulegen)

- **Drawdown ≤ 15 % (Entscheidung 6):** Ein Long-only-Portfolio mit Beta ≈ 1 kann allein durch den Markt über 15 % fallen (2022: etwa −20 %). Über 6 Monate ist es eine einzige Pfadrealisation. Empfehlung: Vorab festlegen, ob absolut oder relativ zum Benchmark gegatet wird. Dazu die DD-Verteilung aus einem Block-Bootstrap des Backtests und ein Betriebs-Kill bei 10 %/Tag 2 % (siehe O8).
- **Kalibrierung (Entscheidung 6, PRED-03-Entwurf):** „Wird berichtet“ ist richtig. Die Entwurfsschwelle „Brier 5 % besser“ bzw. eine ECE-Schwelle von 0,05 ist bei N_eff = 300 nicht messbar: Der Bin-Standardfehler liegt bei etwa 9 pp, die ECE allein durch Rauschen bei 0,05–0,07. Höchstens eine Plausibilitätsschwelle (Slope-KI enthält 1, BSS ≥ 0).
- **Jev-Labels (Entscheidung 8):** n = 50/Monat ergibt ±11 pp Unsicherheit. Labels werden kumuliert ausgewertet (~300 nach 6 Monaten), blind, mit Codebuch und 10 % Wiederholungen (κ < 0,6 bedeutet: als Ground Truth ungeeignet).
- **Einstiegskonvention:** IBKR Paper unterstützt keine Auktionsorders (MOO/MOC). Bei `next_open` wird mit Limit-Orders nahe der Eröffnung angenähert und die Abweichung gemessen. Die Gate-Rendite kommt aus dem Schattenbuch und dem Kostenmodell, nicht aus Paper-Fills.

---

## Sofort zeitkritisch

**Das News- und Meldungsarchiv muss jetzt starten, noch vor der Aktivierung von M3 und unabhängig von M2-Phase 6.** Begründung:

- LLM-Merkmale zählen nur prospektiv (K7). Jeder Tag ohne Archiv fehlt **unwiederbringlich** in der prospektiven LLM-Evidenz und verschiebt die gepaarte Ablation nach hinten.
- GDELT DOC 2.0 liefert nur die **letzten 3 Monate**. Ein Start heute sichert rückwirkend Metadaten etwa ab Juli 2026. Diese Einträge werden als `backfilled` markiert und zählen nicht für das LLM-Gate, sind aber für die Pipeline-Entwicklung nutzbar. Mit jedem Tag Warten schrumpft dieses Fenster.
- Der Aufwand ist klein, der Sammler ist unabhängig vom Rest. Er passt als Quick Task oder als erster Plan.

**Minimalumfang (ohne Scoring):**
- Quellen:
  - GDELT DOC 2.0 täglich (Metadaten, URL, Ton);
  - EQS-News Ad-hoc und Directors' Dealings als HTML-Liste, schonend (1 Abruf/15 min), nach Prüfung der Nutzungsbedingungen;
  - Investegate-RSS für RNS: nur Überschrift, Zeit, Emittent, Link;
  - Euronext-Feeds je Titel, soweit die URLs schon bekannt sind;
  - IR-Seiten als Fallback.
- Felder: `published_at` (Quelle), `first_seen_ts`/`captured_at` (eigene Uhr, UTC), Quelle, URL, Emittent/ISIN falls bekannt, Sprache, Hash, Tagesstatus je Quelle (`ok`/`partial`/`missing`). Volltext nur, wo die Lizenz es erlaubt.
- Ablage **außerhalb des öffentlichen Repos** (z. B. `%LOCALAPPDATA%\tradingenginex\archive\` mit Backup, später im privaten Begleit-Repo), append-only.
- Abrufe über `requests` mit dem AVG-CA-Bundle (Rezept in `scripts/PAPER_RUN.md`), nicht über den urllib-Abruf von feedparser. robots.txt und TDM-Vorbehalte werden je Quelle geprüft und vermerkt.
- Der Lauf ist geplant (Task Scheduler oder Actions im privaten Repo). Ein Heartbeat zeigt Archivlücken an.

**Ebenfalls früh, aber nicht so eilig:**
- Den EODHD-Historian im Jahresabo buchen; ab da entstehen eigene, datierte Fundamental-Snapshots.
- Den LLM-Snapshot für den Extraktor festlegen. Rohdaten lassen sich später mit einem gepinnten Modell extrahieren, solange dessen Cutoff vor dem Meldungsdatum liegt und das Modell noch verfügbar ist (60-Tage-Frist).

---

## Vorgeschlagene Phasenfolge

### Abgleich mit dem Entwurf (P1–P6)

| Entwurf | Recherche-Ergebnis | Neu |
|---|---|---|
| – | Präregistrierung und Gate-Präzisierung fehlen als eigener Schritt, sie werden in allen Fallstricken gebraucht | **P0** (neu) |
| – | Das Archiv ist zeitkritisch und unabhängig | **Vorlauf** (sofort, vor P0) |
| P1 Datenbasis | bleibt, plus privates Repo, Kalender je MIC, FX und Universum je Stichtag | **P1** |
| P2 Baselines/Validierung | bleibt, plus Kostenmodell je Land, Label-Spezifikation, Power-Werkzeug, finaler Freeze der Präregistrierung | **P2** |
| P3 Prognosemodell(e) | **aufgeteilt:** Statistikmodell mit historischem Bericht (früher No-Go-Punkt ohne LLM-Kosten) getrennt vom LLM-Teil (nur prospektiv, eigenes Risiko) | **P3** + **P4** |
| P4 Risiko/Sizing | bleibt, als Schattenbetrieb ohne Orders, legt den `targets.json`-Vertrag fest | **P5** |
| P5 Betrieb inkl. Europa | **aufgeteilt:** EU-Ausführer (parallel baubar) getrennt von Betrieb und Paper-Bewährung | **P6** + **P7** |
| P6 Gate | bleibt | **P8** |

### Phasen

#### Vorlauf: News-Archiv starten (sofort, als Quick Task)
**Begründung:** prospektive Uhr für LLM-Evidenz; GDELT-3-Monats-Fenster.
**Liefert:** laufender Sammler mit Tagesstatus, Ablage außerhalb des öffentlichen Repos.
**Vermeidet:** Fallstricke 1 und 14.

#### P0: Präregistrierung und Gate-Präzisierung
**Begründung:** Alle Konflikte K1–K7 müssen entschieden sein, bevor Daten gesichtet werden. Sonst wird p-Hacking über die Fallzählung zur Versuchung (Fallstrick 5 und 7).
**Liefert:** `PREREG.md` (versioniert, Hash, CI prüft Unveränderlichkeit) mit:
- Labeldefinition, Horizonten, Einstiegskonvention, Total Return/EUR;
- Universumsregel, Benchmark und Kostenmodell-Rahmen;
- Baselines und Definition „unabhängiger Fall“;
- Poweranalyse mit offengelegten Annahmen;
- Gate-Struktur: historisch als Hauptbeleg, prospektiv als Bestätigung, LLM gepaart;
- Gewichtung der Horizonte, Alpha- und DD-Definition;
- maximale Variantenzahl, Holdout-Periode, Ära-Regel, Verlängerungsregel.

Dazu: privates Begleit-Repo anlegen, Antworten auf die Operator-Entscheidungen O1–O8.
**Hinweis:** Werte, die erst in P2 messbar sind (ρ, σ_idio), stehen als Annahme mit Aktualisierungsregel drin. Der **endgültige Freeze** folgt am Ende von P2, vor P3.

#### P1: Datenbasis und point-in-time
**Begründung:** Grundlage für Labels und Merkmale.
**Liefert:**
- EODHD-Client (eigener `requests`-Client) und Backfill-Monat mit Abnahmetests;
- `universe.py` (ISIN/MIC/Währung, Universum je Stichtag einschließlich Delistings);
- `calendars.py` (Kalender je MIC, Union- und Intersection-Logik), FX, Benchmark-Serie;
- bitemporaler Store (DuckDB + Parquet);
- Härtung des Archivs (`missing`-Status, Dedupe, Heartbeat);
- Extra `forecast` in `pyproject.toml` und `ci`.

**Adressiert:** DATA-01/03, PIT-Datenbasis.
**Vermeidet:** Fallstricke 2, 3, 9 (GBp/GBP, Kapitalmaßnahmen, Feiertage) und 14.

#### P2: Validierungsrahmen, Kosten und Baselines
**Begründung:** Validierung vor dem Modell, sonst wird das Modell auf den Messrahmen hin gebaut.
**Liefert:**
- `labels.py`, `costs.py` (je Titel, Seite und Land), `settle.py` (EUR, netto, `next_open`);
- sechs Baselines und `PurgedWalkForward`;
- Block-Bootstrap, HAC/Cluster, SPA/StepM, DSR, Variantenregister;
- Power-Werkzeug und ρ-Schätzung, Kalibrierungsbericht;
- Rekonstruktionstest, Bias-Bezifferung des Universums;
- **finaler Freeze der Präregistrierung.**

**Adressiert:** VAL-01 bis VAL-06, PRED-01, PRED-03.
**Vermeidet:** Fallstricke 4, 5, 6, 11 und 16–17.

#### P3: Statistikmodell und historischer Walk-forward-Bericht
**Begründung:** Erster ehrlicher No-Go-Prüfpunkt, noch ohne LLM-Kosten.
**Liefert:**
- Merkmale (Reversal residual, Momentum 12-1, Quality/Value-Kontrollen, Risikomerkmale, gerankt je Datum);
- Logit je Horizont mit Platt-Kalibrierung im Walk-forward;
- `registry.py` (Manifest, ohne Pickle);
- einmalige Auswertung des historischen Holdouts.

**Abbruchregel:** Schlägt das Modell im präregistrierten historischen Holdout die Baselines nicht, wird ein **No-Go-Kandidat** an den Operator eskaliert. Dann ist zu entscheiden, ob P4–P7 überhaupt gebaut werden.
**Vermeidet:** Fallstricke 5, 8 und 11.

#### P4: LLM-Merkmale, Veto und Labeling
**Begründung:** Nur prospektiv messbar, deshalb früh produktiv. Hängt vom Archiv (Vorlauf/P1) und vom Modell (P3) ab.
**Liefert:**
- `llm_features.py` mit Schema, ≤12-Klassen-Taxonomie, Cache, Snapshot-Pin, Ära-Konzept, Memorization-Probe;
- Prompt-Injection-Schutz (nur strukturierte Ausgabe);
- Aggregation mit Abklingen;
- Shortlist-Aufruf von `daily_paper_run.run_ticker` und `veto.py` (nur verkleinernd, Kontrafaktum);
- gepaarte Ablation, PRED-04-Stichprobe;
- blinde Label-Oberfläche (`questionary`/`rich`) mit Codebuch und monatlicher Auswertung;
- reservierendes Budget (N-05).

**Vermeidet:** Fallstricke 1, 12, 13 und 15.

#### P5: Entscheidung, Risiko und Sizing im Schattenbetrieb
**Begründung:** Legt den `targets.json`-Vertrag fest, die Schnittstelle zu P6.
**Liefert:**
- `decide.py`, `sizing.py` (Vol-Target, Edge über Break-even, Hysterese, Kelly-Deckel), `risk.py` (Kappen je Titel, Land und Sektor, DD- und Tages-Kill, Gesundheitsstopp, gestaffelter Abbaupfad);
- `scripts/forecast_daily.py` im privaten Repo (Abendlauf, Morgen-Fallback);
- `forecasts.jsonl` mit kontrafaktischen Zielen;
- Replay-Test bitgleich.

**Adressiert:** RISK-01 bis RISK-05 (Planseite).
**Vermeidet:** Fallstricke 18 und 19.

#### P6: EU-Ausführer
**Begründung:** Parallel zu P3–P5 baubar, sobald das Schema von `targets.json` steht. Setzt **M2-Phase 6 abgeschlossen** voraus (erste echte Order, 06-09/06-10) und den übernommenen **Phase-7-Stand** (`ibkr_publish`, `ibkr_report`, Portfolio-Feed; laut Commits auf `main` bis `e5b18c6` ausgeführt; beim Umschalten festhalten).
**Liefert:**
- `ibkr_targets.py` (`plan_target`, schließt N-07);
- `load_calendar(mic)`;
- ISIN-, Primärbörsen- und Währungsauflösung mit `conId`-Cache;
- `check_notional` und gestaffelte Reduktion (N-08);
- Währungsregel statt `CURRENCY_MISMATCH` (K6);
- Rundung auf Tickgröße;
- IBKR-EU-Berechtigungen und Marktdatenabos.

**Vermeidet:** Fallstricke 9 (Tick, ISIN, Auktion), 21 und 22.

#### P7: Betrieb und Paper-Bewährung (übernimmt M2-Phase 8 und den Rest aus Phase 7)
**Begründung:** Ab hier läuft die 6-Monats-Uhr. Jede Verzögerung vor P5/P6 verschiebt das Gate direkt.
**Liefert:**
- Heartbeat für `forecast-log` und das Archiv;
- Backup einschließlich privatem Repo und IBKR-State (`state_maintenance.py`-Allow-Liste);
- Soll-Ist mit Prognosen, **Schattenbuch** mit eigener Kosten-, Dividenden- und Steuerrechnung, Implementation-Shortfall-Logging;
- Drift-Monitor (PSI, rollierender Brier gegen Klimatologie);
- Budgetbericht;
- monatliche Fortschrittsanzeige mit N_eff und Zeit bis zur Entscheidbarkeit;
- Scheduler in `Europe/Berlin` mit DST-Test.

**Adressiert:** OPS-01 bis OPS-03, DATA-03.
**Vermeidet:** Fallstricke 7, 10, 14 und 21.

#### P8: Go/No-Go-Gate
**Begründung:** Erst nach Ablauf der präregistrierten Dauer und Fallzahl.
**Liefert:**
- Gate-Lauf auf dem präregistrierten Hash;
- binäre Prüfpunkte (Fallzahl, Netto-Alpha-Differenz mit KI, DSR, DD, ×2-Kosten, Kalibrierung, LLM-Inkrement, Ausführung, Datenqualität);
- Protokoll mit Unterschrift des Operators.

Bei Go folgt nur eine gedeckelte Echtgeld-Pilotphase. Bei No-Go wird der Meilenstein regulär beendet.

### Abhängigkeiten und kritischer Pfad

```
Vorlauf (Archiv) ─────────────────────────────────────────────┐
P0 ─▶ P1 ─▶ P2 (Freeze) ─▶ P3 ─▶ P4 ─▶ P5 ─▶ P7 ─▶ [≥ 6 Monate] ─▶ P8
                              │            ▲      ▲
M2-Ph.6 fertig + Ph.7-Stand ──┴────▶ P6 ───┴──────┘   (P6 parallel zu P3–P5, sobald targets.json-Schema steht)
M2-Ph.8 ─────────────────────────────────────▶ geht in P7 auf
```

- **Kritischer Pfad:** P0 → P1 → P2 → P3 → P5 → P7 → Zeit → P8.
- P4 kann teilweise parallel zu P5 laufen. Die LLM-Uhr läuft ohnehin seit dem Vorlauf.
- **Frühester Gate-Termin:** Start von P7 + 6 Monate (nach der empfohlenen Gate-Struktur aus K1). Bei wörtlicher Auslegung von „300 prospektive Fälle“ sind es bei 20 T mindestens 14–29 Monate.
- **Früher Ausstieg:** Am Ende von P3 ist ein begründetes No-Go möglich, bevor LLM- und Betriebskosten entstehen.

### Recherche-Flags

Phasen mit vertiefter Recherche (`/gsd:plan-phase --research-phase`):
- **P1:** EODHD-Abdeckung in der Praxis (Delistings je Börse, `filing_date`, Restatements, Abfindungen), ISIN ↔ Vendor ↔ IBKR-Symbolik, Nutzungsbedingungen der News-Quellen
- **P2:** Bootstrap mit Zeit- und Titelabhängigkeit, Designeffekt-Schätzung, DSR- und SPA-Umsetzung, amtliche Prüfung der Steuersätze
- **P4:** Cutoff und Ruhestandsplan des gewählten Snapshots, Option Open-Weight-Modell, Batch-API-Kosten, Prompt-Injection
- **P6:** IBKR-EU-Routing, Paper-Verhalten bei Auktionen, Steuern und FX, Umstellung der Basiswährung, Tickgrößen-Market-Rules, Marktdatenabos

Standardmuster ohne eigene Recherche:
- **P0:** Dokumentarbeit, Inhalte stehen in dieser Recherche
- **P3:** sklearn-Standard
- **P5:** folgt dem `daily_paper_run`-Muster
- **P7:** folgt M2-Phase 7
- **P8:** Auswertung nach Protokoll

---

## Offene Entscheidungen für den Operator

**O1: Wie wird das Gate in endlicher Zeit entscheidbar (K1)?**
- (a) **(empfohlen)** Zweistufig: Der präregistrierte historische Walk-forward mit Holdout ist der Hauptbeleg für das Statistikmodell. 6 Monate prospektiv bestätigen (kein Bruch, Kalibrierung stabil). Das LLM-Inkrement wird gepaart prospektiv getestet. Fälle sind alle Prognosen des Universums, effektiv nach Designeffekt.
- (b) Wörtlich: ≥ 300 effektiv unabhängige *prospektive* Fälle, bei 20 T also mindestens 14–29 Monate Paper.
- (c) Prospektiv wird nur 5 T gegatet, 20 T nur berichtet, ohne Anrechnung der Historie.

**O2: Wie werden die Kosten in UK, IE, FR, IT und ES behandelt (K2)?**
- (a) **(empfohlen)** Kostenmodell je Titel, Seite und Land (Steuer, Mindestgebühr, Spread, FX). 20 bp als Untergrenze, ×2-Sensitivität, volles Universum.
- (b) Kaufuniversum auf Länder ohne Kaufabgabe beschränken (DE, NL, CH), Benchmark entsprechend anpassen.
- (c) Pauschal 20 bp beibehalten und die Abweichung nur als Einschränkung berichten.

**O3: Welches Universum ersetzt die nicht kaufbare STOXX-600-Historie (K4)?**
- (a) **(empfohlen)** Eigenes Regeluniversum je Stichtag: Top 200–300 nach Größe und 60-Tage-Euro-Umsatz, quartalsweise, einschließlich Delistings, aus EODHD. STOXX 600 nur als Benchmark-Serie.
- (b) Wie (a), zusätzlich eine einmalige Preisanfrage bei STOXX/Qontigo für eine historische Kompositionsdatei (Kauf nur unter etwa 200 €).
- (c) Kleineres festes Universum (30–60 liquide Large Caps zum Stichtag des Backtest-Beginns), mit beziffertem Bias.

**O4: Wo laufen Daten und Rechenlauf (K5)?**
- (a) **(empfohlen)** Privates Begleit-Repo mit GitHub Actions für Ingest, Archiv, Prognose und Shortlist-LLM; Ausführung lokal am Morgen.
- (b) Alles lokal über Windows Task Scheduler; der PC muss abends und morgens laufen.
- (c) Privates Repo für Code und Logs, Rohdaten in einem separaten Objektspeicher.

**O5: Wie wird die Währung behandelt (K6)?**
- (a) **(empfohlen)** Alpha in EUR, Universum EUR/GBP/CHF. Explizite FX-Orders und Cash je Währung. `CURRENCY_MISMATCH` wird ersetzt durch „Währung auf Whitelist und Saldo ausreichend“.
- (b) Basiswährung des Paper-Kontos auf EUR umstellen (Machbarkeit unverifiziert) und Auto-FX zulassen, mit FX-Kosten im Modell.
- (c) Nur Eurozone-Titel, Benchmark EURO STOXX statt STOXX Europe 600.

**O6: Welches LLM liefert die Merkmale, und was passiert beim Modell-Ruhestand (K7)?**
- (a) **(empfohlen)** Gepinnter Anthropic-Snapshot der Haiku-Klasse, Cutoff im Datensatz. Ein Modellwechsel startet eine neue Ära mit eigener Uhr. Alte Merkmale bleiben eingefroren.
- (b) Lokales Open-Weight-Modell mit bekanntem, prüfbarem Cutoff (dauerhaft pinbar, mehr Betriebsaufwand auf Windows).
- (c) Beide parallel; das Open-Weight-Modell dient als Absicherung gegen den Ruhestand.

**O7: Wie wird das LLM-Budget aufgeteilt (K3)?**
- (a) **(empfohlen)** Extraktor je Meldung mit Batch-API und Dedupe für das ganze Universum. Vollgraph nur für ≤ 5 Shortlist-Kandidaten pro Tag als Veto. PRED-04 (k = 5) auf 10 % Stichprobe. Erwartet sind ≈ 80–110 €/Monat gesamt.
- (b) LLM nur ereignisgetrieben an Tagen mit Pflichtmeldungen (am billigsten, weniger Abdeckung).
- (c) Vollgraph täglich für ≈ 25 Titel als Merkmalslieferant, ohne Extraktor (schöpft das Budget aus, schlechter reproduzierbar).

**O8: Welcher Drawdown wird gegatet?**
- (a) **(empfohlen)** Drawdown relativ zum Benchmark ≤ 15 % wird gegatet. Absoluter Drawdown und DD-Verteilung aus dem Block-Bootstrap werden berichtet. Betriebs-Kill bei 10 % absolut bzw. 2 % Tagesverlust.
- (b) Absoluter Drawdown ≤ 15 % wie gesetzt (Long-only mit Beta ≈ 1 kann allein am Markt scheitern).
- (c) Beta-Hedge über Index-Future und absoluter Drawdown (Berechtigungen und Margin nötig, eher v2).

---

## Vertrauensbewertung

| Bereich | Vertrauen | Anmerkung |
|---|---|---|
| Stack | MITTEL | Versionen auf PyPI geprüft (HOCH). EODHD-Preise von der Anbieterseite (HOCH), PIT-Qualität und Delisting-Abdeckung in Europa nur nach Anbieterangabe (NIEDRIG–MITTEL). FMP- und IBKR-Datenpreise nicht verifiziert. |
| Funktionen | MITTEL | Methodik (Kalibrierung, Purging, DSR, Sizing) HOCH. Effektgrößen in Europa nach Kosten auf 5–20 Tagen dünn und gemischt (NIEDRIG–MITTEL). |
| Architektur | HOCH | Integrationspunkte am Code mit Zeilenangaben geprüft. Timing, Vendor-Lieferzeiten und Actions-Minuten MITTEL. LLM-Kosten NIEDRIG. Provenienz-Aussagen ohne aktuellen `git`-Abgleich (git hing). |
| Fallstricke | MITTEL | Statistik und Rechenwege HOCH und von Hand nachvollziehbar. Steuersätze und IBKR-Paper-Verhalten MITTEL. Stärke des LLM-Lecks in der Literatur umstritten. ρ = 0,05–0,10 ist eine Annahme. |

**Gesamtvertrauen:** MITTEL. Die strukturellen Schlüsse (Gate-Dauer, Kostenlücke, Budgetlücke, Fork-Öffentlichkeit, LLM-Leck) sind robust gegenüber den Unsicherheiten. Unsicher sind vor allem Details der Anbieter und die exakten Zahlen.

### Zu klärende Lücken

- **ρ und σ_idio:** In P2 empirisch schätzen, die Poweranalyse vor dem Freeze aktualisieren.
- **EODHD-Datenqualität Europa:** Abnahmetests im Backfill-Monat (P1). Fallen sie durch, Fundamentaldaten konservativ verzögern oder Universum verkleinern.
- **Steuersätze und Abgrenzungen:** amtlich prüfen (FR-, IT-, ES-Listen, Irland, Belgien TOB), dazu Quellensteuersätze für den Steuerstatus des Operators (P2).
- **IBKR Paper:** Ob FTT, Stamp Duty und Dividenden gebucht werden, wie Auktionen behandelt werden, ob die Basiswährung umstellbar ist, aktuelle EU-Mindestkommissionen und L1-Abokosten (P6).
- **Nutzungsbedingungen der News-Quellen:** EQS, Investegate und Euronext-Feed-URLs vor dem Dauerbetrieb prüfen (Vorlauf/P1).
- **Phase-7-Stand:** Beim Umschalten festhalten, welcher Stand übernommen wird. Die Commits auf `main` reichen bis `e5b18c6`, der Abschluss von Phase 7 ist nicht bestätigt.
- **Verträglichkeit:** scipy-Auflösung auf py3.11, `arch` 8.0 mit pandas 3, Wheels für cp314/win_amd64. Nachweis über die CI-Matrix.
- **LLM-Kosten:** Haiku-Klasse-Preise und Meldungsvolumen je Titel in der Berichtssaison (×3) im ersten Monat messen.

---

## Quellen

### Primär (HOCH)
- Code im Arbeitsbaum, Stand 2026-10-20: `tradingagents/memory/log.py`, `settlement.py`, `graph/trading_graph.py`, `default_config.py`, `portfolio.py`, `scripts/daily_paper_run.py`, `ibkr_decision.py` (u. a. `judge_preview`/`CURRENCY_MISMATCH :430`), `ibkr_guards.py`, `ibkr_contracts.py`, `ibkr_paperlog.py`, `ibkr_publish.py`, `ibkr_report.py`, `pyproject.toml`
- Projektplanung: `.planning/MILESTONE-CONTEXT.md`, Codex-Reviews `261019-oxc` und `261018-kof`, Meilenstein-Entwurf `261019-oxc-MILESTONE-DRAFT.md`
- PyPI (Versionen), scikit-learn-Kalibrierungsdoku, GitHub-Doku zur Sichtbarkeit von Forks, § 44b UrhG, EODHD-Preisseite
- Methodik: López de Prado (AFML), Bailey/López de Prado (DSR), Novy-Marx/Velikov 2016, Harvey/Liu/Zhu 2016, Politis/Romano 1994, Gneiting/Raftery 2007, Heston/Sinha 2017, Glasserman/Lin 2023, He/Lv/Manela/Wu 2025

### Sekundär (MITTEL)
- EODHD Fundamentals- und Delisting-Doku; Tax Foundation und IBKR-Gebührenseite; Legifiscal (FR 0,4 %), Bird & Bird (IT 0,2 %); Anthropic Model Deprecations (60 Tage); Xetra-Handelsparameter
- Effekt-Literatur Europa: Blitz et al. 2013, RIBAF 2019, Medhat/Schmeling 2022, Martineau 2022, Lopez-Lira/Tang (versionsabhängig)
- LLM-Look-ahead: DatedGPT, Look-Ahead-Bench, FinCAD (Abstracts)

### Tertiär (NIEDRIG, validieren)
- FMP-Planpreise (offizielle Seite 403), Finnhub-Abdeckung, IBKR-Marktdatenpreise, Investegate- und Euronext-Feed-URLs, STOXX-Fast-Entry-Regeln, IBKR-Paper-Verhalten (Forum), Ticker-Wiederverwendung bei EODHD

---
*Recherche abgeschlossen: 2026-10-20*
*Bereit für die Roadmap: ja, nach Beantwortung von O1–O8 (P0)*
