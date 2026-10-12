# Phase 3: Symbol-Auflösung, Handelbarkeit und Handelszeiten - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 03-symbol-aufl-sung-handelbarkeit-und-handelszeiten
**Areas discussed:** Mapping-Tabelle, conId-Persistenz & Drift, Handelbarkeit ohne Schicht 4, Kommando & Fehlerverhalten

---

## Mapping-Tabelle

| Frage | Optionen | Gewählt |
|---|---|---|
| Ort der Zuordnung | Code-Konstante · versionierte TOML im Repo · Datei unter LOCALAPPDATA | Code-Konstante ✓ |
| Erwartungswerte fest? | Nur Suchschlüssel (conId lernen) · Alles hart inkl. conId · Du entscheidest | Nur Suchschlüssel ✓ |
| Matching | Exakt, case-sensitiv · Trim + upper() | Exakt ✓ |
| Selbsttest | Unit-Test prüft Tabelle · Laufzeit · Beides | Unit-Test ✓ |
| Gemappte Nicht-STK-Ticker | Einträge mit echtem secType, gesperrt · separate Sperrliste | Einträge gesperrt ✓ |
| Identitätsfelder | Nur 4 aus REQ-30 · alle 6 · 4 + 2 als Warnung | Nur 4 ✓ |
| Abdeckung PAPER_RUN_TICKERS | Test gegen Default · nur Laufzeit-Abweisung | Test ✓ |
| Trennungsnachweis SC5 | Import-Test + Verhaltenstest · nur Verhaltenstest | Beides ✓ |
| Aliase | Nur real emittierte Roh-Strings · alle bekannten Aliase | Nur emittierte ✓ |
| Modulschnitt | Eigenes reines Modul · alles in ibkr_broker.py · Du entscheidest | Eigenes Modul ✓ |
| Neuer Ticker | Commit + resolve-Probelauf · nur Commit | Commit + Probelauf ✓ |

**Notes:** Der Nutzer wollte bei diesem Bereich zweimal weitere Fragen. Danach waren nur noch Implementierungsdetails offen.

---

## conId-Persistenz & Drift

| Frage | Optionen | Gewählt |
|---|---|---|
| Erstlauf | Automatisch lernen + loggen · Operator-Freigabe | Automatisch ✓ |
| Speicher | LOCALAPPDATA JSON · im Repo · paper-state/ | LOCALAPPDATA ✓ |
| Drift-Reichweite | Nur dieser Ticker · ganzer Lauf stoppt | Nur Ticker ✓ |
| Neufestlegung | `resolve --rebaseline` · Eintrag manuell löschen | Kommando ✓ |
| Gegenprobe ab Lauf 2 | conId + Symbol-Suche vergleichen · nur conId | Beide ✓ |
| Korrupte Datei | Ganzer Lauf stoppt · wie Erstlauf | Stopp ✓ |
| Fehlende Datei | Explizites `--init` nötig · Erstlauf ist Erstlauf | `--init` ✓ |
| Historie | Append-only JSONL · im selben JSON · nur Log | JSONL ✓ |
| Init-Anker | AAPL gegen PROBE_CON_ID prüfen · getrennt halten | Anker ✓ |

---

## Handelbarkeit ohne Schicht 4

| Frage | Optionen | Gewählt |
|---|---|---|
| Fehlendes `ineligibilityReasonList` | REQ-31 ändern + Ersatzsignale · defensiv per getattr · beides | REQ ändern ✓ |
| orderTypes | MKT und LMT · nur MKT · gar nicht prüfen | MKT + LMT ✓ |
| Halt-Erkennung | Research klärt, sonst Phase 4 · immer Snapshot in Phase 3 · nur 154 im Order-Pfad | Research klärt ✓ |
| Puffer zu Öffnung/Schluss | Puffer als Konstante · nackt liquidHours · Du entscheidest | Puffer ✓ |
| Cache Handelszeiten | Kein persistenter Cache · Datei-Cache mit Datum | Kein Cache ✓ |
| Kein Fenster für heute | Eigener Zustand session-unknown · ganzer Lauf stoppt | Eigener Zustand ✓ |
| Parser | Eigener Parser + Gegentest · ib_async liquidSessions() direkt | Eigener Parser ✓ |
| Puffergröße | 15/15 · 30/30 · Du entscheidest | 15/15 ✓ |
| 10089/10090 Log-Level | INFO mit State-Label · WARNING | INFO ✓ |

---

## Kommando & Fehlerverhalten

| Frage | Optionen | Gewählt |
|---|---|---|
| Lauffähiges Ende | Subkommando `resolve` · zwei Kommandos resolve + session | `resolve` ✓ |
| Exit bei Abweisung | Exit 2 (EXIT_PRECONDITION) · Exit 0 · neuer Code 9 | Exit 2 ✓ |
| Außerhalb der Sitzung | Exit 0, Zustand closed · Exit 2 | Exit 0 ✓ |
| Ausgabe | Konsole + Log, optional --out JSON · nur Konsole + Log | Mit --out ✓ |
| Ticker-Quelle | Argumente Pflicht · alle STK-Einträge · PAPER_RUN_TICKERS | Pflicht ✓ |
| Nachweis Mehrdeutigkeit SC3 | Fake-Test + Befund · zusätzlich Live-Sonde mit Allow-List-Bypass | Fake + Befund ✓ |

---

## Claude's Discretion

- Zustandsnamen und Dataclass-Form des Ergebnisses, JSON-Schema von contracts.json/-history.jsonl, Name/Schnitt der Broker-Lesemethoden (≤ 10 öffentliche Methoden), ob 154/HALTED in STATE_BY_CODE landen.

## Deferred Ideas

Keine.
