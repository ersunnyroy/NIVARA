"""F&O overview and paper trading."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import not_found
from app.models import FnoSnapshot, PaperOrder, User
from app.paper import engine as paper
from app.schemas.dto import j, row
from app.services import portfolio_service as ps
from app.services.performance import performance
from app.services.prices import stock_by_symbol

router = APIRouter(tags=["fno", "paper"])


@router.get("/fno/overview")
def fno_overview(date_: date | None = Query(None, alias="date"), buildup: str | None = None,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    d = date_ or db.scalar(select(func.max(FnoSnapshot.date)))
    if d is None:
        return {"date": None, "items": [], "status": "data_unavailable",
                "message": "No F&O data ingested yet (run the F&O job)."}
    q = select(FnoSnapshot).where(FnoSnapshot.date == d)
    if buildup:
        q = q.where(FnoSnapshot.buildup == buildup)
    items = [row(s, {"details"}) for s in db.scalars(q.order_by(FnoSnapshot.underlying))]
    counts: dict[str, int] = {}
    for i in items:
        counts[i["buildup"] or "n/a"] = counts.get(i["buildup"] or "n/a", 0) + 1
    return {"date": d.isoformat(), "items": items, "buildup_counts": counts, "status": "ok",
            "source": "NSE F&O bhavcopy (EOD); IV computed by Black-76/Black-Scholes from settlement prices",
            "caveat": "OI is one input; never decide on OI alone."}


@router.get("/paper")
def paper_home(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    p = paper.get_portfolio(db, user.id, "paper")
    m = paper.get_portfolio(db, user.id, "model")
    db.commit()
    orders = db.scalars(select(PaperOrder).where(PaperOrder.portfolio_id.in_([p.id, m.id]))
                        .order_by(PaperOrder.created_at.desc()).limit(200)).all()
    perf = performance(db, user.id)["kinds"]
    return j({
        "portfolio": ps.holdings(db, p, user.id), "model_portfolio": ps.holdings(db, m, user.id),
        "cash": paper.cash(db, p), "model_cash": paper.cash(db, m),
        "orders": [row(o) | {"symbol": o.stock.symbol, "portfolio": "model" if o.portfolio_id == m.id else "paper"}
                   for o in orders],
        "follow_model": paper.follow_model_enabled(db, user.id),
        "comparison": {"model": perf.get("system", {"total_trades": 0}), "user": perf.get("paper", {"total_trades": 0})},
        "notice": "Paper trading simulates fills on official EOD bars. No real orders are ever placed.",
    })


class PaperOrderIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: Decimal = Field(gt=0)
    order_type: str = Field("MARKET", pattern="^(MARKET|LIMIT)$")
    limit_price: float | None = Field(None, gt=0)
    stop: float | None = Field(None, gt=0)
    target: float | None = Field(None, gt=0)
    valid_sessions: int = Field(3, ge=1, le=20)


@router.post("/paper/orders", status_code=201)
def place(body: PaperOrderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    st = stock_by_symbol(db, body.symbol)
    if st is None:
        raise not_found(f"Stock {body.symbol}")
    p = paper.get_portfolio(db, user.id, "paper")
    try:
        o = paper.place_order(db, p, st, body.side, body.quantity, body.order_type, body.limit_price, body.stop,
                              body.target, body.valid_sessions)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return row(o) | {"symbol": st.symbol, "note": "Will be filled against the next session's official EOD bar."}


@router.delete("/paper/orders/{oid}")
def cancel(oid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    o = db.get(PaperOrder, oid)
    p = paper.get_portfolio(db, user.id, "paper")
    if o is None or o.portfolio_id != p.id:
        raise not_found("Order")
    if o.status == "open":
        o.status = "cancelled"
    db.commit()
    return {"ok": True}


class PaperSettingsIn(BaseModel):
    follow_model: bool


@router.put("/paper/settings")
def paper_settings(body: PaperSettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    paper.set_follow_model(db, user.id, body.follow_model)
    db.commit()
    return {"follow_model": body.follow_model}
