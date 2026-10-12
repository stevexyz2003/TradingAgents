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
`_WRITE_CALLS` in `scripts/ibkr_broker.py:44`) are replaced by a refusing
function before the first byte goes to the gateway
(`scripts/ibkr_broker.py:241`). The client parameter `readonly=True`
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

Open observation (2026-10-12, before the first real run): the gateway process
listened on `:::7497`, i.e. on all interfaces, not only on `127.0.0.1`. Whether
"Allow connections from localhost only" is set in the gateway was **not**
confirmed by the operator; this manual does not claim that it is.

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
| 2 | `EXIT_PRECONDITION` | precondition not met (reserved for later phases) |
| 3 | `EXIT_GATEWAY` | gateway/session not reachable |
| 4 | `EXIT_KILL_SWITCH` | kill switch active or release missing (reserved for later phases) |
| 5 | `EXIT_REJECTED` | order rejected (reserved for later phases) |
| 6 | `EXIT_RECONCILE` | reconciliation unresolved, run aborted (reserved for later phases) |
| 7 | `EXIT_LOCKED` | lock not acquired (second instance), clean exit (reserved for later phases) |
| 8 | `EXIT_ACCOUNT_GUARD` | account guard violated (managedAccounts != ["DUQ634065"]) |
| 20 | `EXIT_NO_CREDENTIALS` | IBKR settings missing or unreadable - same meaning as `EXIT_NO_CREDENTIALS` in `daily_paper_run.py` |

Code 3 means "gateway" here, unlike `EXIT_RUN_FAILED` (3) in the paper run.
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
| 10089, 10090 | `MARKET_DATA_NOT_SUBSCRIBED` |
| 2172 | `GATEWAY_VERSION_EXPIRING` |
| any other | `UNKNOWN` |

Source: `STATE_BY_CODE`, `scripts/ibkr_broker.py:49`; INFO codes at `:75`.
502, 504 and 507 never arrive as events from the client library; the adapter
derives them from the exceptions of the connect (refused/OS error → 502,
connection error → 504, reset/EOF → 507).

States without a gateway code: `CONNECT_TIMEOUT`, `REQUEST_TIMEOUT`,
`PROBE_TIMEOUT`, `PROBE_FAILED`, `SNAPSHOT_INCOMPLETE`, `HEALTHY`, and from
the executor `ACCOUNT_GUARD_VIOLATED`, `SETTINGS_MISSING`, `CONFIG_INVALID`,
`LIBRARY_MISSING`, `OUTPUT_INVALID`, `UNEXPECTED`.

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
2. Connect with `readonly=True`, clientId 20001 and no startup fetch; timeouts
   10 s connect, 10 s per request, 5 s probe (`scripts/ibkr_broker.py:37-41`).
3. Paper guard: `managedAccounts()` must be exactly `["DUQ634065"]` — a foreign
   account, a superset or an empty list disconnects and ends with exit 8
   (`scripts/ibkr_broker.py:294`).
4. Health probe (above); unhealthy → exit 3, no file.
5. Positions and `TotalCashValue` (EUR), asked fresh on every run
   (`positions()`, `scripts/ibkr_broker.py:347`). Average prices in another
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

## Commands

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
the CI run never passes it.

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
* The gateway listened on `:::7497` (all interfaces); see the open observation
  under "Gateway Read-Only switch".

## See also

* `scripts/PAPER_RUN.md` — the daily analysis run.
* `scripts/STATE_OPERATIONS.md` — what the runs leave on disk.
* `.planning/ibkr-konto-befund.md` — the account findings of phase 1 (port,
  read-only proof, marker 321).
