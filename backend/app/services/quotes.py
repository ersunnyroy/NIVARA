"""Optional real-time quotes. Only active when a broker data provider (Upstox/Kite) is configured."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.data import registry
from app.data.providers.base import ProviderError
from app.models import PriceQuote, Recommendation, Stock, TaxLot, WatchlistItem


def symbols_of_interest(db: Session, limit: int = 400) -> list[Stock]:
    ids = {r for (r,) in db.execute(select(TaxLot.stock_id).where(TaxLot.remaining_quantity > 0))}
    ids |= {r for (r,) in db.execute(select(WatchlistItem.stock_id))}
    latest = db.scalar(select(Recommendation.session_date).order_by(Recommendation.session_date.desc()).limit(1))
    if latest:
        ids |= {r for (r,) in db.execute(select(Recommendation.stock_id).where(Recommendation.session_date == latest))}
    return list(db.scalars(select(Stock).where(Stock.id.in_(ids))))[:limit] if ids else []


def refresh_quotes(db: Session) -> dict:
    prov = registry.realtime_quotes()
    if prov is None:
        return {"skipped": "No real-time provider configured (set UPSTOX_ACCESS_TOKEN or KITE_API_KEY/KITE_ACCESS_TOKEN)"}
    stocks = symbols_of_interest(db)
    if not stocks:
        return {"quotes": 0}
    by_sym = {s.symbol: s for s in stocks}
    try:
        res = prov.quotes(list(by_sym))
    except ProviderError as e:
        return {"error": str(e)}
    now = utcnow()
    n = 0
    for q in res.data:
        st = by_sym.get(q.symbol)
        if st is None:
            continue
        db.add(PriceQuote(stock_id=st.id, ts=q.ts, ltp=q.ltp, open=q.open, high=q.high, low=q.low,
                          prev_close=q.prev_close, volume=q.volume, vwap=q.vwap, source=res.provenance.source,
                          retrieved_at=now, is_delayed=q.is_delayed))
        n += 1
    db.commit()
    return {"quotes": n, "source": res.provenance.source}
