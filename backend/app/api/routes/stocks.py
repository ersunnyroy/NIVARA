from __future__ import annotations

from datetime import timedelta

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import not_found
from app.models import (
    CorporateAction,
    FinancialResult,
    FnoSnapshot,
    NewsItem,
    NewsSentiment,
    Recommendation,
    Shareholding,
    Signal,
    Stock,
)
from app.schemas.dto import j, price_dto, rec_dto, row, stock_brief
from app.services.prices import bars, current_price, stock_by_symbol
from app.technical.indicators import compute_all

router = APIRouter(prefix="/stocks", tags=["stocks"], dependencies=[Depends(get_current_user)])

RANGES = {"1D": 5, "5D": 10, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "3Y": 3 * 366, "5Y": 5 * 366}


def _stock(db: Session, symbol: str) -> Stock:
    s = stock_by_symbol(db, symbol)
    if s is None:
        raise not_found(f"Stock {symbol}")
    return s


@router.get("")
def search(q: str = "", limit: int = Query(20, le=100), db: Session = Depends(get_db)) -> list[dict]:
    query = select(Stock).where(Stock.exchange_code == "NSE", Stock.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Stock.symbol.ilike(like), Stock.name.ilike(like)))
    rows = db.scalars(query.limit(500)).all()
    ql = q.upper().strip()
    rows.sort(key=lambda s: (s.symbol != ql, not s.symbol.startswith(ql), "nifty500" not in (s.index_memberships or []),
                             s.symbol))
    return [stock_brief(s) for s in rows[:limit]]


@router.get("/{symbol}")
def detail(symbol: str, db: Session = Depends(get_db)) -> dict:
    s = _stock(db, symbol)
    sig = db.scalar(select(Signal).where(Signal.stock_id == s.id).order_by(Signal.id.desc()).limit(1))
    d = stock_brief(s) | {"exchange": s.exchange_code, "face_value": s.face_value, "listing_date": j(s.listing_date),
                          "fno_lot_size": s.fno_lot_size, "price": price_dto(current_price(db, s.id))}
    d["latest_signal"] = ({"score": sig.score, "setup": sig.setup, "session_date": j(sig.session_date),
                           "rejected": sig.rejected, "rejection_reasons": sig.rejection_reasons} if sig else None)
    return d


def _series(df, col: str) -> list[dict]:
    if col not in df:
        return []
    s = df[col]
    return [{"time": t.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for t, v in s.items() if not np.isnan(v)]


@router.get("/{symbol}/bars")
def price_bars(symbol: str, range_: str = Query("1Y", alias="range"), db: Session = Depends(get_db)) -> dict:
    s = _stock(db, symbol)
    days = RANGES.get(range_.upper(), 366)
    full = bars(db, s.id, lookback_days=days + 450)  # extra history so long indicators are warm
    if full.empty:
        return {"bars": [], "overlays": {}, "panes": {}, "interval": "1d", "status": "data_unavailable"}
    ind = compute_all(full)
    view = ind[ind.index >= ind.index[-1] - timedelta(days=days)]
    out = {
        "interval": "1d", "adjusted": True, "status": "ok",
        "bars": [{"time": t.strftime("%Y-%m-%d"), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                  "volume": float(r.volume)} for t, r in view.iterrows()],
        "overlays": {k: _series(view, k) for k in ("ema_20", "ema_50", "ema_200", "sma_20", "sma_50", "sma_200",
                                                   "bb_upper", "bb_mid", "bb_lower", "supertrend", "vwap_20")},
        "panes": {k: _series(view, k) for k in ("rsi_14", "macd", "macd_signal", "macd_hist")},
        "data_as_of": view.index[-1].strftime("%Y-%m-%d"),
        "source": "NSE CM bhavcopy (EOD), split/bonus adjusted",
    }
    if range_.upper() in ("1D", "5D"):
        out["note"] = ("Intraday candles need a real-time data provider (Upstox/Kite). Showing the most recent daily "
                       "bars instead.")
    out["note_vwap"] = "VWAP shown is a rolling 20-day volume-weighted price (daily bars cannot give intraday VWAP)."
    return out


@router.get("/{symbol}/technical")
def technical(symbol: str, db: Session = Depends(get_db)) -> dict:
    from app.services.stock_analysis import analyze

    s = _stock(db, symbol)
    res = analyze(db, s)
    if res["status"] != "ok":
        return res
    ev = res["evaluation"]
    setup = None
    if ev.levels:
        setup = j(ev.levels.asdict()) | {
            "score": ev.score.breakdown() if ev.score else None, "confidence": ev.confidence,
            "confidence_notes": ev.confidence_notes, "action": ev.action, "rejected": ev.rejected,
            "rejection_reasons": ev.rejection_reasons, "why": ev.why, "why_not": ev.why_not,
            "invalidation": ev.invalidation, "cmp": ev.cmp}
    return {"status": "ok", "as_of": res["as_of"], "indicators": ev.indicators, "price_action": j(ev.price_action),
            "setup": setup, "notes": res["notes"],
            "disclaimer": "Computed on demand from EOD data; not a recommendation unless it appears in the daily Top 10."}


@router.get("/{symbol}/fundamentals")
def fundamentals(symbol: str, db: Session = Depends(get_db)) -> dict:
    from app.core.timeutil import today_ist
    from app.services.fundamentals_service import fundamental_view

    s = _stock(db, symbol)
    cp = current_price(db, s.id)
    fv = fundamental_view(db, s.id, s.symbol, today_ist(), cp.price)
    res = db.scalars(select(FinancialResult).where(FinancialResult.stock_id == s.id)
                     .order_by(FinancialResult.period_end.desc()).limit(12)).all()
    fv["results"] = [row(r, {"raw", "analysis"}) for r in res]
    fv["price_used"] = price_dto(cp)
    return j(fv)


@router.get("/{symbol}/news")
def stock_news(symbol: str, limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    s = _stock(db, symbol)
    items = db.scalars(select(NewsItem).where(NewsItem.stock_id == s.id).order_by(NewsItem.published_at.desc())
                       .limit(limit)).all()
    return [news_dto(db, n) for n in items]


def news_dto(db: Session, n: NewsItem) -> dict:
    d = row(n, {"raw", "dedupe_hash", "body"})
    ai = db.scalar(select(NewsSentiment).where(NewsSentiment.news_id == n.id).order_by(NewsSentiment.id.desc()).limit(1))
    d["ai"] = ({"facts": ai.facts, "interpretation": ai.interpretation, "speculation": ai.speculation,
                "summary": ai.summary, "model": ai.model, "guardrail_flags": ai.guardrail_flags} if ai else None)
    d["verification"] = "Primary exchange filing" if n.source_tier == "primary" else (
        "Reputable secondary source — not independently verified" if n.source_tier == "reputable" else "Unverified")
    return d


@router.get("/{symbol}/fno")
def stock_fno(symbol: str, db: Session = Depends(get_db)) -> dict:
    s = _stock(db, symbol)
    if not s.is_fno:
        return {"is_fno": False, "snapshot": None, "history": [], "message": "Not an F&O stock"}
    hist = db.scalars(select(FnoSnapshot).where(FnoSnapshot.underlying == s.symbol)
                      .order_by(FnoSnapshot.date.desc()).limit(60)).all()
    return {"is_fno": True, "lot_size": s.fno_lot_size, "snapshot": row(hist[0]) if hist else None,
            "history": [row(h, {"details"}) for h in reversed(hist)],
            "message": None if hist else "F&O data unavailable — run the F&O ingestion job",
            "caveat": "OI is one input; never decide on OI alone."}


@router.get("/{symbol}/corporate-actions")
def corp_actions(symbol: str, db: Session = Depends(get_db)) -> list[dict]:
    s = _stock(db, symbol)
    return [row(c, {"raw"}) for c in db.scalars(select(CorporateAction).where(CorporateAction.stock_id == s.id)
                                                 .order_by(CorporateAction.ex_date.desc()).limit(50))]


@router.get("/{symbol}/shareholding")
def shareholding(symbol: str, db: Session = Depends(get_db)) -> list[dict]:
    s = _stock(db, symbol)
    return [row(x) for x in db.scalars(select(Shareholding).where(Shareholding.stock_id == s.id)
                                        .order_by(Shareholding.period_end.desc()).limit(12))]


@router.get("/{symbol}/signals")
def signals(symbol: str, db: Session = Depends(get_db)) -> dict:
    s = _stock(db, symbol)
    recs = db.scalars(select(Recommendation).where(Recommendation.stock_id == s.id)
                      .order_by(Recommendation.session_date.desc()).limit(100)).unique().all()
    sigs = db.scalars(select(Signal).where(Signal.stock_id == s.id).order_by(Signal.id.desc()).limit(60)).all()
    return {"recommendations": [rec_dto(r) for r in recs],
            "scores": [{"session_date": j(x.session_date), "score": x.score, "setup": x.setup, "rejected": x.rejected}
                       for x in reversed(sigs)]}


@router.get("/{symbol}/analysis")
def ai_analysis(symbol: str, db: Session = Depends(get_db)) -> dict:
    from app.ai.analysis import get_or_build

    return get_or_build(db, _stock(db, symbol), regenerate=False)


@router.post("/{symbol}/analysis")
def ai_analysis_regen(symbol: str, db: Session = Depends(get_db)) -> dict:
    from app.ai.analysis import get_or_build

    return get_or_build(db, _stock(db, symbol), regenerate=True)
