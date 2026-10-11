---
phase: 261011-k4s
reviewed: 2026-10-11T14:21:11Z
depth: quick
files_reviewed: 5
files_reviewed_list:
  - scripts/smoke/stub_llm.py
  - scripts/smoke/docker_smoke.sh
  - scripts/state_maintenance.py
  - tests/test_state_maintenance.py
  - .github/workflows/ci.yml
findings:
  critical: 2
  warning: 15
  info: 10
  total: 27
status: issues_found
---

# Phase 261011-k4s: Code Review Report

**Reviewed:** 2026-10-11T14:21:11Z
**Depth:** quick (escalated — see Summary)
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The requested depth was `quick`, but `scripts/state_maintenance.py` deletes files, so
pattern matching alone would have been worthless. The review therefore read all five files
in full, cross-read the library code they depend on (`tradingagents/graph/checkpointer.py`,
`tradingagents/memory/log.py`, `tradingagents/dataflows/symbols.py`,
`tradingagents/graph/trading_graph.py:303-307`, `langgraph/checkpoint/sqlite/__init__.py:134`,
`Dockerfile`, `.dockerignore`) and **executed five probes** against the real module to
confirm the destructive findings rather than assert them. Every finding marked "proven" below
was reproduced; findings without that word are code-reading conclusions and say so.

**Mid-review change.** `scripts/smoke/docker_smoke.sh` was edited on disk while this review ran
(uncommitted, working tree at the time of writing). The edit is a correct and valuable fix: the
old `printf '%s' "$NEG_OUT" | grep -Eq ...` inverted its own result under `set -o pipefail`
because `grep -q` exits on the first match, `printf` takes SIGPIPE (141), and `pipefail`
promotes that to the pipeline status — so `if !` fired exactly when the marker *was* found. It
also widened the marker list across langchain-openai versions. This review covers the **edited**
file: the finding about the duplicated marker list is retired (the edit removed the duplication),
and one new Warning (WR-15) applies to the replacement line, which reintroduces the same
pipe/SIGPIPE shape the new comment above it forbids. Line references for the smoke script are
against the working-tree version; everything outside lines 243-261 is unchanged from
`86ac1ae`.

Overall: the smoke harness is unusually well-reasoned (the `--internal` network, the
side-effect-free probe, the negative control that distinguishes exit 125 from a real
connection error, `ThreadingHTTPServer` with a measured justification). The destructive tool
is where the defects cluster: its guard rails are documented more thoroughly than they are
implemented. Two of them are exploitable by an ordinary filename or a mistyped flag, and both
end in deleting data the tool decided to keep.

Answers to the five directed questions are in **Directed Questions** at the end — including
three places judged **acceptable** rather than defective.

## Critical Issues

### CR-01: `prune --apply` deletes the WAL of a database it just decided to keep (unescaped glob)

**File:** `scripts/state_maintenance.py:215` (same construct at `:79`, read-only there)
**Issue:** The sidecar group is built by interpolating a filesystem-derived name into a glob
pattern: `cp_dir.glob(f"{db.name}-*")`. `db.name` comes from `cp_dir.glob("*.db")`, i.e. from
whatever is on disk — not from the validated ticker. Any glob metacharacter in that name
re-targets the pattern at *other* files. Proven:

```
# checkpoints/ contains backup[1].db (30 d old), backup1.db (fresh), backup1.db-wal (fresh)
$ state_maintenance.py prune --apply
  keep backup1.db (0.0 d old, limit 7 d)
  deleted backup[1].db, backup1.db-wal (30.0 d old, limit 7 d)
```

`backup1.db-wal` is the WAL of the database the previous line explicitly kept. In WAL mode
(`SqliteSaver.setup()` sets `PRAGMA journal_mode=WAL`) that file can hold the only copy of
committed rows, so this silently corrupts a surviving checkpoint — and the output *reads* as
if everything is fine. The same class of mistake lets the pattern match another `.db`
(`AAPL.db-old.db` is deleted as a sidecar of `AAPL.db`, bypassing its own age check).
The docstring's claim "same glob logic as `clear_all_checkpoints`" is accurate
(`checkpointer.py:80` has the identical bug), but `clear_all_checkpoints` deletes everything
anyway, so there it is latent; here it crosses the keep/delete boundary.
**Fix:** stop building patterns from names. Either escape, or match literally:

```python
import glob as _glob
# escape variant
group = [db, *(p for p in sorted(cp_dir.glob(f"{_glob.escape(db.name)}-*")) if not p.is_symlink())]
# or no glob at all (preferred — also fixes the read-only site at :79)
prefix = db.name + "-"
group = [db, *sorted(
    p for p in cp_dir.iterdir()
    if p.name.startswith(prefix) and p.is_file() and not p.is_symlink()
)]
```

### CR-02: negative `--checkpoint-days` / `--report-days` delete today's state

**File:** `scripts/state_maintenance.py:369-370` (no validation), consumed at `:201`, `:230`
**Issue:** `type=int` accepts negative values, which push the cutoff into the future, so
*every* candidate is "expired". The day limit is the only guard rail this tool has, and it has
no lower bound. Proven:

```
$ state_maintenance.py prune --apply --checkpoint-days -1 --report-days -1
  deleted AAPL.db, AAPL.db-wal (0.0 d old, limit -1 d)
  deleted AAPL_20261011_161925/ (name stamp: 2026-10-11, limit -1 d)
```

The second line is today's consolidated report tree — `rmtree`, irreplaceable analysis output
under a declared 90-day retention — removed by a sign typo (`--report-days -1`,
`--report-days=-90`). The dry-run default limits this to invocations that already pass
`--apply`, which is the documented operating mode in `STATE_OPERATIONS.md`, so it is one
keystroke from a real operator command.
**Fix:** reject the input before anything is scanned, in `main()`/`prune()`:

```python
for name, value in (("--checkpoint-days", checkpoint_days), ("--report-days", report_days)):
    if value < 0:
        print(f"FAIL: {name} must be >= 0, got {value} - refusing to delete anything")
        return EXIT_CONFIG
```

(An `argparse` `type=` callback that raises `ArgumentTypeError` works too and is caught by the
existing `SystemExit` translation in `main()`.)

## Warnings

### WR-01: the group's age is read off the `.db` only, so a crash-fresh WAL is pruned with a stale database

**File:** `scripts/state_maintenance.py:210-215`
**Issue:** `mtime = db.stat().st_mtime` decides the fate of the whole group, but in WAL mode
the main `.db` file is only touched on a checkpoint — which, per the project's own runbook
(`STATE_OPERATIONS.md:75-80`), happens on a clean `conn.close()`. So the exact case the
sidecar handling exists for — "`-wal`/`-shm` only ever survive a **crash**" — is the case
where the `.db` mtime is *older* than the data in the WAL. Proven:

```
# MSFT.db mtime = 10 days ago (last clean close), MSFT.db-wal written 1 minute ago
$ state_maintenance.py prune --apply
  deleted MSFT.db, MSFT.db-wal (10.0 d old, limit 7 d)
```

A one-hour-old crash recovery point is destroyed under a 7-day policy, and the printed age
(`10.0 d`) actively misleads the operator about what was just deleted.
**Fix:** age the group, not the file:

```python
group = [db, *sidecars]                      # build the group first
mtime = max(p.stat().st_mtime for p in group)
```

### WR-02: `REPORT_DIR_RE` is narrower than the validator that creates the names

**File:** `scripts/state_maintenance.py:55`
**Issue:** Report directories are named with `safe_ticker_component(ticker)`
(`trading_graph.py:307`), whose pattern is `^[A-Za-z0-9._\-\^=+]+$`
(`dataflows/symbols.py:152`). The prune regex only allows `[A-Za-z0-9._-]`, so `^`, `=` and
`+` are rejected. Those are not exotic — `^GSPC`, `^DJI`, `BTC=F`, `ES=F` are the standard
yfinance index/futures spellings this codebase handles. Proven:

```
'^GSPC_20200101_120000'   matches REPORT_DIR_RE: False
'BTC=F_20200101_120000'   matches REPORT_DIR_RE: False
'BRK-B_20200101_120000'   matches REPORT_DIR_RE: True
```

Consequence: those report trees are **never** pruned (90-day retention silently does not
apply to index/futures tickers, unbounded growth), and the output lies about why —
`keep ^GSPC_20200101_120000 (name is not <TICKER>_<YYYYmmdd>_<HHMMSS>)` when the name is
exactly that. The failure direction is safe (keeps data), which is why this is a Warning and
not a Blocker.
**Fix:** derive the class from the one source of truth instead of restating it:

```python
from tradingagents.dataflows.symbols import _TICKER_PATH_RE  # or re-export it publicly
REPORT_DIR_RE = re.compile(r"^[A-Za-z0-9._\-\^=+]+_(\d{8})_(\d{6})$")
```

and add a test with a `^GSPC_*` directory.

### WR-03: `verify` crashes instead of reporting a finding, and the crash exit code means the opposite

**File:** `scripts/state_maintenance.py:126` (`read_text`), `:78` (`copy2`), `:385-411` (no
top-level handler)
**Issue:** `check_decision_log` does `path.read_text(encoding="utf-8")` with no error
handling. A decision log that got mangled to invalid UTF-8 — a textbook corruption mode for
the one file this tool calls irreplaceable — produces a traceback, not a finding. Proven:

```
$ state_maintenance.py verify --memory-log <log with a stray 0xFF byte>
checkpoints: no directory at ... (nothing to check)
CRASH: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 44
```

Python exits 1, and the module docstring defines 1 as "usage/configuration error - nothing was
done" — so an automated caller reading the exit code concludes the *invocation* was wrong, not
the data. `shutil.copy2` at `:78` (vanished file, permission denied) and `shutil.rmtree` at
`:253` have the same exposure; the latter can leave a half-deleted report directory behind
while still exiting 1 ("nothing was done").
**Fix:** convert the expected failures into findings and backstop the rest:

```python
def check_decision_log(path):
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return f"not valid UTF-8: {exc}"
    except OSError as exc:
        return f"cannot read: {exc}"
```

and wrap the dispatch in `main()` so an unexpected `OSError` exits `EXIT_FINDING` (or a new
code) rather than the "nothing was done" code.

### WR-04: `check_decision_log` reads the log twice without the writer's lock (false FAIL)

**File:** `scripts/state_maintenance.py:126-135`
**Issue:** `blocks` is computed from the `text` read at `:126`; `entries` comes from
`load_entries()` (`memory/log.py:76-86`), which opens and reads the file **again**. Between
the two reads, `store_decision` can append — it takes `locked(self._log_path)`
(`memory/log.py:49`), a lock `verify` does not take. The paper run appending while a `verify`
runs therefore yields `len(entries) > len(blocks)` and a confident, wrong FAIL (exit 2) that
sends the operator into the recovery procedure for a healthy log. The message is also
nonsensical in that direction: it reads `only 3/2 blocks parsed as entries`.
**Fix:** one read, or the writer's lock:

```python
from tradingagents.memory.log import locked
with locked(path):
    text = path.read_text(encoding="utf-8")
    log = TradingMemoryLog({"memory_log_path": str(path)})
    entries = log.load_entries()
```

plus a direction-aware message (`len(entries) != len(blocks)` can now only mean a dropped
entry, but say which way it went).

### WR-05: the containment guard protects `unlink` and leaves `rmtree` unguarded

**File:** `scripts/state_maintenance.py:224-226` (missing), compare `:176-186`
**Issue:** `_checkpoint_dir` exists specifically so a symlinked `checkpoints` cannot let a
prune reach outside the directory it was pointed at — and it guards the *weaker* operation
(`unlink` of `*.db` + sidecars). `_prune_reports`, the only code path that calls
`shutil.rmtree`, has no equivalent: it does `Path(results_dir).resolve() / "reports"` and never
resolves or containment-checks `reports` itself, so `reports.is_dir()` happily follows a
symlink and `iterdir()` enumerates the target. The per-entry `is_symlink()` check at `:234`
does not help — it filters the *children*, not the parent. (Code reading only; not reproduced,
as creating directory symlinks needs elevation on this host.) The name regex still gates what
gets deleted, which caps the blast radius, so: Warning.
Flip side of the same inconsistency: a *legitimate* symlinked `checkpoints` (pointed at
another disk — an ordinary ops move) makes `prune` return `EXIT_CONFIG` and skip report
pruning entirely, so the whole command becomes a no-op with an error that reads like
misconfiguration.
**Fix:** give reports the same belt, and apply one policy to both paths:

```python
def _reports_dir(results_dir: str) -> Path | None:
    base = Path(results_dir).expanduser().resolve()
    reports = (base / "reports").resolve()
    return reports if base in reports.parents else None
```

### WR-06: `backup` claims "never a directory sweep" but sweeps `runs/**` with a suffix-only filter

**File:** `scripts/state_maintenance.py:294-296` (docstring), `:324-328` (implementation)
**Issue:** The docstring's security rationale is "An explicit allow-list, never a directory
sweep: the state directory of a real deployment sits next to secrets, and a sweep would pack
them." The top level honours that (two named files). `runs/` does not: `rglob("*")` takes every
file beneath it, and the only filter is `path.suffix not in (".lock", ".tmp", ".db")`. So
`runs/2026-10-09/.env` (`Path(".env").suffix == ""`), `token.json`, `id_rsa`, `creds.yaml` all
get packed — and `.db-wal` sidecars too, since `Path("x.db-wal").suffix` is `".db-wal"`, not
`".db"`. The test at `tests/test_state_maintenance.py:328` proves only that a secret at the
state-dir *root* stays out, which is the half the allow-list already covers.
Secondary: on Python 3.11/3.12 (both in the CI matrix) `rglob` follows symlinked directories —
that behaviour changed in 3.13 — so a symlink under `runs/` copies real file contents into the
archive on two of the four supported interpreters.
**Fix:** name the shapes you intend to archive and say so in the docstring:

```python
for pattern in ("runs/*/summary.json", "runs/*/*.md"):
    for path in sorted(state.glob(pattern)):
        if path.is_file() and not path.is_symlink() and _backup_included(path):
            members.append((path, path.relative_to(state).as_posix()))
```

and add a test with a secret *inside* `runs/<date>/`.

### WR-07: the smoke asserts an exact call count while leaving client-side retries at the default

**File:** `scripts/smoke/docker_smoke.sh:156-165` (main run), `:212` (assertion), compare
`:229` (negative control)
**Issue:** The negative control explicitly sets `TRADINGAGENTS_LLM_MAX_RETRIES=0`; the main run
does not. `llm_max_retries` defaults to `None` (`default_config.py:120`), so
`factory.py:182-184` never passes `max_retries` and `ChatOpenAI` keeps its own default of 2.
Any single transient failure during the parallel analyst burst (socket reset, the stub handler's
30 s timeout, a loaded runner) is retried transparently, the stub counts the retry, and
`test "$CALLS" -eq 9` turns the job red with a message pointing at an upstream rebase. The
comment at `:204-209` asserts that "more means a decider failed to parse the stub's arguments"
— that inference is only sound once retries are pinned.
**Fix:** one line in step 5, identical to the one the negative control already has:

```sh
  -e TRADINGAGENTS_LLM_MAX_RETRIES=0 \
```

### WR-08: step 8 and the image build have no timeout under a 10-minute job cap, and there is no layer cache

**File:** `scripts/smoke/docker_smoke.sh:88`, `:223-233`; `.github/workflows/ci.yml:53-63`
**Issue:** The `timeout 300` wrapper is applied only to the main CLI run. The `docker build`
(a full `pip install .` of the langchain/pandas/yfinance tree with no `cache-from`, rebuilt
from scratch on every runner) and the negative-control `docker run` are unbounded. Their
combined budget is the job's `timeout-minutes: 10`, which the SUMMARY itself flags as the
likely failure point ("lokal 49 s bei warmem Cache" — a cold runner is a different number). When
that cap trips, GitHub cancels the job: no `SMOKE FAIL:` line, no `docker logs`, no indication
of which step was slow.
**Fix:** budget each long step so the failure is attributable, e.g.
`"${TIMEOUT[@]}" docker build ...` and reuse `"${TIMEOUT[@]}"` on the negative control; raise
`timeout-minutes` to ~20; optionally add a registry/gha layer cache.

### WR-09: the INT/TERM trap cleans up but does not exit, so Ctrl-C resumes the script

**File:** `scripts/smoke/docker_smoke.sh:82`
**Issue:** `trap teardown INT TERM EXIT` runs `teardown` and returns control to the statement
after the interrupted command. Containers and network are gone by then, so the script carries
on against nothing: the next `docker` call fails, `set -e` exits, and the EXIT trap re-runs
teardown. Cleanup does end up complete (the stated goal holds), but the operator sees a
spurious docker error instead of an interrupt, and the exit status is 1 rather than 130. If the
interrupt lands between `docker build` and `docker network create`, a second Ctrl-C is needed.
**Fix:** make the signal handlers terminal and keep EXIT for the normal path:

```sh
trap teardown EXIT
trap 'teardown; exit 130' INT
trap 'teardown; exit 143' TERM
```

### WR-10: `"${TIMEOUT[@]}"` breaks the advertised developer caller on macOS

**File:** `scripts/smoke/docker_smoke.sh:151-156`
**Issue:** The header states "One script, two callers: a developer with Docker, and the CI job".
Under `set -u`, expanding an **empty** array as `"${arr[@]}"` is an unbound-variable error on
bash < 4.4; macOS ships bash 3.2.57. And `TIMEOUT` is empty exactly when `command -v timeout`
fails — which is the macOS case, since coreutils installs it as `gtimeout`. So both conditions
coincide and the script dies at step 5 with `TIMEOUT[@]: unbound variable` after a full image
build. (ubuntu-latest and the Git Bash 5.3 of this host are unaffected.)
**Fix:** `${TIMEOUT[@]+"${TIMEOUT[@]}"}`, or drop the array and use an explicit
`if/else` on the two command forms.

### WR-11: the recovery tool cannot start unless the entire agent/vendor import tree imports

**File:** `scripts/state_maintenance.py:42-43`
**Issue:** The docstring promises "Pure stdlib plus `tradingagents`; no network, no LLM", but
`from tradingagents.memory.log import TradingMemoryLog` pulls `tradingagents.memory.__init__`
→ `memory.log` → `agents.rating` → `tradingagents.agents.__init__` → every analyst →
`dataflows.vendors.yahoo.*`, which executes module-level side effects against yfinance
(`vendors/yahoo/common.py:30`). This is the tool you reach for *when state is broken*, possibly
in a stripped recovery environment, and it has the dependency surface of the full application.
Reproduced in this repository's own venv (which has yfinance 0.2.63 against a
`yfinance>=1.7.0` pin, i.e. a stale venv — the root cause is not this phase's code, but it is a
faithful demonstration of the coupling):

```
$ .venv/Scripts/python.exe scripts/state_maintenance.py verify --cache-dir C:/nonexistent ...
  File ".../dataflows/vendors/yahoo/common.py", line 30, in <module>
    yf.config.debug.hide_exceptions = False
AttributeError: module 'yfinance' has no attribute 'config'
```

Note what it needs from all of that: one private constant (`_SEPARATOR`) and `load_entries`.
**Fix:** import the leaf lazily and only inside `check_decision_log`, or (better) have
`tradingagents.memory.log` reachable without `tradingagents.agents` — today `memory/log.py:7`
imports `agents.rating`, which is what drags the graph in. Short of that, defining the
separator locally with a comment pinning it to `log.py:15` removes the import entirely from
the `prune`/`backup` paths.

### WR-12: the safety rails are the untested part, and two tests assert SQLite error prose

**File:** `tests/test_state_maintenance.py` (whole file)
**Issue:** 18 tests, and the branches that exist *solely* to prevent data loss have none:
`_checkpoint_dir`'s symlink-escape refusal (`state_maintenance.py:184`, the tool's headline
guard rail), both `keep ... (symlink, not followed)` branches (`:207`, `:234`), the sidecar
grouping against a non-trivial filename (CR-01 would have been caught by one such test), the
mtime/WAL relationship (WR-01), and any negative/zero-boundary day value (CR-02). Coverage
tracks the happy paths and the documented talking points rather than the risk.
Separately, `test_verify_flags_a_corrupt_checkpoint_db:104` asserts the substring `"malformed"`
and `:116` asserts `"file is not a database"`. Those strings are SQLite's, not the tool's; the
implementation correctly handles *both* the raising and the non-`"ok"`-row outcomes
(`state_maintenance.py:90-96`), but the tests only pass if the bundled SQLite picks the exact
wording — across a py3.11/3.12/3.13/3.14 matrix with four different bundled SQLite builds,
`quick_check` may instead return rows like `*** in database main *** Page 3: btreeInitPage()
returns error code 11`. The SUMMARY notes the tool's own message deliberately avoids the word
"malformed" so the assertion cannot pass accidentally — good — but the assertion is still
pinned to a foreign implementation detail.
**Fix:** assert on the tool's contract (`rc == 2` plus the `FAIL: <name>:` prefix and the
`quick_check` label) rather than the vendor's prose, and add the five guard-rail tests above.

### WR-13: the stub binds `0.0.0.0` unauthenticated with no bind-address knob

**File:** `scripts/smoke/stub_llm.py:28`, `:179`
**Issue:** `ThreadingHTTPServer(("", PORT), StubHandler)` listens on every interface, answers
any `POST */chat/completions` from anyone, and has no auth. Inside the smoke this is correct
and *not* reachable from outside (verified: `docker create` at `docker_smoke.sh:101` publishes
no ports, and the network is `--internal`), and `127.0.0.1` would break the cross-container
call the design depends on. The exposure is the *other* caller: the file has a shebang, a
`main()` and a `if __name__ == "__main__"`, so running `python scripts/smoke/stub_llm.py`
directly — the obvious thing to do when debugging the stub — opens an unauthenticated service
on the developer's LAN for as long as it runs, with nothing in the file warning against it.
**Fix:** take the bind address from the environment and default to loopback, letting the
container be the explicit exception:

```python
BIND = os.getenv("STUB_BIND", "127.0.0.1")   # docker_smoke.sh passes -e STUB_BIND=0.0.0.0
server = ThreadingHTTPServer((BIND, PORT), StubHandler)
```

plus one line in the module docstring: not for production, no auth, test fixture only.

### WR-14: "Report directories: 90 days, enforced by prune" covers one of the three report trees

**File:** `scripts/state_maintenance.py:224-255`; cross-reference
`scripts/STATE_OPERATIONS.md:42-45`, `:82-88`
**Issue:** `_prune_reports` only walks `<results_dir>/reports/<TICKER>_<stamp>` — the
consolidated tree (inventory row 45). The per-run reports `logs/<TICKER>/<date>/reports/*.md`
(row 42, written by `cli/run.py:151`) and the pipeline's state log
`logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<date>.json` (row 44) have no
retention row and no code that ever deletes them. They are not hypothetical — this phase's own
smoke asserts both exist (`docker_smoke.sh:187-196`). The runbook's retention table reads as if
reports are handled; the operator will believe pruning is solved and keep accumulating the two
largest trees (the state log carries full agent message histories).
**Fix:** either prune them (date-stamped directory per run, so the same stamp logic applies) or
add an explicit "not pruned, grows unbounded" row to the retention table in the same honest
style as the existing "The honest limitation on '90 days'" paragraph.

### WR-15: the replacement marker-extraction line reintroduces the SIGPIPE shape its own comment forbids

**File:** `scripts/smoke/docker_smoke.sh:261`
**Issue:** The comment at `:243-249` establishes the rule — no pipe whose reader can exit before
the writer finishes, because `set -o pipefail` turns the writer's SIGPIPE (141) into the
pipeline's status. Twelve lines later:

```sh
NEG_MARKER=$(grep -Eo "$NEG_MARKERS" <<<"$NEG_OUT" | head -1)
```

`head -1` is exactly such a reader. The here-string removed the *first* pipe; this line adds a
new one. Reproduced with the same mechanism, on a `NEG_OUT` large enough that `grep -Eo`'s
output exceeds the 64 KiB pipe buffer:

```
$ bash -c 'set -euo pipefail; NEG_OUT=$(...8000 marker occurrences...)
>   NEG_MARKER=$(grep -Eo "$NEG_MARKERS" <<<"$NEG_OUT" | head -1); echo survived'
exit=141          # "survived" never printed
```

The threshold is higher than before (grep writes only the matches, ~20 bytes each, so it takes
roughly 2700 occurrences rather than 64 KiB of raw output), which is why this is a Warning and
not a Blocker. The failure mode is nasty, though: it triggers *after* every assertion has
passed, aborting before `echo "SMOKE OK"` and before `== 9/9 done`, with no `SMOKE FAIL:` line
and no output at all — a red job whose log ends mid-script. The first CI failure already proved
that this script's error output is bigger on the runner than locally, so the margin is not
something the script controls.
**Fix:** no pipe, per the rule the comment states — the writer exits on its own and the shell
reads to EOF, so SIGPIPE is structurally impossible:

```sh
NEG_MARKER=$(awk -v pat="$NEG_MARKERS" 'match($0, pat) { print substr($0, RSTART, RLENGTH); exit }' <<<"$NEG_OUT")
```

Minimal alternative if `head` is preferred: `grep -Eom1` so grep stops after the first matching
line and has nothing left to write (`grep -Eom1 "$NEG_MARKERS" <<<"$NEG_OUT" | head -1`).

## Info

### IN-01: the negative control's marker set now rests on three libraries' message prose

**File:** `scripts/smoke/docker_smoke.sh:256`
**Issue:** `NEG_MARKERS` spans five spellings across openai-python, httpx/urllib3 and
langchain-openai, including the generic `Connection error`. Checked and **judged acceptable**:
that exact phrase is openai-python's `APIConnectionError` message, nothing in this repository
emits it (`grep -rniE "connection error" cli/ tradingagents/` → no hits), and the data-vendor
failures on the isolated network surface as `DATA_UNAVAILABLE` strings, so a vendor error cannot
satisfy the control. What remains is that the assertion's specificity is owned by third-party
message text, with no test and nothing tying it to port 9999.
**Fix (optional strengthener):** also require the script's own choice to appear, e.g.
`grep -Eq "$NEG_MARKERS" <<<"$NEG_OUT" && grep -q '9999' <<<"$NEG_OUT"` — the port is the one
token the script controls and no library can rename.

### IN-02: fixed container and network names make two concurrent runs destroy each other

**File:** `scripts/smoke/docker_smoke.sh:68-77`
**Issue:** `tex-smoke-stub/-run/-neg/-net` are constants, and the pre-flight teardown removes
them unconditionally. Two developers on one Docker host, or a future matrix on the
`docker-smoke` job, would have run B delete run A's containers mid-flight. Single-job CI today,
so: informational.
**Fix:** suffix the names with `$$` or `${GITHUB_RUN_ID:-$$}` and drop the pre-flight teardown
to a targeted one.

### IN-03: the `mktemp -d` artefact directory is never removed

**File:** `scripts/smoke/docker_smoke.sh:57`, `:257`
**Issue:** The teardown removes docker objects but not `$OUT`; every local run leaves a copy of
`.tradingagents` in the temp directory. Deliberate for `SMOKE_KEEP`/post-mortem, undocumented
for the default path.
**Fix:** mention it next to the `artefacts:` line, or remove it on success only.

### IN-04: no `docker logs tex-smoke-stub` when the call-count assertion fails

**File:** `scripts/smoke/docker_smoke.sh:212-213`
**Issue:** The `STUB call n model=... tools=[...] -> label` lines are the one artefact that
explains a count mismatch (which role answered, how often, with which bound tools). Every other
failure path in the script dumps logs; this one only prints the two numbers.
**Fix:** `docker logs tex-smoke-stub >&2 || true` before the `fail` call.

### IN-05: the port 8000 is a magic number in two files

**File:** `scripts/smoke/stub_llm.py:28`; `scripts/smoke/docker_smoke.sh:131`, `:161`, `:211`
**Issue:** Four literals that must agree, with no single source. A change to `PORT` silently
breaks the readiness probe and the counter read (`SMOKE_FAIL` after 30 s, cause not stated).
**Fix:** `SMOKE_STUB_PORT="${SMOKE_STUB_PORT:-8000}"` in the script, passed to the container as
`-e STUB_PORT`, read by the stub via `os.getenv`.

### IN-06: the stub trusts `Content-Length`

**File:** `scripts/smoke/stub_llm.py:157-158`
**Issue:** `int(self.headers.get("Content-Length") or 0)` raises `ValueError` on a malformed
header (handler thread dies, connection reset, no response), and a negative value makes
`rfile.read(-1)` block until EOF, parking a thread. No request-size bound either.
**Judged acceptable** for a fixture that only ever talks to one client on an internal network —
listed so it is a decision rather than an oversight. **Fix** if desired: `try/except ValueError`
→ 400, and clamp the length.

### IN-07: backup archives collide within the same second; the suffix filter is case-sensitive

**File:** `scripts/state_maintenance.py:337-341`, `:288-289`
**Issue:** The name has second granularity and `tarfile.open(..., "w:gz")` truncates, so two
backups in the same second leave one archive. And `path.suffix not in (".lock", ".tmp", ".db")`
misses `.LOCK`/`.TMP`/`.DB`, which exist on case-insensitive filesystems (the operator's own
platform here is Windows).
**Fix:** `exist_ok` check or `%f`/counter suffix; `path.suffix.lower() not in ...`.

### IN-08: `backup` reports a finding with the usage-error exit code

**File:** `scripts/state_maintenance.py:333-335`
**Issue:** "nothing on the allow-list found under `<state>`" returns `EXIT_CONFIG` (1,
documented as "usage/configuration error"), but the invocation was valid — the state is
unexpectedly empty, which is a `EXIT_FINDING` (2) condition and the more alarming one for a
backup job.
**Fix:** return `EXIT_FINDING` and say so in the docstring's exit-code table.

### IN-09: `age` is computed from a second clock read

**File:** `scripts/state_maintenance.py:201` vs `:211`
**Issue:** `cutoff` uses one `time.time()`, the printed `age` another, so the keep/delete
decision and the number shown to the operator rest on different instants. Cosmetic at a
0.1-day display precision.
**Fix:** `now = time.time()` once at the top of the function and use it for both.

### IN-10: the state-log assertion depends on `json.dump` separators

**File:** `scripts/smoke/docker_smoke.sh:195`
**Issue:** `grep -q '"final_rating": "Overweight"'` bakes in the default
`": "` key/value separator. A future `separators=(",", ":")` or a different indent in the log
writer turns this into "no '"final_rating": "Overweight"' in ..." — a confusing failure for a
formatting change.
**Fix:** `grep -Eq '"final_rating"[[:space:]]*:[[:space:]]*"Overweight"'`.

## Directed Questions

**1. Is dry-run really the default, and can a wrong invocation delete the decision log?**
Dry-run is genuinely the default: `--apply` is `action="store_true"`, every delete is behind
`if apply_changes`, and the run ends with `nothing was deleted - pass --apply to carry this
out`. Confirmed by probe — nothing was removed without the flag. The decision log is **safe
from `prune`**: there is no code path that reads `memory_log_path` during a prune, the only
`unlink` is restricted to `<cache>/checkpoints/*.db` plus sidecars, and the only `rmtree` is
restricted to directories under `<results_dir>/reports` whose names match the stamp regex. A
log file sitting in the blast radius survives (`tests/test_state_maintenance.py:251` covers
both locations, and I reproduced it). Two caveats, both filed above: CR-02 means a sign typo
deletes *today's* reports, and WR-05 means the `rmtree` path has no containment check, so a
symlinked `reports` directory widens the blast radius beyond the cache/results trees.
The `-wal`/`-shm` sidecar naming is correct (`<db>-wal`, `<db>-shm`; the wildcard also catches
`-journal`). The **globbing is not** correct — CR-01 proves it reaches a kept database's
sidecar. The **mtime comparison is not** correct for the crash case — WR-01 proves it deletes a
one-minute-old WAL. The `> cutoff` direction itself is right (future mtimes are kept, i.e. it
errs toward keeping).
Also checked and fine: `TradingMemoryLog.__init__` does `parent.mkdir(parents=True,
exist_ok=True)` (`memory/log.py:25`) — a write in a read-only `verify` path — but `verify` only
constructs it after `log_path.is_file()`, so the parent provably exists and the call is a
no-op. Worth a comment, not a finding.

**2. Does `verify` actually catch `sqlite3.DatabaseError` around `PRAGMA quick_check`?**
Yes — correctly, and better than asked. `state_maintenance.py:90-96` wraps the pragma in
`try/except sqlite3.DatabaseError` **and** handles the non-raising outcomes (`rows` empty →
`<no result>`; `row[0] != "ok"` → reported). It then does not stop there: the schema check at
`:100-108` catches the case the comment documents from research (a corrupt file that still
answers `SELECT count(*)`), and the whole check runs against a *copy* with the sidecars, which
is the right call given WAL needs write access to `-shm`. `tests/test_state_maintenance.py:92`
and `:107` cover both raising shapes. This is the strongest part of the submission. The only
blemish is in the tests, not the code (WR-12: they assert SQLite's wording).

**3. Is the stub only reachable inside the smoke's network, does it bind narrowly, and are
there injection paths?**
Reachability inside the smoke: yes. `docker create` publishes no ports, the network is
`--internal`, and `--network-alias stub` is the only name that resolves. Binding: **not**
narrow — `("", 8000)` is every interface, which is required inside the container but makes the
directly-runnable script a LAN exposure (WR-13). Injection: **none found** — no `subprocess`,
no `shell=True`, no `eval`/`exec`, no `os.system`, no filesystem writes; the request body is
only `json.loads`'d, the `model` string is echoed into the JSON response and into a `print`.
The one residue is log-line forgery via a model name containing newlines/ANSI, which no
component consumes. `python -I` in `docker_smoke.sh:102` is a good touch: on 3.11+ `-I` implies
`-P`, so a file planted at `/` cannot be imported as a module. "Never mistakable for a
production component" is carried entirely by the docstring today — one explicit warning line
would make it carried by the file (WR-13).

**4. Do `set -euo pipefail` plus the traps leave nothing behind, and can an unquoted variable
word-split?**
No leftovers on the normal paths: the pre-flight `teardown` at `:77` is the right design (it
makes "green twice in a row" true), the EXIT trap covers `fail`, `set -e` aborts and the
negative control, and the ordering comment (containers before network) is correct. Ctrl-C does
end up clean too, but only via a second mechanism and with a misleading error on the way —
WR-09. Not removed on any path: `$OUT` (IN-03) and the `tex-smoke:local` image (deliberate).
Word splitting: **clean**. Every parameter expansion that could carry a path is quoted
(`"$OUT"`, `"$TA"`, `"$f"`, `"$STATE_LOG"`, `"$MEM_LOG"`, `"${REPORT_DIRS[0]}"`,
`"$(dirname "$0")/../.."`), and the one glob assignment
`REPORT_DIRS=("$TA"/logs/reports/"${SMOKE_TICKER}"_*)` is immune by construction — pathname
expansion results are not subject to further word splitting, so a `$TMPDIR` with spaces is
safe. The array-related defect is a different one (WR-10, empty array under `set -u` on bash
3.2).
Also verified fine: `.dockerignore` excludes `.env`, `.venv`, `.git`, so making
`docker build .` a routine local command does **not** bake a developer's real API keys into
`tex-smoke:local` — exactly the thing that would have undermined the "no real LLM call"
property. And the non-executable file mode (`100644`) matches the convention for everything
else in `scripts/` (`graphify.sh`, `daily_paper_run.py`), so it is not flagged.

**5. What would make the CI job flaky?**
Ranked: (a) WR-15, the `| head -1` SIGPIPE on line 261, which kills an otherwise-green run with
an empty log and is the direct descendant of the bug that already broke the first CI run;
(b) WR-07, exact `== 9` with client retries left at 2 — the only finding here that can
go red without any code change; (c) WR-08, a cold-cache `docker build` plus two unbounded
`docker run`s inside a 10-minute cap, which fails as an opaque cancellation; (d) WR-12's
SQLite-prose assertions in the `test` matrix job, flaky across four interpreter/SQLite builds;
(e) the unavoidable `python:3.13-slim` pull from Docker Hub (rate limit/outage), inherent to
the design and correctly not worked around. Explicitly **not** flaky and worth saying so: the
readiness gate is a real probe loop with a per-iteration liveness re-check rather than a fixed
sleep; `GET /__count` is side-effect-free, so probe retries cannot perturb the counter
assertion (the docstring at `stub_llm.py:141-146` reasons this out correctly); there is no host
port and no host Python dependency; `SMOKE_DATE` is pinned instead of `auto`; and
`ThreadingHTTPServer` is justified with a measured deadlock. The CRLF/`.gitattributes` risk for
a fresh Windows clone and the first-CI-run uncertainty are already declared as operator items
in the SUMMARY and are not re-filed here.

---

_Reviewed: 2026-10-11T14:21:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick (escalated to full-file reads plus five executed probes, given the destructive tool)_
