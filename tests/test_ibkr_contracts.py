"""The IBKR contract core: table, allow-list, tradability, identity, session parser.

Pure functions only. The clock is always an injected, aware datetime; nothing here
touches the gateway or the local clock.
"""

import dataclasses
import importlib.util
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_CONTRACTS = ROOT / "scripts" / "ibkr_contracts.py"


def _load_contracts():
    """The module, loaded once under one name so every consumer sees the same classes."""
    if "ibkr_contracts" in sys.modules:
        return sys.modules["ibkr_contracts"]
    spec = importlib.util.spec_from_file_location("ibkr_contracts", _CONTRACTS)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ibkr_contracts"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("ibkr_contracts", None)
        raise
    return module


c = _load_contracts()


# --- table (D-01, D-02, D-04, D-06, D-07) -----------------------------------------------


def test_table_has_exactly_the_decided_keys():
    assert set(c.CONTRACT_TABLE) == {"AAPL", "MSFT", "NVDA", "^GSPC", "XAUUSD+"}


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA"])
def test_table_stock_entries(ticker):
    assert c.CONTRACT_TABLE[ticker] == c.ContractSpec(ticker, "STK", "SMART", "USD", "NASDAQ")


def test_table_non_stock_entries_carry_their_real_sec_type():
    assert c.CONTRACT_TABLE["^GSPC"] == c.ContractSpec("SPX", "IND", "CBOE", "USD", "")
    assert c.CONTRACT_TABLE["XAUUSD+"] == c.ContractSpec("XAUUSD", "CMDTY", "SMART", "USD", "")


def test_table_required_fields_and_no_duplicates():
    specs = list(c.CONTRACT_TABLE.values())
    for spec in specs:
        assert spec.symbol and spec.sec_type and spec.exchange and spec.currency
        if spec.sec_type == "STK":
            assert spec.primary_exchange
        if spec.sec_type in c.ALLOWED_SEC_TYPES:
            assert spec.sec_type == "STK"
    assert len(set(specs)) == len(specs)


def test_table_is_read_only():
    with pytest.raises(TypeError):
        c.CONTRACT_TABLE["TSLA"] = c.CONTRACT_TABLE["AAPL"]  # type: ignore[index]


def test_table_has_no_con_id_or_local_symbol_field():
    names = {f.name for f in dataclasses.fields(c.ContractSpec)}
    assert "con_id" not in names and "local_symbol" not in names
    assert names == {"symbol", "sec_type", "exchange", "currency", "primary_exchange"}


def test_table_covers_the_paper_run_ticker_default():
    text = (ROOT / ".github" / "workflows" / "daily-paper-run.yml").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "TICKERS:" in ln and "||" in ln)
    match = re.search(r"\|\|\s*'([A-Z,]+)'", line)
    assert match, line
    tickers = match.group(1).split(",")
    assert tickers
    missing = [t for t in tickers if t not in c.CONTRACT_TABLE]
    assert missing == []


def test_symbols_resolver_and_vendor_normalizer_are_separate_paths():
    from tradingagents.dataflows.symbols import normalize_symbol

    spec = c.classify("XAUUSD+").spec
    assert (spec.symbol, spec.sec_type) == ("XAUUSD", "CMDTY")
    assert normalize_symbol("XAUUSD+") == "GC=F"
    for entry in c.CONTRACT_TABLE.values():
        assert entry.symbol != "GC" and entry.sec_type != "FUT"


# --- classify (D-03, D-04, D-05) ---------------------------------------------------------


def test_classify_known_stock_is_ok():
    verdict = c.classify("AAPL")
    assert verdict.state == c.OK
    assert verdict.spec == c.CONTRACT_TABLE["AAPL"]


@pytest.mark.parametrize("raw", ["aapl", " AAPL", "AAPL ", "XYZQ", "GOLD", "XAU", ""])
def test_classify_unmapped_is_exact_and_case_sensitive(raw):
    verdict = c.classify(raw)
    assert verdict.state == c.NOT_MAPPED
    assert verdict.spec is None
    assert "no entry in the contract table" in verdict.detail
    assert repr(raw) in verdict.detail


def test_classify_unmapped_detail_neutralises_log_injection():
    verdict = c.classify("A\nB")
    assert "\n" not in verdict.detail


@pytest.mark.parametrize(("raw", "sec_type"), [("^GSPC", "IND"), ("XAUUSD+", "CMDTY")])
def test_classify_non_stock_is_not_allowed(raw, sec_type):
    verdict = c.classify(raw)
    assert verdict.state == c.NOT_ALLOWED
    assert verdict.spec.sec_type == sec_type
    assert "allow-list" in verdict.detail and "STK" in verdict.detail


def test_allow_list_is_stock_only():
    assert frozenset({"STK"}) == c.ALLOWED_SEC_TYPES


# --- tradability (D-19) ------------------------------------------------------------------


def test_check_tradable_accepts_a_normal_stock():
    assert c.check_tradable("SMART,NASDAQ,ARCA", "ACTIVETIM,LMT,MKT,STP") is None


@pytest.mark.parametrize(
    ("exchanges", "order_types", "needle"),
    [
        ("VALUE", "LMT,MKT", "VALUE"),
        ("NASDAQ,ARCA", "LMT,MKT", "SMART"),
        ("SMART", "LMT", "MKT"),
        ("SMART", "MKT", "LMT"),
        ("", "LMT,MKT", ""),
        ("SMART", "", ""),
        (" , ", "LMT,MKT", ""),
    ],
)
def test_check_tradable_rejects_fail_closed(exchanges, order_types, needle):
    reason = c.check_tradable(exchanges, order_types)
    assert reason is not None
    assert needle in reason


def test_check_tradable_tolerates_whitespace_around_elements():
    assert c.check_tradable(" SMART , NASDAQ", " LMT , MKT ") is None


# --- identity (D-09) ---------------------------------------------------------------------


def _ident(**kw):
    base = {
        "con_id": 265598,
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "local_symbol": "AAPL",
    }
    base.update(kw)
    return c.Identity(**base)


def test_identity_diff_equal_is_empty():
    assert c.identity_diff(_ident(), _ident()) == ()


def test_identity_diff_names_each_changed_field_in_fixed_order():
    assert c.identity_diff(_ident(), _ident(con_id=1)) == ("conId",)
    assert c.identity_diff(_ident(), _ident(local_symbol="X", currency="EUR")) == (
        "currency",
        "localSymbol",
    )
    assert c.identity_diff(_ident(), _ident(primary_exchange="NYSE")) == ("primaryExchange",)
    assert set(c.IDENTITY_FIELDS) == {"conId", "primaryExchange", "currency", "localSymbol"}


def test_identity_of_ignores_trading_class_and_long_name():
    info = SimpleNamespace(
        con_id=265598,
        primary_exchange="NASDAQ",
        currency="USD",
        local_symbol="AAPL",
        trading_class="NMS",
        long_name="APPLE INC",
    )
    assert c.identity_of(info) == _ident()
    other = SimpleNamespace(**{**vars(info), "trading_class": "ZZZ", "long_name": "OTHER"})
    assert c.identity_diff(c.identity_of(info), c.identity_of(other)) == ()


def test_rejected_states_membership():
    assert c.HALTED in c.REJECTED_STATES
    assert c.CLOSED not in c.REJECTED_STATES
    assert c.OK not in c.REJECTED_STATES
    assert c.SESSION_UNKNOWN in c.REJECTED_STATES


# --- session parser (D-23) ---------------------------------------------------------------

NEW_FORMAT = "20261011:CLOSED;20261012:0930-20261012:1600;20261013:0930-20261013:1600"
OLD_FORMAT = "20090507:0700-1830"
# Invented fixture (assumption A4): a shortened day is just a shorter window.
HALF_DAY = "20261127:0930-20261127:1300"
LEADING_SEMICOLON = ";20261011:1800-20261012:1700;20261012:1800-20261013:1700"
ZONE = "US/Eastern"


@pytest.fixture(scope="module")
def ny():
    try:
        return ZoneInfo(ZONE)
    except ZoneInfoNotFoundError:
        pytest.skip("tz database has no US/Eastern")


def _utc(ny, *args):
    return datetime(*args, tzinfo=ny).astimezone(UTC)


def test_parse_new_format_with_closed_day(ny):
    lh = c.parse_liquid_hours("20261011:CLOSED;20261012:0930-20261012:1600", ZONE)
    assert len(lh.windows) == 1
    assert lh.closed_dates == frozenset({date(2026, 10, 11)})
    w = lh.windows[0]
    assert w.start == datetime(2026, 10, 12, 9, 30, tzinfo=ny)
    assert w.end == datetime(2026, 10, 12, 16, 0, tzinfo=ny)
    assert lh.time_zone_id == ZONE


def test_parse_leading_semicolon_and_overnight_windows(ny):
    lh = c.parse_liquid_hours(LEADING_SEMICOLON, ZONE)
    assert len(lh.windows) == 2
    assert lh.windows[0].start == datetime(2026, 10, 11, 18, 0, tzinfo=ny)
    assert lh.windows[0].end == datetime(2026, 10, 12, 17, 0, tzinfo=ny)
    assert lh.windows[1].end == datetime(2026, 10, 13, 17, 0, tzinfo=ny)


def test_parse_old_format_end_takes_the_start_date(ny):
    lh = c.parse_liquid_hours(OLD_FORMAT, ZONE)
    assert len(lh.windows) == 1
    assert lh.windows[0].start == datetime(2009, 5, 7, 7, 0, tzinfo=ny)
    assert lh.windows[0].end == datetime(2009, 5, 7, 18, 30, tzinfo=ny)


def test_parse_empty_string_gives_no_windows():
    lh = c.parse_liquid_hours("", ZONE)
    assert lh.windows == () and lh.closed_dates == frozenset()


@pytest.mark.parametrize(
    "raw",
    ["20261012:0930", "garbage", "20261012:1600-20261012:0930", "20261012:0930-1600-1700"],
)
def test_parse_rejects_malformed_strings(raw):
    with pytest.raises(c.SessionParseError):
        c.parse_liquid_hours(raw, ZONE)


@pytest.mark.parametrize("zone", ["", "Bad/Zone"])
def test_parse_rejects_bad_zone(zone):
    with pytest.raises(c.SessionParseError):
        c.parse_liquid_hours(NEW_FORMAT, zone)


# --- evaluate_session (D-21, D-24) -------------------------------------------------------


def test_buffer_constant():
    assert c.SESSION_BUFFER_MINUTES == 15


def test_buffer_boundaries_are_exact(ny):
    window = c.parse_liquid_hours(NEW_FORMAT, ZONE).windows[0]
    buf = timedelta(minutes=15)

    def at(moment):
        return c.evaluate_session(NEW_FORMAT, ZONE, moment.astimezone(UTC))

    assert at(window.start + buf).state == c.OK  # start + 15min
    early = at(window.start + buf - timedelta(seconds=1))  # start + 15min - 1s
    assert early.state == c.CLOSED
    assert early.next_open == window.start + buf
    assert at(window.end - buf).state == c.OK  # end - 15min
    assert at(window.end - buf + timedelta(seconds=1)).state == c.CLOSED  # end - 15min + 1s


def test_ok_verdict_carries_the_window(ny):
    verdict = c.evaluate_session(NEW_FORMAT, ZONE, _utc(ny, 2026, 10, 12, 12, 0))
    assert verdict.state == c.OK
    assert verdict.window is not None


def test_closed_day_is_closed_not_session_unknown(ny):
    verdict = c.evaluate_session(NEW_FORMAT, ZONE, _utc(ny, 2026, 10, 11, 12, 0))
    assert verdict.state == c.CLOSED
    assert verdict.state not in c.REJECTED_STATES
    monday = c.parse_liquid_hours(NEW_FORMAT, ZONE).windows[0]
    assert verdict.next_open == monday.start + timedelta(minutes=15)


def test_missing_day_entry_is_session_unknown(ny):
    raw = "20261013:0930-20261013:1600"
    verdict = c.evaluate_session(raw, ZONE, _utc(ny, 2026, 10, 12, 12, 0))
    assert verdict.state == c.SESSION_UNKNOWN
    assert verdict.state in c.REJECTED_STATES
    assert "2026-10-12" in verdict.detail


@pytest.mark.parametrize(("raw", "zone"), [("garbage", ZONE), (NEW_FORMAT, "Bad/Zone")])
def test_parse_failure_becomes_session_unknown_without_raising(ny, raw, zone):
    verdict = c.evaluate_session(raw, zone, _utc(ny, 2026, 10, 12, 12, 0))
    assert verdict.state == c.SESSION_UNKNOWN
    assert verdict.detail


def test_after_midnight_inside_a_window_that_began_yesterday(ny):
    verdict = c.evaluate_session(LEADING_SEMICOLON, ZONE, _utc(ny, 2026, 10, 12, 1, 0))
    assert verdict.state == c.OK


def test_half_day_is_a_shorter_window_without_special_case(ny):
    assert c.evaluate_session(HALF_DAY, ZONE, _utc(ny, 2026, 11, 27, 12, 40)).state == c.OK
    assert c.evaluate_session(HALF_DAY, ZONE, _utc(ny, 2026, 11, 27, 12, 50)).state == c.CLOSED


def test_no_later_window_means_no_next_open(ny):
    raw = "20261012:0930-20261012:1600"
    verdict = c.evaluate_session(raw, ZONE, _utc(ny, 2026, 10, 12, 17, 0))
    assert verdict.state == c.CLOSED
    assert verdict.next_open is None


def test_naive_now_is_refused():
    with pytest.raises(ValueError, match="time zone"):
        c.evaluate_session(NEW_FORMAT, ZONE, datetime(2026, 10, 12, 12, 0))


# --- counter-test against the client library's own parser (SC6) --------------------------


@pytest.mark.parametrize(
    "raw",
    [
        NEW_FORMAT,
        "20261011:CLOSED;20261012:0930-20261012:1600",
        HALF_DAY,
        LEADING_SEMICOLON,
        "20261012:0400-20261012:0930;20261012:0930-20261012:1600;20261013:0400-20261013:0930",
    ],
)
def test_parser_agrees_with_ib_async_on_new_format(raw):
    ib_async = pytest.importorskip("ib_async")
    details = ib_async.ContractDetails(liquidHours=raw, timeZoneId=ZONE)
    theirs = [(s.start, s.end) for s in details.liquidSessions()]
    ours = [(w.start, w.end) for w in c.parse_liquid_hours(raw, ZONE).windows]
    assert ours == theirs


def test_old_format_is_rejected_by_ib_async_but_parsed_here(ny):
    ib_async = pytest.importorskip("ib_async")
    details = ib_async.ContractDetails(liquidHours=OLD_FORMAT, timeZoneId=ZONE)
    with pytest.raises(ValueError):
        details.liquidSessions()
    window = c.parse_liquid_hours(OLD_FORMAT, ZONE).windows[0]
    assert (window.start.hour, window.start.minute) == (7, 0)
    assert (window.end.hour, window.end.minute) == (18, 30)


# --- persistence (D-11, D-12, D-14, D-18, D-22) ------------------------------------------

import json  # noqa: E402
import os  # noqa: E402

_AT = "2026-10-12T17:00:00+00:00"


def _stored(con_id=265598, symbol="AAPL"):
    return c.StoredContract(c.Identity(con_id, "NASDAQ", "USD", symbol), _AT)


def _event(event="init", ticker="AAPL", old=None, con_id=265598):
    return c.HistoryEvent(
        event, ticker, old, c.Identity(con_id, "NASDAQ", "USD", ticker), "test reason", _AT
    )


def _write_raw(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _good_entry():
    return {
        "conId": 265598,
        "primaryExchange": "NASDAQ",
        "currency": "USD",
        "localSymbol": "AAPL",
        "learned_at": _AT,
    }


def test_persist_roundtrip_and_exact_schema(tmp_path):
    p = tmp_path / "contracts.json"
    c.commit_contracts(p, {"AAPL": _stored()}, [_event()])
    assert c.load_contracts_file(p) == {"AAPL": _stored()}
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data) == {"schema_version", "contracts"}
    assert data["schema_version"] == 1
    assert set(data["contracts"]["AAPL"]) == {
        "conId",
        "primaryExchange",
        "currency",
        "localSymbol",
        "learned_at",
    }


def test_contracts_file_missing_has_path(tmp_path):
    p = tmp_path / "nope.json"
    with pytest.raises(c.ContractsFileMissing) as ei:
        c.load_contracts_file(p)
    assert ei.value.path == p
    assert "resolve --init" in str(ei.value)


def test_contracts_file_not_utf8(tmp_path):
    p = tmp_path / "contracts.json"
    p.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(c.ContractsFileError) as ei:
        c.load_contracts_file(p)
    assert str(p) in str(ei.value)


def test_contracts_file_not_json(tmp_path):
    p = tmp_path / "contracts.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(c.ContractsFileError):
        c.load_contracts_file(p)


def _bad_payloads():
    good = _good_entry()
    yield "toplevel-list", []
    yield "no-version", {"contracts": {}}
    yield "version-2", {"schema_version": 2, "contracts": {}}
    yield "version-bool", {"schema_version": True, "contracts": {}}
    yield "contracts-list", {"schema_version": 1, "contracts": []}
    yield "extra-toplevel", {"schema_version": 1, "contracts": {}, "x": 1}
    yield "conid-str", {"schema_version": 1, "contracts": {"AAPL": {**good, "conId": "1"}}}
    yield "conid-zero", {"schema_version": 1, "contracts": {"AAPL": {**good, "conId": 0}}}
    yield "conid-neg", {"schema_version": 1, "contracts": {"AAPL": {**good, "conId": -1}}}
    yield "conid-bool", {"schema_version": 1, "contracts": {"AAPL": {**good, "conId": True}}}
    yield (
        "empty-primary",
        {"schema_version": 1, "contracts": {"AAPL": {**good, "primaryExchange": ""}}},
    )
    missing = dict(good)
    del missing["currency"]
    yield "missing-field", {"schema_version": 1, "contracts": {"AAPL": missing}}
    yield (
        "extra-field",
        {"schema_version": 1, "contracts": {"AAPL": {**good, "liquidHours": "x"}}},
    )
    yield "entry-not-object", {"schema_version": 1, "contracts": {"AAPL": 5}}


@pytest.mark.parametrize("name,payload", list(_bad_payloads()))
def test_contracts_file_schema_violations(tmp_path, name, payload):
    p = tmp_path / "contracts.json"
    _write_raw(p, payload)
    with pytest.raises(c.ContractsFileError) as ei:
        c.load_contracts_file(p)
    assert str(p) in str(ei.value)


def test_history_lines_after_two_commits(tmp_path):
    p = tmp_path / "contracts.json"
    c.commit_contracts(p, {"AAPL": _stored()}, [_event()])
    old = c.Identity(265598, "NASDAQ", "USD", "AAPL")
    c.commit_contracts(p, {"AAPL": _stored(1)}, [_event("rebaseline", old=old, con_id=1)])
    h = c.contracts_history_path(p)
    assert h == tmp_path / "contracts-history.jsonl"
    raw = h.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(x) for x in lines]
    for row in rows:
        assert {"at", "event", "ticker", "old", "new", "reason"} <= set(row)
    assert rows[0]["old"] is None
    assert set(rows[1]["old"]) == {"conId", "primaryExchange", "currency", "localSymbol"}
    assert rows[1]["event"] == "rebaseline"


def test_history_row_written_before_replace(tmp_path, monkeypatch):
    p = tmp_path / "contracts.json"
    seen = {}
    real = os.replace

    def spy(src, dst):
        seen["history"] = c.contracts_history_path(p).read_text(encoding="utf-8")
        return real(src, dst)

    monkeypatch.setattr(c.os, "replace", spy)
    c.commit_contracts(p, {"AAPL": _stored()}, [_event()])
    assert '"event": "init"' in seen["history"]


def test_atomic_replace_failure_keeps_old_file_and_logs_aborted(tmp_path, monkeypatch):
    p = tmp_path / "contracts.json"
    c.commit_contracts(p, {"AAPL": _stored()}, [_event()])
    before = p.read_bytes()

    def boom(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(c.os, "replace", boom)
    with pytest.raises(PermissionError):
        c.commit_contracts(p, {"AAPL": _stored(2)}, [_event("learn", con_id=2)])
    assert p.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    text = c.contracts_history_path(p).read_text(encoding="utf-8")
    rows = [json.loads(x) for x in text.splitlines()]
    assert [r["event"] for r in rows] == ["init", "learn", "learn-aborted"]
    assert "PermissionError" in rows[-1]["reason"]


def test_write_json_atomic_check_failure_leaves_target(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("old", encoding="utf-8")

    def bad(temp):
        raise ValueError("no")

    with pytest.raises(ValueError):
        c.write_json_atomic(p, {"a": 1}, check=bad)
    assert p.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))


def test_commit_without_events_writes_no_history_and_makes_dir(tmp_path):
    p = tmp_path / "sub" / "contracts.json"
    c.commit_contracts(p, {}, [])
    assert p.exists()
    assert not c.contracts_history_path(p).exists()


def test_persisted_files_carry_no_session_values(tmp_path):
    p = tmp_path / "contracts.json"
    c.commit_contracts(p, {"AAPL": _stored()}, [_event()])
    text = p.read_text(encoding="utf-8") + c.contracts_history_path(p).read_text(encoding="utf-8")
    assert "liquid" not in text.lower()
    assert "tradinghours" not in text.lower()


# --- resolver (D-10, D-13, D-15..D-17, D-19, D-21, D-24, D-29, D-31) ---------------------

import logging  # noqa: E402

from tests import ibkr_fakes  # noqa: E402

_ContractInfo = ibkr_fakes.load_broker().ContractInfo
_NY = ZoneInfo("America/New_York")
_OPEN_NOW = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)  # 11:00 in New York
_CLOSED_NOW = datetime(2026, 10, 14, 23, 0, tzinfo=UTC)  # 19:00 in New York


def _hours_for(now_utc):
    """A liquid-hours text for the New York day of ``now_utc`` (built from the injected now)."""
    day = now_utc.astimezone(_NY).date()
    nxt = day + timedelta(days=1)
    return f"{day:%Y%m%d}:0930-{day:%Y%m%d}:1600;{nxt:%Y%m%d}:0930-{nxt:%Y%m%d}:1600"


def _info(symbol="AAPL", con_id=265598, *, details=False, now=_OPEN_NOW, **over):
    base = {
        "con_id": con_id,
        "symbol": symbol,
        "sec_type": "STK",
        "exchange": "SMART",
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "local_symbol": symbol,
        "trading_class": "NMS",
    }
    if details:
        base.update(
            long_name=f"{symbol} Inc",
            valid_exchanges="SMART,NASDAQ",
            order_types="LMT,MKT",
            time_zone_id="America/New_York",
            liquid_hours=_hours_for(now),
            trading_hours=_hours_for(now),
        )
    base.update(over)
    return _ContractInfo(**base)


class StubBroker:
    def __init__(self, search=None, details=None):
        self.search = search or {}
        self.details = details or {}
        self.calls = []

    def search_contract(self, spec):
        self.calls.append(("search", spec.symbol))
        return tuple(self.search.get(spec.symbol, ()))

    def contract_details(self, con_id, exchange):
        self.calls.append(("details", con_id, exchange))
        return tuple(self.details.get(con_id, ()))


def _good_broker(symbols=("AAPL", "MSFT"), now=_OPEN_NOW):
    ids = {"AAPL": 265598, "MSFT": 272093, "NVDA": 4815747}
    return StubBroker(
        {s: (_info(s, ids[s]),) for s in symbols},
        {ids[s]: (_info(s, ids[s], details=True, now=now),) for s in symbols},
    )


_LOG = logging.getLogger("test.resolve")


def _resolve(tickers, **kw):
    kw.setdefault("contracts", {})
    kw.setdefault("broker", _good_broker())
    kw.setdefault("now_utc", _OPEN_NOW)
    kw.setdefault("logger", _LOG)
    return c.resolve_all(tickers, **kw)


def _by(outcome):
    return {r.ticker: r for r in outcome.results}


def test_needs_broker_false_when_all_rejected_locally():
    assert c.needs_broker(["XYZQ", "^GSPC", "XAUUSD+"]) is False
    assert c.needs_broker(["XYZQ", "AAPL"]) is True


def test_resolve_all_local_rejections_need_no_broker():
    out = _resolve(["XYZQ", "^GSPC", "XAUUSD+"], broker=None)
    states = [r.state for r in out.results]
    assert states == ["not-mapped", "not-allowed", "not-allowed"]
    assert out.rejected


def test_resolve_learns_single_match(caplog):
    broker = _good_broker()
    with caplog.at_level(logging.INFO, logger="test.resolve"):
        out = _resolve(["AAPL"], broker=broker)
    r = _by(out)["AAPL"]
    assert r.state == "ok" and not r.rejected
    assert r.identity.con_id == 265598
    assert r.window is not None
    assert out.contracts["AAPL"].identity.con_id == 265598
    assert len(out.events) == 1
    assert out.events[0].event == "learn" and out.events[0].old is None
    assert "learned conId=265598" in caplog.text
    assert broker.calls[0][0] == "search"
    assert broker.calls[1] == ("details", 265598, "SMART")


def test_resolve_learn_with_mismatching_search_key_is_drift():
    broker = StubBroker({"AAPL": (_info("AAPL", primary_exchange="NYSE"),)})
    out = _resolve(["AAPL"], broker=broker)
    assert _by(out)["AAPL"].state == "drift"
    assert "AAPL" not in out.contracts
    assert out.events == ()


def test_resolve_not_found_on_zero_matches():
    out = _resolve(["AAPL"], broker=StubBroker())
    assert _by(out)["AAPL"].state == "not-found"


def test_resolve_ambiguous_logs_all_candidates_in_one_record(caplog):
    cands = tuple(_info("AAPL", 1000 + i, local_symbol=f"AAPL{i}") for i in range(3))
    with caplog.at_level(logging.INFO, logger="test.resolve"):
        out = _resolve(["AAPL"], broker=StubBroker({"AAPL": cands}))
    assert _by(out)["AAPL"].state == "ambiguous"
    recs = [r for r in caplog.records if "ibkr-state=AMBIGUOUS_CONTRACT" in r.getMessage()]
    assert len(recs) == 1
    msg = recs[0].getMessage()
    for i in range(3):
        assert f"conId={1000 + i}" in msg
        assert f"localSymbol=AAPL{i}" in msg
    assert "primaryExchange=NASDAQ" in msg


def test_resolve_ambiguous_with_21_candidates_is_not_truncated(caplog):
    cands = tuple(_info("AAPL", 2000 + i) for i in range(21))
    with caplog.at_level(logging.INFO, logger="test.resolve"):
        _resolve(["AAPL"], broker=StubBroker({"AAPL": cands}))
    recs = [r for r in caplog.records if "ibkr-state=AMBIGUOUS_CONTRACT" in r.getMessage()]
    assert len(recs) == 1
    assert recs[0].getMessage().count("conId=") == 21


def test_resolve_second_run_checks_by_conid_and_cross_checks_by_search():
    broker = _good_broker()
    out = _resolve(["AAPL"], broker=broker, contracts={"AAPL": _stored()})
    assert _by(out)["AAPL"].state == "ok"
    assert out.events == ()
    assert ("details", 265598, "SMART") in broker.calls
    assert ("search", "AAPL") in broker.calls


def test_resolve_manipulated_conid_is_drift_and_others_continue(caplog):
    broker = _good_broker()
    broker.details[999999] = (_info("AAPL", 999999, details=True),)
    stored = {"AAPL": _stored(999999), "MSFT": _stored(272093, "MSFT")}
    with caplog.at_level(logging.INFO, logger="test.resolve"):
        out = _resolve(["AAPL", "MSFT"], broker=broker, contracts=stored)
    by = _by(out)
    assert by["AAPL"].state == "drift"
    assert by["MSFT"].state == "ok"
    assert out.contracts["AAPL"].identity.con_id == 999999
    assert out.events == ()
    recs = [r for r in caplog.records if "ibkr-state=CONTRACT_DRIFT" in r.getMessage()]
    assert len(recs) == 1 and recs[0].levelno == logging.ERROR
    assert "999999" in recs[0].getMessage() and "265598" in recs[0].getMessage()


def test_resolve_same_conid_other_local_symbol_is_drift():
    broker = _good_broker()
    broker.details[265598] = (_info("AAPL", details=True, local_symbol="AAPL.X"),)
    out = _resolve(["AAPL"], broker=broker, contracts={"AAPL": _stored()})
    r = _by(out)["AAPL"]
    assert r.state == "drift" and "localSymbol" in r.detail


def test_resolve_trading_class_and_long_name_change_is_not_drift():
    broker = _good_broker()
    broker.details[265598] = (
        _info("AAPL", details=True, trading_class="XYZ", long_name="Renamed Corp"),
    )
    out = _resolve(["AAPL"], broker=broker, contracts={"AAPL": _stored()})
    assert _by(out)["AAPL"].state == "ok"


def test_resolve_details_without_match_is_drift():
    broker = StubBroker({"AAPL": (_info("AAPL"),)}, {})
    out = _resolve(["AAPL"], broker=broker, contracts={"AAPL": _stored()})
    assert _by(out)["AAPL"].state == "drift"


def test_resolve_rebaseline_replaces_identity_with_history(caplog):
    broker = _good_broker()
    broker.details[999999] = (_info("AAPL", 999999, details=True),)
    with caplog.at_level(logging.INFO, logger="test.resolve"):
        out = _resolve(
            ["AAPL"],
            broker=broker,
            contracts={"AAPL": _stored(999999)},
            mode="rebaseline",
            rebaseline="AAPL",
        )
    assert _by(out)["AAPL"].state != "drift"
    assert out.contracts["AAPL"].identity.con_id == 265598
    (event,) = out.events
    assert event.event == "rebaseline" and event.old.con_id == 999999
    recs = [r for r in caplog.records if "CONTRACT_REBASELINED" in r.getMessage()]
    assert len(recs) == 1 and recs[0].levelno == logging.WARNING
    assert "999999" in recs[0].getMessage() and "265598" in recs[0].getMessage()


def test_resolve_init_learns_and_checks_anchor():
    out = _resolve(["AAPL", "MSFT"], contracts=None, mode="init", anchor_con_id=265598)
    assert set(out.contracts) == {"AAPL", "MSFT"}
    assert [e.event for e in out.events] == ["init", "init"]


def test_resolve_init_anchor_mismatch():
    broker = StubBroker({"AAPL": (_info("AAPL", 111),)}, {111: (_info("AAPL", 111, details=True),)})
    with pytest.raises(c.AnchorMismatch) as ei:
        _resolve(["AAPL"], contracts=None, broker=broker, mode="init", anchor_con_id=265598)
    assert ei.value.expected == 265598 and ei.value.seen == 111


def test_resolve_init_anchor_not_found():
    with pytest.raises(c.AnchorMismatch) as ei:
        _resolve(["AAPL"], contracts=None, broker=StubBroker(), mode="init", anchor_con_id=265598)
    assert ei.value.seen is None


def test_resolve_not_tradable_value_only():
    broker = _good_broker()
    broker.details[265598] = (_info("AAPL", details=True, valid_exchanges="VALUE"),)
    out = _resolve(["AAPL"], broker=broker)
    assert _by(out)["AAPL"].state == "not-tradable"


def test_resolve_closed_outside_window_is_not_a_rejection():
    out = _resolve(["AAPL"], broker=_good_broker(now=_CLOSED_NOW), now_utc=_CLOSED_NOW)
    r = _by(out)["AAPL"]
    assert r.state == "closed" and not r.rejected
    assert r.next_open is not None


def test_resolve_session_unknown_without_hours_is_rejected():
    broker = _good_broker()
    broker.details[265598] = (_info("AAPL", details=True, liquid_hours=""),)
    out = _resolve(["AAPL"], broker=broker)
    r = _by(out)["AAPL"]
    assert r.state == "session-unknown" and r.rejected


def test_resolve_deduplicates_tickers_in_order():
    broker = _good_broker()
    out = _resolve(["MSFT", "AAPL", "MSFT"], broker=broker)
    assert [r.ticker for r in out.results] == ["MSFT", "AAPL"]
    assert sum(1 for call in broker.calls if call == ("search", "MSFT")) == 1


def test_resolve_learned_payload_has_no_session_values():
    out = _resolve(["AAPL"])
    text = json.dumps(c.contracts_payload(out.contracts)).lower()
    assert "liquid" not in text and "trading_hours" not in text and "tradinghours" not in text
