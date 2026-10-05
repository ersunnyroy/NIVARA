import numpy as np
import pandas as pd
import pytest

from app.technical import indicators as ti
from tests.synthetic import linear_bars, make_bars


def test_sma_and_ema_basic():
    s = pd.Series([1.0, 2, 3, 4, 5, 6])
    assert ti.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0, 5.0]
    assert np.isnan(ti.sma(s, 3).iloc[1])
    e = ti.ema(s, 3)
    # alpha = 0.5; adjust=False recursion from first value: 1, 1.5, 2.25, 3.125 ...
    assert e.iloc[2] == pytest.approx(2.25)
    assert e.iloc[3] == pytest.approx(3.125)


def test_rsi_extremes_and_range():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert ti.rsi(up).iloc[-1] == pytest.approx(100.0)
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert ti.rsi(down).iloc[-1] == pytest.approx(0.0)
    df = make_bars()
    r = ti.rsi(df["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_atr_constant_range():
    df = linear_bars()
    a = ti.atr(df).dropna()
    # high-low = 2, |high-prev close| = 1.5, |low-prev close| = 0.5 → TR = 2 every bar.
    assert a.iloc[-1] == pytest.approx(2.0)


def test_macd_positive_in_uptrend():
    m = ti.macd(linear_bars()["close"])
    assert m["macd"].iloc[-1] > 0
    assert m["macd_hist"].iloc[-1] == pytest.approx(m["macd"].iloc[-1] - m["macd_signal"].iloc[-1])


def test_bollinger_and_stochastic_bounds():
    df = make_bars()
    bb = ti.bollinger(df["close"]).dropna()
    assert (bb["bb_upper"] >= bb["bb_mid"]).all() and (bb["bb_mid"] >= bb["bb_lower"]).all()
    st = ti.stochastic(df).dropna()
    assert ((st["stoch_k"] >= 0) & (st["stoch_k"] <= 100)).all()
    wr = ti.williams_r(df).dropna()
    assert ((wr <= 0) & (wr >= -100)).all()


def test_adx_strong_trend_and_supertrend_up():
    df = linear_bars()
    a = ti.adx(df)
    assert a["adx"].iloc[-1] > 25
    assert a["plus_di"].iloc[-1] > a["minus_di"].iloc[-1]
    st = ti.supertrend(df)
    assert st["supertrend_dir"].iloc[-1] == 1
    assert st["supertrend"].iloc[-1] < df["close"].iloc[-1]


def test_obv_and_relative_volume():
    df = pd.DataFrame({"high": [2, 3, 3, 2.0], "low": [1, 2, 2, 1.0], "close": [1.5, 2.5, 2.5, 1.5],
                       "volume": [100, 200, 300, 400.0]})
    assert ti.obv(df).tolist() == [0.0, 200.0, 200.0, -200.0]
    v = pd.Series([100.0] * 20 + [300.0])
    assert ti.relative_volume(v).iloc[-1] == pytest.approx(3.0)


def test_historical_volatility_scale():
    df = make_bars(vol=0.02, n=400)
    hv = ti.historical_volatility(df["close"]).dropna()
    # daily σ≈2% → annualised ≈ 0.32; allow sampling noise
    assert 0.2 < hv.median() < 0.45


def test_rolling_percentile_causal():
    s = pd.Series(np.arange(100, dtype=float))
    p = ti.rolling_percentile(s, window=50, min_periods=10)
    assert p.iloc[-1] == pytest.approx(100.0)  # latest is the max of its window
    # causal: changing future values does not change past percentiles
    s2 = s.copy()
    s2.iloc[-1] = -5
    p2 = ti.rolling_percentile(s2, window=50, min_periods=10)
    assert p.iloc[:-1].equals(p2.iloc[:-1])


def test_compute_all_no_lookahead():
    df = make_bars(n=300)
    full = ti.compute_all(df)
    part = ti.compute_all(df.iloc[:250])
    cols = ["ema_20", "rsi_14", "atr_14", "adx", "macd", "supertrend", "bb_upper", "rel_volume", "hv_percentile"]
    pd.testing.assert_frame_equal(full[cols].iloc[:250], part[cols], check_exact=False, atol=1e-9)


def test_latest_values_nan_to_none():
    df = make_bars(n=30)
    vals = ti.latest_values(ti.compute_all(df))
    assert vals["ema_200"] is None
    assert isinstance(vals["close"], float)
