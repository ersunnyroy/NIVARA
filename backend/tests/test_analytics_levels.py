import pytest

from app.analytics.levels import SetupContext, compute_levels, position_size, rtick


def _ctx(**kw):
    base = {"cmp": 1240.0, "atr": 25.0, "ema20": 1225.0, "ema50": 1180.0,
                "supports": [{"price": 1220.0, "touches": 3, "strength": 0.8}, {"price": 1185.0, "touches": 2, "strength": 0.6}],
                "resistances": [{"price": 1290.0, "touches": 2, "strength": 0.7}, {"price": 1350.0, "touches": 2, "strength": 0.5}],
                "last_swing_low": 1195.0, "high_52w": 1410.0, "hv_20": 0.28, "patterns": {}, "regime": "BULLISH"}
    base.update(kw)
    return SetupContext(**base)


def test_levels_ordering_and_methodology():
    lv = compute_levels(_ctx())
    assert lv.stop < lv.conservative_low <= lv.conservative_high <= lv.entry_high
    assert lv.entry_low <= lv.entry_high
    assert lv.target1 < lv.target2 < lv.target3
    assert lv.stop < lv.entry_low
    for k in ("entry", "stop", "target1", "target2", "target3", "no_chase", "trailing"):
        assert lv.methodology.get(k)
    assert lv.reward_pcts[0] > 0
    assert lv.holding_min <= lv.holding_max


def test_stop_is_not_fixed_percent_and_respects_atr_band():
    lv = compute_levels(_ctx())
    mid = (lv.entry_low + lv.entry_high) / 2
    assert 1.0 * 25 - 0.06 <= mid - lv.stop <= 3.5 * 25 + 0.06


def test_breakout_setup_anchors_on_level():
    pats = {"breakout": {"detected": True, "level": 1230.0, "details": {"volume_confirmed": True}}}
    lv = compute_levels(_ctx(patterns=pats))
    assert lv.setup.startswith("Fresh breakout")
    assert lv.entry_low == pytest.approx(1230.0)


def test_no_chase_level_matches_min_rr():
    lv = compute_levels(_ctx(), {"min_rr_t2": 1.8, "max_risk_pct_per_setup": 8.0, "atr_stop_multiple": 2.0})
    # At the no-chase price, R:R to T2 should be >= ~1.8 (or capped earlier by zone+1ATR)
    rr = (lv.target2 - lv.no_chase_above) / (lv.no_chase_above - lv.stop)
    assert rr >= 1.8 - 0.02


def test_rejects_wide_risk():
    lv = compute_levels(_ctx(atr=200.0, supports=[], resistances=[], last_swing_low=None),
                        {"min_rr_t2": 1.8, "max_risk_pct_per_setup": 8.0, "atr_stop_multiple": 2.0})
    assert not lv.valid and any("exceeds max" in r for r in lv.rejections)


def test_tick_rounding():
    assert rtick(1234.567) == 1234.55
    assert rtick(1234.567, "down") == 1234.55
    assert rtick(1234.51, "up") == 1234.55


def test_position_size_spec_example():
    ps = position_size(1_000_000, 1.0, 1240.0, 1190.0, targets=[1290.0, 1340.0])
    assert ps.risk_per_share == 50.0
    assert ps.quantity == 200
    assert ps.max_loss == 10_000.0
    assert ps.capital_required == 248_000.0
    assert ps.potential_profits == [10_000.0, 20_000.0]


def test_position_size_caps():
    ps = position_size(100_000, 5.0, 1000.0, 999.0)
    assert ps.quantity == 100 and ps.capped_by == "capital"
    ps2 = position_size(1_000_000, 1.0, 1000.0, 990.0, max_position_pct=10)
    assert ps2.quantity == 100 and ps2.capped_by == "max_position_pct"
    with pytest.raises(ValueError):
        position_size(1_000_000, 1.0, 1000.0, 1010.0)
