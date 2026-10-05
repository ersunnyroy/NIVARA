"""Split/bonus back-adjustment.

NOTE (verified 2026-10): the current NSE UDiFF bhavcopy does NOT adjust ``PrvsClsgPric`` on ex-dates, so
``detect_adjustments`` finds nothing for UDiFF data. The authoritative path is
``app.services.ingestion.derive_adjustments_from_actions`` (exchange corporate-action records, price-verified).
``detect_adjustments`` is kept for sources that do publish adjusted previous closes.

Original method notes:

Method: on an ex-date NSE publishes the *adjusted* previous close in the bhavcopy (``PrvsClsgPric`` /
``PREVCLOSE``). For consecutive trading rows (t-1, t) of one symbol::

    factor(t) = prev_close(t) / close(t-1)

is 1.0 on ordinary days and e.g. 0.2 on a 1:5 split ex-date or 0.5 on a 1:1 bonus ex-date. Factors that
deviate from 1 by more than ``threshold`` are treated as adjustment events. Back-adjustment multiplies all
prices strictly before the ex-date by the factor and divides volumes by it, so the adjusted series is
continuous with post-event prices. The factor reflects whatever the exchange applied (splits, bonuses,
rights and occasionally large special dividends) — it is derived from published numbers, not assumed.
Cross-check with corporate-action records before trusting an unexpected factor.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from itertools import pairwise

import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close")


def detect_adjustments(
    bars_by_date: Iterable[tuple[date, float, float | None]], threshold: float = 0.005
) -> list[tuple[date, float]]:
    """``bars_by_date``: (date, close, exchange prev_close) for one symbol → [(ex_date, factor)] ascending."""
    rows = sorted(bars_by_date, key=lambda r: r[0])
    out: list[tuple[date, float]] = []
    for (_, last_close, _), (d, _, prev_close) in pairwise(rows):
        if prev_close is None or last_close is None or last_close <= 0 or prev_close <= 0:
            continue
        factor = prev_close / last_close
        if abs(factor - 1.0) > threshold:
            out.append((d, factor))
    return out


def apply_adjustments(df: pd.DataFrame, adjustments: Iterable[tuple[date, float]]) -> pd.DataFrame:
    """Back-adjust a date-indexed OHLCV frame (columns open/high/low/close/volume). Returns a copy.

    Volume becomes float (e.g. ×5 after a 1:5 split). Missing columns are ignored.
    """
    out = df.copy()
    prices = [c for c in PRICE_COLUMNS if c in out.columns]
    if "volume" in out.columns:
        out["volume"] = out["volume"].astype(float)
    if prices:
        out[prices] = out[prices].astype(float)
    is_dt = isinstance(out.index, pd.DatetimeIndex)
    for ex_date, factor in adjustments:
        if factor <= 0:
            raise ValueError(f"invalid adjustment factor {factor} for {ex_date}")
        key = pd.Timestamp(ex_date) if is_dt else ex_date
        mask = out.index < key
        if prices:
            out.loc[mask, prices] = out.loc[mask, prices] * factor
        if "volume" in out.columns:
            out.loc[mask, "volume"] = out.loc[mask, "volume"] / factor
    return out
