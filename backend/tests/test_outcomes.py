import pandas as pd

from app.recommendations.outcomes import TradePlan, simulate

PLAN = TradePlan(entry_low=100, entry_high=102, stop=96, target1=106, target2=110, target3=115,
                 trailing_after_t1=101, holding_max=10)


def _bars(rows):
    idx = pd.bdate_range("2026-01-05", periods=len(rows))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def test_entry_then_target2():
    o = simulate(PLAN, _bars([(103, 104, 101.5, 103), (103, 107, 102, 106), (106, 111, 105, 110)]))
    assert o.entry_price == 102 and o.status == "target2"
    assert o.t1_hit_date is not None and o.exit_price == 110
    assert o.return_pct == round(100 * (110 / 102 - 1), 3)


def test_stop_checked_before_target_same_bar():
    o = simulate(PLAN, _bars([(101, 102, 100, 101), (101, 112, 95, 100)]))
    assert o.status == "stopped" and o.exit_price == 96


def test_gap_through_stop_exits_at_open():
    o = simulate(PLAN, _bars([(101, 102, 100, 101), (93, 94, 92, 93)]))
    assert o.status == "stopped" and o.exit_price == 93


def test_trailing_after_t1():
    o = simulate(PLAN, _bars([(101, 102, 100, 101), (102, 107, 101.5, 106), (105, 105, 100.5, 101)]))
    assert o.status == "target1" and o.exit_price == 101  # trailed stop at 101


def test_not_triggered_and_invalidated():
    o = simulate(PLAN, _bars([(108, 109, 104, 108)] * 4))
    assert o.status == "not_triggered" and o.entry_price is None
    o2 = simulate(PLAN, _bars([(95, 96, 94, 95)]))
    assert o2.status == "invalidated"


def test_expiry():
    rows = [(101, 102, 100, 101)] + [(101, 103, 99, 102)] * 12
    o = simulate(PLAN, _bars(rows))
    assert o.status == "expired" and o.sessions_held == 10 and o.exit_price == 102


def test_mfe_mae():
    o = simulate(PLAN, _bars([(101, 102, 100, 101), (101, 105, 98, 104)]))
    assert o.mfe_pct > 0 and o.mae_pct < 0 and o.status == "open"
