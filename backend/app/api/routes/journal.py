"""Trade journal + performance."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.models import Portfolio, Trade, User
from app.schemas.dto import j, row
from app.services.performance import performance
from app.services.prices import stock_by_symbol

router = APIRouter(tags=["journal"])


class TradeIn(BaseModel):
    portfolio_id: int
    symbol: str
    kind: str = Field("live", pattern="^(live|paper|user)$")
    entry_date: date
    entry_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    stop: float | None = None
    target: float | None = None
    exit_date: date | None = None
    exit_price: Decimal | None = Field(None, gt=0)
    reason_entry: str | None = Field(None, max_length=4000)
    reason_exit: str | None = Field(None, max_length=4000)
    market_regime: str | None = None
    score_at_entry: float | None = None
    recommendation_id: int | None = None
    charges: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=8000)
    attachment_url: str | None = Field(None, max_length=1000)


def _compute(db: Session, t: Trade) -> None:
    if t.exit_price is None or t.exit_date is None:
        t.status = "open"
        return
    from app.paper.engine import close_trade  # reuse the same charge/tax estimate path
    from app.services.portfolio_service import charges_engine

    sell = SimpleNamespace(charges_total=charges_engine(db).compute(
        "delivery", "SELL", Decimal(t.quantity), Decimal(t.exit_price), "NSE", trade_date=t.exit_date).rounded().total)
    user_charges = t.charges
    close_trade(db, t, t.exit_date, Decimal(t.exit_price), t.reason_exit or "", sell)
    if user_charges is not None:
        t.charges = user_charges
        t.net_pnl = Decimal(t.gross_pnl) - user_charges - Decimal(t.tax_estimate or 0)


@router.get("/trades")
def list_trades(kind: str | None = None, status: str | None = None, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> list[dict]:
    pids = [p.id for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id))]
    q = select(Trade).where(Trade.portfolio_id.in_(pids or [-1])).order_by(Trade.entry_date.desc())
    if kind:
        q = q.where(Trade.kind == kind)
    if status:
        q = q.where(Trade.status == status)
    return [row(t) | {"symbol": t.stock.symbol, "name": t.stock.name} for t in db.scalars(q.limit(1000))]


@router.post("/trades", status_code=201)
def create_trade(body: TradeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    p = db.get(Portfolio, body.portfolio_id)
    if p is None or p.user_id != user.id:
        raise not_found("Portfolio")
    st = stock_by_symbol(db, body.symbol)
    if st is None:
        raise not_found(f"Stock {body.symbol}")
    if body.exit_date and body.exit_date < body.entry_date:
        raise bad_request("Exit date before entry date")
    data = body.model_dump(exclude={"symbol", "portfolio_id"})
    t = Trade(portfolio_id=p.id, stock_id=st.id, origin="user", **data)
    db.add(t)
    db.flush()
    _compute(db, t)
    db.commit()
    return row(t) | {"symbol": st.symbol}


@router.put("/trades/{tid}")
def update_trade(tid: int, body: TradeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    t = db.get(Trade, tid)
    if t is None or db.get(Portfolio, t.portfolio_id).user_id != user.id:
        raise not_found("Trade")
    for k, v in body.model_dump(exclude={"symbol", "portfolio_id"}).items():
        setattr(t, k, v)
    _compute(db, t)
    db.commit()
    return row(t) | {"symbol": t.stock.symbol}


@router.delete("/trades/{tid}")
def delete_trade(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    t = db.get(Trade, tid)
    if t is None or db.get(Portfolio, t.portfolio_id).user_id != user.id:
        raise not_found("Trade")
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.get("/performance")
def perf(kind: str | None = Query(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    out = performance(db, user.id)
    if kind:
        out["kinds"] = {k: v for k, v in out["kinds"].items() if k == kind}
    return j(out)
