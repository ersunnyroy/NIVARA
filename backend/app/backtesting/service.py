"""Persisted backtests: load data from the store, run the engine, save metrics/trades."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.config import MODEL_VERSION, load_config, validate_weights
from app.analytics.sector import BENCHMARK, SECTOR_INDICES
from app.backtesting.engine import STRATEGIES, Backtester, BacktestParams, decimal_charges_fn
from app.core.timeutil import utcnow
from app.models import OHLCV, Backtest, BacktestTrade, Stock
from app.services.portfolio_service import charges_engine
from app.services.prices import bars_bulk, index_series


def create_backtest(db: Session, user_id: int | None, name: str, strategy: str, start: date, end: date,
                    params: dict, universe: str = "liquid_pit") -> Backtest:
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}")
    if end <= start:
        raise ValueError("end must be after start")
    bt = Backtest(user_id=user_id, name=name, strategy=strategy, params=params, universe=universe, start_date=start,
                  end_date=end, status="queued", model_version=MODEL_VERSION, created_at=utcnow())
    db.add(bt)
    db.commit()
    return bt


def execute_backtest(db: Session, backtest_id: int) -> dict:
    bt = db.get(Backtest, backtest_id)
    bt.status = "running"
    db.commit()
    try:
        cfg = load_config(db)
        p = bt.params or {}
        params = BacktestParams(
            strategy=bt.strategy, start=bt.start_date, end=bt.end_date,
            capital=float(p.get("capital", 1_000_000)), risk_pct=float(p.get("risk_pct", 1.0)),
            max_positions=int(p.get("max_positions", 8)), top_n=int(p.get("top_n", 5)),
            slippage_bps=float(p.get("slippage_bps", 10)), universe_size=int(p.get("universe_size", 250)),
            min_score=float(p.get("min_score", cfg["scanner"]["min_score"])),
            weights=validate_weights(cfg["scoring_weights"]), risk_cfg=cfg["risk_limits"], excl_cfg=cfg["exclusions"],
        )
        # Warm-up: indicators need ~1 year before the first signal date.
        load_from = bt.start_date - timedelta(days=430)
        ids = [i for (i,) in db.execute(select(OHLCV.stock_id).where(OHLCV.date == bt.start_date))] or \
              [i for (i,) in db.execute(select(OHLCV.stock_id).where(OHLCV.date >= bt.start_date).distinct())]
        series = {s.id: s.symbol for s in db.scalars(select(Stock).where(Stock.id.in_(ids), Stock.series == "EQ"))}
        frames = bars_bulk(db, list(series), bt.end_date + timedelta(days=60), lookback_days=(bt.end_date - load_from).days + 60)
        frames = {series[k]: v for k, v in frames.items() if k in series}
        idx = index_series(db, [BENCHMARK, "Nifty Bank", "India VIX", *SECTOR_INDICES], bt.end_date + timedelta(days=60),
                           lookback_days=(bt.end_date - load_from).days + 60)
        res = Backtester(frames, idx, decimal_charges_fn(charges_engine(db)), params).run()
        db.query(BacktestTrade).filter(BacktestTrade.backtest_id == bt.id).delete()
        for t in res["trades"]:
            db.add(BacktestTrade(backtest_id=bt.id, symbol=t.symbol, split=t.split, signal_date=t.signal_date,
                                 entry_date=t.entry_date, entry_price=t.entry_price, exit_date=t.exit_date,
                                 exit_price=t.exit_price, quantity=Decimal(t.quantity), gross_pnl=Decimal(str(round(t.gross_pnl, 2))),
                                 charges=Decimal(str(round(t.charges, 2))), net_pnl=Decimal(str(round(t.net_pnl, 2))),
                                 exit_reason=t.exit_reason, holding_sessions=t.holding_sessions, score=t.score))
        bt.metrics = res["metrics"]
        bt.equity_curve = res["curve"]
        bt.splits = {"train_end": res["bounds"][0].isoformat(), "validation_end": res["bounds"][1].isoformat(),
                     "ratios": list(params.split)}
        bt.warnings = res["warnings"]
        bt.status, bt.completed_at = "completed", utcnow()
        db.commit()
        return {"id": bt.id, "status": bt.status, "trades": len(res["trades"])}
    except Exception as e:
        db.rollback()
        bt = db.get(Backtest, backtest_id)
        bt.status, bt.error, bt.completed_at = "failed", f"{type(e).__name__}: {e}"[:2000], utcnow()
        db.commit()
        raise


