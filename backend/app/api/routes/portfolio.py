from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.audit import audit
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.models import Portfolio, PortfolioPosition, Stock, Transaction, User
from app.schemas.dto import j, row
from app.services import portfolio_service as ps
from app.services.prices import stock_by_symbol

router = APIRouter(tags=["portfolio"])


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field("live", pattern="^(live|paper)$")
    broker: str | None = Field(None, max_length=80)
    starting_cash: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)


class TransactionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(BUY|SELL|buy|sell)$")
    quantity: Decimal = Field(gt=0, le=Decimal("100000000"))
    price: Decimal = Field(gt=0, le=Decimal("10000000"))
    trade_date: date
    trade_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    segment: str = Field("delivery", pattern="^(delivery|intraday)$")
    exchange: str = Field("NSE", pattern="^(NSE|BSE)$")
    broker: str | None = Field(None, max_length=80)
    charges_total: Decimal | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)
    fmv_31jan2018: Decimal | None = Field(None, gt=0, description="Per-share FMV on 31-Jan-2018 (grandfathering)")

    @field_validator("trade_date")
    @classmethod
    def not_future(cls, v: date) -> date:
        from app.core.timeutil import today_ist

        if v > today_ist():
            raise ValueError("Trade date cannot be in the future")
        return v


class PositionLevelsIn(BaseModel):
    stop: float | None = Field(None, gt=0)
    target1: float | None = Field(None, gt=0)
    target2: float | None = Field(None, gt=0)
    trailing_stop: float | None = Field(None, gt=0)
    thesis: str | None = Field(None, max_length=4000)


def own_portfolio(db: Session, user: User, pid: int) -> Portfolio:
    p = db.get(Portfolio, pid)
    if p is None or p.user_id != user.id:
        raise not_found("Portfolio")
    return p


@router.get("/portfolios")
def list_portfolios(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [row(p) for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id))]


@router.post("/portfolios", status_code=201)
def create_portfolio(body: PortfolioIn, request: Request, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    p = Portfolio(user_id=user.id, name=body.name, kind=body.kind, broker=body.broker,
                  starting_cash=body.starting_cash, notes=body.notes)
    db.add(p)
    db.flush()
    audit(db, "portfolio.create", user.id, "portfolio", p.id, ip=client_ip(request))
    db.commit()
    return row(p)


@router.delete("/portfolios/{pid}")
def delete_portfolio(pid: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    p = own_portfolio(db, user, pid)
    audit(db, "portfolio.delete", user.id, "portfolio", p.id, {"name": p.name}, client_ip(request))
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/portfolios/{pid}")
def portfolio_detail(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return j(ps.holdings(db, own_portfolio(db, user, pid), user.id))


@router.get("/portfolios/{pid}/transactions")
def list_txns(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    p = own_portfolio(db, user, pid)
    out = []
    for t in db.scalars(select(Transaction).where(Transaction.portfolio_id == p.id)
                        .order_by(Transaction.trade_date.desc(), Transaction.id.desc())):
        d = row(t)
        d["symbol"], d["name"] = t.stock.symbol, t.stock.name
        d["value"] = float(t.quantity * t.price)
        out.append(d)
    return out


@router.post("/portfolios/{pid}/transactions", status_code=201)
def add_txn(pid: int, body: TransactionIn, request: Request, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    p = own_portfolio(db, user, pid)
    if p.kind == "model":
        raise bad_request("The model portfolio is managed automatically")
    st = stock_by_symbol(db, body.symbol)
    if st is None:
        raise not_found(f"Stock {body.symbol}")
    try:
        t = ps.add_transaction(db, p, st, body.side.upper(), body.quantity, body.price, body.trade_date,
                               body.segment, body.exchange, body.broker, body.charges_total, body.notes,
                               trade_time=body.trade_time, fmv_31jan2018=body.fmv_31jan2018)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    audit(db, "transaction.add", user.id, "transaction", t.id,
          {"symbol": st.symbol, "side": t.side, "qty": str(t.quantity), "price": str(t.price)}, client_ip(request))
    db.commit()
    return row(t) | {"symbol": st.symbol}


@router.delete("/portfolios/{pid}/transactions/{tid}")
def delete_txn(pid: int, tid: int, request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    p = own_portfolio(db, user, pid)
    t = db.get(Transaction, tid)
    if t is None or t.portfolio_id != p.id:
        raise not_found("Transaction")
    sid = t.stock_id
    db.delete(t)
    db.flush()
    try:
        ps.rebuild_lots(db, p.id, sid)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, f"Cannot delete: {e}") from e
    audit(db, "transaction.delete", user.id, "transaction", tid, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.put("/portfolios/{pid}/positions/{symbol}")
def set_levels(pid: int, symbol: str, body: PositionLevelsIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    p = own_portfolio(db, user, pid)
    st = stock_by_symbol(db, symbol)
    if st is None:
        raise not_found(f"Stock {symbol}")
    pp = db.scalar(select(PortfolioPosition).where(PortfolioPosition.portfolio_id == p.id,
                                                   PortfolioPosition.stock_id == st.id))
    if pp is None:
        pp = PortfolioPosition(portfolio_id=p.id, stock_id=st.id)
        db.add(pp)
    for k, v in body.model_dump().items():
        setattr(pp, k, v)
    db.commit()
    return row(pp)


@router.get("/portfolios/{pid}/realized")
def realized(pid: int, tax_year: str | None = None, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    from app.core.timeutil import fy_of, today_ist

    p = own_portfolio(db, user, pid)
    ty = tax_year or fy_of(today_ist())
    rows = ps.realized_lines(db, [p.id], ty)
    lines = []
    for r in rows:
        d = row(r)
        d["symbol"] = db.get(Stock, r.stock_id).symbol
        lines.append(d)
    return {"tax_year": ty, "lines": lines,
            "summary": ps.summarize_realized(db, rows, ps.tax_profile(db, user.id), ty)}


@router.get("/portfolio/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ports = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id, Portfolio.kind == "live")).all()
    agg = dict.fromkeys(("invested", "current_value", "gross_pnl", "unrealized_gross_pnl", "realized_gross_pnl", "charges_incl_estimated_exit", "estimated_tax_unrealized", "estimated_tax_realized", "net_pnl"), 0.0)
    actions, details = [], []
    for p in ports:
        h = ps.holdings(db, p, user.id)
        details.append({"id": p.id, "name": p.name, "summary": h["summary"], "positions": len(h["positions"])})
        for k in agg:
            agg[k] += h["summary"].get(k) or 0.0
        for pos in h["positions"]:
            m = pos.get("monitor")
            if m:
                actions.append({"portfolio_id": p.id, "portfolio": p.name, "symbol": pos["symbol"],
                                "action": m["action"], "severity": m["severity"], "reasons": m["reasons"][:3],
                                "pnl_pct": m["pnl_pct"]})
    agg["net_return_pct"] = 100 * agg["net_pnl"] / agg["invested"] if agg["invested"] else None
    sev = {"critical": 0, "warning": 1, "info": 2}
    actions.sort(key=lambda a: sev.get(a["severity"], 3))
    return j({"summary": agg, "actions": actions, "portfolios": details,
              "labels": {"tax": "ESTIMATED", "unrealized_note": "Unrealized gains are informational and not "
                                                                "necessarily currently taxable."}})


@router.get("/portfolio/exits")
def exits(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """SELL / EXIT NOW: holdings where any exit condition fired, each with its reasons."""
    out = []
    for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id, Portfolio.kind.in_(["live", "paper"]))):
        for pos in ps.holdings(db, p, user.id)["positions"]:
            m = pos.get("monitor")
            if m and (m["sell_signals"] or m["action"] in ("EXIT", "PARTIAL PROFIT")):
                out.append({"portfolio_id": p.id, "portfolio": p.name, "kind": p.kind, "symbol": pos["symbol"],
                            "name": pos["name"], "action": m["action"], "severity": m["severity"],
                            "reasons": m["reasons"], "sell_signals": m["sell_signals"],
                            "suggested_trailing_stop": m["suggested_trailing_stop"],
                            "partial_exit_pct": m["partial_exit_pct"], "pnl": m["pnl"], "pnl_pct": m["pnl_pct"],
                            "price": pos["price"], "price_as_of": pos["price_as_of"], "levels": m.get("levels")})
    return j(out)
