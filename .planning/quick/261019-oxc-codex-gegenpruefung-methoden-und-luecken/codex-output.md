**HEAD-SHA des Prüfstands: `4a55d2c93f6e70f2f48e50be0fef271b4544b233`**

Geprüft wurden ausschließlich Git-Blobs dieses Commits. Projektcode und Tests wurden nicht ausgeführt; Netzwerk-APIs, Working Tree und Secret-Dateien wurden nicht verwendet. Die o31-Unterlagen habe ich erst nach meinem eigenen Urteil zu H-01 bis H-10 gelesen.

**Beleggrad:** **B** = unmittelbar durch Code oder Suchbefund belegt; **W** = schriftlicher Lauf-/Abnahmebericht, hier nicht wiederholt; **I** = daraus abgeleitete Schlussfolgerung. Die unten dokumentierten Suchbelege **S1–S9** gehören zu den jeweiligen Negativaussagen. Alle Zeilenangaben gelten ausschließlich für den Prüf-SHA.

| Nr | Hypothese/Befund | Datei:Zeile | Grad (B/W/I) | Urteil (bestätigt/widerlegt/teils/nicht prüfbar/neu) | Begründung |
|---|---|---|---|---|---|
| H-01 | Kein eigenes stochastisches Prognosemodell | `pyproject.toml:11`; `tradingagents/agents/managers/portfolio_manager.py:80`; `tradingagents/dataflows/vendors/polymarket.py:129` | B | bestätigt | Im untersuchten Python-Umfang kein Monte-Carlo-, ARCH/GARCH-, Bayes-, Random-Walk- oder Verteilungsprognosemodell gefunden (**S1/S2**). Der PM erzeugt das Rating per LLM. Polymarket liefert externe Ereigniswahrscheinlichkeiten als Eingabe; das ist kein eigenes Aktienrenditemodell. |
| H-02 | Keine Statistik-/ML-/NLP-Bibliotheken | `pyproject.toml:21`; `pyproject.toml:28`; `tradingagents/patterns/evaluate.py:42`; `tradingagents/dataflows/vendors/yahoo/market.py:8` | B | teils | Für die ausdrücklich genannten ML-/NLP-Pakete stimmen Dependency- und Importsuche (**S1/S2**). Die allgemeine Aussage „keine statistischen Bibliotheken“ ist zu weit: `pandas`, `stockstats` und ein direkter `numpy`-Import existieren. |
| H-03 | Ausschließlich ungesteuertes LLM-Sampling; `random.uniform` nur Retry-Jitter | `tradingagents/default_config.py:115`; `tradingagents/llm_clients/factory.py:177`; `tradingagents/agents/post_screen.py:84`; `tradingagents/dataflows/vendors/reddit.py:148` | B | teils | Die beiden `random.uniform`-Stellen dienen Retry-Jitter. `temperature=None` überlässt die Einstellung dem Provider; eine explizite Temperatur wird aber unterstützt. „Ungesteuert“ gilt somit nur für den Default. Tatsächliches Provider-Sampling und dessen Alleinstellung sind statisch nicht vollständig prüfbar. Weitere Zufallsquellen erzeugen Infrastruktur-/Authentifizierungskennungen (**S3**). |
| H-04 | `stockstats`-Indikatoren sind LLM-Eingabe | `tradingagents/agents/analysts/market_analyst.py:22`; `tradingagents/agents/analysts/market_analyst.py:77`; `tradingagents/dataflows/vendors/yahoo/snapshot.py:77`; `tradingagents/agents/managers/portfolio_manager.py:80` | B | bestätigt | Der Analyst liest berechnete Indikatoren und interpretiert sie per LLM. RSI-Schwellen und ATR-Sizing stehen als Anweisungen im Prompt. Im verfolgten Entscheidungspfad wird daraus kein numerischer Regelentscheider; die separaten Muster sind nicht eingebunden (**S4**). |
| H-05 | `patterns/` ist vom Graph getrennte Nachauswertung | `scripts/pattern_eval.py:31`; `tradingagents/patterns/evaluate.py:278`; `tradingagents/patterns/signals.py:101`; `tradingagents/graph/setup.py:125` | B | bestätigt | Sechs deterministische Muster existieren tatsächlich. Die Referenzsuche findet ihre Nutzung ausschließlich innerhalb der Musterschicht und ihres Auswertungsskripts; keine Graph-/Agentenreferenz (**S4**). |
| H-06 | Keine eigene News-/Social-Verarbeitung; Score vom LLM; Alpha Vantage inaktiv | `tradingagents/dataflows/vendors/yahoo/news.py:167`; `tradingagents/dataflows/vendors/yahoo/news.py:184`; `tradingagents/agents/post_screen.py:147`; `tradingagents/dataflows/vendors/stocktwits.py:153`; `tradingagents/agents/analysts/sentiment_analyst.py:114`; `tradingagents/agents/schemas.py:330` | B | teils | Die pauschale Abwesenheitsbehauptung ist falsch: Globale Yahoo-News werden nach identischem Titel dedupliziert; Yahoo-Suche filtert Ticker-Tags; StockTwits-Labels werden gezählt; optional klassifiziert Jev Social-Posts nach Relevanz und Haltung. `overall_score` bleibt LLM-Ausgabe. Embeddings und lokale NLP-Pakete wurden nicht gefunden (**S1/S2/S5**). Der eingecheckte Paper-Workflow verwendet die Yahoo-Konfiguration und aktiviert das Post-Screening nicht: `tradingagents/default_config.py:179`, `.github/workflows/daily-paper-run.yml:100`, `scripts/daily_paper_run.py:273`. |
| H-07 | Memory-Retrieval rein zeitbasiert, keine Ähnlichkeitssuche | `tradingagents/memory/log.py:106`; `tradingagents/memory/log.py:118`; `tradingagents/memory/log.py:124` | B | teils | Keine semantische Ähnlichkeitssuche gefunden (**S6**). Die Auswahl ist aber genauer: nur abgerechnete Einträge, optional `resolved <= as_of`, anschließend bis zu fünf gleiche und drei andere Ticker. Verwendet wird umgekehrte **Einfügereihenfolge**, keine explizite Datumssortierung. |
| H-08 | Statistik ausschließlich nachträglich; Rückwirkung nur durch Reflexion | `tradingagents/memory/settlement.py:118`; `tradingagents/backtest.py:223`; `tradingagents/patterns/evaluate.py:67`; `tradingagents/memory/log.py:368`; `tradingagents/agents/managers/portfolio_manager.py:35` | B | teils | Settlement, Summary und Wilson-Auswertung sind nachträglich. „Statistik nur nachträglich“ unterschlägt jedoch Indikatoren und Social-Verhältnisse als Entscheidungseingaben. Auch die Rückwirkung erfolgt nicht ausschließlich über Reflexion: Der PM erhält bei gleichen Tickern frühere Entscheidungstexte **und numerische raw-/alpha-Ergebnisse** im Memory-Kontext. |
| H-09 | Feste Größenleiter; keine Konfidenz-/Volatilitätssteuerung; Stops nicht an IBKR | `scripts/ibkr_decision.py:323`; `scripts/ibkr_decision.py:336`; `scripts/ibkr_decision.py:355`; `tradingagents/agents/schemas.py:146`; `scripts/ibkr_broker.py:503` | B | teils | Die feste Zielbestandsleiter stimmt; tatsächliche Ordermenge ist die Differenz zum Bestand. **`Hold` bedeutet unverändert halten, nicht null Blöcke.** Im Orderpfad fehlen die genannten Sizing-Eingaben und Stop-Felder (**S7**). Außerdem besitzt `TraderProposal` überhaupt kein `take_profit`-Feld; vorhanden sind `entry_price`, `stop_loss`, `position_sizing`. |
| H-10 | Jev-Konfidenz nur REVIEW-Fallback ≥0,9; keine Aggregation/Kalibrierung | `tradingagents/jev/hooks.py:133`; `tradingagents/jev/hooks.py:142`; `tradingagents/jev/hooks.py:152`; `tradingagents/agents/post_screen.py:37`; `tradingagents/agents/post_screen.py:120` | B | teils | Für `jev/hooks.py` stimmt die Fallback-/Shadow-Trennung; 0,9 ist der **konfigurierbare Default**. Repo-weit stimmt „nur Fallback“ nicht: Post-Screening verwendet zusätzliche Relevanz-/Konfidenzschwellen und aggregiert Haltungen. Für die Run-Review-Schattenausgaben wurde keine Aggregations-/Kalibrierungsauswertung gefunden (**S8**). Die behauptete externe Kalibrierung ist hier nicht prüfbar. |
| H-11 | Statuszählungen und Lückenliste stimmen | `.github/workflows/security-audit.yml:20`; `.planning/ROADMAP.md:39`; `.planning/ROADMAP.md:49`; `scripts/IBKR_EXECUTION.md:963`; `README.md:109` | B | teils | Security-Scan und dokumentierter erster Paper-Fill widerlegen wesentliche Begründungen der alten Matrix. 70 M2-Anforderungen sind vorhanden. Die Gesamtzählung `52/9/9` ist als aktueller Abnahmestand nicht belastbar; Einzelheiten unten. U-35 bleibt für den automatischen Upstream-Graphpfad offen, obwohl der separate Fork-Ausführer Orders senden kann (**S9**). |
| H-12 | Datenbasis für belastbare Trefferquote fehlt | `.github/workflows/daily-paper-run.yml:75`; `tradingagents/backtest.py:161`; `tradingagents/patterns/evaluate.py:183`; `tradingagents/dataflows/vendors/yahoo/ohlcv.py:212`; `tests/fixtures/paper_log_71df89d/decision-log.md:1` | I | teils | Methodische Einschränkungen sind belegt: nicht archivierte Textfeeds, aktuelle adjustierte Kursdownloads, überlappende Entscheidungsfenster und kleiner Default-Pool. Der Pool ist allerdings konfigurierbar; das Handbuch dokumentiert bereits 20 betrachtete Engine-Entscheidungen (`scripts/IBKR_EXECUTION.md:972`). Die **aktuelle Anzahl abgerechneter Entscheidungen** ist aus diesem Commit nicht unabhängig prüfbar: Die eingecheckte Fixture enthält lediglich einen alten pending-Eintrag, nicht den aktuellen `paper-log`-Bestand. |
| N-01 | Globale News haben bereits einfache Deduplizierung | `tradingagents/dataflows/vendors/yahoo/news.py:167`; `tradingagents/dataflows/vendors/yahoo/news.py:184`; `tradingagents/dataflows/vendors/yahoo/news.py:67` | B | neu | o31s Zusammenfassung unterschlägt die Titel-Deduplizierung und den Ticker-Tag-Filter. Das ist einfache Datenbereinigung; eine inhaltliche Gleichheit zweier unterschiedlich betitelter Artikel prüft diese Implementierung nicht (**S5**). |
| N-02 | Ties werden ausdrücklich ausgeschlossen | `tradingagents/backtest.py:87`; `tradingagents/backtest.py:95`; `tradingagents/patterns/evaluate.py:212` | B | neu | o31s Aussage „Ties zählen als Fehltreffer“ ist falsch. Nullrenditen verlassen den Nenner. Zusätzlich werden gespeicherte Renditen auf 0,1 Prozentpunkte gerundet (`tradingagents/memory/log.py:174`), wodurch kleine Ergebnisse zu Ties werden können. |
| N-03 | Jev-Fallback-Ratings werden vom IBKR-Ausführer gesperrt | `scripts/ibkr_decision.py:289`; `scripts/ibkr_decision.py:292` | B | neu | Ein Jev-Fallback kann das protokollierte Rating verändern, wird aber im vorhandenen IBKR-Pfad ausdrücklich nicht gehandelt. Das begrenzt seine unmittelbare Orderwirkung erheblich. |
| N-04 | Point-in-time-Schutz ist differenzierter als „Feeds nicht PIT“ | `tradingagents/dataflows/vendors/fred.py:203`; `tradingagents/dataflows/vendors/sec_edgar.py:176`; `tradingagents/agents/tools.py:35`; `tradingagents/dataflows/vendors/polymarket.py:86` | B | neu | FRED pinnt Datenvintages, SEC filtert nach Veröffentlichungsdatum, Tools begrenzen Modell-Datumswünsche und historische Polymarket-Abfragen werden zurückgehalten. Dagegen lädt Yahoo aktuelle adjustierte Historien; der Standard-Indikatorpfad füllt fehlende Werte vorwärts/rückwärts (`tradingagents/dataflows/vendors/yahoo/ohlcv.py:88`). Das verlangt eine feldweise Qualitätsbewertung. |
| N-05 | Das Kostenbudget ist keine harte Obergrenze aller gleichzeitig laufenden Calls | `tradingagents/budget.py:75`; `tradingagents/budget.py:117`; `tradingagents/budget.py:123`; `tradingagents/graph/setup.py:164` | I | neu | Geprüft werden bereits verbuchte Kosten vor dem nächsten Call; abgebrochen wird bei `cost > max_cost`. Ein laufender Call kann die Grenze überschreiten. Parallel gestartete Analysten können denselben noch freien Budgetstand passieren. „Hart“ beschreibt den anschließenden Abbruch, keine reservierte maximale Gesamtausgabe. |
| N-06 | Erster Paper-Fill bereits dokumentiert — einschließlich Fehlalarm und Kosten | `scripts/IBKR_EXECUTION.md:971`; `scripts/IBKR_EXECUTION.md:975`; `scripts/IBKR_EXECUTION.md:976`; `tests/test_ibkr_execute.py:2573` | W | neu | Dokumentiert sind BUY 1 AAPL, Fill, Ledger-Kette und zweiter Lauf ohne Doppelorder. Der erste Lauf endete wegen eines inzwischen behandelten Mengenfeld-Problems mit Exit 10. Es war ein **markierter Pipeline-Test**, keine Kaufentscheidung der Engine. Die dokumentierte Kommission von 1 USD entspricht bei 342,86 USD ungefähr **0,29 % einseitig**. |
| N-07 | REQ-IBKR-23 ist nicht vollständig umgesetzt | `.planning/REQUIREMENTS.md:109`; `scripts/ibkr_decision.py:345`; `scripts/ibkr_decision.py:367`; `scripts/ibkr_executor.py:2875` | B | neu | Gefordert wird `Ziel − Ist − offen`. Tatsächlich wird bei vorhandenen offenen Orders abgebrochen; ansonsten wird `Ziel − Ist` gerechnet. Der sichere Abbruch ersetzt keine implementierte Nettierung. Die alte Kennzeichnung „umgesetzt“ ist deshalb zu stark. |
| N-08 | Stückzahlgrenze schützt nicht automatisch das Portfolio und kann einen Abbau blockieren | `scripts/ibkr_guards.py:349`; `scripts/ibkr_guards.py:356`; `scripts/ibkr_decision.py:367`; `scripts/ibkr_executor.py:2883` | I | neu | Die Grenze beträgt zwei Stück je Order. Daraus folgt keine einheitliche Geld- oder Risikogrenze. Beispiel aus der vorhandenen Logik: Bestand drei, Ziel null ergibt SELL 3 und wird durch den Größenwächter abgewiesen. Für größere oder manuell entstandene Bestände braucht es einen definierten Abbaupfad. |
| N-09 | Wilson-Auswertung berücksichtigt einen Teil der Abhängigkeiten | `tradingagents/patterns/evaluate.py:183`; `tradingagents/patterns/evaluate.py:205`; `tradingagents/patterns/evaluate.py:218`; `tradingagents/patterns/evaluate.py:329` | I | neu | Nicht überlappende Fenster werden je Ticker und Auswertungszelle ausgewählt; unter `MIN_N=20` wird keine Trefferquote ausgegeben. Das ist eine vorhandene Absicherung. Tickerübergreifende Marktkorrelation und die vielen korrelierten Musterzellen werden dadurch jedoch nicht zu unabhängigen Experimenten; Mehrfachtestverfahren wurden nicht gefunden (**S2**). |

### Präzisierung zu H-11

**M1:** Nach der historischen DoD-Konvention ergibt die Security-Korrektur **11 = 7 umgesetzt / 1 teilweise / 2 offen / 1 verworfen**. Grundlage sind `.planning/MILESTONE.md:122`, `:127`, `:130`, `:133`, `:135`, `:150`, `:152` sowie der tatsächlich vorhandene Audit-Workflow. Das ist eine Umsetzungszählung; ein reproduzierbar identischer Dependency-Build folgt daraus nicht, denn die Dependencies verwenden überwiegend Mindestversionen (`pyproject.toml:11`).

**M2:** Sowohl die Anforderungsdefinitionen als auch die Coverage-Tabelle enthalten **70 IDs**. Die Coverage steht in `.planning/ROADMAP.md:414`; die zusätzlichen Anforderungen sind in `.planning/REQUIREMENTS.md:170` und `:174` definiert. Die alte Verteilung `52/9/9` lässt sich als o31-Klassifikation nachvollziehen, aber nicht als aktueller, widerspruchsfreier Abnahmestand bestätigen:

- Die Roadmap bezeichnet Phase 5 gleichzeitig als abgeschlossen und offen (`.planning/ROADMAP.md:37`, `:49`).
- Phase 6 hat bereits schriftliche Ausführungsevidenz, während die Roadmap noch offene Operator-Schritte nennt (`scripts/IBKR_EXECUTION.md:971`, `.planning/ROADMAP.md:348`).
- REQ-IBKR-23 ist gegenüber seinem Wortlaut nur teilweise erfüllt, siehe N-07.
- Die früheren Verifikationen sind datierte Berichte früherer Stände. Ihre Frontmatter meldet jeweils `passed`: `02-VERIFICATION.md:4`, `03-VERIFICATION.md:4`, `04-VERIFICATION.md:4`, `05-VERIFICATION.md:4` in den jeweiligen Phasenverzeichnissen. Sie ersetzen keine erneute Ausführung am Prüf-SHA.

Eine neue **vollständig abgenommene** Gesamtverteilung ist damit **nicht prüfbar**, ohne Statusmaßstab und widersprüchliche Abnahmeunterlagen aufzulösen. Ich ersetze sie nicht durch eine geschätzte Zahl.

| ID | Gegenprüfung am Prüf-SHA | Beleg |
|---|---|---|
| M1-P1-2 | **Umgesetzt im Codebestand.** Der behauptete fehlende Security-Scan ist widerlegt; ein grüner aktueller Lauf wurde hier nicht geprüft. | `.github/workflows/security-audit.yml:20`, `:36`, `:46`; `.github/workflows/ci.yml:19`, `:70`; `pyproject.toml:34` |
| M1-P2-6 | **Offen hinsichtlich des vollständigen Observability-/Alerting-Ziels.** Laufzusammenfassungen und Kostenmessung existieren bereits. | `.planning/MILESTONE.md:94`; `scripts/daily_paper_run.py:284`; **S9** |
| M1-P2-8 | **Offen als übergreifende Ausfall-/Quota-Policy.** Retry- und Vendor-Fallback-Bausteine existieren. | `.planning/MILESTONE.md:94`; `tradingagents/llm_clients/factory.py:184`; `tradingagents/dataflows/router.py:231` |
| REQ-IBKR-49 | **Offen:** branchübergreifender Soll-Ist-Bericht. | `.planning/REQUIREMENTS.md:213`; `.planning/ROADMAP.md:365`; **S9** |
| REQ-IBKR-50 | **Offen:** geforderter Bericht mit getrennten Ausführungs-/Entscheidungsmetriken. Einzelne Fill-Daten werden bereits gespeichert. | `.planning/REQUIREMENTS.md:215`; `scripts/ibkr_ledger.py:590`; **S9** |
| REQ-IBKR-51 | **Offen:** Backup-Allow-Liste enthält Ledger und Contract-Cache nicht. | `scripts/state_maintenance.py:382`, `:386`, `:391`; **S9** |
| REQ-IBKR-52 | **Offen als Gesamtanforderung:** eigener Veröffentlichungsbranch des Ausführers. | `.planning/REQUIREMENTS.md:225`; `.planning/ROADMAP.md:364`; **S9** |
| REQ-IBKR-53 | **Offen:** Ausführungs-Heartbeat auch bei Fehler-/Leerlauf. | `.planning/REQUIREMENTS.md:228`; **S9** |
| REQ-IBKR-54 | **Offen:** CI-Alterskontrolle dieses Heartbeats. | `.planning/REQUIREMENTS.md:231`; **S9** |
| REQ-IBKR-56 | **Kein eingecheckter Einrichtungsnachweis:** deshalb offen im Repo; tatsächlicher Windows-Zustand nicht prüfbar. | `.planning/REQUIREMENTS.md:251`; **S9** |
| REQ-IBKR-57 | **Vorbedingungsprüfung im Code umgesetzt; Betriebsnachweis eingeschränkt.** Die Startzeit wird nicht als Freigabe verwendet; Sitzung und Frische werden nochmals unmittelbar vor dem Intent geprüft. | `scripts/ibkr_executor.py:2979`, `:2989`; `.planning/ROADMAP.md:392` |
| REQ-IBKR-58 | **Kein eingecheckter Aktivierungsnachweis:** offen im Repo; tatsächliche Task-History nicht prüfbar. | `.planning/REQUIREMENTS.md:257`; **S9** |
| REQ-IBKR-59 | **Offen hinsichtlich des geforderten vollständigen Dauerbetriebsnachweises.** | `.planning/REQUIREMENTS.md:260`; `.planning/ROADMAP.md:394`; **S9** |
| REQ-IBKR-60 | **Teilweise:** umfangreiches Handbuch vorhanden; die geforderten Betriebsabschnitte sind nicht vollständig belegt. | `scripts/IBKR_EXECUTION.md:587`, `:710`, `:963`; **S9** |
| REQ-IBKR-65 | **Implementiert und erstmals praktisch berührt; formaler Abschluss nicht belegt.** Read-back, Vergleich und Alarm existieren. „Keine reale Order“ ist überholt; der erste dokumentierte Lauf zeigte einen Fehlalarm, der Code enthält die Korrektur und einen Regressionstest. | `scripts/ibkr_executor.py:1456`, `:1472`, `:1522`; `scripts/IBKR_EXECUTION.md:976`; `tests/test_ibkr_execute.py:2573` |
| U-35 | **Offen für den beschriebenen Upstream-Graphpfad.** Der separate Fork-Ausführer erfüllt eine andere, ausdrücklich gestartete Ausführungskette. | `README.md:109`; `tradingagents/graph/setup.py:185`; `tradingagents/graph/trading_graph.py:457`; `scripts/ibkr_broker.py:1539`; **S9** |

**Upstream 35 = 34/0/1:** Als Inventar vorhandener Funktionen ist diese Einteilung nachvollziehbar: Agenten/Graph (`tradingagents/graph/setup.py:125`), Structured Output (`tradingagents/agents/structured.py:62`), Memory/Settlement/Backtest, CLI (`cli/main.py:37`, `:108`), Reporting (`tradingagents/reporting.py:96`), Checkpoints (`tradingagents/graph/checkpointer.py:42`), Provider/Auth (`tradingagents/llm_clients/api_key_env.py:49`, `tradingagents/llm_clients/chatgpt_auth.py:324`) und Datenpfade sind vorhanden. „Umgesetzt“ bedeutet hier **Funktion vorhanden**, nicht nachgewiesene Prognosegüte, vollständige Point-in-time-Daten oder erfolgreicher Betrieb am Prüf-SHA.

### Such- und Abwesenheitsprotokoll

**Vollständigkeit:** Durchsucht wurden alle **114 `.py`-Dateien** unter `tradingagents/`, `scripts/`, `cli/` des Prüfcommits. Zusätzlich wurden die unten ausdrücklich benannten Tests, Workflows und Dokumente untersucht. Notebooks, externe Bibliotheksimplementierungen, externe Datenbestände und nicht eingecheckte Betriebszustände sind nicht vollständig umfasst.

Für jeden folgenden Abwesenheitsbeleg gilt zusätzlich der gemeinsame positive Dependency-Anker: **`pyproject.toml:11`** für Runtime-Dependencies, **`:33`** für optionale Dependencies. Der nächstliegende Implementierungsanker steht jeweils beim Suchbeleg.

Alle Mustersuchen verwendeten:

```text
git grep -n -i -E '<Muster>' 4a55d2c93f6e70f2f48e50be0fef271b4544b233 -- <Suchpfade>
```

Die Trefferzahlen zählen passende **Zeilen**, nicht einzelne Wörter.

**S1 — vorgeschriebene Begriffe.** Suchpfade exakt:

```text
':(glob)tradingagents/**/*.py'
':(glob)scripts/**/*.py'
':(glob)cli/**/*.py'
```

```text
Muster                    Treffer
numpy\.random             0
np\.random                0
statistics\.              2
np\.percentile            0
quantile                  0
textblob                  0
vader                     0
transformers              0
sentence-transformers     0
sklearn                   0
arch                      237
statsmodels               0
scipy\.stats              0
embedding                 0
cosine                    0
tfidf                     0
bullish|bearish            43
sentiment                 99
```

Die zwei `statistics\.`-Treffer sind Prosa in `cli/stats_handler.py:69` und `scripts/pattern_eval.py:7`, keine Nutzung des Statistikmoduls. Das breite `arch` trifft unter anderem „research“; die abgegrenzte Gegenprobe unten hat null Treffer. Die Bullish/Bearish-/Sentiment-Treffer führen gerade zu den vorhandenen Schemas, Labelzählungen und Jev-Kriterien; sie wurden nicht als Abwesenheit behandelt. Positive Anker: `tradingagents/agents/post_screen.py:41`, `tradingagents/dataflows/vendors/stocktwits.py:142`, `tradingagents/agents/schemas.py:311`.

**S2 — Synonyme, indirekte Modelle und Validierung.** Gleiche Python-Suchpfade wie S1:

```text
(^|[^[:alnum:]_])(arch|garch|bayes|monte.?carlo|random.?walk)([^[:alnum:]_]|$)
→ 0

stochast|monte.?carlo|arch_model|garch|bayes|random.?walk|brownian|wiener|markov|posterior|likelihood|probabilistic|prediction.interval|forecast
→ 1

scipy|sklearn|statsmodels|textblob|vader|transformers|sentence.transformers|embedding|cosine|tfidf
→ 0

vectorstore|chroma|faiss|bm25|tf.?idf|similarity|nearest.neigh|nltk|spacy|finbert
→ 0

walk.?forward|out.of.sample|survivorship|bootstrap|multiple.test|bonferroni|sharpe|drawdown|slippage|buy.and.hold|brier|log.loss|reliability
→ 1

probabilit|probab|uncertain|distribution|kelly|value.at.risk|expected.shortfall|cvar|risk.parity|risk.budget
→ 18
```

Der Forecast-Treffer ist der Polymarket-Hinweis (`tradingagents/dataflows/vendors/polymarket.py:117`). Der Validierungstreffer ist „sharpen“ in `scripts/ibkr_guards.py:413`, kein Sharpe-Verfahren. Die Wahrscheinlichkeits-Treffer betreffen Polymarket, Jev, Promptformulierungen und Paketmetadaten. Positive Ersatzimplementierung: LLM-PM in `tradingagents/agents/managers/portfolio_manager.py:80`; vorhandene Messung in `tradingagents/backtest.py:223` und `tradingagents/patterns/evaluate.py:67`.

Dasselbe Dependency-Muster wurde zusätzlich ausschließlich in `pyproject.toml` gesucht:

```text
scipy|sklearn|statsmodels|textblob|vader|transformers|sentence.transformers|embedding|nltk|spacy|finbert
→ 0
```

**S3 — Zufallsquellen.** Python-Suchpfade wie S1:

```text
random|temperature|seed
→ 21

random\.|secrets\.|uuid|urandom|SystemRandom
→ 21
```

Positive Anker: Retry-Jitter `tradingagents/agents/post_screen.py:84`, `tradingagents/dataflows/vendors/reddit.py:148`; UUID-Dateinamen `tradingagents/dataflows/files.py:24`; Authentifizierungszufall `tradingagents/llm_clients/chatgpt_auth.py:336`; Temperaturweitergabe `tradingagents/llm_clients/factory.py:180`.

**S4 — Mustereinbindung.**

```text
Muster: tradingagents\.patterns|compute_patterns|pattern_eval

Suchpfade: tradingagents/graph tradingagents/agents
→ 0

Suchpfade: alle Python-Pfade aus S1
→ 7
```

Die sieben Treffer liegen ausschließlich in `scripts/pattern_eval.py` und `tradingagents/patterns/`. Positive Anker: `scripts/pattern_eval.py:31`, `tradingagents/patterns/evaluate.py:47`; tatsächliche Graph-Erzeugung `tradingagents/graph/setup.py:125`.

**S5 — Keyword-/News-Vorverarbeitung.**

```text
Muster:
dedup|duplicat|seen|relevan|weight|lexicon|keyword|word.list

Suchpfade:
tradingagents/dataflows/vendors/yahoo/news.py
tradingagents/agents/post_screen.py
tradingagents/dataflows/vendors/stocktwits.py
→ 4
```

Positive Anker: Ticker-Tag-Filter `tradingagents/dataflows/vendors/yahoo/news.py:67`; Titelgleichheit `:184`; semantische externe Klassifikation `tradingagents/agents/post_screen.py:41`, `:147`. Zusammen mit S1/S2 ist damit die Aussage auf diese Implementierungen begrenzt; die pauschale Behauptung „keine Verarbeitung“ wird ausdrücklich verworfen.

**S6 — Memory-Ähnlichkeitssuche.**

```text
Muster: embedding|cosine|tfidf|similarity|vector|bm25|nearest
Suchpfad: tradingagents/memory
→ 0
```

Positive Ersatzimplementierung: `tradingagents/memory/log.py:118`, `:124`, `:125` — Filterung und rückwärtige Auswahl gespeicherter Einträge.

**S7 — Stops und risikobasiertes Sizing im Orderpfad.**

```text
Muster:
stop_loss|take_profit|take.profit|StopOrder|target_price|position_sizing|volatility|confidence

Suchpfade:
scripts/ibkr_decision.py scripts/ibkr_broker.py scripts/ibkr_executor.py
→ 0
```

Positive Ersatzimplementierungen: Leiter `scripts/ibkr_decision.py:323`, Mengenrechnung `:367`, Orderbuilder `scripts/ibkr_broker.py:503`, Stückzahlwächter `scripts/ibkr_guards.py:352`.

**S8 — Review-Aggregation und Kalibrierung.**

```text
Muster: calibrat|brier|log.loss|reliability|jev_review
Suchpfade: alle Python-Pfade aus S1
→ 2

Muster: calibrat|brier|log.loss|reliability
Suchpfad: ':(glob)tests/**/*.py'
→ 0
```

Die zwei Treffer sind die unbelegte Kalibrierungsbeschreibung in `tradingagents/agents/post_screen.py:3` und der Sidecar-Dateiname in `tradingagents/jev/hooks.py:188`. Positive vorhandene Verarbeitung: Einzelreview und Speicherung in `tradingagents/jev/hooks.py:135`, `:152`, `:180`.

**S9 — Betrieb, Ausführung und Nettoperformance.**

```text
Muster: ledger|contracts\.json
Suchpfad: scripts/state_maintenance.py
→ 0

Muster: heartbeat|paper.fills|git.*push|subprocess.*push|soll.ist
Suchpfade: scripts/ibkr_executor.py scripts/ibkr_ledger.py
→ 0

Muster:
heartbeat|paper.fills|soll.ist|schtasks|ClosedownAt|task.history|auto.restart|weekly.login|Wochenlogin
Suchpfade: alle Python-Pfade aus S1 sowie .github/workflows
→ 2

Muster:
scheduler|schtasks|task.history|ClosedownAt|auto.restart|weekly.login|Wochenlogin
Suchpfad: scripts/IBKR_EXECUTION.md
→ 0

Muster:
placeOrder|place_order|execute_order|submit_order|send_order|MarketOrder|LimitOrder|ib_async|backtrader|zipline
Suchpfade: tradingagents cli
→ 0

Muster:
commission|slippage|spread|turnover|(^|[^[:alnum:]_])fee([^[:alnum:]_]|$)|transaction.cost
Suchpfade: tradingagents/backtest.py tradingagents/memory/settlement.py
→ 0

Muster: prometheus|opentelemetry|statsd|sentry|webhook|alertmanager
Suchpfade: alle Python-Pfade aus S1
→ 0
```

Die zwei Heartbeat-Treffer beschreiben den **Analyselauf**, nicht einen Ausführungs-Heartbeat: `.github/workflows/daily-paper-run.yml:1`, `scripts/daily_paper_run.py:106`.

Positive nächstliegende Implementierungen: lokale Ausführung/Read-back `scripts/ibkr_executor.py:1179`, `:1456`; Fill-Aufzeichnung `scripts/ibkr_ledger.py:590`; bestehende Backup-Allow-Liste `scripts/state_maintenance.py:382`; Laufzusammenfassung `scripts/daily_paper_run.py:284`; reine Renditerechnung `tradingagents/memory/settlement.py:118`; Graph-Ende ohne Order `tradingagents/graph/setup.py:185`.

## Lückenbewertung

**P0** bezeichnet Voraussetzungen vor einer Echtgeldfreigabe; **P1** erforderliche Forschungs-/Qualitätsarbeit. Das sind Vorschläge für dieses Repo, keine Profitabilitätszusage.

| Dimension | Bewertung und notwendiger nächster Nachweis | Priorität |
|---|---|---|
| Vorhersage und Kalibrierung | Der PM liefert ein Rating; der Sentiment-Score ist Intensität, keine Trefferwahrscheinlichkeit (`tradingagents/agents/managers/portfolio_manager.py:80`, `tradingagents/agents/schemas.py:330`). Benötigt werden klar definierte Zielgröße und Horizont sowie messbare Prognosen oder erwartete Nettorenditen. Jev-Textklassifikation und künftige Kursentwicklung müssen getrennt kalibriert werden. GARCH oder Monte Carlo sind dabei keine Pflicht und allein kein Qualitätsnachweis. | P1 |
| Out-of-Sample und Walk-Forward | Der vorhandene Grid-Backtest führt dieselbe Pipeline aus, ist aber ausdrücklich kein fortgeschriebenes Portfolio (`tradingagents/backtest.py:9`, `:199`). Eine getrennte, zeitlich gesperrte Evaluierung mit unveränderter Konfiguration, Purging/Embargo über den Haltehorizont und protokollierten Modell-/Promptversionen ist erforderlich; entsprechende Verfahren wurden nicht gefunden (**S2**). | P0 |
| Baselines und statistische Aussage | Benchmarkdifferenzen existieren (`tradingagents/memory/settlement.py:121`), vollständige Buy-and-Hold-/Zufallsvergleiche wurden nicht gefunden (**S2**). Verglichen werden müssen Cash, Buy-and-Hold, einfache technische Regeln und Zufallsentscheidungen bei vergleichbarem Exposure und Kosten. Konfidenzintervalle müssen Zeit-/Tickerabhängigkeiten berücksichtigen; Muster-, Prompt- und Modellauswahl benötigen Mehrfachtestkontrolle. | P0 |
| Look-ahead und Survivorship | Datums- und Vintage-Schutz sind vorhanden, siehe N-04. Yahoo lädt jedoch heute adjustierte Historien (`tradingagents/dataflows/vendors/yahoo/ohlcv.py:212`), Textfeeds sind nicht archiviert (`tradingagents/backtest.py:162`). Benötigt werden archivierte Eingaben mit Veröffentlichungs- und Erfassungszeit sowie ein zeitpunktbezogenes Universum einschließlich ausgeschiedener Titel. Datumsfilter allein schließen außerdem späteres Wissen eines historischen LLM nicht aus. | P0 |
| Kosten und Slippage | Settlement und Summary rechnen ohne Transaktionskosten (**S9**). Die tatsächliche Ausführung erfolgt zudem zu anderen Zeitpunkten als die `next_close`-Messkonvention (`tradingagents/memory/settlement.py:74`, `scripts/IBKR_EXECUTION.md:971`). Es braucht einen Portfolio-Simulator mit Cash, Beständen, Gebühren, Spread, Slippage, FX und Analyse-/LLM-Kosten. Paper-Fills müssen als Mechaniktest getrennt bleiben. | P0 |
| Positionsgröße, Stop, Drawdown, Exposure | Stückzahlgrenze, Long-only, Margin-Vorschau und Kill-Switch existieren (`scripts/ibkr_guards.py:349`, `scripts/ibkr_decision.py:351`, `:386`). Sie ersetzen kein Portfolio-Risikobudget. Benötigt werden begründete Notional-/Exposure-Grenzen, Verlust-/Drawdown-Abschaltung und ein getesteter Ausstiegspfad, insbesondere für Bestände oberhalb des Orderlimits. Ein Stop-Konzept muss auch Gaps und fehlende Ausführbarkeit berücksichtigen. | P0 |
| Datenqualität und Vendor-Ausfall | Es gibt Staleness-Prüfung, Cache-TTL und explizite Ausfallpfade (`tradingagents/dataflows/vendors/yahoo/ohlcv.py:18`, `:24`; `tradingagents/dataflows/router.py:237`). Das beantwortet noch nicht, wann eine Analyse trotz fehlender Quellen handelbar bleibt. Erforderlich sind verbindliche Mindestabdeckung, Frische je Datentyp, Kennzeichnung imputierter Werte und getestete Entscheidungen bei Quota-/Vendor-Ausfällen. | P0 |
| Monitoring und Betrieb | Ledger, Read-back und Alarmzustände sind vorhanden (`scripts/ibkr_executor.py:1456`, `:1522`). Branchübergreifender Bericht, Ausführungs-Heartbeat und vollständiger Betriebsnachweis bleiben offen (**S9**). Vor unbeaufsichtigtem Betrieb müssen Alarmzustellung, Recovery, Backup einschließlich IBKR-State und Wochenwechsel praktisch nachgewiesen werden. | P0 |

## Go/No-Go-Kriterien

Die folgenden Schwellen sind **Vorschläge**, vor der Auswertung festzulegen. Mindest-N allein genügt nicht; eine Poweranalyse muss zeigen, ob der wirtschaftlich relevante Effekt erkennbar wäre.

| Bereich | Vorgeschlagene messbare Freigabeschwelle |
|---|---|
| Datenbasis | Mindestens **24 Monate zeitlich getrennte OOS-Auswertung**, mindestens **30 vorab definierte Titel** und **500 effektiv unabhängige bewertbare Richtungsfälle**; Rohfallzahl und Abhängigkeitskorrektur separat ausweisen. Zusätzlich mindestens **6 Monate prospektiver Forward-Lauf**. |
| Prognosegüte | Bei Wahrscheinlichkeitsausgaben: Brier-/Log-Loss gegen vorab definierte Baselines, beispielsweise mindestens **5 % bessere Brier-Score-Leistung** und Kalibrierungsfehler höchstens **0,05** bei ausreichend besetzten Gruppen. Jev-Klassifikationskonfidenzen separat gegen menschlich gelabelte Texte prüfen. |
| Wirtschaftlichkeit | Positive Nettoperformance nach sämtlichen Kosten; **untere 95-%-Konfidenzgrenze des Mehrertrags über der festgelegten Hauptbaseline > 0**, mit Zeit-/Tickerabhängigkeit und Mehrfachtests berücksichtigt. Ergebnis zusätzlich unter **doppelten angenommenen Ausführungskosten** noch positiv. Trefferquote allein ist kein Freigabekriterium. |
| Portfolio-Risiko | Beispielhafte Grenzen: maximal **0,5 % NAV geplantes Risiko je Position**, **5 % NAV je Titel**, **100 % Bruttoexposure**, **2 % Tagesverlust** und **10 % Drawdown** als Abschaltschwellen. Alle Grenzen einschließlich Abbau größerer Bestände und Gap-Szenarien testen. |
| Datenfreigabe | Für **100 % der gehandelten Entscheidungen** nachvollziehbare Eingabe-Snapshots, Zeitstempel und Datenqualitätsstatus. Fehlende Pflichtdaten oder überschrittene Frischegrenzen führen nachweislich zu keiner neuen Position. |
| Ausführungsmechanik | Mindestens **20 aufeinanderfolgende Sitzungen** mit vollständigem Ledger-/Broker-Abgleich; **null Doppelorders**, **null ungeklärte Intents**, **100 % Order-/Fill-Zuordnung**. Reconnect, Teil-Fill, verspäteter Fill, Kill, Quota-Ausfall und Crash nach Intent jeweils mit Negativkontrolle. |
| Betrieb | Alarm bei fehlendem Lauf spätestens **30 Minuten nach dem vorgesehenen Abschluss**; dokumentierter Restore-Test mit vollständigem IBKR-State; mindestens ein erfolgreich durchlaufener Wochenwechsel. |
| Aktueller Prüfstand | **No-Go für Echtgeld und eine Profitabilitätsbehauptung.** Ein beaufsichtigter Paper-Mechaniktest ist durch vorhandenen Code und schriftliche Ausführungsevidenz begründbar; die Forschungs- und Betriebsgates sind damit nicht geschlossen. |

## Verdikt

TradingEngineX entscheidet im geprüften Stand überwiegend durch LLM-Urteile über Texte und berechnete Marktdaten; ein eigenes probabilistisches Renditeprognosemodell wurde nicht gefunden. Die pauschalen Aussagen „keine News-Vorverarbeitung“, „Statistik nur nachträglich“ und „Jev nur REVIEW-Fallback“ sind dagegen zu korrigieren. Security-Scan und erster dokumentierter Paper-Fill machen Teile der o31-Lückenliste bereits überholt, während andere Umsetzungsaussagen — besonders zur Ordernettierung — zu stark sind. Für eine evidenzbasierte Trading-Freigabe fehlen vor allem ein kostenbereinigter Portfolio-Nachweis, unabhängige Validierung und vollständig belegter Betrieb. Auch ein vollständig erfüllter Plan kann künftige Profitabilität nicht garantieren.