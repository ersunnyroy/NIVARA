import numpy as np
import pandas as pd

from app.technical import patterns as pt
from tests.synthetic import make_bars


def _frame(closes, vol=None, spread=0.5):
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    vol = np.full(len(closes), 100_000.0) if vol is None else np.asarray(vol, dtype=float)
    return pd.DataFrame({"open": closes, "high": closes + spread, "low": closes - spread, "close": closes,
                         "volume": vol}, index=idx)


def test_pivots_need_right_confirmation():
    closes = [10, 11, 12, 13, 12, 11, 10, 11, 12]
    df = _frame(closes)
    piv = pt.find_pivots(df, k=3)
    assert any(p.kind == "high" and p.idx == 3 for p in piv)
    # a peak at the last bar can never be a confirmed pivot
    df2 = _frame([10, 11, 12, 13, 14, 15, 16])
    assert not [p for p in pt.find_pivots(df2, k=3) if p.idx >= len(df2) - 3]


def test_breakout_with_volume():
    closes = [100 + (i % 5) * 0.3 for i in range(30)] + [104.0]
    vol = [100_000.0] * 30 + [250_000.0]
    bo, bd = pt.detect_breakout(_frame(closes, vol))
    assert bo.detected and bo.details["volume_confirmed"]
    assert not bd.detected


def test_breakdown():
    closes = [100 + (i % 5) * 0.3 for i in range(30)] + [96.0]
    _, bd = pt.detect_breakout(_frame(closes))
    assert bd.detected


def test_gap_up():
    df = _frame([100.0] * 10)
    df.iloc[-1, df.columns.get_loc("open")] = 102.0
    df.iloc[-1, df.columns.get_loc("high")] = 103.0
    gu, gd = pt.detect_gaps(df)
    assert gu.detected and not gd.detected


def test_consolidation():
    closes = list(np.linspace(80, 100, 30)) + [100 + 0.2 * ((-1) ** i) for i in range(15)]
    det = pt.detect_consolidation(_frame(closes, spread=0.4))
    assert det.detected


def test_double_bottom_confirmed():
    seg = list(np.linspace(120, 100, 10)) + list(np.linspace(100, 110, 8)) + list(np.linspace(110, 100.5, 8)) \
        + list(np.linspace(100.5, 112, 8))
    df = _frame(seg)
    piv = pt.find_pivots(df, k=3)
    _, db = pt.detect_double(piv, df, min_sep=5)
    assert db.detected and db.details["confirmed"]


def test_support_resistance_split_by_price():
    df = make_bars(n=260)
    sup, res = pt.support_resistance(df)
    last = df["close"].iloc[-1]
    assert all(s.price < last for s in sup) and all(r.price >= last for r in res)
    if len(sup) > 1:
        assert sup[0].price >= sup[1].price  # nearest first


def test_analyze_price_action_shape():
    out = pt.analyze_price_action(make_bars(n=260))
    assert set(out) >= {"structure", "supports", "resistances", "patterns"}
    assert {"breakout", "retest", "flag", "triangle", "channel", "double_top"} <= set(out["patterns"])
