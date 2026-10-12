"""The IBKR contract core: table, allow-list, tradability, identity, session parser.

Pure functions only. The clock is always an injected, aware datetime; nothing here
touches the gateway or the local clock.
"""

import dataclasses
import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace

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
    assert c.ALLOWED_SEC_TYPES == frozenset({"STK"})


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
    base = {"con_id": 265598, "primary_exchange": "NASDAQ", "currency": "USD", "local_symbol": "AAPL"}
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
