"""Market breadth, sector strength and market regime — computed from stored data, then persisted."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.config import load_config
from app.analytics.regime import RegimeInputs, compute_regime
from app.analytics.sector import BENCHMARK, SECTOR_INDICES, rank_sectors
from app.core.timeutil import ist_datetime, utcnow
from app.market_calendar.calendar import CLOSE
from app.models import OHLCV, InstitutionalFlow, MarketBreadth, MarketRegime, Sector, SectorStrength, Stock
from app.repositories.upsert import upsert
from app.services.prices import bars_bulk, index_series

REGIME_INDICES = [BENCHMARK, "Nifty Bank", "India VIX", "Nifty Next 50", "Nifty Financial Services"]


def compute_breadth(db: Session, session: date, universe: str = "nifty500") -> MarketBreadth | None:
    """A/D for all EQ-series stocks that traded; %-above-DMA and 52w highs/lows for the chosen universe."""
    rows = db.execute(select(OHLCV.close, OHLCV.prev_close).join(Stock, Stock.id == OHLCV.stock_id)
                      .where(OHLCV.date == session, Stock.series == "EQ")).all()
    if not rows:
        return None
    adv = sum(1 for c, p in rows if p and c > p)
    dec = sum(1 for c, p in rows if p and c < p)
    unch = len(rows) - adv - dec
    members = [s.id for s in db.scalars(select(Stock)) if universe in (s.index_memberships or [])]
    frames = bars_bulk(db, members, session, lookback_days=400)
    a20 = a50 = a200 = n = hi = lo = 0
    for df in frames.values():
        if df.empty or df.index[-1].date() != session or len(df) < 60:
            continue
        c = df["close"]
        n += 1
        a20 += c.iloc[-1] > c.rolling(20).mean().iloc[-1]
        a50 += c.iloc[-1] > c.rolling(50).mean().iloc[-1]
        if len(c) >= 200:
            a200 += c.iloc[-1] > c.rolling(200).mean().iloc[-1]
        win = df.iloc[-252:]
        hi += df["high"].iloc[-1] >= win["high"].max()
        lo += df["low"].iloc[-1] <= win["low"].min()
    mb = MarketBreadth(date=session, universe="ALL_EQ", advances=adv, declines=dec, unchanged=unch,
                       pct_above_20dma=round(100 * a20 / n, 1) if n else None,
                       pct_above_50dma=round(100 * a50 / n, 1) if n else None,
                       pct_above_200dma=round(100 * a200 / n, 1) if n >= 50 else None,
                       new_52w_highs=int(hi) if n else None, new_52w_lows=int(lo) if n else None,
                       computed_at=utcnow())
    db.merge(mb)
    db.commit()
    return mb


def compute_sectors(db: Session, session: date) -> list:
    closes = index_series(db, [BENCHMARK, *SECTOR_INDICES], session, lookback_days=400)
    rows = rank_sectors(closes)
    by_index = {s.index_name: s.id for s in db.scalars(select(Sector)) if s.index_name}
    upsert(db, SectorStrength, [{
        "date": session, "index_name": r.index_name, "sector_id": by_index.get(r.index_name), "rank": r.rank,
        "score": r.score, "ret_1w": r.ret_1w, "ret_1m": r.ret_1m, "ret_3m": r.ret_3m,
        "rs_vs_nifty_1m": r.rs_vs_nifty_1m, "rs_vs_nifty_3m": r.rs_vs_nifty_3m, "trend": r.trend,
        "details": _clean(r.details)} for r in rows], ["date", "index_name"])
    db.commit()
    return rows


def _clean(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and np.isnan(v) else (bool(v) if isinstance(v, np.bool_) else v))
            for k, v in d.items()}


def compute_and_store_regime(db: Session, session: date) -> MarketRegime | None:
    cfg = load_config(db)["regime"]
    idx = index_series(db, REGIME_INDICES, session, lookback_days=500)
    if BENCHMARK not in idx or idx[BENCHMARK].index[-1].date() != session:
        return None
    breadth = db.get(MarketBreadth, {"date": session, "universe": "ALL_EQ"}) or compute_breadth(db, session)
    sectors = compute_sectors(db, session)
    flows = db.execute(select(InstitutionalFlow.category, InstitutionalFlow.net_value_cr)
                       .where(InstitutionalFlow.date <= session, InstitutionalFlow.date > session - timedelta(days=8))).all()
    res = compute_regime(RegimeInputs(
        nifty=idx.get(BENCHMARK), banknifty=idx.get("Nifty Bank"), vix=idx.get("India VIX"),
        advances=breadth.advances if breadth else None, declines=breadth.declines if breadth else None,
        pct_above_50dma=breadth.pct_above_50dma if breadth else None,
        pct_above_200dma=breadth.pct_above_200dma if breadth else None,
        sector_rows=sectors or None, flows=[(c, float(v)) for c, v in flows] or None,
    ), cfg)
    row = MarketRegime(session_date=session, computed_at=utcnow(), data_as_of=ist_datetime(session, CLOSE.hour, CLOSE.minute),
                       regime=res.regime, score=res.score, confidence=res.confidence,
                       recommended_exposure_pct=res.recommended_exposure_pct, max_positions=res.max_positions,
                       components={"items": [asdict(c) for c in res.components]}, missing_inputs=res.missing_inputs,
                       model_version=res.model_version)
    db.add(row)
    db.commit()
    return row


def latest_regime(db: Session) -> MarketRegime | None:
    return db.scalar(select(MarketRegime).order_by(MarketRegime.session_date.desc(), MarketRegime.id.desc()).limit(1))
