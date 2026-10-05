from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.analytics.config import DEFAULTS
from app.analytics.evaluate import ExternalInputs, LookAheadError, evaluate
from app.analytics.regime import RegimeInputs, compute_regime
from app.analytics.sector import rank_sectors, rs_percentiles, stock_relative_strength
from tests.synthetic import make_bars


def _series(n=300, drift=0.001, seed=1):
    return make_bars(n=n, drift=drift, seed=seed)["close"]


def test_regime_bullish_vs_bearish():
    bull = compute_regime(RegimeInputs(nifty=_series(drift=0.002), banknifty=_series(drift=0.002, seed=2),
                                       vix=pd.Series(np.linspace(18, 12, 300)), advances=1500, declines=600,
                                       pct_above_50dma=68, pct_above_200dma=70, flows=[("FII", 3000), ("DII", 2000)]))
    bear = compute_regime(RegimeInputs(nifty=_series(drift=-0.002), banknifty=_series(drift=-0.002, seed=2),
                                       vix=pd.Series(np.linspace(12, 24, 300)), advances=500, declines=1600,
                                       pct_above_50dma=25, pct_above_200dma=30, flows=[("FII", -6000), ("DII", 1000)]))
    assert bull.score > 20 and bull.regime in ("BULLISH", "STRONG BULLISH")
    assert bear.score < -20 and bear.regime in ("BEARISH", "STRONG BEARISH")
    assert bull.recommended_exposure_pct > bear.recommended_exposure_pct
    assert 0 <= bull.confidence <= 95
    assert len(bull.components) >= 5  # never a single indicator
    assert any("Global" in m for m in bull.missing_inputs)


def test_regime_with_no_data_is_neutral_zero_confidence():
    r = compute_regime(RegimeInputs(nifty=None))
    assert r.regime == "NEUTRAL" and r.confidence == 0.0


def test_sector_ranking_and_rs():
    closes = {"Nifty 50": _series(seed=3), "Nifty IT": _series(drift=0.003, seed=4),
              "Nifty Metal": _series(drift=-0.002, seed=5)}
    rows = rank_sectors(closes)
    assert next(r.index_name for r in rows) == "Nifty IT"
    assert rows[0].rank == 1 and rows[0].score > rows[-1].score
    rs = stock_relative_strength(_series(drift=0.003, seed=6), closes["Nifty 50"])
    assert set(rs) == {"1w", "1m", "3m", "6m"}
    pr = rs_percentiles({"A": {"1w": 1, "1m": 5, "3m": 10, "6m": 20}, "B": {"1w": -1, "1m": -5, "3m": -10, "6m": -20}})
    assert pr["A"] > pr["B"]


def test_evaluate_rejects_lookahead():
    bars = make_bars(n=260)
    with pytest.raises(LookAheadError):
        evaluate("X", bars, date(2024, 1, 5), ExternalInputs(), DEFAULTS["scoring_weights"],
                 DEFAULTS["risk_limits"], DEFAULTS["exclusions"])


def test_evaluate_produces_explained_levels():
    bars = make_bars(n=320, drift=0.002, seed=11)
    as_of = bars.index[-1].date()
    ev = evaluate("X", bars, as_of, ExternalInputs(regime="BULLISH", rs_rating=80), DEFAULTS["scoring_weights"],
                  DEFAULTS["risk_limits"], DEFAULTS["exclusions"])
    assert ev.levels is not None and ev.score is not None
    assert ev.invalidation.startswith("Setup becomes invalid")
    assert ev.why_not  # always at least one risk
    assert ev.action in ("BUY", "WAIT", "AVOID")


def test_evaluate_insufficient_history():
    bars = make_bars(n=60)
    ev = evaluate("X", bars, bars.index[-1].date(), ExternalInputs(), DEFAULTS["scoring_weights"],
                  DEFAULTS["risk_limits"], DEFAULTS["exclusions"])
    assert ev.rejected and "Insufficient history" in ev.rejection_reasons[0]
