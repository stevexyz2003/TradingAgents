---
phase: quick-260922-iz5
plan: 01
subsystem: strand-maintenance
tags: [rebase, upstream-v0.5.0, budget, checkpoint-lifecycle, paper-run]
requires: [upstream v0.5.0 2d17df8, strand 16bbe96]
provides: [branch rebase/upstream-v0.5.0 @164869a, backup/pre-rebase-v0.5.0 @16bbe96]
affects: [tradingagents/graph/trading_graph.py, cli/main.py, tests/test_budget.py, scripts/paper_run_rates.json]
tech-stack:
  added: []
  patterns: [budget reset in create_run_state, always-streamed _run_graph with best-effort partial save, CLI abort inside upstream #1249 try/finally]
key-files:
  created: []
  modified:
    - tradingagents/graph/trading_graph.py
    - cli/main.py
    - tradingagents/default_config.py
    - tests/test_budget.py
    - tests/test_memory_log.py
    - tests/test_portfolio_context.py
    - tests/test_structured_agents.py
    - tests/test_daily_paper_run.py
    - scripts/paper_run_rates.json
    - scripts/PAPER_RUN.md
    - CHANGELOG.md
    - .planning/STATE.md
decisions:
  - "Budget reset is the first statement of create_run_state, before _resolve_pending_entries: reflector LLM spend now counts toward the run cap (old strand wiped it)"
  - "_run_graph always streams (stream_mode=values) so a budget abort has a last state to save; merged result equals invoke()"
  - "Ticker validation kept but rebuilt on upstream _run_directory: upstream already rejects before any disk write but only with a traceback; ours adds red message + exit 1"
  - "Paper-run rate table gains placeholder rates for upstream's new default models (gpt-5.6 family); a guard test ties the table to DEFAULT_CONFIG"
metrics:
  started: 2026-09-22T11:48:50Z
  completed: 2026-09-22T12:12:00Z
  duration: ~23 min
  tasks: 3
  commits_ahead_of_base: 17
---

# Quick 260922-iz5: Rebase strand onto upstream v0.5.0 (Summary)

The TradingEngineX strand now sits on upstream v0.5.0 (2d17df8) as 17 local commits on `rebase/upstream-v0.5.0`: 16 replayed from the old strand plus one docs commit. The budget (#582) was rebuilt on upstream's #1249 checkpoint lifecycle, and `stream_run` / `clear_run_checkpoint` are gone. Nothing was pushed, and `main`, `fork/main` and all tags are unchanged.

- **Worktree:** `C:/Users/admin/PycharmProjects/TradingEngineX-rebase-v050`
- **Branch:** `rebase/upstream-v0.5.0`, HEAD `164869abbac199aad99b7b29be56cece1abbf0dc`
- **Backup:** `backup/pre-rebase-v0.5.0` = `16bbe96658159721f7d084c22cc993de275e664e`
- **Pending operator approval:** promoting the branch to `main` and force-pushing `fork/main`. Neither was done.

## Before-snapshot (Step A)

Preconditions all held: `origin/main` = `v0.5.0^{commit}` = 2d17df8, `main` = `fork/main` = 16bbe96, the worktree path was absent, and neither new branch existed. `git -C MAIN status --porcelain` before the task:

```
 M .gitignore
 M .planning/STATE.md
?? .claude/
?? .idea/
?? .mcp.json
?? .planning/quick/260922-iz5-rebase-strand-onto-upstream-v0-5-0/
?? .serena/
?? CLAUDE.md
?? scripts/graphify.sh
?? uv.lock
```

`main` had not moved, so no extra main commits are left to replay.

## Old to new SHA mapping (BASE..HEAD)

| Old | New | How |
|---|---|---|
| e63c91e | 273ec0c | clean (docs) |
| c5407c7 | e61b174 | clean (docs) |
| a6f8581 | 79ff6e4 | CONFLICT, rebuilt on #1249 (see below) |
| 4a31720 | 6290e0e | CONFLICT (tests), both sides kept |
| e02fc88 | 2629505 | clean; the except clause and the import were picked up automatically |
| baf53d0 | 8239ada | CONFLICT, adapted to upstream `_run_directory` |
| 5452126 | 49951d6 | clean (docs) |
| 5912fb5 | ad28325 | clean (docs) |
| 3944ac3 | 801f7e0 | CONFLICT (CHANGELOG) |
| 8eaadf5 | 3c42285 | CONFLICT, shrunk (clear_run_checkpoint part dropped) |
| 402cd8b | **dropped** | empty from the start (`ci: trigger fork CI`); dropped via `--no-keep-empty` |
| 359bd03 | 843c433 | CONFLICT, shrunk (B904 parts already written; keeps the import sort and budget.py annotations) |
| ba576e3 | bc150f0 | clean (README) |
| 9916b84 | d9dc5fe | clean on replay, then a fixup was autosquashed in after a gate finding (pre-fixup SHA 09d66ef) |
| 6257535 | 6b46277 | clean (pre-autosquash 67bfe2d) |
| d6bd688 | d70ffa7 | clean (pre-autosquash acb1ff2) |
| 16bbe96 | 2014cb6 | clean (pre-autosquash 75c0b62) |
| (new) | 164869a | `docs(planning): rebase protocol for upstream v0.5.0` (Task 3) |

No commit was dropped automatically as an upstream duplicate or by resolution; 402cd8b is the only drop. Commit messages and authors are unchanged, as the plan requires. The messages of a6f8581/79ff6e4 and 8eaadf5/3c42285 still mention `stream_run` / `clear_run_checkpoint`; their diffs no longer contain them.

## Conflict resolutions (one line each)

- **a6f8581 `tradingagents/default_config.py`:** kept upstream's `max_tokens` and added our 3 budget keys (`max_cost_per_run`, `max_tokens_per_run`, `model_cost_rates`) before `checkpoint_enabled`.
- **a6f8581 `tradingagents/graph/trading_graph.py`:** upstream's file is the base, and its whole #1249 lifecycle, portfolio params and #1027 dedup are unchanged. On top of it:
  - the budget import;
  - `self.spend_tracker = build_spend_tracker(config)`, appended to callbacks before the LLM clients are built, plus a class-level default `spend_tracker = None`;
  - the reset as the first statement of `create_run_state`;
  - one `self.graph.stream` loop in `_run_graph`, with debug printing only when `self.debug` is set and `except BudgetExceededError -> _save_partial_state -> raise`;
  - a new helper, `_save_partial_state`.

  Our `stream_run` and `clear_run_checkpoint` were deleted.
- **a6f8581 `cli/main.py`:** upstream's #1249 block is kept verbatim. Added on top of it:
  - `except BudgetConfigError` around `TradingAgentsGraph(`;
  - `except BudgetExceededError` before upstream's `finally`, which records the abort, sets `graph.ticker` and calls `graph._save_partial_state(date, trace[-1] if trace else None)`;
  - upstream's completion block (agent statuses, "Completed analysis", report sections) now runs only when there was no abort;
  - after the Live block, the red message and `typer.Exit(1)`.

  Our `while True / next(stream)` loop and the `graph.stream_run(...)` call were dropped. No `--max-cost` flag was added.
- **a6f8581 `tests/test_budget.py`:** the stream_run tests were rewritten onto the new seat:
  - `_run_graph`: abort saves and re-raises; an abort before the first chunk saves None; success merges chunks and persists in the order `_log_state`, then `record_decision`, then `clear_checkpoint_on_success`.
  - `_save_partial_state`: mock-level tests plus one against the real `_log_state`.
  - `create_run_state`: reset per run, and reflection spend counts toward the new run.
  - A real-lifecycle integration test through `propagate()`: an abort keeps the checkpoint, and the resumed run completes and clears it.
  - CLI: the abort path, and BudgetConfigError exits with 1.

  The `clear_run_checkpoint` test was deleted; upstream's checkpoint tests cover `clear_checkpoint_on_success`.
- **a6f8581 `tests/test_memory_log.py`:** took upstream's file; the only change is the stub at about line 930, `graph.invoke.return_value` → `graph.stream.return_value = iter([fake_state])`.
- **a6f8581 `tests/test_portfolio_context.py` (not in the plan, see Deviations):** same one-line stub change `invoke` → `stream` in `test_completed_run_clears_the_checkpoint_it_wrote`. The assertion is unchanged.
- **4a31720 `tests/test_structured_agents.py`:** kept upstream's 5 new tests and our `_sample_plan` + `TestRetryThenFallback` (4 tests); there were no identical duplicates. `structured.py` applied as-is, since upstream did not change it between a33fd4c and 2d17df8.
- **baf53d0 `cli/main.py`:** instead of a second `safe_ticker_component` call, upstream's `results_dir = _run_directory(...)` (cli/main.py:995 at BASE) is wrapped in `try/except ValueError`, which prints a red "Invalid ticker" message and exits 1. Our old `Path(config["results_dir"]) / selections["ticker"] / ...` line was not restored.
- **3944ac3 `CHANGELOG.md`:** "## [Unreleased] — TradingEngineX strand (rebased onto v0.5.0)" goes directly above `## [0.5.0] — 2026-09-18`, and the intro now says "ported onto upstream v0.5.0". The "Shared `stream_run()` path" bullet was dropped. The budget, structured-retry and fail-fast bullets were kept (9916b84 later adds the paper-run bullet and fixes the `--max-cost` wording). The Fixed bullet was reworded to what our kept code does: a clean error and exit 1 instead of a traceback. Upstream's sections are byte-identical.
- **8eaadf5 (all 3 files):** took HEAD's versions and re-applied the intent by hand:
  - `_save_partial_state` became best-effort (`try/except Exception` + `logger.exception`) and never masks the abort;
  - the CLI message no longer promises a saved state;
  - new tests: "a failed persistence keeps the checkpoint", "budget abort survives a real partial-save failure", "a failing save is swallowed", and "an early-abort state is swallowed by the real `_log_state`".

  The `clear_run_checkpoint` part was dropped: upstream's `clear_checkpoint_on_success` runs after persistence in both `_run_graph` and the CLI, and bbcd666 removes the SQLite sidecars.
- **359bd03 `cli/main.py`:** the `MissingAPIKeyError` import goes to its sorted place before `tradingagents.portfolio`. The second hunk took HEAD (empty), so our old `results_dir = Path(...)` line did not come back.
- **9916b84 fixup (gate finding, see Deviations 5):** added `gpt-5.6`, `gpt-5.6-terra` and `gpt-5.6-luna` placeholder rates to `scripts/paper_run_rates.json`. The `RATES` fixture in `tests/test_daily_paper_run.py` is now keyed by `DEFAULT_CONFIG`'s models, and a new guard test checks the committed table against the default models.

## Deliberate behaviour changes

1. **The budget reset now happens before the reflector.** `create_run_state` resets the SpendTracker as its first statement, before `_resolve_pending_entries` (trading_graph.py:566-567). The reflection LLM calls that settle a ticker's earlier decisions now count toward the run's cap; in the old strand, the reset in `stream_run` came after reflection and wiped that spend. For the paper run, this means the per-ticker cost figure and `PAPER_RUN_MAX_COST` now include reflection.
2. **`_run_graph` always streams and never calls `invoke`.** The non-debug path uses `graph.stream` (stream_mode="values"), and the merged result equals invoke's. This is needed so that a budget abort has a last state to save.
3. **A rejected CLI ticker gives a clean error.** A ticker like `..` produces a red "Invalid ticker" message and exit code 1 instead of upstream's raw ValueError traceback. Upstream still validates before any disk write.

## Findings (checked, no upstream change made)

- `ensure_api_key` also writes the key to `os.environ` (cli/utils.py:672 at HEAD), so fail-fast cannot fire right after a successful prompt.
- `factory._required_env_vars` still resolves against upstream's registry: `api_key_env.PROVIDER_API_KEY_ENV` has the same anthropic/google/azure entries, bedrock is `None` (excluded), and the model-list refreshes are in `model_catalog.py` only. `tests/test_api_key_failfast.py` is green.
- The paper-run script is compatible with v0.5.0. It calls `graph.propagate(ticker, trade_date)` positionally, stores a `REVIEW` signal as an opaque string, and its trade date is always the previous weekday, which passes `_validate_trade_date`.

## Gate results (verbatim tails; all gates re-run on the final HEAD 164869a)

**G0 import sanity: PASS**
```
C:\Users\admin\PycharmProjects\TradingEngineX-rebase-v050\tradingagents\__init__.py
C:\Users\admin\PycharmProjects\TradingEngineX-rebase-v050\cli\__init__.py
```

**G1 `PYTHONPATH=. PY -m pytest -q`: FAIL as written (4 failed), with the same 4 failures as pristine upstream v0.5.0**
```
FAILED tests/test_no_data_handling.py::TestLoadOhlcvNoPoison::test_empty_download_raises_and_does_not_cache
FAILED tests/test_ohlcv_cache_freshness.py::test_current_day_cache_past_ttl_is_not_fresh
FAILED tests/test_ohlcv_cache_freshness.py::test_a_download_from_an_earlier_day_is_not_fresh
FAILED tests/test_ohlcv_cache_freshness.py::test_load_ohlcv_refetches_stale_same_day_cache
4 failed, 1024 passed, 5 skipped, 22 warnings, 88 subtests passed in 15.41s
```
Baseline on pristine BASE, taken from a `git archive 2d17df8` export and run with the same venv:
```
4 failed, 939 passed, 5 skipped, 22 warnings, 88 subtests passed in 16.65s
```
Root causes, both environmental and both upstream:
- **3× `test_ohlcv_cache_freshness`:** the test writes mtimes from a naive timestamp read as UTC, while `_cache_is_fresh` reads them back via `pd.Timestamp.fromtimestamp` in local time (CEST here). Under `TZ=UTC0` they pass.
- **`test_no_data_handling`:** makes a real reachability probe to query2.finance.yahoo.com, which fails from this machine.

Environment-adjusted run on HEAD:
```
TZ=UTC0 ... pytest -q --deselect tests/test_no_data_handling.py::TestLoadOhlcvNoPoison::test_empty_download_raises_and_does_not_cache
1027 passed, 5 skipped, 1 deselected, 22 warnings, 88 subtests passed in 13.73s
```
Our changes add 85 tests (1028 vs 943 collected), all passing.

**G2 `RUFF check .`: PASS**
```
All checks passed!
```
Also clean with `--target-version py310` on our files. No noqa or ignores were added. The intermediate commit 2629505 (e02fc88) carries an I001 import-order issue that 843c433 (359bd03) fixes, the same as in the original history; HEAD is clean.

**G3 paper run without credentials: PASS**
```
preflight: credentials missing for provider 'openai': OPENAI_API_KEY
paper-run: 2 ticker(s) AAPL, MSFT on 2026-09-21 | provider=openai deep=gpt-5.6 quick=gpt-5.6-luna | budget $1.50/ticker, $3.00 total
rc=20
```
Without `--preflight`:
```
error: missing credentials for provider 'openai': OPENAI_API_KEY
paper-run: 2 ticker(s) AAPL, MSFT on 2026-09-21 | provider=openai deep=gpt-5.6 quick=gpt-5.6-luna | budget $1.50/ticker, $3.00 total
rc=1
```
`test ! -e .env` held in WT, and the temp out/state dirs contained 0 files afterwards. Before the rate-table fixup, the real rates file lacked gpt-5.6/gpt-5.6-luna and this gate would have returned rc=1 instead of 20. Workflow mapping in `.github/workflows/daily-paper-run.yml`, lines 121-133:
```
          rc=$?
          set -e
          if [ "$rc" -eq 20 ]; then
            # No key configured yet: skip instead of crying wolf every morning.
            # The warning keeps it visible without a permanently red schedule.
            echo "::warning title=Paper run skipped::No provider credentials configured - add the API key secret to enable the daily run."
            ...
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi
```

**G4 structural invariants: PASS**, with one justified file outside the allowlist
```
pyproject identical rc=0
deleted: []
empty commits: 0 of 17
removed-dep imports: []
outside allowlist: tests/test_portfolio_context.py
```
`tests/test_portfolio_context.py` is the one-line invoke→stream stub change (+2/-1 via numstat). Upstream test files carry only stub edits or pure additions: test_memory_log 3/1, test_portfolio_context 2/1, test_structured_agents 101/0.

**G5 outward invariants: PASS**
```
main=16bbe96658159721f7d084c22cc993de275e664e fork/main=16bbe96658159721f7d084c22cc993de275e664e
tag refs unchanged (13 v* tags; v0.5.0 at BASE)
```
The MAIN porcelain is identical to the before-snapshot. No push command was run. The only writes to MAIN were `git branch backup/pre-rebase-v0.5.0` and `git worktree add`.

**Plan verify commands:**
- Task 1: every step passed except its pytest step, which stopped on the paper-run fixture failures fixed by the fixup; after the fixup the targeted files pass.
- Task 2 and Task 3, as written: rc=1, only because of the G1 environment failures above.
- The same chains with `TZ=UTC0` and the network probe deselected: rc=0.

## Deviations from Plan

1. **[Rule 3 - Blocking] A second upstream test edit.** Upstream's `tests/test_portfolio_context.py::test_completed_run_clears_the_checkpoint_it_wrote` stubs `graph.invoke`; once `_run_graph` streams, that test raised AttributeError. The fix is the same one-line stub change as in test_memory_log (invoke→stream), with the assertion unchanged. The plan allowed only the test_memory_log edit.
2. **[Rule 3 - Blocking] Class default `spend_tracker = None` on TradingAgentsGraph.** Upstream tests build graphs with `object.__new__` and call the real `create_run_state` (test_cli_decision_log, test_portfolio_context). Without the default they would hit AttributeError on the new reset line.
3. **[Rule 1 - Bug] The CLI partial save needs `graph.ticker`.** Upstream's CLI never sets `graph.ticker` (only `propagate` does), so `_log_state` → `safe_ticker_component(None)` would always fail on the CLI abort path. The CLI abort handler now sets `graph.ticker = selections["ticker"]` before `_save_partial_state`.
4. **[Rule 1 - Bug] The CLI completion block after an abort.** Upstream's post-stream block reads `final_state`, which is unbound after an abort, so that block now runs only without an abort. Otherwise a NameError would have replaced the budget message.
5. **[Rule 1 - Bug, gate finding] The paper-run rate table did not cover the new default models.** Upstream v0.5.0 moved the defaults from gpt-5.5/gpt-5.4-mini to gpt-5.6/gpt-5.6-luna. Neither `scripts/paper_run_rates.json` nor the test fixture priced them, so the scheduled paper run would have exited 1 (red) every morning, and 6 paper-run tests failed. The fix was folded into the paper-run commit via `git commit --fixup=09d66ef` + `GIT_EDITOR=true git rebase --autosquash --no-keep-empty 2d17df8`. It adds placeholder rates using the same tier values as the old defaults (still `_verified: never`), a fixture that follows `DEFAULT_CONFIG`, and a guard test (red before the table fix, green after). All gates were re-run afterwards.
6. **[Rule 2] Extra coverage for the rebuilt paths.** Added CLI-level budget tests and a real-lifecycle integration test (checkpoint kept on abort, resume clears it), because the CLI path and the checkpoint interplay were rebuilt, not just moved.
7. **Adapted rather than kept verbatim.** The ticker validation now wraps upstream's `_run_directory` instead of duplicating it, and the CHANGELOG Fixed bullet was reworded to match.

## Known Stubs

- `scripts/paper_run_rates.json`: every rate is an operator placeholder by design (`"_verified": "never - placeholder values"`). This includes the new gpt-5.6-family entries and was already an open operator task.

## Deferred Issues

- 4 upstream tests fail on this machine for environmental reasons (see G1). They are not caused by this task and are identical on pristine v0.5.0. Upstream CI runs in UTC with network and is not affected. A candidate upstream report is to make the freshness test timezone-independent and to mock `vendor_reachable` in test_no_data_handling.

## Open decisions for the operator

1. Approve promoting `rebase/upstream-v0.5.0` (164869a) to `main` and force-pushing `fork/main`. `backup/pre-rebase-v0.5.0` holds the old strand.
2. Verify or replace the placeholder rates for gpt-5.6 / gpt-5.6-terra / gpt-5.6-luna, or pin the models via the `TRADINGAGENTS_*_THINK_LLM` repo variables. Note that the per-ticker cap now also covers reflection calls (behaviour change 1).

## Self-Check: PASSED

- The worktree, branch HEAD 164869a, backup branch at 16bbe96, and every new SHA in the mapping (273ec0c … 2014cb6, 164869a) exist in `git log 2d17df8..HEAD`.
- The WT working tree is clean; there is no SUMMARY inside WT; `main` = `fork/main` = 16bbe96.
- This SUMMARY and the PLAN are left uncommitted in the main repo for the orchestrator.
