# Phase 6: Die erste echte Order - Discussion Log

> **Nur Prüfprotokoll.** Nicht als Eingabe für Planungs-, Recherche- oder Ausführungsagenten verwenden.
> Die Entscheidungen stehen in CONTEXT.md, dieses Protokoll bewahrt die erwogenen Alternativen.

**Date:** 2026-10-18
**Phase:** 06-die-erste-echte-order
**Areas discussed:** Todos, Scharfschalten, Jev-Ratings, Nach der Order, Nachweise 321 & Reject

---

## Todos einfalten

| Option | Description | Selected |
|--------|-------------|----------|
| WR-07 Fills mit Vorzeichen | Phase-5-Review: Käufe zählen +, Verkäufe −; dazu die Frische-Prüfung vor dem `intent` | ✓ |
| Jev-Fallback-Ratings (D-23) | Eingangsaufgabe vor der ersten Order | ✓ |

## Scharfschalten

| Frage | Optionen | Gewählt |
|--------|-------------|----------|
| Live-Modus | `--live` pro Lauf / Konstante umstellen | `--live` pro Lauf |
| Erste Order | Operator live dabei / unbeaufsichtigt | Operator live dabei |
| Ticker | Was der Paper-Log hergibt / fest AAPL / Operator wählt am Tag | Was der Paper-Log hergibt |
| Read-Only danach | bleibt aus / nach jedem Test wieder an | bleibt aus |

## Jev-Ratings

| Frage | Optionen | Gewählt |
|--------|-------------|----------|
| Weg | (b) Abgleich mit summary.json / (a) Log-Tag / (c) akzeptieren | (b) |
| summary.json fehlt | Fail-closed, Ticker skipped / als Engine-Rating werten | Fail-closed |
| Ledger `rating_source` | befüllen / leer lassen | befüllen |

## Nach der Order

| Frage | Optionen | Gewählt |
|--------|-------------|----------|
| Fill-Warten | 60 s, dann Ende mit Alarm-Exit / 60 s, dann stornieren / nicht warten | 60 s, dann Alarm-Exit |
| Abweichung (REQ-65) | Lauf stoppt / nur der Ticker | Lauf stoppt |
| Persistenz (REQ-48) | im execute-Lauf / Subkommando `sync` / beides | im execute-Lauf |

## Nachweise 321 & Reject

| Frage | Optionen | Gewählt |
|--------|-------------|----------|
| 321-Beleg (SC1) | frisch am Tag messen / Phase-4-Messung reicht | frisch messen |
| Reject (SC7) | Fixture + Stub-Broker / echter Reject am Konto | Fixture + Stub (Abweichung vom Roadmap-Wortlaut, in D-12 festgehalten) |
| execId-Fixture (SC5) | Rohform aus dem Befund / Claude entscheidet | Rohform aus dem Befund |

## Claude's Discretion

- Namen und Exit-Codes der neuen Zustände
- Bau der `placeOrder`-Öffnung in der Socket-Sperre (nach dem Muster des Einmal-Permits von `cancel_all`)

## Deferred Ideas

- `cancelOrder` als zweite Schreiböffnung
- Subkommando `sync`
- Kill-Grenze aus Phase 5 (KILL erst nach einem Halt wegen ungültiger Freigabe)
