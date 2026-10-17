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
| 2026-10-12 | off | operator | after D-14 measurement 2: the switch blocks whatIf (321); phase 4 is protected by the socket barrier |

Localhost only: the gateway process listens on `:::7497`, i.e. on all
interfaces, not only on `127.0.0.1`. That is expected - the gateway refuses
remote clients when it accepts the connection, not when it binds. What matters
is the setting *Configure → Settings → API → Settings → "Allow connections
from localhost only"*: the operator checked it on 2026-10-12 and it was already
set. Keep the *Trusted IPs* list empty or at `127.0.0.1`.

Phase 4 measurement (D-14, 2026-10-12, gateway 10.50.1, `ibkr-konto-befund.md`,
section "whatIf-Vorschau und Read-Only-Schalter"): with the switch **off** the
`whatIf` preview answers in 0.79 s with margin and commission; with the switch
**on** it is blocked: error 321 ("API is in read-only mode"), no margin data,
and the preview runs into its 10 s timeout. So the switch cannot protect the
preview. **Rule for phase 4: the switch stays off.** What protects phase 4 is
the socket barrier alone: it lets message id 3 through only as a stock `whatIf`
preview and refuses every real order. Error 154 (halt) cannot be provoked on
the paper gateway and is not measured; `halted` is covered by the official code
list and a fake test only.

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

The market-data stream (`scripts/ibkr_market_data.py`) connects with clientId
**20002**, the constant `MARKET_DATA_CLIENT_ID`, for the same reasons. It is a
session of its own, so the stream can run while the executor is connected, and
market data never enters the order path (REQ-IBKR-26).

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
| `IBKR_PAPER_LOG_REMOTE` | no | git remote `preview` reads the decision log from; default `fork` |
| `IBKR_PAPER_LOG_BRANCH` | no | branch `preview` reads; default `paper-log` |

The two paper-log keys accept only a plain ref name (letters, digits, `.`, `_`,
`-`, `/`; no leading `-`, no `..`); anything else ends with exit 1 before a
command line sees it. A failed fetch stops the run with
`paper-log-unavailable` (exit 2): there is no fallback to an older local copy
(D-02), because a stale decision must never look like a fresh one.

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
| 1 | `EXIT_CONFIG` | configuration error - nothing was done; also a `summary.json` with `schema_version` != 1 or a broken contract |
| 2 | `EXIT_PRECONDITION` | precondition not met, including Hold (D-16): a ticker was rejected by resolve or preview, the paper-log is unavailable, contracts.json is missing, or --init found an existing file |
| 3 | `EXIT_GATEWAY` | gateway/session not reachable |
| 4 | `EXIT_KILL_SWITCH` | kill switch active (KILL present), or release missing, unreadable, invalid, expired, more than 90 days ahead or for another account; only a present KILL file triggers a global cancel |
| 5 | `EXIT_REJECTED` | whatIf preview rejected: empty or incomplete, rejected with a reason, halted (154), over budget, tif overridden or unconfirmed, read-only gateway, currency mismatch |
| 6 | `EXIT_RECONCILE` | ledger corrupt or a ledger entry could not be reconciled against open orders, completed orders and executions; no new order |
| 7 | `EXIT_LOCKED` | run lock not acquired (another run holds `ledger.jsonl.lock`) or the lock attempt failed; nothing was done |
| 8 | `EXIT_ACCOUNT_GUARD` | account guard violated (managedAccounts != ["DUQ634065"]) |
| 20 | `EXIT_NO_CREDENTIALS` | IBKR settings missing or unreadable - same meaning as `EXIT_NO_CREDENTIALS` in `daily_paper_run.py` |

Exits 4, 6 and 7 are active since phase 5 (`execute`). When several things go
wrong in one run, the run exit is the worst by this rank: `4 > 7 > 6 > 8 > 3 >
1 > 5 > 2 > 0`.

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
| `not-mapped` | the ticker is not in `CONTRACT_TABLE` |
| `not-allowed` | the security type is not on the allow-list (e.g. `^GSPC` IND, `XAUUSD+` CMDTY) |
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
unfinished replace after the history append). After a process crash the history
can be a superset; `contracts.json` is authoritative.

A write takes `contracts.json.lock` beside the file and aborts (exit 1) if it
already exists or if `contracts.json` changed since the run read it. A
`.lock` left behind by a killed process blocks every later write: make sure
no `resolve` is running, then delete the `.lock` file by hand.

* First build: `resolve --init AAPL MSFT NVDA`. If `contracts-history.jsonl`
  already contains entries while `contracts.json` is missing, `--init` stops;
  restore `contracts.json` manually instead of learning a new baseline. AAPL is
  the anchor: its
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

## preview

`preview TICKER...` is the dry run: it takes the newest decision of each ticker
from the `paper-log` branch, works out what the paper account would do and asks
the gateway for a `whatIf` preview. It **sends nothing**, and it is not the
ledger (no write-ahead, no lock; that is phase 5). The tickers are required (no
default list). Call: `python scripts/ibkr_executor.py preview AAPL [MSFT ...]`.

Chain, in steps (the gateway is contacted only for a ticker that survives
steps 1-6):

1. Fetch `IBKR_PAPER_LOG_REMOTE`/`IBKR_PAPER_LOG_BRANCH` and read the branch
   without a checkout. A failed fetch is `paper-log-unavailable`.
2. Copy the files under `%LOCALAPPDATA%\TradingEngineX\ibkr\paper-log\decision-log.md`
   (without `LOCALAPPDATA`: `~/.tradingenginex/ibkr/paper-log/`) and verify the
   copy; every log line carries the read commit SHA.
3. Newest entry per ticker (`no-decision`, `log-missing-entry`, `rating-review`).
4. `summary.json` contract: `schema_version` 1 and the fields the consumer
   reads (`summary-missing`, `summary-schema`, `summary-contract`,
   `run-not-ok`, `signal-null`, `signal-divergence`).
5. Preconditions: Hold is `skipped-hold`, exit 2 (D-16).
6. Freshness, counted in XNYS sessions, not in calendar days: an entry is
   fresh for the next execution session; a calendar gap over a weekend or
   holiday is flagged `weekend_gap` and is still fresh. Otherwise
   `stale-decision`, `future-decision` or `calendar-conflict`.
7. Resolve and session as in `resolve`; a `closed` market is a mark, not a stop.
8. Position by `conId` (never by symbol); a fractional position stops the ticker.
9. Foreign open orders: in phase 4 every open order is foreign (`foreign-open-order`).
10. Target: blocks x `block_qty`, tolerance of one block, long-only
    (`within-tolerance`, `long-only-noop`).
11. `whatIf` with a market order, time in force DAY.
12. Judgement: fail-closed on anything missing, rejected, halted, with another
    time in force than sent, in another currency than the account, or with an
    initial margin at or above the available funds.

Console: one line per ticker (`preview: <TICKER> <state> ...`). Log: one
`ibkr-state=PREVIEW ticker=... sha=...` line per ticker, plus a
`PREVIEW_RESULT` line for every ticker that reached the preview. Exit: the
worst state over all tickers, ranked 1 > 5 > 2 > 0.

Dry-run record: `%LOCALAPPDATA%\TradingEngineX\ibkr\preview.json` (`--out`
overrides), written atomically; the record of an earlier run is removed at the
start. Fields: `schema_version` (1), `as_of` (UTC), `paper_log` (`remote`,
`branch`, `sha` - the provenance of the decision), `run_state`, `sent` (always
`false`) and `rows`. A row has `ticker`, `state`, `detail`, the entry
(`rating`, `trade_date`), `freshness` (including `weekend_gap` and `gap_days`),
`session`, `intent` (side, quantity, `MKT`, `tif_sent`; absent for a Hold) and
`preview` (margin and commission, `warning_text`, `reject_reason`, `errors`,
`tif_sent`, `effective_tif`). `reject_reason` is built from the request's error
texts: the order state of the client library has no reject-reason field.
`effective_tif` is read back from the gateway's echo, never assumed.

### States (phase 4)

| State | Exit | Meaning |
|---|---|---|
| `skipped-hold` | 2 | the decision is Hold; nothing to do (D-16) |
| `rating-review` | 2 | the rating needs a human look |
| `run-not-ok` | 2 | the run behind the decision did not finish ok |
| `signal-null` | 2 | the run produced no signal |
| `signal-divergence` | 2 | log entry and summary disagree on the signal |
| `summary-missing` | 2 | no `summary.json` for the entry's day |
| `summary-schema` | 1 | `summary.json` has a `schema_version` this tool does not know |
| `summary-contract` | 1 | `summary.json` lacks a field the tool reads |
| `no-decision` | 2 | no entry for the ticker |
| `log-missing-entry` | 2 | the summary lists the ticker but the log has no entry |
| `invalid-trade-date` | 2 | the entry's trade date is not a date |
| `log-finding` | 2 | the copy of the log failed verification |
| `paper-log-unavailable` | 2 | the fetch or the read of the branch failed |
| `stale-decision` | 2 | the decision is older than the next execution session |
| `future-decision` | 2 | the decision is dated after the execution session |
| `calendar-conflict` | 2 | the session calendar cannot answer for the date |
| `not-resolved-yet` | 2 | the ticker has no stored contract yet |
| `foreign-open-order` | 2 | an open order exists; phase 4 never sends, so it is foreign |
| `fractional-position` | 2 | the held quantity is fractional |
| `short-position` | 2 | the held quantity is negative (short); the plan is long-only, so no order |
| `within-tolerance` | 0 | target and holding differ by less than one block |
| `long-only-noop` | 0 | sell or underweight without a holding; no short |
| `preview-ok` | 0 | whatIf ok, within budget |
| `preview-empty` | 5 | the whatIf returned nothing or incomplete values |
| `preview-rejected` | 5 | the gateway rejected the order with a reason |
| `preview-read-only` | 5 | the gateway's Read-Only API switch blocks the preview (321) |
| `tif-overridden` | 5 | the gateway changed the time in force |
| `tif-unconfirmed` | 5 | the effective time in force was not readable |
| `over-budget` | 5 | initial margin at or above the available funds |
| `currency-mismatch` | 5 | funds currency differs from the account currency |
| `halted` | 5 | the instrument is halted (154) |

Source: `EXIT_BY_STATE` in `scripts/ibkr_decision.py`; a test keeps the table in
step with it.

### Block size

The target is `blocks x block_qty`: Buy = 2 blocks, Overweight = 1, Underweight
and Sell = 0. `block_qty` sits per ticker in the contract table
(`scripts/ibkr_contracts.py`): 1 share per block for AAPL, MSFT and NVDA. It is
the operator's fixed choice and never derived from a price; changing it is a
commit.

## RELEASE and KILL

Two plain files in the state folder (`%LOCALAPPDATA%\TradingEngineX\ibkr\`, never
inside a git tree) decide whether `execute` may go on. Both are read first in
every run, and again before every whatIf and before every `intent`.

| File | Path | Meaning |
|---|---|---|
| `RELEASE` | `...\ibkr\RELEASE` | the operator's permission: account and a "valid until" date |
| `KILL` | `...\ibkr\KILL` | the stop: any file or folder named `KILL` or `KILL.<anything>`, in any case |

`KILL` matches loosely on purpose: Explorer hides file endings by default, so
"New > Text Document" typed as `KILL` is `KILL.txt` on disk. Every entry in the state
folder whose name, ignoring case, is `KILL` or starts with `KILL.` counts as a present
kill switch (`KILL`, `KILL.txt`, `kill.TXT`); `KILLER` or `KILL_old` do not. If the
state folder cannot be listed, the state is `kill-unreadable`. `RELEASE` stays exact:
only a file named `RELEASE` is read, so a stray `RELEASE.txt` never opens trading.

`RELEASE` is UTF-8 JSON without a byte-order mark with exactly two keys:

```json
{"account": "DUQ634065", "valid_until": "YYYY-MM-DD"}
```

The day in `valid_until` counts in full, in UTC. The date may lie at most 90 days
ahead (D-20), and `account` must be the paper account (D-02). Anything else is
exit 4 with its own state: `release-missing`, `release-unreadable`,
`release-invalid` (not UTF-8, not JSON, wrong keys), `release-expired`,
`release-account-mismatch`.

PowerShell one-liners (write the file as UTF-8 without a BOM):

```powershell
# create the release, valid for 30 days (adjust the date by hand if you prefer)
$d = Join-Path $env:LOCALAPPDATA 'TradingEngineX\ibkr'; New-Item -ItemType Directory -Force $d | Out-Null; [IO.File]::WriteAllText("$d\RELEASE", '{"account": "DUQ634065", "valid_until": "' + (Get-Date).ToUniversalTime().AddDays(30).ToString('yyyy-MM-dd') + '"}')

# stop everything: create KILL
New-Item -ItemType File -Force (Join-Path $env:LOCALAPPDATA 'TradingEngineX\ibkr\KILL')

# lift the stop: remove KILL and every KILL.* (KILL.txt from Explorer included)
Get-ChildItem (Join-Path $env:LOCALAPPDATA 'TradingEngineX\ibkr') | Where-Object { $_.Name -ieq 'KILL' -or $_.Name -ilike 'KILL.*' } | Remove-Item -Recurse
```

Do not write the release with `echo ... > RELEASE` or `Set-Content`: Windows
PowerShell 5.1 writes a BOM with `>` (UTF-16, or UTF-8 with BOM if the default
encoding was changed) and the ANSI code page with `Set-Content`. The executor
rejects all of these as `release-invalid` (not UTF-8 JSON). That is safe, but the
release never works. The one-liner above was checked on this machine on
2026-10-17: it reads as `release-ok`, the `KILL` line as `kill-active`.

What the switch does:

* A present `KILL` stops the run with exit 4 and is the only thing that sends a
  global cancel. The cancel (D-17) takes back **all** open orders of the account,
  including orders you placed by hand in TWS. It is sent once per run, the open
  orders are then re-read for up to 10 seconds, and the `kill_cancel` ledger event
  records `sent` and `remaining`.
* An unreadable switch state (`kill-unreadable`, or a `RELEASE` that cannot be
  read) blocks trading with exit 4 but cancels nothing.
* The cancel only works when the gateway's "Read-Only API" switch is off (see
  "Gateway Read-Only switch"); with it on, the cancel is refused and `remaining`
  stays above zero.
* A kill that shows up between two orders stops the second one (no `intent`).
* Known limit: if a run already stopped on a release failure and `KILL` appears
  only afterwards, that run does not cancel; the next run does.

## execute

```
ibkr_executor.py execute AAPL [MSFT ...] [--contracts PATH] [--log-file PATH] [--env-file PATH]
```

At least one ticker is required (no default list). In phase 5 the run is forced
dry: no option lifts that (phase 6 removes only the force). It goes through the
whole chain, writes every decision that survives as an `intent` and completes it
with `dry_complete`; no order leaves the process. Exit 0 with a `dry_complete`
means "this order would have been sent".

Order of the chain, per run and per ticker:

1. run lock (`ledger.jsonl.lock`, exit 7 if held)
2. switch preflight: `RELEASE` and `KILL` (exit 4). This comes before the
   reconciliation on purpose (D-21), so an active kill is not hidden behind exit 6.
3. startup reconciliation of open ledger entries (exit 6 if unresolved)
4. paper-log fetch, preconditions, freshness
5. decision key check (`already_attempted`, `decision_changed`), after freshness
   because the trade date is only known from the local chain
6. contract resolution and tradability
7. position and the source comparisons (they need the resolved `conId`)
8. target calculation
9. size cap
10. session window
11. switch check, whatIf with `orderRef`, switch check
12. second size check, then `intent` (write-ahead, flushed to disk), then the dry
    completion; nothing after the `intent` can refuse the order

Console and log lines start with `execute:` and `ibkr-state=EXECUTE...`. The
ledger is the record of the run; the log is the narrative.

**Size cap.** `MAX_QTY_PER_ORDER = 2`. A planned order above the cap is rejected,
never trimmed: if you hold 5 shares by hand and the rating is Sell, the plan is
`SELL 5`, which ends as `size_cap` (exit 5) and not as a smaller order.

**Session window.** The regular session with a buffer of `SESSION_BUFFER_MINUTES`
at both ends; half days follow `liquidHours` of the contract. Outside the window the
ticker is skipped as `outside_session` (exit 2) before the whatIf.

**Second sources (D-22).** Every fact an order depends on is checked against a
second source. A disagreement stops with its own state (D-11): the account stops the
whole run (exit 8), the others stop only that ticker.

| Fact | First source | Second source |
|---|---|---|
| account | paper guard (`managedAccounts`) | `RELEASE.account`; the echo on the whatIf is optional |
| position | broker positions | fills in the ledger (D-18, narrow rule: a conflict only counts when the ledger holds own fills) |
| already executed | ledger | `orderRef` in open orders, completed orders and executions |
| tradable now | exchange calendar | `liquidHours`; the order status 399 joins in phase 6 |
| order reference | the `orderRef` sent (the decision key) | the `orderRef` echo on the whatIf; optional, but a different one stops the ticker as `source-conflict` before any `intent` |

## Ledger and reconciliation

Files in the state folder: `ledger-dryrun.jsonl` (what phase 5 writes),
`ledger.jsonl` (from phase 6; a dry run never touches it) and
`ledger.jsonl.lock` (the run lock, always this name, also in dry mode).

The ledger is JSONL, one line per event, appended and never rewritten. Events:
`run_start`, `switch_check`, `reconcile`, `intent`, `dry_complete`, `placed`,
`filled`, `partial`, `rejected`, `skipped` (always with a `reason`), `kill_cancel`,
`run_end`. An attempt is the `intent`: per decision key (`trade_date|ticker`) there
is at most one, and the first version wins. A second run of the same key is
`already_attempted`; if the rating changed since, it is `decision_changed`. A
`skipped` before the intent does not use the key up.

Reasons of a `skipped` ticker:

| `reason` | Comes from | Exit |
|---|---|---|
| `hold`, `review`, `tolerance` | decision states of phase 4 | 2 / 2 / 0 |
| `stale` | decision older or newer than the execution session | 2 |
| `not_tradable` | resolution, drift, `liquidHours` unknown, no valid decision key (`invalid-decision-key`) | 2 |
| `outside_session` | session window | 2 |
| `size_cap` | planned quantity above `MAX_QTY_PER_ORDER` | 5 |
| `kill_switch` | any `release-*` or `kill-*` state | 4 |
| `source_conflict` | position, already-executed, calendar or `orderRef` echo sources disagree | 2 |
| `already_attempted` | the key has an `intent` already | 2 |
| `decision_changed` | the key has an `intent` for another rating | 2 |
| `foreign_open_order` | an open order not from this ledger | 2 |

`weekend_gap` is not a reason: it is a flag (with `gap_days`) on the entry when a
calendar gap over a weekend or holiday separates the decision from the session; the
decision is still fresh.

**Torn tail.** A crash can cut the last line. That line is tolerated; the first
append after it carries `seals_torn_line` with the number of the cut line. A broken
line directly followed by its seal is fine anywhere; every other defect in the
middle of the file is exit 6 (`ledger-corrupt`). The same holds within a run: when
an append fails midway (full disk, network drive), the next append of that run (the
error path's `run_end`) first checks the end of the file and seals a cut-off line;
if that append fails too, the run logs `LEDGER_APPEND_FAILED` and ends with the
original error.

**Reconciliation.** Before any new order, each open entry (an `intent` or `placed`
without an end) is resolved against open orders, completed orders and executions by
its `orderRef`. A clear case writes `placed`, `filled`, `partial` or `rejected`
with `source: reconcile`. In the live ledger, a crash after the `intent` that left
no trace at the broker is not "already attempted": it is exit 6 on the next run
(`no_trace`), as are a double hit (`collision`) and contradicting sources
(`contradiction`). In the dry-run ledger an `intent` is never sent, so an open dry
`intent` without any trace at the broker is resolved as `never_sent`: the
`reconcile` line carries that outcome, a `rejected` line with `state: never-sent`
closes the entry, and the run goes on without exit 6 (its key stays used up). A
collision or contradiction stays exit 6 in both ledgers.

**Resolving exit 6 (`reconcile-unresolved`, D-19).**

1. Read the console message: it names the key and what each source found.
2. Look at the three sources yourself:
   `.venv\Scripts\python.exe scripts\smoke\ibkr_order_probe.py --history`
   prints open orders, completed orders and executions as JSON. Check TWS too.
3. In dry mode, once you know the dry intent can be discarded, rename
   `ledger-dryrun.jsonl` (for instance to `ledger-dryrun.jsonl.bak`). Never edit or
   delete lines inside it.
4. A `--resolve` flag that records a `resolved` event comes with phase 6.

### States (phase 5)

| State | Exit | Meaning |
|---|---|---|
| `dry-complete` | 0 | the dry run reached its end for this ticker; nothing was sent |
| `kill-absent` | 0 | no KILL file |
| `release-ok` | 0 | the release file is valid |
| `not-dry` | 1 | the placer is not dry; phase 5 refuses to run |
| `state-in-git-tree` | 1 | a state path lies inside a git work tree; refused |
| `already-attempted` | 2 | the decision key has an `intent` already |
| `decision-changed` | 2 | the decision key has an `intent` for another rating |
| `invalid-decision-key` | 2 | no decision key can be built for the ticker (for instance `^GSPC`); only this ticker stops |
| `outside-session` | 2 | outside the regular session with its buffer |
| `source-conflict` | 2 | two sources disagree on position, already-executed, tradability or the `orderRef` echo; this ticker stops |
| `kill-active` | 4 | a KILL file exists (`KILL` or `KILL.*`, any case); global cancel |
| `kill-unreadable` | 4 | the state of KILL cannot be read (or the state folder cannot be listed); trading stops, nothing is cancelled |
| `release-account-mismatch` | 4 | the release is for another account |
| `release-expired` | 4 | `valid_until` lies in the past (UTC) |
| `release-invalid` | 4 | not UTF-8 JSON, wrong keys or a bad date |
| `release-missing` | 4 | no RELEASE file |
| `release-unreadable` | 4 | the RELEASE file cannot be read |
| `size-cap` | 5 | planned quantity above `MAX_QTY_PER_ORDER`; rejected, never trimmed |
| `ledger-corrupt` | 6 | the ledger has a defect that is not a torn tail |
| `reconcile-unresolved` | 6 | an open ledger entry cannot be resolved against the broker |
| `lock-error` | 7 | the lock attempt itself failed |
| `lock-held` | 7 | another run holds the lock |
| `account-conflict` | 8 | account sources disagree; the whole run stops |

Source: `EXIT_BY_STATE` in `scripts/ibkr_guards.py`; a test keeps the table in
step with it. The run exit is the worst of these by the rank under "Exit codes".

## Commands

```
:: dry run: decision from paper-log to a whatIf preview, sends nothing
python scripts/ibkr_executor.py preview AAPL

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

## First resolve run

Four `resolve` runs against the running paper gateway (account `DUQ634065`),
executed by the plan-03-06 executor agent from the repository root; each run
once, no retry, no other command against the gateway.

| | |
|---|---|
| Date | 2026-10-12, 20:09:45 – 20:09:59 local time (CEST), 14:09 in New York (EDT) |
| Read-Only API | on (table above) |
| Market data type | `ibkr-state=MARKET_DATA_TYPE detail="delayed (3)"` on every connected run |

**(a)** `resolve --init AAPL MSFT NVDA` - exit **0**

```
contracts: 3 change(s) written -> C:\Users\admin\AppData\Local\TradingEngineX\ibkr\contracts.json
resolve: AAPL ok conId=265598 NASDAQ/USD/AAPL tradable until 2026-10-12T15:45:00-04:00
resolve: MSFT ok conId=272093 NASDAQ/USD/MSFT tradable until 2026-10-12T15:45:00-04:00
resolve: NVDA ok conId=4815747 NASDAQ/USD/NVDA tradable until 2026-10-12T15:45:00-04:00
```

Learned identities (log: `CONTRACT_LEARNED`, tradingClass NMS for all three):
AAPL 265598, MSFT 272093, NVDA 4815747, each `primaryExchange=NASDAQ`,
`currency=USD`, `localSymbol` = symbol. `contracts-history.jsonl` got three
`init` lines (3 lines in total).

**(b)** `resolve AAPL MSFT NVDA --out ...\resolve.json` - exit **0**; the same
three `ok` lines with the same conIds. No new history line (still 3), no
`CONTRACT_LEARNED`: the identities were checked by `conId` and exchange.

**(c)** `resolve XYZQ ^GSPC XAUUSD+` - exit **2**

```
resolve: 'XYZQ' not-mapped - 'XYZQ': no entry in the contract table; nothing tried
resolve: ^GSPC not-allowed - '^GSPC': secType IND is not in the allow-list {STK}
resolve: XAUUSD+ not-allowed - 'XAUUSD+': secType CMDTY is not in the allow-list {STK}
```

No `CONNECTED` line in the log for this run: nothing reached the gateway.

**(d)** drift check on a COPY of `contracts.json` (AAPL `conId` set to 999999),
`resolve AAPL --contracts <copy>` - exit **2**

```
resolve: AAPL drift - ticker=AAPL fields=conId stored=conId=999999/primaryExchange=NASDAQ/currency=USD/localSymbol=AAPL seen=none (persisted conId unknown to the gateway); check, then resolve --rebaseline AAPL
```

The gateway does not know 999999 (`ibkr-state=CONTRACT_NOT_FOUND code=200`), so
the drift line says `seen=none` instead of naming 265598; log:
`ibkr-state=CONTRACT_DRIFT` at ERROR. The real `contracts.json` was
unchanged by the drift check (SHA-256 identical before and after).

Observed gateway states: `FARM_OK` 2104 (eufarm) and 2158 (secdefeu) at INFO,
`UNKNOWN` 2107 (euhmds, inactive but available on demand) at WARNING, as in
"First real run". 10167 did not appear in these runs. No `orderStatus`,
`newOrder` or `ReadOnlyViolation` line in the log.

Not covered by this run: the Saturday run (`closed`, D-24 against D-29) is an
open verification item.

## See also

* `scripts/PAPER_RUN.md` — the daily analysis run.
* `scripts/STATE_OPERATIONS.md` — what the runs leave on disk.
* `.planning/ibkr-konto-befund.md` — the account findings of phase 1 (port,
  read-only proof, marker 321).
