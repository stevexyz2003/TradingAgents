# IBKR paper execution — operating manual

Companion to `scripts/PAPER_RUN.md`. That one covers the daily analysis run;
this one covers the local IBKR paper executor: the connection to the paper
gateway, the paper-account guard, and reading the account into a portfolio
JSON. It is the start of the operating manual of REQ-IBKR-60 and grows with
every phase up to phase 8.

Every claim here carries a `file:line` reference or a pointer to the account
findings (`.planning/ibkr-konto-befund.md`), measured on 2026-10-11, so a later
reader can check it instead of trusting it.

| | |
|---|---|
| Tool | `scripts/ibkr_executor.py` (`account`) |
| Adapter | `scripts/ibkr_broker.py` (the only module that talks to the IBKR client library) |
| Tests | `tests/test_ibkr_*.py` |
| Account | `DUQ634065` (paper) |
| Extra | `pip install -e ".[ibkr]"` |

**Phase 2 is read-only.** The adapter has no write API at all — no place, no
preview, no cancel, not even as a stub. On top of that, the client's write
calls (`placeOrder`, `cancelOrder`, `reqGlobalCancel`, `exerciseOptions`,
`_WRITE_CALLS` in `scripts/ibkr_broker.py`) are replaced by a refusing
function before the first byte goes to the gateway (`_arm_write_barrier`).
Because a list of call names proves nothing about the calls it does not
name, the same barrier also guards the client's send path, through which
every request goes: a message with one of the write ids 3 (place order),
4 (cancel order), 19 (replace FA), 21 (exercise options) or 58 (global
cancel) is refused there, whichever call produced it (`_WRITE_MESSAGE_IDS`).
Tests run this against the real client object of the pinned library. The
client parameter `readonly=True`
(`scripts/ibkr_broker.py:250`) does **not** block anything: in the pinned
library version it only skips the order sync at startup. The gateway switch
"Read-Only API" is **not** a default setting and was off after the phase-1
measurement (`ibkr-konto-befund.md`, Korrektur 2).

## Gateway Read-Only switch

The gateway's "Read-Only API" switch is a second barrier outside this
repository. Its state is recorded here whenever it changes.

| Date | State | By | Note |
|---|---|---|---|
| 2026-10-11 20:27 | off | operator | turned off again after the 321 proof (ibkr-konto-befund.md) |
| 2026-10-12 08:45 | on | operator | before the first real Phase-2 run (D-02); paper user login confirmed |

Localhost only: the gateway process listens on `:::7497`, i.e. on all
interfaces, not only on `127.0.0.1`. That is expected - the gateway refuses
remote clients when it accepts the connection, not when it binds. What matters
is the setting *Configure → Settings → API → Settings → "Allow connections
from localhost only"*: the operator checked it on 2026-10-12 and it was already
set. Keep the *Trusted IPs* list empty or at `127.0.0.1`.

Marker: with the switch on, gateway 10.50.1 rejects a write with error **321**
(state `READ_ONLY_API`), not with the documented 10015
(`ibkr-konto-befund.md`, Korrektur 1; `scripts/ibkr_broker.py:65-68`). With the
switch on, two 321 notices already arrive at connect, before any order; the
executor logs them as warnings and carries on.

## clientId

The executor connects with clientId **20001**, the constant
`EXECUTOR_CLIENT_ID` in `scripts/ibkr_broker.py:31`. Why this value:

* outside 0..9999, where ai_tradex hands out `hash % 10000`, so the two never
  collide;
* not 0: clientId 0 binds the orders placed manually in TWS;
* not 1: that is the client library's default, so any ad-hoc script would
  collide with it;
* not 98: that was the phase-1 probe.

A clientId already in use shows up as error **326** and ends the run with
state `CLIENT_ID_IN_USE`, exit 3. Assumption A2 ("the gateway accepts values
above 9999") was confirmed by the first real run on 2026-10-12 (see
"First real run").

Order ids: never set by this code. They start at the gateway's
`nextValidId` (phase 6); `tests/test_ibkr_isolation.py` keeps hard-coded order
ids out of the adapter.

## Settings

The executor reads the `.env` at the repository root by a fixed path
(`DEFAULT_ENV_FILE`, `scripts/ibkr_executor.py:67`), not from the current
directory; `--env-file PATH` overrides it. Only these keys are taken
(`scripts/ibkr_executor.py:61`, `read_settings` at `:123`):

| Key | Required | Rule |
|---|---|---|
| `IBKR_HOST` | yes | e.g. `127.0.0.1` |
| `IBKR_PORT` | yes | integer 1..65535; measured **7497** (the gateway runs on the TWS paper port, not on 4002; `ibkr-konto-befund.md`) |
| `IBKR_ACCOUNT_ID` | yes | must be `DUQ634065`: the expected account is a code constant (`scripts/ibkr_broker.py:27`), the `.env` has to match it, never the other way round |
| `IBKR_TRADING_MODE` | no | when set, must be `paper` |

A missing or blank required key, or an unreadable settings file, ends with
exit 20 before any connection; an invalid port, another account or another
mode ends with exit 1 before any connection (`validate_settings`,
`scripts/ibkr_executor.py:142`). The API needs no user name or password; the
command does not copy them out of the `.env` and never logs them. None of
these values is ever a CI secret — the executor is local operator tooling.

## Exit codes

Identical to the table in the docstring of `scripts/ibkr_executor.py`; a test
(`tests/test_ibkr_isolation.py`) keeps the two in step.

| Code | Constant | Meaning |
|---|---|---|
| 0 | `EXIT_OK` | ok, including "nothing to do" |
| 1 | `EXIT_CONFIG` | configuration error - nothing was done |
| 2 | `EXIT_PRECONDITION` | precondition not met: a ticker was rejected by resolve, contracts.json is missing, or --init found an existing file |
| 3 | `EXIT_GATEWAY` | gateway/session not reachable |
| 4 | `EXIT_KILL_SWITCH` | kill switch active or release missing (reserved for later phases) |
| 5 | `EXIT_REJECTED` | order rejected (reserved for later phases) |
| 6 | `EXIT_RECONCILE` | reconciliation unresolved, run aborted (reserved for later phases) |
| 7 | `EXIT_LOCKED` | lock not acquired (second instance), clean exit (reserved for later phases) |
| 8 | `EXIT_ACCOUNT_GUARD` | account guard violated (managedAccounts != ["DUQ634065"]) |
| 20 | `EXIT_NO_CREDENTIALS` | IBKR settings missing or unreadable - same meaning as `EXIT_NO_CREDENTIALS` in `daily_paper_run.py` |

Exit 2 is active since phase 3 (`resolve`): a rejected ticker (any result
other than `ok` or `closed`), a missing `contracts.json` and `--init` on an
existing file all end with 2. A broken `contracts.json` or a wrong
`schema_version` is exit 1 (configuration, nothing was done). A `closed`
session is exit 0: the contract is fine, the market is just not open.

Code 3 means "gateway" here, unlike `EXIT_RUN_FAILED` (3) in the paper run.
Exit 3 also covers a write the barrier refused (state `WRITE_REFUSED`, its
own log line) and any unexpected error once the connect has started: from
then on a socket and a handshake may have stood, so "nothing was done" no
longer holds. An unexpected error before the connect starts stays exit 1.
Exit 1 also covers a missing `ibkr` extra (the console line names
`pip install -e ".[ibkr]"`) and a portfolio JSON that could not be written or
did not validate.

## States and log format

Every run writes one UTF-8 log file; its first line names its own absolute
path. Default: `%LOCALAPPDATA%\TradingEngineX\ibkr\logs\ibkr_executor.log`
(without `LOCALAPPDATA`: `~/.tradingenginex/ibkr/logs/ibkr_executor.log`),
outside every git tree; `--log-file PATH` overrides it. The file handler sits
on the root logger, so the client library's own log lines land in the same
file and never on the console. The console gets exactly one line: the summary
on success, `error: ...` on failure. A traceback, if any, is in the log file
only.

Gateway lines have the form

```
ibkr-state=<STATE> code=<code> detail="..."
```

| Code | State |
|---|---|
| 502 | `GATEWAY_UNREACHABLE` |
| 504 | `NOT_CONNECTED` |
| 507 | `SOCKET_EOF` |
| 326 | `CLIENT_ID_IN_USE` |
| 1100 | `CONNECTIVITY_LOST` |
| 1101 | `RESTORED_DATA_LOST` |
| 1102 | `RESTORED_DATA_KEPT` |
| 1300 | `PORT_CHANGED` |
| 2103, 2105 | `FARM_DOWN` |
| 2104, 2106, 2158 | `FARM_OK` (logged at INFO) |
| 2110 | `SERVER_LINK_BROKEN` |
| 321 | `READ_ONLY_API` (measured marker of the read-only switch) |
| 10015 | `TRADING_NOT_ALLOWED` |
| 10089, 10090 | `MARKET_DATA_NOT_SUBSCRIBED` (INFO: expected, not an error) |
| 10167 | `MARKET_DATA_DELAYED` (INFO: expected, measured for delayed stock quotes) |
| 200 | `CONTRACT_NOT_FOUND` |
| 2172 | `GATEWAY_VERSION_EXPIRING` |
| any other | `UNKNOWN` |

10089, 10090 and 10167 are logged at INFO: the paper account has no market
data subscription and works on delayed data, so they are expected. Code 154
(halt) is deliberately not mapped; it is measured in phase 4 on the `whatIf`
preview.

Executor and resolver states without a gateway code (phase 3):
`AMBIGUOUS_CONTRACT`, `CONTRACT_DRIFT`, `CONTRACT_LEARNED`,
`CONTRACT_REBASELINED`, `CONTRACTS_MISSING`, `CONTRACTS_INVALID`,
`CONTRACTS_EXIST`, `ANCHOR_MISMATCH`, `MARKET_DATA_TYPE`.

Source: `STATE_BY_CODE`, `scripts/ibkr_broker.py:49`; INFO codes at `:75`.
502, 504 and 507 never arrive as events from the client library; the adapter
derives them from the exceptions of the connect (refused/OS error → 502,
connection error → 504, reset/EOF → 507).

States without a gateway code: `CONNECT_TIMEOUT`, `REQUEST_TIMEOUT`,
`PROBE_TIMEOUT`, `PROBE_FAILED`, `SNAPSHOT_INCOMPLETE`, `HEALTHY`, and from
the executor `ACCOUNT_GUARD_VIOLATED`, `WRITE_REFUSED`, `SETTINGS_MISSING`,
`CONFIG_INVALID`, `LIBRARY_MISSING`, `OUTPUT_INVALID`, `UNEXPECTED`.

Liveness is a real server answer, not the socket state: `health()`
(`scripts/ibkr_broker.py:305`) asks for the contract details of
conId 265598 (AAPL on SMART) under a timeout and counts the session as healthy
only when exactly that contract comes back. An open 1100/2110/1300 makes the
session unhealthy without a probe.

The snapshot is fail-closed over its whole read window: `positions()` reads
nothing while a 1100/2110/1300 is open, lets the loop read the socket for
`SNAPSHOT_SETTLE_S` (0.05 s) after the last answer, and discards the snapshot
when any of 1100, 1101, 1102, 1300 or 2110 (`LINK_CODES`) arrived inside the
window — exit 3, no file. After a 1100 the gateway answers from its local
state with well-formed rows, so the absence of an error proves nothing. The
same rule voids a probe answer that arrived together with a link event.

## Startup sequence

1. Write barrier on the client (`scripts/ibkr_broker.py:241`).
2. Connect with `readonly=True`, clientId 20001 and no startup fetch. The
   client library waits up to `CONNECT_TIMEOUT_S` (10 s) in each of its
   connect steps (TCP connect, API start, startup positions); the adapter
   ends the whole connect after `CONNECT_TIMEOUT_S + CONNECT_GRACE_S`
   (10 s + 5 s = **15 s**), and the `CONNECT_TIMEOUT` line names that bound.
   Then 10 s per request and 5 s for the probe (constants at the top of
   `scripts/ibkr_broker.py`). A test with a peer that never answers ends in
   `CONNECT_TIMEOUT`, not in a hang.
3. Paper guard: `managedAccounts()` must be exactly `["DUQ634065"]` — a foreign
   account, a superset or an empty list disconnects and ends with exit 8
   (`scripts/ibkr_broker.py:294`).
4. Health probe (above); unhealthy → exit 3, no file.
5. Positions and `TotalCashValue` (EUR), asked fresh on every call
   (`positions()` in `scripts/ibkr_broker.py`). The client library answers
   the account summary from its own cache after the first request of a
   session; the adapter empties that cache before each call, so every call
   sends the request again. Known limit: each call leaves one summary
   subscription open in the session (one call per run in phase 2). Average prices in another
   currency than the cash — e.g. USD stocks in the EUR account — are written
   as `average_price: null` and logged as a WARNING, because
   `PortfolioContext` carries one currency label only; conversion comes with
   phase 4 (`snapshot_to_portfolio`, `scripts/ibkr_executor.py:219`).
   Non-stock positions get no price either (the average cost includes the
   multiplier).
6. Disconnect, then write the JSON atomically: temp file beside the target,
   validated by `load_portfolio()`, moved into place with `os.replace`
   (`write_portfolio_atomic` in `scripts/ibkr_executor.py`). The file carries
   the snapshot time as an extra top-level key `as_of` (UTC, ISO 8601;
   `portfolio_json`). `PortfolioContext` ignores unknown keys, so
   `load_portfolio()` reads the book unchanged and its fingerprint does not
   move. **A failed run leaves no file:** before anything else, even before
   the settings are read, the executor removes the `--out` file of an earlier
   run (`_discard_previous`; log line `previous portfolio removed`). A file
   that cannot be removed ends the run with exit 1 before any connection.
7. Cross-check: `load_portfolio()` on the file in place
   (`scripts/ibkr_executor.py:309`).

Note: the handshake of the client library already requests the positions
before the guard runs — a harmless read; nothing is written before the guard.

## Dependency pin

The client library is pinned to 2.1.0 in the `ibkr` extra of
`pyproject.toml`, next to the cap `tzdata>=2025.2,<2026.0`
(`pyproject.toml:47-49`): the pinned library version declares that cap
itself, so any `tzdata>=2026` requirement elsewhere makes the extra
unresolvable. Measured negative proof: the pinned version together with
`tzdata>=2026.1` ends in pip's `ResolutionImpossible`
(`.planning/phases/02-verbindung-paper-guard-und-kontolesen/02-01-SUMMARY.md`).

## resolve

`resolve TICKER...` answers, per ticker, one question: may the executor trade
this symbol, and is its market open right now? It only reads; the write
barrier and the paper guard are unchanged. The ticker arguments are required
(no default list, D-27). The gateway is contacted only when at least one
ticker passes the local checks; a run of rejected tickers never connects.

Check chain per ticker: mapping (`CONTRACT_TABLE` in
`scripts/ibkr_contracts.py`) -> allow-list (`STK` only) -> resolution and
identity against `contracts.json` -> tradability -> session.

| State | Meaning |
|---|---|
| `ok` | resolved, identity as stored, tradable, session open (outside the buffer) |
| `closed` | contract fine, session not open; the console line names the next window; exit 0 |
| `not-mapped` | the ticker is not in `CONTRACT_TABLE` (this also stops `^GSPC`, `XAUUSD+` and the like) |
| `not-allowed` | the security type is not on the allow-list |
| `ambiguous` | the gateway returned more than one contract for the search key |
| `not-found` | the gateway knows no such contract (code 200) |
| `drift` | `conId`, `primaryExchange`, `currency` or `localSymbol` differs from `contracts.json` |
| `not-tradable` | the contract lacks a required order type or the SMART route |
| `session-unknown` | the session could not be derived from the contract data; treated as rejected |
| `halted` | never set in phase 3: "unknown" is not "not halted"; measured in phase 4 |

Session rule: a ticker is `ok` only inside a liquid-hours window, with a
15-minute buffer after the open and before the close
(`SESSION_BUFFER_MINUTES`). The window comes from the contract data of the
gateway; no clock time is coded and nothing about the session is cached on
disk.

Console: one line per ticker (`resolve: <TICKER> <state> ...`), details in the
log. `--out PATH` writes the results as JSON, atomically (temp file, then
`os.replace`); a previous file at that path is removed at the start of the run.

Options: `--init` (create `contracts.json`), `--rebaseline TICKER` (accept a
changed contract), `--contracts PATH` (override the store path), `--out PATH`,
`--log-file PATH`, `--env-file PATH`.

### contracts.json and its history

Default path: `%LOCALAPPDATA%\TradingEngineX\ibkr\contracts.json` (without
`LOCALAPPDATA`: `~/.tradingenginex/ibkr/contracts.json`); `--contracts`
overrides it. Schema: `schema_version` 1 and a `contracts` object with, per
ticker, `conId`, `primaryExchange`, `currency`, `localSymbol`, `learned_at`.
There is no session field.

Next to it, `contracts-history.jsonl` is append-only: one line per change,
event `init`, `learn` or `rebaseline` (an `-aborted` suffix marks an
unfinished write).

* First build: `resolve --init AAPL MSFT NVDA`. AAPL is the anchor: its
  learned `conId` must equal `PROBE_CON_ID` 265598, otherwise the run ends
  with `ANCHOR_MISMATCH` (exit 2) and writes nothing. `--init` never
  overwrites an existing file (exit 2).
* A new ticker in an existing file is learned on its first successful
  `resolve <TICKER>` (event `learn`); known tickers are checked by `conId` and
  exchange.
* A differing identity is `drift`: nothing is changed. After checking the
  change by hand, `resolve AAPL --rebaseline AAPL` accepts it (event
  `rebaseline`, old and new values in the history).
* Files are written only after the gateway session is closed.

## New ticker

1. Add the ticker to `CONTRACT_TABLE` in `scripts/ibkr_contracts.py`: a search
   key only, no identity.
2. Commit.
3. Run `resolve <TICKER>` exactly once against the gateway. The result must be
   exactly one match (not `ambiguous`, not `not-found`).
4. Put the console output into the commit message or the PR.

This is a convention, not a technical gate. Non-STK classes stay blocked by the
allow-list; to open one, extend the allow-list, do not rebuild the table (D-04).

## Commands

```
:: first build of contracts.json, anchor AAPL (Windows cmd)
python scripts/ibkr_executor.py resolve --init AAPL MSFT NVDA

:: normal check of known tickers
python scripts/ibkr_executor.py resolve AAPL MSFT NVDA

:: same, with the results as JSON
python scripts/ibkr_executor.py resolve AAPL MSFT NVDA --out "%LOCALAPPDATA%\TradingEngineX\ibkr\resolve.json"

:: blocked tickers are rejected locally, exit 2, no gateway connection
python scripts/ibkr_executor.py resolve XYZQ ^^GSPC XAUUSD+

:: accept a changed contract, only after checking the drift
python scripts/ibkr_executor.py resolve AAPL --rebaseline AAPL
```

```
:: read the paper account into a portfolio JSON (Windows cmd)
python scripts/ibkr_executor.py account --out "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json"

:: the log goes to %LOCALAPPDATA%\TradingEngineX\ibkr\logs\ibkr_executor.log by default
python scripts/ibkr_executor.py account --out "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json" --log-file "%LOCALAPPDATA%\TradingEngineX\ibkr\logs\ibkr_executor.log"

:: snapshot and local paper run in one line: && runs the paper run only on exit 0
python scripts/ibkr_executor.py account --out "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json" && python scripts/daily_paper_run.py --tickers AAPL --max-cost 0.50 --out results\paper-local --state paper-state --portfolio "%LOCALAPPDATA%\TradingEngineX\ibkr\portfolio.json"
```

`--tickers`, `--max-cost`, `--out` and `--state` are required by the paper run
(`parse_args` in `scripts/daily_paper_run.py`); their meaning and the cost
budget are described in `scripts/PAPER_RUN.md`. `--portfolio` is local only;
the CI run never passes it. The paper run picks its LLM provider from the
environment: without `TRADINGAGENTS_LLM_PROVIDER=anthropic` and the two model
variables in `.env` it falls back to `openai` instead of the CI's Anthropic
setup (see "Running it locally" in `scripts/PAPER_RUN.md`).

With `--portfolio` the reports, the archived copies under
`paper-state/runs/<date>/`, the decision log and the summaries carry cash,
positions and average prices of the paper account. The two relative
directories of the command above, `results/paper-local/` and `paper-state/`,
are therefore listed in `.gitignore`, and `tests/test_ibkr_isolation.py`
checks with `git check-ignore` that every `--out`/`--state` directory of
this section stays ignored. Pointing them elsewhere inside the repository
needs a matching ignore rule first; outside the tree (like the log under
`%LOCALAPPDATA%`) needs none.

Never run the paper run on its own against an older book. Two barriers keep a
stale book out, either one enough by itself:

* the executor removes the old file at the start of every run, so after a
  failed snapshot there is no file and the paper run stops with exit 1;
* `daily_paper_run.py --portfolio` accepts a file only with an `as_of` that
  has a time zone, is not more than 5 minutes in the future and not older
  than `--portfolio-max-age-minutes` (default 60; `load_fresh_portfolio`).
  A file without `as_of` — hand-written, or from before this rule — is
  refused, also under `--preflight`.

## First real run

One single `account` run against the running paper gateway, executed by the
plan-02-05 executor agent from the repository root; no retry, no other
command against the gateway.

| | |
|---|---|
| Date | 2026-10-12, 13:26:30 – 13:26:32 local time |
| Command | `.venv/Scripts/python.exe scripts/ibkr_executor.py account --out "$LOCALAPPDATA/TradingEngineX/ibkr/portfolio.json"` |
| Read-Only API | on (operator, 08:45 the same day; table above) |
| Gateway | 10.50.1 (`ibkr-konto-befund.md`); log: `Logged on to server version 178` |
| Exit code | **0** |
| Console | `account: 0 position(s), cash 1005459.44 EUR -> C:\Users\admin\AppData\Local\TradingEngineX\ibkr\portfolio.json` |
| Positions | 0 |
| Cash | 1005459.44 EUR (`TotalCashValue`); log only: `AvailableFunds` and `NetLiquidation` 1005888.32 EUR |
| clientId | **20001 accepted** — no 326; assumption A2 confirmed |
| Paper guard | passed: `ibkr-state=CONNECTED account=DUQ634065 clientId=20001 readonly=True` |
| Session | 333 ms on the socket, 6 messages sent, 103 received; whole run about 2 s |
| Cross-check | `load_portfolio()` on the written file: `{'cash': 1005459.44, 'currency': 'EUR', 'positions': []}` |
| Writes | none: no `placeOrder`, `orderStatus`, `newOrder` or `ReadOnlyViolation` line in the log |

Observed gateway states:

* `ibkr-state=FARM_OK code=2104` (eufarm) and `code=2158` (secdefeu) at INFO.
* `ibkr-state=UNKNOWN code=2107` at WARNING (gateway text, translated): "HMDS data farm connection is
  inactive but should be available upon demand" (euhmds). 2107 is not in
  `STATE_BY_CODE` yet; it is harmless and should be mapped as an INFO code.
* **No 321 at connect.** The phase-1 measurement saw two 321 notices at
  connect with the switch on; this run saw none, although the operator
  reported the switch on. Either the notices depend on something else (e.g.
  the order sync that `readonly=True` skips), or the switch was not in effect.
  Not decided here — the operator checks the switch in the gateway.

Findings for later plans:

* The health probe is not logged on success: `health()` returns `HEALTHY`
  without a log line (`scripts/ibkr_broker.py:345`). It is proven only
  indirectly — an unhealthy session would have ended with exit 3 before the
  snapshot.
* The arming of the write barrier is not logged either.
* `TotalCashValue` (1005459.44) and `NetLiquidation` (1005888.32) differ by
  428.88 EUR with no position open; probably accrued interest or similar, not
  examined here.
* The gateway listened on `:::7497` (all interfaces); "Allow connections from
  localhost only" was confirmed as set on 2026-10-12 (see "Gateway Read-Only
  switch").

## See also

* `scripts/PAPER_RUN.md` — the daily analysis run.
* `scripts/STATE_OPERATIONS.md` — what the runs leave on disk.
* `.planning/ibkr-konto-befund.md` — the account findings of phase 1 (port,
  read-only proof, marker 321).
