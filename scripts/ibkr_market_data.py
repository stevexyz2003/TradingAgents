"""IBKR market-data stream: a read-only session of its own, outside the order path.

REQ-IBKR-26: market data is not part of the order path. The executor, the adapter
(``ibkr_broker.py``) and the decision module never request it, and
``tests/test_ibkr_isolation.py`` guards that. This module is the one place that
does, on its own session with its own clientId, so a missing subscription
(10089/10090) or a stalled stream can never hold up an order.

The session itself is an ``IbkrBroker``: the same write barrier, paper-account
guard and delayed data type (``reqMarketDataType(3)``), and the client library
stays imported in the adapter only. Values are delayed on the paper gateway
unless a live subscription is held.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_BROKER_PATH = Path(__file__).resolve().parent / "ibkr_broker.py"


def _load_broker_module():
    """The adapter module, loaded once under the name ``ibkr_broker``.

    Same rule as ``ibkr_executor.load_broker_module``: registered in
    ``sys.modules`` before it runs, so this module, the executor and the tests
    share one set of exception classes.
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


_broker = _load_broker_module()
GatewayUnavailable = _broker.GatewayUnavailable

#: Fixed API client id of the stream session, next to the executor's 20001 and
#: outside 0..9999 for the same reasons (handbook, "clientId"). Its own id lets
#: the stream run while the executor is connected.
MARKET_DATA_CLIENT_ID = 20002

#: Seconds between link/socket checks while a stream is running. The loop delivers
#: ticks in between; this only bounds how fast a dropped link or a set stop flag
#: ends the stream.
STREAM_POLL_S = 0.1


@dataclass(frozen=True)
class MarketTick:
    """One market-data update of a streamed contract, broker-neutral.

    No library object leaves this module: a ``Ticker`` becomes this. Fields the
    gateway has not sent yet are ``None`` (the library uses NaN).
    """

    con_id: int
    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    bid_size: float | None
    ask_size: float | None
    last_size: float | None
    volume: float | None
    time: datetime | None


def _tick_from_ticker(ticker) -> MarketTick:
    """A broker-neutral ``MarketTick`` from a library ``Ticker``."""
    contract = getattr(ticker, "contract", None)
    money = _broker._money
    return MarketTick(
        con_id=int(getattr(contract, "conId", 0) or 0),
        symbol=_broker._text(contract, "symbol") if contract is not None else "",
        bid=money(getattr(ticker, "bid", None)),
        ask=money(getattr(ticker, "ask", None)),
        last=money(getattr(ticker, "last", None)),
        bid_size=money(getattr(ticker, "bidSize", None)),
        ask_size=money(getattr(ticker, "askSize", None)),
        last_size=money(getattr(ticker, "lastSize", None)),
        volume=money(getattr(ticker, "volume", None)),
        time=getattr(ticker, "time", None),
    )


class IbkrMarketData:
    """One read-only market-data session against the paper gateway.

    Public: ``connect``, ``stream``. Use as a context manager; leaving it
    disconnects. Keyword arguments other than ``client_id`` and ``poll`` go to
    the underlying ``IbkrBroker`` (``ib_factory``, ``loop``, timeouts, ...).
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        client_id: int = MARKET_DATA_CLIENT_ID,
        poll: float = STREAM_POLL_S,
        logger: logging.Logger | None = None,
        **session_kwargs,
    ):
        self._log = logger or logging.getLogger("ibkr_market_data")
        self._poll = poll
        self._session = _broker.IbkrBroker(
            host, port, client_id=client_id, logger=self._log, **session_kwargs
        )

    def __enter__(self) -> IbkrMarketData:
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self._session._disconnect()

    def connect(self) -> None:
        """Connect read-only with the paper guard and delayed data; see ``IbkrBroker.connect``."""
        self._session.connect()

    def stream(
        self,
        con_ids,
        on_tick,
        *,
        duration: float | None = None,
        stop=None,
        generic_ticks: str = "",
    ) -> None:
        """Stream market-data ticks for ``con_ids`` to ``on_tick``; read-only.

        ``reqMktData``/``cancelMktData`` (message ids 1 and 2) are not in the
        adapter's write message ids, so the write barrier lets them through; the
        stream never places, previews or changes an order.

        Each conId is qualified once (``reqContractDetails``, a fail-closed read)
        and then subscribed. Every update calls ``on_tick`` with a ``MarketTick``;
        a callback that raises is logged and the stream continues. The call
        returns when ``duration`` seconds have elapsed, when ``stop`` (a
        ``threading.Event``-like object) is set, or raises ``GatewayUnavailable``
        when the link drops.

        Fail-closed: no subscription starts while a link flag (1100/2110/1300) is
        open, and a 1100/1101/1102/1300/2110 during the stream ends it. Every
        subscription is cancelled before returning; the library cancels none.
        """
        session = self._session
        ib, handles = session._ib, session._handles
        if ib is None or handles is None:
            raise GatewayUnavailable("NOT_CONNECTED", 504, "no session; connect() first")
        opened = session._open_link()
        if opened is not None:
            raise GatewayUnavailable(opened[0], None, f"{opened[1]}; no stream started")

        wanted = [int(c) for c in con_ids]
        if not wanted:
            return

        contracts = []
        for con_id in wanted:
            details = session._read(
                "reqContractDetails",
                lambda cid=con_id: ib.reqContractDetailsAsync(handles.contract(conId=cid)),
            )
            if len(details) != 1:
                raise GatewayUnavailable(
                    _broker.REQUEST_FAILED,
                    None,
                    f"conId {con_id} returned {len(details)} contracts; not streamable",
                )
            contracts.append(details[0].contract)

        def deliver(tickers) -> None:
            for ticker in tickers:
                try:
                    on_tick(_tick_from_ticker(ticker))
                except Exception:  # noqa: BLE001 — a callback error must not kill the stream
                    con = getattr(getattr(ticker, "contract", None), "conId", "-")
                    self._log.exception("ibkr-state=STREAM_CALLBACK_ERROR conId=%s", con)

        mark = len(session._link_codes)
        ib.pendingTickersEvent += deliver
        subscribed = []
        try:
            for contract in contracts:
                # Returns a live Ticker; the loop updates it in place and fires
                # pendingTickersEvent on each change.
                ib.reqMktData(contract, generic_ticks, False, False)
                subscribed.append(contract)
            self._log.info(
                "ibkr-state=STREAM_STARTED conIds=%s duration=%s",
                wanted,
                "unbounded" if duration is None else f"{duration:g}s",
            )
            self._run(ib, mark, duration, stop)
        finally:
            for contract in subscribed:
                with contextlib.suppress(Exception):
                    ib.cancelMktData(contract)
            with contextlib.suppress(ValueError, AttributeError):
                ib.pendingTickersEvent -= deliver
            self._log.info("ibkr-state=STREAM_STOPPED conIds=%s", wanted)

    def _run(self, ib, mark: int, duration: float | None, stop) -> None:
        """Pump the session's loop until duration/stop/link-loss; raise on a dropped link."""
        session = self._session
        loop = session._loop
        poll = self._poll

        async def driver():
            deadline = None if duration is None else loop.time() + duration
            while True:
                if stop is not None and stop.is_set():
                    return
                await asyncio.sleep(poll)
                if not ib.isConnected():
                    raise GatewayUnavailable(
                        "NOT_CONNECTED", 504, "socket went down during the stream; stream ended"
                    )
                event = session._link_event_since(mark)
                if event is not None:
                    state, code = event
                    raise GatewayUnavailable(
                        state, code, f"link event {code} during the stream; stream ended"
                    )
                if deadline is not None and loop.time() >= deadline:
                    return

        loop.run_until_complete(driver())
