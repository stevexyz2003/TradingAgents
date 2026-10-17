---
title: Signed fills in the ledger (WR-07 from the phase-5 review)
created: 2026-10-17
resolves_phase: 6
area: tooling
source: .planning/phases/05-leitplanken-scharf/05-REVIEW.md (WR-07)
files:
  - scripts/ibkr_ledger.py (Ledger.filled_quantity)
  - scripts/ibkr_guards.py (position_conflict)
  - scripts/ibkr_executor.py (_reconcile, FILLED/PARTIAL appends)
---

## Problem

`Ledger.filled_quantity(con_id)` addiert `filled_qty` aller `filled`/`partial`-Ereignisse
einer `conId`, ohne die Seite (`side`) zu beachten. Verkäufe werden also mitgezählt statt
abgezogen, und es wird nie verrechnet.

Nach einem gefüllten Verkauf oder einem manuellen Verkauf in TWS gilt
`ledger_filled_qty > broker_held`. `guards.position_conflict` (D-18, enge Regel) meldet
dann in jedem künftigen Lauf `source-conflict` für diesen Ticker. Ohne `--resolve` (erst
Phase 6, D-19) lässt sich der Ticker nicht mehr entsperren: aus der unscharfen Regel wird
eine dauerhafte Sperre.

In Phase 5 tritt das nicht auf, weil `execute` zwangsweise trocken läuft und das echte
Ledger leer bleibt. Mit dem Placer von Phase 6 kommen echte Fills und Verkäufe.

## Lösung (aus dem Review)

- `filled`/`partial` schreiben die Seite (`side`) mit, übernommen aus dem offenen `intent`.
- `filled_quantity` summiert vorzeichenbehaftet: BUY +, SELL −.
- `_check` (Schema) verlangt `side` in `filled`/`partial` für neue Zeilen; alte Zeilen ohne
  `side` brauchen eine klare Regel (z. B. Seite aus dem zugehörigen `intent` ableiten).
- Test: Kauf 2 gefüllt, Verkauf 2 gefüllt, Broker hält 0 → kein `source-conflict`.
- Negativ-Kontrolle: ohne Vorzeichen meldet derselbe Fall `source-conflict`.

Eingangsaufgabe von Phase 6, vor der ersten echten Order (zusammen mit der Schärfung von
D-18 für Verkäufe und Fremdbestände).

## Mitgenommen aus WR-05 (2026-10-17)

Das Sitzungsfenster wird seit `39c4eac` direkt vor dem `intent` mit `ctx.clock()` neu
geprüft. Die **Frische** (`stale-decision`) wird dagegen weiter mit dem Startzeitpunkt des Laufs
bewertet. Mit dem Placer in Phase 6 ebenfalls direkt vor dem `intent` neu prüfen.
