from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.market_calendar.calendar import load_calendar
from app.models import OHLCV, IndexOHLCV, InstitutionalFlow, MarketBreadth, MarketRegime, SectorStrength, Stock
from app.schemas.dto import j, row
from app.services.market import latest_regime

router = APIRouter(prefix="/market", tags=["market"], dependencies=[Depends(get_current_user)])

HEADLINE_INDICES = ["Nifty 50", "Nifty Next 50", "Nifty Bank", "Nifty Financial Services", "India VIX",
                    "Nifty Midcap 50", "NIFTY Smallcap 100", "Nifty 500"]
DISPLAY = {"Nifty 50": "NIFTY 50", "Nifty Next 50": "NIFTY NEXT 50", "Nifty Bank": "BANK NIFTY",
           "Nifty Financial Services": "FINNIFTY", "India VIX": "INDIA VIX"}


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    cal = load_calendar(db)
    st = cal.status()
    last = db.scalar(select(func.max(OHLCV.date)))
    expected = date.fromisoformat(st["last_completed_eod_session"])
    st["data"] = {"last_eod_date": j(last), "is_current": bool(last and last >= expected),
                  "sessions_behind": cal.sessions_between(last, expected) if last and last < expected else 0,
                  "realtime_quotes": False}
    from app.data import registry

    st["data"]["realtime_quotes"] = registry.realtime_quotes() is not None
    return st


def regime_dto(r: MarketRegime | None) -> dict | None:
    if r is None:
        return None
    d = row(r)
    d["components"] = (r.components or {}).get("items", [])
    return d


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    last = db.scalar(select(func.max(IndexOHLCV.date)))
    out: dict = {"data_as_of": j(last), "regime": regime_dto(latest_regime(db)), "indices": [], "breadth": None,
                 "flows": [], "sectors": [], "movers": {"gainers": [], "losers": [], "most_active": []}}
    if last is None:
        out["status"] = "data_unavailable"
        return out
    rows = {r.index_name: r for r in db.scalars(select(IndexOHLCV).where(IndexOHLCV.date == last,
                                                                         IndexOHLCV.index_name.in_(HEADLINE_INDICES)))}
    out["indices"] = [{"name": DISPLAY.get(n, n.upper()), "index_name": n, "close": rows[n].close,
                       "change_pct": rows[n].change_pct, "date": j(rows[n].date), "source": rows[n].source}
                      for n in HEADLINE_INDICES if n in rows]
    b = db.scalar(select(MarketBreadth).order_by(MarketBreadth.date.desc()).limit(1))
    out["breadth"] = row(b) if b else None
    out["flows"] = [row(f) for f in db.scalars(select(InstitutionalFlow).order_by(InstitutionalFlow.date.desc()).limit(10))]
    sd = db.scalar(select(func.max(SectorStrength.date)))
    if sd:
        out["sectors"] = [row(s) for s in db.scalars(select(SectorStrength).where(SectorStrength.date == sd)
                                                     .order_by(SectorStrength.rank))]
    od = db.scalar(select(func.max(OHLCV.date)))
    if od:
        q = (select(Stock.symbol, Stock.name, OHLCV.close, OHLCV.prev_close, OHLCV.volume, OHLCV.turnover)
             .join(Stock, Stock.id == OHLCV.stock_id).where(OHLCV.date == od, Stock.series == "EQ",
                                                            OHLCV.turnover > 5e7))
        movers = [{"symbol": s, "name": n, "close": c, "change_pct": round(100 * (c / p - 1), 2) if p else None,
                   "volume": v, "turnover_cr": round((t or 0) / 1e7, 2)} for s, n, c, p, v, t in db.execute(q)]
        movers = [m for m in movers if m["change_pct"] is not None]
        out["movers"] = {"gainers": sorted(movers, key=lambda m: -m["change_pct"])[:8],
                         "losers": sorted(movers, key=lambda m: m["change_pct"])[:8],
                         "most_active": sorted(movers, key=lambda m: -m["turnover_cr"])[:8], "date": j(od)}
    out["status"] = "ok"
    return out


@router.get("/regime/history")
def regime_history(days: int = 120, db: Session = Depends(get_db)) -> list[dict]:
    since = date.today() - timedelta(days=days)
    return [regime_dto(r) for r in db.scalars(select(MarketRegime).where(MarketRegime.session_date >= since)
                                               .order_by(MarketRegime.session_date))]
