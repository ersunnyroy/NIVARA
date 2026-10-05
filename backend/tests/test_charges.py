"""ChargesEngine tests. Expected values are hand-computed in comments (rates from app.tax.defaults)."""
from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal as D

import pytest

from app.tax.charges import (
    ChargeSchedule,
    ChargesEngine,
    OrderIn,
    compute_charges,
    select_schedule,
)
from app.tax.defaults import DEFAULT_SCHEDULE_NAME, default_charge_schedules

ENGINE = ChargesEngine.default()
DAY = date(2025, 6, 2)


def test_delivery_buy_100_at_1000_nse_components():
    b = ENGINE.compute("equity_delivery", "BUY", D(100), D(1000), "NSE", trade_date=DAY)
    # turnover            = 100 x 1000                     = 1,00,000
    # brokerage           = zero                           = 0
    # STT 0.1% buy        = 100.00 (rupee rounding: 100)
    # NSE txn 0.00307%    = 3.07
    # SEBI 10/crore       = 1,00,000 x 10 / 1,00,00,000    = 0.10
    # stamp 0.015% buy    = 15.00
    # GST 18% on (0 + 3.07 + 0.10 + 0 IPFT)                 = 0.5706 -> 0.57
    # DP                  = 0 (buy)
    assert b.turnover == D(100000)
    assert b.brokerage == 0
    assert b.stt == D(100)
    assert b.exchange_txn == D("3.07")
    assert b.sebi == D("0.10")
    assert b.stamp == D(15)
    assert b.ipft == 0
    assert b.gst == D("0.5706")
    assert b.dp == 0
    assert b.total == D("118.7406")  # full precision
    r = b.rounded()
    assert r.gst == D("0.57")
    assert r.total == D("118.74")  # 100 + 3.07 + 0.10 + 15 + 0.57
    assert b.is_estimate is True
    assert b.schedule_name == DEFAULT_SCHEDULE_NAME
    assert b.to_dict()["total"] == "118.74"


def test_delivery_sell_100_at_1000_nse_components():
    s = ENGINE.compute("delivery", "SELL", D(100), D(1000), trade_date=DAY)
    # STT 0.1% sell = 100; txn 3.07; SEBI 0.10; stamp 0 (sell); GST 0.5706; DP 15.34 (GST-incl.)
    # total = 100 + 3.07 + 0.10 + 0.5706 + 15.34 = 119.0806 -> 119.08
    assert s.stt == D(100)
    assert s.stamp == 0
    assert s.dp == D("15.34")
    assert s.total == D("119.0806")
    assert s.rounded().total == D("119.08")
    assert s.total_excl_stt == D("19.0806")


def test_intraday_brokerage_cap_and_sell_only_stt():
    big = ENGINE.compute("equity_intraday", "BUY", D(1000), D(500), trade_date=DAY)
    # turnover 5,00,000; 0.03% = 150 -> capped at 20
    # txn 0.00307% = 15.35; SEBI = 0.50; stamp 0.003% = 15; STT 0 on buy
    # GST = 18% x (20 + 15.35 + 0.50) = 6.453
    assert big.brokerage == D(20)
    assert big.stt == 0
    assert big.exchange_txn == D("15.35")
    assert big.sebi == D("0.5")
    assert big.stamp == D(15)
    assert big.gst == D("6.453")
    assert big.rounded().total == D("57.30")  # 20 + 15.35 + 0.50 + 15 + 6.45

    small = ENGINE.compute("intraday", "BUY", D(10), D(500), trade_date=DAY)
    # turnover 5,000 -> 0.03% = 1.50 (below cap)
    assert small.brokerage == D("1.5")

    sell = ENGINE.compute("intraday", "SELL", D(1000), D(500), trade_date=DAY)
    # STT 0.025% sell = 125; no stamp; no DP
    assert sell.stt == D(125)
    assert sell.stamp == 0 and sell.dp == 0
    assert sell.rounded().total == D("167.30")  # 20 + 125 + 15.35 + 0.50 + 6.45


def test_bse_exchange_rate():
    b = ENGINE.compute("equity_delivery", "BUY", D(100), D(1000), "BSE", trade_date=DAY)
    # BSE 0.00375% of 1,00,000 = 3.75; GST = 18% x (3.75 + 0.10) = 0.693
    assert b.exchange_txn == D("3.75")
    assert b.gst == D("0.693")
    assert b.rounded().total == D("119.54")  # 100 + 3.75 + 0.10 + 15 + 0.69


def test_unknown_exchange_rate_raises():
    with pytest.raises(ValueError, match="BSE"):
        ENGINE.compute("futures", "SELL", D(75), D(24000), "BSE", trade_date=DAY)


def test_futures_stt_switches_on_2026_04_01():
    before = ENGINE.compute("futures", "SELL", D(75), D(24000), trade_date=date(2026, 3, 31))
    after = ENGINE.compute("futures", "SELL", D(75), D(24000), trade_date=date(2026, 4, 1))
    # turnover 18,00,000
    # before: STT 0.02% = 360 ; after (Budget 2026): 0.05% = 900
    assert before.stt == D(360)
    assert after.stt == D(900)
    # brokerage 0.03% = 540 -> cap 20; NSE txn 0.00183% = 32.94; SEBI 1.80
    # GST = 18% x (20 + 32.94 + 1.80) = 9.8532
    assert before.brokerage == D(20)
    assert before.exchange_txn == D("32.94")
    assert before.gst == D("9.8532")
    assert before.rounded().total == D("424.59")  # 20 + 360 + 32.94 + 1.80 + 9.85
    assert after.rounded().total == D("964.59")
    buy = ENGINE.compute("futures", "BUY", D(75), D(24000), trade_date=date(2026, 4, 1))
    assert buy.stt == 0
    assert buy.stamp == D(36)  # 0.002% of 18,00,000


def test_options_stt_on_premium_dated_and_rupee_rounding():
    before = ENGINE.compute("options", "SELL", D(75), D(200), trade_date=date(2026, 3, 31))
    after = ENGINE.compute("options", "SELL", D(75), D(200), trade_date=date(2026, 4, 1))
    # premium turnover = 75 x 200 = 15,000
    # before: 0.1% = 15 ; after: 0.15% = 22.50 -> rounded to nearest rupee (HALF_UP) = 23
    assert before.stt == D(15)
    assert after.stt == D(23)
    # flat brokerage 20; txn 0.03553% = 5.3295; SEBI 0.015; GST 18% x 25.3445 = 4.56201
    assert before.brokerage == D(20)
    assert before.exchange_txn == D("5.3295")
    assert before.gst == D("4.56201")
    assert any("premium" in n for n in before.notes)


def test_stt_rounding_configurable_paise():
    sched = copy.deepcopy(default_charge_schedules()[1])
    sched["rates"]["stt_rounding"] = "paise"
    out = compute_charges("options", "SELL", D(75), D(200), trade_date=date(2026, 4, 1), schedule=sched)
    assert out.stt == D("22.50")


def test_stt_rupee_rounding_small_delivery_trade():
    b = ENGINE.compute("equity_delivery", "BUY", D(7), D("333.33"), trade_date=DAY)
    # turnover 2,333.31 x 0.1% = 2.33331 -> 2 (nearest rupee)
    assert b.stt == D(2)


def test_dp_once_per_scrip_per_day():
    orders = [
        OrderIn("INFY", "delivery", "SELL", D(10), D(1500), DAY),
        OrderIn("INFY", "delivery", "SELL", D(5), D(1501), DAY),  # same scrip same day -> no DP
        OrderIn("TCS", "delivery", "SELL", D(1), D(3500), DAY),  # different scrip -> DP
        OrderIn("INFY", "delivery", "SELL", D(5), D(1490), date(2025, 6, 3)),  # next day -> DP
        OrderIn("INFY", "delivery", "BUY", D(5), D(1490), DAY),  # buys never pay DP
        OrderIn("INFY", "intraday", "SELL", D(5), D(1490), DAY),  # intraday: no DP
    ]
    out = ENGINE.compute_orders(orders)
    assert [o.dp for o in out] == [D("15.34"), 0, D("15.34"), D("15.34"), 0, 0]
    assert any("already applied" in n for n in out[1].notes)


def test_round_trip():
    rt = ENGINE.compute_round_trip("equity_delivery", D(100), D(1000), D(1100), buy_date=DAY)
    # buy = 118.7406 ; sell on 1,10,000: STT 110 + txn 3.377 + SEBI 0.11 + GST 0.62766 + DP 15.34 = 129.45466
    assert rt.buy.total == D("118.7406")
    assert rt.sell.total == D("129.45466")
    assert rt.total == D("248.19526")
    assert rt.stt_total == D(210)


def test_schedule_selection_by_date_and_fallback():
    schedules = default_charge_schedules()
    s, notes = select_schedule(schedules, date(2026, 3, 31))
    assert s.effective_to == date(2026, 3, 31) and notes == []
    s, notes = select_schedule(schedules, date(2026, 4, 1))
    assert s.effective_from == date(2026, 4, 1)
    with pytest.raises(ValueError, match="No charge schedule covers"):
        select_schedule(schedules, date(2024, 1, 1), strict=True)
    s, notes = select_schedule(schedules, date(2024, 1, 1))
    assert s.effective_from == date(2024, 10, 1) and "nearest" in notes[0]


def test_default_schedules_shape_and_json():
    a, b = default_charge_schedules()
    json.dumps(a["rates"])  # JSON-serialisable (Decimals as strings)
    for seg in ("equity_delivery", "equity_intraday"):
        assert a["rates"][seg] == b["rates"][seg]
    assert a["rates"]["futures"]["stt_sell_pct"] == "0.02"
    assert b["rates"]["futures"]["stt_sell_pct"] == "0.05"
    assert a["rates"]["options"]["stt_sell_pct"] == "0.1"
    assert b["rates"]["options"]["stt_sell_pct"] == "0.15"
    assert a["source_url"] == "https://zerodha.com/charges"
    assert "configure if levied" in a["notes"]
    assert ChargeSchedule.coerce(a).covers(date(2025, 1, 1))


def test_invalid_inputs():
    with pytest.raises(ValueError):
        ENGINE.compute("equity_delivery", "HOLD", D(1), D(1), trade_date=DAY)
    with pytest.raises(ValueError):
        ENGINE.compute("commodity", "BUY", D(1), D(1), trade_date=DAY)
    with pytest.raises(ValueError):
        ENGINE.compute("equity_delivery", "BUY", D(0), D(1), trade_date=DAY)
