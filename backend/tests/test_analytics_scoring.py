import pytest

from app.analytics.config import DEFAULT_WEIGHTS, validate_weights
from app.analytics.scoring import build_score, confidence_from

IND = {"close": 1240.0, "ema_20": 1225.0, "ema_50": 1180.0, "ema_200": 1050.0, "adx": 28.0, "plus_di": 30.0,
       "minus_di": 15.0, "supertrend_dir": 1.0, "rsi_14": 63.0, "macd": 12.0, "macd_signal": 8.0, "macd_hist": 4.0,
       "roc_12": 5.0, "roc_63": 18.0, "stoch_k": 70.0, "williams_r": -20.0, "rel_volume": 1.8, "avg_vol_20": 2e5,
       "avg_vol_50": 1.5e5, "delivery_pct": 55.0, "avg_delivery_pct_20": 42.0, "atr_14": 25.0, "high_52w": 1300.0}
PA = {"structure": {"higher_highs": True, "higher_lows": True}, "patterns": {"breakout": {"detected": True}},
      "resistances": [{"price": 1300.0}]}


def _score(**kw):
    args = {"obv_rising": True, "ad_rising": True, "rs_rating": 85.0, "rs_excess": {"3m": 9.0},
                "fundamentals": (72.0, ["Revenue growth 18%"], [], None), "sector": (70.0, "Nifty IT"),
                "news": (60.0, [], [], None), "fno": (None, [], [], "Not an F&O stock"), "rr_t2": 2.4, "risk_pct": 4.0}
    args.update(kw)
    return build_score(DEFAULT_WEIGHTS, IND, PA, **args)


def test_score_is_transparent_and_bounded():
    s = _score()
    assert 0 <= s.total <= 100
    assert s.earned == pytest.approx(sum(c.points for c in s.components if c.points is not None), abs=0.05)
    assert s.available == pytest.approx(95.0)  # F&O (5) unavailable
    fno = next(c for c in s.components if c.key == "fno")
    assert fno.points is None and fno.missing_reason
    tech = next(c for c in s.components if c.key == "technical")
    assert tech.reasons and tech.points <= tech.weight


def test_missing_components_reduce_confidence_except_structural():
    s = _score()
    c_ok, _ = confidence_from(s, "BULLISH", 80, True, missing_optional={"fno"})
    s2 = _score(fundamentals=(None, [], [], "No data"))
    c_missing, notes = confidence_from(s2, "BULLISH", 80, True, missing_optional={"fno"})
    assert c_missing < c_ok and any("unavailable" in n for n in notes)
    assert c_ok <= 95  # never certain


def test_bearish_regime_and_stale_data_penalties():
    s = _score()
    base, _ = confidence_from(s, "BULLISH", 80, True, {"fno"})
    bear, _ = confidence_from(s, "BEARISH", 80, True, {"fno"})
    stale, _ = confidence_from(s, "BULLISH", 80, False, {"fno"})
    assert bear < base and stale < base


def test_overbought_rsi_lowers_momentum():
    hot = dict(IND, rsi_14=85.0)
    s_hot = build_score(DEFAULT_WEIGHTS, hot, PA, obv_rising=True, ad_rising=True, rs_rating=85.0, rs_excess=None,
                        fundamentals=(None, [], [], "x"), sector=(None, None), news=(50.0, [], [], None),
                        fno=(None, [], [], "x"), rr_t2=2.4, risk_pct=4.0)
    m = next(c for c in s_hot.components if c.key == "momentum")
    assert any("overextended" in x for x in m.cautions)


def test_weights_validation():
    w = validate_weights({**DEFAULT_WEIGHTS, "technical": 50})
    assert sum(w.values()) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        validate_weights({"bogus": 1})
    with pytest.raises(ValueError):
        validate_weights({"technical": -1})
