# Phase 5: Leitplanken scharf - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-16
**Phase:** 05-leitplanken-scharf
**Areas discussed:** Freigabe & Kill-Datei, reqGlobalCancel vs. Sperre, Trockenlauf & Ledger, Größe/Fenster/Widerspruch

---

## Freigabe & Kill-Datei

**Form der Freigabe**

| Option | Description | Selected |
|--------|-------------|----------|
| Datei mit Ablaufdatum | RELEASE im State-Ordner mit „gültig bis"; fehlt/unlesbar/abgelaufen → Exit 4; Wochen im Voraus setzbar, Phase-8-tauglich | ✓ |
| Env-Variable bis Widerruf | `IBKR_EXECUTION_RELEASED=true` mit strikter Bool-Koerzion; wörtlich REQ-33, läuft nie ab | |
| Beides | Env-Generalschalter und Datei mit Ablauf; zwei Stellen zu setzen | |

**Kontobindung**

| Option | Description | Selected |
|--------|-------------|----------|
| Ja, Konto-ID in der Freigabe | Abweichendes Konto → Exit 4; zweite Quelle neben dem Paper-Guard | ✓ |
| Nein | Paper-Guard (Exit 8) prüft das Konto schon beim Verbinden | |

**Ort der Kill-Datei**

| Option | Description | Selected |
|--------|-------------|----------|
| State-Ordner | `%LOCALAPPDATA%\TradingEngineX\ibkr\KILL`, neben RELEASE und Ledger | ✓ |
| Desktop | Im Ernstfall am schnellsten erreichbar | |
| Konfigurierbar | Pfad per Setting, Default State-Ordner | |

**User's choice:** jeweils die Empfehlung.
**Notes:** Abwägung offengelegt: Eine tägliche Freigabe sabotiert den unbeaufsichtigten Betrieb aus Phase 8, eine ewige wird vergessen.

---

## reqGlobalCancel vs. Sperre

**Wann darf Nachricht 58 durch die Socket-Sperre?**

| Option | Description | Selected |
|--------|-------------|----------|
| Nur im Kill-Pfad | Ein einzelner protokollierter Durchlass nach festgestelltem Kill-Switch | ✓ |
| Immer frei | Stornieren ist die sichere Richtung; ein Bug könnte aber fremde TWS-Orders wegräumen | |
| Erst ab Phase 6 | SC3 nur gegen den Stub; verschiebt einen Roadmap-Nachweis | |

**Echter SC3-Nachweis**

| Option | Description | Selected |
|--------|-------------|----------|
| Operator legt die Order in TWS an | Kleine DAY-Limit-Order weit vom Markt, KILL anlegen, Lauf starten; Phase 5 sendet selbst nie | ✓ |
| Nur gegen den Stub | SC3 wird umformuliert | |

**User's choice:** jeweils die Empfehlung.

---

## Trockenlauf & Ledger

**Kommando**

| Option | Description | Selected |
|--------|-------------|----------|
| Neues `execute`, in Phase 5 nur trocken | Volle Kette mit Trocken-Abschluss; Phase 6 nimmt nur den Zwang heraus; `preview` bleibt | ✓ |
| `preview` erweitern | Weniger Kommandos jetzt, Umbau in Phase 6 | |

**Ledger für Trockenläufe**

| Option | Description | Selected |
|--------|-------------|----------|
| Eigene Datei | `ledger-dryrun.jsonl`, gleicher Code-Pfad; echter Ledger bleibt bis Phase 6 leer | ✓ |
| Ein Ledger, Einträge markiert | `mode: dry_run`; Markierungsfehler macht Trocken-intent zum echten | |
| Trockenläufe schreiben nichts | Write-Ahead nur per Test bewiesen | |

**User's choice:** jeweils die Empfehlung.
**Notes:** Begründung offengelegt: Ein Trocken-`intent` im echten Ledger wäre für die Startup-Reconciliation unauflösbar und würde jeden Lauf mit Exit 6 beenden.

---

## Größe, Fenster, Widerspruch

**MAX_QTY_PER_ORDER**

| Option | Description | Selected |
|--------|-------------|----------|
| Code-Konstante = 2 | Größte Order, die D-10 heute erzeugt; jeder Fehler darüber wird abgelehnt | ✓ |
| Code-Konstante mit Luft (z. B. 10) | Spätere `block_qty`-Erhöhung ohne zweiten Commit | |
| Setting in .env | Ohne Commit änderbar, nicht versioniert | |

**Sitzungsfenster**

| Option | Description | Selected |
|--------|-------------|----------|
| Phase-3-Puffer übernehmen | +15 / −15 min über `SESSION_BUFFER_MINUTES` | ✓ |
| Eigenes, breiteres Fenster | z. B. +30 / −30 min, eigene Konstante | |

**Quellen-Widerspruch**

| Option | Description | Selected |
|--------|-------------|----------|
| Konto global, Rest pro Ticker | Konto stoppt den Lauf; Position/Ausführung/Handelbarkeit nur den Ticker | ✓ |
| Immer ganzer Lauf | Am vorsichtigsten, blockiert im Phase-8-Betrieb jeden Lauf | |
| Immer nur der Ticker | Zu schwach für einen Konto-Widerspruch | |

**User's choice:** jeweils die Empfehlung.

---

## Claude's Discretion

- Dateiformat von RELEASE, exaktes Ledger-Schema, Zustandsnamen und Logzeilen, Wiederverwendung von `run_preview`-Bausteinen in `execute`.

## Deferred Ideas

- Kurs-Stream (`scripts/ibkr_market_data.py`, laufende Arbeit des Operators): außerhalb des Order-Pfads; offene Frage, ob 2103 einen Stream beenden soll.
