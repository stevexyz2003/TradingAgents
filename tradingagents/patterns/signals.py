"""Look-ahead-free price patterns computed from OHLCV closes (fork-only).

Every pattern is +1 (bullish), -1 (bearish), 0 (computable but inactive) or
``None`` (not enough bars). :func:`compute_patterns` truncates the frame to
``Date <= as_of`` itself, before any indicator is computed, so the result can
only depend on prices up to and including the decision date.

Directions are modelling choices. RSI and Bollinger are read *contrarian*
(oversold -> +1); the momentum reading would be the opposite sign.
"""

import pandas as pd

PATTERNS: tuple[str, ...] = (
    "rsi_extreme",
    "macd_cross",
    "breakout_20",
    "trend_sma200",
    "sma50_200",
    "bollinger_out",
)

# RSI: Wilder smoothing, standard 14 periods, 30/70 thresholds.
RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
RSI_MIN_BARS = RSI_PERIOD + 1  # one diff is lost

# MACD: standard 12/26/9; a cross within the last 3 sessions still counts, so a
# cross on the previous day is not lost.
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MACD_CROSS_LOOKBACK = 3
MACD_MIN_BARS = MACD_SLOW + MACD_SIGNAL

# Donchian channel: about one trading month; the current bar is excluded.
BREAKOUT_WINDOW = 20
BREAKOUT_MIN_BARS = BREAKOUT_WINDOW + 1

# Classic long-term trend filter and golden/death-cross regime.
SMA_SLOW = 200
SMA_FAST = 50

# Bollinger: 20 bars, 2 sigma (population std, the usual definition).
BB_WINDOW = 20
BB_SIGMA = 2.0


def _closes_up_to(ohlcv: pd.DataFrame, as_of: str) -> pd.Series:
    frame = ohlcv[["Date", "Close"]].copy()
    dates = pd.to_datetime(frame["Date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    frame["Date"] = dates.dt.normalize()
    frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date")
    frame = frame[frame["Date"] <= pd.Timestamp(as_of).normalize()]
    return frame["Close"].astype(float).reset_index(drop=True)


def _rsi(close: pd.Series) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    g, ls = float(gain.iloc[-1]), float(loss.iloc[-1])
    if ls == 0.0:
        return 50.0 if g == 0.0 else 100.0
    return 100.0 - 100.0 / (1.0 + g / ls)


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def compute_patterns(ohlcv: pd.DataFrame, as_of: str) -> dict[str, int | None]:
    """Return the state of every pattern using only bars with ``Date <= as_of``."""
    close = _closes_up_to(ohlcv, as_of)
    n = len(close)
    out: dict[str, int | None] = dict.fromkeys(PATTERNS)

    if n >= RSI_MIN_BARS:
        rsi = _rsi(close)
        out["rsi_extreme"] = 1 if rsi <= RSI_OVERSOLD else -1 if rsi >= RSI_OVERBOUGHT else 0

    if n >= MACD_MIN_BARS:
        macd = (
            close.ewm(span=MACD_FAST, adjust=False).mean()
            - close.ewm(span=MACD_SLOW, adjust=False).mean()
        )
        hist = macd - macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
        window = hist.iloc[-(MACD_CROSS_LOOKBACK + 1):].tolist()
        state = 0
        for prev, cur in zip(window, window[1:], strict=False):
            if prev < 0 < cur:
                state = 1
            elif prev > 0 > cur:
                state = -1
        out["macd_cross"] = state

    if n >= BREAKOUT_MIN_BARS:
        prior = close.iloc[-(BREAKOUT_WINDOW + 1):-1]
        last = float(close.iloc[-1])
        out["breakout_20"] = 1 if last > prior.max() else -1 if last < prior.min() else 0

    if n >= SMA_SLOW:
        sma200 = float(close.iloc[-SMA_SLOW:].mean())
        sma50 = float(close.iloc[-SMA_FAST:].mean())
        out["trend_sma200"] = _sign(float(close.iloc[-1]) - sma200)
        out["sma50_200"] = _sign(sma50 - sma200)

    if n >= BB_WINDOW:
        tail = close.iloc[-BB_WINDOW:]
        mid, sd = float(tail.mean()), float(tail.std(ddof=0))
        last = float(close.iloc[-1])
        out["bollinger_out"] = (
            1 if last < mid - BB_SIGMA * sd else -1 if last > mid + BB_SIGMA * sd else 0
        )

    return out
