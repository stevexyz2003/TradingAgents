#!/usr/bin/env python3
"""IBKR paper executor for DUQ634065, local operator tooling, milestone M2.

Operational tooling, not part of the ``tradingagents`` library. Phase 2 reads
only: the ``account`` command connects through the adapter in
``scripts/ibkr_broker.py``, checks the paper-account guard and the session's
liveness, reads positions and cash, and writes them as a ``PortfolioContext``
JSON, dated by an ``as_of`` key, that ``scripts/daily_paper_run.py --portfolio``
accepts while it is fresh. Every run first removes the ``--out`` file of an
earlier run, so a failed run leaves no book behind.

Phase 3 adds ``resolve``: it turns tickers into broker contracts through the pure
chain in ``scripts/ibkr_contracts.py`` (mapping table, allow-list, persisted
identity, tradability, session) and reports one line per ticker. It connects
only when a ticker survives the local checks. The clock is injected: tests pass
``main(clock=...)``.

Phase 4 adds ``preview``, a dry run that sends nothing: it reads the ``paper-log``
branch (fetch, copy, ``state_maintenance.verify``), checks the preconditions and the
freshness of each ticker's newest decision, and only for a ticker that survives them
contacts the gateway: resolution and session, position by ``conId``, foreign open
orders, the target calculation and a ``whatIf`` preview, judged for rejection, halt,
time in force and budget. The result is one console line and one log line per ticker
(the read commit SHA in every log line) and an atomic dry-run JSON. The clock, the
paper-log source and the session calendar are injected: tests pass
``main(clock=..., paper_log_factory=..., calendar=...)``.

Phase 5 adds ``execute``: the guarded chain to a dry completion. It runs the same local
and gateway chain as ``preview``, but every decision that survives is first written to the
ledger as an ``intent`` (write-ahead, fsync, ``orderRef`` == decision key, the paper-log
SHA as provenance) and only then completed by the placer. In phase 5 the placer is forced
dry: it writes ``dry_complete`` and sends nothing. Dry runs write ``ledger-dryrun.jsonl`` in
the state folder, never ``ledger.jsonl``; a state folder inside a git work tree is refused.

Phase 6 adds ``--live`` to ``execute``: dry unless that flag is given. With it the live placer
sends one market order per intent, waits for the fill, checks the result against the intent
and writes the fills to ``ledger.jsonl`` in the same run; any deviation ends the whole run.

Operating manual: ``scripts/IBKR_EXECUTION.md``.

    ibkr_executor.py account --out PATH [--log-file PATH] [--env-file PATH]
    ibkr_executor.py resolve TICKER... [--contracts PATH] [--init | --rebaseline TICKER]
                             [--out PATH] [--log-file PATH] [--env-file PATH]
    ibkr_executor.py preview TICKER... [--contracts PATH] [--out PATH] [--log-file PATH]
                             [--env-file PATH]
    ibkr_executor.py execute TICKER... [--live] [--contracts PATH] [--log-file PATH]
                             [--env-file PATH]
    ibkr_executor.py execute --resolve KEY=never_sent --note TEXT [--log-file PATH]
                             [--env-file PATH]

Settings come from the ``.env`` at the repository root (a fixed path, not the
current directory) or from ``--env-file``. Only IBKR_HOST, IBKR_PORT,
IBKR_ACCOUNT_ID and IBKR_TRADING_MODE are taken from it, plus the optional
IBKR_PAPER_LOG_REMOTE (default fork) and IBKR_PAPER_LOG_BRANCH (default paper-log) for
``preview``; the API needs no user name or password, and this command copies neither.

Every run writes a UTF-8 log file; the console gets one summary or error line.

Exit codes:
    0   ok, including "nothing to do"
    1   configuration error - nothing was done
    2   precondition not met - a ticker was rejected (including Hold, per D-16), the
        paper-log is unavailable, or contracts.json is missing (resolve, preview)
    3   gateway/session not reachable
    4   kill switch active or release missing/unreadable/invalid
    5   order preview rejected (whatIf): empty, rejected, halted, over budget, tif
    6   ledger corrupt or reconciliation unresolved
    7   run lock not acquired (second instance), clean exit
    8   account guard violated (managedAccounts != ["DUQ634065"])
    9   fill timeout: the order is placed but not filled within the wait; it stays open (D-08)
    10  post-order mismatch: the state at IBKR after the order differs from the intent (D-09, REQ-65)
    20  IBKR settings missing or unreadable - same meaning as EXIT_NO_CREDENTIALS in daily_paper_run.py

Code 3 means "gateway" here, unlike EXIT_RUN_FAILED (3) in the paper run.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

from tradingagents.dataflows.files import locked
from tradingagents.memory.log import TradingMemoryLog
from tradingagents.portfolio import PortfolioContext, Position, load_portfolio

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_PRECONDITION = 2
EXIT_GATEWAY = 3
EXIT_KILL_SWITCH = 4
EXIT_REJECTED = 5
EXIT_RECONCILE = 6
EXIT_LOCKED = 7
EXIT_ACCOUNT_GUARD = 8
EXIT_FILL_TIMEOUT = 9
EXIT_POST_ORDER = 10
EXIT_NO_CREDENTIALS = 20

#: The settings the command needs (D-06). User name and password stay out:
#: the API does not need them, so they are neither copied nor logged.
REQUIRED_ENV = ("IBKR_HOST", "IBKR_PORT", "IBKR_ACCOUNT_ID")
#: Optional; when set it must say paper.
TRADING_MODE_ENV = "IBKR_TRADING_MODE"
EXPECTED_TRADING_MODE = "paper"

#: Optional: where ``preview`` reads the paper-log branch from (D-03).
PAPER_LOG_REMOTE_ENV = "IBKR_PAPER_LOG_REMOTE"
PAPER_LOG_BRANCH_ENV = "IBKR_PAPER_LOG_BRANCH"
OPTIONAL_ENV_DEFAULTS = {PAPER_LOG_REMOTE_ENV: "fork", PAPER_LOG_BRANCH_ENV: "paper-log"}

#: Top-level key of the portfolio JSON that dates the snapshot (UTC, ISO 8601).
#: Same literal as ``PORTFOLIO_AS_OF_KEY`` in daily_paper_run.py; a test keeps them in step.
AS_OF_KEY = "as_of"

#: The repository's .env, by a fixed path so the current directory does not matter.
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

REPO_ROOT = Path(__file__).resolve().parents[1]

_BROKER_PATH = Path(__file__).with_name("ibkr_broker.py")
_CONTRACTS_PATH = Path(__file__).with_name("ibkr_contracts.py")
_DECISION_PATH = Path(__file__).with_name("ibkr_decision.py")
_PAPERLOG_PATH = Path(__file__).with_name("ibkr_paperlog.py")
_STATE_MAINTENANCE_PATH = Path(__file__).with_name("state_maintenance.py")
_GUARDS_PATH = Path(__file__).with_name("ibkr_guards.py")
_LEDGER_PATH = Path(__file__).with_name("ibkr_ledger.py")

#: How long the live placer waits for the fill of one market order (D-08). The deadline never
#: cancels: a timeout is reported and the state is read again.
FILL_TIMEOUT_S = 60.0

#: After a fill the broker's order history is read up to this many times, this far apart: its
#: three sources (open, completed, executions) are not read atomically (Pitfall 8).
POST_ORDER_READS = 5
POST_ORDER_RETRY_S = 1.0

#: After the global cancel the open orders are read again for this long, every interval:
#: the request is fire-and-forget, only the re-read proves it worked (Pitfall 5).
KILL_RECHECK_SECONDS = 10.0
KILL_RECHECK_INTERVAL_S = 0.5
_sleep = time.sleep

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOGGER_NAME = "ibkr_executor"

#: The file handler this module put on the root logger, and the level before it.
_FILE_HANDLER: logging.FileHandler | None = None
_PREVIOUS_ROOT_LEVEL: int | None = None


class ConfigError(Exception):
    """Invalid configuration - nothing was done."""


class MissingSettings(Exception):
    """The IBKR settings are missing or unreadable - nothing was done."""


class OutputError(Exception):
    """The portfolio JSON could not be written or did not validate."""


class _RunAbort(Exception):
    """A run-level stop of ``preview``: no ticker verdicts, one named state."""

    def __init__(self, state: str, detail: str):
        super().__init__(f"{state}: {detail}")
        self.state = state
        self.detail = detail


def load_broker_module():
    """The adapter module, loaded once under the name ``ibkr_broker``.

    Registered in ``sys.modules`` before it runs, the same rule as
    ``tests/ibkr_fakes.load_broker()``, so the executor and the tests share
    one set of exception classes.
    """
    if "ibkr_broker" in sys.modules:
        return sys.modules["ibkr_broker"]
    spec = importlib.util.spec_from_file_location("ibkr_broker", _BROKER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_broker"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_broker", None)
        raise
    return module


def load_contracts_module():
    """The resolver module, loaded once under the name ``ibkr_contracts``.

    Same rule as ``load_broker_module``: registered in ``sys.modules`` before it
    runs, and removed again if it fails to load.
    """
    if "ibkr_contracts" in sys.modules:
        return sys.modules["ibkr_contracts"]
    spec = importlib.util.spec_from_file_location("ibkr_contracts", _CONTRACTS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_contracts"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_contracts", None)
        raise
    return module


def _load_script_module(name: str, path: Path):
    """Load ``path`` once under ``name``; registered before it runs, removed if it fails."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def load_decision_module():
    """The decision logic, loaded once under the name ``ibkr_decision``."""
    return _load_script_module("ibkr_decision", _DECISION_PATH)


def load_paperlog_module():
    """The paper-log reader, loaded once under the name ``ibkr_paperlog``."""
    return _load_script_module("ibkr_paperlog", _PAPERLOG_PATH)


def load_state_maintenance_module():
    """The state tool whose ``verify`` checks the log copy, loaded as ``state_maintenance``."""
    return _load_script_module("state_maintenance", _STATE_MAINTENANCE_PATH)


def load_guards_module():
    """The guard building blocks, loaded once under the name ``ibkr_guards``."""
    return _load_script_module("ibkr_guards", _GUARDS_PATH)


def load_ledger_module():
    """The ledger, loaded once under the name ``ibkr_ledger``."""
    return _load_script_module("ibkr_ledger", _LEDGER_PATH)


def _ibkr_base(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "TradingEngineX" / "ibkr"
    return Path.home() / ".tradingenginex" / "ibkr"


def default_preview_file(environ=None) -> Path:
    """The default dry-run record, outside every repository."""
    return _ibkr_base(environ) / "preview.json"


def default_release_file(environ=None) -> Path:
    """The operator's release file in the state folder."""
    return _ibkr_base(environ) / "RELEASE"


def default_kill_file(environ=None) -> Path:
    """The kill-switch file in the state folder."""
    return _ibkr_base(environ) / "KILL"


def default_ledger_file(environ=None) -> Path:
    """The live ledger; a dry run never writes it."""
    return _ibkr_base(environ) / "ledger.jsonl"


def default_dryrun_ledger_file(environ=None) -> Path:
    """The dry-run ledger, the only ledger phase 5 writes."""
    return _ibkr_base(environ) / "ledger-dryrun.jsonl"


def default_paper_log_copy(environ=None) -> Path:
    """Where the byte-exact copy of ``decision-log.md`` is kept for ``verify``."""
    return _ibkr_base(environ) / "paper-log" / "decision-log.md"


def default_contracts_file(environ=None) -> Path:
    """The default contracts file, outside every git tree (D-11)."""
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "TradingEngineX" / "ibkr" / "contracts.json"
    return Path.home() / ".tradingenginex" / "ibkr" / "contracts.json"


def default_log_file(environ=None) -> Path:
    """The default log path, outside every git tree."""
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "TradingEngineX" / "ibkr" / "logs" / "ibkr_executor.log"
    return Path.home() / ".tradingenginex" / "ibkr" / "logs" / "ibkr_executor.log"


# --- settings -----------------------------------------------------------------------


def read_settings(env_file: Path) -> dict[str, str]:
    """The IBKR settings from ``env_file``: the required keys and the trading mode only."""
    env_file = Path(env_file)
    if not env_file.is_file():
        raise MissingSettings(f"settings file not readable: {env_file}")
    try:
        values = dotenv_values(env_file, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MissingSettings(
            f"settings file not readable: {env_file} ({type(exc).__name__})"
        ) from exc
    wanted = (*REQUIRED_ENV, TRADING_MODE_ENV, *OPTIONAL_ENV_DEFAULTS)
    settings = {key: values[key].strip() for key in wanted if isinstance(values.get(key), str)}
    missing = [key for key in REQUIRED_ENV if not settings.get(key)]
    if missing:
        raise MissingSettings("missing IBKR settings: " + ", ".join(missing))
    return settings


def validate_settings(raw: dict[str, str], expected_account: str) -> tuple[str, int, str]:
    """Host, port and account, checked against the executor's own constants."""
    host = raw["IBKR_HOST"]
    try:
        port = int(raw["IBKR_PORT"])
    except ValueError:
        raise ConfigError("IBKR_PORT is not an integer") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"IBKR_PORT {port} is outside 1..65535")
    account = raw["IBKR_ACCOUNT_ID"]
    if account != expected_account:
        raise ConfigError(
            f"IBKR_ACCOUNT_ID {account!r} does not match the executor's expected "
            f"account {expected_account}"
        )
    mode = raw.get(TRADING_MODE_ENV)
    if mode and mode.lower() != EXPECTED_TRADING_MODE:
        raise ConfigError(
            f"{TRADING_MODE_ENV} is {mode!r}; this executor runs {EXPECTED_TRADING_MODE} only"
        )
    return host, port, account


def paper_log_settings(settings: dict[str, str], paperlog_mod) -> tuple[str, str]:
    """Remote and branch for ``preview``, whitelisted before any command line sees them (D-03)."""
    values = []
    for key, what in ((PAPER_LOG_REMOTE_ENV, "remote"), (PAPER_LOG_BRANCH_ENV, "branch")):
        value = settings.get(key) or OPTIONAL_ENV_DEFAULTS[key]
        try:
            values.append(paperlog_mod.validate_ref_name(value, what))
        except ValueError as exc:
            raise ConfigError(f"{key}: {exc}") from exc
    return values[0], values[1]


# --- logging ------------------------------------------------------------------------


def setup_logging(log_file: Path) -> logging.Logger:
    """One UTF-8 file handler on the root logger; the first line names the file.

    The executor's, the adapter's and the IBKR client library's loggers all
    propagate to the root, so all of them land in this one file, and since the
    root now has a handler, ``logging.lastResort`` never prints to stderr.
    Only the handler this function added earlier is replaced; other root
    handlers stay untouched.
    """
    global _FILE_HANDLER, _PREVIOUS_ROOT_LEVEL
    close_logging()
    path = Path(log_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    _PREVIOUS_ROOT_LEVEL = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _FILE_HANDLER = handler
    logger = logging.getLogger(_LOGGER_NAME)
    logger.info("log file: %s", path)
    return logger


def close_logging() -> None:
    """Remove and close the file handler of ``setup_logging``; restore the root level."""
    global _FILE_HANDLER, _PREVIOUS_ROOT_LEVEL
    root = logging.getLogger()
    if _FILE_HANDLER is not None:
        root.removeHandler(_FILE_HANDLER)
        _FILE_HANDLER.close()
        _FILE_HANDLER = None
    if _PREVIOUS_ROOT_LEVEL is not None:
        root.setLevel(_PREVIOUS_ROOT_LEVEL)
        _PREVIOUS_ROOT_LEVEL = None


def _log_path() -> str:
    return _FILE_HANDLER.baseFilename if _FILE_HANDLER is not None else "the log file"


def _fail(logger: logging.Logger, code: int, log_line: str, console: str) -> int:
    logger.error(log_line)
    print(f"error: {console}", file=sys.stderr)
    return code


# --- the account command ------------------------------------------------------------


def snapshot_to_portfolio(snapshot, logger: logging.Logger) -> PortfolioContext:
    """The broker snapshot as the broker-neutral ``PortfolioContext``.

    ``PortfolioContext`` carries one currency label, the cash currency. An
    average price in another currency (USD stocks in the EUR account) would sit
    under the wrong label, so it is dropped until FX conversion lands in phase 4.
    For non-stock positions the average cost includes the multiplier, so no
    price is kept there either (allow-list in phase 3).
    """
    positions = []
    for held in snapshot.positions:
        if held.sec_type == "STK" and held.currency == snapshot.cash_currency:
            positions.append(
                Position(ticker=held.symbol, quantity=held.quantity, average_price=held.avg_cost)
            )
        elif held.sec_type == "STK":
            logger.warning(
                "average price dropped for %s: position currency %s != cash currency %s "
                "(no FX before phase 4)",
                held.symbol,
                held.currency,
                snapshot.cash_currency,
            )
            positions.append(Position(ticker=held.symbol, quantity=held.quantity))
        else:
            ticker = held.local_symbol or held.symbol
            logger.warning(
                "average price dropped for %s: sec_type %s is not a stock "
                "(average cost includes the multiplier)",
                ticker,
                held.sec_type,
            )
            positions.append(Position(ticker=ticker, quantity=held.quantity))
    return PortfolioContext(
        cash=snapshot.cash, currency=snapshot.cash_currency, positions=positions
    )


def portfolio_json(ctx: PortfolioContext, as_of: datetime) -> str:
    """The file content: the ``PortfolioContext`` fields plus ``as_of`` (UTC, ISO 8601).

    ``as_of`` is an extra top-level key. ``PortfolioContext`` ignores unknown
    keys, so ``load_portfolio()`` reads the file unchanged and the book's
    fingerprint does not move; ``daily_paper_run.py --portfolio`` reads the key
    as its proof that the book is fresh (CR-02).
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must carry a time zone")
    data = ctx.model_dump(mode="json")
    data[AS_OF_KEY] = as_of.astimezone(UTC).isoformat()
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_portfolio_atomic(
    ctx: PortfolioContext, out: Path, *, as_of: datetime, check=None
) -> None:
    """Write ``out`` through a uniquely named temp file beside it, then move it into place.

    ``check`` (if given) reads the temp file before the move, so a file that
    does not validate never replaces the previous one. Unlike the cache helper
    in ``tradingagents/dataflows/files.py`` nothing is swallowed: a
    ``PermissionError`` is raised like every other error, and the temp file
    is removed either way.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_name(f"{out.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(portfolio_json(ctx, as_of), encoding="utf-8")
        if check is not None:
            check(temp)
        os.replace(temp, out)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def run_account(args, settings, broker_mod, broker_factory, logger, progress=None) -> int:
    """Connect, check liveness, read the book, then write and cross-check the JSON.

    The JSON is written only on the exit-0 path and only after the session is
    closed; the caller has already removed any earlier file, so a failed run
    leaves none. ``progress["connecting"]`` tells the caller that the connect
    has started, so a socket and a handshake may have stood; from then on no
    error means "nothing was done". ``progress["connected"]`` marks a session
    that passed the guard.
    """
    host, port, _account = settings
    out = Path(args.out).resolve()
    progress = {} if progress is None else progress
    adapter = broker_factory(host, port, logger)
    progress["connecting"] = True
    with adapter as broker:
        progress["connected"] = True
        health = broker.health()
        if not health.ok:
            line = f'ibkr-state={health.state} code=- detail="{health.detail}"'
            logger.error(line)
            print(f"error: {line}", file=sys.stderr)
            return EXIT_GATEWAY
        snapshot = broker.positions()
    logger.info(
        "ibkr-snapshot account=%s as_of=%s positions=%d cash=%s %s clientId=%s",
        snapshot.account,
        snapshot.as_of.isoformat(),
        len(snapshot.positions),
        snapshot.cash,
        snapshot.cash_currency,
        broker_mod.EXECUTOR_CLIENT_ID,
    )
    try:
        ctx = snapshot_to_portfolio(snapshot, logger)
        write_portfolio_atomic(ctx, out, as_of=snapshot.as_of, check=load_portfolio)
        load_portfolio(out)  # cross-check of the file in place (criterion 1)
    except (OSError, ValueError) as exc:
        raise OutputError(f"{out}: {type(exc).__name__}: {exc}") from exc
    logger.info("portfolio written: %s", out)
    print(f"account: {len(ctx.positions)} position(s), cash {ctx.cash} {ctx.currency} -> {out}")
    return EXIT_OK


# --- the resolve command ------------------------------------------------------------


def _result_line(result, buffer_minutes: int) -> str:
    """The console line of one resolve result."""
    state = result.state
    if result.identity is None:
        name = repr(result.ticker) if state == "not-mapped" else result.ticker
        return f"resolve: {name} {state} - {result.detail}"
    ident = result.identity
    head = (
        f"resolve: {result.ticker} {state} conId={ident.con_id} "
        f"{ident.primary_exchange}/{ident.currency}/{ident.local_symbol}"
    )
    if state == "ok":
        until = result.window.end - timedelta(minutes=buffer_minutes)
        return f"{head} tradable until {until.isoformat()}"
    when = result.next_open.isoformat() if result.next_open else "unknown"
    return f"{head} next window {when}"


def run_resolve(
    args, contracts_mod, broker_mod, broker_factory, logger, progress, now_utc: datetime
) -> int:
    """Resolve the tickers; connect only when one of them needs the gateway.

    Exit 2 when any ticker is rejected, after every ticker was checked and
    reported. The contracts file is read before anything else and written only
    after the gateway session is closed.
    """
    contracts_path = Path(args.contracts or default_contracts_file()).resolve()
    if args.out is not None:
        out = Path(args.out).resolve()
        try:
            _discard_previous(out, logger)
        except OSError as exc:
            return _fail(
                logger,
                EXIT_CONFIG,
                f"ibkr-state=OUTPUT_INVALID previous file not removable: {out} "
                f"({type(exc).__name__}: {exc})",
                f"previous resolve output not removable: {out} ({type(exc).__name__})",
            )

    if args.init:
        mode = contracts_mod.MODE_INIT
        if contracts_path.exists():
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=CONTRACTS_EXIST {contracts_path} exists; --init never overwrites",
                f"{contracts_path} exists; check it, then use resolve --rebaseline TICKER",
            )
        history = contracts_mod.contracts_history_path(contracts_path)
        if history.exists() and history.stat().st_size > 0:
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=CONTRACTS_HISTORY_EXISTS {history}; --init would reset identity",
                f"{contracts_path} is missing but {history} exists; restore contracts.json manually",
            )
        contracts = None
        contracts_before = None
    else:
        mode = contracts_mod.MODE_REBASELINE if args.rebaseline else contracts_mod.MODE_RUN
        try:
            contracts_before = contracts_path.read_bytes()
            contracts = contracts_mod.load_contracts_file(contracts_path)
        except (FileNotFoundError, contracts_mod.ContractsFileMissing):
            history = contracts_mod.contracts_history_path(contracts_path)
            hint = (
                f"{contracts_path} not found; {history} exists, restore contracts.json manually"
                if history.exists() and history.stat().st_size > 0
                else f"{contracts_path} not found; create it with: resolve --init AAPL MSFT NVDA"
            )
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=CONTRACTS_MISSING {hint}",
                hint,
            )
        except OSError as exc:
            return _fail(
                logger,
                EXIT_CONFIG,
                f"ibkr-state=CONTRACTS_INVALID {contracts_path}: unreadable ({type(exc).__name__})",
                f"contracts file: {contracts_path}: unreadable ({type(exc).__name__})",
            )
        except contracts_mod.ContractsFileError as exc:
            return _fail(
                logger, EXIT_CONFIG, f"ibkr-state=CONTRACTS_INVALID {exc}", f"contracts file: {exc}"
            )
        if args.rebaseline and args.rebaseline not in contracts:
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=REBASELINE_UNKNOWN {args.rebaseline!r} has no stored contract",
                f"{args.rebaseline!r} has no stored contract to re-baseline",
            )

    anchor = broker_mod.PROBE_CON_ID if args.init else None
    common = {
        "contracts": contracts,
        "now_utc": now_utc,
        "logger": logger,
        "mode": mode,
        "rebaseline": args.rebaseline,
        "anchor_con_id": anchor,
    }
    try:
        if not contracts_mod.needs_broker(args.tickers):
            outcome = contracts_mod.resolve_all(args.tickers, broker=None, **common)
        else:
            raw = read_settings(args.env_file)
            host, port, _account = validate_settings(raw, broker_mod.EXPECTED_ACCOUNT)
            adapter = broker_factory(host, port, logger)
            progress["connecting"] = True
            with adapter as broker:
                progress["connected"] = True
                health = broker.health()
                if not health.ok:
                    line = f'ibkr-state={health.state} code=- detail="{health.detail}"'
                    logger.error(line)
                    print(f"error: {line}", file=sys.stderr)
                    return EXIT_GATEWAY
                outcome = contracts_mod.resolve_all(args.tickers, broker=broker, **common)
    except contracts_mod.AnchorMismatch as exc:
        return _fail(
            logger,
            EXIT_PRECONDITION,
            f"ibkr-state=ANCHOR_MISMATCH expected={exc.expected} seen={exc.seen}",
            str(exc),
        )

    # The gateway session is closed here; only now does anything reach the disk.
    if outcome.events:
        try:
            contracts_mod.commit_contracts(
                contracts_path,
                outcome.contracts,
                outcome.events,
                expected_bytes=contracts_before,
            )
        except (OSError, contracts_mod.ContractsFileError) as exc:
            raise OutputError(f"{contracts_path}: {type(exc).__name__}: {exc}") from exc
        for event in outcome.events:
            logger.info(
                "ibkr-state=CONTRACTS_WRITTEN event=%s ticker=%s conId=%s",
                event.event,
                event.ticker,
                event.new.con_id,
            )
            if event.event == "rebaseline" and event.old is not None:
                print(
                    f"resolve: {event.ticker} rebaselined conId {event.old.con_id} -> "
                    f"{event.new.con_id} (primaryExchange/currency/localSymbol "
                    f"{event.old.primary_exchange}/{event.old.currency}/{event.old.local_symbol}"
                    f" -> {event.new.primary_exchange}/{event.new.currency}/"
                    f"{event.new.local_symbol})"
                )
        print(f"contracts: {len(outcome.events)} change(s) written -> {contracts_path}")

    for result in outcome.results:
        line = _result_line(result, contracts_mod.SESSION_BUFFER_MINUTES)
        print(line)
        state = "RESOLVED" if not result.rejected else "RESOLVE_REJECTED"
        logger.log(
            logging.WARNING if result.rejected else logging.INFO,
            "ibkr-state=%s ticker=%s state=%s detail=%r tradingClass=%s longName=%s",
            state,
            result.ticker,
            result.state,
            result.detail,
            result.trading_class,
            result.long_name,
        )

    if args.out is not None:
        payload = _resolve_payload(outcome, contracts_mod, now_utc)
        try:
            contracts_mod.write_json_atomic(out, payload)
        except OSError as exc:
            raise OutputError(f"{out}: {type(exc).__name__}: {exc}") from exc
        logger.info("resolve output written: %s", out)
    return EXIT_PRECONDITION if outcome.rejected else EXIT_OK


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _resolve_payload(outcome, contracts_mod, now_utc: datetime) -> dict:
    """The ``--out`` content: identities and window bounds, never the broker's hours text."""
    rows = []
    for result in outcome.results:
        ident = result.identity
        rows.append(
            {
                "ticker": result.ticker,
                "state": result.state,
                "detail": result.detail,
                "conId": None if ident is None else ident.con_id,
                "primaryExchange": None if ident is None else ident.primary_exchange,
                "currency": None if ident is None else ident.currency,
                "localSymbol": None if ident is None else ident.local_symbol,
                "window_start": _iso(result.window.start) if result.window else None,
                "window_end": _iso(result.window.end) if result.window else None,
                "next_open": _iso(result.next_open),
            }
        )
    return {
        "schema_version": contracts_mod.SCHEMA_VERSION,
        "as_of": now_utc.isoformat(),
        "results": rows,
    }


# --- command line -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ibkr_executor.py",
        description=(
            "IBKR paper executor for DUQ634065 (read-only in phases 2-4; "
            "phase 4 previews with whatIf and sends nothing; "
            "execute is dry unless --live: guards, ledger, and with --live a market order)."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    account = sub.add_parser("account", help="read positions and cash into a portfolio JSON")
    account.add_argument("--out", type=Path, default=None, help="portfolio JSON (required)")
    account.add_argument("--log-file", type=Path, default=default_log_file())
    account.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)

    resolve = sub.add_parser("resolve", help="resolve tickers to contracts and check tradability")
    resolve.add_argument("tickers", nargs="*", metavar="TICKER")
    resolve.add_argument("--contracts", type=Path, default=None, help="contracts.json path")
    mode = resolve.add_mutually_exclusive_group()
    mode.add_argument("--init", action="store_true", help="create contracts.json (anchor AAPL)")
    mode.add_argument("--rebaseline", metavar="TICKER", help="accept a changed contract")
    resolve.add_argument("--out", type=Path, default=None, help="write the results as JSON")
    resolve.add_argument("--log-file", type=Path, default=default_log_file())
    resolve.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)

    # No date option (D-07): the decision's date comes from the paper-log entry.
    help_text = "dry run: decision from paper-log to a whatIf preview; sends nothing"
    preview = sub.add_parser("preview", help=help_text)
    preview.add_argument("tickers", nargs="*", metavar="TICKER")
    preview.add_argument("--contracts", type=Path, default=None, help="contracts.json path")
    preview.add_argument("--out", type=Path, default=None, help="dry-run record (JSON)")
    preview.add_argument("--log-file", type=Path, default=default_log_file())
    preview.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)

    # ``--live`` per run (phase 6, D-01); no release or date option: RELEASE is a file, the
    # date comes from the paper-log.
    help_execute = "guarded chain: dry by default; --live places market orders on the paper account"
    execute = sub.add_parser("execute", help=help_execute)
    execute.add_argument("tickers", nargs="*", metavar="TICKER")
    execute.add_argument(
        "--live",
        action="store_true",
        help="send real orders to the paper account (needs a valid RELEASE); without it the run is dry",
    )
    execute.add_argument(
        "--resolve",
        metavar="KEY=OUTCOME",
        default=None,
        help=(
            "close an open live intent without a broker trace: KEY=never_sent (needs --note); "
            "takes no TICKER and no --live"
        ),
    )
    execute.add_argument("--note", metavar="TEXT", default=None, help="reason for --resolve")
    execute.add_argument("--contracts", type=Path, default=None, help="contracts.json path")
    execute.add_argument("--log-file", type=Path, default=default_log_file())
    execute.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser


NOTE_MAX = 500


def _split_resolve(value: str) -> tuple[str, str]:
    """``KEY=OUTCOME`` split at the last ``=`` (the key itself never contains one)."""
    key, _, outcome = value.rpartition("=")
    return key, outcome


def _resolve_args_problem(args) -> str | None:
    """Why the ``--resolve`` arguments are unusable (exit 1), or None (D-14, T-06-37)."""
    if args.tickers or args.live:
        return "--resolve takes no TICKER and no --live"
    key, outcome = _split_resolve(args.resolve)
    if outcome != "never_sent":
        return f"--resolve needs KEY=never_sent, got outcome {outcome!r}"
    note = args.note
    if note is None or not note.strip():
        return "--resolve needs --note TEXT (why the order was never sent)"
    if len(note) > NOTE_MAX or not note.isprintable():
        return f"--note must be printable text of at most {NOTE_MAX} characters"
    guards = load_guards_module()
    trade_date, sep, ticker = key.partition(guards.DECISION_KEY_SEPARATOR)
    try:
        if not sep or guards.decision_key(trade_date, ticker) != key:
            raise ValueError(key)
    except ValueError:
        return f"--resolve key {key!r} is not <trade date>{guards.DECISION_KEY_SEPARATOR}<ticker>"
    return None


def main(
    argv: list[str] | None = None,
    *,
    broker_factory=None,
    clock=None,
    paper_log_factory=None,
    calendar=None,
    placer=None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on a usage error and on --help; return a code instead.
        return EXIT_CONFIG if exc.code else EXIT_OK
    clock = clock or (lambda: datetime.now(UTC))

    if not args.command:
        parser.print_usage(sys.stderr)
        print(
            "error: ibkr_executor.py needs a subcommand: account, resolve, preview, execute",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    if args.command == "account" and args.out is None:
        print("error: account needs --out PATH", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "preview" and not args.tickers:
        parser.print_usage(sys.stderr)
        print("error: preview needs at least one TICKER (no default list)", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "execute" and args.resolve is not None:
        problem = _resolve_args_problem(args)
        if problem:
            print(f"error: {problem}", file=sys.stderr)
            return EXIT_CONFIG
    elif args.command == "execute" and args.note is not None:
        print("error: --note belongs to --resolve", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "execute" and args.resolve is None and not args.tickers:
        parser.print_usage(sys.stderr)
        print("error: execute needs at least one TICKER (no default list)", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "resolve":
        if not args.tickers:
            parser.print_usage(sys.stderr)
            print("error: resolve needs at least one TICKER (no default list)", file=sys.stderr)
            return EXIT_CONFIG
        if args.rebaseline and args.rebaseline not in args.tickers:
            print(
                f"error: --rebaseline {args.rebaseline} must be one of the tickers", file=sys.stderr
            )
            return EXIT_CONFIG
        if args.init and "AAPL" not in args.tickers:
            print(
                "error: --init needs AAPL among the tickers: it is the anchor checked "
                "against PROBE_CON_ID",
                file=sys.stderr,
            )
            return EXIT_CONFIG

    try:
        logger = setup_logging(args.log_file)
    except OSError as exc:
        print(f"error: log file not writable: {args.log_file} ({exc})", file=sys.stderr)
        return EXIT_CONFIG
    try:
        if args.command == "account":
            return _account(args, broker_factory, logger)
        if args.command == "preview":
            return _preview(args, broker_factory, logger, clock, paper_log_factory, calendar)
        if args.command == "execute":
            return _execute(
                args, broker_factory, logger, clock, paper_log_factory, calendar, placer
            )
        return _resolve(args, broker_factory, logger, clock)
    finally:
        close_logging()


def _discard_previous(out: Path, logger: logging.Logger) -> None:
    """Remove the file of an earlier run before anything else happens (CR-02).

    A failed run must leave no book behind: the paper run reads whatever file
    is there, and an old one would pass every schema check.
    """
    try:
        out.unlink()
    except FileNotFoundError:
        return
    logger.info("previous output removed: %s", out)


def _guarded(logger, broker_mod, progress, run, output_what: str) -> int:
    """Run ``run()`` and map every failure to its exit code; shared by both commands."""
    try:
        return run()
    except MissingSettings as exc:
        return _fail(logger, EXIT_NO_CREDENTIALS, f"ibkr-state=SETTINGS_MISSING {exc}", str(exc))
    except ConfigError as exc:
        return _fail(logger, EXIT_CONFIG, f"ibkr-state=CONFIG_INVALID {exc}", str(exc))
    except broker_mod.AccountGuardViolation as exc:
        line = f"ibkr-state=ACCOUNT_GUARD_VIOLATED accounts_seen={exc.accounts_seen}"
        return _fail(logger, EXIT_ACCOUNT_GUARD, line, line)
    except broker_mod.ReadOnlyViolation as exc:
        # The barrier held: a write was refused before it reached the gateway.
        # The most safety-relevant event of a read-only run gets its own state.
        line = f'ibkr-state=WRITE_REFUSED code=- detail="{exc}"'
        return _fail(logger, EXIT_GATEWAY, line, line)
    except broker_mod.GatewayUnavailable as exc:
        return _fail(logger, EXIT_GATEWAY, str(exc), str(exc))
    except ImportError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=LIBRARY_MISSING {type(exc).__name__}: {exc}",
            'the IBKR client library is missing - pip install -e ".[ibkr]"',
        )
    except OutputError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=OUTPUT_INVALID {exc}",
            f"{output_what} not written: {exc}",
        )
    except Exception as exc:
        # The traceback goes to the log file only; the console gets one line.
        logger.exception("ibkr-state=UNEXPECTED %s: %s", type(exc).__name__, exc)
        print(
            f"error: unexpected {type(exc).__name__}: {exc} (details in {_log_path()})",
            file=sys.stderr,
        )
        return EXIT_GATEWAY if progress["connecting"] else EXIT_CONFIG


def _account(args, broker_factory, logger) -> int:
    out = Path(args.out).resolve()
    try:
        _discard_previous(out, logger)
    except OSError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=OUTPUT_INVALID previous file not removable: {out} "
            f"({type(exc).__name__}: {exc})",
            f"previous portfolio JSON not removable: {out} ({type(exc).__name__})",
        )
    try:
        raw = read_settings(args.env_file)
    except MissingSettings as exc:
        return _fail(logger, EXIT_NO_CREDENTIALS, f"ibkr-state=SETTINGS_MISSING {exc}", str(exc))
    try:
        broker_mod = load_broker_module()
        settings = validate_settings(raw, broker_mod.EXPECTED_ACCOUNT)
    except ConfigError as exc:
        return _fail(logger, EXIT_CONFIG, f"ibkr-state=CONFIG_INVALID {exc}", str(exc))
    if broker_factory is None:

        def broker_factory(host, port, logger):
            return broker_mod.IbkrBroker(host, port, logger=logger)

    progress = {"connecting": False, "connected": False}
    return _guarded(
        logger,
        broker_mod,
        progress,
        lambda: run_account(args, settings, broker_mod, broker_factory, logger, progress),
        "portfolio JSON",
    )


def _resolve(args, broker_factory, logger, clock) -> int:
    try:
        broker_mod = load_broker_module()
        contracts_mod = load_contracts_module()
    except ImportError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=LIBRARY_MISSING {type(exc).__name__}: {exc}",
            'the IBKR client library is missing - pip install -e ".[ibkr]"',
        )
    if broker_factory is None:

        def broker_factory(host, port, logger):
            return broker_mod.IbkrBroker(host, port, logger=logger)

    progress = {"connecting": False, "connected": False}
    return _guarded(
        logger,
        broker_mod,
        progress,
        lambda: run_resolve(
            args, contracts_mod, broker_mod, broker_factory, logger, progress, clock()
        ),
        "resolve output",
    )


# --- the preview command ------------------------------------------------------------


def _preview(args, broker_factory, logger, clock, paper_log_factory, calendar) -> int:
    try:
        broker_mod = load_broker_module()
        contracts_mod = load_contracts_module()
        decision_mod = load_decision_module()
        paperlog_mod = load_paperlog_module()
        maintenance_mod = load_state_maintenance_module()
        calendar = calendar or decision_mod.load_xnys_calendar()
    except ImportError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=LIBRARY_MISSING {type(exc).__name__}: {exc}",
            'a library for the preview is missing - pip install -e ".[ibkr]"',
        )
    if broker_factory is None:

        def broker_factory(host, port, logger):
            return broker_mod.IbkrBroker(host, port, logger=logger)

    if paper_log_factory is None:

        def paper_log_factory(repo, remote, branch):
            return paperlog_mod.GitPaperLog(repo, remote, branch)

    mods = SimpleNamespace(
        broker=broker_mod,
        contracts=contracts_mod,
        decision=decision_mod,
        paperlog=paperlog_mod,
        maintenance=maintenance_mod,
    )
    progress = {"connecting": False, "connected": False}
    return _guarded(
        logger,
        broker_mod,
        progress,
        lambda: run_preview(
            args, mods, broker_factory, paper_log_factory, calendar, logger, progress, clock()
        ),
        "preview output",
    )


# --- the execute command ------------------------------------------------------------


class _ExecuteStop(Exception):
    """A run-level stop of ``execute`` with an exit code; the ledger's ``run_end`` names it."""

    def __init__(self, code: int, state: str, detail: str):
        super().__init__(f"{state}: {detail}")
        self.code = code
        self.state = state
        self.detail = detail


class DryPlacer:
    """The phase-5 placer: completes an intent on paper and never contacts the broker."""

    dry = True

    def complete(self, ctx, intent: dict) -> str:
        # The second size check runs right before the ``intent`` line (``_execute_ticker``),
        # so nothing can fail here between the intent and its completion (WR-02).
        ctx.ledger.append(
            ctx.mods.ledger.DRY_COMPLETE,
            decision_key=intent["decision_key"],
            ticker=intent["ticker"],
        )
        return ctx.mods.guards.DRY_COMPLETE


def _execution_view(execution) -> dict:
    """One execution as plain data for the alarm line."""
    return {
        "exec_id": execution.exec_id,
        "shares": execution.shares,
        "price": execution.price,
        "side": execution.side,
        "con_id": execution.con_id,
        "order_ref": execution.order_ref,
        "perm_id": execution.perm_id,
        "order_id": execution.order_id,
    }


# D-16: an order parked until the market opens (399) is not a rejection. Not measurable at the
# gateway, covered by a fake test only (gap like ``halted``, REQ-67).
PARKED_CODES = frozenset({399})
#: Local end states that may be a rejection. ``ValidationError`` is none: the client library
#: sets it for order warnings while the order is still live (CR-01). Even these states can be
#: set by the library alone, so a rejection is booked only once the broker's history confirms.
REJECT_STATUSES = frozenset({"Cancelled", "ApiCancelled", "Inactive"})


class LivePlacer:
    """The phase-6 placer: sends one market order per intent, waits for the fill, checks the
    result against the intent (REQ-65) and writes the fills in the same run (REQ-47, REQ-48).

    Outcomes: clean fill, fill timeout / link event / parked (alarm, order stays open, run
    stops), rejection confirmed at the broker (key closed; an unconfirmed one is a fill
    timeout), partial fill (deviation path), unexpected failure after the send (fill timeout).
    """

    dry = False

    def complete(self, ctx, intent: dict) -> str:
        placing = ctx.placing
        # A GatewayUnavailable or ValueError is not caught here: the intent stays open, the
        # run ends on the existing error path and the next run reconciles it.
        result = placing.broker.place_order(
            con_id=intent["con_id"],
            symbol=placing.symbol,
            sec_type=placing.sec_type,
            currency=placing.currency,
            primary_exchange=placing.primary_exchange,
            action=intent["side"],
            quantity=int(intent["quantity"]),
            order_ref=intent["order_ref"],
            timeout_s=FILL_TIMEOUT_S,
        )
        # From here on the order is out. No failure may end the run as a plain gateway error
        # (exit 3) without an alarm: anything unexpected becomes a fill-timeout (WR-01).
        try:
            return self._after_send(ctx, intent, result)
        except _ExecuteStop:
            raise
        except Exception as exc:  # noqa: BLE001 - every failure after the send is an alarm
            raise self._post_send_failure(ctx, intent, result, exc) from exc

    def _after_send(self, ctx, intent: dict, result) -> str:
        """Everything after ``place_order`` returned: ``placed`` first, then the outcome."""
        guards = ctx.mods.guards
        ledger_mod = ctx.mods.ledger
        key = intent["decision_key"]
        ticker = intent["ticker"]
        ctx.ledger.append(
            ledger_mod.PLACED,
            decision_key=key,
            ticker=ticker,
            order_id=result.order_id,
            perm_id=result.perm_id,
            status=result.status,
            source="placer",
        )
        ctx.logger.info(
            "ibkr-state=ORDER_PLACED ticker=%s key=%s order_id=%s perm_id=%s status=%s",
            ticker,
            key,
            result.order_id,
            result.perm_id,
            result.status,
        )
        kind = self._classify(result)
        codes = f"codes={list(result.error_codes)}, texts={list(result.error_texts)}"
        if kind == "link":
            self._fill_timeout(
                ctx,
                intent,
                result,
                f"link event during the wait (status {result.status!r}); {codes}",
            )
        if kind == "parked":
            self._fill_timeout(ctx, intent, result, f"parked (399): {codes}")
        if kind == "timeout":
            self._fill_timeout(
                ctx,
                intent,
                result,
                f"no fill within {FILL_TIMEOUT_S:g} s (status {result.status!r})"
                + (f"; {codes}" if result.error_codes else ""),
            )
        if kind == "rejected":
            unconfirmed = self._unconfirmed_rejection(ctx, intent, result)
            if unconfirmed is not None:
                self._fill_timeout(
                    ctx,
                    intent,
                    result,
                    f"rejection not confirmed by the broker (status {result.status!r}, "
                    f"{codes}): {unconfirmed}",
                )
            return self._rejected(ctx, intent, result)
        if kind == "partial":
            order, mine = self._read_back(ctx, intent, result)
            detail = (
                f"partial fill {result.filled:g} of {intent['quantity']} "
                f"then {result.status!r}; {codes}"
            )
            self._deviation(ctx, intent, result, order, mine, detail)
        order, mine = self._read_back(ctx, intent, result)
        problems = self._compare(ledger_mod, intent, result, order, mine)
        if problems:
            self._deviation(ctx, intent, result, order, mine, "; ".join(problems))
        records = ledger_mod.fill_records(intent, mine)
        for number, (event, fields) in enumerate(records):
            fields = {**fields, "source": "placer"}
            fields["order_id"] = result.order_id
            fields["perm_id"] = result.perm_id
            if number == len(records) - 1:
                fields["avg_price"] = result.avg_fill_price
                fields["completed_status"] = order.status
                fields["completed_filled"] = order.filled
            ctx.ledger.append(event, **fields)
        ctx.logger.info(
            "ibkr-state=ORDER_FILLED ticker=%s key=%s exec_ids=%s avg_price=%s",
            ticker,
            key,
            ",".join(e.exec_id for e in ledger_mod.effective_executions(mine)),
            result.avg_fill_price,
        )
        return guards.ORDER_FILLED

    @staticmethod
    def _classify(result) -> str:
        """Sort the outcome of a send: link, parked, timeout, rejected, partial or filled."""
        if result.link_event and result.status != "Filled":
            return "link"
        if PARKED_CODES & set(result.error_codes) and not result.filled:
            return "parked"
        if result.timed_out:
            return "timeout"
        if result.status in REJECT_STATUSES:
            return "partial" if result.filled else "rejected"
        return "filled"

    @staticmethod
    def _fill_timeout(ctx, intent: dict, result, detail: str) -> None:
        """An unclear outcome: the order stays open, nothing is cancelled (D-08); stop the run."""
        guards = ctx.mods.guards
        ctx.ledger.append(
            ctx.mods.ledger.ALARM,
            state=guards.FILL_TIMEOUT,
            decision_key=intent["decision_key"],
            ticker=intent["ticker"],
            detail=detail,
            order_id=result.order_id,
            perm_id=result.perm_id,
            status=result.status,
            filled=result.filled,
        )
        ctx.logger.error(
            'ibkr-state=FILL_TIMEOUT ticker=%s key=%s detail="%s"',
            intent["ticker"],
            intent["decision_key"],
            detail,
        )
        print(
            f"execute: {guards.FILL_TIMEOUT} ({intent['ticker']}: {detail}); the order stays "
            "open, nothing was cancelled - the next run reconciles"
        )
        raise _ExecuteStop(EXIT_FILL_TIMEOUT, guards.FILL_TIMEOUT, detail)

    @staticmethod
    def _post_send_failure(ctx, intent: dict, result, exc: Exception) -> _ExecuteStop:
        """An unexpected failure after the send (WR-01): alarm best-effort, stop with exit 9.

        The order is out and its outcome unknown, so it is treated like a fill timeout: the
        entry stays open, nothing is cancelled, the next run reconciles. Returns the stop for
        the caller to raise; a failing alarm write is logged and does not change the exit.
        """
        guards = ctx.mods.guards
        detail = f"post-send failure ({type(exc).__name__}): {exc}"
        try:
            ctx.ledger.append(
                ctx.mods.ledger.ALARM,
                state=guards.FILL_TIMEOUT,
                decision_key=intent["decision_key"],
                ticker=intent["ticker"],
                detail=detail,
                order_id=result.order_id,
                perm_id=result.perm_id,
                status=result.status,
                filled=result.filled,
            )
        except Exception as alarm_exc:  # noqa: BLE001 - the stop must happen regardless
            ctx.logger.error(
                'ibkr-state=FILL_TIMEOUT ticker=%s key=%s detail="alarm not written (%s: %s)"',
                intent["ticker"],
                intent["decision_key"],
                type(alarm_exc).__name__,
                alarm_exc,
            )
        ctx.logger.error(
            'ibkr-state=FILL_TIMEOUT ticker=%s key=%s detail="%s"',
            intent["ticker"],
            intent["decision_key"],
            detail,
        )
        print(
            f"execute: {guards.FILL_TIMEOUT} ({intent['ticker']}: {detail}); the order was "
            "sent, nothing was cancelled - the next run reconciles"
        )
        return _ExecuteStop(EXIT_FILL_TIMEOUT, guards.FILL_TIMEOUT, detail)

    @staticmethod
    def _matches(record, intent: dict, result) -> bool:
        """Whether an order or execution of the history belongs to this placement."""
        if result.perm_id and record.perm_id == result.perm_id:
            return True
        if result.order_id and getattr(record, "order_id", 0) == result.order_id:
            return True
        return record.order_ref == intent["order_ref"]

    def _unconfirmed_rejection(self, ctx, intent: dict, result) -> str | None:
        """Why a local rejection is not (yet) confirmed by the broker; ``None`` = confirmed.

        ``Cancelled``/``Inactive`` can be set by the client library alone while the order is
        live (CR-01). Confirmed means: no open order and no execution of this placement, and
        a completed order of it (if any) is cancelled/inactive with nothing filled.
        """
        time.sleep(POST_ORDER_RETRY_S)
        try:
            history = ctx.placing.broker.order_history()
        except Exception as exc:  # noqa: BLE001 - unreadable history never confirms
            return f"order history unreadable ({type(exc).__name__}: {exc})"
        still_open = [o for o in history.open if self._matches(o, intent, result)]
        if still_open:
            return f"order still open at the broker (status {still_open[0].status!r})"
        _order, mine = self._own(history, intent, result)
        if mine:
            return f"{len(mine)} execution(s) of this order at the broker"
        for order in history.completed:
            if not self._matches(order, intent, result):
                continue
            if order.status not in REJECT_STATUSES:
                return f"completed order status {order.status!r}"
            if order.filled is not None and float(order.filled) != 0:
                return f"completed order filled {order.filled}"
        return None

    @staticmethod
    def _rejected(ctx, intent: dict, result) -> str:
        """A rejection the broker confirmed closes the key: nothing left to reconcile."""
        guards = ctx.mods.guards
        ctx.ledger.append(
            ctx.mods.ledger.REJECTED,
            decision_key=intent["decision_key"],
            ticker=intent["ticker"],
            state=guards.PLACE_REJECTED,
            status=result.status,
            error_codes=list(result.error_codes),
            error_texts=list(result.error_texts),
            order_id=result.order_id,
            perm_id=result.perm_id,
            source="placer",
        )
        ctx.logger.warning(
            "ibkr-state=PLACE_REJECTED ticker=%s key=%s status=%s codes=%s",
            intent["ticker"],
            intent["decision_key"],
            result.status,
            list(result.error_codes),
        )
        return guards.PLACE_REJECTED

    @staticmethod
    def _own(history, intent: dict, result):
        """The broker's own order and executions of this placement (Pitfall 4).

        The order is found by ``permId`` (``orderId`` when the permanent id is not set); the
        executions by ``permId`` or by ``orderRef``, never by the reference alone.
        """
        pool = (*history.completed, *history.open)
        if result.perm_id:
            orders = [o for o in pool if o.perm_id == result.perm_id]
        else:
            orders = [o for o in pool if o.order_id == result.order_id]
        order = orders[0] if orders else None
        mine = [
            e
            for e in history.executions
            if (result.perm_id and e.perm_id == result.perm_id)
            or e.order_ref == intent["order_ref"]
        ]
        return order, mine

    def _read_back(self, ctx, intent: dict, result):
        """Read the order history until it shows the whole fill (Pitfall 8: not atomic)."""
        ledger_mod = ctx.mods.ledger
        want = float(intent["quantity"])
        order, mine = None, []
        for attempt in range(POST_ORDER_READS):
            history = ctx.placing.broker.order_history()
            order, mine = self._own(history, intent, result)
            shares = sum(float(e.shares) for e in ledger_mod.effective_executions(mine))
            if order is not None and shares >= want:
                break
            if attempt + 1 < POST_ORDER_READS:
                time.sleep(POST_ORDER_RETRY_S)
        return order, mine

    @staticmethod
    def _compare(ledger_mod, intent: dict, result, order, mine: list) -> list[str]:
        """Every difference between what was meant and what the broker shows (REQ-65)."""
        problems: list[str] = []
        ref = intent["order_ref"]
        want = float(intent["quantity"])
        if order is None:
            problems.append("no order with this permId/orderId in the broker's history")
        else:
            if order.status != "Filled":
                problems.append(f"order status {order.status!r}, expected 'Filled'")
            if order.action != intent["side"]:
                problems.append(f"order side {order.action!r}, expected {intent['side']!r}")
            if float(order.quantity) != want:
                problems.append(f"order quantity {order.quantity}, expected {want}")
            if order.filled is not None and float(order.filled) != want:
                problems.append(f"order filled {order.filled}, expected {want}")
            if order.order_ref != ref:
                problems.append(f"order orderRef {order.order_ref!r}, expected {ref!r}")
            if order.con_id != intent["con_id"]:
                problems.append(f"order conId {order.con_id}, expected {intent['con_id']}")
        for execution in mine:
            if execution.side != intent["side"]:
                problems.append(f"execution {execution.exec_id} side {execution.side!r}")
            if execution.con_id != intent["con_id"]:
                problems.append(f"execution {execution.exec_id} conId {execution.con_id}")
            if execution.order_ref != ref:
                problems.append(f"execution {execution.exec_id} orderRef {execution.order_ref!r}")
            if result.perm_id and execution.perm_id and execution.perm_id != result.perm_id:
                problems.append(f"execution {execution.exec_id} permId {execution.perm_id}")
        shares = sum(float(e.shares) for e in ledger_mod.effective_executions(mine))
        if shares != want:
            problems.append(f"executions add up to {shares}, expected {want}")
        return problems

    def _deviation(self, ctx, intent: dict, result, order, mine: list, detail: str) -> None:
        """Alarm and stop the whole run (D-09); the fills that are certain are kept first."""
        guards = ctx.mods.guards
        ledger_mod = ctx.mods.ledger
        key = intent["decision_key"]
        ref = intent["order_ref"]
        trusted = [
            e
            for e in mine
            if e.side == intent["side"] and e.con_id == intent["con_id"] and e.order_ref == ref
        ]
        for event, fields in ledger_mod.fill_records(intent, trusted):
            fields = {**fields, "source": "placer", "order_id": result.order_id}
            fields["perm_id"] = result.perm_id
            ctx.ledger.append(event, **fields)
        ctx.ledger.append(
            ledger_mod.ALARM,
            state=guards.POST_ORDER_MISMATCH,
            decision_key=key,
            ticker=intent["ticker"],
            detail=detail,
            expected={
                "side": intent["side"],
                "quantity": intent["quantity"],
                "order_ref": ref,
                "con_id": intent["con_id"],
            },
            seen={
                "status": order.status if order is not None else result.status,
                "filled": order.filled if order is not None else result.filled,
                "order_ref": order.order_ref if order is not None else None,
                "perm_id": result.perm_id,
                "executions": [_execution_view(e) for e in mine],
            },
        )
        ctx.logger.error(
            'ibkr-state=POST_ORDER_MISMATCH ticker=%s key=%s detail="%s"',
            intent["ticker"],
            key,
            detail,
        )
        print(
            f"execute: {guards.POST_ORDER_MISMATCH} ({intent['ticker']}: {detail}); "
            "run stopped - see IBKR_EXECUTION.md"
        )
        raise _ExecuteStop(EXIT_POST_ORDER, guards.POST_ORDER_MISMATCH, detail)


def _execute(args, broker_factory, logger, clock, paper_log_factory, calendar, placer) -> int:
    try:
        broker_mod = load_broker_module()
        contracts_mod = load_contracts_module()
        decision_mod = load_decision_module()
        paperlog_mod = load_paperlog_module()
        maintenance_mod = load_state_maintenance_module()
        guards_mod = load_guards_module()
        ledger_mod = load_ledger_module()
        calendar = calendar or decision_mod.load_xnys_calendar()
    except ImportError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=LIBRARY_MISSING {type(exc).__name__}: {exc}",
            'a library for execute is missing - pip install -e ".[ibkr]"',
        )
    if broker_factory is None:

        def broker_factory(host, port, logger):
            return broker_mod.IbkrBroker(host, port, logger=logger)

    if paper_log_factory is None:

        def paper_log_factory(repo, remote, branch):
            return paperlog_mod.GitPaperLog(repo, remote, branch)

    placer = (LivePlacer() if args.live else DryPlacer()) if placer is None else placer
    if args.resolve is not None:
        progress = {"connecting": False, "connected": False}
        resolve_mods = SimpleNamespace(broker=broker_mod, guards=guards_mod, ledger=ledger_mod)
        return _guarded(
            logger,
            broker_mod,
            progress,
            lambda: run_resolve_entry(args, resolve_mods, broker_factory, logger, progress, clock),
            "execute ledger",
        )
    mods = SimpleNamespace(
        broker=broker_mod,
        contracts=contracts_mod,
        decision=decision_mod,
        paperlog=paperlog_mod,
        maintenance=maintenance_mod,
        guards=guards_mod,
        ledger=ledger_mod,
    )
    progress = {"connecting": False, "connected": False}
    return _guarded(
        logger,
        broker_mod,
        progress,
        lambda: run_execute(
            args, mods, broker_factory, paper_log_factory, calendar, placer, logger, progress, clock
        ),
        "execute ledger",
    )


def run_resolve_entry(args, mods, broker_factory, logger, progress, clock) -> int:
    """``execute --resolve KEY=never_sent --note TEXT``: close a live ``intent`` by hand (D-14).

    Appends one ``resolved`` event under the ledger lock and never changes a line. Only an
    open entry whose last lifecycle event is ``intent`` qualifies, and only when the broker's
    history shows no trace of it; the key stays used up. No order is sent, so RELEASE and KILL
    are not looked at.
    """
    ledger_mod = mods.ledger
    key, _outcome = _split_resolve(args.resolve)
    raw = read_settings(args.env_file)
    host, port, _account = validate_settings(raw, mods.broker.EXPECTED_ACCOUNT)
    state_dir = default_ledger_file().parent
    try:
        ledger_mod.ensure_outside_git(state_dir)
    except ledger_mod.StateInGitTree as exc:
        return _fail(
            logger, EXIT_CONFIG, f"ibkr-state=STATE_IN_GIT_TREE {exc}", f"state folder: {exc}"
        )
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=STATE_DIR_UNUSABLE {state_dir}: {type(exc).__name__}: {exc}",
            f"state folder not usable: {state_dir} ({type(exc).__name__})",
        )
    lock_stack = contextlib.ExitStack()
    try:
        held = lock_stack.enter_context(locked(default_ledger_file(), wait=False))
    except OSError as exc:
        lock_stack.close()
        return _fail(
            logger,
            EXIT_LOCKED,
            f'ibkr-state=LOCK_ERROR detail="{type(exc).__name__}: {exc}"',
            "execute: lock-error (not resolved)",
        )
    if not held:
        lock_stack.close()
        return _fail(
            logger,
            EXIT_LOCKED,
            f'ibkr-state=LOCK_HELD detail="{default_ledger_file()}.lock"',
            "execute: lock-held (another run holds the ledger lock)",
        )
    with lock_stack:
        try:
            ledger = ledger_mod.Ledger.open(
                default_ledger_file(),
                mode=ledger_mod.MODE_LIVE,
                clock=clock,
                run_id=uuid.uuid4().hex,
            )
        except Exception as exc:  # noqa: BLE001 - an unreadable ledger is "corrupt"
            detail = (
                str(exc)
                if isinstance(exc, ledger_mod.LedgerError)
                else f"{type(exc).__name__}: {exc}"
            )
            return _fail(
                logger,
                EXIT_RECONCILE,
                f'ibkr-state=LEDGER_CORRUPT detail="{detail}"',
                f"execute: ledger-corrupt ({detail})",
            )
        entry = next((e for e in ledger.unresolved() if e["decision_key"] == key), None)
        if entry is None:
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=RESOLVE_NOT_OPEN key={key}",
                f"execute: {key} is not an open entry of the live ledger",
            )
        last = ledger.last_event(key)
        if last is None or last["event"] != ledger_mod.INTENT:
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=RESOLVE_NOT_INTENT key={key} last={last and last['event']}",
                f"execute: {key} is past its intent: a placed order was sent",
            )
        ctx = SimpleNamespace(
            logger=logger,
            progress=progress,
            broker_factory=broker_factory,
            host=host,
            port=port,
            broker=None,
            history=None,
            stack=contextlib.ExitStack(),
        )
        try:
            history = _history(ctx)
        except _ExecuteStop as stop:
            return stop.code
        finally:
            ctx.stack.close()
        res = ledger_mod.resolve_entry(entry, history, dry=False)
        if res.outcome != ledger_mod.NO_TRACE:
            return _fail(
                logger,
                EXIT_RECONCILE,
                f"ibkr-state=RESOLVE_HAS_TRACE key={key} outcome={res.outcome} "
                f"open={res.open} completed={res.completed} executions={res.executions}",
                f"execute: {key} shows a trace at the broker ({res.outcome}); "
                "the normal reconciliation resolves it",
            )
        ledger.append(
            ledger_mod.RESOLVED,
            decision_key=key,
            ticker=entry["ticker"],
            outcome=ledger_mod.NEVER_SENT,
            note=args.note,
            detail=res.detail,
            source="operator",
        )
        logger.info('ibkr-state=RESOLVED_BY_OPERATOR key=%s note="%s"', key, args.note)
        print(f"execute: resolved {key} as never_sent")
        return EXIT_OK


def _ledger_row_finished(ctx, row: dict, state: str, detail: str) -> None:
    """Put the end of a ticker into the ledger: ``skipped`` with a reason, or ``rejected``.

    Never a ticker end without a line: a state with neither a reason nor a verdict is recorded
    as ``skipped`` / ``review`` (fail closed) and flagged.
    """
    guards = ctx.mods.guards
    ledger_mod = ctx.mods.ledger
    if state == guards.DRY_COMPLETE or state in guards.PLACER_STATES:
        return  # the placer wrote ``dry_complete`` / its own fill or reject lines already
    fresh = row["freshness"]
    fields = {
        "ticker": row["ticker"],
        "trade_date": row["trade_date"],
        "state": state,
        "detail": detail,
        "paper_log_sha": ctx.sha,
        "weekend_gap": fresh["weekend_gap"] if fresh else None,
    }
    for extra in ("rating", "first_rating", "first_paper_log_sha"):
        # The second version of a changed decision is logged next to the first one (SC8).
        if state == guards.DECISION_CHANGED and row.get(extra) is not None:
            fields[extra] = row[extra]
    if row["trade_date"]:
        # An undated or malformed decision has no key; the state says why.
        with contextlib.suppress(ValueError):
            fields["decision_key"] = guards.decision_key(row["trade_date"], row["ticker"])
    # The verdict wins: the two tables are disjoint, the order is only a guard.
    if state in ledger_mod.REJECTED_STATES:
        ctx.ledger.append(ledger_mod.REJECTED, **fields)
    elif state in ledger_mod.REASON_BY_STATE:
        ctx.ledger.append(ledger_mod.SKIPPED, reason=ledger_mod.REASON_BY_STATE[state], **fields)
    else:
        ctx.logger.warning("ibkr-state=LEDGER_REASON_UNMAPPED state=%s", state)
        ctx.ledger.append(ledger_mod.SKIPPED, reason="review", unmapped_state=True, **fields)


def run_execute(
    args, mods, broker_factory, paper_log_factory, calendar, placer, logger, progress, clock
) -> int:
    """The guarded chain: dry unless ``--live`` (then the live placer sends, D-01).

    ``clock`` is the injected callable: ``now_utc`` is read once here, later guard checks
    read ``ctx.clock()`` again.
    """
    # Placer and mode must agree, before any file is touched (D-01): no global switch.
    live = bool(getattr(args, "live", False))
    if not live and getattr(placer, "dry", None) is not True:
        return _fail(
            logger,
            EXIT_CONFIG,
            "ibkr-state=NOT_DRY the placer is not dry",
            "execute without --live needs a dry placer",
        )
    if live and getattr(placer, "dry", None) is not False:
        return _fail(
            logger,
            EXIT_CONFIG,
            "ibkr-state=NOT_LIVE --live with a dry placer",
            "execute --live needs the live placer",
        )
    now_utc = clock()
    raw = read_settings(args.env_file)
    host, port, _account = validate_settings(raw, mods.broker.EXPECTED_ACCOUNT)
    remote, branch = paper_log_settings(raw, mods.paperlog)
    problems = mods.contracts.table_problems()
    if problems:
        raise ConfigError("contract table: " + "; ".join(problems))
    ledger_mod = mods.ledger
    state_dir = default_ledger_file().parent
    try:
        ledger_mod.ensure_outside_git(state_dir)
    except ledger_mod.StateInGitTree as exc:
        return _fail(
            logger, EXIT_CONFIG, f"ibkr-state=STATE_IN_GIT_TREE {exc}", f"state folder: {exc}"
        )
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=STATE_DIR_UNUSABLE {state_dir}: {type(exc).__name__}: {exc}",
            f"state folder not usable: {state_dir} ({type(exc).__name__})",
        )
    # The outermost bracket of the run (T-05-27): one run at a time per ledger. Only the
    # attempt to take the lock sits in the ``try``; an OSError inside the run is never exit 7.
    # The lock path is always ``ledger.jsonl``, also for the dry run (it is the live ledger's lock).
    lock_stack = contextlib.ExitStack()
    try:
        held = lock_stack.enter_context(locked(default_ledger_file(), wait=False))
    except OSError as exc:
        lock_stack.close()
        return _fail(
            logger,
            EXIT_LOCKED,
            f'ibkr-state=LOCK_ERROR detail="{type(exc).__name__}: {exc}"',
            "execute: lock-error (not executed)",
        )
    if not held:
        lock_stack.close()
        return _fail(
            logger,
            EXIT_LOCKED,
            f'ibkr-state=LOCK_HELD detail="{default_ledger_file()}.lock"',
            "execute: lock-held (another run holds the ledger lock)",
        )
    with lock_stack:
        return _run_locked(
            args,
            mods,
            broker_factory,
            paper_log_factory,
            calendar,
            placer,
            logger,
            progress,
            clock,
            now_utc=now_utc,
            host=host,
            port=port,
            remote=remote,
            branch=branch,
            state_dir=state_dir,
        )


def _check_switches(ctx):
    """Read the release file and the kill file anew; the clock is read on every call (D-04)."""
    today = ctx.clock().astimezone(UTC).date()
    return ctx.mods.guards.check_switches(
        str(ctx.state_dir),
        today_utc=today,
        expected_account=ctx.mods.broker.EXPECTED_ACCOUNT,
    )


def _blocking_detail(ctx, switches) -> str:
    guards = ctx.mods.guards
    if switches.kill.state != guards.KILL_ABSENT:
        detail = switches.kill.detail or "KILL file present"
    else:
        detail = switches.release.detail or "no valid release"
    return detail


def _report_blocked(ctx, switches) -> str:
    """One log line and one console line for the state that blocks the run."""
    state = switches.blocking_state
    detail = _blocking_detail(ctx, switches)
    ctx.logger.warning('ibkr-state=%s detail="%s"', state.upper().replace("-", "_"), detail)
    print(f"execute: {state} ({detail})")
    return detail


def _halt_on_switches(ctx, row: dict, switches) -> None:
    """A switch closed between two orders: this ticker and all later ones end as skipped."""
    ctx.halted = ctx.halted or switches
    _finish_row(ctx, row, switches.blocking_state, _blocking_detail(ctx, switches))


def _kill_path(ctx, switches) -> None:
    """The one place that cancels: only for a positively present KILL file (D-17).

    The cancel is fire-and-forget; the open orders are read again to see whether it worked.
    The exit stays 4 either way. A broker that cannot be reached ends the run with 4, not 3.
    A wrong account is not caught here (exit 8) and never reaches ``cancel_all``.
    """
    if not switches.cancel:
        raise RuntimeError("the kill path needs a positively present KILL file")
    if ctx.cancelled:
        return
    ctx.cancelled = True  # once per run, whatever comes of it
    broker_mod = ctx.mods.broker
    ledger_mod = ctx.mods.ledger
    record = switches.as_record()
    try:
        broker = _session(ctx)
        broker.cancel_all(kill_evidence=switches.kill)
    except (broker_mod.GatewayUnavailable, _ExecuteStop) as exc:
        ctx.logger.error('ibkr-state=KILL_CANCEL_FAILED detail="%s"', exc)
        print(f"execute: kill-active, global cancel not sent ({type(exc).__name__})")
        if ctx.ledger is not None:
            ctx.ledger.append(
                ledger_mod.KILL_CANCEL,
                outcome="gateway_unavailable",
                detail=str(exc),
                sent=0,
                **record,
            )
        return
    remaining: int | None = None
    rechecks = 0
    detail = ""
    deadline = time.monotonic() + KILL_RECHECK_SECONDS
    try:
        while True:
            remaining = len(broker.open_orders())
            rechecks += 1
            if remaining == 0 or time.monotonic() >= deadline:
                break
            _sleep(KILL_RECHECK_INTERVAL_S)
    except broker_mod.GatewayUnavailable as exc:
        detail = f"re-read failed: {exc}"
    if ctx.ledger is not None:
        ctx.ledger.append(
            ledger_mod.KILL_CANCEL,
            outcome="sent",
            sent=1,
            remaining=remaining,
            rechecks=rechecks,
            detail=detail,
            **record,
        )
    ctx.logger.log(
        logging.WARNING if remaining != 0 else logging.INFO,
        'ibkr-state=KILL_CANCEL remaining=%s rechecks=%s detail="%s"',
        remaining,
        rechecks,
        detail,
    )
    print(f"execute: kill-active, global cancel sent, {remaining} open order(s) left")


def _run_locked(
    args,
    mods,
    broker_factory,
    paper_log_factory,
    calendar,
    placer,
    logger,
    progress,
    clock,
    *,
    now_utc,
    host,
    port,
    remote,
    branch,
    state_dir,
) -> int:
    """The run proper, holding the ledger lock: switches first, then the ledger, then the chain."""
    guards = mods.guards
    ledger_mod = mods.ledger
    # The context exists before the ledger is opened, so the guards can work without one.
    ctx = SimpleNamespace(
        mods=mods,
        logger=logger,
        clock=clock,
        now_utc=now_utc,
        args=args,
        host=host,
        port=port,
        remote=remote,
        branch=branch,
        calendar=calendar,
        progress=progress,
        broker_factory=broker_factory,
        placer=placer,
        guards=guards,
        label="execute",
        stack=contextlib.ExitStack(),
        broker=None,
        ledger=None,
        switches=None,
        cancelled=False,
        halted=None,
        history=None,
        sha=None,
        out=None,
        on_row_finished=_ledger_row_finished,
        state_dir=state_dir,
    )
    # Preflight (D-21): both switches are read before anything else, and logged in every run.
    switches = ctx.switches = _check_switches(ctx)
    logger.log(
        logging.INFO if switches.allowed else logging.WARNING,
        "ibkr-state=SWITCHES release=%s kill=%s valid_until=%s",
        switches.release.state,
        switches.kill.state,
        switches.release.valid_until,
    )
    try:
        live = bool(getattr(args, "live", False))
        ctx.ledger = ledger_mod.Ledger.open(
            default_ledger_file() if live else default_dryrun_ledger_file(),
            mode=ledger_mod.MODE_LIVE if live else ledger_mod.MODE_DRYRUN,
            clock=clock,
            run_id=uuid.uuid4().hex,
        )
    except Exception as exc:  # noqa: BLE001 - an unreadable ledger is "corrupt", never a crash
        # A malformed record is a LedgerError; a file another program holds open (Windows),
        # or any other read failure, ends the same way, so a present KILL still cancels.
        detail = (
            str(exc) if isinstance(exc, ledger_mod.LedgerError) else f"{type(exc).__name__}: {exc}"
        )
        logger.error('ibkr-state=LEDGER_CORRUPT detail="%s"', detail)
        print(f"execute: ledger-corrupt ({detail})")
        if switches.allowed:
            return EXIT_RECONCILE
        # A closed switch is the stronger signal (rank 4 before 6); nothing is written to the
        # damaged ledger, but a present KILL file still cancels.
        try:
            _report_blocked(ctx, switches)
            if switches.cancel:
                _kill_path(ctx, switches)
        finally:
            ctx.stack.close()
        return EXIT_KILL_SWITCH
    tickers = list(dict.fromkeys(args.tickers))
    ctx.ledger.append(
        ledger_mod.RUN_START, command="execute", tickers=tickers, **switches.as_record()
    )
    rows: dict = {}
    abort_code = None
    stop_state = None
    try:
        try:
            if not switches.allowed:
                _report_blocked(ctx, switches)
                if switches.cancel:
                    _kill_path(ctx, switches)
                raise _ExecuteStop(
                    EXIT_KILL_SWITCH, switches.blocking_state, _blocking_detail(ctx, switches)
                )
            # Reconciliation before anything is read or decided (REQ-45: lock, switches,
            # reconciliation, paper-log, ...): an open ledger entry is resolved or the run ends.
            _reconcile(ctx)
            source = paper_log_factory(REPO_ROOT, remote, branch)
            ctx.sha = source.fetch()
            rows, remaining = _local_chain(ctx, source, args.tickers)
            remaining = _check_attempts(ctx, rows, remaining)
            if remaining:
                _execute_gateway_chain(ctx, rows, remaining)
            if ctx.halted is not None and ctx.halted.cancel:
                _kill_path(ctx, ctx.halted)
        except mods.paperlog.PaperLogUnavailable as exc:
            # No second attempt and no fall back to a local ref (D-02).
            stop = _RunAbort(mods.decision.PAPER_LOG_UNAVAILABLE, exc.reason)
            abort_code, stop_state = _abort_run(ctx, stop, rows), stop.state
        except _RunAbort as stop:
            abort_code, stop_state = _abort_run(ctx, stop, rows), stop.state
        except _ExecuteStop as stop:
            abort_code, stop_state = stop.code, stop.state
        finally:
            ctx.stack.close()
    except Exception as exc:
        try:
            # After a failed append the ledger seals the cut-off line first (WR-01).
            ctx.ledger.append(ledger_mod.RUN_END, outcome="error", error=type(exc).__name__)
        except Exception as end_exc:  # noqa: BLE001 - the original error is the one to report
            logger.error(
                'ibkr-state=LEDGER_APPEND_FAILED event=run_end detail="%s: %s"',
                type(end_exc).__name__,
                end_exc,
            )
        raise
    exits = [row["exit"] for row in rows.values() if row["exit"] is not None]
    if abort_code is not None:
        exits.append(abort_code)
    code = guards.worst_run_exit(exits)
    end = {"exit": code}
    if stop_state:
        end["state"] = stop_state
    ctx.ledger.append(ledger_mod.RUN_END, **end)
    return code


def _history(ctx):
    """The broker's order history (open, completed, executions): read once per run."""
    if ctx.history is None:
        ctx.history = _session(ctx).order_history()
    return ctx.history


def _fill_quantity(entry: dict, history, ledger_mod) -> float:
    """Filled pieces of an entry: the executions first, else what the completed order reports.

    Executions count once per execId family (a ``.02`` correction replaces ``.01``, REQ-47).
    """
    key = entry.get("order_ref") or entry["decision_key"]
    mine = [e for e in history.executions if e.order_ref == key]
    shares = sum(float(e.shares) for e in ledger_mod.effective_executions(mine))
    if shares:
        return shares
    return sum(
        float(o.filled) for o in history.completed if o.order_ref == key and o.filled is not None
    )


def _reconcile(ctx) -> None:
    """Resolve every open ledger entry against the broker before any new order (REQ-43, SC6).

    A ``reconcile`` event is no lifecycle event: an entry that cannot be resolved stays open
    in every later run, and the run ends with exit 6 and no new ``intent`` (D-19). Resolution
    by hand follows the manual (IBKR_EXECUTION.md, Ledger and reconciliation); ``--resolve``
    closes a ``no_trace`` live intent.
    """
    pending = ctx.ledger.unresolved()
    if not pending:
        return  # no gateway contact without an open entry
    guards = ctx.mods.guards
    ledger_mod = ctx.mods.ledger
    history = _history(ctx)
    unresolved: list[tuple[str, str]] = []
    dry = ctx.ledger.mode == ledger_mod.MODE_DRYRUN
    for entry in pending:
        key = entry["decision_key"]
        res = ledger_mod.resolve_entry(entry, history, dry=dry)
        ctx.ledger.append(
            ledger_mod.RECONCILE,
            decision_key=key,
            ticker=entry.get("ticker"),
            outcome=res.outcome,
            open=res.open,
            completed=res.completed,
            executions=res.executions,
            detail=res.detail,
        )
        follow = {"decision_key": key, "ticker": entry.get("ticker"), "source": "reconcile"}
        if res.outcome == ledger_mod.OPEN:
            # The entry is open already after a ``placed``; do not repeat the line every run.
            last = ctx.ledger.last_event(key)
            if last is not None and last["event"] == ledger_mod.INTENT:
                ctx.ledger.append(ledger_mod.PLACED, **follow)
        elif res.outcome in (ledger_mod.FILLED_OUT, ledger_mod.PARTIAL_OUT):
            key_ref = entry.get("order_ref") or key
            mine = [e for e in history.executions if e.order_ref == key_ref]
            if mine:
                # One fill row per effective execId, the same helper the live placer uses (D-10).
                known = {
                    r["exec_id"]
                    for r in ctx.ledger.records
                    if r["event"] in (ledger_mod.FILLED, ledger_mod.PARTIAL)
                    and r.get("decision_key") == key
                    and r.get("exec_id")
                }
                for event, fields in ledger_mod.fill_records(entry, mine, known_exec_ids=known):
                    ctx.ledger.append(event, source="reconcile", detail=res.detail, **fields)
            else:
                full = res.outcome == ledger_mod.FILLED_OUT
                event = ledger_mod.FILLED if full else ledger_mod.PARTIAL
                ctx.ledger.append(
                    event,
                    con_id=entry["con_id"],
                    side=entry["side"],
                    filled_qty=_fill_quantity(entry, history, ledger_mod),
                    detail=res.detail,
                    **follow,
                )
        elif res.outcome == ledger_mod.NOT_FILLED:
            ctx.ledger.append(ledger_mod.REJECTED, state="not-filled", detail=res.detail, **follow)
        elif res.outcome == ledger_mod.NEVER_SENT:
            # A dry intent left open by a broken run (D-08): closed, the run goes on.
            ctx.ledger.append(ledger_mod.REJECTED, state="never-sent", detail=res.detail, **follow)
            ctx.logger.warning(
                'ibkr-state=RECONCILE_NEVER_SENT key=%s detail="%s"', key, res.detail
            )
        else:
            unresolved.append((key, res.outcome))
            ctx.logger.warning(
                "ibkr-state=RECONCILE_UNRESOLVED key=%s outcome=%s open=%d completed=%d "
                'executions=%d detail="%s"',
                key,
                res.outcome,
                res.open,
                res.completed,
                res.executions,
                res.detail,
            )
    if unresolved:
        shown = ", ".join(f"{key} ({outcome})" for key, outcome in unresolved)
        print(
            f"execute: reconcile-unresolved {shown}; no new order - "
            "see IBKR_EXECUTION.md, Ledger and reconciliation"
        )
        raise _ExecuteStop(
            EXIT_RECONCILE, guards.RECONCILE_UNRESOLVED, ", ".join(k for k, _ in unresolved)
        )


def _check_attempts(ctx, rows: dict, remaining: list[str]) -> list[str]:
    """One attempt per decision_key, the first version wins (REQ-40, SC8).

    An attempt is a key that reached ``intent``; a ``skipped`` line never consumes the key.
    This is the integrity check from the ledger, in the spirit of the first-version-wins rule
    of ``tradingagents/memory/log.py``; the broker-side "already executed?" counter-check
    follows in 05-07.

    REQ-45 order deviation: the key check runs after freshness, because the trade_date of the
    entry is only known once the local chain has read and dated it; documented for the
    phase-6 order test (ROADMAP note from 05-09).
    """
    guards = ctx.mods.guards
    kept: list[str] = []
    for ticker in remaining:
        row = rows[ticker]
        try:
            key = guards.decision_key(row["trade_date"], ticker)
        except ValueError as exc:
            # A ticker outside the key whitelist (``^GSPC``, ``XAUUSD+`` from the contract
            # table) can never get an orderRef: it ends here, the other tickers go on (D-11).
            _finish_row(ctx, row, guards.INVALID_DECISION_KEY, str(exc))
            continue
        first = ctx.ledger.attempt_of(key)
        if first is None:
            kept.append(ticker)
        elif first["rating"] != row["rating"]:
            row["first_rating"] = first["rating"]
            row["first_paper_log_sha"] = first["paper_log_sha"]
            detail = (
                f"{key}: first version {first['rating']} (sha {first['paper_log_sha']}), "
                f"now {row['rating']} (sha {ctx.sha}); first version wins"
            )
            _finish_row(ctx, row, guards.DECISION_CHANGED, detail)
        else:
            detail = f"{key}: intent of run {first['run_id']} at {first['ts']}"
            _finish_row(ctx, row, guards.ALREADY_ATTEMPTED, detail)
    return kept


def _preview_payload(run_state, rows, sha, remote, branch, now_utc: datetime) -> dict:
    """The dry-run record: provenance (``paper_log.sha``), the verdict per ticker, ``sent: false``.

    Dry-run record, not the ledger (phase 5): no write-ahead, no lock.
    """
    return {
        "schema_version": 1,
        "as_of": now_utc.isoformat(),
        "paper_log": {"remote": remote, "branch": branch, "sha": sha},
        "run_state": run_state,
        "sent": False,
        "rows": list(rows),
    }


def _write_preview(out: Path, payload: dict, contracts_mod, logger) -> None:
    try:
        contracts_mod.write_json_atomic(out, payload)
    except OSError as exc:
        raise OutputError(f"{out}: {type(exc).__name__}: {exc}") from exc
    logger.info("preview output written: %s", out)


def _abort_run(ctx, abort: _RunAbort, rows: dict | None = None) -> int:
    """Report a run-level stop: one log line, one console line, the record, the exit code.

    ``rows`` are the tickers that were already decided before the stop.
    """
    label = getattr(ctx, "label", "preview")
    code = ctx.mods.decision.EXIT_BY_STATE.get(abort.state, EXIT_PRECONDITION)
    decided = [row for row in (rows or {}).values() if row["state"]]
    name = abort.state.upper().replace("-", "_")
    ctx.logger.log(
        logging.WARNING if code else logging.INFO,
        'ibkr-state=%s remote=%s branch=%s sha=%s detail="%s"',
        name,
        ctx.remote,
        ctx.branch,
        ctx.sha,
        abort.detail,
    )
    print(f"{label}: {abort.state} ({abort.detail})")
    # ``execute`` has no preview record; its ``run_end`` carries the state instead.
    if getattr(ctx, "out", None) is not None:
        payload = _preview_payload(
            abort.state, decided, ctx.sha, ctx.remote, ctx.branch, ctx.now_utc
        )
        _write_preview(ctx.out, payload, ctx.mods.contracts, ctx.logger)
    return code


_ROW_KEYS = (
    "trade_date",
    "rating",
    "freshness",
    "rating_source",
    "session",
    "position",
    "open_orders",
    "intent",
    "preview",
    "budget",
)


def _new_row(ticker: str) -> dict:
    row = {"ticker": ticker, "state": None, "exit": None, "detail": ""}
    row.update(dict.fromkeys(_ROW_KEYS))
    return row


def _console_suffix(row: dict) -> str:
    """The short addition to a console line: the order intent, then the dating."""
    intent = row["intent"]
    head = f" {intent['side']} {intent['quantity']}" if intent else ""
    notes = []
    if row["trade_date"]:
        notes.append(f"trade_date {row['trade_date']}")
    fresh = row["freshness"]
    if fresh and fresh.get("weekend_gap"):
        notes.append(f"weekend_gap {fresh['gap_days']}d")
    if row["session"] and row["session"].get("closed"):
        notes.append("market closed")
    return head + (f" ({', '.join(notes)})" if notes else "")


def _finish_row(ctx, row: dict, state: str, detail: str) -> None:
    """Give a ticker its end state: exit code, one log line (with the SHA), one console line."""
    # Phase-3 rejections (not-mapped, drift, ...) have no entry in the decision table; D-16
    # puts every precondition under exit 2.
    label = getattr(ctx, "label", "preview")
    code = ctx.mods.decision.EXIT_BY_STATE.get(state)
    if code is None:
        guards = getattr(ctx.mods, "guards", None)
        code = guards.EXIT_BY_STATE.get(state, EXIT_PRECONDITION) if guards else EXIT_PRECONDITION
    row.update(state=state, exit=code, detail=detail)
    ctx.logger.log(
        logging.WARNING if code else logging.INFO,
        "ibkr-state=%s ticker=%s state=%s sha=%s detail=%r",
        label.upper(),
        row["ticker"],
        state,
        ctx.sha,
        detail,
    )
    print(f"{label}: {row['ticker']} {state}{_console_suffix(row)}")
    hook = getattr(ctx, "on_row_finished", None)
    if hook is not None:
        hook(ctx, row, state, detail)


def _finish_run(ctx, rows: dict) -> int:
    """Write the record and combine the ticker states into the exit code (1 > 5 > 2 > 0)."""
    decision_mod = ctx.mods.decision
    # A phase-3 rejection counts as exit 2, like every other precondition.
    states = [
        row["state"]
        if row["state"] in decision_mod.EXIT_BY_STATE
        else decision_mod.NOT_RESOLVED_YET
        for row in rows.values()
    ]
    payload = _preview_payload(None, rows.values(), ctx.sha, ctx.remote, ctx.branch, ctx.now_utc)
    _write_preview(ctx.out, payload, ctx.mods.contracts, ctx.logger)
    return decision_mod.worst_exit(states)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` through a temp file in the same directory, then move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _read_log_entries(ctx, source) -> list[dict]:
    """Fetch ``decision-log.md``, keep a byte-exact copy, verify it, parse its entries (REQ-15)."""
    paperlog_mod = ctx.mods.paperlog
    decision_mod = ctx.mods.decision
    where = f"{ctx.branch}@{ctx.sha}"
    try:
        blob = source.read(paperlog_mod.DECISION_LOG_PATH)
    except paperlog_mod.BlobMissing:
        raise _RunAbort(
            decision_mod.LOG_FINDING, f"{paperlog_mod.DECISION_LOG_PATH} missing on {where}"
        ) from None
    copy = default_paper_log_copy()
    _write_bytes_atomic(copy, blob)
    try:
        text = paperlog_mod.decode_utf8(blob, paperlog_mod.DECISION_LOG_PATH)
    except paperlog_mod.PaperLogUnavailable as exc:
        raise _RunAbort(decision_mod.LOG_FINDING, exc.reason) from None
    if not text.strip():
        # verify reads an empty file as "nothing to check"; for a decision source it is a finding.
        raise _RunAbort(decision_mod.LOG_FINDING, f"{paperlog_mod.DECISION_LOG_PATH} is empty")
    buffer = io.StringIO()
    # An empty cache directory: verify also looks at <cache_dir>/checkpoints.
    with tempfile.TemporaryDirectory() as cache_dir, contextlib.redirect_stdout(buffer):
        status = ctx.mods.maintenance.verify(cache_dir=cache_dir, memory_log=str(copy))
    lines = buffer.getvalue().splitlines()
    for line in lines:
        ctx.logger.info("state_maintenance verify: %s", line)
    if status != 0:
        findings = "; ".join(line for line in lines if line.startswith("FAIL:"))
        raise _RunAbort(decision_mod.LOG_FINDING, findings or f"verify returned {status}")
    return TradingMemoryLog({"memory_log_path": str(copy)}).load_entries()


def _summary_reader(ctx, source):
    """A cached reader of ``runs/<date>/summary.json``; ``None`` for a missing file."""
    paperlog_mod = ctx.mods.paperlog
    decision_mod = ctx.mods.decision
    cache: dict[str, object] = {}

    def read(day: str):
        if day not in cache:
            path = paperlog_mod.summary_path(day)
            try:
                blob = source.read(path)
            except paperlog_mod.BlobMissing:
                cache[day] = None
            else:
                text = paperlog_mod.decode_utf8(blob, path)
                try:
                    summary = decision_mod.read_summary(text)
                except decision_mod.SummarySchemaError as exc:
                    raise _RunAbort(decision_mod.SUMMARY_SCHEMA, f"{path}: {exc}") from None
                except decision_mod.SummaryContractError as exc:
                    raise _RunAbort(decision_mod.SUMMARY_CONTRACT, f"{path}: {exc}") from None
                # The path picks the file, the field dates the run: both must
                # name the same day, or a copied summary would pass as another
                # day's and the supersede check would read the wrong date.
                if summary.trade_date != day:
                    raise _RunAbort(
                        decision_mod.SUMMARY_CONTRACT,
                        f"{path}: trade_date {summary.trade_date} does not match the path date {day}",
                    )
                cache[day] = summary
        return cache[day]

    return read


def _local_chain(ctx, source, tickers) -> tuple[dict, list[str]]:
    """Everything that needs no gateway: the log, the summaries, the freshness.

    Returns the rows (input order) and the tickers that still need the gateway. A Hold
    ends here, so it never connects (SC1).
    """
    decision_mod = ctx.mods.decision
    rows = {ticker: _new_row(ticker) for ticker in dict.fromkeys(tickers)}
    latest = decision_mod.latest_entries(_read_log_entries(ctx, source))
    run_dates = source.list_run_dates()
    read_summary = _summary_reader(ctx, source)
    remaining: list[str] = []
    for ticker, row in rows.items():
        entry = latest.get(ticker)
        if entry is None:
            state, detail = decision_mod.NO_DECISION, "no entry for this ticker in the log"
            if run_dates:
                newest = read_summary(run_dates[-1])
                found = (
                    decision_mod.newer_summary_state(date.min, newest, ticker) if newest else None
                )
                if found:
                    state = found
                    detail = f"summary of {run_dates[-1]} reports this ticker, the log has no entry"
            _finish_row(ctx, row, state, detail)
            continue
        entry_day = entry["date"]
        parsed = decision_mod.parse_trade_date(entry_day)
        row["rating"] = entry["rating"]
        row["trade_date"] = entry_day
        verdict = decision_mod.evaluate_decision(entry, read_summary(entry_day) if parsed else None)
        row["rating_source"] = verdict.rating_source
        if verdict.state != decision_mod.EXECUTABLE:
            _finish_row(ctx, row, verdict.state, verdict.detail)
            continue
        newer = [day for day in run_dates if day > entry_day]
        if newer:
            summary = read_summary(newer[-1])
            found = decision_mod.newer_summary_state(parsed, summary, ticker) if summary else None
            if found:
                detail = f"summary of {newer[-1]} supersedes the log entry of {entry_day}"
                _finish_row(ctx, row, found, detail)
                continue
        fresh = decision_mod.freshness(parsed, ctx.now_utc, ctx.calendar)
        row["freshness"] = {
            "state": fresh.state,
            "execution_day": fresh.execution_day.isoformat() if fresh.execution_day else None,
            "in_session_day": fresh.in_session_day,
            "gap_days": fresh.gap_days,
            "weekend_gap": fresh.weekend_gap,
            "closed_sessions": [day.isoformat() for day in fresh.closed_sessions],
        }
        if fresh.state != decision_mod.FRESH:
            _finish_row(ctx, row, fresh.state, fresh.detail)
            continue
        remaining.append(ticker)
    return rows, remaining


def _load_stored_contracts(ctx) -> dict:
    """The persisted contracts, read only: ``preview`` never learns, writes or repairs one."""
    contracts_mod = ctx.mods.contracts
    path = Path(ctx.args.contracts or default_contracts_file()).resolve()
    try:
        return contracts_mod.load_contracts_file(path)
    except FileNotFoundError:
        history = contracts_mod.contracts_history_path(path)
        if history.exists() and history.stat().st_size > 0:
            hint = f"{path} not found; {history} exists, restore contracts.json manually"
        else:
            hint = f"{path} not found; create it with: resolve --init AAPL MSFT NVDA"
        raise _RunAbort("CONTRACTS_MISSING", hint) from None
    except OSError as exc:
        raise ConfigError(f"contracts file: {path}: unreadable ({type(exc).__name__})") from exc
    except contracts_mod.ContractsFileError as exc:
        raise ConfigError(f"contracts file: {exc}") from exc


def _session_info(result, closed: bool) -> dict:
    return {
        "state": result.state,
        "closed": closed,
        "session_day": result.session_day,
        "window_start": _iso(result.window.start) if result.window else None,
        "window_end": _iso(result.window.end) if result.window else None,
        "next_open": _iso(result.next_open),
        "detail": result.detail,
    }


def _position_and_orders(ctx, broker, row: dict, identity, spec, snapshot) -> tuple[float, tuple]:
    """Position by conId (other conIds are reported, never netted) and the open orders."""
    ticker = row["ticker"]
    held = 0.0
    elsewhere = []
    for position in snapshot.positions:
        if position.con_id == identity.con_id:
            held += position.quantity
        elif position.symbol == spec.symbol:
            # Same symbol, other contract: reported, never netted (D-11).
            elsewhere.append({"con_id": position.con_id, "quantity": position.quantity})
            ctx.logger.warning(
                "ibkr-state=POSITION_OTHER_CONID ticker=%s conId=%s quantity=%s",
                ticker,
                position.con_id,
                position.quantity,
            )
    row["position"] = {"con_id": identity.con_id, "held": held, "other_conid": elsewhere}
    orders = broker.open_orders(identity.con_id)
    row["open_orders"] = [
        {
            "con_id": order.con_id,
            "action": order.action,
            "quantity": order.quantity,
            "order_type": order.order_type,
            "status": order.status,
            "client_id": order.client_id,
        }
        for order in orders
    ]
    return held, orders


def _preview_ticker(ctx, broker, row: dict, result, snapshot) -> None:
    """Position by conId, open orders, target, whatIf preview and verdict for one ticker."""
    contracts_mod = ctx.mods.contracts
    decision_mod = ctx.mods.decision
    ticker = row["ticker"]
    identity = result.identity
    spec = contracts_mod.CONTRACT_TABLE[ticker]
    held, orders = _position_and_orders(ctx, broker, row, identity, spec, snapshot)
    # The block is the operator's fixed share count from the table, never derived from a price.
    plan = decision_mod.plan_order(
        row["rating"], held_qty=held, open_orders=len(orders), block_qty=spec.block_qty
    )
    if plan.state != decision_mod.INTENT:
        _finish_row(ctx, row, plan.state, plan.detail)
        return
    preview = broker.preview_order(
        con_id=identity.con_id,
        symbol=spec.symbol,
        sec_type=spec.sec_type,
        currency=identity.currency,
        primary_exchange=identity.primary_exchange,
        action=plan.side,
        quantity=plan.quantity,
    )
    verdict = decision_mod.judge_preview(
        preview,
        available_funds=snapshot.available_funds,
        funds_currency=snapshot.available_funds_currency,
        account_currency=snapshot.cash_currency,
    )
    row["intent"] = {
        "side": plan.side,
        "quantity": plan.quantity,
        "order_type": "MKT",
        "tif_sent": preview.sent_tif,
    }
    row["preview"] = {
        "state": preview.state,
        "init_margin_change": preview.init_margin_change,
        "maint_margin_change": preview.maint_margin_change,
        "commission": preview.commission,
        "commission_currency": preview.commission_currency,
        "warning_text": preview.warning_text,
        "reject_reason": verdict.reject_reason,
        "reject_source": verdict.reject_source,
        "errors": [[code, text] for code, text in preview.errors],
        "tif_sent": preview.sent_tif,
        "effective_tif": preview.effective_tif,
    }
    row["budget"] = {
        "available_funds": snapshot.available_funds,
        "currency": snapshot.available_funds_currency,
    }
    ctx.logger.info(
        "ibkr-state=PREVIEW_RESULT ticker=%s sha=%s side=%s quantity=%s initMarginChange=%s "
        "commission=%s %s rejectReason=%r tif_sent=%s tif_effective=%s",
        ticker,
        ctx.sha,
        plan.side,
        plan.quantity,
        preview.init_margin_change,
        preview.commission,
        preview.commission_currency,
        verdict.reject_reason,
        preview.sent_tif,
        preview.effective_tif,
    )
    _finish_row(ctx, row, verdict.state, verdict.detail)


def _resolve_and_preview(ctx, broker, rows: dict, to_resolve: list[str]) -> None:
    """Resolve against the stored contracts, then judge each surviving ticker."""
    contracts_mod = ctx.mods.contracts
    decision_mod = ctx.mods.decision
    outcome = contracts_mod.resolve_all(
        to_resolve,
        contracts=ctx.stored,
        broker=broker,
        now_utc=ctx.now_utc,
        logger=ctx.logger,
        mode=contracts_mod.MODE_RUN,
    )
    # Every ticker has a stored contract, so nothing is learned; were it otherwise, the
    # events would only be logged, never written.
    for event in outcome.events:
        ctx.logger.warning(
            "ibkr-state=CONTRACT_EVENT_NOT_WRITTEN event=%s ticker=%s", event.event, event.ticker
        )
    snapshot = None
    for result in outcome.results:
        row = rows[result.ticker]
        # A closed market is a mark, not a stop: the preview still runs (D-08).
        closed = result.state == contracts_mod.CLOSED
        row["session"] = _session_info(result, closed)
        if result.rejected:
            _finish_row(ctx, row, result.state, result.detail)
            continue
        if decision_mod.calendar_conflict(ctx.now_utc, ctx.calendar, result.session_day):
            detail = (
                f"exchange calendar and liquid hours disagree about today "
                f"(liquid hours: session day {result.session_day})"
            )
            _finish_row(ctx, row, decision_mod.CALENDAR_CONFLICT, detail)
            continue
        if snapshot is None:
            snapshot = broker.positions()
        _preview_ticker(ctx, broker, row, result, snapshot)


def _gateway_chain(ctx, rows: dict, remaining: list[str]) -> int | None:
    """Everything that needs the gateway; returns an exit code only if the session is unusable."""
    contracts_mod = ctx.mods.contracts
    decision_mod = ctx.mods.decision
    ctx.stored = _load_stored_contracts(ctx)
    to_resolve = []
    for ticker in remaining:
        if ticker in ctx.stored:
            to_resolve.append(ticker)
        else:
            detail = "no stored contract; run resolve first (preview never learns one)"
            _finish_row(ctx, rows[ticker], decision_mod.NOT_RESOLVED_YET, detail)
    if not to_resolve:
        return None
    if not contracts_mod.needs_broker(to_resolve):
        _resolve_and_preview(ctx, None, rows, to_resolve)
        return None
    adapter = ctx.broker_factory(ctx.host, ctx.port, ctx.logger)
    ctx.progress["connecting"] = True
    with adapter as broker:
        ctx.progress["connected"] = True
        health = broker.health()
        if not health.ok:
            line = f'ibkr-state={health.state} code=- detail="{health.detail}"'
            ctx.logger.error(line)
            print(f"error: {line}", file=sys.stderr)
            return EXIT_GATEWAY
        _resolve_and_preview(ctx, broker, rows, to_resolve)
    return None


def _session(ctx):
    """The one broker session of an ``execute`` run: opened on first use, closed with the run."""
    if ctx.broker is not None:
        return ctx.broker
    adapter = ctx.broker_factory(ctx.host, ctx.port, ctx.logger)
    ctx.progress["connecting"] = True
    broker = ctx.stack.enter_context(adapter)
    ctx.progress["connected"] = True
    health = broker.health()
    if not health.ok:
        line = f'ibkr-state={health.state} code=- detail="{health.detail}"'
        ctx.logger.error(line)
        print(f"error: {line}", file=sys.stderr)
        raise _ExecuteStop(EXIT_GATEWAY, health.state, health.detail)
    ctx.broker = broker
    return broker


def _execute_ticker(ctx, broker, row: dict, result, snapshot) -> None:
    """Target, whatIf with ``orderRef``, write-ahead ``intent`` and the placer's completion."""
    contracts_mod = ctx.mods.contracts
    decision_mod = ctx.mods.decision
    guards = ctx.mods.guards
    ledger_mod = ctx.mods.ledger
    ticker = row["ticker"]
    identity = result.identity
    spec = contracts_mod.CONTRACT_TABLE[ticker]
    held, orders = _position_and_orders(ctx, broker, row, identity, spec, snapshot)
    key = guards.decision_key(row["trade_date"], ticker)
    # REQ-45 order deviation: position and already-executed checks run after resolution because
    # they need the resolved conId (and the order_ref for the history lookup); documented for
    # the phase-6 order test (ROADMAP note from 05-09). Two sources per fact, the more
    # cautious one wins (REQ-63); a conflict stops this ticker only (D-11).
    reason = guards.position_conflict(
        ledger_filled_qty=ctx.ledger.filled_quantity(identity.con_id), broker_held=held
    )
    if reason is not None:
        _finish_row(ctx, row, guards.SOURCE_CONFLICT, f"position: {reason}")
        return
    history = _history(ctx)
    known = (*history.open, *history.completed, *history.executions)
    has_ref = any(r.order_ref == key for r in known)
    # "Ledger yes, broker no" cannot get here (key check and reconciliation come first); if it
    # does, the same cautious value applies.
    reason = guards.executed_conflict(
        ledger_attempted=ctx.ledger.attempt_of(key) is not None, history_has_ref=has_ref
    )
    if reason is not None:
        _finish_row(ctx, row, guards.SOURCE_CONFLICT, f"executed: {reason}")
        return
    plan = decision_mod.plan_order(
        row["rating"], held_qty=held, open_orders=len(orders), block_qty=spec.block_qty
    )
    if plan.state != decision_mod.INTENT:
        _finish_row(ctx, row, plan.state, plan.detail)
        return
    # Size before trading hours before switches (REQ-45): a quantity above the cap is rejected
    # and reported, never trimmed (REQ-32); nothing is previewed and no ``intent`` is written.
    cap_reason = guards.check_size(plan.quantity)
    if cap_reason is not None:
        row["intent"] = {"side": plan.side, "quantity": plan.quantity, "order_type": "MKT"}
        ctx.logger.warning(
            "ibkr-state=SIZE_CAP ticker=%s quantity=%s max=%s",
            ticker,
            plan.quantity,
            guards.MAX_QTY_PER_ORDER,
        )
        _finish_row(ctx, row, guards.SIZE_CAP, cap_reason)
        return
    # The session window comes from ``evaluate_session`` with its buffers (D-10): half days
    # shorten it through the broker's liquid hours; no second constant or clock logic here.
    if row["session"] and row["session"].get("closed"):
        detail = (
            f"outside the regular-session window ({result.detail}); "
            f"next open {row['session'].get('next_open')}"
        )
        _finish_row(ctx, row, guards.OUTSIDE_SESSION, detail)
        return
    # Read the switches anew right before the whatIf (REQ-34, D-21): no cache between orders.
    switches = _check_switches(ctx)
    if not switches.allowed:
        _halt_on_switches(ctx, row, switches)
        return
    preview = broker.preview_order(
        con_id=identity.con_id,
        symbol=spec.symbol,
        sec_type=spec.sec_type,
        currency=identity.currency,
        primary_exchange=identity.primary_exchange,
        action=plan.side,
        quantity=plan.quantity,
        order_ref=key,
    )
    # Account from three sources (REQ-63): the connection guard (managedAccounts) came first,
    # here the release file and the optional whatIf echo (D-22). A conflict stops the whole run
    # (D-11): no intent, no further ticker.
    reason = guards.account_conflict(
        managed_account=ctx.mods.broker.EXPECTED_ACCOUNT,
        release_account=switches.release.account,
        echo_account=preview.echo_account,
    )
    if reason is not None:
        ctx.logger.warning('ibkr-state=ACCOUNT_CONFLICT ticker=%s detail="%s"', ticker, reason)
        print(f"execute: {guards.ACCOUNT_CONFLICT} ({reason})")
        raise _ExecuteStop(EXIT_ACCOUNT_GUARD, guards.ACCOUNT_CONFLICT, reason)
    # The orderRef echo (optional, D-22): a different one stops this ticker before any
    # intent, or the order could never be found again by the reconciliation (WR-04).
    reason = guards.order_ref_conflict(decision_key=key, echo_order_ref=preview.echo_order_ref)
    if reason is not None:
        ctx.logger.warning('ibkr-state=ORDER_REF_CONFLICT ticker=%s detail="%s"', ticker, reason)
        _finish_row(ctx, row, guards.SOURCE_CONFLICT, f"orderRef: {reason}")
        return
    verdict = decision_mod.judge_preview(
        preview,
        available_funds=snapshot.available_funds,
        funds_currency=snapshot.available_funds_currency,
        account_currency=snapshot.cash_currency,
    )
    row["intent"] = {
        "side": plan.side,
        "quantity": plan.quantity,
        "order_type": "MKT",
        "tif_sent": preview.sent_tif,
    }
    row["preview"] = {
        "state": preview.state,
        "init_margin_change": preview.init_margin_change,
        "maint_margin_change": preview.maint_margin_change,
        "commission": preview.commission,
        "commission_currency": preview.commission_currency,
        "warning_text": preview.warning_text,
        "reject_reason": verdict.reject_reason,
        "reject_source": verdict.reject_source,
        "errors": [[code, text] for code, text in preview.errors],
        "tif_sent": preview.sent_tif,
        "effective_tif": preview.effective_tif,
        "echo_order_ref": preview.echo_order_ref,
        "echo_account": preview.echo_account,
    }
    row["budget"] = {
        "available_funds": snapshot.available_funds,
        "currency": snapshot.available_funds_currency,
    }
    if verdict.state != decision_mod.PREVIEW_OK:
        _finish_row(ctx, row, verdict.state, verdict.detail)
        return
    # And once more right before the write-ahead line; the result is part of the record.
    switches = _check_switches(ctx)
    ctx.ledger.append(
        ledger_mod.SWITCH_CHECK, decision_key=key, ticker=ticker, **switches.as_record()
    )
    if not switches.allowed:
        _halt_on_switches(ctx, row, switches)
        return
    # The session window anew with a fresh clock (WR-05): the window was judged at the
    # start of the run, and lock, reconciliation, fetch, resolution and the whatIf take time.
    now = ctx.clock()
    if result.window is None or not contracts_mod.window_open(result.window, now):
        detail = (
            f"the regular-session window closed during the run (now {now.isoformat()}, "
            f"window end {_iso(result.window.end) if result.window else None})"
        )
        _finish_row(ctx, row, guards.OUTSIDE_SESSION, detail)
        return
    # Freshness anew with a fresh clock (WR-05): judged at run start until phase 5; the
    # placer sends right after the intent.
    fresh = decision_mod.freshness(
        decision_mod.parse_trade_date(row["trade_date"]), now, ctx.calendar
    )
    if fresh.state != decision_mod.FRESH:
        _finish_row(ctx, row, fresh.state, fresh.detail)
        return
    intent = ledger_mod.intent_record(
        decision_key=key,
        ticker=ticker,
        trade_date=row["trade_date"],
        rating=row["rating"],
        paper_log_sha=ctx.sha,
        side=plan.side,
        quantity=plan.quantity,
        con_id=identity.con_id,
        order_ref=key,
        weekend_gap=bool(row["freshness"]["weekend_gap"]),
        rating_source=row["rating_source"],
    )
    # A second size check at the last step before the write-ahead line, with the same
    # constant as the first one: after the ``intent`` nothing may refuse the order (WR-02).
    cap_reason = guards.check_size(intent["quantity"])
    if cap_reason is not None:
        ctx.logger.warning(
            "ibkr-state=SIZE_CAP ticker=%s quantity=%s max=%s check=before-intent",
            ticker,
            intent["quantity"],
            guards.MAX_QTY_PER_ORDER,
        )
        _finish_row(ctx, row, guards.SIZE_CAP, f"size check before intent: {cap_reason}")
        return
    # Write-ahead: the line is on disk (fsync) before the placer may complete anything.
    ctx.ledger.append(ledger_mod.INTENT, **intent)
    ctx.logger.info(
        "ibkr-state=EXECUTE_INTENT ticker=%s key=%s sha=%s side=%s quantity=%s",
        ticker,
        key,
        ctx.sha,
        plan.side,
        plan.quantity,
    )
    # What the live placer needs to send: the same values the whatIf above used.
    ctx.placing = SimpleNamespace(
        broker=broker,
        symbol=spec.symbol,
        sec_type=spec.sec_type,
        currency=identity.currency,
        primary_exchange=identity.primary_exchange,
    )
    state = ctx.placer.complete(ctx, intent)
    _finish_row(ctx, row, state, f"{plan.side} {plan.quantity} {key}")


def _execute_gateway_chain(ctx, rows: dict, remaining: list[str]) -> None:
    """Resolution, position, target and whatIf for the tickers that need the gateway."""
    contracts_mod = ctx.mods.contracts
    decision_mod = ctx.mods.decision
    ctx.stored = _load_stored_contracts(ctx)
    to_resolve = []
    for ticker in remaining:
        if ticker in ctx.stored:
            to_resolve.append(ticker)
        else:
            detail = "no stored contract; run resolve first (execute never learns one)"
            _finish_row(ctx, rows[ticker], decision_mod.NOT_RESOLVED_YET, detail)
    if not to_resolve:
        return
    broker = _session(ctx)
    outcome = contracts_mod.resolve_all(
        to_resolve,
        contracts=ctx.stored,
        broker=broker,
        now_utc=ctx.now_utc,
        logger=ctx.logger,
        mode=contracts_mod.MODE_RUN,
    )
    for event in outcome.events:
        ctx.logger.warning(
            "ibkr-state=CONTRACT_EVENT_NOT_WRITTEN event=%s ticker=%s", event.event, event.ticker
        )
    snapshot = None
    for result in outcome.results:
        row = rows[result.ticker]
        if ctx.halted is not None:
            # A switch closed earlier in this run: no further broker call for this ticker.
            _halt_on_switches(ctx, row, ctx.halted)
            continue
        # A closed market is noted here; ``_execute_ticker`` refuses it after the size check.
        closed = result.state == contracts_mod.CLOSED
        row["session"] = _session_info(result, closed)
        if result.rejected:
            _finish_row(ctx, row, result.state, result.detail)
            continue
        # REQ-63 tradability: exchange calendar against liquidHours decides per ticker (D-22);
        # order status 399 joins with the phase-6 placer.
        if decision_mod.calendar_conflict(ctx.now_utc, ctx.calendar, result.session_day):
            detail = (
                f"exchange calendar and liquid hours disagree about today "
                f"(liquid hours: session day {result.session_day})"
            )
            _finish_row(ctx, row, decision_mod.CALENDAR_CONFLICT, detail)
            continue
        if snapshot is None:
            snapshot = broker.positions()
        _execute_ticker(ctx, broker, row, result, snapshot)


def run_preview(
    args, mods, broker_factory, paper_log_factory, calendar, logger, progress, now_utc: datetime
) -> int:
    """The dry run from the paper-log to a judged whatIf preview; nothing is sent.

    The earlier ``--out`` is removed first, so a failed run leaves no record that
    looks like a result. The paper-log is read before any gateway contact.
    """
    out = Path(args.out or default_preview_file()).resolve()
    try:
        _discard_previous(out, logger)
    except OSError as exc:
        return _fail(
            logger,
            EXIT_CONFIG,
            f"ibkr-state=OUTPUT_INVALID previous file not removable: {out} "
            f"({type(exc).__name__}: {exc})",
            f"previous preview output not removable: {out} ({type(exc).__name__})",
        )
    raw = read_settings(args.env_file)
    host, port, _account = validate_settings(raw, mods.broker.EXPECTED_ACCOUNT)
    remote, branch = paper_log_settings(raw, mods.paperlog)
    # A broken contract table is a configuration error (exit 1); left alone it
    # would surface mid-window as a plan_order ValueError and exit as a gateway
    # failure with the session open and the finished rows lost.
    problems = mods.contracts.table_problems()
    if problems:
        raise ConfigError("contract table: " + "; ".join(problems))
    source = paper_log_factory(REPO_ROOT, remote, branch)
    ctx = SimpleNamespace(
        mods=mods,
        logger=logger,
        out=out,
        remote=remote,
        branch=branch,
        sha=None,
        now_utc=now_utc,
        host=host,
        port=port,
        calendar=calendar,
        progress=progress,
        broker_factory=broker_factory,
        args=args,
    )
    try:
        ctx.sha = source.fetch()
        rows, remaining = _local_chain(ctx, source, args.tickers)
    except mods.paperlog.PaperLogUnavailable as exc:
        # No second attempt and no fall back to a local ref (D-02).
        return _abort_run(ctx, _RunAbort(mods.decision.PAPER_LOG_UNAVAILABLE, exc.reason))
    except _RunAbort as stop:
        return _abort_run(ctx, stop)
    if remaining:
        try:
            early_exit = _gateway_chain(ctx, rows, remaining)
        except _RunAbort as stop:
            return _abort_run(ctx, stop, rows)
        if early_exit is not None:
            return early_exit
    return _finish_run(ctx, rows)


if __name__ == "__main__":
    sys.exit(main())
