---
source: codex exec (codex-cli 0.163.0, sandbox read-only), Modell gpt-6.1-sol, Reasoning Effort high
scope: committed HEAD 4a55d2c93f6e70f2f48e50be0fef271b4544b233 (alle Zeilenangaben beziehen sich darauf; Codex las Git-Blobs per git show / git grep). Uncommittete Phase-6-Dateien (scripts/ibkr_executor.py, tests/test_ibkr_execute.py, scripts/IBKR_EXECUTION.md, STATE.md, .planning/debug/) liegen ausserhalb des Umfangs.
date: 2026-10-19
note: nur statische Analyse; Codex fuehrte weder Tests noch Code aus, kein Backtest, keine LLM-API-Kosten (ChatGPT-Konto). Die Rohantwort liegt unveraendert in codex-output.md.
---

# Quick 261019-oxc: Codex-Gegenpruefung der Methoden- und Luecken-Bestandsaufnahme (o31)

**Hinweis zum Lauf:** Ein Versuch, Exit-Code 0, rund 8-10 Minuten, im Hintergrund gestartet (stderr und Exit-Code im Scratchpad). Kein Fehler, kein zweiter Versuch noetig. Der Prompt (`codex-prompt.md`) enthielt H-01..H-12 mit Widerlegungspflicht, Abwesenheitsbeleg-Pflicht und dem festen SHA. Codex hat die o31-Dateien nach eigener Angabe erst nach seinem Urteil zu H-01..H-10 gelesen. 114 `.py`-Dateien unter `tradingagents/`, `scripts/`, `cli/` wurden durchsucht.

**Ergebnis laut Codex:** Ein eigenes probabilistisches Renditeprognosemodell existiert nicht (H-01 bestaetigt), dasselbe gilt fuer ML-/NLP-Pakete und eine Musterschicht im Entscheidungspfad. Die pauschalen o31-Aussagen "keine News-Vorverarbeitung", "Statistik nur nachtraeglich" und "Jev nur REVIEW-Fallback" sind zu korrigieren; die Lueckenliste ist teils veraltet (Security-Scan, erster Paper-Fill) und teils zu optimistisch (REQ-IBKR-23).

## Befunde

Grad: B = unmittelbar durch Code/Suchbefund belegt, W = schriftlicher Bericht (hier nicht wiederholt), I = Schlussfolgerung. S1..S9 verweisen auf das Suchprotokoll in `codex-output.md` (Abwesenheitsbelege mit Mustern, Pfaden, Trefferzahlen, Ankern).

| Nr | Datei:Zeile (4a55d2c) | Grad | Status | Befund |
|---|---|---|---|---|
| H-01 | `pyproject.toml:11`, `agents/managers/portfolio_manager.py:80`, `dataflows/vendors/polymarket.py:129` | B | bestaetigt | Kein Monte-Carlo-, ARCH/GARCH-, Bayes-, Random-Walk- oder Verteilungsmodell (S1/S2). Rating kommt vom LLM-PM; Polymarket liefert externe Ereigniswahrscheinlichkeiten als Eingabe. |
| H-02 | `pyproject.toml:21`, `:28`, `patterns/evaluate.py:42`, `yahoo/market.py:8` | B | teils | Keine scipy/sklearn/statsmodels/NLP-Pakete (S1/S2). "Keine statistischen Bibliotheken" ist zu weit: `pandas`, `stockstats` und ein direkter `numpy`-Import existieren. |
| H-03 | `default_config.py:115`, `llm_clients/factory.py:177`, `agents/post_screen.py:84`, `dataflows/vendors/reddit.py:148` | B | teils | `random.uniform` nur Retry-Jitter. `temperature=None` ist nur der Default; explizite Temperatur wird weitergereicht. Weitere Zufallsquellen sind Kennungen (S3). |
| H-04 | `agents/analysts/market_analyst.py:22`, `:77`, `yahoo/snapshot.py:77`, `portfolio_manager.py:80` | B | bestaetigt | Indikatoren sind LLM-Eingabe; RSI-Schwellen und ATR-Sizing stehen nur als Prompt-Anweisung. Kein numerischer Regelentscheider (S4). |
| H-05 | `scripts/pattern_eval.py:31`, `patterns/evaluate.py:278`, `patterns/signals.py:101`, `graph/setup.py:125` | B | bestaetigt | Sechs deterministische Muster; Nutzung nur innerhalb von `patterns/` und `scripts/pattern_eval.py`, 0 Treffer in `graph/` und `agents/` (S4). |
| H-06 | `yahoo/news.py:167`, `:184`, `agents/post_screen.py:147`, `vendors/stocktwits.py:153`, `analysts/sentiment_analyst.py:114`, `agents/schemas.py:330` | B | teils | Pauschale Abwesenheit falsch: Titel-Deduplizierung globaler Yahoo-News, Ticker-Tag-Filter, StockTwits-Labelzaehlung, optionale Jev-Klassifikation. `overall_score` bleibt LLM-Ausgabe; keine Embeddings/lokalen NLP-Pakete (S1/S2/S5). Paper-Workflow aktiviert Post-Screening nicht (`default_config.py:179`, `daily-paper-run.yml:100`, `daily_paper_run.py:273`). |
| H-07 | `memory/log.py:106`, `:118`, `:124` | B | teils | Keine Aehnlichkeitssuche (S6). Auswahl praeziser: nur abgerechnete Eintraege, optional `resolved <= as_of`, bis zu 5 gleiche und 3 andere Ticker, umgekehrte Einfuegereihenfolge. |
| H-08 | `memory/settlement.py:118`, `backtest.py:223`, `patterns/evaluate.py:67`, `memory/log.py:368`, `portfolio_manager.py:35` | B | teils | Settlement/Summary/Wilson sind nachtraeglich. Aber Indikatoren und Social-Verhaeltnisse sind Entscheidungseingaben, und der PM bekommt fruehere Entscheidungstexte und numerische raw-/alpha-Ergebnisse im Memory-Kontext. |
| H-09 | `ibkr_decision.py:323`, `:336`, `:355`, `agents/schemas.py:146`, `ibkr_broker.py:503` | B | teils | Feste Zielbestandsleiter stimmt; Ordermenge ist Differenz zum Bestand. `Hold` heisst unveraendert halten (skip), nicht null Bloecke. Im Orderpfad keine Konfidenz-/Volatilitaets-/Stop-Felder (S7). `TraderProposal` hat kein `take_profit`, nur `entry_price`, `stop_loss`, `position_sizing`. |
| H-10 | `jev/hooks.py:133`, `:142`, `:152`, `post_screen.py:37`, `:120` | B | teils | In `jev/hooks.py` nur Fallback/Shadow; 0,9 ist konfigurierbarer Default. Repo-weit nicht "nur Fallback": Post-Screening nutzt Relevanz-/Konfidenzschwellen und aggregiert Haltungen. Keine Aggregation/Kalibrierung der Run-Review-Schatten (S8); externe Kalibrierung nicht pruefbar. |
| H-11 | `.github/workflows/security-audit.yml:20`, `.planning/ROADMAP.md:39`, `:49`, `scripts/IBKR_EXECUTION.md:963`, `README.md:109` | B | teils | Security-Scan und dokumentierter erster Paper-Fill widerlegen Teile der alten Matrix; 70 M2-IDs vorhanden; Verteilung 52/9/9 nicht als Abnahmestand bestaetigbar. Details in der Tabelle unten. |
| H-12 | `daily-paper-run.yml:75`, `backtest.py:161`, `patterns/evaluate.py:183`, `yahoo/ohlcv.py:212`, `tests/fixtures/paper_log_71df89d/decision-log.md:1` | I | teils | Einschraenkungen belegt (nicht archivierte Feeds, aktuelle adjustierte Kurse, ueberlappende Fenster, kleiner Default-Pool). Pool ist konfigurierbar. Aktuelle Zahl abgerechneter Entscheidungen aus dem Commit nicht pruefbar. |
| N-01 | `yahoo/news.py:167`, `:184`, `:67` | B | neu | Einfache Titel-Deduplizierung und Ticker-Tag-Filter existieren (inhaltliche Gleichheit wird nicht geprueft). |
| N-02 | `backtest.py:87`, `:95`, `patterns/evaluate.py:212`, `memory/log.py:174` | B | neu | Ties verlassen den Nenner (o31 "Ties = Fehltreffer" ist falsch). Gespeicherte Renditen sind auf 0,1 pp gerundet, kleine Ergebnisse werden dadurch zu Ties. |
| N-03 | `ibkr_decision.py:289`, `:292` | B | neu | Jev-Fallback-Ratings werden vom IBKR-Ausfuehrer nicht gehandelt (fail-closed). |
| N-04 | `vendors/fred.py:203`, `sec_edgar.py:176`, `agents/tools.py:35`, `polymarket.py:86` | B | neu | Point-in-time-Schutz differenzierter: FRED-Vintages, SEC-Veroeffentlichungsdatum, Datumsbegrenzung, Polymarket-Rueckhalt. Yahoo: aktuelle adjustierte Historien, Standard-Indikatorpfad fuellt vorwaerts/rueckwaerts (`yahoo/ohlcv.py:88`). |
| N-05 | `budget.py:75`, `:117`, `:123`, `graph/setup.py:164` | I | neu | Kostenbudget prueft verbuchte Kosten vor dem naechsten Call; laufende/parallele Calls koennen die Grenze ueberschreiten. Keine reservierte Gesamtobergrenze. |
| N-06 | `scripts/IBKR_EXECUTION.md:971`, `:975`, `:976`, `tests/test_ibkr_execute.py:2573` | W | neu | Erster Paper-Fill dokumentiert (BUY 1 AAPL, Fill 342,86 USD, Kommission 1,00 USD, ca. 0,29 % einseitig). Markierter Pipeline-Test, keine Engine-Entscheidung; Exit 10 war Fehlalarm (inzwischen behoben). |
| N-07 | `.planning/REQUIREMENTS.md:109`, `ibkr_decision.py:345`, `:367`, `ibkr_executor.py:2875` | B | neu | REQ-IBKR-23 fordert `Ziel - Ist - offen`; umgesetzt ist Abbruch bei offenen Orders, sonst `Ziel - Ist`. "umgesetzt" ist zu stark. |
| N-08 | `ibkr_guards.py:349`, `:356`, `ibkr_decision.py:367`, `ibkr_executor.py:2883` | I | neu | `MAX_QTY_PER_ORDER = 2` ist keine Geld-/Risikogrenze; Bestand 3 / Ziel 0 ergibt SELL 3 und wird abgewiesen. Abbaupfad fuer groessere oder manuelle Bestaende fehlt. |
| N-09 | `patterns/evaluate.py:183`, `:205`, `:218`, `:329` | I | neu | Nicht ueberlappende Fenster je Ticker und Zelle; unter `MIN_N=20` keine Quote. Tickeruebergreifende Marktkorrelation und viele Musterzellen bleiben abhaengig; kein Mehrfachtestverfahren (S2). |

### Praezisierung zu H-11 (Codex)

M1 nach der DoD-Konvention mit Security-Korrektur: **11 = 7 umgesetzt / 1 teilweise / 2 offen / 1 verworfen** (o31: 6/2/2/1). M2: 70 IDs in Definition und Coverage-Tabelle; die Verteilung 52/9/9 ist als o31-Klassifikation nachvollziehbar, aber kein widerspruchsfreier Abnahmestand (ROADMAP bezeichnet Phase 5 gleichzeitig als abgeschlossen und offen; Phase 6 hat Ausfuehrungsevidenz, die Roadmap nennt noch offene Operator-Schritte; REQ-IBKR-23 nur teilweise). Eine neue Gesamtverteilung ist **nicht pruefbar**; Codex schaetzt keine Zahl. Upstream 35 = 34/0/1 als Funktionsinventar nachvollziehbar; "umgesetzt" heisst Funktion vorhanden, nicht Prognosegueite oder Betriebserfolg.

| ID | Gegenpruefung durch Codex | Beleg |
|---|---|---|
| M1-P1-2 | Umgesetzt im Codebestand; Scan-Luecke widerlegt (gruener aktueller Lauf nicht geprueft) | `security-audit.yml:20`, `:36`, `:46`, `ci.yml:19`, `:70`, `pyproject.toml:34` |
| M1-P2-6 | Offen (volles Observability/Alerting-Ziel); Laufzusammenfassung und Kostenmessung existieren | `MILESTONE.md:94`, `daily_paper_run.py:284` |
| M1-P2-8 | Offen als uebergreifende Ausfall-/Quota-Policy; Retry/Fallback-Bausteine existieren | `MILESTONE.md:94`, `llm_clients/factory.py:184`, `dataflows/router.py:231` |
| REQ-IBKR-49 | Offen: branchuebergreifender Soll-Ist-Bericht | `REQUIREMENTS.md:213` |
| REQ-IBKR-50 | Offen: Bericht mit getrennten Ausfuehrungs-/Entscheidungsmetriken | `REQUIREMENTS.md:215`, `ibkr_ledger.py:590` |
| REQ-IBKR-51 | Offen: Backup-Allow-Liste ohne Ledger und Contract-Cache | `state_maintenance.py:382`, `:386`, `:391` |
| REQ-IBKR-52 | Offen: eigener Veroeffentlichungsbranch des Ausfuehrers | `REQUIREMENTS.md:225` |
| REQ-IBKR-53 | Offen: Ausfuehrungs-Heartbeat bei Fehler/Leerlauf | `REQUIREMENTS.md:228` |
| REQ-IBKR-54 | Offen: CI-Alterskontrolle des Heartbeats | `REQUIREMENTS.md:231` |
| REQ-IBKR-56 | Kein Einrichtungsnachweis im Repo; Windows-Zustand nicht pruefbar | `REQUIREMENTS.md:251` |
| REQ-IBKR-57 | Vorbedingungspruefung im Code umgesetzt, Betriebsnachweis eingeschraenkt | `ibkr_executor.py:2979`, `:2989` |
| REQ-IBKR-58 | Kein Aktivierungsnachweis; Task-History nicht pruefbar | `REQUIREMENTS.md:257` |
| REQ-IBKR-59 | Offen (vollstaendiger Dauerbetriebsnachweis) | `REQUIREMENTS.md:260` |
| REQ-IBKR-60 | Teilweise: Handbuch vorhanden, Betriebsabschnitte nicht vollstaendig belegt | `IBKR_EXECUTION.md:587`, `:710`, `:963` |
| REQ-IBKR-65 | Implementiert und erstmals praktisch beruehrt (Fehlalarm, Korrektur, Regressionstest); formaler Abschluss nicht belegt | `ibkr_executor.py:1456`, `:1472`, `:1522`, `IBKR_EXECUTION.md:976` |
| U-35 | Offen fuer den Upstream-Graphpfad; der Fork-Ausfuehrer ist eine andere, ausdruecklich gestartete Kette | `README.md:109`, `graph/setup.py:185`, `ibkr_broker.py:1539` |

**Verdikt (Codex):** TradingEngineX entscheidet im geprueften Stand ueberwiegend durch LLM-Urteile ueber Texte und berechnete Marktdaten; ein eigenes probabilistisches Renditeprognosemodell wurde nicht gefunden. Die pauschalen Aussagen "keine News-Vorverarbeitung", "Statistik nur nachtraeglich" und "Jev nur REVIEW-Fallback" sind zu korrigieren. Security-Scan und erster dokumentierter Paper-Fill machen Teile der o31-Lueckenliste bereits ueberholt, andere Umsetzungsaussagen (Ordernettierung) sind zu stark. Fuer eine evidenzbasierte Freigabe fehlen ein kostenbereinigter Portfolio-Nachweis, unabhaengige Validierung und vollstaendig belegter Betrieb. Auch ein vollstaendig erfuellter Plan kann kuenftige Profitabilitaet nicht garantieren.

## Lueckenbewertung und Go/No-Go (Codex)

P0 = Voraussetzung vor Echtgeld; P1 = erforderliche Forschungs-/Qualitaetsarbeit. Vorschlaege fuer dieses Repo, keine Profitabilitaetszusage.

| Dimension | Bewertung / naechster Nachweis | Prio |
|---|---|---|
| Vorhersage und Kalibrierung | Rating und Intensitaets-Score, keine Trefferwahrscheinlichkeit. Zielgroesse, Horizont und messbare Prognosen oder erwartete Nettorenditen fehlen; Jev-Textklassifikation getrennt von Kursprognose kalibrieren. GARCH/Monte Carlo sind keine Pflicht. | P1 |
| Out-of-Sample / Walk-Forward | Grid-Backtest ist kein fortgeschriebenes Portfolio (`backtest.py:9`, `:199`). Zeitlich gesperrte Evaluierung mit Purging/Embargo und protokollierten Modell-/Promptversionen noetig. | P0 |
| Baselines und Statistik | Nur Benchmarkdifferenz. Cash, Buy-and-Hold, einfache technische Regeln und Zufall bei gleichem Exposure und Kosten; Konfidenzintervalle mit Zeit-/Tickerabhaengigkeit, Mehrfachtestkontrolle. | P0 |
| Look-ahead / Survivorship | Yahoo liefert heute adjustierte Historien, Textfeeds nicht archiviert. Archivierte Eingaben mit Veroeffentlichungs- und Erfassungszeit, zeitpunktbezogenes Universum; Datumsfilter schliessen spaeteres Wissen eines LLM nicht aus. | P0 |
| Kosten / Slippage | Settlement und Summary ohne Transaktionskosten (S9). Portfolio-Simulator mit Cash, Gebuehren, Spread, Slippage, FX, LLM-Kosten; Paper-Fills als Mechaniktest trennen. | P0 |
| Positionsgroesse, Stop, Drawdown, Exposure | Stueckzahlgrenze, Long-only, Kill-Switch existieren, ersetzen kein Risikobudget. Notional-/Exposure-Grenzen, Drawdown-Abschaltung, getesteter Ausstiegspfad auch ueber dem Orderlimit, Gap-Szenarien. | P0 |
| Datenqualitaet / Vendor-Ausfall | Staleness, Cache-TTL, Ausfallpfade vorhanden; fehlt: verbindliche Mindestabdeckung, Frische je Datentyp, Kennzeichnung imputierter Werte, getestete Entscheidung bei Ausfall. | P0 |
| Monitoring / Betrieb | Ledger, Read-back, Alarmzustaende vorhanden; Soll-Ist-Bericht, Ausfuehrungs-Heartbeat, Backup inkl. IBKR-State, Wochenwechsel praktisch nachzuweisen. | P0 |

**Go/No-Go-Schwellen (Vorschlag von Codex, vor der Auswertung festzulegen; Mindest-N allein genuegt nicht, Poweranalyse noetig):**

| Bereich | Schwelle |
|---|---|
| Datenbasis | mind. 24 Monate zeitlich getrennte OOS-Auswertung, 30 vorab definierte Titel, 500 effektiv unabhaengige bewertbare Richtungsfaelle (Rohzahl und Korrektur separat), plus 6 Monate prospektiver Forward-Lauf |
| Prognosegueite | Brier/Log-Loss gegen vorab definierte Baselines (z. B. mind. 5 % besser), Kalibrierungsfehler max. 0,05; Jev-Konfidenzen separat gegen menschlich gelabelte Texte |
| Wirtschaftlichkeit | positive Nettoperformance nach allen Kosten; untere 95-%-Grenze des Mehrertrags ueber der Hauptbaseline > 0 (Zeit-/Tickerabhaengigkeit, Mehrfachtests); bei doppelten Ausfuehrungskosten noch positiv; Trefferquote allein kein Kriterium |
| Portfolio-Risiko | z. B. max. 0,5 % NAV Risiko je Position, 5 % NAV je Titel, 100 % Brutto, 2 % Tagesverlust, 10 % Drawdown als Abschaltschwellen; inkl. Abbau grosser Bestaende und Gaps |
| Datenfreigabe | 100 % der gehandelten Entscheidungen mit Eingabe-Snapshot, Zeitstempel, Datenqualitaetsstatus; fehlende Pflichtdaten fuehren nachweislich zu keiner neuen Position |
| Ausfuehrungsmechanik | mind. 20 aufeinanderfolgende Sitzungen mit vollstaendigem Ledger-/Broker-Abgleich; 0 Doppelorders, 0 ungeklaerte Intents, 100 % Order-/Fill-Zuordnung; Negativkontrollen (Reconnect, Teil-Fill, spaeter Fill, Kill, Quota-Ausfall, Crash nach Intent) |
| Betrieb | Alarm bei fehlendem Lauf spaetestens 30 Minuten nach geplantem Abschluss; Restore-Test mit vollem IBKR-State; mind. ein Wochenwechsel |
| Aktueller Stand | **No-Go fuer Echtgeld und jede Profitabilitaetsbehauptung.** Ein beaufsichtigter Paper-Mechaniktest ist begruendbar; Forschungs- und Betriebsgates sind nicht geschlossen. |

Profitabilitaet kann kein Plan garantieren; planbar sind Nachweisfuehrung und Abbruch bei Nichterfuellung.

## Disposition

Querpruefung: "geprueft" = Beleg von mir selbst an der SHA-Zeile (`git show 4a55d2c:<pfad>`) bzw. die Abwesenheit selbst per `git grep` am SHA nachvollzogen; "nur uebernommen" = Codex-Aussage nicht selbst nachgeprueft.

| Nr | Disposition | Pruefung | Detail |
|---|---|---|---|
| H-01 | bestaetigt | nur übernommen | Suchprotokoll S1/S2 nicht wiederholt; `random.uniform`-Treffer (s. H-03) stuetzen das Bild. Meilenstein-Kandidat (PRED). |
| H-02 | bestaetigt | geprüft | `import numpy as np` in `patterns/evaluate.py:42` gesehen, keine scipy/sklearn. Formulierung in o31 praezisieren. |
| H-03 | bestaetigt | geprüft | Beide `random.uniform` sind Retry-Jitter (`post_screen.py:84`, `reddit.py:148`); `default_config.py` Kommentar zu `temperature: None`. Zeile 115 ist der Kommentar, nicht der Wert (Zeilenversatz klein). Meilenstein-Kandidat (PRED-Streuung messen). |
| H-04 | bestaetigt | nur übernommen | Plausibel (kein Entscheidungsregel-Code im Graph, s. H-05). |
| H-05 | bestaetigt | nur übernommen | Eigene Gegenprobe nicht gefahren; Docstrings in `patterns/evaluate.py` bestaetigen Nachauswertungsrolle. |
| H-06 | widerlegt (pauschale Form; Kern "kein eigenes Sentiment-Scoring/Embedding" bleibt) | geprüft | `yahoo/news.py:165-186` gelesen: `seen_titles`-Deduplizierung vorhanden; `post_screen.py:1-8` beschreibt Jev-Klassifikation. Meilenstein-Kandidat (DATA/PRED). |
| H-07 | bestaetigt (mit Praezisierung) | nur übernommen | Auswahlregel nicht selbst nachgelesen; "keine Aehnlichkeitssuche" durch Embedding-Nullsuche gestuetzt. |
| H-08 | widerlegt (teilweise) | geprüft | `portfolio_manager.py:33-37` zeigt `past_context` als Eingabe in den PM; numerischer Inhalt (raw/alpha) selbst nur teils gesehen (`memory/log.py` formatiert `raw_pct`/`alpha_pct`). |
| H-09 | bestaetigt (Kern), mit Korrektur | geprüft | `schemas.py:164-180`: nur `entry_price`, `stop_loss`, `position_sizing`, kein `take_profit`. `ibkr_decision.py:287` und `:321-323`: Hold wird vor der Rechnung uebersprungen, ist nicht in `BLOCKS`. Designfrage Operator (Sizing). |
| H-10 | widerlegt (teilweise) | nur übernommen | Post-Screening-Schwellen aus Codex; Docstring `post_screen.py:1-8` ("calibrated probabilities") stuetzt, dass Jev auch ausserhalb des Fallbacks wirkt. Meilenstein-Kandidat (Kalibrierung). |
| H-11 | widerlegt (teilweise) | geprüft | `security-audit.yml` mit `pip-audit` (Job, blockierend) vorhanden; `IBKR_EXECUTION.md:969-977` bestaetigt den Paper-Fill; `ibkr_decision.py:343-370` bestaetigt N-07. Gesamtverteilung nicht neu bestimmt. |
| H-12 | bestaetigt | geprüft | `daily-paper-run.yml:75` Default `AAPL,MSFT,NVDA`; `IBKR_EXECUTION.md:972`: 20 von 20 Engine-Entscheidungen ohne Buy. Meilenstein-Kandidat (VAL/DATA). |
| N-01 | neu | geprüft | `yahoo/news.py:182-186` `seen_titles`. |
| N-02 | neu | geprüft | `backtest.py:87-97` `_tally`: Nullen als Tie ausserhalb des Nenners. Rundung im Log `f"{raw_return:+.1%}"` (`memory/log.py` um :172-173, Codex nennt :174). |
| N-03 | neu | geprüft | `ibkr_decision.py:289-293`: `rating_source_null` und `source == "jev"` werden nicht gehandelt. |
| N-04 | neu | nur übernommen | Zeilen fred.py:203 (`pit = min(as_of_date, ...)`) und sec_edgar.py:176 (`fact["filed"] > as_of_date`) gesehen; Polymarket und Tools nicht. Meilenstein-Kandidat (DATA). |
| N-05 | neu | geprüft | `budget.py:117-125`: Pruefung auf bereits verbuchte Kosten (`cost > max_cost`) vor dem naechsten Call. Parallelitaet nicht selbst geprueft. |
| N-06 | neu | geprüft | `IBKR_EXECUTION.md:969-977`: "pipeline test, not an engine decision", 20 of 20 ohne Buy, Fill 1 @ 342.86, Kommission 1.00 USD. Meilenstein-Kandidat (Kosten). |
| N-07 | neu | geprüft | `ibkr_decision.py:343-352` Abbruch bei `open_orders > 0`; Docstring `:337-340`: "Own open orders are only netted as target - held - open from phase 6 on". Codex' Befund passt, "umgesetzt" ist im Sinn der Anforderung zu stark; Phase-6-Abhaengigkeit beachten. |
| N-08 | neu | geprüft | `ibkr_guards.py:348-358` `MAX_QTY_PER_ORDER = 2`, lehnt ab statt zu kuerzen; Beispiel Bestand 3 / Ziel 0 folgt aus `plan_order`. Meilenstein-Kandidat (RISK), Designfrage Operator. |
| N-09 | neu | nur übernommen | `_independent` bei `evaluate.py:183` und `MIN_N = 20` (`:51`) gesehen; Mehrfachtest-Abwesenheit aus S2 uebernommen. |

Hinweis: Zeilenangaben bei Codex weichen mehrfach um wenige Zeilen ab (`default_config.py:115`, `memory/log.py:174`). Die Befunde selbst stimmen; die Belege sind lesbar mit Versatz.

## Abgleich mit o31

| o31-Aussage (Fundstelle) | Codex | Abweichung | Folge |
|---|---|---|---|
| Keine News-Vorverarbeitung / kein Sentiment-Scoring (Architektur §3, H-06) | Titel-Deduplizierung, Ticker-Tag-Filter, StockTwits-Labelzaehlung, optionale Jev-Klassifikation | Pauschalaussage zu weit; Kern (kein Embedding, kein lokaler NLP) bleibt | Methodenteil der o31-Seite praezisieren |
| Statistik nur in der Nachauswertung (H-08) | Indikatoren/Social-Verhaeltnisse sind Eingaben; PM erhaelt numerische raw/alpha im Memory-Kontext | Rueckwirkung nicht nur ueber Reflexionstexte | Methodenteil korrigieren |
| "Keine statistischen Bibliotheken" (H-02) | pandas, stockstats, numpy vorhanden | Formulierung zu weit | praezisieren |
| Retrieval rein zeitbasiert (H-07) | Filter auf abgerechnete Eintraege, 5 gleiche + 3 andere Ticker, Einfuegereihenfolge | Detail | praezisieren |
| Hold = 0 Bloecke, take_profit geht nicht an IBKR (H-09) | Hold = unveraendert/skip; `TraderProposal` hat kein `take_profit` | Korrektur zweier Details | Methodenteil korrigieren |
| Jev nur REVIEW-Fallback (H-10) | Post-Screening nutzt Jev auch fuer Relevanz/Haltung; 0,9 konfigurierbar | zu pauschal | korrigieren |
| Ties zaehlen als Fehltreffer (o31/Methodenteil) | Ties verlassen den Nenner (`backtest.py:87-97`) | o31 falsch | korrigieren; N-02 |
| M1-P1-2 teilweise, kein Security-Scan (Matrix) | `security-audit.yml` seit cf6ab73, umgesetzt | Status veraltet | M1 neu: 7/1/2/1 statt 6/2/2/1 |
| Keine reale Order bei REQ-IBKR-65 (Matrix) | Erster Paper-Fill 2026-10-19 dokumentiert | Status veraltet | Eintrag aktualisieren |
| REQ-IBKR-23 umgesetzt (Matrix) | Nettierung `Ziel - Ist - offen` nur teilweise | zu stark | Status auf teilweise (Phase-6-abhaengig) |
| M2 52/9/9 (Matrix) | 70 IDs bestaetigt, Verteilung nicht als Abnahmestand pruefbar (Roadmap widerspruechlich) | Zaehlung nicht belegbar | Statusmassstab klaeren |
| Upstream 34/0/1, U-35 offen | als Funktionsinventar nachvollziehbar; "umgesetzt" = Funktion vorhanden | keine | Legende ergaenzen |
| (nicht genannt) | N-01, N-03, N-04, N-05, N-06, N-08, N-09 | neu | in Meilenstein-Entwurf eingeflossen |

**Veraltete Teile der o31-Seite:** Der Methodenteil (News-Auswertung, Rueckwirkung, Jev-Rolle, Tie-Behandlung, Hold/take_profit) muss korrigiert werden. In Matrix und Schaubild sind M1-P1-2, REQ-IBKR-65 und REQ-IBKR-23 veraltet, die M1-Zaehlung (6/2/2/1 statt 7/1/2/1) und die M2-Gesamtverteilung. Die Seite selbst wurde nicht geaendert.
