"""Insert SYNTHETIC bars for tests (never used by the application)."""
from __future__ import annotations

from datetime import date

from app.core.timeutil import utcnow
from app.models import OHLCV, IndexOHLCV, Stock
from tests.synthetic import make_bars


def add_stock(db, symbol="TESTCO", industry="Information Technology", members=("nifty500",), n=320, drift=0.0015,
              seed=3, start="2025-06-02", price=500.0) -> Stock:
    st = Stock(symbol=symbol, exchange_code="NSE", name=f"{symbol} Ltd", series="EQ", industry=industry,
               index_memberships=list(members), is_active=True, surveillance_flags=[], meta={})
    db.add(st)
    db.flush()
    df = make_bars(n=n, drift=drift, seed=seed, start_date=start, start=price)
    prev = None
    for t, r in df.iterrows():
        db.add(OHLCV(stock_id=st.id, date=t.date(), open=r.open, high=r.high, low=r.low, close=r.close,
                     prev_close=prev, volume=int(r.volume * 20), turnover=float(r.close * r.volume * 20),
                     delivery_pct=45.0, source="TEST SYNTHETIC", retrieved_at=utcnow()))
        prev = r.close
    db.commit()
    return st


def add_index(db, name="Nifty 50", n=320, drift=0.0008, seed=9, start="2025-06-02") -> None:
    df = make_bars(n=n, drift=drift, seed=seed, start_date=start, start=20000.0)
    for t, r in df.iterrows():
        db.add(IndexOHLCV(index_name=name, date=t.date(), open=r.open, high=r.high, low=r.low, close=r.close,
                          source="TEST SYNTHETIC", retrieved_at=utcnow()))
    db.commit()


def last_date(db) -> date:
    from sqlalchemy import func, select

    return db.scalar(select(func.max(OHLCV.date)))
