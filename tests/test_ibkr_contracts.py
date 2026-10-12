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
