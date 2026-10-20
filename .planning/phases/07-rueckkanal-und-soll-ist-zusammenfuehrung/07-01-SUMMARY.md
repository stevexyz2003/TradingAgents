---
phase: 07-rueckkanal-und-soll-ist-zusammenfuehrung
plan: 01
subsystem: ibkr-publish
tags: [git, ibkr-log, publish]
requires: []
provides:
  - scripts/ibkr_publish.py (Snapshot, PublishResult, PublishError, resolve_remote_url, publish)
affects: [07-06]
key-files:
  created:
    - scripts/ibkr_publish.py
    - tests/test_ibkr_publish.py
decisions:
  - "Remote `fork` und Branch `ibkr-log` sind Modulkonstanten ohne Env-Override; Push nur als `HEAD:refs/heads/ibkr-log` ohne Force"
metrics:
  completed: 2026-10-20
  tasks: 1
  files: 2
---

# Phase 7 Plan 01: ibkr-log-Publisher Summary

Reines Modul `scripts/ibkr_publish.py`: Snapshot-Bytes in einen Ein-Branch-Klon, Commit nur bei Diff, Push ohne Force auf `fork/ibkr-log`.

## Ergebnis

- Task 1 (Commit 27294e1): Modul und 17 Tests gegen echtes Git mit lokalen Bare-Repos (`fork.git`, `origin.git`).
- Erstanlage (`ls-remote` Exit 2) und Fortschreibung (Fetch + `reset --hard`) laufen über denselben Pfad. Ein leerer Diff erzeugt keinen Commit. Ein früher gescheiterter Erst-Push wird nachgeholt.
- Non-Fast-Forward führt zu `PublishError("push-rejected")`, ohne etwas zu erzwingen. Ein Fremd-Autor wird als `foreign_author` gemeldet.
- Bytes bleiben unverändert, auch mit `core.autocrlf=true` in der globalen Konfiguration (Test vergleicht `git cat-file blob` mit den Quellbytes).
- Der Runner-Test belegt: kein argv enthält `origin`, `paper-log` oder ein Force-Flag. Der Push-Refspec beginnt nicht mit `+`. Jeder Aufruf hat `timeout` und `GIT_TERMINAL_PROMPT=0` sowie `GCM_INTERACTIVE=never`.

## Verifikation (tatsächlich ausgeführt)

- `pytest tests/test_ibkr_publish.py`: 17 passed.
- `pytest tests/test_ibkr_publish.py tests/test_ibkr_isolation.py tests/test_ibkr_paperlog.py`: 85 passed.
- `ruff check` und `ruff format` auf beiden Dateien: sauber.
- grep: `--force` 0 Treffer, `datetime.now|time.time(|date.today` 0 Treffer, `"-A"` 0 Treffer.

## Deviations from Plan

- Worktree-Basis wich ab (HEAD e8f5503 statt b346a33); gemäß Vorgabe per `git reset --hard b346a33` korrigiert, bevor gearbeitet wurde.
- Sonst keine: Plan wie geschrieben umgesetzt (Ruff-Autofix `timezone.utc` zu `UTC`).

## Known Stubs

Keine.

## Self-Check: PASSED

- scripts/ibkr_publish.py und tests/test_ibkr_publish.py vorhanden; Commit 27294e1 vorhanden.
