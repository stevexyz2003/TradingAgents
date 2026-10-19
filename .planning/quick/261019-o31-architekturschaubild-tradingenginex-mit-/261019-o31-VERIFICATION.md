---
quick_id: 261019-o31
verified: 2026-10-19
status: human_needed
score: 7/7 must-haves per Code/Daten verifiziert; Browser-Interaktion und Optik nicht von mir geprüft
---

# Verifikation Quick 261019-o31: Architekturschaubild TradingEngineX

**Ziel:** Interaktives Architekturschaubild mit Anforderungsmatrix (M1, M2, Upstream, Strang) und ehrlicher Bestandsaufnahme der Vorhersagemethoden.
**Ergebnis:** Das Ziel ist nach Datenlage und Code erreicht. Offen bleibt nur ein kurzer manueller Blick im Browser, weil ich keinen Klick- oder Screenshot-Test ausgeführt habe.

## Ausgeführte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `node check_data.mjs` | OK. M1 13 (8/2/2/1), M2 70 (52 davon 2 Override / 9 davon 6 Phase 6 / 9 offen), Upstream 35 (34/0/1), Strang 8 (7/1 Phase 6), Summe 126. Knoten 62, Kanten 21/23/27, Methoden 8/11/8, Antwort 5, Befunde 7. |
| `node check_page.mjs` | PAGE OK |
| `innerHTML` in page-src.html | 0 Treffer. Datenstrings gehen nur über textContent bzw. setAttribute. |
| Git-Status außerhalb des Quick-Verzeichnisses | Nur `.planning/STATE.md` (M) und `.planning/debug/`. Das sind die bekannten fremden Änderungen aus der parallelen Sitzung. |

## Must-haves

| # | Must-have | Status | Evidenz |
|---|---|---|---|
| 1 | Kopf mit Stand und Statuszahlen je Quelle, passend zur Research-Zähltabelle | VERIFIZIERT | Die Zählungen aus check_data stimmen mit dem Plan überein. Die Commits b0989aa und e8f5503 existieren im Repo. Das aktuelle HEAD ist 2c9c383, die Seite ist ausdrücklich eine Momentaufnahme von b0989aa. |
| 2 | Diagramm mit allen Zonen, beschrifteten Flüssen, Herkunft über Umrandung | VERIFIZIERT | 62 Knoten, 71 Kanten, Knoten als `<g data-node tabindex role=button>`. Das Render-Skript erzeugt sie aus TEX_DATA. Die Umrandungsklassen (inactive, planned) hängen am Knoten. Die Optik habe ich nicht gesehen. |
| 3 | Klick/Enter/Leertaste filtert die Matrix, Knoten wird hervorgehoben, Reset | VERIFIZIERT (nur Code) | `selectNode`: bei einer Komponente `setComp(...)`. Bei mehreren Komponenten `state.set` plus temporäre Option "Knoten-Auswahl" und Chip "Komponente: K14 + K17". Der Filter prüft `state.set.indexOf(r.comp)`. Zweiter Klick auf denselben Knoten hebt die Auswahl auf. `clearNode` und `resetAll` (`#f-reset`) stellen alles zurück, `comp-chip-x` löst nur Komponentenfilter und Auswahl. Tastatur: `keydown` für Enter und Leertaste. aria-live-Text vorhanden. Es wurde nicht geklickt. |
| 4 | Matrix mit 126 Zeilen und den Filtern source/status/comp/origin/search | VERIFIZIERT | 126 Datensätze, Filter-IDs und Listener im Skript vorhanden. Die Zählung "x von N" kommt aus `D.requirements.length`. |
| 5 | Methodenteil: Kurzantwort, 27 Methoden (8/11/8), keine Empfehlungen | VERIFIZIERT | Daten per check_data bestätigt, `answer` mit 5 Sätzen. Die Spalten `gap` benennen nur Lücken. |
| 6 | Sieben Auffälligkeiten | VERIFIZIERT | Sieben Titel, passend zum Plan. |
| 7 | Hell/dunkel, schmal, ohne Interaktion sichtbar | TEILWEISE VERIFIZIERT | Statisch geprüft (Token-Blöcke, Marker). Der Orchestrator-Zusatz `svg.arch { width:100%; min-width:1100px }` liegt im Scroll-Container (`.diagram`). Das echte Rendering habe ich nicht gesehen. |

## Stichproben: Treue zur Research

Zeilen im Vergleich Daten gegen RESEARCH-requirements.md: M1-P1-2 (teilweise, pip-audit gedroppt), M1-P1-1 (verworfen-override), REQ-IBKR-05, -33, -49 (offen, Phase 7), -59 (offen, Phase 8), -69 (umgesetzt, nur SUMMARY-Beleg), U-01, U-06, U-35 (offen), S-08. Texte, Status und Phase stimmen mit den Research-Zeilen überein. Die neun M2-offen-Zeilen sind REQ-IBKR-49..54, 56, 58, 59. Das passt zur Phasenlage (Rückkanal/Betrieb, Phasen 7/8).

Methoden im Vergleich zu RESEARCH-architecture.md: Wahrscheinlichkeitsmodell (existiert nicht), Settlement raw/alpha, Technische Indikatoren, post_screen, Kosten-/Token-Budget, Globale News, Fundamentals. Alle stimmen mit den Research-Zeilen überein.

## Stichproben gegen den echten Code

| Behauptung | Befund im Repo |
|---|---|
| Keine scipy/sklearn/statsmodels | In pyproject.toml nur pandas und stockstats im Kernbereich, kein Python-Import dieser Pakete (rg über `*.py` ohne .venv). Bestätigt. |
| Temperature nicht gesetzt | `default_config.py`: `"temperature": None`, die Factory leitet sie nur bei gesetztem Wert weiter. Bestätigt. |
| yfinance ist Vendor-Standard | `data_vendors`: core_stock_apis, technical_indicators, news_data = yfinance. Bestätigt. |
| Alpha-Vantage-Sentiment ungenutzt | NEWS_SENTIMENT nur in `vendors/alpha_vantage/news.py`, im Standard nicht aktiv. Bestätigt. |
| Kein pip-audit/Dependabot | In `.github` nur ISSUE_TEMPLATE und workflows, kein Treffer für pip-audit/dependabot. Bestätigt (Auffälligkeit 1). |
| post_screen ohne TYPESAFE_API_KEY im Workflow | daily-paper-run.yml erwähnt den Schlüssel nur im Kommentar "never TYPESAFE_API_KEY". Bestätigt. |
| Dateien existieren | settlement.py, post_screen.py, budget.py, scripts/ibkr_*.py vorhanden. |

## Gefundene Mängel

Keine Blocker. Hinweis: Die Seite zeigt HEAD b0989aa, das Repo steht inzwischen auf 2c9c383 (nur Docs-Commits für Phase 7). Das ist als Momentaufnahme gekennzeichnet und akzeptabel.

## Menschliche Prüfung nötig

1. Seite im Browser öffnen, einen Knoten anklicken (zum Beispiel `smoke` mit K14 + K17), Matrix filtert und Chip erscheint. Danach "Filter zurücksetzen". Erwartet: alle 126 Zeilen wieder sichtbar.
2. Hell, dunkel und schmale Breite ansehen. Erwartet: lesbar, Diagramm scrollt im eigenen Container, kein Body-Querscrollen.
3. Das Diagramm hat laut SUMMARY viele Kanten. Prüfen, ob die Lesbarkeit für den Operator reicht.

Gründe: Klick, Optik und Responsiveness sind per Code und Grep nicht belegbar.
