# Phase 4: Entscheidungsübernahme und Soll-Rechnung bis zum `whatIf`-Preview - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 4-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
**Areas discussed:** Zugriff auf paper-log, Aktualität in Sitzungen, Blöcke und offene Orders, whatIf trotz Schreibsperre

---

## Zugriff auf paper-log

| Frage | Optionen | Gewählt |
|-------|----------|---------|
| Zugriffsweg | git fetch + git show / eigener Klon oder Worktree / GitHub-API (raw) | git fetch + git show ✓ |
| Fetch-Fehler | Stoppen, eigener Zustand / lokalen Ref nutzen + Warnung | Stoppen ✓ |
| Remote/Branch | Setting mit Default / Code-Konstante | Setting (`fork`/`paper-log`) ✓ |
| Provenienz | SHA in Log und Protokoll / nein | Ja ✓ |

**Notes:** Heute liegt `paper-log` nur als `fork/paper-log` vor, letzter Lauf 2026-10-09.

---

## Aktualität in Sitzungen

| Frage | Optionen | Gewählt |
|-------|----------|---------|
| Quelle der Sitzungszählung | Börsenkalender + Abgleich / eigenes Sitzungsjournal / Wochentage fail-closed | Börsenkalender (`exchange_calendars` XNYS) + Abgleich mit liquidHours ✓ |
| weekend_gap | Jede Kalenderlücke / nur Fr→Mo / getrennte Marken | Jede Kalenderlücke ✓ |
| Welche Entscheidung | Neueste, kein Override / neueste + `--trade-date` | Neueste, kein Override ✓ |
| Außerhalb der Sitzung | Gegen nächste Sitzung rechnen / nur in der Sitzung | Gegen nächste Sitzung, whatIf läuft ✓ |

**Notes:** `liquidHours` reicht laut Konto-Befund nur ab heute etwa 5 Tage nach vorn. Eine reine Wochentagszählung würde SC4 (Feiertagsmontag) verletzen.

---

## Blöcke und offene Orders

| Frage | Optionen | Gewählt |
|-------|----------|---------|
| Ort der Blockgröße | In der Mapping-Tabelle / eigene Konstante / Setting/.env | `block_qty` in `CONTRACT_TABLE` ✓ |
| Startgröße | 1 / 5 / 10 Stück | 1 Stück ✓ |
| Ist-Position | positions() per conId / per Symbol | per conId ✓ |
| Offene Orders | alle, fremde stoppen / alle, verrechnen / nur eigene clientId | Alle am Konto, fremde stoppen ✓ |

---

## whatIf trotz Schreibsperre

| Frage | Optionen | Gewählt |
|-------|----------|---------|
| Durchlass | Nachricht prüfen / Methoden-Flag / zweite Verbindung | Nachricht prüfen (whatIf-Feld im ausgehenden Inhalt) ✓ |
| Gateway-Read-Only blockt whatIf? | Messen, dann entscheiden / Gateway-RO bleibt Pflicht | Messen, dann entscheiden ✓ |
| Budget | gegen AvailableFunds / feste EUR-Grenze / nur protokollieren | gegen AvailableFunds ✓ |
| Exit-Codes | alles Abgelehnte = 5 / 154 als Exit 2 | alles Abgelehnte = 5 ✓ |

---

## Scope-Hinweise des Orchestrators

- REQ-IBKR-69 und -70 stehen in der Traceability unter Phase 4, im Phasenkopf aber nicht. Sie wurden in den Scope aufgenommen, weil `whatIf` ohne explizites `tif` wortlos leer zurückkommt.
- Korrektur einer früheren Aussage: Phase 4 schließt den Heartbeat aus. `resolve_all` wird erst mit dem Heartbeat in einer späteren Phase automatisch laufen.

## Claude's Discretion

Subkommando-Name (Vorschlag `preview`), Format und Ort des Trockenlauf-Protokolls, Zustandsnamen, Schnitt der neuen Adapter-Methoden, Einbindung von `resolve_all`, Form des Vertragstests zu `summary.json`.

## Deferred Ideas

Feste Größen-Obergrenze, Kill-Switch, Ledger (Phase 5); Verrechnung eigener offener Orders (Phase 6); Limit-Orders mit Marktdaten, Marktdaten-Abo (außerhalb M2); 4-Block-Leiter (Erweiterungspfad).
