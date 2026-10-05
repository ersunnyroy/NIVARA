from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from app.data.types import FuturesRow, OptionRow
from app.fno.analytics import (
    OI_CAVEAT,
    FnoSnapshotResult,
    black76_price,
    black_scholes_price,
    classify_buildup,
    compute_basis,
    compute_max_pain,
    fno_score,
    fno_snapshot,
    futures_analytics,
    implied_volatility,
    iv_percentile,
    option_chain_analytics,
    time_to_expiry_years,
)

D = date(2026, 10, 5)
EXP = date(2026, 10, 27)
EXP2 = date(2026, 11, 24)


def opt(strike, typ, oi, change_oi=0, volume=100, close=10.0, d=D, expiry=EXP, und=1000.0):
    return OptionRow("ABC", "STO", d, expiry, float(strike), typ, close, close, und, oi, change_oi, volume)


def fut(close, oi, change_oi, volume=1000, d=D, expiry=EXP, und=None):
    return FuturesRow("ABC", "STF", d, expiry, None, None, None, close, close, und, oi, change_oi, volume, 500)


# ---------------------------------------------------------------- buildup


@pytest.mark.parametrize(
    ("price", "oi", "expected"),
    [
        (2.1, 8.4, "long_buildup"),
        (-2.1, 8.4, "short_buildup"),
        (2.1, -8.4, "short_covering"),
        (-2.1, -8.4, "long_unwinding"),
        (0.2, 8.4, "neutral"),
        (2.1, 1.0, "neutral"),
    ],
)
def test_buildup_quadrants(price, oi, expected):
    r = classify_buildup(price, oi, 1.6)
    assert r.buildup == expected
    assert r.interpretation.endswith(OI_CAVEAT)


def test_buildup_wording_and_confidence():
    r = classify_buildup(2.1, 8.4, 1.6)
    assert r.interpretation.startswith("Price ↑ 2.1%, OI ↑ 8.4%, volume 1.6× avg → Long buildup")
    assert r.confidence == "high"
    sc = classify_buildup(1.0, -3.0, None)
    assert "Possible short covering" in sc.interpretation
    assert sc.confidence == "low"
    # large moves but no volume confirmation -> capped at medium
    assert classify_buildup(3.0, 10.0, 1.0).confidence == "medium"
    assert classify_buildup(3.0, 10.0, None).confidence == "medium"


def test_buildup_missing_inputs():
    r = classify_buildup(None, 5.0)
    assert r.buildup is None and r.missing
    assert OI_CAVEAT in r.interpretation


# ---------------------------------------------------------------- option chain


def _chain():
    # strikes 90/100/110 (scaled), hand-computed max pain below
    return [
        opt(90, "CE", 100, change_oi=10, volume=50),
        opt(100, "CE", 300, change_oi=60, volume=200),
        opt(110, "CE", 500, change_oi=120, volume=300),
        opt(90, "PE", 400, change_oi=90, volume=100),
        opt(100, "PE", 200, change_oi=40, volume=150),
        opt(110, "PE", 50, change_oi=-5, volume=20),
    ]


def test_max_pain_hand_computed():
    # K=90 : CE 0 ; PE 200*10 + 50*20 = 3000             -> 3000
    # K=100: CE 100*10 = 1000 ; PE 50*10 = 500             -> 1500
    # K=110: CE 100*20 + 300*10 = 5000 ; PE 0              -> 5000
    assert compute_max_pain(_chain()) == 100.0


def test_pcr_and_support_resistance():
    a = option_chain_analytics(_chain(), underlying_price=103.0)
    assert a.pcr_oi == pytest.approx(650 / 900, abs=1e-4)
    assert a.pcr_volume == pytest.approx(270 / 550, abs=1e-4)
    assert a.call_resistance == 110.0
    assert [s.strike for s in a.call_resistance_top] == [110.0, 100.0, 90.0]
    assert a.put_support == 90.0
    assert [s.strike for s in a.put_support_top] == [90.0, 100.0, 110.0]
    assert a.call_writing_top[0].strike == 110.0
    assert a.put_writing_top[0].strike == 90.0
    assert a.atm_strike == 100.0
    assert a.max_pain == 100.0
    json.dumps(asdict(a), default=str)


def test_pcr_none_when_no_calls():
    a = option_chain_analytics([opt(100, "PE", 10)], underlying_price=100.0)
    assert a.pcr_oi is None
    assert any("CE OI is zero" in m for m in a.missing)


# ---------------------------------------------------------------- IV


@pytest.mark.parametrize("typ", ["CE", "PE"])
def test_iv_round_trip_black_scholes(typ):
    t = 30 / 365
    p = black_scholes_price(1000.0, 1020.0, t, 0.065, 0.25, typ)
    r = implied_volatility(p, 1000.0, 1020.0, t, typ, model="black_scholes")
    assert r.iv == pytest.approx(0.25, abs=1e-4)


def test_iv_round_trip_black76():
    t = 20 / 365
    p = black76_price(1005.0, 1000.0, t, 0.065, 0.25, "CE")
    assert implied_volatility(p, 1005.0, 1000.0, t, "CE", model="black76").iv == pytest.approx(0.25, abs=1e-4)


def test_iv_none_below_intrinsic_and_zero_premium():
    t = 30 / 365
    r = implied_volatility(50.0, 1100.0, 1000.0, t, "CE", model="black_scholes")  # intrinsic ~105
    assert r.iv is None and "below intrinsic" in r.note
    assert implied_volatility(0.0, 1000.0, 1000.0, t, "CE").iv is None


def test_time_to_expiry():
    assert time_to_expiry_years(D, EXP) == pytest.approx(22 / 365)
    assert time_to_expiry_years(EXP, EXP) == 0.0


def test_iv_percentile():
    r = iv_percentile(0.3, [0.2] * 10)
    assert r.value is None and "insufficient" in r.note
    hist = [0.1 + i * 0.01 for i in range(40)]  # 0.10 .. 0.49
    assert iv_percentile(0.3, hist).value == pytest.approx(50.0)


# ---------------------------------------------------------------- futures


def test_basis_and_annualised():
    b = compute_basis(1010.0, 1000.0, 20)
    assert b["basis"] == 10.0
    assert b["basis_pct"] == pytest.approx(1.0)
    assert b["annualised_basis_pct"] == pytest.approx(1.0 * 365 / 20, abs=1e-3)
    assert b["implied_carry_rate"] == pytest.approx(math.log(1.01) * 365 / 20, abs=1e-5)
    assert compute_basis(1010.0, 1000.0, 0)["annualised_basis_pct"] is None
    assert compute_basis(1010.0, None, 5)["basis"] is None


def test_near_month_and_rollover():
    rows = [fut(1010.0, 1000, 100, expiry=EXP), fut(1020.0, 500, 200, expiry=EXP2)]
    fa = futures_analytics(rows, D, 1000.0)
    assert fa.near.expiry == EXP and not fa.in_rollover_window
    assert fa.oi == 1000 and fa.oi_change_pct == pytest.approx(100 / 900 * 100, abs=1e-3)
    assert fa.next is None
    d_roll = EXP - timedelta(days=2)
    rows2 = [fut(1010.0, 1000, -300, d=d_roll), fut(1020.0, 800, 500, d=d_roll, expiry=EXP2)]
    fa2 = futures_analytics(rows2, d_roll, 1000.0)
    assert fa2.in_rollover_window and fa2.oi_basis == "combined_all_expiries"
    assert fa2.oi == 1800 and fa2.change_oi == 200
    assert fa2.next is not None and fa2.next.expiry == EXP2


# ---------------------------------------------------------------- snapshot + score


def test_snapshot_and_score():
    frows = [fut(1000.0 + i, 10_000, 0, volume=1000, d=D - timedelta(days=30 - i)) for i in range(25)]
    frows.append(fut(1030.0, 11_000, 1_000, volume=2000))  # +~0.6% vs 1024 , OI +10%
    t = time_to_expiry_years(D, EXP)
    orows = []
    for k in (950, 1000, 1050, 1100):
        for typ in ("CE", "PE"):
            px = black76_price(1030.0, k, t, 0.065, 0.3, typ)
            oi = {"CE": {1100: 5000}.get(k, 1000), "PE": {950: 4000}.get(k, 800)}[typ]
            orows.append(opt(k, typ, oi, volume=50, close=round(px, 4), und=1025.0))
    snap = fno_snapshot("ABC", D, frows, orows, spot=1025.0, iv_history=[0.2] * 30)
    assert snap.is_fno
    assert snap.fut_price == 1030.0 and snap.basis == pytest.approx(5.0)
    assert snap.buildup == "long_buildup"
    assert snap.call_resistance == 1100.0 and snap.put_support == 950.0
    assert snap.atm_iv == pytest.approx(0.3, abs=1e-3)
    assert snap.iv_percentile == 100.0
    assert OI_CAVEAT in snap.interpretation
    json.dumps(snap.to_dict(), default=str)
    score, reasons, _missing = fno_score(snap)
    assert score is not None and 0 <= score <= 100
    assert any("IV percentile" in r for r in reasons)


def test_non_fno_score_none():
    snap = fno_snapshot("XYZ", D, [], [], spot=100.0)
    assert snap.is_fno is False
    assert fno_score(snap) == (None, [], ["not an F&O stock"])
    assert fno_score(None) == (None, [], ["not an F&O stock"])


def test_score_extreme_pcr_and_iv_caution():
    base = {
        "underlying": "ABC", "date": D, "is_fno": True, "spot": 100.0, "fut_price": 100.5, "basis": 0.5,
        "basis_pct": 0.5, "fut_oi": 1, "fut_oi_change_pct": 1.0, "fut_volume": 1, "pcr_oi": 1.0, "pcr_volume": 1.0,
        "max_pain": 100.0, "call_resistance": 110.0, "put_support": 90.0, "atm_iv": 0.3, "iv_percentile": 50.0,
        "buildup": "neutral", "interpretation": None,
    }  # fmt: skip
    healthy, _, _ = fno_score(FnoSnapshotResult(**base))
    extreme, reasons, _ = fno_score(FnoSnapshotResult(**{**base, "pcr_oi": 1.8, "iv_percentile": 95.0}))
    assert extreme < healthy
    assert any("contrarian" in r for r in reasons)
    sb, _, _ = fno_score(FnoSnapshotResult(**{**base, "buildup": "short_buildup"}))
    assert sb < healthy
