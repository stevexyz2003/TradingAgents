---
phase: 05-leitplanken-scharf
plan: 05
subsystem: ibkr-executor
tags: [ibkr, execute, lock, kill-switch, release, fail-closed, tdd]
requires: [05-01, 05-02, 05-03, 05-04]
provides:
  - "run_execute: Lauf-Lock (ExitStack, wait=False) als aeusserste Klammer, Exit 7"
  - "_check_switches, _report_blocked, _halt_on_switches, _kill_path (einzige cancel_all-Stelle), _run_locked"
  - "KILL_RECHECK_SECONDS = 10.0, KILL_RECHECK_INTERVAL_S = 0.5, _sleep"
affects: [05-06, 05-07]
key-files:
  modified: [scripts/ibkr_executor.py, tests/test_ibkr_execute.py]
key-decisions:
  - "run_execute teilt sich: Einstellungen und Lock in run_execute, der Rest in _run_locked"
  - "Quelle (paper_log_factory) wird erst nach dem Schalter-Preflight gebaut: Exit 4 hat keinen Paper-Log-Kontakt"
  - "switch_check wird nur vor dem intent geschrieben, nicht vor dem whatIf (Plan: nur Pruefung vor whatIf)"
requirements-completed: [REQ-IBKR-33, REQ-IBKR-34, REQ-IBKR-35, REQ-IBKR-36, REQ-IBKR-44, REQ-IBKR-64, REQ-IBKR-66]
completed: 2026-10-17
---

# Phase 5 Plan 05: Lock, Freigabe/Kill, Kill-Storno Summary

`execute` ist durch `locked(ledger.jsonl, wait=False)` geklammert, liest Freigabe und Kill-Datei als allererstes (und neu vor jedem whatIf und jedem `intent`), endet bei jeder Sperre fail-closed mit Exit 4 und storniert nur bei positiv vorhandener `KILL`-Datei, an genau einer Stelle (`_kill_path`).

## Ergebnis

- **Lock (SC7, T-05-27/28):** nur der Sperrversuch steht im `try`. `OSError` dort ist Exit 7 `LOCK_ERROR` ohne Traceback, vergebener Lock ist Exit 7 `LOCK_HELD`, beide ohne Ledger-Eintrag, ohne Paper-Log, ohne Gateway. Ein `OSError` im Lauf geht durch `_guarded` (Exit 3/1, `run_end` `outcome:"error"`). Sidecar `ledger.jsonl.lock` im State-Ordner, auch im Trockenmodus.
- **Preflight:** `_check_switches(ctx)` liest die injizierte Uhr in UTC bei jedem Aufruf neu. `run_start` enthaelt `release`, `kill`, `valid_until`. Gesperrt: Logzeile des Zustands, Konsole `execute: <state> (...)`, `run_end` `exit:4` mit Zustand. Matrix (fehlend, Verzeichnis, UTF-16, abgelaufen, 91 Tage, falsches Konto, `os.stat(KILL)` wirft) je Exit 4, kein Gateway.
- **Defektes Ledger:** `LEDGER_CORRUPT` wird immer geloggt; bei geschlossenem Schalter gewinnt Exit 4 (bei `KILL` mit Storno, ohne ins Ledger zu schreiben), sonst Exit 6.
- **Pruefung vor jeder Order:** `_execute_ticker` prueft vor `preview_order` und vor `INTENT`; vor dem `intent` steht ein `switch_check` mit beiden Zustaenden. Bei Sperre: `ctx.halted`, Ticker `skipped` mit Grund `kill_switch`, weitere Ticker ohne Broker-Aufruf, am Ende `_kill_path` bei Kill.
- **Kill-Pfad:** `cancel_all(kill_evidence=...)` genau einmal je Lauf, danach `open_orders()` mit Wiederholung bis 0 oder Fristende; `kill_cancel` mit `outcome`, `sent`, `remaining`, `rechecks`. Nicht erreichbares/ungesundes Gateway: `outcome:"gateway_unavailable"`, Exit 4 (nie 3). Falsches Konto: Exit 8, nie `reqGlobalCancel`.
- **G3-Nachweis:** `test_g3_kill_between_two_orders` plus Negativ-Kontrolle mit Cache (zweite Order bekaeme dann ein `intent`) und AST-Test "ein `cancel_all`-Aufruf, in `_kill_path`".

## Commits

- 32cefe1 test(05-05): Lock/Freigabe/Kill Fail-closed-Matrix (RED, 18 Tests rot)
- 6c11147 feat(05-05): Lock, Preflight, Exit 4, Kill-Pfad
- edbfacd test(05-05): Kill-Pfad, G3, einzige cancel_all-Stelle

## Verifikation (tatsaechliche Ausgabe)

- `tests/test_ibkr_execute.py`: 76 passed.
- IBKR-Volllauf (broker, contracts, executor, isolation, resolve, preview, decision, paperlog, guards, ledger, execute): `881 passed`.
- `ruff check scripts tests`: All checks passed. `ruff format` nur auf `tests/test_ibkr_execute.py`; `scripts/ibkr_executor.py` nicht umformatiert (vorhandene Format-Abweichung).
- Greps: `cancel_all(` = 1; `KILL_RECHECK_SECONDS = 10.0` = 1; `enter_context(locked(` = 1; `wait=False` = 1; `_check_switches(` = 4 (Definition, Preflight, vor whatIf, vor intent).

## Deviations from Plan

**1. [Hinweis] Worktree-Basis korrigiert.** Der Worktree stand auf dem Upstream-Stand v0.7.0 (e8f5503); laut Startpruefung auf f802721 zurueckgesetzt (`git reset --hard`, auf `worktree-agent-*`-Branch, nichts verloren).

**2. [Hinweis] TDD-Reihenfolge Task 2.** `_kill_path` wird schon von den Task-1-Pfaden (Preflight-Kill, defektes Ledger) gebraucht und kam deshalb im Task-1-feat-Commit. Die Task-2-Tests waren beim ersten Lauf gruen; die Negativ-Kontrollen (Cache, umgangene Schalter) belegen ihre Empfindlichkeit.

**3. [Anpassung bestehender Tests, Rule 1]** Durch das neue Verhalten geaenderte Erwartungen aus 05-04: `switch_check` im Ereignisablauf (`framed by run_start/run_end`, `write_ahead`), die zwei Ledger-Defekt-Tests laufen jetzt mit gueltiger Freigabe (sonst Exit 4 statt 6), die `"cancel_all(" not in source`-Pruefung ist durch den AST-Test ersetzt.

## Bekannte Grenzen

- Ist `ctx.halted` durch einen Freigabe-Fehler gesetzt und erscheint `KILL` erst danach, wird in diesem Lauf nicht mehr storniert (kein weiterer Schalter-Check nach dem Halt); der naechste Lauf holt es nach.
- Nur ein Teil von Task 2 (Konsole/Log-Texte) ist Texttest; die Wirkung des echten Gateway-`reqGlobalCancel` bleibt dem Operator-Checkpoint vorbehalten (SC3 gegen Fake hier belegt).

## Known Stubs

Keine.

## Threat Flags

Keine neue Flaeche ueber T-05-27..32 hinaus.

## Self-Check: PASSED

- scripts/ibkr_executor.py, tests/test_ibkr_execute.py vorhanden; Commits 32cefe1, 6c11147, edbfacd im Log.
