---
phase: 06-die-erste-echte-order
plan: 08
subsystem: ibkr-executor-tests
tags: [call-order, REQ-45, SC2, SC7, D-12, D-15, REQ-66]
requires: [06-06]
provides:
  - "tests/test_ibkr_call_order.py: Reihenfolgetest des --live-Pfads mit den vier Abweichungen"
  - "Negativ-Kontrollen im scharfen Pfad: whatIf-Reject, Read-Only, Groesse, Sitzung, KILL"
key-files:
  created:
    - tests/test_ibkr_call_order.py
key-decisions:
  - "Beobachtung ueber einen Ereignisstrom: FakeIB.calls als Tee, Ledger.append, check_switches, plan_order, check_size, _session_info (dict-Unterklasse), Paper-Log fetch; alle Hooks rufen zuerst das Original"
  - "Lock wird beim ersten Preflight-Schalterlesen geprueft (nicht erst beim ersten Broker-Aufruf), damit 'Lock vor Preflight' belegt ist"
requirements-completed: [REQ-IBKR-45, REQ-IBKR-10]
completed: 2026-10-19
---

# Phase 6 Plan 08: Reihenfolge der Pruefkette im scharfen Pfad Summary

Ein Ereignisstrom-Test fuer `execute --live` gegen den Stub-Broker pinnt die Kette Lock, Schalter-Preflight, Reconciliation, Paper-Log, Aufloesung, Position, Menge, Groesse, Sitzung, Kill-Lesung, whatIf, Schalterpruefung, `intent` (auf Platte), `placeOrder`, `placed`, `filled`, mit den vier dokumentierten Abweichungen von REQ-45.

## Ergebnis

- Task 1: `test_live_call_order_follows_req45_with_four_deviations` (literale Teilfolge plus paarweise Assertions fuer Abweichungen 1-3, `disk:intent` vor `placeOrder`), `test_live_call_order_pins_quantity_size_session_kill_before_whatif` (jede Beobachtung kommt vor, Ordnung quantity < size < session < erste kill nach session < whatIf < intent < placeOrder), `test_live_call_order_key_check_after_freshness` (verbrauchter Key plus veraltete Entscheidung endet als `stale-decision`).
- Task 2: `test_live_whatif_reject_blocks_the_order` (D-12), `test_live_read_only_ends_at_the_preview` (D-15, 321 am whatIf), Groesse (`size-cap`), Sitzung (`outside-session`), `KILL` zwischen zwei Tickern (zweiter Ticker `kill-active`, genau ein `placeOrder`).
- Hook-Stellen wie geplant, keine Abweichung der Signaturen: `decision.plan_order`, `guards.check_size`, `guards.check_switches`, `executor._session_info` (Lesen von `closed`).
- Beobachteter Lauf: Reconciliation liest `open_orders`, `completed_orders`, `executions`; Aufloesung ruft `contract_details` vor `qualify`; danach `positions`. Die Erwartungsliste haelt genau diese Folge fest.
- Kein Produktionscode geaendert, kein `xfail`: die tatsaechliche Folge entspricht REQ-45 plus den vier Abweichungen, keine Luecke.

## Verifikation

- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_call_order.py -q` -> 8 passed
- `.venv/Scripts/python.exe -m pytest tests/test_ibkr_*.py tests/test_daily_paper_run.py -q` -> 1254 passed
- `.venv/Scripts/python.exe -m ruff check scripts tests` -> All checks passed (Datei zusaetzlich mit `ruff format` formatiert)

## Deviations from Plan

**1. Commit-Aufteilung:** Beide Tasks liegen in derselben neuen Datei und wurden in einem Commit abgeschlossen (bc00075).

**2. Eigene Fixtures statt Import:** Die autouse-Fixtures (`_pin_modules`, `loop` usw.) sind in der neuen Datei nachgebaut (modulweiter `loop`), statt sie aus `test_ibkr_execute` zu importieren, um keine `noqa`-Unterdrueckungen zu brauchen. Hilfen (`_live_run`, `_fake_for` usw.) werden importiert.

**3. Read-Only-Fake:** 321 wird als `whatif="hang"` plus `emit_during` am whatIf erzeugt (Timeout mit 321 ergibt `READ_ONLY_API`).

## Commits

- bc00075 test(06-08): pin the REQ-45 call order and negative controls in the live path

## Known Stubs

Keine.

## Threat Flags

Keine neue Flaeche; T-06-39 bis T-06-42 mitigiert (Beobachtungs-Wrapper aendern keine Rueckgabewerte, es wurde nie ein echtes Gateway kontaktiert).

## Self-Check: PASSED

tests/test_ibkr_call_order.py vorhanden, Commit bc00075 vorhanden.
