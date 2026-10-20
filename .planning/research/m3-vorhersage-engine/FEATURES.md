# Feature-Recherche: M3 Vorhersage-Engine (Europa)

**Domäne:** kalibrierte Wahrscheinlichkeitsprognose (P(Benchmark nach Kosten geschlagen), 5 d / 20 d) für europäische Aktien, hybrides Modell aus Statistik und LLM-Merkmalen, Walk-forward-Validierung, Sizing und Go/No-Go-Gate
**Recherchiert:** 2026-10-20
**Gesamt-Konfidenz:** MITTEL. Die Methodik (Kalibrierung, Purging, DSR, Sizing) ist gut belegt (HOCH). Die Evidenz für Effektgrößen nach Kosten in Europa auf 5–20 Tagen ist dünn bis gemischt (NIEDRIG–MITTEL). Steuer- und Kostensätze je Land sind nur sekundär geprüft (MITTEL).
**Scope:** nur NEUE Funktionen von M3. Bereits vorhanden (nicht Gegenstand): LLM-Analysten, Debatte und PM-Rating, Memory-Log mit Settlement (`tradingagents/memory/settlement.py`, Alpha vs. Benchmark, `ENTRY_CONVENTION = "next_close"`), Backtest-Summary, `patterns/evaluate.py` (Wilson, `MIN_N=20`), Jev-Hooks (`tradingagents/jev/`), Kostenbudget (`tradingagents/budget.py`), IBKR-Paper-Executor (`scripts/ibkr_executor.py`, `scripts/daily_paper_run.py`).

---

## 0. Nüchterne Vorbemerkung: was die Evidenz hergibt

Diese Zahlen begründen die Kategorisierung unten. Sie sollten vor jeder Phasenplanung bekannt sein.

1. **Kurzfristige Signale sind vor Kosten real, nach Kosten aber schmal.** Novy-Marx/Velikov (RFS 2016) zeigen: Anomalien mit mehr als ca. 50 % monatlichem einseitigem Umschlag überleben Kosten selten. Ausgenommen sind Varianten, die gezielt auf Kosten gebaut sind (Buy/Hold-Spanne). Ein 5-Tage-Horizont mit vollständigem Umschlag erzeugt etwa 400 % Umschlag pro Monat. Bei 20 bp pro Seite sind das rund 1,6 % Kosten pro Monat, die das Signal erst verdienen muss.
2. **Effekte schrumpfen nach der Veröffentlichung.** McLean/Pontiff (JF 2016) messen etwa −58 % Rendite nach Publikation, ungefähr −26 % davon außerhalb der Stichprobe. Jensen/Kelly/Pedersen (JF 2023) finden, dass die meisten Faktoren replizieren, auch international. Ihre Effektgrößen sind aber Monats-Long-Short-Prämien, keine Long-only-Überrenditen nach 20 bp pro Seite auf 5 Tagen.
3. **Rechnung zur Teststärke für das Gate (eigene Schätzung, Annahmen offengelegt).** Annahme: Die idiosynkratische Überrendite einer europäischen Large-Cap hat über 20 Tage eine Standardabweichung von ca. 6–9 %. Bei n = 300 wirklich unabhängigen Fällen ergibt sich SE ≈ 0,35–0,52 %. Ein 90-%-KI ohne Null verlangt dann eine **mittlere Netto-Überrendite von ca. 0,6–0,85 % je 20-Tage-Fall**. Das sind annualisiert etwa 7–10 % Netto-Alpha je Position. Für 5 Tage (Standardabweichung ca. 3–4,5 %) liegt die Schwelle bei ca. 0,3–0,45 % netto je Fall, also bei 0,7–0,85 % brutto nach 40 bp Round-Trip. **Das liegt über allem, was die Literatur für Long-only-Signale dieser Art nach Kosten belegt.** Die Folge: Das Gate ist korrekt streng, und **No-Go ist das wahrscheinlichste Ergebnis.** Die Planung muss das als regulären Ausgang behandeln. Ein ehrliches No-Go ist kein Projektfehler. (Konfidenz der Größenordnung: MITTEL. Die exakte Varianz wird in der ersten Validierungsphase gemessen.)
4. **Die Annahme „20 bp pro Seite“ gilt nicht in ganz Europa.** Kaufseitige Transaktionssteuern kommen hinzu: UK-Stempelsteuer 0,5 %, französische FTT 0,3–0,4 % (Large Caps > 1 Mrd. €), Spanien 0,2 %, Italien 0,1–0,2 %. Irland (1 %) und Belgien (TOB) werden in der Praxis ebenfalls genannt, sind hier aber ungeprüft. Ein 5-Tage-Kauf einer UK-Aktie kostet damit über 70 bp Round-Trip. Daraus folgt eine Table-Stakes-Funktion (Kostenmodell je Land, siehe unten). (Konfidenz MITTEL, Quellen: Tax Foundation, IBKR-Gebührenseite. Vor der Umsetzung amtlich prüfen.)

---

## Feature Landscape

### Table Stakes (ohne diese ist das Ergebnis nicht vertrauenswürdig)

Table Stakes bedeutet hier: Fehlt die Funktion, ist jede Gate-Aussage wertlos. Gemeint ist nicht, dass Nutzer sie „erwarten“.

#### A. Zielgröße und Labels

| Funktion | Warum unverzichtbar | Komplexität | Hinweise / Abhängigkeit zum Bestand |
|---|---|---|---|
| **Label-Spezifikation, versioniert (PRED-01)**: `y_h = 1[ r_i(t+1→t+1+h) − r_B(t+1→t+1+h) − 2·c_i > 0 ]`, h ∈ {5, 20} Handelstage, Einstieg am nächsten Schluss (`next_close`), `c_i` = Kosten je Seite **je Titel/Land** | Ohne eingefrorene Definition kann man die Zielgröße nachträglich „passend“ machen. Kosten im Label bewirken, dass die Basisrate ehrlich unter 50 % liegt (typisch 40–47 %). | NIEDRIG | Nutzt `fetch_returns` und `ENTRY_CONVENTION` aus `settlement.py`. Diese rechnen heute ohne Kosten, mit SPY als Default und mit Yahoo-Closes. Neu sind ein Benchmark je Universum (STOXX Europe 600 Net Return, zum Handeln ein ETF-Proxy) und `c_i`. Konvention und ungerundete Werte gehören in den Log-Eintrag (VAL-06). |
| **Ties und fehlende Daten explizit** (Handelsaussetzung, Delisting im Fenster, Kapitalmaßnahme) | Delisting-Renditen und Splits verfälschen Labels still. Ohne Regel entsteht ein Survivorship-Effekt. | MITTEL | Braucht point-in-time-Kapitalmaßnahmen (gekaufte Daten, Entscheidung 5). Regel: Delisting → letzter Kurs bzw. Abfindungskurs; ein fehlender Benchmark-Schluss bedeutet *pending* statt *settled* (wie heute #1169). |
| **Umgang mit Überlappung**: tägliche Stichproben mit h = 20 überlappen zu 95 %. Training mit Gewichten nach Eindeutigkeit (*average uniqueness*, López de Prado AFML Kap. 4). Evaluation auf **nicht-überlappenden Stichproben** (alle h Tage, mit versetzten Startoffsets als Robustheitscheck). KI per Block-Bootstrap nach Datum oder HAC/Newey-West mit Lag ≥ h. | Überlappende Labels blähen n und t-Werte um bis zu √h auf (Hansen/Hodrick 1980; Britten-Jones/Neuberger/Nolte 2011). Das Gate verlangt *unabhängige* Fälle. | MITTEL | Definition „unabhängiger Fall“ = (Titel, nicht-überlappendes Fenster). Zusätzlich muss die **Querschnittskorrelation** am selben Datum geclustert werden: 50 Titel am selben Tag sind keine 50 unabhängigen Fälle. Die Definition muss im Gate-Protokoll stehen, bevor die OOS-Periode beginnt. |
| **Zwei Horizonte als getrennte Modelle bzw. Köpfe**, nicht als ein Modell mit Horizont-Feature | Die Effekte haben unterschiedliche Vorzeichen: 1-Monats-Reversal vs. 12-1-Momentum. Ein gemeinsames Modell vermischt das. | NIEDRIG | Zwei Kalibrierungsberichte, zwei Gate-Zeilen. Die Bonferroni-Logik zählt beide Horizonte als Varianten. |

#### B. Merkmalsfamilien (Basis-Set; Evidenz nüchtern)

| Familie | Evidenz (Europa, 5–20 d, nach Kosten) | Komplexität | Hinweise / Abhängigkeit |
|---|---|---|---|
| **Kurzfrist-Reversal (1 W / 1 M), bevorzugt *residual*** (Rendite nach Herausrechnen von Markt/Sektor) | Klassisch (Jegadeesh 1990; Lehmann 1990) stark vor Kosten, roh nach Kosten weitgehend weg. De Groot/Huij/Zhou (JBF 2012, US): **30–50 bp/Woche netto** nur mit Large Caps und umschlagarmer Konstruktion. Blitz/Huij/Lansdorp/Verbeek (2013): residual reversal netto signifikant, auch Large Caps nach 1990. Europa 1990–2016 (RIBAF 2019): residual besser als roh, **robust in FR/DE, fragil in kleinen Ländern**. Medhat/Schmeling (RFS 2022): Bei Titeln mit hohem Umschlag kehrt sich das Vorzeichen zu *short-term momentum* um. **Gesamt: MITTEL vor Kosten, NIEDRIG–MITTEL nach 20 bp + FTT.** | NIEDRIG | Nur Kurse nötig (PIT-Daten). Interaktion mit Umschlag als Feature aufnehmen (Medhat/Schmeling). Wichtigster Kandidat für h = 5, aber auch der kostensensitivste. Kein Bezug zum LLM-Pfad. |
| **Momentum 12-1 (und Industrie-Momentum)** | Rouwenhorst (JF 1998): 12 europäische Länder, ca. 1 %/Monat Long-Short; Fama/French (JFE 2012): Momentum in Europa stark. Van Dijk/Huibers (FAJ 2002): europäisches Momentum hängt mit der Unterreaktion der Analysten zusammen. Crash-Risiko (Daniel/Moskowitz 2016). **Monatliche Prämie, daher für h = 20 plausibel, für h = 5 schwach.** Long-only fängt nur einen Teil der Prämie ein. **MITTEL.** | NIEDRIG | Gleichzeitig **Baseline** (siehe unten). Wird es Feature und Baseline zugleich, muss das Modell die Momentum-Baseline *schlagen*, nicht nur replizieren. |
| **Quality / Value / Profitabilität** | International robust (Fama/French 2012; Asness/Frazzini/Pedersen „QMJ“ RAS 2019; JKP 2023). Langsame Signale mit kleinem Monatseffekt, daher **auf 5–20 d fast nur Kontrollvariable bzw. Risikoneutralisierung, kaum eigener Edge.** Umschlagarm, daher überlebt das Signal Kosten (Novy-Marx/Velikov). **MITTEL als Signal über Monate, NIEDRIG als Erklärung von 5–20-d-Überrenditen.** | MITTEL | Braucht **point-in-time-Fundamentaldaten mit Veröffentlichungsdatum** (nicht Periodenende). Ohne Reporting-Lag entsteht Look-ahead. Abhängig vom Datenkauf (Entscheidung 5). |
| **Earnings Surprise / PEAD** (SUE, Ankündigungsrendite) | Klassisch stark (Bernard/Thomas 1989), UK belegt (Liu/Strong/Xu 2003). Martineau (CFR 2022): **für US Large Caps seit ca. 2006 verschwunden**, umstritten (2025 Gegenpapiere, Unterschiede im Design). Ng/Rusticus/Verdi: Kosten fressen große Teile, der Effekt sitzt in teuren Titeln. Europa: vor allem Abschlussarbeiten; ein PSI-20-Test über 20 d ist nach Kosten unbefriedigend. **NIEDRIG–MITTEL für europäische Large Caps nach Kosten.** | MITTEL | Braucht Ankündigungskalender und Konsensschätzungen point-in-time. Bei den günstigen Anbietern (20–80 €/Monat) ist das oft nicht enthalten. **Kauf vor Phase 3 prüfen.** Ersatz ohne Konsens: Ankündigungsrendite (Rendite um das Ereignis) als Proxy für die Überraschung, nur Kurse nötig. |
| **Analystenrevisionen** (Netto-Revisionen, Konsensänderung) | Europa belegt, aber alt: Capstaff/Paudyal/Rees (UK/FR/DE), McKnight/Todd (FM 2006), Effekt stärker bei Abwärtsrevisionen und wenig abgedeckten Titeln. Bird/Casavecchia: Analysten folgen eher den Preisen. **MITTEL vor Kosten, Aktualität unklar (Stichproben vor 2010).** | MITTEL–HOCH | IBES-ähnliche Daten sind für das Budget von 150 €/Monat praktisch unerreichbar. **Kandidat für das LLM**: Ratingänderungen und Kurszieländerungen aus archivierten News als Ereignistyp extrahieren (siehe E). |
| **News-Sentiment / Ereignisse** | Tetlock (JF 2007), Tetlock/Saar-Tsechansky/Macskassy (JF 2008): Wortlisten-Sentiment sagt Renditen über 1–2 Tage voraus. Heston/Sinha (FAJ 2017): **tägliche News wirken ca. 2 Tage, wöchentlich aggregierte News ein Quartal; negative News werden verzögert verarbeitet** (oft bis zum nächsten Earnings-Termin). Ke/Kelly/Xiu (2019): Text-Signal stark, Großteil am Tag 0–1. Lopez-Lira/Tang (2023–2025): GPT-Scores sagen Renditen voraus; 2023: >500 % kumuliert vor Kosten, 350 % bei 10 bp, **50 % bei 25 bp** in 15 Monaten. Die aktuelle Fassung betont, dass der *Drift* (nicht die initiale Reaktion) vor allem bei **kleinen Titeln und negativen News** vorhersagbar ist und mit zunehmender LLM-Nutzung abnimmt. **Gesamt: Tag-0/1-Reaktion stark, aber nicht handelbar, wenn der Lauf vor Börsenöffnung mit Einstieg zum Schluss stattfindet. Der handelbare Rest auf 5–20 d bei europäischen Large Caps nach 20 bp: NIEDRIG.** | HOCH | Braucht das **News-Archiv ab heute** (Entscheidung 5), also **keine historische Backtest-Basis**. Der Beitrag des LLM kann nur prospektiv in den 6 Monaten Paper gemessen werden. Wöchentliche Aggregation mit Abklingen (Heston/Sinha) passt zu h = 20. |
| **Risiko- und Kontrollmerkmale**: Volatilität (20/60 d), Beta zum Benchmark, Größe, Liquidität (ADV, Spread-Proxy), Sektor/Land | Kein eigener Edge, aber notwendig, damit das Modell nicht nur Beta/Volatilität „vorhersagt“ (in Up-Märkten gewinnt High-Beta) | NIEDRIG | Pflicht auch für das Sizing (Abschnitt F). Sektor- und Länderneutralisierung von Features per Querschnitts-Rang je Datum. |

**Konsequenz für die Merkmalsauswahl:** Die Familien werden *vorab* festgelegt (5–7 Familien, max. ca. 20–30 Features). Jede weitere Familie zählt als Variante für die Mehrfachtest-Kontrolle. Kein „Feature-Mining“.

#### C. Modell und Wahrscheinlichkeitsausgabe

| Funktion | Warum unverzichtbar | Komplexität | Hinweise |
|---|---|---|---|
| **Regularisierte logistische Regression auf querschnittlich gerankten Features als Primärmodell**, Gradient Boosting höchstens als zweite, gezählte Variante | Bei realistisch ca. 10–50 k Trainingszeilen (EU-Universum ca. 100–300 Titel, 10–15 Jahre) und schwachem Signal (AUC 0,51–0,55) gewinnen einfache Modelle an Robustheit. Logit ist zudem von Haus aus ungefähr kalibriert. | NIEDRIG–MITTEL | Neues Modul, keine Abhängigkeit vom LLM-Graph. Ausgabe je (Titel, Datum, h): `p`, Modellversion, Feature-Hash. |
| **Nachkalibrierung (Platt bzw. isotonic) auf einem eigenen, zeitlich späteren Kalibrierungsfenster** | Boosting-Ausgaben sind schlecht kalibriert (Niculescu-Mizil/Caruana 2005). Isotonic braucht viele Daten (> ca. 1000 je Fenster), sonst Platt. | NIEDRIG | Kalibrierung *innerhalb* des Walk-forward. Sonst entsteht Leakage. |
| **Wahrscheinlichkeit in 100 % der Entscheidungen persistiert (PRED-02)** | Ohne lückenlose `p` kein Kalibrierungsbericht. Fehlende Werte gelten als Laufehler. | NIEDRIG | Erweiterung des Memory-Logs bzw. Paper-Logs (`scripts/ibkr_paperlog.py`). Das bestehende LLM-Rating wird **zusätzlich** gespeichert und ist eine eigene Baseline. |

#### D. Baselines (VAL-02)

| Baseline | Zweck | Komplexität | Hinweise |
|---|---|---|---|
| **Benchmark halten** (STOXX Europe 600 bzw. ETF-Proxy, Alpha = 0 vor Kosten) | Nullpunkt für Alpha | NIEDRIG | Benchmark-Wechsel in `resolve_benchmark`/`benchmark_map` (heute SPY-Default). |
| **Klimatologie-Wahrscheinlichkeit** (rollende Basisrate von `y_h`) | Referenz für den Brier Skill Score. Ein Modell, das die Basisrate nicht schlägt, hat keine Auflösung. | NIEDRIG | Pflichtbaseline für die Kalibrierung, oft vergessen. |
| **Zufallsauswahl bei gleichem Exposure, Umschlag und Kosten**, ≥ 1000 Ziehungen | Verteilung „Glück“. Das Modell-Alpha wird als Perzentil darin berichtet. | NIEDRIG | Gleiche Anzahl Positionen pro Datum, gleiche Haltedauer, gleiches Kostenmodell. |
| **Momentum 12-1 (Top-Quantil)** und **Kurzfrist-Reversal (Bottom-Quantil 1 M)** | Ein „billiger“ Faktor muss geschlagen werden, sonst ist das Modell Faktor-Replikation mit Mehraufwand. | NIEDRIG | Dieselben PIT-Daten. |
| **Bestehende LLM-Engine (PM-Rating → Kauf)** | Die eigentliche Frage des Meilensteins: ist das neue System besser als das heutige? | NIEDRIG | Aus dem bestehenden Memory-Log bzw. Paper-Log. Achtung: Am 2026-10-16 waren 20 von 20 Entscheidungen kein Kauf. Eine nahezu leere Baseline ist als solche zu berichten. |

#### E. Validierung (VAL-01, 03, 04, 05)

| Funktion | Warum unverzichtbar | Komplexität | Hinweise |
|---|---|---|---|
| **Walk-forward mit expandierendem bzw. rollendem Fenster, Purging + Embargo ≥ h** (López de Prado AFML Kap. 7) | Ohne Purging lernt das Training aus Labels, die ins Testfenster reichen (Überlappung bei h = 20). | MITTEL | Fenster und Retrain-Kadenz (z. B. quartalsweise) werden vorab fixiert. Je Fenster werden Modell-, Feature- und Konfigurations-Hash protokolliert. |
| **Strikte Trennung: historisches Pseudo-OOS (gekaufte PIT-Daten, nur Kurs- und Fundamentalfeatures) vs. echtes prospektives OOS (6 Monate Paper, alle Features inkl. LLM)** | LLM-Features haben keine Historie, außerdem gibt es Look-ahead über das LLM-Training (Glasserman/Lin 2023; He/Lv/Manela/Wu 2025). Historische Tests eines LLM auf alten News sind kontaminiert. | MITTEL | **Das Gate darf das LLM-Inkrement nur auf prospektiven Daten nach dem Trainings-Cutoff des Modells bewerten.** Modell-ID und Cutoff stehen im Protokoll. |
| **Kostenmodell je Land/Börse im Simulator** (Kommission IBKR inkl. Mindestgebühr, Spread-Proxy, Slippage, FTT/Stempelsteuer kaufseitig), Sensitivität ×2 | 20 bp pauschal unterschätzt UK/FR/ES/IT deutlich. Mindestgebühren dominieren bei kleinen Tickets (erster Fill: ca. 0,29 % einseitig, N-06). | MITTEL | Kosten sind ein Input des Labels (A) und des Sizings (F): eine Quelle der Wahrheit. Alternative: Universum auf Länder ohne FTT beschränken (DE, NL, CH, Nordics) — **Entscheidung für den Operator.** |
| **Konfidenzintervall für Netto-Alpha per Block- bzw. stationärem Bootstrap nach Datum** (Politis/Romano 1994), Blocklänge ≥ h | Zeit- und Querschnittsabhängigkeit. Ein naiver t-Test überschätzt die Signifikanz. | MITTEL | Ersetzt bzw. ergänzt den Wilson in `patterns/evaluate.py` (der i.i.d. annimmt, ok für Trefferquoten, nicht für Alpha). |
| **Varianten-Register + Mehrfachtest-Korrektur (VAL-05)**: Jede getestete Kombination aus Modell, Featureset, Horizont und Prompt wird gezählt. Bericht: **Deflated Sharpe Ratio** (Bailey/López de Prado 2014) mit tatsächlicher Variantenzahl. Bei mehreren Hypothesen: Holm bzw. Romano-Wolf, oder Hansen SPA / White Reality Check gegen die Baselines | Harvey/Liu/Zhu (RFS 2016): t > 3 als Hürde für neue Faktoren. Ohne Zählung ist jede Signifikanz aus der Suche entstanden. | MITTEL | Register als Append-only-Datei im Repo. Die DSR braucht Schiefe und Kurtosis der Strategie-Renditen und die Varianz der Sharpe-Werte über die Versuche. Geringer Rechenaufwand. |
| **Effektive Fallzahl im Bericht (VAL-04)**: Roh-n, nicht-überlappendes n, Cluster nach Datum | Die Gate-Schwelle „300 unabhängige Fälle“ muss operationalisiert sein | NIEDRIG | Festlegen: n_unabh = Anzahl (Titel × nicht-überlappende Fenster). Das KI wird über Datums-Blöcke gebootstrapt. Beide Zahlen werden berichtet. |

#### F. Kalibrierungsbericht (PRED-03)

| Funktion | Warum unverzichtbar | Komplexität | Hinweise |
|---|---|---|---|
| **Brier Score + Murphy-Zerlegung (Reliability, Resolution, Uncertainty) + Brier Skill Score vs. Klimatologie** | Ein Proper Scoring Rule (Gneiting/Raftery 2007). Die Zerlegung zeigt, ob das Modell *auflöst* oder nur die Basisrate trifft. | NIEDRIG | Realistisch ist ein BSS von **0–2 %**. Die Entwurfsschwelle „mind. 5 % besser“ (PRED-03) ist bei Aktien-Überrenditen unrealistisch und sollte gegen Literaturwerte neu gesetzt werden. |
| **Log-Loss** | Bestraft Überkonfidenz an den Rändern | NIEDRIG | — |
| **Reliability-Diagramm mit 5–10 Bins gleicher Besetzung und Bootstrap-Bändern**, plus **Kalibrierungs-Intercept und -Steigung** (logistische Rekalibrierung) | Bei schwachen Signalen konzentrieren sich die `p` in 0,40–0,60. Bins mit gleicher Breite sind dann leer. Die Steigung < 1 zeigt Überkonfidenz kompakter als ECE. | NIEDRIG | ECE (Guo et al. 2017) wird berichtet, ist aber **binning-abhängig und bei kleinem n verzerrt**. Deshalb zusätzlich Steigung und Intercept, nicht ECE allein als Gate-Kriterium. |
| **Getrennte Berichte je Horizont, Land/Sektor, Regime (Volatilität hoch/niedrig)** | Kalibrierung bricht typischerweise in Teilgruppen | NIEDRIG | Nur deskriptiv, nicht als weitere Gate-Tests (sonst Mehrfachtests). |

#### G. Sizing und Risiko (RISK-01…05)

| Funktion | Warum unverzichtbar | Komplexität | Hinweise |
|---|---|---|---|
| **Volatilitäts-Targeting je Position**: `w_i = min(cap_i, risk_budget / σ_i)`, σ aus 20/60-d-EWMA | Heute feste Leiter (H-09). Vol-Targeting reduziert Tail-Risk in Aktien belegt (Harvey et al., JPM 2018; Moreira/Muir JF 2017 für Faktoren). | NIEDRIG | Ersetzt die Stückleiter im Executor. Limits in Geld statt Stück (RISK-02). |
| **Konfidenzskalierung über die Edge über dem Break-even**: Gewicht ∝ `max(0, p − p_be)`, wobei `p_be` die Basisrate bzw. Kosten-Schwelle ist; **keine Position bei p ≤ p_be + Marge** | Kosten im Entscheidungspfad (Ziel 3). Die Marge ist eine Buy/Hold-Spanne, die Umschlag reduziert (Novy-Marx/Velikov). | NIEDRIG | Die Hysterese (Einstieg bei p > a, Halten bis p < b < a) senkt den Umschlag deutlich. Für h = 5 wahrscheinlich entscheidend. |
| **Fractional Kelly nur als *Obergrenze*** (¼–½ Kelly, `f ≈ μ/σ²` mit geschrumpftem μ aus der kalibrierten `p`) | Kelly ist extrem empfindlich gegenüber Fehlern in μ: Eine um 2 pp überschätzte `p` kann das Vorzeichen umdrehen (MacLean/Thorp/Ziemba 2011). Als Deckel ist er nützlich, als Treiber gefährlich. | NIEDRIG | Harte Kappen greifen zuerst: z. B. 0,5 % NAV Risiko je Position, 5 % NAV je Titel, Brutto ≤ 100 %, Länder- und Sektorkappen. |
| **Portfolio-Drawdown- und Tagesverlust-Kill (RISK-03)** mit Zustandsmaschine (aktiv → reduziert → Kill → manuelle Freigabe) | Das Gate verlangt maxDD ≤ 15 %. Ein Kill bei z. B. 10 % gibt Puffer für Gaps. | MITTEL | Integration in die vorhandenen Guardrails und den Kill-Zustand des IBKR-Executors (M2). Negativkontrolle per simuliertem Verlauf. |
| **Modell-Gesundheitsstopp**: rollender Brier bzw. Log-Loss über N Wochen schlechter als Klimatologie → keine neuen Positionen | Ein Drawdown-Stopp reagiert auf P&L, ein Gesundheitsstopp auf den Prognoseverfall (Regime- oder Datenbruch). Er greift früher und ist kostenfrei. | NIEDRIG | Braucht settled Labels, also Verzögerung h. Für h = 20 träge, deshalb zusätzlich Daten-Qualitätsgates (DATA-03). |
| **Abbaupfad über das Orderlimit, Nettierung offener Orders (RISK-04/05)** | Bestehende Lücke aus M2 (N-07, N-08) | MITTEL | Reine M2-Executor-Erweiterung. |

**Zu Stops auf Einzeltitel:** Kaminski/Lo (JFM 2014) zeigen, dass Stop-Loss-Regeln nur bei Momentum-artigen Renditeprozessen Wert schaffen. Bei Reversal-Signalen (h = 5) schaden enge Einzeltitel-Stops: Sie verkaufen am Tief, und europäische Eröffnungs-Gaps machen Stop-Preise unzuverlässig. Deshalb: **Portfolio-Stopps ja, enge Einzeltitel-Stops nein** (siehe Anti-Features). Gap-Szenarien werden als Testfälle dokumentiert (RISK-04).

#### H. Go/No-Go-Protokoll (OPS-04)

| Bestandteil | Warum | Komplexität |
|---|---|---|
| **Vorregistrierung**: Das Protokoll wird *vor* dem Start der OOS-Periode committet (Commit-SHA und Datum im Protokoll). Inhalt: Hypothesen, Label-Definition (A), Universum je Datum, Benchmark, Kostenmodell, Baselines, Metriken, Schwellen, KI-Methode, Definition „unabhängiger Fall“, maximale Variantenzahl, Abbruchregeln | Schwellen, die man nach dem Ansehen setzt, sind keine Schwellen | NIEDRIG |
| **Teststärke vorab**: Welches Netto-Alpha ist mit n = 300 überhaupt nachweisbar (siehe Abschnitt 0)? | Verhindert, dass ein unterdimensioniertes Gate „knapp gescheitert“ als „fast Go“ gelesen wird | NIEDRIG |
| **Prüfpunkte mit binärem Ergebnis**: (1) n_unabh ≥ 300 und OOS ≥ 6 Monate; (2) Netto-Alpha > jede Baseline, 90-%-Bootstrap-KI der *Differenz* ohne 0; (3) DSR > 0,95 mit gezählten Varianten; (4) maxDD ≤ 15 %; (5) Ergebnis bei ×2-Kosten berichtet; (6) Kalibrierung berichtet (Steigung, BSS); (7) LLM-Inkrement berichtet (G); (8) Ausführung (OPS-03: 0 Doppelorders, 100 % Fill-Zuordnung); (9) Datenqualität (Abdeckung, Imputationsanteil) | Jeder Punkt ist als *erfüllt/nicht erfüllt* festzuhalten. Ein nicht erfüllter Pflichtpunkt bedeutet No-Go, ohne Ermessen. | MITTEL |
| **Entscheidungsregel und Folgen**: Go → nur gedeckelte Echtgeld-Pilotphase (Betrag vom Operator). No-Go → Meilenstein regulär beendet, Befunde archiviert. Kein „Nachschärfen und erneut auf denselben Daten testen“ | Dieselben OOS-Daten zweimal zu benutzen macht sie zu In-Sample-Daten | NIEDRIG |
| **Artefakte**: Bericht, Daten-Hashes, Varianten-Register, Konfigurations-Snapshots, Unterschrift des Operators mit Datum | Reproduzierbarkeit | NIEDRIG |

---

### Differentiators (Mehrwert über das Pflichtprogramm hinaus)

| Funktion | Nutzen | Komplexität | Hinweise / Abhängigkeit |
|---|---|---|---|
| **LLM als strukturierter Merkmalslieferant je Meldung**: JSON-Schema `{relevant: bool, ticker(s), event_type, sentiment ∈ [−1,1] (5-stufig), confidence ∈ [0,1], novelty (neu/Wiederholung), expected_horizon (Tage/Wochen), language}`, Temperatur 0, Modell-ID gepinnt, Prompt-Hash | Macht das LLM-Wissen messbar und ablatierbar. Ein freies „Rating“ ist es nicht. Konsistent mit Lopez-Lira/Tang (Score je Headline) und Heston/Sinha (Aggregation). | MITTEL | Baut auf dem bestehenden LLM-Client bzw. Provider-Setup auf (Anthropic in `.env`). Budget: bei ca. 100–300 Meldungen/Tag × Haiku-Klasse sind wenige €/Monat realistisch, ohne Batch-Rabatt prüfen (siehe STACK). |
| **Ereignistyp-Taxonomie (Europa-spezifisch)**: Ergebnis/Guidance (inkl. Gewinnwarnung), Ad-hoc-Mitteilung nach MAR Art. 17, Directors' Dealings (MAR Art. 19), Analysten-Rating/Kursziel, M&A/Übernahmeangebot, Kapitalmaßnahme (Kapitalerhöhung, Rückkauf, Dividendenänderung), Management-Wechsel, Recht/Regulierung, Produkt/Auftrag, Makro/Sektor, Sonstiges/irrelevant | Unterschiedliche Ereignisse haben unterschiedliche Drift-Profile: negative News verzögert (Heston/Sinha), Directors' Dealings in UK belegt (Fidrmuc/Goergen/Renneboog JF 2006). Die Taxonomie erlaubt Features je Typ und **ersetzt teure Analystendaten teilweise** (Revisionen aus News). | MITTEL | ≤ 12 Klassen, sonst kein verlässliches Labeln in 20 Minuten. Quellen: EQS/DGAP-News, RNS (LSE), Euronext-Mitteilungen, Unternehmens-RSS. Mehrsprachig DE/FR/EN. |
| **Anonymisierung der Firmennamen vor dem Scoring** (Glasserman/Lin 2023) | Reduziert den *distraction effect* (Vorwissen über große Firmen verzerrt das Sentiment), der in-sample stärker war als der Look-ahead | NIEDRIG | Ticker und Name werden durch Platzhalter ersetzt. Als gezählte Variante gegen die nicht-anonymisierte Fassung testen. |
| **Aggregation mit Abklingen**: `S_i,t = Σ conf·sent·exp(−Δt/τ)`, τ ≈ 3 d (h = 5) bzw. ≈ 10 d (h = 20), plus Zähler „News-Intensität“ und Anteil negativer Meldungen | Wöchentliche Aggregation trägt länger als tägliche (Heston/Sinha). Asymmetrie Negativ/Positiv. | NIEDRIG | Ergebnis sind 3–5 LLM-Features je Titel und Tag. |
| **Ablation des LLM-Beitrags (PRED/DATA-04)**: Modell A (ohne LLM-Features) vs. Modell B (mit), **gleiche Folds, gleiche Tage**. Gepaarter Vergleich von Log-Loss/Brier (Diebold-Mariano mit HAC) und von Netto-Alpha (Bootstrap der Differenz). Zusätzlich **Permutationsablation** (LLM-Features innerhalb des Datums permutieren) | Entscheidung 3 verlangt die getrennte Messung. Nur der gepaarte Test hat bei kleinem prospektivem n genug Teststärke. | MITTEL | Läuft ausschließlich auf dem prospektiven Archiv. Nach 6 Monaten ist die Teststärke wahrscheinlich *nicht* ausreichend für eine signifikante Aussage. Das wird als „unentschieden“ berichtet, nicht als „kein Effekt“. |
| **Veto-Ablation mit Kontrafaktum**: Das LLM-Veto wird nur protokolliert und *nicht* ausgeführt (Schattenmodus, analog zu Jev), oder zufällig 50 % der Vetos werden ignoriert. Gemessen wird die Netto-Rendite der vetoten Fälle vs. der nicht vetoten | Ein Veto, das ungeprüft wirkt, entfernt Trades unbeobachtbar. Man weiß nie, ob es geholfen hat. | NIEDRIG–MITTEL | Nutzt das Muster von `tradingagents/jev/hooks.py` (Schattenmodus). Veto-Rate berichten. Ein Veto darf nur reduzieren, nie vergrößern. |
| **Sampling-Streuung des LLM (PRED-04)**: k = 3–5 Wiederholungen auf einer Zufallsstichprobe von Meldungen, Übereinstimmung (Fleiss-κ) und Std der Scores | Bei Temperatur > 0 oder Modell-Updates ist das Feature verrauscht. Zeigt, ob `confidence` informativ ist. | NIEDRIG | Nur Stichprobe (Kosten). Modellwechsel beim Provider ist ein Strukturbruch und wird im Varianten-Register vermerkt. |
| **News-Labeling-Workflow (Entscheidung 8)** — siehe eigener Abschnitt unten | Einziger externer Prüfstein für die LLM-Merkmale; Grundlage für Jev-Kalibrierung | MITTEL | Kleine lokale Oberfläche. |
| **Jev-Post-Screening im Schattenmodus mit Wirkungsmessung** | Jev-Urteile werden wie ein weiteres Feature behandelt. Ihr hypothetischer Beitrag wird ablatiert. | NIEDRIG | Vorhanden: `tradingagents/jev/`. Neu ist nur die Protokollierung neben `p` und der Eingang in die Ablation. |
| **Probability of Backtest Overfitting (PBO, CSCV, Bailey et al. 2017)** auf dem historischen Pseudo-OOS | Ergänzt die DSR um eine verteilungsfreie Overfitting-Schätzung über die Variantenmatrix | MITTEL | Nur sinnvoll, wenn ≥ ca. 10 Varianten existieren. Sonst reicht die DSR. |
| **Beta-Neutralisierung über einen Index-Future bzw. ETF-Short** | Trennt Alpha vom Marktbeta bei Long-only. Der Drawdown wird dann vom Alpha bestimmt, nicht vom Markt. | HOCH | Braucht Future-Berechtigungen und Margin auf dem Paper-Konto. **Eher v2.** Ohne Hedge den maxDD von 15 % gegen Markt-Crashes realistisch prüfen. Ein Long-only-Portfolio mit Beta ≈ 1 kann 15 % allein durch den Markt reißen. |
| **Datenqualitäts-Status je Tag und Quelle** (Abdeckung, Frische, Imputationsanteil) mit Sperre neuer Positionen bei Unterschreitung (DATA-03) | Verhindert Handeln auf halben Daten. Das Archiv wird so zur Evidenz. | NIEDRIG–MITTEL | Erweitert den Heartbeat bzw. die Soll-Ist-Logik aus M2-Phase 7. |

---

### Anti-Features (verlockend, aber schädlich)

| Funktion | Warum gewünscht | Warum problematisch | Besser |
|---|---|---|---|
| **LLM gibt direkt die Wahrscheinlichkeit bzw. Kaufentscheidung** („LLM-as-forecaster“) | Wirkt einfach, die Engine kann es schon | Nicht kalibriert, nicht ablatierbar, Look-ahead bzw. Distraction (Glasserman/Lin), Modellwechsel beim Provider brechen die Serie. Entscheidung 3 schließt das aus. | LLM liefert Features und ein protokolliertes Veto. Die `p` kommt aus dem Statistikmodell. |
| **Historischer Backtest der LLM-Features auf gekauften bzw. gescrapten Alt-News** | „Wir wollen sofort Evidenz“ | Das LLM kennt die Ausgänge (Training vor dem Cutoff). Die Ergebnisse sind nach oben verzerrt (He/Lv/Manela/Wu 2025; Glasserman/Lin 2023). Kostet zudem den Backtest-Topf. | LLM-Features nur prospektiv. Den historischen Backtest auf Kurs- und Fundamentalfeatures beschränken. |
| **Trefferquote (Accuracy) bzw. AUC als Erfolgsmaß** | Intuitiv | Bei p ≈ 0,5 und asymmetrischen Renditen sagt die Trefferquote nichts über das Netto-Alpha. Nicht-Ziel laut Kontext. | Netto-Alpha mit KI, Brier/Log-Loss, Kalibrierungssteigung. |
| **Feature-Mining über Dutzende Indikatoren bzw. Hyperparameter-Suche ohne Register** | „Mehr Features = besseres Modell“ | Garantierte Überanpassung. Die DSR straft mit jeder Variante. Harvey/Liu/Zhu: t > 3. | 5–7 vorregistrierte Familien. Jede Änderung ist eine gezählte Variante. |
| **Kelly-Sizing als Treiber** | „Mathematisch optimal“ | Optimal nur bei *bekannter* Edge. Bei geschätzter, schwacher Edge entstehen Überwetten und Ruin-artige Drawdowns. | Vol-Targeting + Edge-Skalierung, Kelly nur als Deckel (¼–½). |
| **Enge Stop-Loss bzw. Trailing-Stops je Titel** | Fühlt sich nach Risikomanagement an | Schaden bei Reversal-Signalen (Kaminski/Lo 2014). Europäische Eröffnungs-Gaps, mehr Umschlag und Kosten. | Portfolio-Drawdown-Kill, Modell-Gesundheitsstopp, Positionskappen. |
| **Daily Rebalancing bei h = 20 bzw. volles Umschichten bei h = 5 ohne Hysterese** | Maximal „aktuelles“ Signal | Der Umschlag frisst das Alpha (Abschnitt 0). | Buy/Hold-Spanne, gestaffelte Kohorten (1/h des Buchs pro Tag), Mindest-Edge. |
| **ECE als alleiniges Gate-Kriterium bzw. Schwelle „Brier 5 % besser“** | Eine Zahl, leicht zu prüfen | ECE ist binning-abhängig und bei n ≈ 300 verrauscht. 5 % BSS ist bei Aktien unrealistisch: Ein schwaches, *echtes* Signal würde verworfen, eine Überanpassung belohnt. | Kalibrierung *berichten* (wie Entscheidung 6). Gate-relevant ist das Netto-Alpha mit KI. Für die Kalibrierung höchstens eine Plausibilitätsschwelle (z. B. Steigung im KI ∋ 1, BSS ≥ 0). |
| **Gate-Schwellen nach Sicht auf die OOS-Daten anpassen bzw. OOS-Periode verlängern, „bis es reicht“** | „Fast geschafft“ | *Optional stopping* entwertet das KI | Fixe Dauer und Fallzahl, vorregistriert. Verlängerung nur als neue, separat ausgewertete Periode. |
| **Kleine und Mid Caps bzw. kleine Länder ins Universum, weil dort die Effekte größer sind** | Literatur zeigt größere Prämien | Genau dort sind Kosten, FTT und Spreads hoch, und die Effekte fragil (RIBAF 2019: Reversal fragil in kleinen Ländern). Ticket-Mindestgebühren bei kleinem Konto. | Liquide Large Caps (z. B. STOXX-600-Mitglieder mit ADV-Untergrenze), Universum je Datum point-in-time. |
| **Labeln mit sichtbarem LLM-Vorschlag** | Schneller | Anchoring: Die Übereinstimmung wird künstlich hoch | Blindes Labeln, LLM-Output erst nach dem Speichern zeigen. |
| **Die 50 Labels/Monat zum Trainieren bzw. Feintunen nutzen** | „Daten nicht verschwenden“ | Viel zu wenig für Training. Die Labels sind dann nicht mehr unabhängige Evaluation. | Labels nur für Evaluation, Kalibrierung der LLM-`confidence` und Prompt-Abnahme (gezählt). |

---

## News-Labeling-Workflow (Entscheidung 8): erwartetes Verhalten

**Ziel:** die LLM-Merkmale (Relevanz, Sentiment, Ereignistyp, `confidence`) gegen ein menschliches Urteil prüfen. **Nicht** Ziel: Trainingsdaten erzeugen.

1. **Stichprobe** (automatisch, monatlich): 50 Meldungen aus dem Archiv des Vormonats. **Stratifiziert** nach Sprache (DE/FR/EN), Quelle und vom LLM vergebenem Ereignistyp. Dazu ca. 10 Fälle *überabgetastet* mit hoher LLM-`confidence` und ca. 10 an der Entscheidungsgrenze. Die Gewichte werden gespeichert, damit Kennzahlen gewichtbar bleiben. Der Seed wird protokolliert.
2. **Oberfläche** (lokal, minimal, ca. 24 s je Meldung bei 20 Minuten): Überschrift + erster Absatz + Quelle + Datum, **Firmenname sichtbar, LLM-Urteil verborgen**. Felder: relevant ja/nein, Sentiment 5-stufig (−2…+2), Ereignistyp (Dropdown, ≤ 12 Klassen), „unklar“-Knopf. Tastaturbedienung. Speichern in einer Append-only-Datei (JSONL) mit Labeler-ID, Zeit und Schema-Version.
3. **Konsistenz**: ca. 5 Meldungen pro Monat sind Wiederholungen aus Vormonaten (intra-rater-Reliabilität). Bei einem einzigen Labeler ist das der einzige Rauschschätzer.
4. **Auswertung** (automatisch nach dem Labeln): gewichtetes Cohen-κ für Sentiment, κ für Ereignistyp, Spearman-ρ, Konfusionsmatrix. **Kalibrierung der LLM-`confidence`**: Übereinstimmungsrate je `confidence`-Bin. Trend über Monate. Nach 6 Monaten (ca. 300 Labels) ist das KI für κ etwa ±0,07–0,1 breit, also aussagekräftig für grobe Qualität, nicht für feine Prompt-Vergleiche.
5. **Konsequenzen**: Liegt κ unter einer vorab gesetzten Schwelle (z. B. 0,4 für Sentiment), wird das LLM-Feature als „nicht valide“ markiert. Die Ablation läuft weiter, die Gate-Aussage zum LLM erhält einen Vermerk. Prompt-Änderungen nur versioniert und als gezählte Variante. Altlabels bleiben gültig, wenn das Schema stabil ist.
6. **Jev**: Dieselbe Stichprobe kann dem Jev-Urteil gegenübergestellt werden. Kein zweiter Labeling-Aufwand.

Komplexität: MITTEL (UI klein, Auswertung klein, Disziplin groß). Abhängigkeit: News-Archiv (DATA-01) und LLM-Scoring-Pipeline müssen laufen, bevor das erste Labeling sinnvoll ist.

---

## Feature Dependencies

```
PIT-Daten (Kurse, Kapitalmaßnahmen, Fundamentals mit Publikationsdatum, Universum je Datum)  [gekauft, Entscheidung 5]
    └──requires──> Label-Spezifikation (A) inkl. Benchmark STOXX 600 + Kostenmodell je Land
                       └──requires──> Walk-forward + Purging/Embargo (E)
                                          └──requires──> Statistikmodell + Kalibrierung (C)
                                                             └──requires──> Kalibrierungsbericht (F)
                                                             └──requires──> Sizing/Edge-Schwelle (G)
                                                                                └──requires──> IBKR-Executor-Erweiterung (RISK-02/04/05, M2)

News-Archiv ab heute (DATA-01)  [selbst, Entscheidung 5]
    └──requires──> LLM-Scoring-Schema + Ereignistaxonomie
                       └──requires──> Aggregation zu Features
                                          └──enhances──> Statistikmodell (C) [nur prospektiv]
                       └──requires──> Labeling-Workflow (Validierung der LLM-Features)
                       └──requires──> Ablation LLM-Beitrag + Veto-Kontrafaktum

Baselines (D) ──requires──> dieselbe Label-/Kostenpipeline wie das Modell
Varianten-Register ──requires──> ab dem ersten Experiment aktiv (sonst nicht rekonstruierbar)
Go/No-Go-Protokoll ──requires──> Vorregistrierung VOR Beginn der 6-Monats-OOS-Periode
                    ──requires──> OPS-03 Paper-Bewährung (M2-Phasen 7–8, Heartbeat, Backup)

Kostenmodell je Land ──conflicts──> pauschale Gate-Annahme „20 bp/Seite“ (bei UK/FR/ES/IT-Titeln)
Historischer LLM-Backtest ──conflicts──> Validität des Gates (Look-ahead)
Einzeltitel-Stops ──conflicts──> Reversal-Signal (h = 5)
```

### Hinweise zu den Abhängigkeiten

- **Das News-Archiv ist der kritische Pfad in der Zeit**, nicht im Code: Jeder Tag ohne Archiv ist ein Tag weniger prospektive LLM-Evidenz. Das Archiv sollte **vor** allen anderen M3-Phasen produktiv laufen, notfalls als minimaler Sammler (Rohtext + Zeitstempel für Veröffentlichung und Erfassung) ohne Scoring.
- **Die Vorregistrierung erzwingt die Reihenfolge:** Label, Kosten, Baselines, Modellfamilie und Gate-Protokoll müssen stehen, *bevor* die 6 Monate zählen. Damit endet frühestens ca. 7–8 Monate nach Beginn der Phase 3 das Gate.
- **Die Kalibrierung braucht settled Labels.** Bei h = 20 kommt das erste Feedback 4 Wochen nach dem Start, der Gesundheitsstopp ist entsprechend träge.
- **Der europäische Benchmark ist eine Querschnittsänderung im Bestand:** `resolve_benchmark` und `benchmark_map` (heute SPY-Default), Börsenkalender (heute nur XNYS) und Laufzeit vor Börsenöffnung betreffen Settlement, Paper-Run und Executor gleichzeitig.
- **Die Währung muss vor dem Label festgelegt werden:** Rendite des Titels und des Benchmarks in derselben Währung (EUR-Perspektive) oder Universum auf Eurozone beschränken. Sonst steckt FX im Alpha. Heute vergleicht `fetch_returns` Prozentrenditen „each in its own currency“. Für SPY vs. US-Aktie war das unkritisch, für GBP/CHF-Titel vs. STOXX 600 (EUR) ist es falsch.

---

## MVP Definition

### Launch With (v1: alles, was das Gate braucht)

- [ ] News-Archiv-Sammler (Rohdaten, Zeitstempel, Qualitätsstatus je Tag): startet sofort, kritischer Pfad
- [ ] PIT-Datenbasis Europa + Universum je Datum + Kapitalmaßnahmen
- [ ] Label-Spezifikation 5 d/20 d mit Kostenmodell je Land und EU-Benchmark (eingefroren, versioniert)
- [ ] Baselines: Benchmark, Klimatologie, Zufall (1000×), Momentum, Reversal, bestehende LLM-Engine
- [ ] Walk-forward mit Purging/Embargo, Block-Bootstrap-KI, Varianten-Register, DSR
- [ ] Logit-Modell auf Reversal (residual), Momentum, Quality/Value-Kontrollen, Risiko-Features + Platt-Kalibrierung
- [ ] Kalibrierungsbericht (Brier + Zerlegung, BSS, Log-Loss, Reliability mit Bändern, Steigung/Intercept, ECE)
- [ ] LLM-Scoring je Meldung (Schema + Taxonomie) → aggregierte Features, prospektiv
- [ ] Ablation mit/ohne LLM und Veto im Schattenmodus mit Kontrafaktum
- [ ] Vol-Targeting + Edge-Schwelle + Hysterese, Geld-Limits, Drawdown-/Tagesverlust-Kill, Gesundheitsstopp
- [ ] Labeling-Oberfläche (blind) + monatliche Auswertung
- [ ] Vorregistriertes Go/No-Go-Protokoll mit Teststärke-Rechnung

### Add After Validation (v1.x)

- [ ] Earnings-Surprise/PEAD mit Konsensdaten, wenn ein bezahlbarer PIT-Konsens gefunden wird
- [ ] Gradient Boosting als zweite (gezählte) Modellvariante, wenn das Logit-Modell eine Auflösung > 0 zeigt
- [ ] PBO/CSCV, sobald ≥ 10 Varianten existieren
- [ ] Anonymisierte vs. nicht-anonymisierte LLM-Scores als Variante

### Future Consideration (v2+)

- [ ] Beta-Hedge über Index-Future: braucht Berechtigungen und Margin, ändert das Risikoprofil grundlegend
- [ ] US-Universum (Entscheidung 1)
- [ ] Analystenrevisionen aus Lizenzdaten: über Budget
- [ ] Eigenes bzw. chronologisch konsistentes Sprachmodell (ChronoBERT-Ansatz) für historische Text-Backtests

---

## Feature Prioritization Matrix

| Funktion | Nutzen | Aufwand | Priorität |
|---|---|---|---|
| News-Archiv-Sammler | HOCH (zeitkritisch) | NIEDRIG | P1, sofort |
| Label-Spezifikation + Kostenmodell je Land + EU-Benchmark | HOCH | MITTEL | P1 |
| PIT-Datenbasis + Universum je Datum | HOCH | MITTEL | P1 |
| Walk-forward/Purging/Bootstrap-KI/Varianten-Register/DSR | HOCH | MITTEL | P1 |
| Baselines (6) | HOCH | NIEDRIG | P1 |
| Logit + Platt + Kalibrierungsbericht | HOCH | NIEDRIG–MITTEL | P1 |
| Vol-Targeting/Edge-Schwelle/Kill/Gesundheitsstopp | HOCH | MITTEL | P1 |
| Go/No-Go-Protokoll (vorregistriert) | HOCH | NIEDRIG | P1 |
| LLM-Scoring-Schema + Taxonomie + Aggregation | MITTEL | MITTEL | P1 (Entscheidung 3) |
| LLM-/Veto-Ablation | MITTEL | MITTEL | P1 (Entscheidung 3) |
| Labeling-Oberfläche + Auswertung | MITTEL | MITTEL | P1 (Entscheidung 8) |
| Sampling-Streuung (PRED-04) | NIEDRIG–MITTEL | NIEDRIG | P2 |
| PEAD mit Konsens | MITTEL | HOCH (Daten) | P2 |
| Boosting-Variante, PBO | NIEDRIG–MITTEL | MITTEL | P2 |
| Beta-Hedge | MITTEL | HOCH | P3 |

---

## Vergleich: Wie es andere machen

| Funktion | Akademische Praxis (Faktor- und ML-Literatur) | Typische Retail-/LLM-Trading-Projekte | Unser Ansatz |
|---|---|---|---|
| Zielgröße | Querschnittsrang bzw. Überrendite, monatlich | Kursrichtung, oft ohne Kosten | Binär „schlägt Benchmark nach Kosten“, 5/20 d, Kosten je Land |
| Validierung | Rollierend OOS, t > 3, Replikation | In-Sample-Backtest, Sharpe ohne Varianten-Korrektur | Walk-forward + Purging + DSR + Register + Vorregistrierung |
| LLM | Score je Headline → Long-Short-Portfolio, post-cutoff | LLM entscheidet direkt | LLM = Feature + Veto, ablatiert, nur prospektiv bewertet |
| Kalibrierung | selten berichtet | nie | Brier-Zerlegung, Reliability, Steigung |
| Sizing | Gleich- bzw. Wertgewicht | fix bzw. Kelly | Vol-Target + Edge-Schwelle + Kelly-Deckel |
| Abbruch | — | — | vorregistriertes Gate, No-Go als gültiges Ergebnis |

---

## Sources

Konfidenz in Klammern: H = HOCH (Primärquelle bzw. etabliert), M = MITTEL (Primärquelle per Suche bestätigt, Details nicht vollständig gelesen), N = NIEDRIG (nur sekundär).

**Merkmale und Effektgrößen**
- De Groot, Huij, Zhou (2012), Another Look at Trading Costs and Short-Term Reversal Profits, JBF — [ERIM](https://www.erim.eur.nl/research/events/detail/1992/) (M; US-Stichprobe)
- Blitz, Huij, Lansdorp, Verbeek (2013), Short-Term Residual Reversal, JFM — [EFMA-Version](https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2011-Braga/papers/0259_update.pdf) (M)
- Residual return reversals: European evidence, RIBAF 50 (2019) — [RePEc](https://ideas.repec.org:443/a/eee/riibaf/v50y2019icp392-397.html) (M; Kostenanalyse im Volltext ungeprüft)
- Medhat, Schmeling (2022), Short-term Momentum, RFS — [CEPR DP15857](https://cepr.org/publications/dp15857) (M)
- Novy-Marx, Velikov (2016), A Taxonomy of Anomalies and Their Trading Costs, RFS — [NBER w20721](https://www.nber.org/papers/w20721) (H)
- Rouwenhorst (1998) International Momentum Strategies, JF; Fama/French (2012) Size, value, and momentum in international stock returns, JFE; Asness/Frazzini/Pedersen (2019) Quality minus junk, RAS; Jensen/Kelly/Pedersen (2023) Is There a Replication Crisis in Finance?, JF; McLean/Pontiff (2016) Does Academic Research Destroy Stock Return Predictability?, JF (H; aus Fachwissen, nicht neu abgerufen)
- Van Dijk, Huibers (2002), European Price Momentum and Analyst Behavior, FAJ — [CFA Institute](https://rpc.cfainstitute.org/en/research/financial-analysts-journal/2002/european-price-momentum-and-analyst-behavior) (M)
- Capstaff, Paudyal, Rees, Revisions of earnings forecasts and security returns: evidence from three countries — [Strathprints](https://strathprints.strath.ac.uk/8168/) (M); McKnight/Todd (2006) FM — [RePEc](https://ideas.repec.org/a/wly/finmar/v15y2006i5p201-224.html) (M); Bird/Casavecchia — [EFMA 2009](https://efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2009-Milan/papers/EFMA2009_0165_fullpaper.pdf) (M)
- Martineau (2022), Rest in Peace Post-Earnings Announcement Drift, CFR — [PDF](https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf); Gegenposition: [UCLA Anderson Review](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/) (M)
- Ng, Rusticus, Verdi, Implications of transaction costs for the PEAD — [LBS](https://www.london.edu/faculty-and-research/academic-research/i/implications-of-transaction-costs-for-the-post-earnings-announcement-drift) (M)
- PEAD PSI-20 / Euro Area (Abschlussarbeiten) — [RUN UNL](https://run.unl.pt/bitstreams/a3f823a1-90a9-4612-bd0c-08417bb17c4e/download), [RCAAP](https://rc.cplp.org/Record/rcaap_8d32f048546e450be3a2a81205c7ca96?lng=en) (N)
- Heston, Sinha (2017), News vs. Sentiment, FAJ — [FEDS 2016-048](https://www.federalreserve.gov/econresdata/feds/2016/files/2016048pap.pdf) (H)
- Lopez-Lira, Tang, Can ChatGPT Forecast Stock Price Movements? — [arXiv 2304.07619 v6](https://arxiv.org/pdf/2304.07619v6) (M; Zahlen versionsabhängig)
- Tetlock (2007) JF; Tetlock/Saar-Tsechansky/Macskassy (2008) JF; Ke/Kelly/Xiu (2019) Predicting Returns with Text Data; Fidrmuc/Goergen/Renneboog (2006) JF (H; Fachwissen)

**LLM-Look-ahead**
- Glasserman, Lin (2023), Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis — [arXiv 2309.17322](https://arxiv.org/abs/2309.17322) (H)
- He, Lv, Manela, Wu (2025), Chronologically Consistent Large Language Models — [arXiv 2502.21206](https://arxiv.org/html/2502.21206v3) (H)

**Validierung, Kalibrierung, Sizing** (Fachwissen, H)
- Bailey, López de Prado (2014), The Deflated Sharpe Ratio, JPM; Bailey/Borwein/López de Prado/Zhu (2017), The Probability of Backtest Overfitting, JCF; López de Prado (2018), Advances in Financial Machine Learning (Kap. 4, 7: Uniqueness, Purging, Embargo)
- Harvey, Liu, Zhu (2016), …and the Cross-Section of Expected Returns, RFS; White (2000) Reality Check; Hansen (2005) SPA; Romano/Wolf (2005) Stepwise multiple testing
- Politis, Romano (1994), The Stationary Bootstrap; Hansen/Hodrick (1980); Britten-Jones/Neuberger/Nolte (2011) overlapping returns
- Brier (1950); Murphy (1973) Zerlegung; Gneiting, Raftery (2007) Strictly Proper Scoring Rules; Niculescu-Mizil, Caruana (2005) Predicting Good Probabilities; Guo et al. (2017) On Calibration of Modern Neural Networks (ECE)
- Moreira, Muir (2017) Volatility-Managed Portfolios, JF; Harvey et al. (2018) The Impact of Volatility Targeting, JPM; MacLean, Thorp, Ziemba (2011) The Kelly Capital Growth Investment Criterion; Kaminski, Lo (2014) When Do Stop-Loss Rules Stop Losses?, JFM

**Kosten Europa**
- Tax Foundation, Financial Transaction Taxes in Europe — [Übersicht](https://taxfoundation.org/data/all/eu/financial-transaction-taxes-europe/) (M; FR 0,4 % vs. ältere 0,3 % widersprüchlich)
- Interactive Brokers, Summary of Third Party Transaction Fees — [IBKB 4017](https://ibkb.interactivebrokers.com/article/4017) (M)

**Bestand (Code gelesen)**
- `tradingagents/memory/settlement.py` (`resolve_benchmark`, `fetch_returns`, `ENTRY_CONVENTION`), `tradingagents/patterns/evaluate.py` (`wilson`), `tradingagents/jev/hooks.py`, `tradingagents/budget.py`, `scripts/ibkr_executor.py`, `scripts/daily_paper_run.py`

---
*Feature-Recherche für: M3 Vorhersage-Engine (Europa)*
*Recherchiert: 2026-10-20*
