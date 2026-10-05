"""FIFO lot accounting tests (hand-computed)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from app.portfolio.lots import CorpActionIn, TxnIn, average_cost, build_lots


def buy(i, qty, px, d, sym="INFY", charges=0, stt=0, seg="delivery", **kw):
    return TxnIn(i, sym, "BUY", D(qty), D(px), d, D(charges), D(stt), seg, **kw)


def sell(i, qty, px, d, sym="INFY", charges=0, stt=0, seg="delivery"):
    return TxnIn(i, sym, "SELL", D(qty), D(px), d, D(charges), D(stt), seg)


def test_multiple_purchases_average_and_fifo_sell():
    txns = [
        buy(1, 100, 1000, date(2025, 1, 2), charges="118.74", stt=100),
        buy(2, 100, 1100, date(2025, 2, 3), charges="130.6", stt=110),
    ]
    led = build_lots(txns)
    avg = average_cost(led.open_lots)
    # (100 x 1000 + 100 x 1100) / 200 = 1050
    assert avg.quantity == 200
    assert avg.average_price == D(1050)
    # incl. charges: (2,10,000 + 118.74 + 130.60) / 200 = 1051.2467
    assert avg.total_cost_incl_charges == D("210249.34")

    led = build_lots([*txns, sell(3, 50, 1200, date(2025, 3, 3), charges=60, stt=60)])
    assert len(led.matches) == 1
    m = led.matches[0]
    # FIFO: all 50 from lot 1
    assert m.lot_id == "1" and m.buy_txn_id == 1 and m.sell_txn_id == 3
    assert m.quantity == 50
    assert m.purchase_value == D(50000)
    assert m.sale_value == D(60000)
    assert m.buy_charges_alloc == D("59.37")  # 118.74 x 50/100
    assert m.buy_stt_alloc == D(50)
    assert m.sell_charges_alloc == D(60)
    assert m.stt_alloc == D(110)  # 50 buy + 60 sell
    assert m.holding_days == 60
    assert m.acquired_date == date(2025, 1, 2)
    # remaining: 50 @ 1000 + 100 @ 1100 -> avg 1,60,000 / 150 = 1066.67
    avg = average_cost(led.open_lots)
    assert avg.quantity == 150
    assert avg.average_price.quantize(D("0.01")) == D("1066.67")
    lot1 = led.open_lots[0]
    assert lot1.remaining_quantity == 50 and lot1.buy_charges == D("59.37")


def test_partial_sell_across_lots_with_prorata_sell_charges():
    led = build_lots([
        buy(1, 100, 1000, date(2025, 1, 2), charges=120, stt=100),
        buy(2, 100, 1100, date(2025, 2, 3), charges=130, stt=110),
        sell(3, 150, 1200, date(2025, 3, 3), charges=150, stt=180),
    ])
    m1, m2 = led.matches
    assert (m1.lot_id, m1.quantity, m1.purchase_value) == ("1", 100, D(100000))
    assert (m2.lot_id, m2.quantity, m2.purchase_value) == ("2", 50, D(55000))
    # sell charges 150 split 100/50 of 150 -> 100 and 50
    assert m1.sell_charges_alloc == D(100) and m2.sell_charges_alloc == D(50)
    assert m1.sell_stt_alloc == D(120) and m2.sell_stt_alloc == D(60)
    # lot 1 fully consumed -> all its buy charges; lot 2 half -> 65
    assert m1.buy_charges_alloc == D(120) and m2.buy_charges_alloc == D(65)
    assert led.quantity_held("INFY") == 50
    assert len(led.lots) == 2 and len(led.open_lots) == 1


def test_charge_allocation_sums_exactly():
    led = build_lots([
        buy(1, 1, 10, date(2025, 1, 2)),
        buy(2, 1, 10, date(2025, 1, 3)),
        buy(3, 1, 10, date(2025, 1, 4)),
        sell(4, 3, 11, date(2025, 2, 3), charges=10, stt=1),
    ])
    assert sum(m.sell_charges_alloc for m in led.matches) == D(10)
    assert sum(m.sell_stt_alloc for m in led.matches) == D(1)


def test_oversell_raises():
    with pytest.raises(ValueError, match="Oversell"):
        build_lots([buy(1, 10, 100, date(2025, 1, 2)), sell(2, 11, 100, date(2025, 1, 3))])
    with pytest.raises(ValueError, match="Oversell"):
        build_lots([sell(1, 1, 100, date(2025, 1, 3))])


def test_split_fv_10_to_2():
    led = build_lots(
        [buy(1, 100, 1000, date(2023, 1, 10), charges=50), sell(2, 500, 250, date(2024, 6, 3))],
        [CorpActionIn("INFY", date(2024, 1, 15), "split", D(10), D(2))],
    )
    lot = led.lots[0]
    # factor 10/2 = 5: 100 -> 500 shares, cost 1000 -> 200; date unchanged; charges unchanged
    assert lot.quantity == 500
    assert lot.cost_per_share == D(200)
    assert lot.acquired_date == date(2023, 1, 10)
    assert "Split" in lot.adjustments[0]
    m = led.matches[0]
    assert m.quantity == 500
    assert m.purchase_value == D(100000)  # total cost preserved
    assert m.sale_value == D(125000)
    assert m.buy_charges_alloc == D(50)
    assert m.acquired_date == date(2023, 1, 10)


def test_bonus_1_for_1_creates_zero_cost_lot_with_new_date():
    led = build_lots(
        [buy(1, 100, 1000, date(2024, 1, 10)), sell(2, 150, 600, date(2024, 7, 1))],
        [CorpActionIn("INFY", date(2024, 6, 3), "bonus", D(1), D(1))],
    )
    bonus = [lot for lot in led.lots if lot.is_bonus]
    assert len(bonus) == 1
    b = bonus[0]
    assert b.quantity == 100 and b.cost_per_share == 0 and b.acquired_date == date(2024, 6, 3)
    assert b.buy_txn_id is None
    # original lot untouched by bonus
    orig = led.lots[0]
    assert orig.quantity == 100 and orig.cost_per_share == D(1000)
    m1, m2 = led.matches
    assert (m1.lot_id, m1.quantity, m1.acquired_date) == ("1", 100, date(2024, 1, 10))
    assert m2.is_bonus and m2.quantity == 50 and m2.purchase_value == 0
    assert m2.acquired_date == date(2024, 6, 3) and m2.holding_days == 28
    assert led.quantity_held("INFY") == 50


def test_bonus_floor_on_total_holding():
    # 3 shares, bonus 1:2 -> floor(1.5) = 1 bonus share
    led = build_lots(
        [buy(1, 2, 100, date(2024, 1, 10)), buy(2, 1, 100, date(2024, 2, 10))],
        [CorpActionIn("INFY", date(2024, 6, 3), "bonus", D(1), D(2))],
    )
    assert [lot.quantity for lot in led.lots if lot.is_bonus] == [1]


def test_buy_on_ex_date_not_entitled():
    led = build_lots(
        [buy(1, 10, 100, date(2024, 6, 3))],
        [CorpActionIn("INFY", date(2024, 6, 3), "split", D(10), D(1))],
    )
    assert led.lots[0].quantity == 10


def test_intraday_same_day_matching():
    led = build_lots([
        buy(1, 100, 900, date(2025, 1, 2)),  # delivery holding
        sell(3, 50, 1010, date(2025, 3, 3), seg="intraday", charges=20, stt=12),  # listed before buy: short-cover
        buy(2, 50, 1000, date(2025, 3, 3), seg="intraday", charges=10),
        buy(4, 10, 1000, date(2025, 3, 3)),  # same-day delivery buy
        sell(5, 10, 1005, date(2025, 3, 3)),  # delivery sell -> FIFO oldest delivery lot (txn 1)
    ])
    intraday = [m for m in led.matches if m.segment == "intraday"]
    assert len(intraday) == 1
    m = intraday[0]
    assert m.lot_id == "2" and m.quantity == 50 and m.holding_days == 0
    assert m.trading_pnl == D(500) - D(30)  # 50 x 10 gross - 10 buy - 20 sell
    deliv = [m for m in led.matches if m.segment == "delivery"]
    assert deliv[0].lot_id == "1" and deliv[0].quantity == 10
    assert led.quantity_held("INFY") == 100  # 90 from lot 1 + 10 from lot 4


def test_intraday_oversell_and_carry_over():
    with pytest.raises(ValueError, match="intraday"):
        build_lots([buy(1, 100, 900, date(2025, 1, 2)), sell(2, 5, 1000, date(2025, 1, 3), seg="intraday")])
    led = build_lots([buy(1, 10, 100, date(2025, 1, 2), seg="intraday"), sell(2, 10, 120, date(2025, 1, 6))])
    assert led.matches[0].segment == "delivery"
    assert "not squared off" in led.lots[0].adjustments[0]


def test_invalid_segment():
    with pytest.raises(ValueError, match="delivery/intraday"):
        build_lots([buy(1, 1, 1, date(2025, 1, 2), seg="futures")])
