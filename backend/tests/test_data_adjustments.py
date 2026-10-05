from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.data.adjustments import apply_adjustments, detect_adjustments


def test_detects_split_and_bonus_ignores_noise():
    rows = [
        (date(2026, 9, 1), 1000.0, 990.0),
        (date(2026, 9, 2), 1010.0, 1000.0),
        (date(2026, 9, 3), 205.0, 202.0),  # 1:5 split ex-date: exchange prev close 1010/5
        (date(2026, 9, 4), 206.0, 205.0),
        (date(2026, 9, 7), 104.0, 103.0),  # 1:1 bonus: 206/2
        (date(2026, 9, 8), 105.0, 104.2),  # 0.19% rounding noise, below threshold
        (date(2026, 9, 9), 106.0, None),
    ]
    adj = detect_adjustments(reversed(rows))
    assert [d for d, _ in adj] == [date(2026, 9, 3), date(2026, 9, 7)]
    assert adj[0][1] == pytest.approx(0.2) and adj[1][1] == pytest.approx(0.5)


def test_apply_back_adjusts_prices_and_volume():
    idx = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    df = pd.DataFrame(
        {"open": [1000, 1010, 204], "high": [1020, 1015, 210], "low": [990, 1000, 200], "close": [1010, 1010, 205],
         "volume": [100, 200, 1000]},
        index=idx,
    )
    out = apply_adjustments(df, [(date(2026, 9, 3), 0.2)])
    assert out.loc[date(2026, 9, 2), "close"] == pytest.approx(202.0)
    assert out.loc[date(2026, 9, 1), "volume"] == pytest.approx(500.0)
    assert out.loc[date(2026, 9, 3), "close"] == 205.0 and out.loc[date(2026, 9, 3), "volume"] == 1000.0
    assert df.loc[date(2026, 9, 2), "close"] == 1010  # input untouched


def test_apply_compounds_and_supports_datetime_index():
    df = pd.DataFrame(
        {"open": [100.0] * 3, "high": [100.0] * 3, "low": [100.0] * 3, "close": [100.0] * 3, "volume": [10] * 3},
        index=pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
    )
    out = apply_adjustments(df, [(date(2026, 2, 1), 0.5), (date(2026, 3, 1), 0.5)])
    assert list(out["close"]) == [25.0, 50.0, 100.0]
    assert list(out["volume"]) == [40.0, 20.0, 10.0]
    with pytest.raises(ValueError):
        apply_adjustments(df, [(date(2026, 2, 1), 0.0)])
