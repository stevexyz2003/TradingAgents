# Meilenstein-Entwurf: Vorhersage-Engine

> **ENTWURF — nicht beschlossen.** Grundlage für `/gsd:new-milestone`; Ziele, Umfang und Schwellen entscheidet der Operator.

Stand: 2026-10-19, Prüfstand `4a55d2c`. Quelle: `261019-oxc-CODEX-REVIEW.md` (H-/N-Nummern dort).

## Ausgangslage

Die Entscheidung ist heute ein LLM-Urteil über Texte und berechnete Marktdaten; ein eigenes Prognosemodell (stochastisch, statistisch oder ML) existiert nicht (H-01, H-02). Technische Indikatoren und Sentiment sind LLM-Eingaben, kein Regelentscheider (H-04, H-06); die Musterschicht `patterns/` ist reine Nachauswertung (H-05). Statistik gibt es nachträglich (Settlement, Summary, Wilson mit `MIN_N=20`), ohne Kosten, ohne Out-of-Sample-Trennung und ohne Baselines (H-08, N-09, Lückenbewertung). Die Datenbasis ist dünn: fester Ticker-Pool, überlappende Fenster, nicht archivierte Feeds, aktuelle adjustierte Kurse (H-12, N-04); 20 von 20 Engine-Entscheidungen am 2026-10-16 waren kein Kauf (N-06). Die Positionsgröße ist eine feste Leiter ohne Konfidenz, Volatilität oder Stop (H-09), die Stückzahlgrenze ist keine Risikogrenze (N-08). Der erste Paper-Fill war ein markierter Pipeline-Test mit ca. 0,29 % einseitiger Kommission (N-06). Der Operator hält diesen Stand für echtes Trading nicht für ausreichend; Codex bewertet ihn als No-Go für Echtgeld.

## Ziele

1. Eine messbare Prognose mit ausgewiesener Unsicherheit je Entscheidung (Zielgröße, Horizont, Wahrscheinlichkeit/Verteilung), deren Kalibrierung berichtet wird.
2. Eine Validierung vor jeder Freigabe: zeitlich getrennte Out-of-Sample-Auswertung gegen definierte Baselines, mit Kosten.
3. Risiko und Kosten im Entscheidungspfad statt nur in der Nachauswertung.
4. Eine point-in-time-Datenbasis mit archivierten Eingaben und Qualitätsstatus.
5. Ein Go/No-Go-Gate mit vorab festgelegten Schwellen und ein Protokoll, das auch No-Go als gültiges Ergebnis festhält.

## Was kein Plan garantieren kann

Profitabilität ist nicht planbar und wird von diesem Meilenstein weder zugesagt noch als Ziel gesetzt. Planbar sind die Nachweisführung (was wird gemessen, gegen was, mit welcher Schwelle) und der Abbruch bei Nichterfüllung. **No-Go ist ein gültiges Ergebnis.**

## Anforderungskandidaten

Schwellwerte in eckigen Klammern sind Vorschläge, die der Operator festlegt. Kriterien beschreiben Nachweise, keine Renditezusagen.

### PRED: Prognose

| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft |
|---|---|---|---|
| PRED-01 | Zielgröße und Horizont der Prognose sind schriftlich definiert (z. B. Richtung oder erwartete Nettorendite über N Handelstage). | Ein Dokument legt Zielgröße, Horizont und Auswertungskonvention fest, bevor Ergebnisse ausgewertet werden; Änderung nur mit Versionsvermerk. | H-01, Codex-Dimension Vorhersage und Kalibrierung |
| PRED-02 | Je Entscheidung wird eine Wahrscheinlichkeit oder Verteilung neben dem Rating gespeichert. | In 100 % der protokollierten Entscheidungen steht ein maschinenlesbarer Wahrscheinlichkeitswert [für die gewählte Richtung]; fehlende Werte gelten als Fehler im Lauf. | H-01, H-10 |
| PRED-03 | Die Kalibrierung der Prognosen wird berichtet (Brier-Score, Log-Loss, Reliability-Tabelle). | Bericht je Auswertungslauf mit Brier/Log-Loss und Kalibrierungsfehler je Gruppe; Gate vergleicht gegen eine vorab definierte Baseline [mind. 5 % besser bei Kalibrierungsfehler höchstens 0,05]. | Codex Go/No-Go (Prognosegüte), H-10 |
| PRED-04 | Die Streuung des LLM-Samplings wird gemessen. | Pro Ticker und Handelstag werden [k = 5] unabhängige Läufe ausgewertet; Rating-Übereinstimmung und Wahrscheinlichkeitsstreuung werden berichtet; Temperatur und Modellversion stehen im Protokoll. | H-03 |

### VAL: Validierung

| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft |
|---|---|---|---|
| VAL-01 | Walk-Forward-Auswertung mit festen Out-of-Sample-Fenstern, Purging/Embargo über den Haltehorizont. | Auswertungsskript mit festgelegten Fenstern läuft reproduzierbar; Embargo mindestens Haltehorizont; Modell-/Prompt-/Konfigurationsstand je Fenster protokolliert. | Codex Dimension Out-of-Sample, N-09 |
| VAL-02 | Baselinevergleich: Cash, Buy-and-Hold, einfache technische Regeln, Zufallsstrategie bei vergleichbarem Exposure und Kosten. | Bericht mit allen vier Baselines je Zeitraum; Zufallsstrategie über [1000] Ziehungen mit Verteilung. | Codex Dimension Baselines, H-05 |
| VAL-03 | Kosten und Slippage sind im Portfolio-Simulator enthalten. | Annahme in bp [Spread + Slippage + Kommission, z. B. 10 bp einseitig, Sensitivität ×2] und Analyse-/LLM-Kosten werden im Bericht ausgewiesen; Ergebnis mit ×2-Kosten wird zusätzlich berichtet. | N-06, Codex Dimension Kosten |
| VAL-04 | Mindestfallzahl unabhängiger Fälle mit Abhängigkeitskorrektur. | Bericht trennt Rohfallzahl und effektiv unabhängige Fälle (Fenster, Ticker, Marktkorrelation); Gate-Schwelle [500 effektiv unabhängige Fälle, 30 Titel, 24 Monate OOS]. | H-12, N-09 |
| VAL-05 | Mehrfachtest-Kontrolle über Muster-, Prompt- und Modellvarianten. | Anzahl getesteter Varianten wird protokolliert; Korrektur (z. B. Bonferroni/FDR) ist im Bericht ausgewiesen; Konfidenzintervall berücksichtigt Zeit-/Tickerabhängigkeit. | N-09, Codex Dimension Baselines |
| VAL-06 | Settlement-Konventionen (Benchmark, Haltedauer, Eintrittskonvention) und Rundung werden im Log gespeichert statt aus aktueller Config abgeleitet; Ties sind explizit. | Neue Log-Einträge enthalten Konvention und ungerundete Rendite; Test belegt, dass sich ein Config-Wechsel nicht auf alte Einträge auswirkt. | N-02 |

### RISK: Risiko

| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft |
|---|---|---|---|
| RISK-01 | Positionsgröße folgt Volatilität und Konfidenz statt fester Leiter. | Dokumentierte Sizing-Formel; Test belegt: gleiche Rating-Eingabe mit höherer Volatilität führt zu kleinerer oder gleicher Größe; Risiko je Position [max. 0,5 % NAV]. | H-09, Codex Dimension Risiko |
| RISK-02 | Exposure-Limits in Geld statt Stück. | Limits je Titel [5 % NAV] und Brutto [100 %] werden vor jeder Order geprüft; Verstoß lehnt ab und wird protokolliert. | N-08 |
| RISK-03 | Drawdown- und Tagesverlust-Abschaltung. | Schwellen [Tagesverlust 2 %, Drawdown 10 %] lösen Kill-Zustand aus; Negativkontrolle im Test mit simuliertem Verlauf. | Codex Go/No-Go (Portfolio-Risiko) |
| RISK-04 | Getesteter Ausstiegspfad für Bestände oberhalb des Orderlimits und Stop-/Gap-Konzept. | Test: Bestand größer als `MAX_QTY_PER_ORDER` mit Ziel 0 führt zu einem definierten Abbau (nicht Abweisung); Stop-/Gap-Szenarien sind als Testfälle dokumentiert. | N-08, H-09 |
| RISK-05 | Offene Eigenorders werden in der Zielrechnung berücksichtigt (`Ziel - Ist - offen`). | Test mit offener Order zeigt netto korrekte Restmenge statt Abbruch; REQ-IBKR-23 wird auf umgesetzt gesetzt. | N-07 |

### DATA: Daten

| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft |
|---|---|---|---|
| DATA-01 | Archivierung der Eingaben (News, Social, Kurse, Indikatoren) mit Veröffentlichungs- und Erfassungszeit. | Für 100 % der gehandelten Entscheidungen existiert ein Eingabe-Snapshot mit Zeitstempeln im Paper-Log; Stichprobe von [20] Entscheidungen ist rekonstruierbar. | H-12, N-04 |
| DATA-02 | Point-in-time-Kurse und -Universum, inklusive ausgeschiedener Titel; imputierte Werte werden gekennzeichnet. | Bericht zeigt Anteil imputierter Werte je Lauf; Rückwärtsfüllung ist im Auswertungspfad ausgeschlossen oder markiert; Universum je Datum festgehalten. | N-04, Codex Dimension Look-ahead |
| DATA-03 | Mindestabdeckung und Frische je Datentyp. | Konfigurierte Schwellen je Quelle; ein Lauf mit unterschrittener Abdeckung erzeugt nachweislich keine neue Position (Test). | Codex Dimension Datenqualität |
| DATA-04 | Rolle der Textquellen: Entscheidung, welche Social-/News-Auswertung (z. B. Jev-Post-Screening) im Pfad aktiv ist, mit Wirkungsmessung. | Konfiguration ist im Paper-Workflow explizit; Beitrag der Quelle zur Prognosegüte wird gegen Lauf ohne Quelle gemessen und berichtet. | H-06, H-10, N-01 |

### OPS: Betrieb

| ID | Anforderung | Messbares Akzeptanzkriterium | Herkunft |
|---|---|---|---|
| OPS-01 | Ausführungs-Heartbeat und Soll-Ist-Bericht über Branches (REQ-IBKR-49..54). | Alarm bei fehlendem Lauf spätestens [30 Minuten] nach geplantem Abschluss; täglicher Bericht Soll gegen Ist; CI prüft das Alter des Heartbeats. | H-11, M2-Lücken |
| OPS-02 | Backup und Restore einschließlich Ledger und Contract-Cache. | Dokumentierter Restore-Test mit vollständigem IBKR-State; Backup-Allow-Liste enthält Ledger und `contracts.json`. | H-11 (REQ-IBKR-51) |
| OPS-03 | Paper-Bewährung: Ausführungsmechanik über mehrere Sitzungen. | [20] aufeinanderfolgende Sitzungen mit vollständigem Ledger-/Broker-Abgleich; 0 Doppelorders, 0 ungeklärte Intents, 100 % Order-/Fill-Zuordnung; Negativkontrollen für Reconnect, Teil-Fill, Kill, Crash. | N-06, Codex Go/No-Go (Ausführung) |
| OPS-04 | Go/No-Go-Gate mit Protokoll. | Vorab festgelegte Schwellen aus PRED/VAL/RISK/DATA/OPS werden in einem Protokoll je Prüfpunkt als erfüllt/nicht erfüllt festgehalten; Gate entscheidet Go/No-Go anhand der Schwellen; Ergebnis und Datum im Repo abgelegt; ohne Go keine Echtgeld-Freigabe. | Codex Go/No-Go (Aktueller Stand) |

## Phasenskizze

### Phase 1: Datenbasis und point-in-time

Ziel: Eingaben werden archiviert, Kurse und Universum sind zeitpunktbezogen, Datenqualität ist sichtbar.

**Anforderungen:** DATA-01, DATA-02, DATA-03, DATA-04

Exit-Kriterium: Snapshots für alle Paper-Entscheidungen eines Zeitraums von [4 Wochen] vorhanden; Qualitätsbericht je Lauf.

### Phase 2: Baselines und Validierungsrahmen

Ziel: Auswertungsrahmen mit Walk-Forward, Baselines, Kosten und Mehrfachtest-Kontrolle, auf dem Bestand erprobt.

**Anforderungen:** VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06

Exit-Kriterium: Bericht auf der heutigen Entscheidungsbasis läuft reproduzierbar, auch wenn er `insufficient` meldet.

### Phase 3: Prognosemodell(e)

Ziel: Zielgröße, Wahrscheinlichkeit/Verteilung, Kalibrierungsbericht und gemessene Sampling-Streuung. Rolle des LLM (Merkmalslieferant oder Entscheider) ist vorher entschieden.

**Anforderungen:** PRED-01, PRED-02, PRED-03, PRED-04

Exit-Kriterium: Kalibrierungsbericht gegen Baseline liegt vor, unabhängig vom Ausgang.

### Phase 4: Risiko und Sizing

Ziel: Sizing aus Volatilität/Konfidenz, Exposure-Limits, Abschaltung, Ausstiegspfad, Nettierung offener Orders.

**Anforderungen:** RISK-01, RISK-02, RISK-03, RISK-04, RISK-05

Exit-Kriterium: Alle Risikotests grün, inklusive Negativkontrollen.

### Phase 5: Betrieb und Paper-Bewährung

Ziel: Heartbeat, Soll-Ist, Backup/Restore und Paper-Sitzungen mit Abgleich.

**Anforderungen:** OPS-01, OPS-02, OPS-03

Exit-Kriterium: [20] Sitzungen ohne ungeklärte Abweichung; Restore-Test dokumentiert.

### Phase 6: Go/No-Go-Gate

Ziel: Gate-Protokoll gegen vorab festgelegte Schwellen; Ergebnis Go oder No-Go.

**Anforderungen:** OPS-04

Exit-Kriterium: Protokoll im Repo; No-Go beendet den Meilenstein regulär.

## Nicht-Ziele

- Keine Echtgeld-Freigabe ohne bestandenes Gate (OPS-04).
- Kein Renditeversprechen und keine Trefferquote als Ziel.
- Kein Ersatz von M2-Phase 6-8; offene M2-Punkte (REQ-IBKR-49..60) sind Abhängigkeit für OPS-01..03, nicht Teil davon, soweit sie dort schon geplant sind.
- Kein Hochfrequenzhandel, kein Intraday-Modell.
- Keine Änderung am Upstream-Kern, die nicht für die Anforderungen nötig ist.

## Offene Fragen an den Operator

1. Welches Universum und welcher Ticker-Pool gelten (heute AAPL, MSFT, NVDA; Gate-Vorschlag verlangt mindestens 30 vorab definierte Titel)?
2. Welche Haltedauer und welche Zielgröße (Richtung, Alpha, Nettorendite) soll prognostiziert werden?
3. Welche Rolle hat das LLM: Merkmalslieferant für ein eigenes Modell oder weiterhin Entscheider mit gemessener Kalibrierung?
4. Wie hoch ist das Budget für LLM-Kosten bei Mehrfachläufen (PRED-04) und Backtests, und ab wann ist ein Backtest vertretbar?
5. Sollen Daten gekauft werden (archivierte News, point-in-time-Kurse), oder nur prospektiv archiviert werden?
6. Welche Gate-Schwellen gelten (Fallzahl, OOS-Dauer, Drawdown, Kostenannahme in bp)?
7. Wie verhält sich der Meilenstein zu M2 (Phase 6-8 zuerst abschließen oder parallel)?
8. Soll das Post-Screening mit Jev im Paper-Lauf aktiviert werden, und wer labelt Referenztexte für die Kalibrierung?
