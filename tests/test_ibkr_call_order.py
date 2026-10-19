"""REQ-45 call order in the live path, with the four documented deviations (ROADMAP phase 6, SC2 note of 2026-10-17).

The observation hooks only append to one event stream; they call the original first and hand
its result back unchanged, so the chain under test is never altered (T-06-41).
"""

import pytest

from tests import ibkr_fakes
from tests.test_ibkr_execute import (
    CON_IDS,
    KEY,
    OPEN_NOW,
    SHA,
    _buy_paper,
    _fake_for,
    _fixed,
    _live_run,
    _paper,
    _read_records,
    _summary,
    _two_buys,
    decision,
    executor,
    guards,
    ledger_mod,
    paperlog,
)

pytestmark = pytest.mark.unit

PREV_KEY = "2026-10-08|MSFT"
STALE_KEY = "2026-10-01|AAPL"


@pytest.fixture(scope="module")
def loop():
    yield from ibkr_fakes.session_loop()


@pytest.fixture(autouse=True)
def _pin_modules(monkeypatch):
    """Hand the executor the module instances this test observes."""
    monkeypatch.setattr(executor, "load_decision_module", lambda: decision)
    monkeypatch.setattr(executor, "load_paperlog_module", lambda: paperlog)
    monkeypatch.setattr(executor, "load_guards_module", lambda: guards)
    monkeypatch.setattr(executor, "load_ledger_module", lambda: ledger_mod)


@pytest.fixture(autouse=True)
def _block_real_connect(monkeypatch):
    ibkr_fakes.block_real_ib_connect(monkeypatch)


@pytest.fixture(autouse=True)
def _close_logging():
    yield
    executor.close_logging()


@pytest.fixture(autouse=True)
def _local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(executor, "POST_ORDER_RETRY_S", 0)


class _SessionDict(dict):
    """The session info of a row; reading ``closed`` is the trading-hours check."""

    stream = None

    def get(self, key, default=None):
        if key == "closed":
            self.stream.append(("check", "session"))
        return super().get(key, default)


def _note_lock(stream):
    """Record once that the ledger lock file exists; called at the first observed event."""
    if not any(item[0] == "lock" for item in stream):
        lock = executor.default_ledger_file().with_name("ledger.jsonl.lock")
        assert lock.exists(), "an observed step came before the ledger lock"
        stream.append(("lock", "held"))


class _Tee(list):
    """``FakeIB.calls`` that also feeds the event stream; the first call must find the lock."""

    def __init__(self, stream, fake):
        super().__init__()
        self._stream = stream
        self._fake = fake

    def append(self, name):
        _note_lock(self._stream)
        if name == "placeOrder":
            on_disk = _read_records(executor.default_ledger_file())
            if any(r["event"] == "intent" and r.get("decision_key") == KEY for r in on_disk):
                self._stream.append(("disk", "intent"))
        self._stream.append(("broker", name))
        super().append(name)


def _observe(monkeypatch, fake):
    """Wire every hook to one event stream and return it."""
    stream = []
    _SessionDict.stream = stream
    fake.calls = _Tee(stream, fake)

    real_append = ledger_mod.Ledger.append

    def append(self, event, **fields):
        result = real_append(self, event, **fields)
        stream.append(("ledger", event))
        return result

    monkeypatch.setattr(ledger_mod.Ledger, "append", append)

    def wrap(module, name, label):
        original = getattr(module, name)

        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            stream.append(("check", label))
            return result

        monkeypatch.setattr(module, name, wrapper)

    wrap(decision, "plan_order", "quantity")
    wrap(guards, "check_size", "size")

    real_switches = guards.check_switches

    def check_switches(*args, **kwargs):
        _note_lock(stream)  # the first switch read is the preflight, right after the lock
        result = real_switches(*args, **kwargs)
        stream.append(("check", "kill"))
        return result

    monkeypatch.setattr(guards, "check_switches", check_switches)

    real_info = executor._session_info

    def session_info(result, closed):
        return _SessionDict(real_info(result, closed))

    monkeypatch.setattr(executor, "_session_info", session_info)
    return stream


class _TracingPaperLog:
    """Wraps the fixture paper log; ``fetch`` is the paper-log access of the run."""

    def __init__(self, inner, stream):
        self._inner = inner
        self._stream = stream

    def fetch(self):
        self._stream.append(("paperlog", "fetch"))
        return self._inner.fetch()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _prepare_live_ledger(key, ticker, trade_date):
    """An open live intent of an earlier day, written the way a former run would have."""
    path = executor.default_ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    led = ledger_mod.Ledger.open(
        path, mode=ledger_mod.MODE_LIVE, clock=_fixed(OPEN_NOW), run_id="prepared"
    )
    led.append(
        ledger_mod.INTENT,
        **ledger_mod.intent_record(
            decision_key=key,
            ticker=ticker,
            trade_date=trade_date,
            rating="Buy",
            paper_log_sha=SHA,
            side="BUY",
            quantity=2,
            con_id=CON_IDS[ticker],
            order_ref=key,
            weekend_gap=False,
        ),
    )


def _is_subsequence(expected, stream):
    iterator = iter(stream)
    return all(item in iterator for item in expected)


def _index(stream, item, start=0):
    return stream.index(item, start)


def _own_fill():
    return ibkr_fakes.fill(
        CON_IDS["AAPL"],
        KEY,
        2,
        exec_id="0000e0d5.6710a3c5.01.01",
        price=250.1,
        perm_id=777,
        order_id=5,
    )


def _own_completed():
    return ibkr_fakes.completed_trade(
        CON_IDS["AAPL"],
        status="Filled",
        order_ref=KEY,
        action="BUY",
        quantity=2,
        filled=2,
        perm_id=777,
        order_id=5,
    )


def _ordered_run(tmp_path, loop, monkeypatch):
    """A full live run (AAPL Buy) after an open intent of the day before that the broker filled."""
    _prepare_live_ledger(PREV_KEY, "MSFT", "2026-10-08")
    fake = _fake_for(
        ("AAPL", "MSFT"),
        executions=[ibkr_fakes.fill(CON_IDS["MSFT"], PREV_KEY, 2)],
        place_executions=[_own_fill()],
        place_completed=_own_completed(),
    )
    stream = _observe(monkeypatch, fake)
    paper = _TracingPaperLog(_buy_paper(tmp_path), stream)
    code, records = _live_run(tmp_path, loop, fake, paper=paper, tickers=("AAPL",))
    return fake, stream, code, records


def test_live_call_order_follows_req45_with_four_deviations(tmp_path, loop, monkeypatch):
    fake, stream, code, _records = _ordered_run(tmp_path, loop, monkeypatch)
    assert code == executor.EXIT_OK
    expected = [
        ("lock", "held"),
        # deviation 1: the switch preflight (first kill read, then run_start with the switch
        # state) comes right after the lock and before the reconciliation reads
        ("check", "kill"),
        ("ledger", "run_start"),
        ("broker", "open_orders"),
        ("broker", "completed_orders"),
        ("broker", "executions"),
        ("ledger", "reconcile"),
        ("paperlog", "fetch"),
        # resolution, then (deviation 3) the position read of the ticker
        ("broker", "contract_details"),
        ("broker", "qualify"),
        ("broker", "positions"),
        ("check", "quantity"),
        ("check", "size"),
        ("check", "session"),
        ("check", "kill"),
        ("broker", "placeOrder(whatIf)"),
        # deviation 2: the switch check right before the intent, after the whatIf
        ("ledger", "switch_check"),
        ("ledger", "intent"),
        ("disk", "intent"),
        ("broker", "placeOrder"),
        ("ledger", "placed"),
        ("ledger", "filled"),
        ("ledger", "run_end"),
    ]
    assert _is_subsequence(expected, stream), "|".join(map(str, stream))
    # deviation 1
    assert _index(stream, ("ledger", "run_start")) < _index(stream, ("broker", "open_orders"))
    # deviation 2
    whatif = _index(stream, ("broker", "placeOrder(whatIf)"))
    assert whatif < _index(stream, ("ledger", "switch_check"), whatif)
    assert _index(stream, ("ledger", "switch_check"), whatif) < _index(stream, ("ledger", "intent"))
    # deviation 3
    resolved = max(
        _index(stream, ("broker", "contract_details")), _index(stream, ("broker", "qualify"))
    )
    assert resolved < _index(stream, ("broker", "positions"))
    # the intent was on disk when the real order reached the broker
    assert _index(stream, ("disk", "intent")) < _index(stream, ("broker", "placeOrder"))
    assert fake.calls.count("placeOrder") == 1


def test_live_call_order_pins_quantity_size_session_kill_before_whatif(tmp_path, loop, monkeypatch):
    _fake, stream, code, _records = _ordered_run(tmp_path, loop, monkeypatch)
    assert code == executor.EXIT_OK
    for item in (
        ("check", "quantity"),
        ("check", "size"),
        ("check", "session"),
        ("check", "kill"),
        ("broker", "placeOrder(whatIf)"),
        ("ledger", "intent"),
        ("broker", "placeOrder"),
    ):
        assert item in stream, item
    quantity = _index(stream, ("check", "quantity"))
    size = _index(stream, ("check", "size"))
    session = _index(stream, ("check", "session"))
    kill = _index(stream, ("check", "kill"), session)
    whatif = _index(stream, ("broker", "placeOrder(whatIf)"))
    intent = _index(stream, ("ledger", "intent"))
    place = _index(stream, ("broker", "placeOrder"))
    assert quantity < size < session < kill < whatif < intent < place


def test_live_call_order_key_check_after_freshness(tmp_path, loop, monkeypatch):
    """Deviation 4: a spent key AND a stale decision ends as stale-decision (freshness first)."""
    _prepare_live_ledger(STALE_KEY, "AAPL", "2026-10-01")
    fake = _fake_for(
        executions=[ibkr_fakes.fill(CON_IDS["AAPL"], STALE_KEY, 2)],
    )
    _observe(monkeypatch, fake)
    paper = _paper(
        tmp_path,
        [("2026-10-01", "AAPL", "Buy")],
        {"2026-10-01": _summary("2026-10-01", ("AAPL", "ok", "Buy"))},
    )
    code, records = _live_run(tmp_path, loop, fake, paper=paper)
    assert code == executor.EXIT_PRECONDITION
    skipped = [r for r in records if r["event"] == "skipped"]
    assert [r["state"] for r in skipped] == ["stale-decision"]
    assert "placeOrder" not in fake.calls


# --- negative controls in the live path ------------------------------------------------------


def _no_intent_no_order(records, fake):
    assert [r for r in records if r["event"] == "intent"] == []
    assert "placeOrder" not in fake.calls


def test_live_whatif_reject_blocks_the_order(tmp_path, loop):
    # D-12: SC7 is proven with a fixture and a stub broker; a real IBKR reject is not provoked
    # because MAX_QTY_PER_ORDER = 2 stops before the whatIf. The reject reason comes from the
    # request error texts; OrderState has no rejectReason in the pinned client version
    # (RESEARCH Pitfall 6).
    text = "Order rejected - reason: insufficient permissions"
    fake = _fake_for(whatif=[], emit_during={"whatif": [(17, 201, text, None)]})
    code, records = _live_run(tmp_path, loop, fake)
    assert code == executor.EXIT_REJECTED
    (rejected,) = [r for r in records if r["event"] == "rejected"]
    assert rejected["state"] == "preview-rejected"
    assert "placeOrder(whatIf)" in fake.calls
    _no_intent_no_order(records, fake)


def test_live_read_only_ends_at_the_preview(tmp_path, loop):
    # D-15: with the gateway's Read-Only switch on, the whatIf is blocked (321); the run never
    # reaches the order. This is the state measured on the day of the first order (06-09).
    fake = _fake_for(whatif="hang", emit_during={"whatif": [(17, 321, "API is read-only", None)]})
    code, records = _live_run(tmp_path, loop, fake)
    assert code == executor.EXIT_REJECTED
    (rejected,) = [r for r in records if r["event"] == "rejected"]
    assert rejected["state"] == "preview-read-only"
    _no_intent_no_order(records, fake)


def test_live_size_cap_sends_no_preview(tmp_path, loop, monkeypatch):
    monkeypatch.setattr(
        decision,
        "plan_order",
        lambda rating, **kwargs: decision.Plan(decision.INTENT, "BUY", 3, 3, 0.0, "BUY 3"),
    )
    fake = _fake_for()
    code, records = _live_run(tmp_path, loop, fake)
    assert code == executor.EXIT_REJECTED
    (skipped,) = [r for r in records if r["event"] == "skipped"]
    assert skipped["state"] == "size-cap"
    assert "placeOrder(whatIf)" not in fake.calls
    _no_intent_no_order(records, fake)


def test_live_outside_session_sends_no_preview(tmp_path, loop):
    fake = _fake_for(liquid_hours="20261012:0930-20261012:1000")
    code, records = _live_run(tmp_path, loop, fake)
    assert code == executor.EXIT_PRECONDITION
    (skipped,) = [r for r in records if r["event"] == "skipped"]
    assert skipped["state"] == "outside-session"
    assert "placeOrder(whatIf)" not in fake.calls
    _no_intent_no_order(records, fake)


def test_live_kill_between_two_tickers_sends_no_second_order(tmp_path, loop):
    fake = _fake_for(
        ("AAPL", "MSFT"),
        place_executions=[_own_fill()],
        place_completed=_own_completed(),
    )
    real = fake.placeOrder

    def hook(contract, order):
        trade = real(contract, order)
        if not getattr(order, "whatIf", False):
            executor.default_kill_file().write_text("stop", encoding="utf-8")
        return trade

    fake.placeOrder = hook
    code, records = _live_run(
        tmp_path, loop, fake, tickers=("AAPL", "MSFT"), paper=_two_buys(tmp_path)
    )
    assert code == executor.EXIT_KILL_SWITCH
    assert fake.calls.count("placeOrder") == 1
    assert [r["ticker"] for r in records if r["event"] == "intent"] == ["AAPL"]
    (skipped,) = [r for r in records if r["event"] == "skipped"]
    assert skipped["ticker"] == "MSFT"
    assert skipped["state"] == "kill-active"
