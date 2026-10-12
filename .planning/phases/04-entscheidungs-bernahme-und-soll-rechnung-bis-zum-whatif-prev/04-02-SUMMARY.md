---
phase: 04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev
plan: 02
subsystem: ibkr-adapter
tags: [write-barrier, whatif, ib_async, safety]
requires: []
provides:
  - "Schreibsperre mit whatIf-Durchlass für Nachricht Id 3 (nur STK)"
  - "FakeOrder und placeOrder(whatIf)-Aufzeichnung in FakeIB.calls"
affects: [04-03, 04-07]
tech-stack:
  added: []
  patterns: ["drei Wächter (Aufruf, Feldebene, String-Ebene), fail-closed bei unbekanntem Layout"]
key-files:
  created: []
  modified:
    - scripts/ibkr_broker.py
    - tests/ibkr_fakes.py
    - tests/test_ibkr_broker.py
key-decisions:
  - "Layout-Indizes aus ib_async==2.1.0 Client.placeOrder abgezählt; jeder Block, der die whatIf-Position verschieben würde (Delta-Neutral, Scale, Hedge, DN-Contract, Algo), muss im Leerzustand sein, sonst abgewiesen"
  - "Feld- und String-Ebene teilen eine Prüffunktion (_whatif_layout); der String wird auf die Feldform zurückgefaltet (Contract 12 Felder -> 1)"
requirements-completed: [REQ-IBKR-38, REQ-IBKR-25]
duration: 25min
completed: 2026-10-12
---

# Phase 4 Plan 02: whatIf-Durchlass der Schreibsperre Summary

Nachricht Id 3 passiert die Sperre nur noch als whatIf-Vorschau eines STK-Contracts, an allen drei Stellen, mit Leitungsnachweis über die echte `ib_async.client.Client`-Klasse.

## Umgesetzt

- `_WRITE_CALLS` ohne `placeOrder`; `guarded_place` lässt nur `order.whatIf is True` und `secType == "STK"` durch.
- `_whatif_in_fields` (Feldebene) und `_whatif_in_message` (String-Ebene) mit gemeinsamem `_whatif_layout`; Ids 4, 19, 21, 58 sowie cancel/globalCancel/exercise unverändert gesperrt.
- Fakes: `FakeOrder`, Recorder schreibt `placeOrder(whatIf)` getrennt von `placeOrder`.
- Tests: 6+ `whatif_barrier`/`place_order_refused`-Tests, darunter echte Client-Klasse mit Stub-Verbindung (whatIf=True: genau eine Nachricht, whatIf-Feld "1" an Index 84; whatIf=False: nichts gesendet).

## Deviations from Plan

**1. [Ablauf] Kein getrennter RED-Commit.** Implementierung und Tests entstanden in einem Zug, beide Tasks sind in einem Commit (`4e32c5c`, `feat(04-02)`) zusammengefasst; die Tests wurden gegen die fertige Sperre grün gefahren. Die Real-Client-Tests würden bei einer Layoutverschiebung rot.

**2. [Rule 3] Event-Loop im Wire-Test.** `Client.sendMsg` ruft `getLoop()`, das einen Socketpair öffnet und den Netzblock der Suite auslöst. Der Test patcht `ib_async.client.getLoop` auf die Session-Loop.

**3. [Rule 1] `guarded_place` toleriert Clients ohne `placeOrder`** (SimpleNamespace in einem bestehenden Test): fehlt die Methode, wird sie durch eine reine Ablehnung ersetzt.

## Known Limitation

Layout gilt für Server-Version >= 177 und Nicht-BAG-Contracts (BAG ist ohnehin abgewiesen). Bei Version < 177 verschöbe sich das Layout um ein Feld; der Wächter würde dann eher abweisen als durchlassen.

## Verifikation

- `tests/test_ibkr_broker.py`, `_executor`, `_resolve`, `_isolation`: grün; `ruff check scripts tests`: ohne Befund.
- Gesamtsuite: 1805 grün, 1 Fehler `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` (umgebungsbedingt, nicht durch diesen Plan; nicht angefasst).
- `grep -cE "orderId=|\.orderId =" scripts/ibkr_broker.py` == 0.

## Commits

- 4e32c5c: feat(04-02): let message id 3 pass the write barrier only as a STK whatIf preview

## Self-Check: PASSED
