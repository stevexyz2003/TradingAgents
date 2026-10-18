"""Pattern signals: look-ahead freedom, warm-up and known values."""

import numpy as np
import pandas as pd

from tradingagents.patterns.signals import PATTERNS, compute_patterns

FAR = "2035-01-01"


def _frame(closes, start="2024-01-01"):
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Date": dates, "Close": np.asarray(closes, dtype=float)})


def _wave(n, seed=1):
    rng = np.random.default_rng(seed)
    return 100 + np.cumsum(rng.normal(0, 1, n))


def test_no_lookahead_future_prices_do_not_change_result():
    base = _frame(_wave(300))
    as_of = str(base["Date"].iloc[249].date())
    expected = compute_patterns(base, as_of)

    tampered = base.copy()
    tampered.loc[tampered["Date"] > pd.Timestamp(as_of), "Close"] *= 10
    extra = _frame([5000.0] * 10, start="2030-01-01")
    tampered = pd.concat([tampered, extra], ignore_index=True)

    assert compute_patterns(tampered, as_of) == expected
    assert set(expected) == set(PATTERNS)


def test_warmup_gives_none_not_zero():
    short = compute_patterns(_frame(_wave(150)), FAR)
    assert short["trend_sma200"] is None
    assert short["sma50_200"] is None
    assert short["rsi_extreme"] is not None
    full = compute_patterns(_frame(_wave(250)), FAR)
    assert full["trend_sma200"] in (1, -1)
    assert full["sma50_200"] in (1, -1)


def test_rsi_monotonic_series_is_overbought_or_oversold():
    up = compute_patterns(_frame(np.arange(1, 60, dtype=float)), FAR)
    assert up["rsi_extreme"] == -1  # RSI 100, contrarian
    down = compute_patterns(_frame(np.arange(60, 1, -1, dtype=float)), FAR)
    assert down["rsi_extreme"] == 1


def test_breakout_excludes_current_bar():
    flat = [100.0 + (i % 3) for i in range(40)]
    assert compute_patterns(_frame([*flat, 110.0]), FAR)["breakout_20"] == 1
    assert compute_patterns(_frame([*flat, 90.0]), FAR)["breakout_20"] == -1
    assert compute_patterns(_frame([*flat, 101.0]), FAR)["breakout_20"] == 0


def _macd_states(closes):
    return [
        compute_patterns(_frame(closes[:k]), FAR)["macd_cross"] for k in range(40, len(closes) + 1)
    ]


def test_macd_cross_up_and_down():
    down_then_up = list(np.linspace(150, 100, 60)) + list(np.linspace(100, 110, 8))
    assert 1 in _macd_states(down_then_up)
    up_then_down = list(np.linspace(100, 150, 60)) + list(np.linspace(150, 140, 8))
    assert -1 in _macd_states(up_then_down)
    assert compute_patterns(_frame(np.linspace(100, 150, 80)), FAR)["macd_cross"] == 0


def test_as_of_on_non_trading_day_uses_last_bar_before():
    frame = _frame(_wave(100))
    friday = frame.loc[frame["Date"].dt.dayofweek == 4, "Date"].iloc[5]
    saturday = str((friday + pd.Timedelta(days=1)).date())
    assert compute_patterns(frame, saturday) == compute_patterns(frame, str(friday.date()))


def test_bollinger_contrarian_and_unsorted_input():
    assert compute_patterns(_frame([100.0] * 30 + [130.0]), FAR)["bollinger_out"] == -1
    frame = _frame([100.0] * 30 + [70.0]).sample(frac=1, random_state=3)
    assert compute_patterns(frame, FAR)["bollinger_out"] == 1
