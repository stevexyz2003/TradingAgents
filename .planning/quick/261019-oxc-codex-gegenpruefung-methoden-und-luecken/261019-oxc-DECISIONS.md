# Operator-Entscheidungen zum Meilenstein-Entwurf „Vorhersage-Engine“

**Entschieden:** 2026-10-20 (Operator). Grundlage: `261019-oxc-MILESTONE-DRAFT.md`, offene Fragen 1–8.
**Verwendung:** Eingabe für `/gsd:new-milestone`. Diese Entscheidungen gelten als gesetzt und werden dort nicht neu aufgerollt.

| # | Frage | Entscheidung |
|---|---|---|
| 1 | Universum | **Zunächst nur Europa.** US folgt später, abhängig von den Handelszeiten (die US-Sitzung beginnt erst 15:30 MEZ). Weicht vom Vorschlag „30–50 US-Large-Caps“ ab. |
| 2 | Zielgröße und Horizont | **Alpha nach Kosten**, ausgewertet für 5 und 20 Handelstage, als Wahrscheinlichkeit, den Benchmark nach Kosten zu schlagen. |
| 3 | Rolle des LLM | **Hybrid.** Ein eigenes statistisches Modell aus Kurs-, Fundamental- und News-Merkmalen liefert die Wahrscheinlichkeit. Das LLM liefert Merkmale (z. B. News-Sentiment als Zahl) und darf begründen oder ein Veto einlegen. Beide Beiträge werden getrennt gemessen. |
| 4 | Budget | **Bis 150 €/Monat** für den laufenden Betrieb, dazu ein einmaliger Backtest-Topf von etwa 300 €. |
| 5 | Daten | **Kurse und Fundamentaldaten point-in-time kaufen** (Anbieter mit Europa-Abdeckung, Größenordnung 20–80 €/Monat; auf das Budget aus Frage 4 anzurechnen). **News und Meldungen ab sofort selbst archivieren.** |
| 6 | Go/No-Go-Gate | **Mittel:** mindestens 300 unabhängige, abgerechnete Fälle und mindestens 6 Monate Out-of-Sample bzw. Paper. Das Alpha nach Kosten muss über den Baselines liegen, und das 90-%-Konfidenzintervall darf die Null nicht enthalten. Maximaler Drawdown höchstens 15 %, Kostenannahme 20 bp pro Seite, die Kalibrierung wird berichtet. |
| 7 | Verhältnis zu M2 | **Phase 6 (erste echte Order) wird abgeschlossen.** Die M2-Phasen 7–8 werden pausiert und als Abhängigkeit in die Betriebsphase des neuen Meilensteins übernommen. |
| 8 | Jev / Text-Labels | **Jev-Post-Screening läuft im Schattenmodus** mit: Es protokolliert, beeinflusst aber nicht die Entscheidung. Der Operator labelt **monatlich etwa 50 zufällige Meldungen** für die Kalibrierung, über eine kleine Oberfläche (rund 20 Minuten). |

## Folgen von Entscheidung 1 (Europa zuerst)

Der Entwurf ist US-zentriert. In `/gsd:new-milestone` sind deshalb noch zu klären bzw. anzupassen:
- **Börsenplätze:** z. B. Xetra, Euronext, LSE, SIX. Dazu Handelszeiten (09:00–17:30 MEZ) und der Kalender je Börse; heute ist nur XNYS hinterlegt.
- **Benchmark:** STOXX Europe 600 oder je Land DAX/CAC 40 usw. statt SPY. Das betrifft `resolve_benchmark`.
- **Währung:** EUR, GBP oder CHF. Alpha und Kosten in Heimatwährung, Umgang mit FX.
- **IBKR:** Marktdaten- und Handelsberechtigungen für Europa auf dem Paper-Konto, die Symbolauflösung (Primärbörse, ISIN) und die Kostenstruktur bei europäischen Börsen.
- **Ablauf:** Zeitpunkt des täglichen Laufs, der Lauf muss vor Börsenöffnung in Europa fertig sein; heute läuft er auf US-Zeit ausgerichtet.
- **News-Quellen:** mit europäischer Abdeckung und Sprache (DE/FR/EN), wichtig für die Archivierung aus Entscheidung 5.
