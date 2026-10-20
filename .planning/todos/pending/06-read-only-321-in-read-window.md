---
title: Map a 321 without request id in a read window to READ_ONLY_API
created: 2026-10-20
area: tooling
source: .planning/phases/06-die-erste-echte-order/06-VERIFICATION.md (D-15 override)
files:
  - scripts/ibkr_broker.py (WINDOW_BENIGN_CODES, Z. ~162-172)
  - scripts/ibkr_executor.py (exit mapping)
  - tests/test_ibkr_call_order.py (test_live_read_only_ends_at_the_preview, Z. ~357-365)
---

## Problem

Mit eingeschaltetem „Read-Only API“ bekommt `reqCompletedOrders` über das Gateway
eine 321 mit `reqId -1` und keine Antwort (gemessen 2026-10-19,
`ibkr-konto-befund.md`, Messung 1). `WINDOW_BENIGN_CODES` führt 321 als harmlos
(„owned by the preview“). Das Lesefenster läuft deshalb nach 10 s in den Timeout,
und `execute --live` sowie `--history` enden mit `REQUEST_TIMEOUT` (Exit 3). Für den
Operator heißt Exit 3 „Gateway nicht verfügbar“; die richtige Diagnose wäre
„Read-Only an“ (`READ_ONLY_API`, Exit 5).

Der Test `test_live_read_only_ends_at_the_preview` modelliert ein Gateway, das die 321
erst am whatIf meldet. Sein Kommentar behauptet, das sei der am Messtag gemessene
Zustand, was nicht stimmt.

## Lösung

- Eine 321 im Lesefenster beendet das Fenster sofort als `READ_ONLY_API`, statt es
  in den Timeout laufen zu lassen. Der Exit soll 5 sein, wie bei `preview-read-only`.
- Ein Test mit der gemessenen Reihenfolge: 321 bei `reqCompletedOrders`, kein
  `intent`, Exit 5, Zustand `READ_ONLY_API`.
- Den Kommentar von `test_live_read_only_ends_at_the_preview` korrigieren. Der Test
  bleibt für den Pfad „321 am whatIf“.
- Handbuch („Gateway Read-Only switch“, „First live order“) danach anpassen.

Kein Sicherheitsproblem: Der Lauf ist heute schon fail-closed.
