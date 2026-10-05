"""Technical indicators on daily OHLCV.

Conventions
-----------
* Input: DataFrame indexed by date (ascending) with float columns open, high, low, close, volume
  (prices already split/bonus adjusted).
* Every indicator is causal: the value at row t uses rows <= t only (no centred windows), so the
  same code is safe for point-in-time backtests.
* Wilder smoothing (RMA) is used where the original definition uses it (RSI, ATR, ADX).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

INDICATOR_VERSION = "ind-1.0"
TRADING_DAYS = 252


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    # Seed with the SMA of the first n values (classic definition), then recursive EMA.
    out = s.ewm(span=n, adjust=False, min_periods=n).mean()
    return out


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (alpha = 1/n)."""
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = rma(gain, n)
    avg_loss = rma(loss, n)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    # All gains, no losses → RSI 100.
    out = out.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3) -> pd.DataFrame:
    lowest = df["low"].rolling(k, min_periods=k).min()
    highest = df["high"].rolling(k, min_periods=k).max()
    raw = 100.0 * (df["close"] - lowest) / (highest - lowest).replace(0.0, np.nan)
    k_line = raw.rolling(smooth, min_periods=smooth).mean()
    d_line = k_line.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"stoch_k": k_line, "stoch_d": d_line})


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return 100.0 * (close / close.shift(n) - 1.0)


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    highest = df["high"].rolling(n, min_periods=n).max()
    lowest = df["low"].rolling(n, min_periods=n).min()
    return -100.0 * (highest - df["close"]) / (highest - lowest).replace(0.0, np.nan)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    width = (upper - lower) / mid
    pct_b = (close - lower) / (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width, "bb_pct_b": pct_b})


def historical_volatility(close: pd.Series, n: int = 20) -> pd.Series:
    """Annualised close-to-close volatility (decimal, e.g. 0.28 = 28%)."""
    lr = np.log(close / close.shift(1))
    return lr.rolling(n, min_periods=n).std(ddof=1) * np.sqrt(TRADING_DAYS)


def rolling_percentile(s: pd.Series, window: int = TRADING_DAYS, min_periods: int = 60) -> pd.Series:
    """Percentile rank (0-100) of the latest value within its trailing window (causal)."""

    def _rank(a: np.ndarray) -> float:
        last = a[-1]
        if np.isnan(last):
            return np.nan
        valid = a[~np.isnan(a)]
        return 100.0 * (valid < last).sum() / max(len(valid) - 1, 1)

    return s.rolling(window, min_periods=min_periods).apply(_rank, raw=True)


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr_s = rma(true_range(df), n)
    plus_di = 100.0 * rma(plus_dm, n) / tr_s.replace(0.0, np.nan)
    minus_di = 100.0 * rma(minus_dm, n) / tr_s.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return pd.DataFrame({"adx": rma(dx, n), "plus_di": plus_di, "minus_di": minus_di})


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """Classic Supertrend. direction = 1 (up / bullish) or -1 (down)."""
    a = atr(df, n)
    hl2 = (df["high"] + df["low"]) / 2.0
    basic_up = (hl2 + mult * a).to_numpy()
    basic_dn = (hl2 - mult * a).to_numpy()
    close = df["close"].to_numpy()
    size = len(df)
    final_up = np.full(size, np.nan)
    final_dn = np.full(size, np.nan)
    st = np.full(size, np.nan)
    direction = np.zeros(size)
    for i in range(size):
        if np.isnan(basic_up[i]):
            continue
        if i == 0 or np.isnan(final_up[i - 1]):
            final_up[i], final_dn[i] = basic_up[i], basic_dn[i]
            direction[i] = 1 if close[i] >= basic_dn[i] else -1
            st[i] = final_dn[i] if direction[i] == 1 else final_up[i]
            continue
        final_up[i] = basic_up[i] if (basic_up[i] < final_up[i - 1] or close[i - 1] > final_up[i - 1]) else final_up[i - 1]
        final_dn[i] = basic_dn[i] if (basic_dn[i] > final_dn[i - 1] or close[i - 1] < final_dn[i - 1]) else final_dn[i - 1]
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] < final_dn[i] else 1
        else:
            direction[i] = 1 if close[i] > final_up[i] else -1
        st[i] = final_dn[i] if direction[i] == 1 else final_up[i]
    return pd.DataFrame(
        {"supertrend": st, "supertrend_dir": np.where(np.isnan(st), np.nan, direction)}, index=df.index
    )


def obv(df: pd.DataFrame) -> pd.Series:
    sign = np.sign(df["close"].diff()).fillna(0.0)
    return (sign * df["volume"]).cumsum()


def accumulation_distribution(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    return (mfm.fillna(0.0) * df["volume"]).cumsum()


def rolling_vwap(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """n-day volume-weighted average of the typical price (daily bars cannot give intraday VWAP)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(n, min_periods=n).sum()
    v = df["volume"].rolling(n, min_periods=n).sum()
    return pv / v.replace(0.0, np.nan)


def relative_volume(volume: pd.Series, n: int = 20) -> pd.Series:
    """Today's volume ÷ average of the previous n sessions (excludes today)."""
    avg_prev = volume.shift(1).rolling(n, min_periods=n).mean()
    return volume / avg_prev.replace(0.0, np.nan)


EMA_PERIODS = (5, 10, 20, 50, 100, 200)


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Return a frame with every indicator column appended (input not modified)."""
    out = df.copy()
    c = out["close"]
    for p in EMA_PERIODS:
        out[f"ema_{p}"] = ema(c, p)
        out[f"sma_{p}"] = sma(c, p)
    out = out.join(adx(out))
    out = out.join(supertrend(out))
    out["rsi_14"] = rsi(c)
    out = out.join(macd(c))
    out = out.join(stochastic(out))
    out["roc_12"] = roc(c, 12)
    out["roc_63"] = roc(c, 63)
    out["williams_r"] = williams_r(out)
    out["atr_14"] = atr(out)
    out["atr_pct"] = 100.0 * out["atr_14"] / c
    out = out.join(bollinger(c))
    out["hv_20"] = historical_volatility(c, 20)
    out["hv_percentile"] = rolling_percentile(out["hv_20"])
    out["bb_width_percentile"] = rolling_percentile(out["bb_width"])
    out["avg_vol_20"] = out["volume"].shift(1).rolling(20, min_periods=20).mean()
    out["avg_vol_50"] = out["volume"].shift(1).rolling(50, min_periods=50).mean()
    out["rel_volume"] = relative_volume(out["volume"])
    out["obv"] = obv(out)
    out["ad_line"] = accumulation_distribution(out)
    out["vwap_20"] = rolling_vwap(out)
    out["high_52w"] = out["high"].rolling(TRADING_DAYS, min_periods=120).max()
    out["low_52w"] = out["low"].rolling(TRADING_DAYS, min_periods=120).min()
    if "turnover" in out.columns:
        out["avg_turnover_20"] = out["turnover"].shift(1).rolling(20, min_periods=10).mean()
    if "delivery_pct" in out.columns:
        out["avg_delivery_pct_20"] = out["delivery_pct"].shift(1).rolling(20, min_periods=10).mean()
    return out


def latest_values(ind: pd.DataFrame) -> dict[str, float | None]:
    """Last row as a JSON-friendly dict (NaN → None)."""
    if ind.empty:
        return {}
    row = ind.iloc[-1]
    out: dict[str, float | None] = {}
    for k, v in row.items():
        if isinstance(v, (int, float, np.floating, np.integer)):
            fv = float(v)
            out[str(k)] = None if np.isnan(fv) else round(fv, 6)
    return out
