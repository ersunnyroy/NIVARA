"""Deterministic SYNTHETIC price series for unit tests only (never used by the application)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_bars(n: int = 300, start: float = 100.0, drift: float = 0.001, vol: float = 0.015, seed: int = 7,
              start_date: str = "2024-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    volume = rng.integers(80_000, 120_000, n).astype(float)
    idx = pd.bdate_range(start_date, periods=n)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
    df["turnover"] = df["close"] * df["volume"]
    df["delivery_pct"] = 45.0
    return df


def linear_bars(n: int = 260, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    close = start + step * np.arange(n)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"open": close - step / 2, "high": close + 1, "low": close - 1, "close": close,
                         "volume": np.full(n, 100_000.0)}, index=idx)
