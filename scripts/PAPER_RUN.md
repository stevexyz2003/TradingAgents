# Daily paper run — operating manual

The scheduled paper run is the **heartbeat** of this strand: every trading
morning it analyzes a short ticker list, records the decision, and turns red
when something breaks. It exists as much to keep the project moving as to
produce trading signals — a repository with a daily green check that goes red
on failure cannot quietly stall for three months.

It is **paper only**. Nothing here places, routes, or simulates orders; the
output is an analysis report and a rating (Buy / Overweight / Hold /
Underweight / Sell).

| | |
|---|---|
| Workflow | `.github/workflows/daily-paper-run.yml` |
| Runner | `scripts/daily_paper_run.py` |
| Rate table | `scripts/paper_run_rates.json` (operator-maintained) |
| Schedule | Tue–Sat 06:30 UTC — the morning after each US session |
| Per-run output | Workflow artifact `paper-run-<n>` (90 days) |
| Track record | Branch `paper-log`, kept forever |

## One-time setup

1. **Enable Actions in the fork** (Settings → Actions → General). Forks start
   with Actions disabled, and a fork's scheduled workflows only run once they
   are enabled.
2. **Add the provider secret** (Settings → Secrets and variables → Actions →
   *Secrets*), e.g. `OPENAI_API_KEY`. Until then the workflow ends green with
   a *"Paper run skipped"* warning — a missing key is a setup gap, not a
   failure, and a schedule that is red every morning stops being read.
3. **Set the repository variables** you want to deviate on (same page →
   *Variables*):

   | Variable | Default | Meaning |
   |---|---|---|
   | `PAPER_RUN_TICKERS` | `AAPL,MSFT,NVDA` | comma-separated, max 10 |
   | `PAPER_RUN_MAX_COST` | `1.50` | **hard** USD cap per ticker |
   | `TRADINGAGENTS_LLM_PROVIDER` | `openai` | any supported provider |
   | `TRADINGAGENTS_DEEP_THINK_LLM` | config default | the expensive model |
   | `TRADINGAGENTS_QUICK_THINK_LLM` | config default | the cheap model |
   | `TRADINGAGENTS_MAX_DEBATE_ROUNDS` | `1` | raise = better, pricier |

4. **Verify the rate table** in `scripts/paper_run_rates.json` against your
   provider's current price list. The values committed there are conservative
   **placeholders**, not quotes. This matters: the cap is enforced against
   *computed* cost, so wrong rates mean a wrong cap. Overestimating is the safe
   direction — the run then aborts early rather than overspending.
5. **Dry-run it once:** Actions → *Daily Paper Run* → *Run workflow* with
   `preflight_only = true`. That validates tickers, date, rate table and
   credentials without a single LLM call.

## What one run costs

`PAPER_RUN_MAX_COST` is per *ticker*; the day's ceiling is that times the
number of tickers, and the runner stops starting new tickers once the day's
ceiling is reached. With the defaults that is 3 × $1.50 = **$4.50 per day**,
roughly **$95 per month** at 21 trading days — the worst case, not the
expected spend. Pointing both `TRADINGAGENTS_*_THINK_LLM` variables at a small
model cuts it by an order of magnitude and is the right setting while you are
still tuning the cadence.

The cap is enforced check-before-spend by `SpendTracker` (#582): the run aborts
*before* the next LLM call once the accumulated cost exceeds the limit, the
partial state is saved, and the day is reported as `partial`.

## Reading the result

**Green** — every ticker analyzed. The job summary carries the per-ticker
table (signal, cost, tokens, duration).

**Red** — one of:

| Exit | Meaning | Usual fix |
|---|---|---|
| 1 | config error; nothing ran | rate table, ticker list, or credentials |
| 3 | a ticker failed at runtime | look at the traceback in the log — usually a data vendor |
| 4 | the budget aborted or skipped a ticker | raise `PAPER_RUN_MAX_COST` or use a cheaper model |

**Green with a warning** — no credentials configured; the run did nothing.

## Where the output lives

Per run, in the artifact:

```
summary.json            machine-readable result (schema_version 1)
summary.md              the job-summary table
reports/<TICKER>/       full markdown report tree, as the CLI writes it
logs/                   the pipeline's own per-run state JSON
```

Permanently, on the `paper-log` branch:

```
decision-log.md         the append-only decision log — the actual track record
index.md                one row per ticker run, all days
runs/<date>/summary.json
runs/<date>/<TICKER>.md the consolidated report
```

`decision-log.md` is the part that compounds. Each run appends its decision as
`pending`; a later run of the same ticker resolves it with the realized return
and alpha versus the benchmark, and feeds those reflections back into the next
analysis as past context. The branch is restored at the start of every run and
committed at the end, so the chain survives artifact expiry — and the daily
commit doubles as repository activity, which is what keeps GitHub from
disabling the cron after 60 idle days.

## Running it locally

```bash
python scripts/daily_paper_run.py \
  --tickers AAPL,MSFT \
  --date auto \
  --max-cost 1.50 \
  --out /tmp/paper-out \
  --state ~/.tradingagents/paper-state
```

Add `--preflight` to validate everything without spending anything. Point
`--state` at the same directory every time or the track record will not build
up. `--date auto` is the previous weekday; pass `YYYY-MM-DD` for a backfill.

## Known limitations

- **The reflection horizon collapses to about one trading day.** Upstream's
  `_fetch_returns` defaults to a five-day holding period but resolves as soon
  as two price bars exist, so with a daily cadence on the same tickers every
  entry is scored one day after the decision. The track record is therefore a
  1-day return series, not a 5-day one. Fixing it properly means requiring
  `len(bars) > holding_days` before resolving — an upstream-relevant change,
  deliberately not made here.
- **Exchange holidays are not modelled.** On a holiday the pipeline analyzes
  the last session's data; the run is green and the report shows it.
- **LLM output is not deterministic.** Two runs on the same date can disagree.
  That is a property of the framework, not a bug in the schedule.
- **One writer only.** The `concurrency` group serializes runs; a second
  concurrent writer to `paper-log` would lose a day's log.
