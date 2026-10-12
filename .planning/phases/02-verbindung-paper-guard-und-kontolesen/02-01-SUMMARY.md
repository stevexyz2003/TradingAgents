---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 01
subsystem: dependencies / ibkr-isolation
tags: [ibkr, ib_async, tzdata, pin, extra, ci-isolation, venv]
requires: []
provides:
  - "Optionales Extra `ibkr` (ib_async==2.1.0, tzdata>=2025.2,<2026.0) mit Begründungskommentar"
  - "Wächtertests tests/test_ibkr_isolation.py (Pin, Deckel-Kommentar, .env nicht getrackt, CI ohne IBKR)"
  - "Lauffähiges lokales .venv mit -e .[dev,ibkr]"
  - "Gemessener Negativnachweis für ROADMAP Phase 2 Kriterium 6"
affects: [02-02, 02-03, 02-04, 02-05, 02-06]
tech-stack:
  added: ["ib_async 2.1.0 (optional extra ibkr)", "tzdata 2025.x (Deckel <2026.0)"]
  patterns: ["Optionales Extra statt Kern-Abhängigkeit", "Strukturtests auf pyproject.toml via tomllib"]
key-files:
  created:
    - tests/test_ibkr_isolation.py
  modified:
    - pyproject.toml
    - .env.example
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
decisions:
  - "Kriterium 6 beschreibt den gemessenen Negativnachweis (ib_async==2.1.0 + tzdata>=2026.1 -> ResolutionImpossible), nicht mehr ‚ohne Pin bricht es‘ (D-03)"
  - "Paket-Legitimität ib_async 2.1.0 / tzdata vom Operator am 2026-10-12 freigegeben (T-02-SC)"
metrics:
  duration: "ca. 10 min (Task 3, Fortsetzung)"
  completed: 2026-10-12
  tasks: 3
  files: 5
---

# Phase 2 Plan 01: Extra `ibkr`, Pin-Deckel-Nachweis und Isolationswächter Summary

`ib_async==2.1.0` als optionales, exakt gepinntes Extra `ibkr` samt sichtbarem `tzdata<2026.0`-Deckel; der Deckel ist per pip `ResolutionImpossible` gemessen, vier Wächtertests halten Pin, `.env`-Tracking und CI-Credential-Freiheit fest, und das `.venv` ist auf `-e .[dev,ibkr]` aufgefrischt.

## Tasks

| Task | Name | Commit | Dateien |
| ---- | ---- | ------ | ------- |
| 1 | Extra `ibkr` deklarieren, Kriterium 6 umformulieren, Wächtertests anlegen | f647784 | pyproject.toml, .env.example, .planning/ROADMAP.md, .planning/REQUIREMENTS.md, tests/test_ibkr_isolation.py |
| 2 | Paket-Legitimität bestätigen (checkpoint:human-verify, blocking-human) | — (Freigabe) | — |
| 3 | `.venv` auffrischen und Pin-Deckel messen | — (nur lokales `.venv`, Protokoll hier) | — |

## Freigabe Paket-Legitimität (Task 2, T-02-SC)

- **Datum:** 2026-10-12
- **Wer:** Operator, Antwort „approved“
- **Belege (vom Orchestrator lokal geprüft):** `ai_tradex/.venv` enthält `ib_async-2.1.0.dist-info` (License BSD, Repository `https://github.com/ib-api-reloaded/ib_async`) — dasselbe Paket, mit dem die Phase-1-Probe lief. `tzdata` ist das PSF-Projekt (2025.2 in diesem `.venv`, 2025.3 in `ai_tradex`).
- Erst nach dieser Freigabe wurde installiert.

## Messprotokoll (Task 3, 2026-10-12, ab 07:07 UTC)

Alle Befehle aus dem Repo-Wurzelverzeichnis, `P=.venv/Scripts/python.exe` (Python 3.13, pip 25.1.1, uv 0.11.7). pip erreichte PyPI direkt über den System-Truststore; der uv-Ausweichweg war für die Installation nicht nötig.

### 1. Auffrischen — Exit 0

```
$ $P -m pip install -e ".[dev,ibkr]"
Successfully installed aeventkit-2.1.0 ... ib_async-2.1.0 ... nest_asyncio-1.6.0 ...
  pytest-subtests-0.15.0 ruff-0.17.0 tradingagents-0.6.0 ... yfinance-1.7.0
EXIT=0
$ $P -m pip check
No broken requirements found.        EXIT=0
$ $P -c "...m.version('ib_async'), m.version('tzdata')"
2.1.0 2025.2
$ $P -m ruff --version
ruff 0.17.0
```

Das `.venv` war deutlich veraltet (Pitfall 9): u. a. `tradingagents` 0.2.4 → 0.6.0, `langgraph` 0.4.8 → 1.2.14 wurden mit aktualisiert. Das vorhandene `tzdata` 2025.2 erfüllt den Deckel und blieb stehen.

### 2. Negativnachweis Kriterium 6 — Exit 1, `ResolutionImpossible`

```
$ $P -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2026.1"
Collecting tzdata>=2026.1
  Using cached tzdata-2026.5-py2.py3-none-any.whl.metadata (1.4 kB)
ERROR: Cannot install ib-async==2.1.0 and tzdata>=2026.1 because these package versions have conflicting dependencies.
The conflict is caused by:
    The user requested tzdata>=2026.1
    ib-async 2.1.0 depends on tzdata<2026.0 and >=2025.2
ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
EXIT=1
```

Echter Auflösungskonflikt, kein Netz-/SSL-Fehler — zählt als Negativnachweis.

### 3. Positivnachweis gepinntes Paar — Exit 0

```
$ $P -m pip install --dry-run --ignore-installed "ib_async==2.1.0" "tzdata>=2025.2,<2026.0"
Would install aeventkit-2.1.0 ib_async-2.1.0 nest-asyncio-1.6.0 numpy-2.5.4 tzdata-2025.3
EXIT=0
```

### 4. Projekt-Positivnachweis in frischer Auflösung — Exit 0

```
$ uv pip compile --system-certs --python-version 3.13 pyproject.toml --extra ibkr -o <scratchpad>/ibkr-resolution.txt
EXIT=0   (285 Zeilen)
  72: ib-async==2.1.0
 259: tzdata==2025.3
```

### 5. Tests und Lint

```
$ $P -m pytest tests/test_ibkr_isolation.py tests/test_portfolio_context.py -q
24 passed in 1.51s
$ $P -m pytest -q
1 failed, 1386 passed, 4 skipped, 1 deselected, 20 warnings, 101 subtests passed in 25.94s
  FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
$ $P -m ruff check .
All checks passed!
$ git ls-files .env
(leer)
```

Der eine Fehlschlag ist der bekannte umgebungsabhängige Windows-Fehler (bestehend, identisch mit Upstream), nicht durch diesen Plan verursacht und hier bewusst nicht behoben. Die Suite sammelt wieder vollständig, es gibt keinen `yfinance`-Collection-Fehler mehr. Die 4 Skips betreffen POSIX-Dateirechte (3) und das nicht installierte Extra `bedrock` (1).

## Deviations from Plan

Keine — Plan wie geschrieben ausgeführt (Task 1 im Vorlauf, Task 2 als blockierender Checkpoint, Task 3 in dieser Fortsetzung).

## Known Stubs

Keine. Die `.env.example`-Zeilen sind absichtlich auskommentierte Vorlagen.

## Self-Check: PASSED

- FOUND: tests/test_ibkr_isolation.py
- FOUND: Commit f647784
- FOUND: `ib_async` 2.1.0 / `tzdata` 2025.2 im `.venv`
- Alle vier Messungen mit Exit-Code und Datum protokolliert
