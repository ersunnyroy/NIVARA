"""Price-action detection on daily bars.

All detectors look only at the bars they are given (callers truncate history to the evaluation
date), and swing points need `k` bars on the right to be *confirmed* — so a pivot is never
"known" before it could have been known in real time. Patterns are supporting evidence only; the
scoring engine never relies on them exclusively.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import pairwise

import numpy as np
import pandas as pd

from app.technical.indicators import atr as _atr


@dataclass(slots=True)
class Pivot:
    idx: int
    date: str
    price: float
    kind: str  # "high" | "low"


@dataclass(slots=True)
class Level:
    price: float
    kind: str  # support | resistance
    touches: int
    last_touch: str
    strength: float  # 0-1


@dataclass(slots=True)
class Detection:
    name: str
    detected: bool
    direction: str = "neutral"  # bullish | bearish | neutral
    level: float | None = None
    details: dict = field(default_factory=dict)


def find_pivots(df: pd.DataFrame, k: int = 3) -> list[Pivot]:
    """Swing highs/lows with k bars each side. Only pivots with k confirmed bars on the right."""
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    dates = [str(d)[:10] for d in df.index]
    out: list[Pivot] = []
    n = len(df)
    for i in range(k, n - k):
        win_h = highs[i - k : i + k + 1]
        win_l = lows[i - k : i + k + 1]
        # Plateaus count once, at their first bar.
        if int(np.argmax(win_h)) == k:
            out.append(Pivot(i, dates[i], float(highs[i]), "high"))
        if int(np.argmin(win_l)) == k:
            out.append(Pivot(i, dates[i], float(lows[i]), "low"))
    return out


def support_resistance(
    df: pd.DataFrame, pivots: list[Pivot] | None = None, lookback: int = 250, tol_atr: float = 0.6
) -> tuple[list[Level], list[Level]]:
    """Cluster pivot prices (within tol_atr × ATR) into levels; split by current price."""
    if len(df) < 30:
        return [], []
    d = df.iloc[-lookback:]
    piv = [p for p in (pivots or find_pivots(df)) if p.idx >= len(df) - lookback]
    a = float(_atr(df).iloc[-1]) if len(df) > 15 else float((d["high"] - d["low"]).mean())
    if not np.isfinite(a) or a <= 0:
        a = float(d["close"].iloc[-1]) * 0.02
    tol = tol_atr * a
    clusters: list[list[Pivot]] = []
    for p in sorted(piv, key=lambda x: x.price):
        if clusters and abs(p.price - np.mean([q.price for q in clusters[-1]])) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    last_close = float(d["close"].iloc[-1])
    n = len(df)
    sup, res = [], []
    for c in clusters:
        price = float(np.mean([q.price for q in c]))
        last = max(c, key=lambda q: q.idx)
        recency = 1.0 - (n - 1 - last.idx) / max(lookback, 1)
        strength = min(1.0, 0.25 * len(c) + 0.5 * max(recency, 0.0))
        lvl = Level(round(price, 2), "support" if price < last_close else "resistance", len(c), last.date, round(strength, 3))
        (sup if price < last_close else res).append(lvl)
    sup.sort(key=lambda lv: -lv.price)  # nearest first
    res.sort(key=lambda lv: lv.price)
    return sup, res


def trend_structure(pivots: list[Pivot]) -> dict:
    highs = [p for p in pivots if p.kind == "high"][-3:]
    lows = [p for p in pivots if p.kind == "low"][-3:]
    hh = len(highs) >= 2 and all(b.price > a.price for a, b in pairwise(highs))
    lh = len(highs) >= 2 and all(b.price < a.price for a, b in pairwise(highs))
    hl = len(lows) >= 2 and all(b.price > a.price for a, b in pairwise(lows))
    ll = len(lows) >= 2 and all(b.price < a.price for a, b in pairwise(lows))
    if hh and hl:
        label = "uptrend (higher highs & higher lows)"
    elif lh and ll:
        label = "downtrend (lower highs & lower lows)"
    else:
        label = "mixed / range"
    return {"higher_highs": hh, "higher_lows": hl, "lower_highs": lh, "lower_lows": ll, "label": label}


def detect_breakout(df: pd.DataFrame, n: int = 20, vol_mult: float = 1.5) -> tuple[Detection, Detection]:
    if len(df) < n + 2:
        return Detection("breakout", False), Detection("breakdown", False)
    prior = df.iloc[-n - 1 : -1]
    last = df.iloc[-1]
    hi, lo = float(prior["high"].max()), float(prior["low"].min())
    avg_vol = float(prior["volume"].mean()) or np.nan
    rv = float(last["volume"]) / avg_vol if avg_vol and np.isfinite(avg_vol) else None
    vol_ok = rv is not None and rv >= vol_mult
    up = float(last["close"]) > hi
    down = float(last["close"]) < lo
    return (
        Detection("breakout", up, "bullish", round(hi, 2),
                  {"lookback": n, "rel_volume": rv and round(rv, 2), "volume_confirmed": vol_ok}),
        Detection("breakdown", down, "bearish", round(lo, 2),
                  {"lookback": n, "rel_volume": rv and round(rv, 2), "volume_confirmed": vol_ok}),
    )


def detect_retest(df: pd.DataFrame, n: int = 20, within: int = 10, tol_atr: float = 1.0) -> Detection:
    """Breakout above an n-day high in the last `within` sessions, price since pulled back to the
    breakout level (within tol_atr × ATR) and closes still above it."""
    if len(df) < n + within + 2:
        return Detection("retest", False)
    a = float(_atr(df).iloc[-1])
    closes, highs = df["close"].to_numpy(), df["high"].to_numpy()
    lows = df["low"].to_numpy()
    last_i = len(df) - 1
    for j in range(last_i - 1, last_i - within - 1, -1):
        level = highs[j - n : j].max()
        if closes[j] > level:  # breakout bar j
            after_lows = lows[j + 1 : last_i + 1]
            if len(after_lows) == 0:
                continue
            touched = after_lows.min() <= level + tol_atr * a
            holding = closes[last_i] > level and after_lows.min() >= level - 0.5 * a
            if touched and holding:
                return Detection("retest", True, "bullish", round(float(level), 2),
                                 {"breakout_date": str(df.index[j])[:10], "sessions_since": last_i - j})
            return Detection("retest", False, details={"breakout_date": str(df.index[j])[:10]})
    return Detection("retest", False)


def detect_consolidation(df: pd.DataFrame, n: int = 15, max_range_atr: float = 3.0) -> Detection:
    if len(df) < max(n, 30):
        return Detection("consolidation", False)
    win = df.iloc[-n:]
    a = float(_atr(df).iloc[-1])
    rng = float(win["high"].max() - win["low"].min())
    ok = a > 0 and rng <= max_range_atr * a
    return Detection("consolidation", ok, "neutral", None,
                     {"range": round(rng, 2), "range_atr_multiple": round(rng / a, 2) if a else None,
                      "box_high": round(float(win["high"].max()), 2), "box_low": round(float(win["low"].min()), 2)})


def detect_gaps(df: pd.DataFrame, min_pct: float = 0.5) -> tuple[Detection, Detection]:
    if len(df) < 2:
        return Detection("gap_up", False), Detection("gap_down", False)
    prev, last = df.iloc[-2], df.iloc[-1]
    up_pct = 100.0 * (float(last["open"]) / float(prev["high"]) - 1.0)
    dn_pct = 100.0 * (1.0 - float(last["open"]) / float(prev["low"]))
    return (
        Detection("gap_up", up_pct >= min_pct, "bullish", round(float(prev["high"]), 2), {"gap_pct": round(up_pct, 2)}),
        Detection("gap_down", dn_pct >= min_pct, "bearish", round(float(prev["low"]), 2), {"gap_pct": round(dn_pct, 2)}),
    )


def detect_double(pivots: list[Pivot], df: pd.DataFrame, tol_pct: float = 2.0, min_sep: int = 10,
                  min_depth_pct: float = 4.0) -> tuple[Detection, Detection]:
    """Double top / bottom from the last two swing highs/lows; confirmed when price crosses the neckline."""
    last_close = float(df["close"].iloc[-1]) if len(df) else np.nan
    res = []
    for kind, name, direction in (("high", "double_top", "bearish"), ("low", "double_bottom", "bullish")):
        ps = [p for p in pivots if p.kind == kind][-2:]
        if len(ps) < 2 or ps[1].idx - ps[0].idx < min_sep:
            res.append(Detection(name, False))
            continue
        a, b = ps
        similar = abs(a.price - b.price) / a.price * 100.0 <= tol_pct
        seg = df.iloc[a.idx : b.idx + 1]
        neckline = float(seg["low"].min()) if kind == "high" else float(seg["high"].max())
        depth = abs(neckline - a.price) / a.price * 100.0
        formed = similar and depth >= min_depth_pct
        confirmed = formed and ((last_close < neckline) if kind == "high" else (last_close > neckline))
        res.append(Detection(name, formed, direction, round(neckline, 2),
                             {"first": a.date, "second": b.date, "depth_pct": round(depth, 2),
                              "confirmed": confirmed}))
    return res[0], res[1]


def _fit(points: list[Pivot]) -> tuple[float, float, float]:
    x = np.array([p.idx for p in points], dtype=float)
    y = np.array([p.price for p in points], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-9
    return float(slope), float(intercept), 1.0 - ss_res / ss_tot


def detect_triangle_channel(pivots: list[Pivot], df: pd.DataFrame, window: int = 60) -> tuple[Detection, Detection]:
    n = len(df)
    recent = [p for p in pivots if p.idx >= n - window]
    highs = [p for p in recent if p.kind == "high"]
    lows = [p for p in recent if p.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return Detection("triangle", False), Detection("channel", False)
    sh, ih, _ = _fit(highs)
    sl, il, _ = _fit(lows)
    price = float(df["close"].iloc[-1])
    # Normalise slopes to % of price per bar.
    nh, nl = 100 * sh / price, 100 * sl / price
    flat = 0.03
    tri_kind = None
    if nh < -flat and nl > flat:
        tri_kind = "symmetrical"
    elif abs(nh) <= flat and nl > flat:
        tri_kind = "ascending"
    elif nh < -flat and abs(nl) <= flat:
        tri_kind = "descending"
    upper_now, lower_now = sh * (n - 1) + ih, sl * (n - 1) + il
    tri = Detection("triangle", tri_kind is not None,
                    {"ascending": "bullish", "descending": "bearish"}.get(tri_kind or "", "neutral"),
                    round(upper_now, 2) if tri_kind else None,
                    {"type": tri_kind, "upper_line": round(upper_now, 2), "lower_line": round(lower_now, 2)})
    parallel = abs(nh - nl) <= 0.05 and abs(nh) > flat / 2
    chan = Detection("channel", parallel and upper_now > lower_now,
                     "bullish" if nh > 0 else "bearish" if nh < 0 else "neutral", None,
                     {"slope_pct_per_bar": round(nh, 4), "upper_line": round(upper_now, 2),
                      "lower_line": round(lower_now, 2)})
    return tri, chan


def detect_flag(df: pd.DataFrame, pole_max_bars: int = 10, pole_min_pct: float = 8.0,
                flag_min: int = 4, flag_max: int = 15) -> Detection:
    """Bull flag: strong pole then a tight, shallow pullback/consolidation."""
    if len(df) < pole_max_bars + flag_max + 5:
        return Detection("flag", False)
    close, high, low = df["close"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy()
    last = len(df) - 1
    for flag_len in range(flag_min, flag_max + 1):
        pole_end = last - flag_len
        for pole_len in range(3, pole_max_bars + 1):
            pole_start = pole_end - pole_len
            if pole_start < 0:
                break
            gain = 100.0 * (close[pole_end] / close[pole_start] - 1.0)
            if gain < pole_min_pct:
                continue
            f_hi, f_lo = high[pole_end + 1 : last + 1].max(), low[pole_end + 1 : last + 1].min()
            pole_range = close[pole_end] - close[pole_start]
            retrace = (close[pole_end] - f_lo) / pole_range if pole_range > 0 else 1.0
            tight = (f_hi - f_lo) <= 0.5 * pole_range
            if retrace <= 0.5 and tight and f_hi <= high[pole_end] * 1.01:
                return Detection("flag", True, "bullish", round(float(f_hi), 2),
                                 {"pole_gain_pct": round(gain, 2), "flag_sessions": flag_len,
                                  "retracement": round(float(retrace), 2)})
    return Detection("flag", False)


def analyze_price_action(df: pd.DataFrame) -> dict:
    """Run every detector; returns a JSON-friendly dict."""
    pivots = find_pivots(df)
    sup, res = support_resistance(df, pivots)
    bo, bd = detect_breakout(df)
    gu, gd = detect_gaps(df)
    dt, db = detect_double(pivots, df)
    tri, chan = detect_triangle_channel(pivots, df)
    dets = [bo, bd, detect_retest(df), detect_consolidation(df), gu, gd, dt, db, detect_flag(df), tri, chan]
    return {
        "structure": trend_structure(pivots),
        "supports": [asdict(s) for s in sup[:5]],
        "resistances": [asdict(r) for r in res[:5]],
        "patterns": {d.name: asdict(d) for d in dets},
        "last_swing_low": next((p.price for p in reversed(pivots) if p.kind == "low"), None),
        "last_swing_high": next((p.price for p in reversed(pivots) if p.kind == "high"), None),
    }
