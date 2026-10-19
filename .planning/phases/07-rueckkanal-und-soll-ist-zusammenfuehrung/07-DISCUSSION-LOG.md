# Phase 7: Rückkanal und Soll-Ist-Zusammenführung - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-19
**Phase:** 07-rueckkanal-und-soll-ist-zusammenfuehrung
**Areas discussed:** Veröffentlichungsbranch, Portfolio-Rückkanal, Berichtsform, Slippage-Referenz

---

## Veröffentlichungsbranch

| Frage | Optionen | Gewählt |
|---|---|---|
| Branchname | ibkr-log · execution-log · Claude entscheidet | ibkr-log |
| Inhalt | Ledger + Portfolio (+ Contracts) · nur abgeleitete Tagesdateien · zusätzlich Laufprotokoll | Ledger + Portfolio |
| Zeitpunkt des Pushs | eigener `publish`-Befehl · am Ende jedes `execute` · beides | eigener `publish`-Befehl |
| Arbeitsbaum | eigener Klon im State-Ordner · Worktree des Repos · Claude entscheidet | eigener Klon im State-Ordner |

---

## Portfolio-Rückkanal

| Frage | Optionen | Gewählt |
|---|---|---|
| Höchstalter in CI | bis zum letzten Handelstag · feste Grenze (36 h) · kein Limit, nur anzeigen | bis zum letzten Handelstag |
| Datei da, aber veraltet/kaputt/ohne `as_of` | fail-open mit Vermerk · Lauf abbrechen | fail-open mit Vermerk |
| Verbraucher | nur CI · CI und lokal | nur CI |

---

## Berichtsform

| Frage | Optionen | Gewählt |
|---|---|---|
| Ausgabe | Markdown stdout + `--out` · Markdown + CSV · HTML | Markdown stdout + `--out` |
| Zeitraum | alles mit `--since/--until` · letzte 20 Handelstage | alles, filterbar |
| Zeilen | jede Entscheidung · nur Tage mit Order-Versuch | jede Entscheidung |
| Ort | nur lokal · lokal und CI-Job | nur lokal |

---

## Slippage-Referenz

| Frage | Optionen | Gewählt |
|---|---|---|
| Referenzpreis | Schluss am trade_date · Eröffnung am Ausführungstag · beides | Schluss am trade_date |
| Fill-Quote | gefüllt/beauftragt je Order · Anteil voll gefüllter Orders | gefüllt/beauftragt je Order |
| Kurs fehlt | leer mit Grund · Bericht bricht ab | leer mit Grund |

---

## Claude's Discretion

Backup-Umfang (REQ-51), `publish`-Fehlerverhalten und Erstanlage des Branches, CI-Lesemechanik für `ibkr-log`, Name/Ort des Berichtsskripts, Rekonstruktion von Ziel-/Ist-Position je Zeile.

## Deferred Ideas

Eröffnungskurs als zweite Referenz; CSV/HTML und CI-Job für den Bericht; Laufprotokoll → Heartbeat Phase 8; automatisches `publish` → Zeitplan Phase 8. Drei auto-gefundene Todos gehören zu Phase 6 und werden dort abgeschlossen.
