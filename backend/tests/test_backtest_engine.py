import pandas as pd
import pytest

from app.analytics.evaluate import ExternalInputs, LookAheadError, evaluate
from app.backtesting.engine import Backtester, BacktestParams
from tests.synthetic import make_bars


def _frames(n=420):
    return {f"S{i}": make_bars(n=n, drift=0.0015 + 0.0004 * i, seed=20 + i, start_date="2024-06-03") for i in range(6)}


def _index(n=420):
    return {"Nifty 50": make_bars(n=n, drift=0.0007, seed=99, start_date="2024-06-03")["close"]}


def _bt(frames, strategy="combined"):
    idx = _index()
    sess = idx["Nifty 50"].index
    p = BacktestParams(strategy=strategy, start=sess[260].date(), end=sess[-1].date(), universe_size=10,
                       min_turnover_cr=0.0, min_price=1.0, min_score=0.0)
    return Backtester(frames, idx, lambda side, q, px, d: 0.001 * q * px, p).run()


def test_backtest_runs_and_reports_splits():
    res = _bt(_frames())
    m = res["metrics"]
    assert {"overall", "train", "validation", "test"} <= set(m)
    assert res["curve"][0]["equity"] == pytest.approx(1_000_000.0)
    for t in res["trades"]:
        assert t.entry_date > t.signal_date  # next-session fills only
        assert t.charges > 0


def test_future_data_cannot_change_past_decisions():
    frames = _frames()
    base = _bt(frames)
    # Corrupt everything after the cut-off; trades signalled before it must be identical.
    idx = _index()["Nifty 50"].index
    cut = idx[330]
    tampered = {}
    for s, f in frames.items():
        g = f.copy()
        g.loc[g.index > cut, ["open", "high", "low", "close"]] *= 3.0
        tampered[s] = g
    other = _bt(tampered)
    early = lambda res: [(t.symbol, t.signal_date) for t in res["trades"] if pd.Timestamp(t.signal_date) < cut - pd.Timedelta(days=60)]
    assert early(base) == early(other)


def test_evaluate_guard():
    f = make_bars(n=300)
    with pytest.raises(LookAheadError):
        evaluate("X", f, f.index[100].date(), ExternalInputs(), {}, {}, {})
