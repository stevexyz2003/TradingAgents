"""Read-only probe for the phase-5 operator checkpoint.

Reads the order history once, or sends one whatIf with an orderRef; it never sends an
order and never cancels one. Manual use against the paper gateway:

    .venv/Scripts/python.exe scripts/smoke/ibkr_order_probe.py --history
    .venv/Scripts/python.exe scripts/smoke/ibkr_order_probe.py --whatif AAPL \
        --order-ref "2026-10-09|AAPL"

``--history`` prints open orders, completed orders and executions as JSON
(measurement A2). ``--whatif`` prints the preview state, error codes and the
orderRef/account the gateway echoed (measurements A3 and A5). Only the adapter's
public read methods are used, behind its socket barrier.

Exit codes: 0 ok, 1 configuration or usage, 3 gateway unavailable, 8 account guard.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_EXECUTOR_PATH = Path(__file__).resolve().parents[1] / "ibkr_executor.py"


def _load_executor():
    """The executor module, loaded by path; its loaders and settings readers are reused."""
    if "ibkr_executor" in sys.modules:
        return sys.modules["ibkr_executor"]
    spec = importlib.util.spec_from_file_location("ibkr_executor", _EXECUTOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_executor"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_executor", None)
        raise
    return module


_executor = _load_executor()
DEFAULT_ENV_FILE = _executor.DEFAULT_ENV_FILE
close_logging = _executor.close_logging
setup_logging = _executor.setup_logging

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_GATEWAY = 3
EXIT_ACCOUNT_GUARD = 8


class _ProbeError(Exception):
    """A usage or configuration problem; carries the exit code."""

    def __init__(self, message: str, code: int = EXIT_CONFIG):
        super().__init__(message)
        self.code = code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ibkr_order_probe",
        description="Read-only probe: order history once, or one whatIf with an orderRef.",
    )
    parser.add_argument("--history", action="store_true", help="print the order history as JSON")
    parser.add_argument("--whatif", metavar="TICKER", help="send one whatIf BUY for TICKER")
    parser.add_argument("--order-ref", default="", help="orderRef to put on the whatIf order")
    parser.add_argument("--quantity", type=int, default=1, choices=(1, 2), help="whatIf shares")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser


def _dump(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _history(broker) -> dict:
    history = broker.order_history()
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "open": [dataclasses.asdict(item) for item in history.open],
        "completed": [dataclasses.asdict(item) for item in history.completed],
        "executions": [dataclasses.asdict(item) for item in history.executions],
    }


def _stored_identity(ticker: str):
    contracts_mod = _executor.load_contracts_module()
    path = _executor.default_contracts_file()
    try:
        stored = contracts_mod.load_contracts_file(path)
    except FileNotFoundError:
        raise _ProbeError(f"{path} not found; create it with: resolve --init {ticker}") from None
    except (OSError, ValueError) as exc:
        raise _ProbeError(f"contracts file: {path}: {exc}") from exc
    entry = stored.get(ticker)
    spec = contracts_mod.CONTRACT_TABLE.get(ticker)
    if entry is None or spec is None:
        raise _ProbeError(f"{ticker}: no stored contract; run: resolve --init {ticker}")
    return entry.identity, spec


def _whatif(broker, args) -> dict:
    identity, spec = _stored_identity(args.whatif)
    result = broker.preview_order(
        con_id=identity.con_id,
        symbol=spec.symbol,
        sec_type=spec.sec_type,
        currency=identity.currency,
        primary_exchange=identity.primary_exchange,
        action="BUY",
        quantity=args.quantity,
        order_ref=args.order_ref,
    )
    return {
        "ticker": args.whatif,
        "order_ref": args.order_ref,
        "state": result.state,
        "errors": [list(item) for item in result.errors],
        "echo_order_ref": result.echo_order_ref,
        "echo_account": result.echo_account,
        "effective_tif": result.effective_tif,
        "sent_tif": result.sent_tif,
        "init_margin_change": result.init_margin_change,
        "commission": result.commission,
    }


def _err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def main(argv=None, *, broker_factory=None) -> int:
    args = _build_parser().parse_args(argv)
    if bool(args.history) == bool(args.whatif):
        _err("choose exactly one of --history or --whatif TICKER")
        return EXIT_CONFIG
    broker_mod = _executor.load_broker_module()
    try:
        raw = _executor.read_settings(args.env_file)
        host, port, _account = _executor.validate_settings(raw, broker_mod.EXPECTED_ACCOUNT)
    except (_executor.MissingSettings, _executor.ConfigError) as exc:
        _err(str(exc))
        return EXIT_CONFIG
    logger = setup_logging(_executor.default_log_file())
    if broker_factory is None:

        def broker_factory(host, port, logger):
            return broker_mod.IbkrBroker(host, port, logger=logger)

    try:
        with broker_factory(host, port, logger) as broker:
            health = broker.health()
            if not health.ok:
                _err(f"gateway not healthy: {health.state} {health.detail}")
                return EXIT_GATEWAY
            payload = _history(broker) if args.history else _whatif(broker, args)
        _dump(payload)
        return EXIT_OK
    except _ProbeError as exc:
        _err(str(exc))
        return exc.code
    except broker_mod.AccountGuardViolation as exc:
        _err(str(exc))
        return EXIT_ACCOUNT_GUARD
    except (broker_mod.GatewayUnavailable, broker_mod.ReadOnlyViolation) as exc:
        _err(str(exc))
        return EXIT_GATEWAY
    finally:
        close_logging()


if __name__ == "__main__":
    sys.exit(main())
