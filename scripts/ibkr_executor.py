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

Operating manual: ``scripts/IBKR_EXECUTION.md``.

    ibkr_executor.py account --out PATH [--log-file PATH] [--env-file PATH]
    ibkr_executor.py resolve TICKER... [--contracts PATH] [--init | --rebaseline TICKER]
                             [--out PATH] [--log-file PATH] [--env-file PATH]

Settings come from the ``.env`` at the repository root (a fixed path, not the
current directory) or from ``--env-file``. Only IBKR_HOST, IBKR_PORT,
IBKR_ACCOUNT_ID and IBKR_TRADING_MODE are taken from it; the API needs no user
name or password, and this command copies neither.

Every run writes a UTF-8 log file; the console gets one summary or error line.

Exit codes:
    0   ok, including "nothing to do"
    1   configuration error - nothing was done
    2   precondition not met - a ticker was rejected, or contracts.json is missing (resolve)
    3   gateway/session not reachable
    4   kill switch active or release missing (reserved for later phases)
    5   order rejected (reserved for later phases)
    6   reconciliation unresolved, run aborted (reserved for later phases)
    7   lock not acquired (second instance), clean exit (reserved for later phases)
    8   account guard violated (managedAccounts != ["DUQ634065"])
    20  IBKR settings missing or unreadable - same meaning as EXIT_NO_CREDENTIALS in daily_paper_run.py

Code 3 means "gateway" here, unlike EXIT_RUN_FAILED (3) in the paper run.
"""

import argparse
import importlib.util
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values

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
EXIT_NO_CREDENTIALS = 20

#: The settings the command needs (D-06). User name and password stay out:
#: the API does not need them, so they are neither copied nor logged.
REQUIRED_ENV = ("IBKR_HOST", "IBKR_PORT", "IBKR_ACCOUNT_ID")
#: Optional; when set it must say paper.
TRADING_MODE_ENV = "IBKR_TRADING_MODE"
EXPECTED_TRADING_MODE = "paper"

#: Top-level key of the portfolio JSON that dates the snapshot (UTC, ISO 8601).
#: Same literal as ``PORTFOLIO_AS_OF_KEY`` in daily_paper_run.py; a test keeps them in step.
AS_OF_KEY = "as_of"

#: The repository's .env, by a fixed path so the current directory does not matter.
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

_BROKER_PATH = Path(__file__).with_name("ibkr_broker.py")
_CONTRACTS_PATH = Path(__file__).with_name("ibkr_contracts.py")

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
    wanted = (*REQUIRED_ENV, TRADING_MODE_ENV)
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
        contracts = None
    else:
        mode = contracts_mod.MODE_REBASELINE if args.rebaseline else contracts_mod.MODE_RUN
        try:
            contracts = contracts_mod.load_contracts_file(contracts_path)
        except contracts_mod.ContractsFileMissing:
            return _fail(
                logger,
                EXIT_PRECONDITION,
                f"ibkr-state=CONTRACTS_MISSING {contracts_path}; create it with resolve --init",
                f"{contracts_path} not found; create it with: resolve --init AAPL MSFT NVDA",
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
            contracts_mod.commit_contracts(contracts_path, outcome.contracts, outcome.events)
        except OSError as exc:
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
            "ibkr-state=%s ticker=%s state=%s detail=%r",
            state,
            result.ticker,
            result.state,
            result.detail,
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
        description="IBKR paper executor for DUQ634065 (read-only in phases 2-3).",
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
    return parser


def main(argv: list[str] | None = None, *, broker_factory=None, clock=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on a usage error and on --help; return a code instead.
        return EXIT_CONFIG if exc.code else EXIT_OK
    clock = clock or (lambda: datetime.now(UTC))

    if not args.command:
        parser.print_usage(sys.stderr)
        print("error: ibkr_executor.py needs a subcommand: account, resolve", file=sys.stderr)
        return EXIT_CONFIG
    if args.command == "account" and args.out is None:
        print("error: account needs --out PATH", file=sys.stderr)
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
    logger.info("previous portfolio removed: %s", out)


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


if __name__ == "__main__":
    sys.exit(main())
