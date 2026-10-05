from app.portfolio.monitor import PositionState, evaluate_position


def _p(**kw):
    base = dict(symbol="ABC", quantity=100, avg_cost=1200.0, cmp=1285.0, stop=1150.0, target1=1320.0, target2=1400.0,
                ema20=1260.0, ema50=1230.0, atr=25.0, rsi=60.0, supertrend_dir=1.0, macd_below_signal=False,
                regime="BULLISH")
    base.update(kw)
    return PositionState(**base)


def test_spec_example_pnl_and_distances():
    r = evaluate_position(_p())
    assert r.pnl == 8500.0 and r.pnl_pct == 7.08
    assert r.distance_to_target_pct == round(100 * (1320 - 1285) / 1285, 2)
    assert r.action == "TRAIL STOP" and r.suggested_trailing_stop is not None


def test_stop_hit_exits():
    r = evaluate_position(_p(cmp=1140.0))
    assert r.action == "EXIT" and any(s["code"] == "stop_hit" for s in r.sell_signals)


def test_target1_partial_profit():
    r = evaluate_position(_p(cmp=1325.0))
    assert r.action == "PARTIAL PROFIT" and r.partial_exit_pct == 30


def test_target2_partial_profit_larger():
    r = evaluate_position(_p(cmp=1405.0))
    assert r.action == "PARTIAL PROFIT" and r.partial_exit_pct == 50


def test_technical_deterioration_plus_regime_exit():
    r = evaluate_position(_p(cmp=1190.0, ema50=1210.0, supertrend_dir=-1.0, macd_below_signal=True,
                             regime="BEARISH"))
    assert r.action == "EXIT"
    codes = {s["code"] for s in r.sell_signals}
    assert {"technical_deterioration", "regime_changed"} <= codes


def test_negative_news_while_losing_exits():
    r = evaluate_position(_p(cmp=1180.0, worst_recent_news=-0.6, negative_news_headline="SEBI order"))
    assert r.action == "EXIT"


def test_add_only_on_dip_when_trend_intact():
    r = evaluate_position(_p(cmp=1190.0, ema50=1150.0))
    assert r.action == "ADD ONLY ON DIP"


def test_missing_levels_waits_and_explains():
    r = evaluate_position(_p(stop=None, target1=None, target2=None, levels_source="none", cmp=1210.0))
    assert r.action == "WAIT" and any("No stop/target" in x for x in r.reasons)


def test_better_opportunity_signal():
    r = evaluate_position(_p(cmp=1250.0, current_score=40, best_alternative_score=85))
    assert any(s["code"] == "better_opportunity" for s in r.sell_signals)
