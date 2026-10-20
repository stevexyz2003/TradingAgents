# Meilenstein-Kontext: M3 Vorhersage-Engine (Europa)

**Stand:** 2026-10-20 · vorbereitet, **noch nicht aktiv**. M2 (IBKR Paper Execution) läuft weiter, bis Phase 6 abgeschlossen ist.
**Wird gelesen von:** `/gsd:new-milestone` beim Umschalten. Diese Datei ersetzt das Fragegespräch zu den Zielen. Ihre Entscheidungen werden dort nicht neu aufgerollt.

## Quellen

- `.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-CODEX-REVIEW.md`: Codex-Gegenprüfung, Verdikt No-Go für Echtgeld, die fünf wichtigsten Lücken.
- `.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-MILESTONE-DRAFT.md`: Ziele, 23 Anforderungskandidaten (PRED/VAL/RISK/DATA/OPS), Phasenskizze, Nicht-Ziele.
- `.planning/quick/261019-oxc-codex-gegenpruefung-methoden-und-luecken/261019-oxc-DECISIONS.md`: Operator-Entscheidungen 1–8 (gesetzt).
- `.planning/research/m3-vorhersage-engine/`: Recherche zu Stack, Funktionen, Architektur und Fallstricken für diesen Meilenstein.

## Ziel in einem Satz

TradingEngineX bekommt für europäische Aktien eine messbare, kalibrierte Prognose. Sie wird vor jeder Freigabe zeitlich getrennt gegen Baselines nach Kosten validiert, steuert Positionsgröße und Risiko und muss vor Echtgeld ein vorab festgelegtes Go/No-Go-Gate bestehen. No-Go ist ein gültiges Ergebnis.

## Gesetzte Entscheidungen (Operator, 2026-10-20)

1. **Universum:** zunächst nur Europa. US folgt später, abhängig von den Handelszeiten.
2. **Zielgröße:** Wahrscheinlichkeit, dass ein Titel seinen Benchmark nach Kosten schlägt. Horizonte 5 und 20 Handelstage.
3. **LLM-Rolle:** hybrid. Ein eigenes statistisches Modell liefert die Wahrscheinlichkeit, das LLM liefert Merkmale (z. B. News-Sentiment als Zahl) und darf begründen oder ein Veto einlegen. Beide Beiträge werden getrennt gemessen.
4. **Budget:** bis 150 €/Monat Betrieb inklusive Datenkauf, dazu einmalig etwa 300 € für Backtests.
5. **Daten:** Kurse und Fundamentaldaten point-in-time kaufen (Europa). News und Meldungen ab sofort selbst archivieren.
6. **Gate:**
   - mindestens 300 unabhängige, abgerechnete Fälle und mindestens 6 Monate Out-of-Sample bzw. Paper;
   - Alpha nach Kosten über den Baselines, 90-%-Konfidenzintervall ohne Null;
   - maximaler Drawdown ≤ 15 %, Kostenannahme 20 bp pro Seite;
   - die Kalibrierung wird berichtet.
7. **Verhältnis zu M2:** M2-Phase 6 wird abgeschlossen. M2-Phasen 7–8 werden pausiert und als Abhängigkeit in die Betriebsphase von M3 übernommen.
   > Hinweis 2026-10-20: Eine parallele Session hat Phase 7 bereits ausgeführt (Commits `docs(phase-07)`). Beim Umschalten ist festzustellen, welcher Stand von Phase 7 übernommen wird.
8. **Jev / Text-Labels:** Das Jev-Post-Screening läuft im Schattenmodus. Der Operator labelt monatlich etwa 50 zufällige Meldungen über eine kleine Oberfläche.

## Präzisierungen nach der Recherche (Operator, 2026-10-20)

Grundlage: `.planning/research/m3-vorhersage-engine/SUMMARY.md`, Konflikte K1–K7, Fragen O1–O8. Diese Antworten präzisieren bzw. ersetzen die Entscheidungen oben, wo sie sich widersprechen.

| # | Thema | Entscheidung |
|---|---|---|
| O1 | Gate-Struktur (präzisiert E6) | **Zweistufig.** Hauptbeleg für das Statistikmodell ist ein vorab festgelegter historischer Walk-forward mit unberührtem Holdout, der nur einmal ausgewertet wird. 6 Monate Paper bestätigen: kein signifikanter Bruch, Kalibrierung stabil, Ausführung sauber. Der LLM-Beitrag wird gepaart prospektiv getestet; nicht entscheidbar heißt „unentschieden“. „Unabhängiger Fall“ = Titel × nicht überlappendes Fenster über alle Prognosen des Universums, effektiv nach Designeffekt. Berichtet wird roh, nicht überlappend und effektiv. |
| O2 | Kosten (präzisiert E6) | **Kostenmodell je Titel, Seite und Land:** Steuer (UK, IE, FR, IT, ES …), Mindestgebühr, halber Spread, FX. 20 bp gelten als Untergrenze, der Bericht weist zusätzlich doppelte Kosten aus. Volles Universum. |
| O3 | Universum | **Eigenes Regeluniversum je Stichtag:** Top 200–300 nach Größe und 60-Tage-Euro-Umsatz, quartalsweise, inklusive delisteter Titel, aus EODHD. STOXX Europe 600 nur als Benchmark-Serie. **Zusätzlich** eine einmalige Preisanfrage bei STOXX/Qontigo für die historische Zusammensetzung; Kauf nur unter etwa 200 € (aus dem Backtest-Topf). |
| O4 | Betriebsort | **Privates Begleit-Repo** mit GitHub Actions für Datenabruf, Archiv, Prognose und Shortlist-LLM, abends. Orders werden lokal am Morgen ausgeführt. In der öffentlichen Fork liegen nur Code, gekürzte Test-Fixtures und nicht lizenzpflichtige Ergebnisse. |
| O5 | Währung | **Alpha und Labels in EUR**, Universum EUR/GBP/CHF. Konvertierung über explizite FX-Orders mit Kosten im Modell. `CURRENCY_MISMATCH` wird ersetzt durch „Währung auf Whitelist und Guthaben reicht“. |
| O6 | LLM-Modell | **Gepinnter Anthropic-Snapshot der Haiku-Klasse**, Cutoff in jedem Datensatz. **Ära-Konzept:** Ein Modell- oder Prompt-Wechsel startet eine neue Ära mit eigener Uhr; Merkmale bleiben eingefroren und werden nie neu extrahiert. LLM-Merkmale zählen nur für Meldungen nach dem Cutoff. |
| O7 | LLM-Budget (präzisiert E3/E4) | **Extraktor je Meldung** für das ganze Universum (Batch-API, Deduplizierung, Caching). **Vollgraph nur für höchstens 5 Shortlist-Kandidaten am Tag** als Veto, das nur verkleinern darf. Mehrfachläufe zur Kalibrierung nur auf 10 % Stichprobe. Erwartet etwa 80–110 €/Monat inklusive Daten. Budget reserviert vor dem Aufruf (Codex-Befund N-05). |
| O8 | Drawdown (präzisiert E6) | **Gegatet wird der Drawdown relativ zum Benchmark, höchstens 15 %.** Der absolute Drawdown wird berichtet. Betriebs-Stopp bei 10 % absolut oder 2 % Tagesverlust. |

**Sofort zeitkritisch (unabhängig vom Umschalten):** Das News- und Meldungsarchiv soll jetzt starten (Vorlauf), weil jeder Tag ohne Archiv als prospektive LLM-Evidenz fehlt und GDELT nur 3 Monate zurückreicht.

**Phasenfolge (aus der Recherche):** Vorlauf (Archiv) → P0 Präregistrierung → P1 Datenbasis → P2 Validierung, Kosten und Baselines (Freeze) → P3 Statistikmodell mit historischem Bericht (früher No-Go-Punkt) → P4 LLM-Merkmale, Veto und Labeling → P5 Entscheidung und Sizing im Schattenbetrieb → P6 EU-Ausführer (parallel ab dem `targets.json`-Schema) → P7 Betrieb und Paper-Bewährung → P8 Go/No-Go-Gate.

## Was kein Plan garantieren kann

Profitabilität ist nicht planbar und wird weder zugesagt noch als Ziel gesetzt. Planbar sind die Nachweisführung (was wird gemessen, gegen was, mit welcher Schwelle) und der Abbruch bei Nichterfüllung.

## Zielfunktionen (Kandidaten, Feinschnitt in `/gsd:new-milestone`)

- **Datenbasis:**
  - point-in-time-Kurse, Fundamentaldaten und Kapitalmaßnahmen für ein festes europäisches Universum;
  - Archiv der News und Meldungen ab sofort, mit Qualitätsstatus je Tag.
- **Validierungsrahmen:**
  - Walk-forward bzw. zeitlich getrennte Auswertung, Baselines (Benchmark halten, Zufall, Momentum);
  - Kosten und Slippage, Kontrolle für Mehrfachtests, Kalibrierungsbericht.
- **Prognosemodell:**
  - statistisches Modell auf Kurs-, Fundamental- und Textmerkmalen, liefert eine Wahrscheinlichkeit je Titel und Horizont;
  - das LLM als Merkmalslieferant und Veto, Beitrag getrennt gemessen.
- **Risiko und Positionsgröße:**
  - Größe nach Volatilität und Konfidenz, Drawdown-Stopp, Abbaupfad über das Orderlimit;
  - Kosten im Entscheidungspfad.
- **Europa-Betrieb:**
  - Börsenkalender und Handelszeiten (Xetra, Euronext …), Benchmark (STOXX Europe 600 bzw. Länderindex), Währung (EUR/GBP/CHF);
  - IBKR-Berechtigungen und Symbolauflösung (ISIN, Primärbörse), Zeitpunkt des täglichen Laufs vor Börsenöffnung.
- **Betrieb und Gate:**
  - Paper-Bewährung mit Heartbeat, Backup und Soll-Ist (übernimmt die M2-Phasen 7–8);
  - Go/No-Go-Gate mit Protokoll.

## Nicht-Ziele

- Keine Echtgeld-Freigabe ohne bestandenes Gate.
- Kein Renditeversprechen, keine Trefferquote als Ziel.
- Kein Hochfrequenz- oder Intraday-Handel.
- Kein US-Handel in diesem Meilenstein (Entscheidung 1).
- Keine Änderung am Upstream-Kern, die für die Anforderungen nicht nötig ist.

## Beim Umschalten zu erledigen (Reihenfolge)

1. Die parallele Session stoppen oder auf Phase 6 begrenzen. Den Stand von Phase 7 festhalten.
2. M2-Phase 6 abschließen (erste echte Order, 06-09/06-10).
3. M2 archivieren, mit Phase 7–8 als pausiert bzw. an M3 übergeben. Vorher `PROJECT.md` und `MILESTONES.md` anlegen; beide fehlen bisher, `/gsd:new-milestone` setzt sie voraus.
4. `/gsd:new-milestone` mit dieser Datei ausführen. Die Phasennummerierung läuft weiter oder beginnt neu, das wird dort entschieden.
