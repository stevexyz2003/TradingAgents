"""Look-ahead-free price patterns computed from OHLCV closes (fork-only).

Every pattern is +1 (bullish), -1 (bearish), 0 (computable but inactive) or
``None`` (not enough bars). :func:`compute_patterns` truncates the frame to
``Date <= as_of`` itself, before any indicator is computed, so the result can
only depend on prices up to and including the decision date.

The breakout is the *close-based* Donchian variant (extreme of prior closes, not of
highs/lows). RSI is Wilder's: seeded with the simple mean of the first 14 gains and
losses, then smoothed recursively. Daily bars are de-duplicated on the normalised
date (last row wins), so the warm-up counts sessions, not rows.

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
    frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date", kind="stable")
    frame = frame.drop_duplicates(subset="Date", keep="last")
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is not None:
        cutoff = cutoff.tz_localize(None)
    frame = frame[frame["Date"] <= cutoff.normalize()]
    return frame["Close"].astype(float).reset_index(drop=True)


def _rsi(close: pd.Series) -> float:
    """Wilder RSI: SMA seed over the first 14 changes, then recursive smoothing."""
    delta = close.diff().dropna().to_numpy()
    gains, losses = delta.clip(min=0.0), (-delta).clip(min=0.0)
    avg_g = float(gains[:RSI_PERIOD].mean())
    avg_l = float(losses[:RSI_PERIOD].mean())
    for g, ls in zip(gains[RSI_PERIOD:], losses[RSI_PERIOD:], strict=True):
        avg_g = (avg_g * (RSI_PERIOD - 1) + g) / RSI_PERIOD
        avg_l = (avg_l * (RSI_PERIOD - 1) + ls) / RSI_PERIOD
    if avg_l == 0.0:
        return 50.0 if avg_g == 0.0 else 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _cross_state(values: list[float]) -> int:
    """+1/-1 if the sign flipped (zeros skipped: last non-zero sign counts), else 0."""
    state, last = 0, 0
    for v in values:
        sign = 1 if v > 0 else -1 if v < 0 else 0
        if sign == 0:
            continue
        if last == -1 and sign == 1:
            state = 1
        elif last == 1 and sign == -1:
            state = -1
        last = sign
    return state


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
        state = _cross_state(window)
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
