---
phase: quick-261018-kof
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tradingagents/patterns/__init__.py
  - tradingagents/patterns/signals.py
  - tradingagents/patterns/evaluate.py
  - tests/test_patterns_signals.py
  - tests/test_patterns_evaluate.py
  - scripts/pattern_eval.py
  - tests/test_pattern_eval_cli.py
  - .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md
  - .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md
autonomous: true
requirements: [QUICK-261018-kof]

must_haves:
  truths:
    - "Fuer jeden Eintrag im Memory-Log werden 5-6 explizite Muster nur aus Kursen bis einschliesslich Entscheidungsdatum berechnet; Kurse nach as_of zu veraendern aendert das Ergebnis nicht (Test beweist es)"
    - "Je Muster und Richtung meldet die Auswertung n_all, n_independent, ties, Wilson-95-%-Intervall und Trefferquote sowohl alpha-basiert als auch raw-return-basiert, oder status=insufficient ohne Trefferquote unter MIN_N"
    - "Der vor dem Fix #1518 abgerechnete Eintrag (2026-10-09 AAPL) bleibt in der Auswertung und ist als alte Einstiegskonvention markiert"
    - "Die Auswertung liest die echte Historie per --git-ref fork/paper-log ohne Checkout und ohne LLM-Aufruf (kein Settlement, kein Reflector)"
    - "Codex hat die Kette Rating -> Settlement -> Backtest-Aggregation und das Muster-Modul statisch geprueft; der Bericht liegt im 04-CODEX-REVIEW-Format im Quick-Verzeichnis"
    - "Upstream-Dateien (rating.py, settlement.py, backtest.py, log.py) sind unveraendert, ausser fuer einen von Codex belegten Fehler mit kleinstmoeglichem Patch plus Test, notiert als Upstream-Kandidat"
  artifacts:
    - path: "tradingagents/patterns/signals.py"
      provides: "Reine Indikatoren und compute_patterns(ohlcv, as_of) mit eigenem Abschneiden auf Date <= as_of"
      exports: ["compute_patterns", "PATTERNS"]
    - path: "tradingagents/patterns/evaluate.py"
      provides: "Log-Join, Wilson, MIN_N, Unabhaengigkeit, Ties, Konventions-Flag, Doppel-Trefferquote"
      exports: ["wilson", "evaluate", "PatternReport", "MIN_N"]
    - path: "scripts/pattern_eval.py"
      provides: "CLI: --log PATH | --git-ref REF, Markdown- oder JSON-Ausgabe"
    - path: ".planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md"
      provides: "Ergebnis des einmaligen Laufs auf fork/paper-log (deutsch)"
    - path: ".planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md"
      provides: "Codex-Bericht mit file:line-Befunden und Dispositionen"
  key_links:
    - from: "tradingagents/patterns/evaluate.py"
      to: "tradingagents.memory.log.TradingMemoryLog.load_entries"
      via: "Parser des Memory-Log-Formats wiederverwenden"
      pattern: "TradingMemoryLog"
    - from: "tradingagents/patterns/evaluate.py"
      to: "tradingagents/patterns/signals.py"
      via: "compute_patterns je Eintrag mit injiziertem price_loader"
      pattern: "compute_patterns\\("
    - from: "scripts/pattern_eval.py"
      to: "git show <ref>:decision-log.md"
      via: "subprocess Argumentliste, kein shell=True"
      pattern: "\\[\"git\", \"show\""
---

<objective>
Schritt 1 der Methodik "Muster -> Prognose" (CONTEXT.md): ein fork-only Modul `tradingagents/patterns/`, das je Entscheidung im Memory-Log 5-6 explizite Kursmuster ohne Look-ahead berechnet und je Muster misst, ob das Engine-Rating danach recht hatte, mit ehrlicher Statistik fuer kleines N. Dazu eine unabhaengige Codex-Validierung der ganzen Bewertungskette und ein einmaliger Lauf auf der echten Paper-Log-Historie.

Purpose: Belegen, welche Muster (spaeter) eine deterministische Muster-Schicht tragen koennten, und Rechenfehler in der Kette aufdecken, bevor Ratings in Phase 6 echte Orders ausloesen.
Output: Modul + CLI + Tests (Code, vom Executor committed), EVALUATION.md + CODEX-REVIEW.md (Docs, vom Orchestrator committed).

Ausser Scope (Orchestrator-Entscheidung 3): Schritt 2, die deterministische Muster-Schicht/Veto. Es gibt noch keine abgerechnete Richtungsentscheidung. Nur als Folgepunkt in EVALUATION.md notieren, keinen Code dafuer schreiben.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CONTEXT.md
@.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-RESEARCH.md
@.planning/phases/04-entscheidungs-bernahme-und-soll-rechnung-bis-zum-whatif-prev/04-CODEX-REVIEW.md

Feste Regeln fuer den Executor:
- Tests: `.venv/Scripts/python.exe -m pytest ...`, Lint: `.venv/Scripts/python.exe -m ruff check ...` (`uv run` scheitert hier an TLS). Ruff: line-length 100, py311.
- Code, Docstrings, Commits auf Englisch; `.planning/`-Dateien auf Deutsch.
- NIE anfassen: `scripts/ibkr_*`, `tests/test_ibkr_*`, `scripts/IBKR_EXECUTION.md` (parallele Phase-6-Session). `scripts/ibkr_paperlog.py` nicht importieren.
- Keine Edits in `tradingagents/agents/rating.py`, `tradingagents/memory/settlement.py`, `tradingagents/memory/log.py`, `tradingagents/backtest.py` — einzige Ausnahme: Task 3, von Codex belegter Fehler.
- Kein Backtest, kein Graph, kein `settle_pending`, kein Reflector, keine LLM-Kosten. Codex ueber das ChatGPT-Konto ist erlaubt (es ist die verlangte Validierung).
- Docs-Artefakte (EVALUATION.md, CODEX-REVIEW.md, SUMMARY, STATE) NICHT committen — das macht der Orchestrator. Code-Commits macht der Executor.
- Der Operator arbeitet parallel im selben Repo: vor jedem Edit frisch lesen, nie fremde Aenderungen ueberschreiben, nur eigene Dateien stagen (`git add <pfad>`, nie `git add -A`).

<interfaces>
Aus dem Codebestand (verifiziert 2026-10-18, HEAD 98430cd):

tradingagents/memory/log.py
- `class TradingMemoryLog(config: dict | None)`; Config-Key `memory_log_path`.
- `load_entries() -> list[dict]`; Keys je Eintrag: date, ticker, rating, pending (bool), raw, alpha, holding, resolved, decision, reflection. `raw`/`alpha` sind Strings im Format `{:+.1%}` (z. B. "+2.0%", "-0.0%"), `holding` ist z. B. "5d", `resolved` ein Datum "YYYY-MM-DD" (das Exit-Datum), bei pending None.
- Abgerechneter Tag: `[2026-10-09 | AAPL | Hold | +2.0% | +4.0% | 5d | resolved:2026-10-16]`.

tradingagents/backtest.py
- `_alpha(entry) -> float | None` (:65), `_DIRECTION` (:90: Buy/Overweight +1, Hold 0, Underweight/Sell -1), `summarize` (:184-214, hit_rate = Anteil alpha*direction > 0, Ties zaehlen als Fehltreffer). Nur lesen, nicht aendern.

tradingagents/dataflows/vendors/yahoo/ohlcv.py
- `load_ohlcv(symbol: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame` (:161): Frame mit Spalte `Date` und OHLCV-Spalten (`Close`), 5 Jahre bis heute, gecacht, abgeschnitten `Date <= as_of` (:229), `auto_adjust=True`. Vor Nutzung die genauen Spaltennamen in :161-235 pruefen.

tradingagents/dataflows/symbols.py
- `safe_ticker_component(value: str, *, max_len: int = 32) -> str` (:155) — Ticker aus dem Log damit pruefen.

Import-Lage: `import tradingagents.<irgendwas>` zieht ueber das Paket-`__init__` bereits `langchain_core`, `langgraph` und `tradingagents.agents.*` (gemessen). Ein Laufzeit-Importverbot auf `langchain*` ist daher nicht haltbar. Das Verbot gilt fuer: `tradingagents.graph`, `tradingagents.memory.settlement`, `tradingagents.memory.reflection`, `tradingagents.llm_clients`, `langchain_openai`, `langchain_anthropic`, `langchain_google_genai` (AST-Check der Quelldateien plus sys.modules-Check in frischem Subprozess fuer graph/settlement/reflection).

CLI-Vorbild: `scripts/state_maintenance.py` (Modul-Docstring mit Aufrufzeilen und Exit-Codes, argparse, stdlib).
Fork-only-Vorbild: `tradingagents/jev/__init__.py` Docstring "... (fork-only)."
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fork-only pattern module (signals + evaluation statistics) with tests</name>
  <files>tradingagents/patterns/__init__.py, tradingagents/patterns/signals.py, tradingagents/patterns/evaluate.py, tests/test_patterns_signals.py, tests/test_patterns_evaluate.py</files>
  <behavior>
    - No look-ahead: compute_patterns(frame, as_of) equals compute_patterns(frame with every Close after as_of multiplied by 10 and extra rows appended, as_of).
    - Warm-up: with fewer than 200 bars, trend_sma200 and sma50_200 are None (not 0, not False); with 250 bars they are +1/-1.
    - Strictly rising series: RSI(14) = 100, rsi_extreme = -1 (overbought, contrarian); strictly falling: rsi_extreme = +1.
    - A constructed close above the max of the previous 20 closes gives breakout_20 = +1; the as_of bar itself is excluded from the max; below the previous 20-day min gives -1; otherwise 0.
    - macd_cross = +1 if MACD minus signal changed sign from negative to positive within the last 3 sessions, -1 for the reverse, 0 otherwise.
    - as_of falling on a non-trading day (holiday/weekend) uses the last bar on or before as_of.
    - wilson(0, 0) is None; wilson(10, 20) is approx (0.299, 0.701) at 3 decimals; wilson(20, 20) has upper bound 1.0.
    - Fewer than MIN_N independent cases gives status "insufficient" with hit_rate None, n still reported.
    - Tie handling: an alpha string "+0.0%" or "-0.0%" is counted in ties, not in the denominator; same for raw-based hit rate with raw "±0.0%".
    - Both hit rates: an Overweight with raw +1.0% and alpha -0.5% is a raw hit and an alpha miss.
    - Daily entries of one ticker with holding 5d give n_independent < n_all (greedy, spacing >= holding business days).
    - Convention flag: [2026-10-09 | AAPL | Hold | ... | 5d | resolved:2026-10-16] is flagged "decision_close" (legacy); an entry dated 2026-10-12 resolved 2026-10-19 is "next_close"; anything else "unknown".
    - REVIEW entries and resolved entries with unparseable alpha are excluded and counted; pending entries are only counted in n_pending; Hold entries count in the pattern-alone evaluation but not in the engine-conditioned one.
    - Round trip: a fixture log in the real tag format (synthetic, 16 entries mirroring the paper-log shape: 13 Hold, 3 Overweight, 1 resolved) parsed through TradingMemoryLog yields the expected counts, no network.
    - Import ban: AST of every file in tradingagents/patterns imports none of the banned modules (see interfaces); a fresh subprocess `import tradingagents.patterns.evaluate` leaves tradingagents.graph, tradingagents.memory.settlement and tradingagents.memory.reflection absent from sys.modules.
  </behavior>
  <action>
Write the tests first (RED), then the implementation (GREEN), following RESEARCH.md sections 2, 3 and 6.

`tradingagents/patterns/__init__.py`: docstring "Deterministic market patterns and their evaluation against the decision log (fork-only)." Re-export nothing heavy.

`signals.py` (pure pandas, no stockstats — RESEARCH 2): public `PATTERNS: tuple[str, ...]` = ("rsi_extreme", "macd_cross", "breakout_20", "trend_sma200", "sma50_200", "bollinger_out") and `compute_patterns(ohlcv: pd.DataFrame, as_of: str) -> dict[str, int | None]`. The function itself sorts by `Date` and truncates to `Date <= as_of` before computing anything (that is what makes the look-ahead test a proof). Each value is +1 (bullish), -1 (bearish), 0 (computable, inactive) or None (not enough bars). Constants as module-level names with a one-line rationale comment each (Claude's discretion per CONTEXT, values from the RESEARCH table): RSI 14 Wilder (`ewm(alpha=1/14, adjust=False)`) with 30/70 and a contrarian direction (oversold -> +1; document this as a modelling choice, assumption A2); MACD 12/26/9 with a 3-session cross lookback; Donchian 20 excluding the current bar; SMA200 trend; SMA50 vs SMA200 regime; Bollinger 20/2 sigma, contrarian (below lower band -> +1). Minimum bars per pattern defined as constants; below them return None.

`evaluate.py`: public `MIN_N = 20`, `Z95 = 1.959963984540054`, `wilson(hits, n, z=Z95) -> tuple[float, float] | None` (formula in RESEARCH 3), dataclasses `PatternCell` (pattern, side +1/-1, mode "engine" | "pattern", n_all, n_independent, ties, hits_alpha, hits_raw, hit_rate_alpha, hit_rate_raw, ci_alpha, ci_raw, mean_alpha, status "ok" | "insufficient") and `PatternReport` (cells, n_entries, n_resolved, n_pending, n_review_excluded, n_unparseable, holdings seen, conventions seen as counts, warnings list, flagged entries list). Function `evaluate(entries: list[dict], price_loader: Callable[[str, str], pd.DataFrame]) -> PatternReport` and `load_log_entries(path) -> list[dict]` that wraps `TradingMemoryLog({"memory_log_path": str(path)}).load_entries()`. Parse "+2.0%" strings with a local helper (do not import backtest._alpha; private). Direction map: Buy/Overweight +1, Hold 0, Underweight/Sell -1, anything else (REVIEW) excluded. Two evaluation modes per pattern and side (RESEARCH 2): "engine" = directional ratings only where the pattern is active on that side, hit = sign(metric) == rating direction; "pattern" = all resolved entries including Hold, hit = sign(metric) == pattern side. Both hit rates are reported side by side, alpha-based and raw-return-based (orchestrator decision 1); ties (metric exactly 0.0 after parsing) leave the denominator and go to `ties`. Independence: per ticker, sort by date, greedy keep when `numpy.busday_count(prev_kept, cur) >= holding_days`; status is "insufficient" when n_independent < MIN_N, and then hit rates and CIs are None but n values stay. Convention flag (orchestrator decision 2, keep the entry, flag it): `numpy.busday_count(date, resolved)` == holding -> "decision_close" (legacy, before fix #1518), == holding + 1 -> "next_close", otherwise "unknown"; document in the docstring that this is inferred from weekdays and a holiday can shift it. Add warnings when more than one holding or more than one convention appears, and a fixed warning that alpha is a plain difference against the benchmark (no beta) and that the ticker pool is fixed (survivorship/selection, RESEARCH points 7 and 9). Prices: the loader is injected; also provide `default_price_loader()` that caches one `load_ohlcv(ticker, max_date, fill_gaps=False)` frame per ticker and returns it; `compute_patterns` does the per-entry truncation. Validate tickers with `safe_ticker_component` before loading. Missing price data for a ticker is a warning plus None patterns, never a silent zero. Provide `render_markdown(report) -> str` (tables, German labels are not required in code — use English) and `report_to_dict(report) -> dict` for JSON.

Tests use synthetic frames built in the test (no network, no monkeypatching yfinance). Do not add dependencies (scipy is not installed; numpy/pandas only).

Commit (code only): `feat(patterns): add look-ahead-free pattern signals and small-N evaluation (fork-only)`.
  </action>
  <verify>
    <automated>.venv/Scripts/python.exe -m pytest tests/test_patterns_signals.py tests/test_patterns_evaluate.py -q && .venv/Scripts/python.exe -m ruff check tradingagents/patterns tests/test_patterns_signals.py tests/test_patterns_evaluate.py</automated>
  </verify>
  <done>All behavior bullets have a passing test; ruff clean; `git diff --stat HEAD~1 -- tradingagents/agents/rating.py tradingagents/memory tradingagents/backtest.py` is empty; code commit exists.</done>
</task>

<task type="auto">
  <name>Task 2: CLI pattern_eval.py and one evaluation run on the real paper-log history</name>
  <files>scripts/pattern_eval.py, tests/test_pattern_eval_cli.py, .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md</files>
  <action>
`scripts/pattern_eval.py` modelled on `scripts/state_maintenance.py` (module docstring with usage lines and exit codes, argparse, no network except price loading, no LLM). Mutually exclusive required inputs: `--log PATH` or `--git-ref REF` (e.g. `fork/paper-log`). For `--git-ref`, validate REF against a conservative regex (letters, digits, `/._-` only, no leading `-`) and run `subprocess.run(["git", "show", f"{ref}:decision-log.md"], capture_output=True, check=False)` — argument list, never `shell=True` — write the blob to a `tempfile` and pass its path to `load_log_entries`. The script does not fetch; the docstring tells the operator to run `git fetch fork paper-log` first. Options `--format md|json` (default md) and `--out FILE` (default stdout). Call `dotenv.load_dotenv()` at startup so the CA-bundle variables from the local `.env` reach yfinance (RESEARCH 4, `scripts/PAPER_RUN.md:156-181`); if any ticker returns no price data, print a loud warning to stderr and exit 3. Exit codes: 0 ok, 1 usage/config error (bad ref, git show failed, unreadable log), 3 price data missing. Do not import anything from `scripts/ibkr_*`.

`tests/test_pattern_eval_cli.py`: run `main([...])` with `--log` on a synthetic fixture log and a stub price loader (make the loader injectable via a module-level function the test monkeypatches), assert exit 0 and that the markdown contains "insufficient"; a ref like `--evil` or `a;b` is rejected with exit 1 before any subprocess call; `--git-ref` path uses a monkeypatched `subprocess.run` and asserts the argument list form.

Commit (code only): `feat(patterns): add pattern_eval CLI for decision-log evaluation (fork-only)`.

Then the one real run (no LLM costs, only yfinance): `git fetch fork paper-log`, then `.venv/Scripts/python.exe scripts/pattern_eval.py --git-ref fork/paper-log --format md` and once `--format json` into the scratchpad. If yfinance fails because of TLS, follow the CA-bundle recipe in `scripts/PAPER_RUN.md` (variables from `.env`), do not fall back to synthetic prices. Record the paper-log commit SHA (`git rev-parse fork/paper-log`).

Write `261018-kof-EVALUATION.md` in German: Frontmatter (date, paper-log SHA, code HEAD SHA, command). Sections: Datenlage (Eintraege, abgerechnet, pending, je Ticker/Rating), Musterzustaende je Eintrag (Tabelle), Auswertung je Muster und Seite (beide Modi, beide Trefferquoten, n_all/n_independent/ties/Status), Markierte Eintraege (2026-10-09 AAPL alte Konvention, Begruendung aus RESEARCH Verdachtsstelle 3), Warnungen, Ergebnis "zu wenig Daten" klar benannt (kein Muster erreicht MIN_N; Aussage, wie viele abgerechnete unabhaengige Richtungsentscheidungen je Muster fehlen und grob wie viele Wochen taeglicher Lauf das bei 3 Tickern bedeutet), Folgepunkte: Schritt 2 Muster-Schicht/Veto erst nach Belegung (Orchestrator-Entscheidung 3), Wiederholung des Laufs mit Kommando. Do not commit this file.
  </action>
  <verify>
    <automated>.venv/Scripts/python.exe -m pytest tests/test_pattern_eval_cli.py tests/test_patterns_signals.py tests/test_patterns_evaluate.py -q && .venv/Scripts/python.exe -m ruff check scripts/pattern_eval.py tests/test_pattern_eval_cli.py && test -s .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md && grep -q "fork/paper-log" .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-EVALUATION.md</automated>
  </verify>
  <done>CLI tests pass, ruff clean; the real run exited 0 on real yfinance prices (not fallback data); EVALUATION.md exists with paper-log SHA, all six patterns, the flagged legacy entry and an explicit "zu wenig Daten" result; code commit exists, EVALUATION.md uncommitted.</done>
</task>

<task type="auto">
  <name>Task 3: Codex review of the rating-settlement-aggregation chain and the pattern module, minimal proven fixes only</name>
  <files>.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md, (only if Codex proves a bug) the affected upstream file plus one new test file tests/test_upstream_fix_<topic>.py, (only if Codex finds a bug in the new module) tradingagents/patterns/*.py and its tests</files>
  <action>
Make sure Task 1 and 2 code is committed; record `git rev-parse --short HEAD`. Write the Codex prompt into the scratchpad (not the repo). The prompt names the HEAD SHA, asks for a static review only (sandbox read-only, pytest will likely be blocked as in Phase 4), German prose, every finding with `file:line`, severity (BLOCKER / WARNING / INFO), "bewiesen" vs "Verdacht", and a final table in the format of `04-CODEX-REVIEW.md`. Scope: `tradingagents/agents/rating.py`, `tradingagents/memory/log.py`, `tradingagents/memory/settlement.py`, `tradingagents/backtest.py`, `tradingagents/dataflows/vendors/yahoo/ohlcv.py` (`_fill_price_gaps` ffill/bfill), `tradingagents/dataflows/vendors/yahoo/market.py:get_closes`, `scripts/daily_paper_run.py:112-129`, and the new `tradingagents/patterns/*` plus `scripts/pattern_eval.py`. Checklist in the prompt = the 10 suspicion points of RESEARCH section 1 verbatim (rounding ties, alpha vs raw direction, mixed entry conventions incl. the 2026-10-09 AAPL entry, mixed windows/benchmarks, pending miscount, rotation, survivorship, overlapping windows, beta, analyst look-ahead), plus: look-ahead freedom of `compute_patterns` (truncation inside the function), correctness of RSI/MACD/Donchian/SMA/Bollinger formulas, Wilson formula, independence selection, tie handling, convention inference, the double-count guard in `store_decision`, and whether anything in the new module can trigger an LLM call.

Run: `codex exec -s read-only -m gpt-5.5 -C "C:/Users/admin/PycharmProjects/TradingEngineX" --ephemeral -o "<scratchpad>/codex-review.md" - < "<scratchpad>/codex-prompt.md"` (timeout up to 600000 ms; run in background if needed). Then run the full suite yourself on the same HEAD: `.venv/Scripts/python.exe -m pytest -q` (known Windows-env failures from STATE.md: test_chatgpt_auth x2, test_cli_updates x2, test_yfinance_keeps_its_cache_out_of_the_users_home — note them, they are not regressions) and `.venv/Scripts/python.exe -m ruff check .`.

Copy the report to `261018-kof-CODEX-REVIEW.md` with frontmatter exactly like Phase 4: `source: codex exec (codex-cli 0.137.0, sandbox read-only)`, `scope: committed HEAD <sha>`, `date: 2026-10-18`, `note:` static-analysis statement plus the suite result you measured. Append a German section "Disposition" with one row per finding: fixed (commit SHA) / accepted as limitation (reason) / design question for the operator / rejected (counter-evidence with file:line). Cross-check each Codex claim against the code yourself before acting — Codex self-claims can be wrong.

Fixes, strictly bounded (CONTEXT "Aenderungsort"):
- Bug in the new `tradingagents/patterns/` or the CLI: fix it with a regression test, commit `fix(patterns): ...`, then re-run Task 2's real evaluation and update EVALUATION.md if numbers change.
- Upstream file (rating.py, log.py, settlement.py, backtest.py, ohlcv.py, market.py): only if Codex proves a real computational bug AND you confirm it by a failing test. Smallest possible patch plus that test, commit `fix(<area>): ... (upstream candidate)`, and mark it "Upstream-Kandidat" in the Disposition. Interpretation questions are NOT bugs and stay unpatched: alpha-vs-raw direction labelling (already answered in the strand module, decision 1) and tie-as-miss in `summarize` (RESEARCH says the operator decides; the strand module already excludes ties) — list them as "Designfrage fuer den Operator".
- Never touch IBKR files. Do not commit CODEX-REVIEW.md or EVALUATION.md.
  </action>
  <verify>
    <automated>test -s .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md && grep -q "^source: codex exec" .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md && grep -q "Disposition" .planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-CODEX-REVIEW.md && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m pytest tests/test_patterns_signals.py tests/test_patterns_evaluate.py tests/test_pattern_eval_cli.py tests/test_backtest.py tests/test_memory_log.py -q</automated>
  </verify>
  <done>CODEX-REVIEW.md exists with Phase-4 frontmatter, file:line findings and a Disposition row for every finding; full suite shows no failures beyond the known Windows-env set; any upstream patch is minimal, test-backed and marked as upstream candidate; `git status` shows no changes under scripts/ibkr_*, tests/test_ibkr_* or scripts/IBKR_EXECUTION.md caused by this task.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CLI args -> subprocess git | `--git-ref` value is operator input passed to `git show` |
| decision-log.md -> parser | Log content from the paper-log branch (written by CI) is parsed; tickers flow into cache paths |
| yfinance -> evaluation | External price data; TLS interception by AVG on this machine |
| repo -> Codex | Codex reads the working tree (read-only sandbox) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-kof-01 | Tampering / Elevation | scripts/pattern_eval.py `--git-ref` | mitigate | Regex allowlist, reject leading `-`, argument-list `subprocess.run`, never `shell=True`; tested with `--evil` and `a;b` |
| T-kof-02 | Tampering | tickers from the log -> load_ohlcv cache path | mitigate | `safe_ticker_component` before any load; invalid ticker = warning, entry skipped |
| T-kof-03 | Information disclosure | `.env` loaded for CA bundle | accept | Only path variables are used; nothing from env is printed or written to EVALUATION.md |
| T-kof-04 | Repudiation / integrity of results | fallback or missing prices | mitigate | Missing data is a stderr warning and exit 3, never synthetic prices in the real run; EVALUATION.md records the paper-log SHA |
| T-kof-05 | Denial of wallet | accidental LLM call | mitigate | AST + sys.modules import-ban test for graph/settlement/reflection/llm_clients/provider SDKs |
| T-kof-06 | Tampering | Codex sandbox | mitigate | `-s read-only --ephemeral`; Codex output copied by the executor, claims cross-checked before any patch |
</threat_model>

<verification>
- `.venv/Scripts/python.exe -m pytest -q` — no failures beyond the known Windows-env set from STATE.md.
- `.venv/Scripts/python.exe -m ruff check .` clean.
- `git diff --stat 98430cd..HEAD -- scripts/ibkr_* tests/test_ibkr_* scripts/IBKR_EXECUTION.md` empty.
- `git diff --stat 98430cd..HEAD -- tradingagents/agents/rating.py tradingagents/memory tradingagents/backtest.py` empty, or each hunk is referenced as "Upstream-Kandidat" in CODEX-REVIEW.md with a test.
- EVALUATION.md and CODEX-REVIEW.md exist and are untracked (orchestrator commits them).
</verification>

<success_criteria>
- Six look-ahead-free patterns, proven by test, computed per log entry.
- Per-pattern evaluation with n, independent n, ties, Wilson CI, alpha- and raw-based hit rates, and an explicit "insufficient" result below MIN_N=20.
- Real paper-log history evaluated once; result documented honestly as "zu wenig Daten", legacy entry flagged.
- Independent Codex review of the full chain plus the new module, every finding dispositioned; only proven bugs patched, minimally and with tests.
- Step 2 (pattern layer/veto) recorded only as a follow-up.
</success_criteria>

<output>
Create `.planning/quick/261018-kof-vorhersagelogik-und-statistische-heurist/261018-kof-SUMMARY.md` when done (German). List for the orchestrator the uncommitted docs artifacts to commit: 261018-kof-EVALUATION.md, 261018-kof-CODEX-REVIEW.md, 261018-kof-SUMMARY.md (plus PLAN/RESEARCH/CONTEXT already in the directory).
</output>
