---
quick_id: 261012-t8w
status: complete
completed: 2026-10-12
commits:
  - 3496dde feat(jev): add opt-in stdlib Jev client and config keys
  - 3e0e587 feat(jev): review finished runs with Jev fallback and shadow checks
  - 580bd6a feat(paper-run): carry the Jev review into the ticker record
  - f5fca1f docs(jev): document the opt-in Jev review in CHANGELOG and .env.example
  - 88dbbc0 test(jev): add manual live smoke for the Jev run review
---

# Quick 261012-t8w: Jev in TradingEngineX (Fallback + Schatten)

## Ergebnis

- `tradingagents/jev/client.py`: stdlib-urllib-Client (validate, build_request, summarize, redact, verifizierender SSL-Kontext, `call_api` mit 1 Retry bei 429/502/503/524/529 nach 1 s). Der Key kommt nur aus `JEV_API_KEY`.
- `tradingagents/jev/hooks.py::review_run`: ein Request pro Ticker mit `decision`/`plan`/`proposal`/`sentiment`.
  - F1 Fallback: Bei REVIEW + Tier + conf >= 0.9 wird `final_rating` ersetzt, `final_rating_source="jev"`, WARNING-Log.
  - F2–F5 nur Schatten: Ergebnisse in `final_state["jev"]` und im Sidecar `jev_review_<date>.json`.
  - Jeder Fehler ergibt genau eine redigierte Warnung.
- `trading_graph.py`: +2/-0 (Import + erster Aufruf in `record_decision`).
- `default_config.py`: `jev_enabled` False, `jev_min_confidence` 0.9, `jev_timeout` 5.0 plus Env-Overrides `TRADINGAGENTS_JEV_*`.
- `daily_paper_run.py`: `record["jev"]` und `record["rating_source"]` nur dann, wenn Jev lief.
- Doku: `.env.example` (+7) und CHANGELOG (+13, nur fork-Abschnitt).
- Smoke-Skript `scripts/smoke/jev_live_smoke.py`.

## Abweichungen

1. **`jev_timeout` Default 5.0 statt 10.0.** Grund: Plan-Checker-Warnung 3. Schlechtester Fall: 5 s + 1 s Backoff + 5 s ≈ 11 s pro Ticker. Die synchronen Kosten stehen im CHANGELOG-Eintrag.
2. **Sidecar auch im Fehlerfall.** Er enthält dann `{"error": ...}`. Schlägt der Sidecar-Write selbst fehl (z. B. ungültiger Ticker), gibt es nur eine eigene Warnung. Ein bereits angewendeter Fallback bleibt dabei bestehen; ein Test sichert das ab.
3. **Docstring in `client.py` nennt `TYPESAFE_API_KEY` nicht wörtlich.** So bleibt das Grep-Gate hart.
4. **TDD-Hilfsmuster:** In `test_daily_paper_run.py` gab es den Fake-Graph `_FakeGraph`. Für den Jev-Test wurde eine kleine Subclass davon angelegt; `_FakeGraph` selbst blieb unverändert. Die `record_decision`-Verdrahtung wird wie in `test_cli_memory_log.py` getestet (`object.__new__` + gestubbtes `_log_state`).

5. **Codex-Review (2 Runden, siehe REVIEW.md).** Runde 1 = BLOCK mit 3 Funden, vom Orchestrator behoben:
   - `155a695`: Läufe mit `portfolio_context` gehen gar nicht an Jev, weil die Analyse-Texte Bestände zitieren können (HIGH). Neuer Test `test_a_run_with_a_portfolio_context_is_not_sent`; der Standard-State der Hook-Tests hat jetzt einen leeren Portfolio-Kontext.
   - `08eeff6`: `jev_*`-Keys in `_NOT_IN_SIGNATURE`. Sonst hätte schon das Hinzufügen der Default-aus-Keys jeden bestehenden Checkpoint ungültig gemacht (MEDIUM). Das prüft jetzt `test_checkpoint_resume.py` mit. Folge: `trading_graph.py` hat +5/-0 statt +2/-0.
   - Runde 2 = **SHIP**, alle Funde RESOLVED, keine neuen.

## Tests

- Neue Tests: `test_jev_client.py` (29), `test_jev_hooks.py` (22 nach Review-Fix), `test_daily_paper_run.py` (+2). Alle grün.
- Volle Suite nach den Review-Fixes (Orchestrator): **1792 passed, 2 failed, 4 skipped, 1 deselected** (Fehlschläge wie unten, schon vorher vorhanden). Executor-Lauf davor: 1791 passed. Beide Fehler bestehen schon vorher und hängen an Windows:
  - `test_suite_isolation::test_yfinance_keeps_its_cache_out_of_the_users_home` (bekannt)
  - `test_cli_commands::test_every_command_is_registered_when_run_as_a_module`: Der Subprocess-Output wird als cp1252 dekodiert (`UnicodeDecodeError`). Auf dem Basis-Commit 26252a8 in einem temporären Worktree ebenfalls rot, also **keine Regression**.
- `ruff check .`: All checks passed.
- Grep-Gate (PowerShell `Select-String`, bricht bei einem Treffer ab): kein `TYPESAFE_API_KEY`/`CERT_NONE`/`check_hostname=False` in `tradingagents/jev/`.
- `git diff --numstat trading_graph.py`: `2 0`.

## Live-Smoke (einmal, echter Key aus `.env`, Exit 0, kein `apikey_`/`sk-or-` in der Ausgabe)

```
INFO tradingagents.jev.hooks: Jev shadow disagreement on trader_action: engine HOLD, jev buy (conf 0.29)
WARNING tradingagents.jev.hooks: Jev fallback: REVIEW -> Overweight (conf 0.99)
{
  "final_rating": "Overweight",
  "final_rating_source": "jev",
  "jev": {
    "model": "jev-1.13.0",
    "input_tokens": 1032,
    "cost_usd": 4.334e-05,
    "latency_ms": 378,
    "attempts": 1,
    "min_confidence": 0.9,
    "questions": {
      "final_rating":            {"existing": "REVIEW",  "jev": "overweight", "confidence": 0.99, "agree": false, "applied": true},
      "research_recommendation": {"existing": "Hold",    "jev": "hold",       "confidence": 0.99, "agree": true,  "applied": false},
      "trader_action":           {"existing": "HOLD",    "jev": "buy",        "confidence": 0.29, "agree": false, "applied": false},
      "sentiment_band":          {"existing": "Neutral", "jev": "neutral",    "confidence": 0.99, "agree": true,  "applied": false}
    }
  }
}
```

Bewertung: Der Fallback hat gegriffen (die Fixture argumentiert absichtlich ohne Label für „mehr als Benchmark-Gewicht“, also Overweight). Bei der kurzen Trader-Fixture war Jev unsicher (0.29); als Schatten blieb das ohne Wirkung. Kosten pro Ticker: $0.00004.

## Hinweise

- **`JEV_API_KEY` und `TYPESAFE_API_KEY` sind bewusst getrennt.** `TYPESAFE_API_KEY` schaltet zusätzlich das Upstream-Post-Screening ein (`agents/post_screen.py`). Der Fork-Client liest ihn nie.
- Jev-Kosten laufen nicht durch das `max_cost_per_run`-Budget.
- Serenas Python-LSP ist in der Research-Phase nicht gestartet (`LanguageServerTerminatedException`), deshalb wurde Grep/Read verwendet.
- Der Graphify-Graph ist veraltet (Stand vor v0.6.0). Vor weiterer Nutzung `/graphify . --update` ausführen.
