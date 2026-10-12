---
phase: 02-verbindung-paper-guard-und-kontolesen
plan: 06
subsystem: paper-run / kontolesen
tags: [ibkr, portfolio, paper-run, kriterium-7, d-10]
requires: ["02-03", "02-05"]
provides:
  - "Nachweis Kriterium 7 am echten System: Portfolio-Block im complete_report.md"
affects: [phase-07-ci-verdrahtung]
tech-stack:
  added: []
  patterns: []
key-files:
  created: []
  modified: []
decisions:
  - "Lokale Paper-Läufe müssen TRADINGAGENTS_LLM_PROVIDER=anthropic plus die CI-Modellvariablen setzen; sonst greift der Bibliotheks-Default openai (derzeit ohne Guthaben)"
  - "SSL-Vendor-Fallbacks lokal (yfinance, sec_edgar) sind eine Maschinen-Eigenheit wie bei npm/uv, kein Phase-2-Defekt; Datenqualität lokaler Läufe ist ein eigenes Folgethema"
metrics:
  duration: "~1 Sitzung (Preflight + 2 Laufversuche)"
  completed: 2026-10-12
requirements: [REQ-IBKR-11, REQ-IBKR-05]
---

# Phase 2 Plan 06: Echter Paper-Lauf mit `--portfolio` (Kriterium 7) — Summary

Das in 02-05 gegen `DUQ634065` erzeugte Portfolio-JSON fließt über `--portfolio` in einen echten lokalen Paper-Lauf (Anthropic, AAPL, 0,1307 $); `complete_report.md` zeigt den Block „Portfolio at the analysis date:“ mit `No current position in AAPL` und `Cash available: 1,005,459.44 EUR`.

## Aufgaben

| Task | Name | Ergebnis | Commit |
|------|------|----------|--------|
| 1 | Preflight mit echtem JSON + Negativprobe | Positivprobe Exit 0, Negativprobe (`does-not-exist.json`) Exit genau 1 | — (keine Repo-Änderung) |
| 2 | Echter lokaler Paper-Lauf mit `--portfolio` | Exit 0, `AAPL: ok signal=Hold cost=$0.1307`; vom Operator freigegeben 2026-10-12 | — (keine Repo-Änderung) |

Der Plan sieht ausdrücklich keine Repo-Dateiänderung vor (`files_modified: []`); dieses SUMMARY ist der einzige Commit.

## Nachweis

Scratch-Verzeichnis: `$TEMP/tex-phase2-k7` (außerhalb des Repos, nicht `paper-log`).

### Task 1 — Preflight (ohne LLM-Kosten)

- Positivprobe mit `--portfolio "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json" --preflight`: Exit 0 (bereit).
- Negativprobe mit `--portfolio <scratch>/does-not-exist.json --preflight`: Exit 1 (`EXIT_CONFIG`) — wie gefordert genau 1.
- Hinweis: Die Preflight-Ausgaben wurden nicht in eine Datei im Scratch-Verzeichnis geschrieben. Die Exit-Codes stammen aus dem Lauf des Orchestrators; diese Fortsetzung hat den Preflight nicht noch einmal ausgeführt (Vorgabe: nur grep).

### Task 2 — Echter Lauf

**Versuch 1** (`run-openai-429.log`, `out-openai-429/`): Lokal war `TRADINGAGENTS_LLM_PROVIDER` nicht gesetzt, also griff der Bibliotheks-Default `openai`. Ergebnis: `Error code: 429 ... insufficient_quota / credit_balance_exhausted`, `EXIT=3` (Log-Zeile 203), 0 $, kein Report. Ursache ist das OpenAI-Konto ohne Guthaben, kein Code-Fehler. Die CI setzt standardmäßig `anthropic`.

**Versuch 2** (`run.log`, `out/`) lief mit genau der CI-Konfiguration: `TRADINGAGENTS_LLM_PROVIDER=anthropic`, `DEEP=claude-sonnet-5-5`, `QUICK=claude-haiku-5-5`, `MAX_DEBATE_ROUNDS=1`, `MAX_RISK_ROUNDS=1`, `LLM_MAX_RETRIES=4`, dazu `--tickers AAPL --max-cost 1 --out $S/out --state $S/state --portfolio %LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json`.

Was im Log steht (per grep geprüft):
```
3:  paper-run: 1 ticker(s) AAPL on 2026-10-09 | provider=anthropic deep=claude-sonnet-5-5 quick=claude-haiku-5-5 | budget $1.00/ticker, $1.00 total
31: --- AAPL: ok signal=Hold cost=$0.1307 ---
39: | AAPL | ok | Hold | 0.1307 | 80957/21513 | 105s |
43: EXIT=0
```

Was im Report `out/reports/AAPL/complete_report.md` steht (per grep geprüft):
```
10: Portfolio at the analysis date:
11: - No current position in AAPL
12: - Cash available: 1,005,459.44 EUR
```

### Repo-Integrität (T-02-25, T-02-26)

- `git status --short`: nur die vorher schon untracked Pfade `.planning/config.json` und `.planning/debug/`, sonst keine neuen Dateien.
- `git diff --quiet -- .github/workflows/`: Exit 0, die Workflows sind unberührt.
- Nichts wurde nach `paper-log` geschrieben. `--state` zeigte auf das Scratch-Verzeichnis.

## Abweichungen vom Plan

1. **[Durchführung] Der echte Lauf wurde vom Orchestrator gestartet, nicht vom Operator selbst.** Der Operator hat das ausdrücklich verlangt („bitte 2“) und das Ergebnis am 2026-10-12 freigegeben. Die Kostengrenze (`--max-cost 1`, ein Ticker) blieb eingehalten.
2. **[Umgebung] Zwei Laufversuche.** Versuch 1 scheiterte am Provider-Default `openai` (429, 0 $, siehe oben). Versuch 2 lief mit der CI-Konfiguration. Code wurde dafür nicht geändert.

## Beobachtung: Datenquellen bei lokalen Läufen (kein Phase-2-Defekt)

`run.log` enthält 17 Zeilen mit `CertificateVerifyError`/`SSLError`:
- 8× `Cookie/crumb fetch failed (CertificateVerifyError)` (yfinance),
- 6× yfinance-Vendor nicht verfügbar → Fallback auf den nächsten Vendor (`get_news` ×2, `get_stock_data` ×2, `get_global_news`, `get_indicators`),
- 3× sec_edgar `SSLError` → Fallback (`get_cashflow`, `get_balance_sheet`, `get_income_statement`).

Dazu kommt, dass `fred` nicht konfiguriert ist (`FRED_API_KEY` fehlt), deshalb waren die optionalen Makrodaten nicht verfügbar.

Die lokale Analyse lief also auf Fallback-Daten. Das ist dieselbe SSL-Eigenheit dieser Maschine wie bei npm/uv; die CI unter Linux betrifft das nicht. Kriterium 7 (Portfolio-Block im Report) ist davon unabhängig belegt. Die Datenqualität lokaler Läufe ist ein eigenes Folgethema.

## Hinweise für STATE/Handbuch (Folgearbeit, hier nicht umgesetzt)

- `scripts/PAPER_RUN.md` sollte für lokale Läufe festhalten, dass `TRADINGAGENTS_LLM_PROVIDER=anthropic` und die CI-Modellvariablen gesetzt sein müssen, sonst greift `openai` (derzeit ohne Guthaben, endet mit Exit 3). Der Plan schreibt diese Handbuch-Notiz nicht vor, deshalb wurde sie hier nicht geändert.
- Optional für lokale Läufe: das SSL-Fallback-Problem (yfinance/sec_edgar) als eigenes Todo aufnehmen.

## Known Stubs

Keine (keine Code-Änderung).

## Threat Flags

Keine neue Angriffsfläche. T-02-24 (Kontostand im Prompt an Anthropic) wird wie geplant akzeptiert: Paper-Konto, nur Cash und Positionen, keine Zugangsdaten.

## Self-Check: PASSED

- FOUND: `$TEMP/tex-phase2-k7/out/reports/AAPL/complete_report.md` mit „Portfolio at the analysis date“ (Zeile 10)
- FOUND: `run.log` `EXIT=0` (Zeile 43), `run-openai-429.log` `EXIT=3` (Zeile 203)
- FOUND: `git diff --quiet -- .github/workflows/` = 0
- Keine Task-Commits zu prüfen (Plan ohne Repo-Änderung)
