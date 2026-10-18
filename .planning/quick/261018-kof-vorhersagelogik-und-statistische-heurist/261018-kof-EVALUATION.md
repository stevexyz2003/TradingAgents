---
date: 2026-10-18
paper_log_sha: 5541cd938c10cc62a3bda919f38bbc0c3d1cba79 (fork/paper-log)
code_head_sha: 33767b3 (Fixes aus dem Codex-Review; Erstlauf auf e1a2bc0 identisch)
command: .venv/Scripts/python.exe scripts/pattern_eval.py --git-ref fork/paper-log --format md
prices: Yahoo (echte Kurse, je Ticker 1255 Bars bis 2026-10-16), Exit 0, kein Fallback
---

# Musterauswertung auf der Paper-Log-Historie

## Ergebnis in einem Satz

**Zu wenig Daten.** Kein Muster erreicht `MIN_N = 20` unabhaengige Faelle; es gibt keine einzige abgerechnete Richtungsentscheidung. Alle 24 Zellen (6 Muster, 2 Seiten, 2 Modi) stehen auf `insufficient`, es wird bewusst keine Trefferquote ausgewiesen.

## Datenlage

- 16 Eintraege (2026-10-09 bis 2026-10-16), Ticker AAPL 6, MSFT 5, NVDA 5.
- Abgerechnet: 1 (2026-10-09 AAPL, Hold, raw +2,0 %, Alpha +4,0 %, 5d). Pending: 15.
- Ratings: 13 Hold (1 abgerechnet, 12 pending), 3 Overweight (alle NVDA, alle pending: 10-13, 10-14, 10-15).
- REVIEW ausgeschlossen: 0. Unlesbar: 0. Haltedauern: nur `5d`.

## Musterzustaende je Eintrag

Berechnet aus Kursen bis einschliesslich Entscheidungsdatum (+1 bullisch, -1 baerisch, 0 inaktiv; RSI und Bollinger konträr gelesen, Annahme A2).

| Datum | Ticker | Rating | Status | rsi | macd | breakout_20 | sma200 | sma50_200 | bollinger |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-09 | AAPL | Hold | abgerechnet | 0 | 0 | 0 | +1 | +1 | 0 |
| 2026-10-12 | AAPL | Hold | pending | 0 | 0 | 0 | +1 | +1 | 0 |
| 2026-10-12 | MSFT | Hold | pending | 0 | 0 | +1 | +1 | +1 | -1 |
| 2026-10-12 | NVDA | Hold | pending | 0 | -1 | 0 | +1 | +1 | 0 |
| 2026-10-13 | AAPL | Hold | pending | 0 | 0 | +1 | +1 | +1 | 0 |
| 2026-10-13 | MSFT | Hold | pending | -1 | 0 | +1 | +1 | +1 | 0 |
| 2026-10-13 | NVDA | Overweight | pending | 0 | -1 | 0 | +1 | +1 | 0 |
| 2026-10-14 | AAPL | Hold | pending | 0 | +1 | +1 | +1 | +1 | 0 |
| 2026-10-14 | MSFT | Hold | pending | 0 | 0 | 0 | +1 | +1 | 0 |
| 2026-10-14 | NVDA | Overweight | pending | 0 | -1 | 0 | +1 | +1 | 0 |
| 2026-10-15 | AAPL | Hold | pending | 0 | +1 | 0 | +1 | +1 | 0 |
| 2026-10-15 | MSFT | Hold | pending | 0 | 0 | 0 | +1 | +1 | 0 |
| 2026-10-15 | NVDA | Overweight | pending | 0 | 0 | -1 | +1 | +1 | +1 |
| 2026-10-16 | AAPL | Hold | pending | 0 | +1 | +1 | +1 | +1 | 0 |
| 2026-10-16 | MSFT | Hold | pending | 0 | 0 | 0 | +1 | +1 | 0 |
| 2026-10-16 | NVDA | Hold | pending | 0 | 0 | -1 | +1 | +1 | +1 |

Auffaellig: Alle drei Ticker stehen im gesamten Zeitraum ueber der SMA200 und im Golden-Cross-Regime. Die beiden Trend-Muster sind damit in dieser Stichprobe konstant +1 und trennen nichts.

## Auswertung je Muster und Seite

Einzige nicht leere Zellen (Modus `pattern`, weil nur ein Hold abgerechnet ist):

| Muster | Seite | Modus | n_all | n_unabh. | Ties alpha/raw | Status |
|---|---|---|---|---|---|---|
| trend_sma200 | +1 | pattern | 1 | 1 | 0/0 | insufficient |
| sma50_200 | +1 | pattern | 1 | 1 | 0/0 | insufficient |

Der Lauf wurde nach den Codex-Fixes wiederholt (Metrik-Nenner je Metrik: den alpha/raw = 1/1, Status je Metrik `insufficient`, Sitzungsbasis statt Wochentage, keine Naeherungswarnung); Zustaende und Ergebnis sind unveraendert. Alle anderen Zellen haben n_all = 0. Im Modus `engine` (nur Richtungsratings) ist jede Zelle leer, weil keine Richtungsentscheidung abgerechnet ist. Trefferquoten, Wilson-Intervalle und beide Metriken (alpha und raw) sind im Code vorhanden und getestet, werden aber unterhalb von MIN_N nicht ausgegeben.

## Markierte Eintraege

- **2026-10-09 AAPL (Hold)**: alte Einstiegskonvention (`decision_close`). Wochentagsabstand Entscheidung bis Ausstieg = 5 Handelstage = Haltedauer; unter der neuen Regel (Fix #1518, Einstieg am ersten Schlusskurs nach dem Entscheidungsdatum) waere der Abstand 6. Der Eintrag wurde am 2026-10-17 um 06:59 UTC abgerechnet, der Fix kam erst um 14:56 UTC auf `fork/main` (RESEARCH Verdachtsstelle 3, Annahme A4). Der Eintrag bleibt in der Auswertung und ist markiert. Die Konvention ist aus Wochentagen abgeleitet; ein Feiertag kann sie verschieben.

## Warnungen

- Alpha ist die einfache Differenz zum Benchmark, ohne Beta-Bereinigung (NVDA mit hohem Beta traegt Marktbewegung im Alpha).
- Ticker-Pool klein und fest; Ergebnisse generalisieren nicht darueber hinaus (Auswahleffekte nicht auszuschliessen).
- Eine Haltedauer, eine erkannte Konvention; keine Mischwarnung noetig.

## Wie viele Daten fehlen

Das Mindest-N gilt je Zelle und in unabhaengigen Faellen (Abstand mindestens eine Haltedauer je Ticker, also 5 Handelstage).

- Bei 3 Tickern entstehen taeglich 3 Entscheidungen, aber nur etwa 1 unabhaengiger Fall je Ticker und Woche, also rund 3 pro Woche ueber alle Ticker.
- **Modus `pattern`** (alle Eintraege inkl. Hold): fuer ein Muster, das fast immer aktiv ist (die zwei Trend-Muster), etwa 7 Wochen taeglicher Lauf bis n_unabh. = 20. Fuer seltene Muster (aktiv in etwa 15-30 % der Tage) grob 25 bis 45 Wochen.
- **Modus `engine`** (nur Richtungsratings): bisher 3 von 16 Entscheidungen (rund 19 %) sind Richtungen. Damit kommen nur etwa 0,6 unabhaengige Richtungsfaelle pro Woche zusammen, also grob 35 Wochen fuer ein Dauer-Muster und deutlich laenger fuer seltene Muster. Eine tragfaehige Engine-Aussage ist mit dem taeglichen 3-Ticker-Lauf nicht in absehbarer Zeit zu erwarten; mehr Ticker oder ein separat entschiedener Backtest waeren der Hebel.
- Diese Zahlen sind Groessenordnungen aus 16 Eintraegen und der Annahme, dass sich der Anteil der Richtungsratings nicht aendert.

## Folgepunkte

- **Schritt 2 (deterministische Muster-Schicht / Veto) bleibt offen** und wird erst angegangen, wenn ein Muster in Schritt 1 mit n_unabh. >= 20 belegt ist (Orchestrator-Entscheidung 3). Kein Code dafuer in dieser Aufgabe.
- Offene Modellierungsfrage fuer den Operator: RSI und Bollinger sind konträr gelesen; die Momentum-Lesart wuerde das Vorzeichen drehen.
- Lauf wiederholen:
  `git fetch fork paper-log && .venv/Scripts/python.exe scripts/pattern_eval.py --git-ref fork/paper-log --format md`
  (lokal braucht yfinance die CA-Bundle-Variablen aus `.env`, siehe `scripts/PAPER_RUN.md`).
