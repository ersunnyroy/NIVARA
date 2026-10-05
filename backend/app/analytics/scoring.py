"""Transparent Stock Opportunity Score (0-100).

Each component returns a fraction in [0, 1] plus reasons (bullish "why") and cautions ("why not").
Points = fraction × weight. Components with no data are shown as "n/a", excluded from the denominator
and reduce confidence — the total is `earned / available × 100`, and both raw and normalised figures
are returned so the user can see exactly how the score was built.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from app.analytics.config import DEFAULT_WEIGHTS, SCORING_VERSION


@dataclass(slots=True)
class ComponentScore:
    key: str
    label: str
    fraction: float | None  # None = unavailable
    weight: float
    points: float | None
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    missing_reason: str | None = None


@dataclass(slots=True)
class ScoreResult:
    total: float  # normalised 0-100
    earned: float
    available: float
    components: list[ComponentScore]
    missing_weight: float
    version: str = SCORING_VERSION

    def breakdown(self) -> dict:
        return {
            "total": self.total, "earned": self.earned, "available": self.available,
            "missing_weight": self.missing_weight, "version": self.version,
            "components": [asdict(c) for c in self.components],
        }


LABELS = {
    "technical": "Technical", "momentum": "Momentum", "volume": "Volume", "relative_strength": "Relative strength",
    "fundamentals": "Fundamentals", "sector": "Sector strength", "news": "News/sentiment", "fno": "F&O",
    "risk_reward": "Risk/reward",
}


def _v(ind: dict, k: str) -> float | None:
    x = ind.get(k)
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def score_technical(ind: dict, pa: dict) -> tuple[float, list[str], list[str]]:
    why, caution, pts, mx = [], [], 0.0, 0.0
    c, e20, e50, e200 = _v(ind, "close"), _v(ind, "ema_20"), _v(ind, "ema_50"), _v(ind, "ema_200")
    if c and e20 and e50 and e200:
        mx += 4
        if c > e20 > e50 > e200:
            pts += 4
            why.append(f"EMAs stacked bullishly: close ₹{c:.2f} > 20-EMA ₹{e20:.2f} > 50-EMA ₹{e50:.2f} > 200-EMA ₹{e200:.2f}")
        else:
            pts += 1.5 * (c > e50) + 1.5 * (c > e200) + 1.0 * (e50 > e200)
            if c < e200:
                caution.append(f"Close below 200-EMA (₹{e200:.2f}) — long-term trend not supportive")
            elif c < e50:
                caution.append(f"Close below 50-EMA (₹{e50:.2f})")
    adx_v, pdi, mdi = _v(ind, "adx"), _v(ind, "plus_di"), _v(ind, "minus_di")
    if adx_v is not None and pdi is not None and mdi is not None:
        mx += 2
        if adx_v >= 20 and pdi > mdi:
            pts += 2
            why.append(f"ADX {adx_v:.1f} with +DI > −DI: trending up")
        elif pdi > mdi:
            pts += 1
        else:
            caution.append(f"−DI above +DI (ADX {adx_v:.1f}): directional pressure is down")
    st = _v(ind, "supertrend_dir")
    if st is not None:
        mx += 1
        if st > 0:
            pts += 1
            why.append("Supertrend(10,3) bullish")
        else:
            caution.append("Supertrend(10,3) bearish")
    s = pa.get("structure", {})
    mx += 1.5
    if s.get("higher_highs") and s.get("higher_lows"):
        pts += 1.5
        why.append("Price structure: higher highs and higher lows")
    elif s.get("lower_highs") and s.get("lower_lows"):
        caution.append("Price structure: lower highs and lower lows")
    else:
        pts += 0.5
    pats = pa.get("patterns", {})
    mx += 1.5
    bull = [n for n in ("breakout", "retest", "flag", "double_bottom") if pats.get(n, {}).get("detected")]
    if pats.get("triangle", {}).get("detected") and pats["triangle"].get("direction") == "bullish":
        bull.append("ascending triangle")
    bear = [n for n in ("breakdown", "double_top") if pats.get(n, {}).get("detected")]
    if bull:
        pts += 1.5 if not bear else 0.5
        why.append("Pattern evidence: " + ", ".join(b.replace("_", " ") for b in bull))
    if bear:
        caution.append("Bearish pattern evidence: " + ", ".join(b.replace("_", " ") for b in bear))
    if pats.get("gap_down", {}).get("detected"):
        caution.append(f"Gap down today ({pats['gap_down']['details'].get('gap_pct')}%)")
    res = pa.get("resistances") or []
    a = _v(ind, "atr_14")
    if res and c and a:
        gap = res[0]["price"] - c
        if gap < 1.0 * a:
            caution.append(f"Resistance ₹{res[0]['price']:.2f} is within 1×ATR overhead")
    h52 = _v(ind, "high_52w")
    if h52 and c:
        mx += 1
        dist = 100 * (1 - c / h52)
        if dist <= 10:
            pts += 1
            why.append(f"Within {dist:.1f}% of the 52-week high (₹{h52:.2f})")
        elif dist >= 35:
            caution.append(f"{dist:.0f}% below the 52-week high")
    return (pts / mx if mx else 0.0), why, caution


def score_momentum(ind: dict) -> tuple[float, list[str], list[str]]:
    why, caution, pts, mx = [], [], 0.0, 0.0
    r = _v(ind, "rsi_14")
    if r is not None:
        mx += 3
        if 55 <= r <= 70:
            pts += 3
            why.append(f"RSI(14) {r:.1f}: strong but not overbought")
        elif 50 <= r < 55 or 70 < r <= 75:
            pts += 2
        elif 75 < r <= 80:
            pts += 1
            caution.append(f"RSI(14) {r:.1f}: stretched")
        elif r > 80:
            caution.append(f"RSI(14) {r:.1f}: overextended — chasing risk")
        elif r < 45:
            caution.append(f"RSI(14) {r:.1f}: weak momentum")
        else:
            pts += 1
    m, ms = _v(ind, "macd"), _v(ind, "macd_signal")
    if m is not None and ms is not None:
        mx += 2
        if m > ms and m > 0:
            pts += 2
            why.append("MACD above signal and above zero")
        elif m > ms:
            pts += 1
            why.append("MACD bullish crossover below zero (early)")
        else:
            caution.append("MACD below signal line")
    for k, w in (("roc_12", 1.0), ("roc_63", 1.5)):
        v = _v(ind, k)
        if v is not None:
            mx += w
            if v > 0:
                pts += w * min(1.0, v / (8.0 if k == "roc_12" else 20.0) + 0.3)
            if k == "roc_63" and v > 15:
                why.append(f"3-month rate of change {v:+.1f}%")
    sk = _v(ind, "stoch_k")
    if sk is not None:
        mx += 0.5
        if 50 <= sk <= 85:
            pts += 0.5
        elif sk > 90 and (r or 0) > 75:
            caution.append(f"Stochastic %K {sk:.0f} and RSI both overbought")
    wr = _v(ind, "williams_r")
    if wr is not None and wr > -5:
        caution.append(f"Williams %R {wr:.0f}: at the top of its 14-day range")
    return (pts / mx if mx else 0.0), why, caution


def score_volume(ind: dict, obv_rising: bool | None, ad_rising: bool | None) -> tuple[float, list[str], list[str]]:
    why, caution, pts, mx = [], [], 0.0, 0.0
    rv = _v(ind, "rel_volume")
    if rv is not None:
        mx += 3
        if 1.3 <= rv <= 4:
            pts += 3
            why.append(f"Volume {rv:.1f}× the 20-day average")
        elif 1.0 <= rv < 1.3:
            pts += 1.5
        elif rv > 4:
            pts += 1.5
            caution.append(f"Volume spike {rv:.1f}× average — check for news/one-off block deals")
        else:
            pts += 0.5
    if obv_rising is not None:
        mx += 2
        if obv_rising:
            pts += 2
            why.append("On-balance volume rising (accumulation)")
        else:
            caution.append("On-balance volume falling")
    if ad_rising is not None:
        mx += 1
        pts += 1 if ad_rising else 0
    v20, v50 = _v(ind, "avg_vol_20"), _v(ind, "avg_vol_50")
    if v20 and v50:
        mx += 1
        if v20 > v50:
            pts += 1
    dp, adp = _v(ind, "delivery_pct"), _v(ind, "avg_delivery_pct_20")
    if dp is not None and adp is not None:
        mx += 2
        if dp >= adp * 1.15 and dp >= 40:
            pts += 2
            why.append(f"Delivery {dp:.0f}% vs 20-day avg {adp:.0f}%: genuine buying interest")
        elif dp >= adp:
            pts += 1
        elif dp < 25:
            caution.append(f"Low delivery {dp:.0f}%: move driven by intraday trading")
    return (pts / mx if mx else 0.0), why, caution


def score_risk_reward(rr_t2: float | None, risk_pct: float | None) -> tuple[float, list[str], list[str]]:
    if rr_t2 is None:
        return 0.0, [], ["Risk/reward unavailable"]
    why, caution = [], []
    frac = float(np.clip((rr_t2 - 1.2) / (3.0 - 1.2), 0, 1))
    if rr_t2 >= 2:
        why.append(f"Reward:risk to Target 2 is 1:{rr_t2:.1f}")
    elif rr_t2 < 1.5:
        caution.append(f"Poor reward:risk (1:{rr_t2:.1f})")
    if risk_pct is not None and risk_pct > 6:
        frac *= 0.8
        caution.append(f"Wide stop: {risk_pct:.1f}% risk per share")
    return frac, why, caution


def build_score(
    weights: dict[str, float],
    ind: dict,
    pa: dict,
    *,
    obv_rising: bool | None,
    ad_rising: bool | None,
    rs_rating: float | None,
    rs_excess: dict | None,
    fundamentals: tuple[float | None, list[str], list[str], str | None],
    sector: tuple[float | None, str | None],
    news: tuple[float | None, list[str], list[str], str | None],
    fno: tuple[float | None, list[str], list[str], str | None],
    rr_t2: float | None,
    risk_pct: float | None,
) -> ScoreResult:
    """Assemble all components. External components are passed as (score_0_100|None, why, caution, missing_reason)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    comps: list[ComponentScore] = []

    def add(key: str, frac: float | None, why: list[str], caution: list[str], inputs: dict | None = None,
            missing: str | None = None) -> None:
        weight = float(w.get(key, 0.0))
        comps.append(ComponentScore(key, LABELS[key], None if frac is None else round(float(frac), 4), weight,
                                    None if frac is None else round(float(frac) * weight, 2),
                                    why, caution, inputs or {}, missing))

    f, y, n = score_technical(ind, pa)
    add("technical", f, y, n)
    f, y, n = score_momentum(ind)
    add("momentum", f, y, n)
    f, y, n = score_volume(ind, obv_rising, ad_rising)
    add("volume", f, y, n)
    if rs_rating is None:
        add("relative_strength", None, [], [], missing="Benchmark/peer history unavailable")
    else:
        why, cau = [], []
        ex3 = (rs_excess or {}).get("3m")
        if rs_rating >= 70:
            why.append(f"Relative-strength rating {rs_rating:.0f}/100"
                       + (f" ({ex3:+.1f} pts vs NIFTY over 3M)" if ex3 is not None else ""))
        elif rs_rating < 40:
            cau.append(f"Lagging the market: RS rating {rs_rating:.0f}/100")
        add("relative_strength", rs_rating / 100.0, why, cau, {"rs_rating": rs_rating, "excess_returns": rs_excess})
    fs, fy, fn, fm = fundamentals
    add("fundamentals", None if fs is None else fs / 100.0, fy, fn, missing=fm)
    ss, sname = sector
    if ss is None:
        add("sector", None, [], [], missing="Sector index data unavailable for this stock's industry")
    else:
        why, cau = [], []
        if ss >= 65:
            why.append(f"Strong sector: {sname} strength {ss:.0f}/100")
        elif ss < 40:
            cau.append(f"Weak sector: {sname} strength {ss:.0f}/100")
        add("sector", ss / 100.0, why, cau, {"sector_index": sname, "sector_score": ss})
    ns, ny, nn, nm = news
    add("news", None if ns is None else ns / 100.0, ny, nn, missing=nm)
    fos, foy, fon, fom = fno
    add("fno", None if fos is None else fos / 100.0, foy, fon, missing=fom)
    f, y, n = score_risk_reward(rr_t2, risk_pct)
    add("risk_reward", f, y, n, {"rr_t2": rr_t2, "risk_pct": risk_pct})

    earned = sum(c.points for c in comps if c.points is not None)
    available = sum(c.weight for c in comps if c.fraction is not None)
    missing_w = sum(c.weight for c in comps if c.fraction is None)
    total = 100.0 * earned / available if available else 0.0
    return ScoreResult(round(total, 2), round(earned, 2), round(available, 2), comps, round(missing_w, 2))


def confidence_from(score: ScoreResult, regime: str | None, regime_conf: float | None, data_fresh: bool,
                    missing_optional: set[str] | None = None) -> tuple[float, list[str]]:
    """Confidence 0-95 (never 100): score level, component agreement, data coverage, regime alignment.

    `missing_optional` lists components whose absence is structural (e.g. F&O for a non-F&O stock)
    and therefore not penalised.
    """
    notes: list[str] = []
    fr = [c.fraction for c in score.components if c.fraction is not None]
    dispersion = float(np.std(fr)) if fr else 0.5
    base = 0.55 * score.total + 0.25 * (100.0 * (1.0 - min(dispersion / 0.35, 1.0))) + 20.0
    penal_missing = sum(c.weight for c in score.components
                        if c.fraction is None and c.key not in (missing_optional or set()))
    if penal_missing:
        base -= 0.8 * penal_missing
        notes.append(f"Confidence reduced: {penal_missing:.0f} weight-points of inputs unavailable")
    if regime in ("BEARISH", "STRONG BEARISH"):
        base -= 12 if regime == "BEARISH" else 20
        notes.append(f"Confidence reduced: market regime {regime}")
    elif regime == "STRONG BULLISH":
        base += 4
    if regime_conf is not None and regime_conf < 50:
        base -= 4
    if not data_fresh:
        base -= 25
        notes.append("Confidence reduced: data not current")
    return round(float(np.clip(base, 5, 95)), 1), notes
