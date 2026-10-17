---
phase: 05-leitplanken-scharf
plan: 09
subsystem: ibkr-docs-guards
tags: [ibkr, handbook, isolation, requirements, operator-checkpoint]
requires: [05-07, 05-08]
provides:
  - "scripts/IBKR_EXECUTION.md: ## RELEASE and KILL, ## execute, ## Ledger and reconciliation, ### States (phase 5), Exit 4/6/7 aktiv"
  - "tests/test_ibkr_isolation.py: sechs neue Wächter (Exit 4/6/7, execute-Nadeln, Zustandstabelle, Reinheit, Stream ohne Storno, git status)"
  - "REQUIREMENTS/ROADMAP: datierte Vermerke zu REQ-25/-33/-42/-63, Phase-5-SC5, Phase-6-SC2"
affects: [05-10]
key-files:
  modified:
    - scripts/IBKR_EXECUTION.md
    - tests/test_ibkr_isolation.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
key-decisions:
  - "Handbuch beschreibt den gebauten Stand: Reihenfolge der Kette mit Schluesselpruefung nach der Aktualitaet, Positions-/Ausgefuehrt-Quellen nach der Aufloesung, Torn-Tail-Siegel, Exit 6 nach Absturz ohne Broker-Spur"
requirements-completed: [REQ-IBKR-25, REQ-IBKR-33, REQ-IBKR-35, REQ-IBKR-42, REQ-IBKR-46, REQ-IBKR-63, REQ-IBKR-66]
completed: 2026-10-17
---

# Phase 5 Plan 09: Handbuch, Wächter, Anforderungsvermerke Summary

Das Handbuch deckt `execute`, `RELEASE`/`KILL`, Ledger/Reconciliation und die Phase-5-Zustandstabelle ab (Exit 4/6/7 aktiv), sechs neue Isolationswächter pinnen das, und REQUIREMENTS/ROADMAP tragen die datierten Vermerke.

## Ergebnis

- **Handbuch:** Exit-Zeilen 4/6/7 aktiv beschrieben plus Rangfolge `4 > 7 > 6 > 8 > 3 > 1 > 5 > 2 > 0`. Neue Abschnitte `## RELEASE and KILL` (JSON-Format, 90-Tage-Grenze, PowerShell-Einzeiler, Warnung `echo >`, Storno trifft alle offenen Orders inkl. manueller TWS-Orders, Read-Only-API-Schalter muss aus sein, bekannte Grenze aus 05-05), `## execute` (zwangsweise trocken, 12-stufige Kette, Größengrenze "SELL 5 wird `size_cap`", Sitzungsfenster, D-22-Quellentabelle), `## Ledger and reconciliation` (Ereignisse, Gründe-Tabelle, `weekend_gap` als Markierung, Torn Tail mit `seals_torn_line`, Exit-6-Auflösungsablauf D-19 mit `ibkr_order_probe.py --history`) und `### States (phase 5)` mit allen 22 Zuständen aus `EXIT_BY_STATE` (per Skript aus dem Modul erzeugt und gegen es geprüft). Der clientId-20002-Absatz (fecb76b) ist unverändert; keine Edits in den ersten 100 Zeilen.
- **Wächter** (mittig in der Datei, nach `test_handbook_documents_preview`): `test_handbook_exit_four_six_seven_are_active`, `test_handbook_documents_execute`, `test_handbook_state_table_matches_guards_module`, `test_new_modules_are_pure`, `test_stream_module_never_cancels`, `test_execute_run_leaves_git_status_unchanged`. Bestehende Tupel unverändert.
- **SC5-Nachweis:** `execute AAPL` ohne `RELEASE` endet mit Exit 4; `git status --porcelain` vorher = nachher; Trocken-Ledger und `ledger.jsonl.lock` entstehen unter `tmp_path`; keiner der fünf State-Pfade liegt unter dem Repo-Baum.
- **Anforderungen/Roadmap:** REQ-33 "Freigabe-Datei"; vier `*Geändert 2026-10-17 (Phase 5 ...)*`-Vermerke (REQ-25, -33, -42, -63); ROADMAP Phase-5-SC5 und Phase-6-SC2 (vier Abweichungen von REQ-45, D-23 als Eingangsaufgabe von Phase 6).

## Commits

- f0e8cfd docs(05-09): handbook for execute, RELEASE/KILL, ledger and phase-5 states
- fbfa04d test(05-09): isolation guards for execute, guards and ledger modules
- 0ce7de1 docs(05-09): dated notes in requirements and roadmap for phase 5

## Verifikation (tatsächliche Ausgabe)

- `pytest tests/test_ibkr_isolation.py`: 32 passed.
- Gesamtsuite: `1 failed, 2425 passed, 4 skipped, 1 deselected` - der eine Fehlschlag ist der bekannte `test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`.
- `ruff check .`: All checks passed; `ruff format tests/test_ibkr_isolation.py`: unverändert.
- Greps: `reserved for later phases` = 0, `ib_async` im Handbuch = 0, `Freigabe-Variable` = 0, `Freigabe-Datei` = 1, `(Phase 5`-Vermerke = 4.

## Einzeiler-Prüfung (T-05-47) - NUR TEILWEISE

PowerShell ließ sich in dieser Sandbox nicht starten (der Aufruf von `powershell.exe` wurde vom Worktree-Schutz verweigert). Die Einzeiler wurden daher **nicht** in PowerShell ausgeführt. Geprüft wurde nur die Leseseite mit den Byte-Mustern, die die Einzeiler laut .NET-Dokumentation erzeugen sollen (Skript im Scratchpad, `read_release`/`read_kill` aus `scripts/ibkr_guards.py`):

```
RELEASE  ReleaseState(state='release-ok', ... valid_until=2026-11-16, account='DUQ634065')   # UTF-8 ohne BOM (WriteAllText-Muster)
RELEASE2 ReleaseState(state='release-invalid', detail='not UTF-8 JSON ...')                 # UTF-16 mit BOM (Windows PowerShell 5.1 '>'-Muster)
KILL     KillState(state='kill-active')                                                      # leere Datei im State-Ordner
KILL absent  KillState(state='kill-absent')                                                  # Ordner ohne KILL
```

Offen für den Operator (Checkpoint 05-10): die drei Einzeiler im Handbuch einmal auf dem Rechner ausführen und `RELEASE` per `ibkr_executor.py execute` gegen `release-ok` prüfen. Der Release-Einzeiler enthält zusätzlich ein `Get-Date`-Ausdruck für das Datum; auch er ist ungeprüft.

## Deviations from Plan

**1. [Hinweis] Worktree-Basis** auf d8d9538 zurückgesetzt (Startprüfung; vorher e8f5503). Im Worktree liegt kein Operator-WIP in Handbuch/Test; daher kein Hunk-Filter nötig, die Dateien wurden normal gestaged. Der clientId-20002-Absatz stammt aus dem Basis-Commit.

**2. [Einschränkung] PowerShell-Einzeiler nicht ausgeführt** (siehe oben) - Handbuchtext enthält sie trotzdem, weil der Plan es verlangt; die Prüfung ist an den Operator-Checkpoint übergeben.

**3. [Hinweis] Zeilenenden.** `REQUIREMENTS.md`/`ROADMAP.md` haben CRLF; die Vermerke wurden mit CRLF eingefügt.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche.

## Self-Check: PASSED

- Commits f0e8cfd, fbfa04d, 0ce7de1 im Log; geänderte Dateien vorhanden; STATE.md unberührt.
