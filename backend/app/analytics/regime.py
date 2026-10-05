"""Market-regime model: a weighted vote of independent inputs (never a single indicator).

Each component returns a sub-score in [-1, +1] with a reason that cites its inputs. Missing inputs are
excluded (weights re-normalised) and lower confidence; they are listed in `missing_inputs`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.analytics.config import DEFAULTS, REGIME_VERSION
from app.technical.indicators import adx, ema, rsi

LABELS = ["STRONG BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "STRONG BULLISH"]


@dataclass(slots=True)
class RegimeInputs:
    nifty: pd.Series | None  # daily closes
    banknifty: pd.Series | None = None
    vix: pd.Series | None = None
    advances: int | None = None
    declines: int | None = None
    pct_above_50dma: float | None = None
    pct_above_200dma: float | None = None
    sector_rows: list | None = None  # SectorRow list (trend field)
    flows: list[tuple[str, float]] | None = None  # [(category, net ₹cr)] over recent sessions
    global_context: float | None = None  # [-1,1] if a global provider is configured


@dataclass(slots=True)
class Component:
    name: str
    score: float  # -1..1
    weight: float
    reason: str
    inputs: dict = field(default_factory=dict)


@dataclass(slots=True)
class RegimeResult:
    regime: str
    score: float  # -100..100
    confidence: float  # 0..100
    recommended_exposure_pct: float
    max_positions: int
    components: list[Component]
    missing_inputs: list[str]
    model_version: str = REGIME_VERSION


def _trend_component(name: str, close: pd.Series | None, weight: float) -> Component | None:
    if close is None or len(close.dropna()) < 210:
        return None
    c = close.dropna()
    e20, e50, e200 = ema(c, 20).iloc[-1], ema(c, 50).iloc[-1], ema(c, 200).iloc[-1]
    last = c.iloc[-1]
    slope50 = (ema(c, 50).iloc[-1] / ema(c, 50).iloc[-11] - 1.0) * 100.0
    pts = 0.0
    pts += 0.3 if last > e50 else -0.3
    pts += 0.3 if last > e200 else -0.3
    pts += 0.2 if e20 > e50 else -0.2
    pts += 0.2 * float(np.clip(slope50 / 2.0, -1, 1))
    return Component(
        name, float(np.clip(pts, -1, 1)), weight,
        f"{'Above' if last > e50 else 'Below'} 50-EMA, {'above' if last > e200 else 'below'} 200-EMA, "
        f"50-EMA 10-day slope {slope50:+.2f}%",
        {"close": round(float(last), 2), "ema20": round(float(e20), 2), "ema50": round(float(e50), 2),
         "ema200": round(float(e200), 2), "ema50_slope_10d_pct": round(float(slope50), 3)},
    )


def compute_regime(inp: RegimeInputs, cfg: dict | None = None) -> RegimeResult:
    cfg = cfg or DEFAULTS["regime"]
    w = cfg["weights"]
    comps: list[Component] = []
    missing: list[str] = []

    for key, series, label in (("nifty_trend", inp.nifty, "NIFTY 50 trend"),
                               ("banknifty_trend", inp.banknifty, "BANK NIFTY trend")):
        c = _trend_component(label, series, w[key])
        (comps.append(c) if c else missing.append(f"{label} (needs ≥210 sessions of index history)"))

    # Breadth: A/D ratio + % of stocks above 50/200 DMA.
    if inp.advances is not None and inp.declines is not None and (inp.advances + inp.declines) > 0:
        ad = inp.advances / max(inp.declines, 1)
        s = float(np.clip(np.log(ad) / np.log(3.0), -1, 1))
        parts = [s]
        if inp.pct_above_50dma is not None:
            parts.append((inp.pct_above_50dma - 50.0) / 30.0)
        if inp.pct_above_200dma is not None:
            parts.append((inp.pct_above_200dma - 50.0) / 30.0)
        sc = float(np.clip(np.mean(parts), -1, 1))
        comps.append(Component("Market breadth", sc, w["breadth"],
                               f"Advances {inp.advances} vs declines {inp.declines} (A/D {ad:.2f})"
                               + (f", {inp.pct_above_50dma:.0f}% above 50-DMA" if inp.pct_above_50dma is not None else "")
                               + (f", {inp.pct_above_200dma:.0f}% above 200-DMA" if inp.pct_above_200dma is not None else ""),
                               {"advances": inp.advances, "declines": inp.declines,
                                "pct_above_50dma": inp.pct_above_50dma, "pct_above_200dma": inp.pct_above_200dma}))
    else:
        missing.append("Market breadth")

    # India VIX: level and 10-day change. Low & falling = supportive; high & rising = risk-off.
    if inp.vix is not None and len(inp.vix.dropna()) >= 30:
        v = inp.vix.dropna()
        lvl, chg = float(v.iloc[-1]), float(100.0 * (v.iloc[-1] / v.iloc[-11] - 1.0))
        pctile = float((v.iloc[-252:] < lvl).mean() * 100.0)
        s = float(np.clip((50.0 - pctile) / 50.0 * 0.6 - np.clip(chg / 30.0, -1, 1) * 0.4, -1, 1))
        comps.append(Component("India VIX", s, w["vix"],
                               f"VIX {lvl:.2f} ({pctile:.0f}th percentile of 1y), 10-day change {chg:+.1f}%",
                               {"vix": lvl, "vix_percentile_1y": round(pctile, 1), "vix_change_10d_pct": round(chg, 2)}))
    else:
        missing.append("India VIX")

    # Index momentum: RSI + ADX direction of NIFTY 50.
    if inp.nifty is not None and len(inp.nifty.dropna()) >= 60:
        c = inp.nifty.dropna()
        r = float(rsi(c).iloc[-1])
        roc20 = float(100.0 * (c.iloc[-1] / c.iloc[-21] - 1.0))
        frame = pd.DataFrame({"high": c, "low": c, "close": c})
        a = adx(frame)
        di = float(a["plus_di"].iloc[-1] - a["minus_di"].iloc[-1]) if not np.isnan(a["plus_di"].iloc[-1]) else 0.0
        s = float(np.clip(0.5 * (r - 50.0) / 20.0 + 0.3 * np.clip(roc20 / 5.0, -1, 1) + 0.2 * np.sign(di), -1, 1))
        comps.append(Component("Index momentum", s, w["momentum"],
                               f"NIFTY RSI(14) {r:.1f}, 20-day return {roc20:+.2f}%",
                               {"rsi14": round(r, 2), "roc20_pct": round(roc20, 2)}))
    else:
        missing.append("Index momentum")

    # Sector participation: share of sector indices in an uptrend.
    if inp.sector_rows:
        ups = sum(1 for s in inp.sector_rows if s.trend == "up")
        downs = sum(1 for s in inp.sector_rows if s.trend == "down")
        n = len(inp.sector_rows)
        s = float(np.clip((ups - downs) / max(n, 1), -1, 1))
        comps.append(Component("Sector participation", s, w["sector_participation"],
                               f"{ups}/{n} sector indices in uptrend, {downs} in downtrend",
                               {"up": ups, "down": downs, "total": n}))
    else:
        missing.append("Sector participation")

    # Institutional flows (provisional): FII+DII net over recent sessions, FII weighted more.
    if inp.flows:
        fii = sum(v for k, v in inp.flows if k.upper().startswith("FII"))
        dii = sum(v for k, v in inp.flows if k.upper().startswith("DII"))
        s = float(np.clip((0.65 * fii + 0.35 * dii) / 10000.0, -1, 1))
        comps.append(Component("FII/DII flows", s, w["flows"],
                               f"Recent net flows: FII ₹{fii:,.0f} cr, DII ₹{dii:,.0f} cr (provisional)",
                               {"fii_net_cr": round(fii, 2), "dii_net_cr": round(dii, 2)}))
    else:
        missing.append("FII/DII flows")

    if inp.global_context is not None:
        comps.append(Component("Global context", float(np.clip(inp.global_context, -1, 1)), w["global"],
                               "Global market context provider", {}))
    else:
        missing.append("Global market context (no provider configured)")

    if not comps:
        return RegimeResult("NEUTRAL", 0.0, 0.0, cfg["exposure"]["NEUTRAL"] * 0.5, 1, [], missing)

    wsum = sum(c.weight for c in comps)
    composite = 100.0 * sum(c.score * c.weight for c in comps) / wsum
    th = cfg["thresholds"]
    if composite >= th["strong_bullish"]:
        label = "STRONG BULLISH"
    elif composite >= th["bullish"]:
        label = "BULLISH"
    elif composite > th["bearish"]:
        label = "NEUTRAL"
    elif composite > th["strong_bearish"]:
        label = "BEARISH"
    else:
        label = "STRONG BEARISH"

    # Confidence: agreement of components with the composite direction, coverage of inputs, and
    # distance from the nearest regime boundary.
    sign = np.sign(composite) if abs(composite) >= 5 else 0
    if sign == 0:
        agree = sum(c.weight for c in comps if abs(c.score) < 0.25) / wsum
    else:
        agree = sum(c.weight for c in comps if np.sign(c.score) == sign) / wsum
    coverage = wsum / sum(w.values())
    bounds = sorted(th.values())
    dist = min(abs(composite - b) for b in bounds)
    margin = float(np.clip(dist / 15.0, 0, 1))
    confidence = float(np.clip(100.0 * (0.5 * agree + 0.3 * coverage + 0.2 * margin), 0, 95))
    exposure = float(cfg["exposure"][label])
    if confidence < 50:  # uncertain regime → trim exposure
        exposure = round(exposure * 0.8, 1)
    return RegimeResult(label, round(composite, 2), round(confidence, 1), exposure,
                        int(cfg["max_positions"][label]), comps, missing)
