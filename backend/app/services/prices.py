"""Price access: split/bonus-adjusted bar frames and 'current price' with explicit provenance."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import IST, ist_datetime
from app.data.adjustments import apply_adjustments
from app.market_calendar.calendar import CLOSE
from app.models import OHLCV, IndexOHLCV, PriceAdjustment, PriceQuote, Stock

COLS = ["date", "open", "high", "low", "close", "volume", "turnover", "delivery_pct", "prev_close"]


def _frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLS)
    if df.empty:
        return df.set_index("date")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.astype(float)


def bars(db: Session, stock_id: int, end: date | None = None, lookback_days: int = 800,
         adjusted: bool = True) -> pd.DataFrame:
    q = select(OHLCV.date, OHLCV.open, OHLCV.high, OHLCV.low, OHLCV.close, OHLCV.volume, OHLCV.turnover,
               OHLCV.delivery_pct, OHLCV.prev_close).where(OHLCV.stock_id == stock_id)
    if end:
        q = q.where(OHLCV.date <= end).where(OHLCV.date >= end - timedelta(days=lookback_days))
    df = _frame(db.execute(q).all())
    if adjusted and not df.empty:
        adj = [(a.ex_date, a.factor) for a in db.scalars(select(PriceAdjustment).where(PriceAdjustment.stock_id == stock_id))
               if end is None or a.ex_date <= end]  # only adjustments known as of `end` (point-in-time)
        if adj:
            df = apply_adjustments(df, adj)
    return df


def bars_bulk(db: Session, stock_ids: list[int], end: date, lookback_days: int = 550) -> dict[int, pd.DataFrame]:
    start = end - timedelta(days=lookback_days)
    rows = db.execute(
        select(OHLCV.stock_id, OHLCV.date, OHLCV.open, OHLCV.high, OHLCV.low, OHLCV.close, OHLCV.volume,
               OHLCV.turnover, OHLCV.delivery_pct, OHLCV.prev_close)
        .where(OHLCV.stock_id.in_(stock_ids), OHLCV.date <= end, OHLCV.date >= start)
    ).all()
    adj: dict[int, list] = {}
    for a in db.scalars(select(PriceAdjustment).where(PriceAdjustment.stock_id.in_(stock_ids),
                                                      PriceAdjustment.ex_date <= end)):
        adj.setdefault(a.stock_id, []).append((a.ex_date, a.factor))
    by: dict[int, list] = {}
    for r in rows:
        by.setdefault(r[0], []).append(r[1:])
    out = {}
    for sid, rs in by.items():
        df = _frame(rs)
        if sid in adj:
            df = apply_adjustments(df, adj[sid])
        out[sid] = df
    return out


def index_series(db: Session, names: list[str], end: date, lookback_days: int = 800) -> dict[str, pd.Series]:
    rows = db.execute(select(IndexOHLCV.index_name, IndexOHLCV.date, IndexOHLCV.close)
                      .where(IndexOHLCV.index_name.in_(names), IndexOHLCV.date <= end,
                             IndexOHLCV.date >= end - timedelta(days=lookback_days))).all()
    out: dict[str, list] = {}
    for n, d, c in rows:
        out.setdefault(n, []).append((pd.Timestamp(d), c))
    return {n: pd.Series(dict(v)).sort_index().astype(float) for n, v in out.items()}


@dataclass(slots=True)
class CurrentPrice:
    price: float | None
    as_of: datetime | None
    source: str | None
    kind: str  # live_quote | delayed_quote | eod_close | unavailable
    prev_close: float | None = None
    change_pct: float | None = None


def current_price(db: Session, stock_id: int, max_quote_age_min: int = 20) -> CurrentPrice:
    """Latest quote if a real-time provider stored one recently, else the last official close.
    The caller must always display `as_of` and `kind` — EOD prices are never presented as live."""
    q = db.scalar(select(PriceQuote).where(PriceQuote.stock_id == stock_id).order_by(PriceQuote.ts.desc()).limit(1))
    last = db.scalar(select(OHLCV).where(OHLCV.stock_id == stock_id).order_by(OHLCV.date.desc()).limit(1))
    if q is not None and last is not None and q.ts.astimezone(IST).date() >= last.date:
        from app.core.timeutil import utcnow

        age = (utcnow() - q.ts).total_seconds() / 60
        if age <= max_quote_age_min:
            pc = q.prev_close or (last.close if q.ts.astimezone(IST).date() > last.date else last.prev_close)
            return CurrentPrice(q.ltp, q.ts, q.source, "delayed_quote" if q.is_delayed else "live_quote", pc,
                                None if not pc else round(100 * (q.ltp / pc - 1), 2))
    if last is None:
        return CurrentPrice(None, None, None, "unavailable")
    return CurrentPrice(last.close, ist_datetime(last.date, CLOSE.hour, CLOSE.minute), last.source, "eod_close",
                        last.prev_close, None if not last.prev_close else round(100 * (last.close / last.prev_close - 1), 2))


def current_prices(db: Session, stock_ids: list[int]) -> dict[int, CurrentPrice]:
    if not stock_ids:
        return {}
    sub = (select(OHLCV.stock_id, func.max(OHLCV.date).label("d")).where(OHLCV.stock_id.in_(stock_ids))
           .group_by(OHLCV.stock_id).subquery())
    rows = db.execute(select(OHLCV).join(sub, (OHLCV.stock_id == sub.c.stock_id) & (OHLCV.date == sub.c.d))).scalars()
    out = {}
    for r in rows:
        out[r.stock_id] = CurrentPrice(r.close, ist_datetime(r.date, CLOSE.hour, CLOSE.minute), r.source, "eod_close",
                                       r.prev_close, None if not r.prev_close else round(100 * (r.close / r.prev_close - 1), 2))
    # Overlay recent quotes when a real-time provider is configured.
    if db.scalar(select(func.count()).select_from(PriceQuote)):
        for sid in stock_ids:
            cp = current_price(db, sid)
            if cp.kind in ("live_quote", "delayed_quote"):
                out[sid] = cp
    for sid in stock_ids:
        out.setdefault(sid, CurrentPrice(None, None, None, "unavailable"))
    return out


def stock_by_symbol(db: Session, symbol: str) -> Stock | None:
    return db.scalar(select(Stock).where(Stock.symbol == symbol.upper(), Stock.exchange_code == "NSE"))


