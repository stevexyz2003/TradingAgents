# State: retention, backup and recovery — operating manual

Companion to `scripts/PAPER_RUN.md`. That one covers the daily run; this one
covers what the run leaves on disk: the decision log (the track record), the
per-ticker SQLite checkpoints, the report tree and the caches.

Every claim here carries a `file:line` reference, measured against `main` on
2026-10-11, so a later reader can check it instead of trusting it.

| | |
|---|---|
| Tool | `scripts/state_maintenance.py` (`verify` / `prune` / `backup`) |
| Tests | `tests/test_state_maintenance.py` |
| Authoritative copy of the track record | branch `paper-log` |

## Where state lives

The decision log exists in **two different places**, and they are not the same
file:

| Context | Path | Source |
|---|---|---|
| CLI / library default | `~/.tradingagents/memory/trading_memory.md` | `tradingagents/default_config.py:86` |
| Scheduled paper run | `<state_dir>/decision-log.md` | `scripts/daily_paper_run.py:223` |

For the scheduled run `state_dir` is `$RUNNER_TEMP/paper-state`
(`.github/workflows/daily-paper-run.yml:101`) — ephemeral on the runner, which
is why the branch `paper-log` is restored before and committed after every run
(`daily-paper-run.yml:144`, `:194-211`).

`state_dir` is **not a config key.** `DEFAULT_CONFIG` has no `state_dir`;
`daily_paper_run.build_config` composes `memory_log_path` from it per run
(`daily_paper_run.py:223`). That is why `state_maintenance.py backup` requires
`--state-dir` explicitly instead of guessing a default — a guessed default would
either archive nothing or archive a directory nobody asked for.

Everything else:

| What | Path | Source |
|---|---|---|
| Checkpoints (opt-in `--checkpoint`) | `~/.tradingagents/cache/checkpoints/<TICKER>.db` | `graph/checkpointer.py:19-25`, `default_config.py:85` |
| Per-run reports | `~/.tradingagents/logs/<TICKER>/<date>/reports/*.md` | `cli/run.py:180-193` |
| Tool/message log of a run | `~/.tradingagents/logs/<TICKER>/<date>/message_tool.log` | `cli/run.py:153` |
| The pipeline's own state log | `~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json` | `graph/trading_graph.py:530` |
| Consolidated report tree | `~/.tradingagents/logs/reports/<TICKER>_<YYYYmmdd>_<HHMMSS>/` | `trading_graph.py:307` |
| Data caches (OHLCV, SEC EDGAR) | `~/.tradingagents/cache/` | `default_config.py:85` |
| Last CLI selections | `~/.tradingagents/cli_prefs.json` | `cli/prefs.py:28,57` |
| Paper-run archive | `<state_dir>/runs/<date>/`, `<state_dir>/index.md` | `daily_paper_run.py:323-331`, `:490` |

In CI there are **never** any checkpoints: the paper run sets
`checkpoint_enabled = False` hard (`daily_paper_run.py:226`). Checkpoint hygiene
is a local-workstation topic only.

## Sidecars

Files that appear beside the ones above and surprise people:

| Sidecar | When it exists | Source |
|---|---|---|
| `<log>.lock` | on every single log write | `memory/log.py:46,156,211` → `dataflows/files.py:37` |
| `<log>.settle.lock` | only once a settlement pass actually starts | `log.py:72`, `memory/settlement.py:158-170` |
| `decision-log.tmp` / `trading_memory.tmp` | during an atomic rewrite | `log.py:198,252` |
| `<name>.<uuid32>.tmp` | during a cache/prefs replace | `files.py:24` |
| `<TICKER>.db-wal`, `<TICKER>.db-shm` | only while a checkpoint connection is open | `checkpointer.py:45,51` |

Three details worth knowing:

* The rewrite temp is **`decision-log.tmp`, not `decision-log.md.tmp`**:
  `Path.with_suffix(".tmp")` *replaces* the extension (`log.py:198`).
* An empty log never produces a `.settle.lock`. `settle_all_pending` iterates
  the pending entries first and only calls `settle_pending` for those
  (`settlement.py:165-166`); with nothing pending the lock file is never
  created. Verified on `paper-log`: `decision-log.md.lock` is in the tree,
  `.settle.lock` is not.
* The checkpoint `-wal`/`-shm` files exist only while a connection is open and
  are gone after `conn.close()` (`checkpointer.py:51`). So they only ever
  survive a **crash** — which is exactly why `clear_all_checkpoints` globs
  `{db.name}-*` (`checkpointer.py:80`) and why `state_maintenance.py prune`
  uses the same glob.

## Retention

| State | Retention | Enforced by |
|---|---|---|
| Decision log | **unlimited**, never trimmed automatically | nothing — by decision |
| Checkpoints | **7 days** | `state_maintenance.py prune` (`--checkpoint-days`) |
| Report directories | **90 days** | `state_maintenance.py prune` (`--report-days`) |
| Workflow artifact `paper-run-<n>` | **90 days** | `daily-paper-run.yml:192` |

**What this table does not cover.** `prune` touches exactly two places:
`<cache>/checkpoints` and the direct children of `<results_dir>/reports`. So
"report directories 90 days" means the *consolidated* tree only — the per-run
tree (`logs/<TICKER>/<date>/reports/*.md`, `message_tool.log`,
`full_states_log_<date>.json`), both data caches and `cli_prefs.json` have **no
retention and no automatic cleanup**. They grow with every run. That is a
deliberate gap, not an oversight: the per-run tree is what a human reads when
reconstructing a single decision, and no measurement exists yet for how much it
grows per month. Delete it by hand (`rm -rf ~/.tradingagents/logs/<TICKER>`) or
file an extension of `prune` once the growth is known.

The decision log is kept forever on purpose: it is the track record and the
basis of the alpha evaluation. A trimmed log silently changes every aggregate
computed over it, and the past-context injection that feeds earlier lessons back
into later analyses reads the same file.

**The honest limitation on "90 days".** Those 90 days are the retention of the
*workflow artifact* only (`daily-paper-run.yml:192`). `runs/<date>/summary.json`,
`runs/<date>/<TICKER>.md` and `index.md` are committed to `paper-log`
**permanently** (`daily_paper_run.py:323-331`, `:490`) and keep growing. Order of
magnitude: ~3 KB per decision-log entry, so ≈190 KB per month at three tickers
over 21 trading days. "Unlimited" is uncritical for years; it is not "nothing
accumulates".

## Rotation

`memory_log_max_entries` exists and is tested (`log.py:273-308`,
`tests/test_memory_log.py:322-368`): when set, the oldest *resolved* entries are
dropped on the next rewrite, pending ones never. But it defaults to `None`
(`default_config.py:90`), it has **no `TRADINGAGENTS_*` override** (it is absent
from `_ENV_OVERRIDES`, `default_config.py:10-34`), and the paper run does not set
it (`daily_paper_run.py:210-227`). Rotation is therefore permanently off in
production and can only be switched on in code.

**`state_maintenance.py` deliberately has no `rotate` subcommand.** The
retention decision "the decision log is unlimited and never trimmed
automatically" is the more specific one and wins; rotation stays an operator
opt-in in code. That is a decision, not a gap.

## Backup

```bash
python scripts/state_maintenance.py backup \
  --out ~/backups --state-dir ~/.tradingagents/paper-state
```

It writes `<out>/tex-state-<YYYYmmddTHHMMSSZ>.tar.gz`, all members under one
top-level directory, from an **explicit allow-list**:

* `<state-dir>/decision-log.md`
* `<state-dir>/index.md`
* `<state-dir>/runs/**`
* the CLI log `--memory-log` (default `~/.tradingagents/memory/trading_memory.md`)

`*.lock`, `*.tmp` and `*.db` are excluded. There is **no directory sweep**: a
state directory in a real deployment sits next to `.env` files and keys, and a
sweep would pack them. `--out` and `--state-dir` are both required; without
either the tool prints which flag is missing and returns 1.

Checkpoints are **not** in the backup. They are 7-day resume points, not a
record; restoring one buys nothing a fresh run does not also buy.

The authoritative copy of the track record is not this archive — it is the
branch `paper-log`. The archive is for the local workstation, where no branch
is pushed.

## Recovery

**A checkpoint database is corrupt or suspect.** Throw it away:

```bash
rm ~/.tradingagents/cache/checkpoints/AAPL.db \
   ~/.tradingagents/cache/checkpoints/AAPL.db-wal \
   ~/.tradingagents/cache/checkpoints/AAPL.db-shm
# or, across all tickers:
tradingagents --clear-checkpoints
```

Then run again. The loss is exactly one resume point.

**Not `.recover`.** `.recover` is a command of the `sqlite3` *shell*, not of
Python's `sqlite3` module, and that binary is present neither on this
workstation nor inside the image (both checked). Repairing a 7-day resume point
would also be work for nothing.

**The decision log is lost or broken.** It is plain markdown and the
authoritative copy is the branch:

```bash
git fetch fork paper-log
git checkout fork/paper-log -- decision-log.md
```

Then check it:

```bash
python scripts/state_maintenance.py verify \
  --memory-log <state_dir>/decision-log.md
```

Two things about that check:

* A log restored this way counts as **intact even without a trailing
  `<!-- ENTRY_END -->`**. `verify` compares non-empty blocks against
  `TradingMemoryLog.load_entries()`, not separator counts — counting separators
  would report a problem that is not there on exactly this recovery path, and
  would hide a real one in the other direction. A block whose tag line has
  fewer than four fields is dropped *silently* by the parser (`log.py:310-341`);
  the block comparison is the only way to see it.
* "I can query the file" is **not** an integrity check. During research the same
  corrupt database answered `select count(*) from checkpoints` with `1`. That
  is why `verify` runs `PRAGMA quick_check` inside `try/except
  sqlite3.DatabaseError` — on a corrupt image the pragma *raises* (`database
  disk image is malformed`; on a garbage header `file is not a database`), so a
  comparison against the returned row never sees anything — and additionally
  requires both tables `checkpoints` and `writes`.

`verify` returns `0` when everything is clean, `2` on any finding, `1` on a
usage error.

## Concurrency and locking

What exists (more than one would assume):

| Mechanism | Source |
|---|---|
| Cross-process lock on every log write (`fcntl.flock` / `msvcrt.locking`) | `log.py:46,156,211` → `files.py:37-88` |
| Separate settlement lock, taken `wait=False` from the graph | `log.py:72`, `settlement.py:120`, `trading_graph.py:343` |
| Atomic rewrites (temp file + `replace`) | `log.py:198,252`, `files.py:14-32` |
| Idempotency: no second entry for the same ticker+date | `log.py:46-55` |

What is missing, and must be known before running two things at once:

1. **Checkpoints have no application-level lock.** Only SQLite's own, and the
   connection runs with `check_same_thread=False` (`checkpointer.py:45`). Two
   concurrent runs on the same ticker+date+signature share both the `.db` *and*
   the `thread_id` (`checkpointer.py:28-38`) — expect `database is locked` or
   interleaved writes. The per-ticker database isolates *different* tickers,
   which is all its docstring claims (`checkpointer.py:3`).
2. **`clear_all_checkpoints` deletes across all tickers, unguarded**
   (`checkpointer.py:68-82`). While another run holds its checkpoint, that
   destroys its resume. `--clear-checkpoints` (`cli/main.py:41-43,75-78`) is a
   maintenance command, not a routine one.
3. **The paper run is serialized only by the GitHub `concurrency` group**
   (`daily-paper-run.yml:58-59`). There is no lock on `paper-log` itself. A
   second writer from another workflow would fail at the non-fast-forward
   `push`, so the failure mode is a *lost* run, not a corrupted log.
4. `get_pending_entries()` is read **outside** any lock in `settle_all_pending`
   (`settlement.py:165`). Harmless — the pass re-reads under the lock — but
   worth knowing when reading the code.
5. **`.lock` files are never deleted** and accumulate one per log path. And
   `decision-log.md.lock` currently sits *committed* on `paper-log`, because the
   state commit uses `git add -A .` without an exclude
   (`daily-paper-run.yml:203`).
   **Status: open, cosmetic — documented, not fixed.** The production path gets
   no new moving parts by operator decision. The fix, when it is wanted, is a
   `.gitignore` inside the state directory or an exclude on that `git add`.

## Commands

```bash
# Integrity: every checkpoint DB plus the decision log. 0 = clean, 2 = finding.
python scripts/state_maintenance.py verify

# Expired checkpoints (7 d) and report directories (90 d).
# DRY RUN by default - it prints what it would delete and deletes nothing.
python scripts/state_maintenance.py prune
python scripts/state_maintenance.py prune --apply

# Archive the track record (allow-list; --out and --state-dir are required).
python scripts/state_maintenance.py backup --out ~/backups --state-dir <state_dir>
```

All paths are overridable: `--cache-dir`, `--results-dir`, `--memory-log`,
`--checkpoint-days`, `--report-days`. The tool is deliberately **not** wired
into the daily paper run — that path runs unattended and gets no new moving
parts.

## See also

* `scripts/PAPER_RUN.md` — the daily run itself.
* `scripts/smoke/docker_smoke.sh` — the end-to-end smoke: one real CLI run
  *through the Docker image* against a stub LLM on an `--internal` network, so
  it proves image, entrypoint, paths/permissions and the whole LLM client chain
  without an API key and without reaching the internet. It runs in CI as the job
  `docker-smoke`. It proves plumbing, not analysis quality: inside the isolated
  network every data vendor degrades to `DATA_UNAVAILABLE`.
