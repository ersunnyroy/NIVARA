"""Sector strength vs NIFTY 50 and stock relative strength."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# NSE "Industry" (as used in niftyindices constituent lists) → NSE sectoral index used to measure it.
INDUSTRY_TO_INDEX: dict[str, str | None] = {
    "Financial Services": "Nifty Financial Services",
    "Capital Goods": "Nifty Capital Goods",
    "Healthcare": "Nifty Healthcare Index",
    "Automobile and Auto Components": "Nifty Auto",
    "Fast Moving Consumer Goods": "Nifty FMCG",
    "Chemicals": "Nifty Chemicals",
    "Information Technology": "Nifty IT",
    "Consumer Services": "Nifty Consumer Services",
    "Metals & Mining": "Nifty Metal",
    "Power": "Nifty Power",
    "Oil Gas & Consumable Fuels": "Nifty Oil & Gas",
    "Consumer Durables": "Nifty Consumer Durables",
    "Services": "Nifty Services Sector",
    "Realty": "Nifty Realty",
    "Construction": "Nifty Construction",
    "Telecommunication": "Nifty Telecommunications",
    "Construction Materials": "Nifty Cement",
    "Media Entertainment & Publication": "Nifty Media",
    "Textiles": None,
    "Diversified": None,
    "Forest Materials": None,
}

# Sector indices ranked on the dashboard (superset of the industry map).
SECTOR_INDICES: list[str] = [
    "Nifty Bank", "Nifty IT", "Nifty Auto", "Nifty Pharma", "Nifty FMCG", "Nifty Metal", "Nifty Realty",
    "Nifty Energy", "Nifty PSU Bank", "Nifty Private Bank", "Nifty Financial Services", "Nifty Media",
    "Nifty Healthcare Index", "Nifty Oil & Gas", "Nifty Consumer Durables", "Nifty Infrastructure",
    "Nifty Capital Goods", "Nifty Chemicals", "Nifty Power", "Nifty Construction", "Nifty Cement",
    "Nifty Telecommunications", "Nifty Consumer Services", "Nifty Services Sector", "Nifty PSE",
    "Nifty India Defence", "Nifty Capital Markets", "Nifty Commodities", "Nifty India Consumption",
]

BENCHMARK = "Nifty 50"
HORIZONS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126}


def period_return(close: pd.Series, n: int) -> float | None:
    s = close.dropna()
    if len(s) <= n:
        return None
    return float(100.0 * (s.iloc[-1] / s.iloc[-1 - n] - 1.0))


@dataclass(slots=True)
class SectorRow:
    index_name: str
    score: float
    rank: int = 0
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    rs_vs_nifty_1m: float | None = None
    rs_vs_nifty_3m: float | None = None
    trend: str | None = None
    details: dict = field(default_factory=dict)


def rank_sectors(index_closes: dict[str, pd.Series]) -> list[SectorRow]:
    """Score each sector index 0-100 on relative performance vs NIFTY 50 and its own trend.

    Composite (documented): 40% 1M RS, 35% 3M RS, 10% 1W RS (cross-sectional percentile each) +
    15% trend (close above 50-day SMA, 50-day SMA rising).
    """
    bench = index_closes.get(BENCHMARK)
    if bench is None or len(bench.dropna()) < 70:
        return []
    b = {k: period_return(bench, n) for k, n in HORIZONS.items()}
    rows: list[SectorRow] = []
    for name in SECTOR_INDICES:
        s = index_closes.get(name)
        if s is None or len(s.dropna()) < 70:
            continue
        r = {k: period_return(s, n) for k, n in HORIZONS.items()}
        sma50 = s.rolling(50, min_periods=50).mean()
        above = bool(s.iloc[-1] > sma50.iloc[-1]) if not np.isnan(sma50.iloc[-1]) else None
        rising = bool(sma50.iloc[-1] > sma50.iloc[-6]) if len(sma50.dropna()) > 6 else None
        trend = "up" if above and rising else "down" if (above is False and rising is False) else "sideways"
        rows.append(SectorRow(
            index_name=name, score=0.0, ret_1w=r["1w"], ret_1m=r["1m"], ret_3m=r["3m"],
            rs_vs_nifty_1m=None if r["1m"] is None or b["1m"] is None else r["1m"] - b["1m"],
            rs_vs_nifty_3m=None if r["3m"] is None or b["3m"] is None else r["3m"] - b["3m"],
            trend=trend,
            details={"rs_1w": None if r["1w"] is None or b["1w"] is None else r["1w"] - b["1w"],
                     "above_50dma": above, "sma50_rising": rising},
        ))
    if not rows:
        return []

    def pct_rank(vals: list[float | None]) -> list[float]:
        arr = pd.Series([np.nan if v is None else v for v in vals], dtype=float)
        return list(arr.rank(pct=True).fillna(0.5) * 100.0)

    p1m = pct_rank([r.rs_vs_nifty_1m for r in rows])
    p3m = pct_rank([r.rs_vs_nifty_3m for r in rows])
    p1w = pct_rank([r.details["rs_1w"] for r in rows])
    for i, r in enumerate(rows):
        trend_pts = 100.0 if r.trend == "up" else 0.0 if r.trend == "down" else 50.0
        r.score = round(0.40 * p1m[i] + 0.35 * p3m[i] + 0.10 * p1w[i] + 0.15 * trend_pts, 2)
        r.details.update({"pct_rank_rs_1m": round(p1m[i], 1), "pct_rank_rs_3m": round(p3m[i], 1)})
    rows.sort(key=lambda x: -x.score)
    for i, r in enumerate(rows, 1):
        r.rank = i
    return rows


def stock_relative_strength(stock_close: pd.Series, bench_close: pd.Series) -> dict[str, float | None]:
    """Excess return of the stock over NIFTY 50 for each horizon (percentage points)."""
    out: dict[str, float | None] = {}
    for k, n in HORIZONS.items():
        rs, rb = period_return(stock_close, n), period_return(bench_close, n)
        out[k] = None if rs is None or rb is None else round(rs - rb, 3)
    return out


def rs_percentiles(rs_by_symbol: dict[str, dict[str, float | None]]) -> dict[str, float]:
    """Cross-sectional RS rating 0-100 (weights: 3M 40%, 6M 30%, 1M 20%, 1W 10%)."""
    if not rs_by_symbol:
        return {}
    df = pd.DataFrame(rs_by_symbol).T.astype(float)
    weights = {"3m": 0.4, "6m": 0.3, "1m": 0.2, "1w": 0.1}
    total = pd.Series(0.0, index=df.index)
    wsum = pd.Series(0.0, index=df.index)
    for k, w in weights.items():
        if k in df:
            pr = df[k].rank(pct=True) * 100.0
            mask = pr.notna()
            total[mask] += w * pr[mask]
            wsum[mask] += w
    rating = (total / wsum.replace(0.0, np.nan)).fillna(50.0)
    return {str(k): round(float(v), 2) for k, v in rating.items()}
