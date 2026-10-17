---
quick_task: 261017-r7x
title: Rebase strand onto upstream v0.7.0
date: 2026-10-17
status: ready-for-promotion
provides: [branch rebase/upstream-v0.7.0 @4b245f7 (+ this summary), backup/pre-rebase-v0.7.0 @fecb76b]
---

# Rebase des Strangs auf Upstream v0.7.0

Upstream hat am 2026-10-16 **v0.7.0** veröffentlicht (`e8f5503`, = `origin/main`).
Nach der Rebase-Kadenz des Strangs ist der ganze Strang darauf neu aufgesetzt, in
einem eigenen Worktree. `main` und `fork/main` sind **nicht** angefasst; die
Promotion braucht die Freigabe des Operators (siehe unten).

## Eckdaten

- **Basis neu:** v0.7.0 `e8f5503` (11 Upstream-Commits über v0.6.0, 37 Dateien).
- **Basis alt:** v0.6.0; Strang `v0.6.0..fecb76b` = 236 Commits, davon 14 Merges.
- **Backup:** `backup/pre-rebase-v0.7.0` = `fecb76b` (der `main`-Stand beim Start).
- **Ergebnis:** Branch `rebase/upstream-v0.7.0`, 222 wiederholte Commits + 1 neuer
  (`4b245f7`, CHANGELOG-Kopfzeile) + dieses Protokoll.
- **Worktree:** `C:/Users/admin/PycharmProjects/TradingEngineX-rebase-v070` mit
  eigenem venv (Python 3.13, `pip install -e ".[dev,ibkr]"`, tradingagents 0.7.0,
  ib_async 2.1.0, ruff 0.17.1). Das venv des Haupt-Baums wurde nicht verändert.

## Methode

`git rebase --onto v0.7.0 v0.6.0 rebase/upstream-v0.7.0`, linear. Die 14 Merges
des Strangs (Executor-Worktrees aus Phase 2–4, ein Codex-Fix-Merge) sind dabei
aufgelöst. Vorher geprüft: alle 14 hatten **0 Auflösungs-Hunks**
(`git show --cc`), sie waren also konfliktfrei entstanden, und die lineare
Wiederholung verliert keine Auflösung.

## Konflikte

Konfliktfläche vorab: 9 Dateien, die Upstream und Strang beide geändert haben
(`.env.example`, `CHANGELOG.md`, `README.md`, `cli/run.py`, `pyproject.toml`,
`tests/test_memory_log.py`, `tradingagents/default_config.py`,
`tradingagents/llm_clients/factory.py`, `tradingagents/llm_clients/model_catalog.py`);
13 Strang-Commits berühren sie.

Tatsächlich angehalten hat der Rebase **einmal**:

- `8f42d9a` (CHANGELOG-Abschnitt des Strangs) gegen den neuen `[0.7.0]`-Abschnitt:
  Strang-Abschnitt `[Unreleased]` oben, `[0.7.0]` direkt darunter. Die Kopfzeile
  „rebased onto v0.6.0" blieb während des Replays bewusst stehen, damit spätere
  Commits im selben Abschnitt glatt anwenden; korrigiert in `4b245f7`.

Alle übrigen Commits liefen ohne Konflikt durch.

## Gates (auf dem finalen Stand)

**Differentielles pytest: bestanden.** Gleiche Fehlschlagmenge auf purem v0.7.0
(`git archive v0.7.0`, außerhalb beider Repos, `PYTHONPATH=.`) und auf dem Strang:

| | passed | failed | skipped |
|---|---|---|---|
| v0.7.0 pur | 1353 | 5 | 4 |
| Strang auf v0.7.0 | 2202 | 5 | 4 |

Die fünf Fehlschläge sind auf beiden Seiten identisch und kommen nicht vom Strang:
`test_chatgpt_auth.py` (2, neu in 0.7.0), `test_cli_updates.py` (2, neu in 0.7.0)
und der bekannte Windows-Fall
`test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home`.
Die vier neuen Upstream-Fehlschläge sind auf diesem Windows-Rechner schon auf
purem v0.7.0 rot.

**ruff check: bestanden** (`All checks passed!`, ruff 0.17.1).

**Nichts vom Strang verloren:** `git diff backup/pre-rebase-v0.7.0 rebase/upstream-v0.7.0`
berührt genau 37 Dateien, und **alle** gehören zu den Upstream-Änderungen
v0.6.0→v0.7.0 — außerhalb davon ist kein einziger Unterschied. In allen acht
Konfliktdateien ist der Strang-Anteil (Diff gegen die jeweilige Basis) zeilengleich
groß geblieben: `cli/run.py` 76, `factory.py` 53, `README.md` 26, `.env.example` 18,
`pyproject.toml` 17, `default_config.py` 15, `model_catalog.py` 9,
`test_memory_log.py` 4.

## Semantische Prüfungen (was Git nicht sieht)

- **Neuer `chatgpt`-Provider gegen unsere Fail-fast-Keys:** Upstream 0.7.0
  authentifiziert `chatgpt` über die Plan-Anmeldung, ohne API-Key
  (`api_key_env.py`: `"chatgpt": None`). Unsere Prüfung
  `factory._required_env_vars` deckt nur die nativen Familien ab
  (Anthropic, Google, Azure) und verlangt für `chatgpt` nichts;
  `daily_paper_run.missing_credentials("chatgpt", {})` ist leer. Kein Übergriff.
- **Bewertung ab dem ersten Schlusskurs nach dem Datum (`f5e3eae`):** Geändert sind
  nur `memory/settlement.py` und `memory/reflection.py`; `memory/log.py` und damit
  das Eintragsformat von `decision-log.md` sind unverändert. Die IBKR-Kette liest
  `paper-log` weiter wie bisher.

## Für uns relevante Upstream-Änderungen

- Ausstehende Bewertungen im Memory-Log werden ab dem ersten Schlusskurs **nach** dem
  Entscheidungsdatum gerechnet; schon abgerechnete Einträge bleiben.
- Läufe ohne Terminal (der tägliche CI-Paper-Run) kontaktieren den
  Ankündigungs-Server nicht.
- Neue Pflicht-Abhängigkeiten: `cryptography>=42`, `packaging>=24`.

## Promotion — braucht die Freigabe des Operators, nicht ausgeführt

`main` ist seit dem Start um 16 Commits weitergelaufen (Phase 5 in einer anderen
Session, `fecb76b..51292b8` zum Zeitpunkt der Prüfung). **Keiner davon berührt eine
Upstream-Datei**, das Nachziehen ist also ein glatter Replay. Ablauf, sobald Phase 5
nicht mehr auf `main` committet:

1. `git rebase --onto rebase/upstream-v0.7.0 fecb76b main` — die neuen
   `main`-Commits auf den Rebase-Branch setzen.
2. Gates im Worktree-venv wiederholen (pytest differentiell, ruff).
3. `main` zeigt dann auf das Ergebnis; Force-Push von `fork/main`
   (`git push --force-with-lease fork main`) nur mit ausdrücklicher Freigabe.
4. Rebase-Protokoll in `STATE.md` eintragen (während Phase 5 bewusst nicht getan,
   die andere Session schreibt dort gerade).
5. Das Haupt-venv braucht danach `pip install -e ".[dev,ibkr]"`
   (tradingagents 0.7.0, `cryptography`, `packaging`).

Kein Push, kein Ref-Update auf `main` in diesem Task. Geschrieben wurden im
Haupt-Repo nur die zwei Refs `backup/pre-rebase-v0.7.0` und
`rebase/upstream-v0.7.0` sowie der Worktree-Eintrag.
