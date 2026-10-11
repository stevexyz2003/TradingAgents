---
phase: quick-261010-raj
plan: 01
subsystem: strand-maintenance
tags: [rebase, upstream-v0.6.0, budget, structured-retry, per-tier-providers, paper-run]
requires: [upstream v0.6.0 1394a3f, strand cc6a5dc]
provides: [branch rebase/upstream-v0.6.0 @a6a06b2, backup/pre-rebase-v0.6.0 @cc6a5dc]
affects:
  - tradingagents/graph/trading_graph.py
  - cli/run.py
  - tradingagents/agents/structured.py
  - tradingagents/llm_clients/factory.py
  - scripts/daily_paper_run.py
  - tests/test_budget.py
tech-stack:
  added: []
  patterns:
    - budget reset in create_run_state, settlement spend counted via in-graph _memory_step
    - one _run_graph loop over upstream's stream_run with merged-accumulator partial save
    - structured retry seated in upstream's invoke_structured (Portfolio Manager included)
    - BudgetExceededError re-raised ahead of upstream's broad except in _memory_step and invoke_structured
key-files:
  created: []
  modified:
    - cli/run.py
    - tradingagents/agents/structured.py
    - tradingagents/graph/trading_graph.py
    - tradingagents/llm_clients/factory.py
    - tradingagents/default_config.py
    - tradingagents/budget.py
    - scripts/daily_paper_run.py
    - scripts/paper_run_rates.json
    - scripts/PAPER_RUN.md
    - tests/test_budget.py
    - tests/test_structured_agents.py
    - tests/test_api_key_failfast.py
    - tests/test_daily_paper_run.py
    - tests/test_memory_log.py
    - tests/test_portfolio_context.py
    - tests/test_cli_symbol_handling.py
    - CHANGELOG.md
    - README.md
    - .planning/STATE.md
decisions:
  - "The CLI halves moved from cli/main.py to cli/run.py; cli/main.py is byte-identical to upstream v0.6.0"
  - "The #583 retry was re-applied in upstream's invoke_structured, not in the wrapper, so the Portfolio Manager's direct caller gets it too"
  - "_save_partial_state takes the ticker as an argument: upstream removed self.ticker and self.curr_state, so last round's graph.ticker workaround is obsolete"
  - "A budget abort is re-raised ahead of the broad except in _memory_step (settlement now runs inside the graph) and in invoke_structured"
  - "The worktree got its own venv: the main tree's .venv cannot even import tradingagents on v0.6.0 (yfinance 0.2.63 < 1.7.0)"
metrics:
  started: 2026-10-10T17:55:00Z
  completed: 2026-10-10T18:45:00Z
  duration: ~50 min
  tasks: 3
  commits_ahead_of_base: 19
---

# Quick 261010-raj: Rebase strand onto upstream v0.6.0 (Summary)

The TradingEngineX strand now sits on upstream v0.6.0 (`1394a3f`) as 19 local commits: all 18 replayed from `cc6a5dc` plus one docs commit. No commit was dropped. Our features were re-seated onto v0.6.0's new structure — the CLI run path (`cli/run.py`), the new structured-output module (`tradingagents/agents/structured.py`), in-graph settlement (`_memory_step`) and upstream's own `stream_run`. Nothing was pushed; `main`, `fork/main` and all 16 tags are unchanged, and the main tree's `.venv` was never touched.

- **Worktree:** `C:/Users/admin/PycharmProjects/TradingEngineX-rebase-v060` (own venv at `.venv/`)
- **Branch:** `rebase/upstream-v0.6.0`, HEAD `a6a06b23394210aa4249208353750b5973dab553`
- **Backup:** `backup/pre-rebase-v0.6.0` = `cc6a5dc8aa3c61d86cab970bae8d41bed5b77b68`
- **Base:** `1394a3f72aa4393e1a98f51b382434c4b4c2d972` (origin/main == `v0.6.0^{commit}`), 135 upstream commits over 2d17df8
- **Pending operator approval:** promoting the branch to `main` and force-pushing `fork/main`. Neither was done; no push command was run at any point.

## Before-snapshot (Step A)

All preconditions held: `origin/main` = `v0.6.0^{commit}` = `1394a3f72aa4393e1a98f51b382434c4b4c2d972`, `main` = `fork/main` = `cc6a5dc`, the worktree path was absent, and neither `backup/pre-rebase-v0.6.0` nor `rebase/upstream-v0.6.0` existed (`backup/pre-rebase-v0.3.1` and `backup/pre-rebase-v0.5.0` were present and stayed). `main` had not moved, so there are no extra main commits left to replay.

`git -C MAIN status --porcelain` before the task:

```
 M .gitignore
?? .claude/
?? .idea/
?? .mcp.json
?? .planning/quick/261010-raj-rebase-strand-onto-upstream-v0-6-0/
?? .serena/
?? CLAUDE.md
?? scripts/graphify.sh
?? uv.lock
```

The only two commands that wrote to the main repo were `git branch backup/pre-rebase-v0.6.0 cc6a5dc` and `git worktree add -b rebase/upstream-v0.6.0 ...`.

Plan correction: the plan expected 14 `v*` tags; there are **16** (`v0.1.0 … v0.5.2 v0.6.0`, incl. `v0.2.5-tex`). The invariant that matters — unchanged, no new tag — holds.

## Worktree venv (Step B2)

The plan's environment finding was confirmed: a pristine v0.6.0 export cannot run in the main tree's venv. The worktree's own venv was created with the main tree's interpreter (`python -m venv`, Python 3.13.15) and installed with `pip install -e ".[dev]"`; `pip check` is clean. Resolved versions (audit list; zero new package names, all are upstream v0.6.0's own dependency list):

```
pandas==3.0.6            langgraph==1.2.14              langgraph-checkpoint-sqlite==3.1.1
langchain-core==1.6.9    langchain-openai==1.7.0        langchain-anthropic==1.7.5
langchain-google-genai==4.4.0   yfinance==1.7.0         markdown-it-py==4.2.0
ruff==0.17.0             pytest==9.1.1                  pytest-subtests==0.15.0
tradingagents==0.6.0 (editable, from the worktree)
```

The install was re-run after the autosquash so v0.6.0's own pins are provably satisfied (`tradingagents` went 0.5.0 → 0.6.0 in the second run; `pip check`: `No broken requirements found.`).

## Pristine v0.6.0 baseline (Step B3)

Taken from a `git archive 1394a3f` export outside both repos, with the worktree venv, **before** the rebase:

```
1 failed, 1258 passed, 4 skipped, 1 deselected, 20 warnings, 99 subtests passed in 21.69s
FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
```

With `TZ=UTC0`, identical (`1 failed, 1258 passed, ...`). Root cause, environmental and upstream's own test:

```
assert not Path(_TzDBManager.get_location()).is_relative_to(Path.home())
E  AssertionError: assert not True
E   where True = WindowsPath('C:/Users/admin/AppData/Local/Temp/tradingagents-tests-yf-...').is_relative_to(WindowsPath('C:/Users/admin'))
```

On Windows `TEMP` lives under `Path.home()`, so the test's "cache is outside the user's home" assertion can only hold on POSIX. Upstream CI runs on Linux and is unaffected. **Good news vs. the v0.5.0 round:** the 3 timezone failures and the Yahoo-reachability failure are gone (v0.6.0 mocks `vendor_reachable` and the freshness test was fixed), so the bar is one platform-specific test instead of four.

## Old → new SHA mapping (18 commits + 1 new)

| Old | New | How |
|---|---|---|
| 273ec0c | `5b33523` | clean (docs) |
| e61b174 | `300c99d` | clean (docs) |
| 79ff6e4 | `865c3aa` | CONFLICT (4 files), core rebuild on v0.6.0 — see below |
| 6290e0e | `b72e61f` | CONFLICT, re-applied in upstream's new module |
| 2629505 | `981726e` | CONFLICT (factory import + cli/main.py), CLI half re-seated |
| 8239ada | `7917437` | CONFLICT, re-seated to `cli/run.py`; + a new test (fixup, pre-fixup SHA b205724) |
| 49951d6 | `6e57326` | clean (docs) |
| ad28325 | `2459103` | clean (docs) |
| 801f7e0 | `8f42d9a` | applied without a textual conflict but at the WRONG anchor; re-anchored via fixup (pre-fixup SHA ec63460) |
| 3c42285 | `49db463` | CONFLICT, **shrunk** to two tests |
| 843c433 | `6ff160f` | CONFLICT, **shrunk** to the `budget.py` annotations |
| bc150f0 | `a46e865` | clean (README) |
| d9dc5fe | `7a96f46` | clean on replay, then a fixup for three gate findings (pre-fixup SHA 58d2207) |
| 6b46277 | `9e0824b` | clean (docs) |
| d70ffa7 | `c6c849f` | clean (CI) |
| 2014cb6 | `d53b790` | clean (CI) |
| 164869a | `ca2c219` | clean (docs) |
| cc6a5dc | `855ee08` | clean (docs) |
| (new) | `a6a06b2` | `docs(planning): rebase protocol for upstream v0.6.0` (Task 3) |

**Dropped: none.** `--no-keep-empty --empty=drop` dropped nothing (the only empty commit of the strand was already dropped in the v0.5.0 round), and no commit became an upstream duplicate. 0 of 19 commits in `1394a3f..HEAD` are empty. Every message and author is unchanged. Note that the messages of `865c3aa` and `49db463` still mention `stream_run` / `clear_run_checkpoint` as *our* code; their diffs do not — upstream owns both names now.

**Shrunk, with reasons:**
- `843c433` (style/ruff): only the `budget.py` annotations survive. Its other half was moving the `MissingAPIKeyError` import in `cli/main.py` — that import now lives in `cli/run.py`, already in isort's place.
- `3c42285` (robust partial-save): its best-effort `_log_state` and the reworded CLI message were landed directly in `865c3aa` (as the plan allowed), so it shrank to its two remaining `_run_graph` robustness tests.

## Conflict resolutions (one line each)

- **865c3aa `tradingagents/default_config.py`** — kept all of upstream's new keys (per-tier provider/backend_url, `holding_period_days`, `_ENV_OVERRIDES`) and added our 3 budget keys before `checkpoint_enabled` inside `build_default_config()`; dropped nothing of upstream's.
- **865c3aa `tradingagents/graph/trading_graph.py`** — upstream's file is the base and its whole lifecycle (`propagate`/`run_config`, `begin/end_checkpoint`, `_memory_step`, `settle_all_pending`, `stream_run`, `record_decision`, `_log_state`, `run_rating` return) is verbatim. Added on top: the budget import (:13), class default `spend_tracker = None`, `build_spend_tracker` appended to `self.callbacks` before `extra` is computed (:79-87), the reset as the first statement of `create_run_state` (:320-321), one stream loop in `_run_graph` with `except BudgetExceededError` (:419-433), `_save_partial_state` (:442-470), and `except BudgetExceededError: raise` in `_memory_step` (:347). Dropped: our old `curr_state` write (upstream removed the attribute).
- **865c3aa `cli/main.py`** — took upstream's file unchanged; all of our hunks moved to `cli/run.py`. `git diff BASE HEAD -- cli/main.py` is empty, as the plan required.
- **865c3aa `cli/run.py`** (new seat, not a conflict) — upstream's stream/checkpoint block kept verbatim including `trace`, `record_decision`, `clear_checkpoint_on_success` and `finally: graph.end_checkpoint()`. Added: `except BudgetConfigError` around the construction (:127-135), `except BudgetExceededError` before upstream's `finally` (:375-385), the completion block gated on no-abort, and the red message + `typer.Exit(1)` after the Live block (:408-418). No `--max-cost` flag was added.
- **865c3aa `tests/test_budget.py`** — rewritten onto the new seats: `stream_run` yields `(messages, state)` pairs; `_save_partial_state` has 3 args; `_log_state` is now called by upstream's `record_decision`, so the "persists in order" test asserts `record_decision` → `clear_checkpoint_on_success`; `_run_graph` returns `run_rating` instead of `process_signal`. New tests: the save gets the merge and not the last chunk, a budget abort escapes `_memory_step`, an ordinary settlement failure is still only noted. The real-lifecycle integration test through `propagate()` was kept and re-stubbed onto `graph.stream`.
- **865c3aa `tests/test_memory_log.py`** — upstream's file; one stub line, `mock_graph.graph.invoke.return_value` → `mock_graph.stream_run.return_value = iter([([], fake_state)])` (+3/-1). Assertions untouched.
- **865c3aa `tests/test_portfolio_context.py`** — upstream's file; the faked `.graph` gained a `stream` generator yielding `((), "values", state)` instead of `invoke` (+5/-1), because `_run_graph` now goes through the real `stream_run` (`subgraphs=True`, list `stream_mode`, and the generator needs a `.close()`). Assertions untouched.
- **b72e61f `tradingagents/agents/structured.py`** — accepted upstream's deletion of `agents/utils/structured.py` (git tracked it as a rename into the new module). Kept upstream's `invoke_structured_or_freetext` verbatim and re-applied our feature inside `invoke_structured`: `_with_error_context` (:34), `_invoke_parsed` (:79), one retry with the error-context prompt, and `except BudgetExceededError: raise` at both stages (:110, :119). The free-text fallback still receives the ORIGINAL prompt.
- **b72e61f `tests/test_structured_agents.py`** — kept upstream's version (new import path, `judge_decision` dropped) and re-added our `_sample_plan` + `TestRetryThenFallback` with the new import; purely additive (+130/-0). No duplicates existed.
- **981726e `tradingagents/llm_clients/factory.py`** — the only conflict was the import block (`import os` + `get_api_key_env` vs. upstream's `from typing import Any`); merged both. `MissingAPIKeyError`, `_required_env_vars` and the `_validate_credentials(...)` call stay inside `create_llm_client` (:94); upstream's `build_llm_kwargs`, `tier_provider` and `create_tier_client` are untouched.
- **981726e `cli/run.py`** — the construction handler became `except (BudgetConfigError, MissingAPIKeyError)`; `README.md` auto-merged (purely additive, +30/-0).
- **7917437 `cli/run.py`** — upstream's `results_dir = _run_directory(...)` call wrapped in `try/except ValueError` with the red "Invalid ticker" message and `raise typer.Exit(1) from None` (:143-149). Upstream still validates before any disk write but only raises a bare `ValueError` — no user-facing message anywhere in `cli/main.py` (its `except ValueError` handlers cover `load_portfolio` and `parse_analysts` only), so our half was kept.
- **8f42d9a `CHANGELOG.md`** — our `## [Unreleased] — TradingEngineX strand (rebased onto v0.6.0)` section now sits directly above `## [0.6.0] — 2026-10-03`, intro "ported onto upstream v0.6.0". Upstream's sections are byte-identical (`git diff BASE HEAD -- CHANGELOG.md` has **0 deleted lines**). No bullet was dropped: upstream owns none of the four features.
- **49db463** — see "shrunk" above; the surviving tests are `test_a_failed_persistence_keeps_the_checkpoint` (now injecting the failure in `record_decision`, which is where upstream persists) and `test_budget_abort_survives_a_real_partial_save_failure`.
- **6ff160f `cli/main.py`** — HEAD's version taken (the import move is obsolete); `budget.py` annotations kept.

## The three re-applications (host code upstream removed)

### 1. #583 structured retry → `tradingagents/agents/structured.py`

Upstream deleted `tradingagents/agents/utils/structured.py` and split the helper into `invoke_structured` (returns the parsed object or `None`) and `invoke_structured_or_freetext`. The retry went into **`invoke_structured`** (:90-127), not the wrapper, because v0.6.0's Portfolio Manager calls `invoke_structured` directly (`tradingagents/agents/managers/portfolio_manager.py:80`) — seating the retry in the wrapper would have left that agent without it. Net effect: the retry now covers *more* callers than before.

**Verified by:** `tests/test_structured_agents.py::TestRetryThenFallback::test_invoke_structured_itself_retries_with_error_context`, `::test_invoke_structured_gives_up_after_one_retry`, `::test_invoke_structured_never_swallows_a_budget_abort` (new, for the direct seat) plus the five ported wrapper tests `::test_retry_succeeds_with_error_context_str_prompt`, `::test_double_failure_falls_back_with_original_prompt`, `::test_list_prompt_retry_appends_user_message_without_mutation`, `::test_budget_exceeded_propagates_without_retry`, `::test_budget_exceeded_on_retry_propagates_without_fallback`. Upstream's own `test_invoke_structured_falls_back_when_result_is_none` still passes unchanged (both attempts return `None`, then prose).

**Could not preserve:** nothing of the behaviour. One wording change only: upstream's first warning said "retrying once as free text"; it now says "retrying once with error context", which is what actually happens.

### 2. CLI ticker-validation message + `BudgetExceededError` handler → `cli/run.py`

`cli/main.py` is a 160-line typer shell in v0.6.0 with no graph construction, so both halves moved to `cli/run.py`: the construction guard at :127-135, the ticker message at :143-149 (now *outside* the `Live` block, simpler than the v0.5.0 seat and the message is visible on a normal screen), the abort handler at :375-385, and the red budget message + `typer.Exit(1)` at :408-418.

**Verified by:** `tests/test_cli_symbol_handling.py::test_the_cli_reports_a_rejected_ticker_instead_of_a_traceback` (new: drives the real `run_analysis` with ticker `..`, asserts exit code 1, "Invalid ticker" on stdout and that no results directory was created) and `tests/test_budget.py::TestCliBudget::test_cli_abort_saves_partial_state_and_skips_record_and_clear` / `::test_cli_budget_config_error_exits_before_the_run` (patch target `cli.run`).

**Could not preserve:** nothing. Two deliberate improvements over a literal port: the abort handler passes the **merged** `trace` instead of `trace[-1]` (a last chunk can be a single analyst's partial report, which `_log_state` would reject), and it no longer sets `graph.ticker` — upstream removed `self.ticker`/`self.curr_state` and `_log_state` reads `final_state["company_of_interest"]`, so last round's Rule-1 workaround is obsolete. `_save_partial_state` takes the ticker as its first argument instead (only for the log line).

### 3. Budget re-raise through v0.6.0's `_memory_step` and `invoke_structured`

v0.6.0 moved settlement+reflection into the graph as `_memory_step`, whose `try` around `settle_all_pending(wait=False)` ends in `except Exception` — it would have logged a `BudgetExceededError` as a settlement failure and let the run continue spending. `except BudgetExceededError: raise` now sits ahead of that broad handler (`tradingagents/graph/trading_graph.py:347`). The same guard is in `invoke_structured` at both attempt stages (`structured.py:110`, `:119`).

**Verified by:** `tests/test_budget.py::TestSpendTrackerReset::test_a_budget_abort_escapes_the_memory_step` (the abort propagates and the memory log is never read) and `::test_an_ordinary_settlement_failure_is_still_only_noted` (a `RuntimeError` still only produces a `memory_note`, so the guard did not turn transient failures into aborted runs); plus `::test_invoke_structured_never_swallows_a_budget_abort` for the structured path.

**Could not preserve / deliberately not done:** the guard was added only to `_memory_step`'s **first** `try`. The second one wraps `memory_log.get_past_context`, which is a markdown-file read with no LLM call (`tradingagents/memory/log.py:93`), so a `BudgetExceededError` cannot originate there; adding a dead handler would have been noise. Noted here so a future change to `get_past_context` revisits it.

## Deliberate behaviour changes

1. **Settlement spend counts toward the cap, structurally.** The reset is still the first statement of `create_run_state` (`trading_graph.py:320-321`), but v0.6.0 settles past decisions *inside* the graph (`_memory_step`, #1428/#1445) instead of before the run. The reflection LLM calls therefore always fall inside the run's budget window — the v0.5.0 strand had to order the reset carefully to get this; now it is a property of upstream's layout. For the paper run, the per-ticker cost figure and `PAPER_RUN_MAX_COST` keep including reflection.
2. **`_run_graph` always streams, through upstream's own `stream_run`.** Upstream's debug/else split (`stream_run` for debug, `graph.invoke` otherwise) collapsed into one loop so an abort always has state to save. The #1027 message dedup stays gated on `self.debug`. Because `stream_run` interleaves full run states with single analysts' partial reports, the saved state is the merged accumulator, never one chunk. The merged result equals `invoke()`'s — upstream's `test_memory_log`, `test_portfolio_context`, `test_checkpoint_lifecycle` and `test_graph_end_to_end` all pass.
3. **A rejected CLI ticker gives a clean error.** `..` produces a red "Invalid ticker" message and exit code 1 instead of a raw `ValueError` traceback. Upstream still rejects it before any disk write.
4. **Scheduled runs settle every ticker.** Not our change, but it makes a documented limitation false — see the PAPER_RUN.md correction in Task 3.

## Gate results (verbatim; all re-run on the final HEAD `a6a06b2`)

**G0 import sanity: PASS**
```
C:\Users\admin\PycharmProjects\TradingEngineX-rebase-v060\tradingagents\__init__.py
C:\Users\admin\PycharmProjects\TradingEngineX-rebase-v060\cli\__init__.py
0.6.0
```

**G1 differential pytest: PASS** (`PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`)
```
FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
1 failed, 1353 passed, 4 skipped, 1 deselected, 20 warnings, 99 subtests passed in 21.54s
```
Baseline (pristine v0.6.0, same venv, captured before the rebase):
```
FAILED tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home
1 failed, 1258 passed, 4 skipped, 1 deselected, 20 warnings, 99 subtests passed in 21.69s
```
`diff baseline-failed.txt final-failed.txt` → empty, i.e. **the FAILED sets are identical**. Side by side: passed 1353 vs 1258 (**+95 tests from our changes**; 1358 vs 1263 collected), skipped 4 vs 4, deselected 1 vs 1, subtests 99 vs 99, failed 1 vs 1. `TZ=UTC0` on HEAD is the same single failure (`1 failed, 1352 passed ...` on the pre-fixup HEAD, `1 failed, 1353 passed` after), so it is not timezone-dependent — it is `Path.home()` containing `TEMP` on Windows. Not reported upstream; a candidate report is to skip or relocate that assertion on Windows.

**G2 ruff: PASS**
```
All checks passed!
```
Also `All checks passed!` with `--target-version py311` explicitly. `ruff 0.17.0` (v0.6.0's CI requires >=0.16; the main tree's 0.15.12 was not used). No `noqa` and no ignore was added; the four UP017 findings (`datetime.UTC`) in our paper-run files were fixed, not suppressed.

**G3 paper run without credentials: PASS**
```
preflight: credentials missing for provider 'openai': OPENAI_API_KEY
paper-run: 2 ticker(s) AAPL, MSFT on 2026-10-09 | provider=openai deep=gpt-6-sol quick=gpt-6-luna | budget $1.50/ticker, $3.00 total
rc=20
```
Without `--preflight`:
```
error: missing credentials for provider 'openai': OPENAI_API_KEY
paper-run: 2 ticker(s) AAPL, MSFT on 2026-10-09 | provider=openai deep=gpt-6-sol quick=gpt-6-luna | budget $1.50/ticker, $3.00 total
rc=1
```
`test ! -e .env` held in the worktree; both runs used `mktemp -d` directories outside both repos and left **0 files** behind (`find "$T" -type f | wc -l` → `0`). Every provider key var was unset via `env -u` (including `ZHIPU_API_KEY`, which is the name v0.6.0's registry actually uses — the plan's `ZHIPUAI_API_KEY` is stale; both were unset). Workflow mapping, `.github/workflows/daily-paper-run.yml:121-134`:
```
          rc=$?
          set -e
          if [ "$rc" -eq 20 ]; then
            # No key configured yet: skip instead of crying wolf every morning.
            # The warning keeps it visible without a permanently red schedule.
            echo "::warning title=Paper run skipped::No provider credentials configured - add the API key secret to enable the daily run."
            {
              echo "### Paper run skipped"
              echo ""
              echo "No provider credentials configured. Add the API key as a repository secret (see \`scripts/PAPER_RUN.md\`)."
            } >> "$GITHUB_STEP_SUMMARY"
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi
```

**G4 structural invariants: PASS, with one documented exception to the file allowlist**
```
pyproject.toml + tradingagents/__init__.py identical to BASE: rc=0
deleted BASE..HEAD: []
cli/main.py changed: []
tradingagents/agents/utils/structured.py at HEAD: absent (OK)
empty commits: 0 of 19
removed-dep imports: []
agents.utils.structured in tradingagents/cli/scripts/tests: []
conflict markers at HEAD: []
```
Changed non-`.planning` files vs BASE: `.github/workflows/daily-paper-run.yml`, `cli/run.py`, `scripts/PAPER_RUN.md`, `scripts/daily_paper_run.py`, `scripts/paper_run_rates.json`, `tests/{test_api_key_failfast,test_budget,test_cli_symbol_handling,test_daily_paper_run,test_memory_log,test_portfolio_context,test_structured_agents}.py`, `tradingagents/agents/structured.py`, `tradingagents/budget.py`, `tradingagents/default_config.py`, `tradingagents/graph/trading_graph.py`, `tradingagents/llm_clients/factory.py`, plus `CHANGELOG.md`, `README.md` and `.planning/**`. `cli/main.py` is absent from that list, as required.

- **Outside the plan's allowlist:** `tests/test_cli_symbol_handling.py` (+26/-0, purely additive) — the new CLI ticker-validation test, justified under Deviations 4.
- Upstream test files carry only stub edits or additions: `test_memory_log` +3/-1, `test_portfolio_context` +5/-1, `test_structured_agents` +130/-0, `test_cli_symbol_handling` +26/-0.

**G4 exception, reported as a partial fail:** the gate as literally written (`test -z "$(git grep -n 'agents.utils.structured' HEAD)"`) **does not pass**. There are 13 hits across 6 files, all of them in archived `.planning/` documents (the 260814-k1j plan/research/summary/verification, the 260922-iz5 plan, and the new 2026-10-10 protocol entry, which names the old path to say where the retry moved *from*). There are **zero** hits in `tradingagents/`, `cli/`, `scripts/` or `tests/` — no stale import anywhere in code. The archived documents are dated records of the pre-v0.6.0 layout and the plan forbids rewriting them, so they were left alone.

**G5 outward invariants: PASS**
```
main=cc6a5dc8aa3c61d86cab970bae8d41bed5b77b68 fork/main=cc6a5dc8aa3c61d86cab970bae8d41bed5b77b68
16 v* tags (v0.1.0 … v0.5.2 v0.6.0); v0.6.0 -> 1394a3f72aa4393e1a98f51b382434c4b4c2d972
branches: backup/pre-rebase-v0.3.1, backup/pre-rebase-v0.5.0, backup/pre-rebase-v0.6.0, rebase/upstream-v0.6.0
```
`git -C MAIN status --porcelain` is byte-identical to the before-snapshot (the operator's `.gitignore` modification and the 7 untracked entries, plus this task's own quick-task directory). No push command was run.

**G6 environment invariant (main tree's venv untouched): PASS**
```
pandas 2.3.0
yfinance 0.2.63
langgraph==0.4.8
langchain-core==1.3.2
ruff==0.15.12
tradingagents==0.2.4
```
Exactly the pre-task state. Every `pip`, `pytest`, `ruff` and `python` invocation of this task used `TradingEngineX-rebase-v060/.venv`; the main interpreter was used once, for `python -m venv`.

**Plan verify commands:**
- Task 1 `<automated>`: rc=0 (all structural checks + `pip check` + the 8 targeted test files + the log listing).
- Task 2 `<automated>`: every step passes **except** the literal `agents.utils.structured` grep described above, which makes the chained command return rc=1. Re-run without that one step: rc=0.
- Task 3 `<automated>`: rc=0.
- Targeted set on the final HEAD: `304 passed in 14.60s`.

## Findings (checked, no upstream change made)

- **`ensure_api_key` still exports the key.** It moved from `cli/utils.py` to `cli/prompts.py:627`, and it still writes `os.environ[env_var] = key` at **`cli/prompts.py:681`** before returning, so our fail-fast validation cannot fire right after a successful prompt. The 2026-09-22 STATE citation `cli/utils.py:672` was stale and has been corrected.
- **`_required_env_vars` still matches upstream's registry.** `tradingagents/llm_clients/api_key_env.py:14-34` has the same `anthropic → ANTHROPIC_API_KEY`, `google → GOOGLE_API_KEY`, `azure → AZURE_OPENAI_API_KEY` entries and `bedrock: None` (excluded). Side note for the Anthropic follow-up: the registry now names GLM's variable `ZHIPU_API_KEY`/`ZHIPU_CN_API_KEY`, not `ZHIPUAI_API_KEY`.
- **Fail-fast does cover per-tier providers.** `create_tier_client` (`factory.py:201-209`) resolves the tier's provider and calls `create_llm_client(provider=..., ...)`, which runs `_validate_credentials` at `factory.py:94`. A deep tier on Anthropic with no `ANTHROPIC_API_KEY` therefore fails at graph construction even when `llm_provider` is OpenAI. Covered by the new `tests/test_api_key_failfast.py::TestPerTierProviders` (3 cases).
- **Gap, NOT implemented (belongs to the Anthropic follow-up):** the paper run's own preflight checks only `config["llm_provider"]` — `provider = config["llm_provider"]; absent = missing_credentials(provider)` at `scripts/daily_paper_run.py:371-372`. With v0.6.0's per-tier providers a tier's key could be missing and the preflight would still report rc=0; the run would then fail later at graph construction (exit 1) rather than being skipped with rc=20.
- **`scripts/daily_paper_run.py` is otherwise compatible with v0.6.0.** `graph.propagate(ticker, trade_date)`, `graph.save_reports(final_state, ticker, out_dir/...)` (v0.6.0's new `html=True` default now also writes `complete_report.html` into the artifact), `getattr(graph, "spend_tracker", None)` and `ensure_rates_configured(...)` all still resolve. Trade dates are always the previous weekday, which passes `_validate_trade_date`.

## Deviations from Plan

1. **[Rule 3 - Blocking, gate finding] `scripts/daily_paper_run.py` imported a module upstream deleted.** `from tradingagents.dataflows.utils import safe_ticker_component` → upstream moved it to `tradingagents.dataflows.symbols`. Our file applied cleanly (it is ours alone), so nothing conflicted — but `tests/test_daily_paper_run.py` could not even be collected (`ModuleNotFoundError: No module named 'tradingagents.dataflows.utils'`) and the scheduled run would have died on import every morning. Fixed and folded into the paper-run commit (`--fixup=58d2207` + non-interactive autosquash).
2. **[Rule 1 - Bug, gate finding] The rate table did not price v0.6.0's default models.** Upstream's defaults are now `gpt-6-sol` / `gpt-6-luna`. Added placeholder entries (`{"input": 5.0, "output": 40.0}` and `{"input": 1.0, "output": 8.0}`, the table's flagship/luna tiers), kept all existing entries and the honest `"_verified": "never - placeholder values, see _note"` marker, and added no Anthropic rates. Red before, green after: `tests/test_daily_paper_run.py::TestRates::test_the_committed_table_prices_the_default_models`. Same fixup.
3. **[Rule 1 - Bug, gate finding] UP017 in our paper-run files.** v0.6.0 targets py311 and ruff >=0.16, so `datetime.timezone.utc` is now a lint error. Rewritten to `datetime.UTC` in `scripts/daily_paper_run.py` (3 sites) and `tests/test_daily_paper_run.py` (1 site) via `ruff check --fix` on those two files only. Same fixup. The py310 constraint from the v0.5.0 round is obsolete.
4. **[Rule 2] A third upstream test file was touched, additively.** The orchestrator required a named test for each re-application, and the CLI ticker-validation message had none (the original `8239ada` shipped without one; upstream's `tests/test_cli_symbol_handling.py::test_the_run_directory_cannot_escape_the_results_directory` covers only the `ValueError`). Added `test_the_cli_reports_a_rejected_ticker_instead_of_a_traceback` to that same file (+26/-0, no upstream assertion changed) and folded it into the ticker commit (`--fixup=b205724` + autosquash). The plan's G4 allowlist did not list this file.
5. **[Rule 1 - Bug] `801f7e0`'s CHANGELOG hunk applied silently at the wrong anchor.** Git replayed it without a textual conflict, placing our `## [Unreleased]` section *below* `## [0.6.0]`, `[0.5.2]` and `[0.5.1]` — exactly where the v0.5.0 anchor used to be — and the header/intro still said v0.5.0. Re-anchored directly above `## [0.6.0] — 2026-10-03` with the v0.6.0 wording via `--fixup=ec63460`. The autosquash then conflicted twice (the fixup's context carried later commits' bullets); both were resolved so each commit keeps only its own delta: `8f42d9a` has the section with the original `--max-cost` wording, `a46e865`/`7a96f46` still apply their own corrections and the paper-run bullet on top.
6. **[Rule 1 - Bug] `_save_partial_state` signature and the dropped `curr_state`.** The plan specified `_save_partial_state(self, trade_date, last_state)` setting `self.curr_state` "as upstream's own code does". Upstream v0.6.0 has **no** `curr_state`, no `self.ticker`, no `log_states_dict` and no `process_signal` — `_log_state` reads `final_state["company_of_interest"]`. Reintroducing those attributes would have been dead state, so the method is `_save_partial_state(self, company_name, trade_date, last_state)` and the CLI no longer needs the `graph.ticker = ...` workaround that the v0.5.0 round had to add.
7. **[Rule 1 - Bug] The CLI abort saves the merged trace, not `trace[-1]`.** The plan specified `trace[-1] if trace else None`. With upstream's `stream_run`, the last chunk can be one analyst's partial report, which `_log_state` rejects — the best-effort save would then have written nothing. The handler merges `trace` first.
8. **[Rule 2] Extra coverage for the re-seated paths.** New tests beyond a literal port: the merged-accumulator save, the `_memory_step` budget escape and its negative case, `invoke_structured`'s own retry/limit/budget behaviour, the three per-tier fail-fast cases, and the CLI ticker message. Our changes now add 95 tests over pristine v0.6.0.
9. **`.planning/MILESTONE.md` left unchanged** (the plan's default expectation). Its statements are explicitly dated snapshots of the v0.2.x milestone ("letzter verifizierter Lauf: **2026-08-14** … `108 passed`"); none of them became false *because of* v0.6.0, so nothing was rewritten.
10. **`.planning/STATE.md`'s Quick-Tasks table has no `261010-raj` row.** Task 3's instructions enumerate the five edits to make and the table is not among them; the row belongs with the PLAN+SUMMARY commit the orchestrator makes. Flagged so it is not forgotten.

## Known Stubs

- `scripts/paper_run_rates.json`: every rate is an operator placeholder by design (`"_verified": "never - placeholder values, see _note"`). The new `gpt-6-sol` / `gpt-6-luna` entries are the minimum the guard test demands and are deliberately conservative (over-estimating trips the budget early). Verifying or replacing them is an existing operator task, and the Anthropic follow-up will add real Claude prices.

## Deferred Issues

- `tests/test_suite_isolation.py::test_yfinance_keeps_its_cache_out_of_the_users_home` fails on this machine for a platform reason and fails identically on pristine v0.6.0 (see G1). Not caused by this task. Candidate upstream report: on Windows the temp directory is a child of `Path.home()`, so the assertion needs a different "outside the user's home" definition or a platform skip.
- The paper run's preflight does not check per-tier provider credentials (`daily_paper_run.py:371-372`). Deliberately not implemented here — it belongs to the Anthropic provider switch.
- The literal G4 grep for `agents.utils.structured` still matches six archived `.planning/` documents (see G4).

## Open decisions for the operator

1. **Approve promoting `rebase/upstream-v0.6.0` (`a6a06b2`) to `main` and force-pushing `fork/main`.** Nothing was pushed. `backup/pre-rebase-v0.6.0` holds the old strand at `cc6a5dc`; the older backup refs and all 16 tags are untouched.
2. **The paper-run rate table** still carries placeholder prices, now including `gpt-6-sol` / `gpt-6-luna`. Verify them against the provider's list, or pin the models via the `TRADINGAGENTS_*_THINK_LLM` repo variables — and note that the per-ticker cap also covers the settlement/reflection calls, which v0.6.0 now runs inside every run for *every* pending ticker, not just the analyzed one.
3. **Before the Anthropic switch:** the paper-run preflight only validates `config["llm_provider"]`'s key. If the follow-up puts the deep tier on Anthropic and the quick tier elsewhere, extend `missing_credentials` to the resolved per-tier providers, or the morning run will exit 1 instead of being skipped with rc=20.
4. **The worktree and its venv** (`TradingEngineX-rebase-v060`, ~1 GB with `.venv`) are still on disk, kept so the gates stay reproducible. Remove with `git worktree remove --force TradingEngineX-rebase-v060` once the branch is promoted.

## Self-Check: PASSED

- Worktree, branch and HEAD verified: `rebase/upstream-v0.6.0` at `a6a06b23394210aa4249208353750b5973dab553`, 19 commits over `1394a3f`, `git merge-base --is-ancestor` true, no rebase in progress, working tree clean.
- Every new SHA in the mapping (`5b33523 … 855ee08`, `a6a06b2`) exists in `git log 1394a3f..HEAD`; `backup/pre-rebase-v0.6.0` resolves to `cc6a5dc8aa3c61d86cab970bae8d41bed5b77b68`.
- Claimed files exist at HEAD: `tradingagents/agents/structured.py`, `cli/run.py`, `scripts/paper_run_rates.json` (with both `gpt-6-*` keys), `.planning/STATE.md` (with `Rebase-Protokoll (2026-10-10)`); `tradingagents/agents/utils/structured.py` is absent.
- No SUMMARY or PLAN inside the worktree; the final commit touches only `.md` files and carries the `Co-Authored-By: Claude Opus 5 (1M context)` trailer.
- `main` = `fork/main` = `cc6a5dc`; this SUMMARY and the PLAN are left uncommitted in the main repo for the orchestrator.
