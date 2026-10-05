from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.timeutil import fy_of, today_ist, utcnow
from app.models import ChargeSchedule, Portfolio, Stock, TaxLot, TaxProfile, TaxRule, User
from app.schemas.dto import j, row
from app.services import portfolio_service as ps
from app.services.prices import current_prices
from app.tax.common import DISCLAIMER
from app.tax.engine import compute_tax_year
from app.tax.harvesting import harvest_candidates

router = APIRouter(prefix="/tax", tags=["tax"])


def _live_ids(db: Session, user: User) -> list[int]:
    return [p.id for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id, Portfolio.kind == "live"))]


@router.get("/summary")
def summary(tax_year: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ty = tax_year or fy_of(today_ist())
    ids = _live_ids(db, user)
    rows = ps.realized_lines(db, ids, ty) if ids else []
    lines = ps.gain_lines_from_rows(db, rows)
    profile = ps.tax_profile(db, user.id)
    res = compute_tax_year(lines, ty, profile, ps.rulebook(db))
    charges = sum((Decimal(r.buy_charges) + Decimal(r.sell_charges) for r in rows), Decimal("0"))
    trading = sum((Decimal(r.trading_pnl) for r in rows), Decimal("0"))
    tp = db.get(TaxProfile, user.id)
    years = sorted({r.tax_year for r in ps.realized_lines(db, ids)} | {ty}, reverse=True) if ids else [ty]
    by_symbol: dict[str, dict] = {}
    for r, ln in zip(rows, lines, strict=False):
        sym = db.get(Stock, r.stock_id).symbol
        d = by_symbol.setdefault(sym, {"symbol": sym, "STCG": 0.0, "LTCG": 0.0, "SPEC": 0.0, "charges": 0.0})
        d[ln.term] = d.get(ln.term, 0.0) + float(ln.capital_gain)
        d["charges"] += float(r.buy_charges + r.sell_charges)
    return j(res.to_dict() | {
        "available_tax_years": years, "charges_total": charges, "realized_trading_pnl_after_charges": trading,
        "net_after_tax": trading - res.total_tax_estimate, "by_symbol": list(by_symbol.values()),
        "broker_reported": (tp.broker_reported or {}).get(ty) if tp else None,
        "potential_liability_note": "Potential liability = estimated tax on realized gains this tax year.",
        "label": "ESTIMATED", "disclaimer": DISCLAIMER,
        "not_a_filing_tool": "This does not replace a chartered accountant or tax-filing software.",
    })


@router.get("/harvesting")
def harvesting(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = _live_ids(db, user)
    ty = fy_of(today_ist())
    lots = db.scalars(select(TaxLot).where(TaxLot.portfolio_id.in_(ids or [-1]), TaxLot.remaining_quantity > 0)).all()
    prices = current_prices(db, list({lot.stock_id for lot in lots}))
    items = []
    for lot in lots:
        cp = prices.get(lot.stock_id)
        if cp is None or cp.price is None:
            continue
        sym = db.get(Stock, lot.stock_id).symbol
        eng = ps._ledger(db, lot.portfolio_id, lot.stock_id, sym)
        items += [(x, Decimal(str(cp.price))) for x in eng if x.lot_id == str(lot.id)]
    lines = ps.gain_lines_from_rows(db, ps.realized_lines(db, ids, ty)) if ids else []
    rep = harvest_candidates(items, lines, ps.tax_profile(db, user.id), ps.rulebook(db), today_ist(),
                             charges_engine=ps.charges_engine(db))
    return j(asdict(rep) if not hasattr(rep, "to_dict") else rep.to_dict())


class ProfileIn(BaseModel):
    residency: str | None = Field(None, pattern="^(resident|nri)$")
    regime: str | None = Field(None, pattern="^(new|old)$")
    other_taxable_income: Decimal | None = Field(None, ge=0)
    slab_rate_for_business_income: Decimal | None = Field(None, ge=0, le=1)
    carried_forward: dict = {}
    broker_reported: dict = {}


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    tp = db.get(TaxProfile, user.id)
    return row(tp) if tp else {"user_id": user.id, "residency": None, "regime": None, "other_taxable_income": None,
                               "slab_rate_for_business_income": None, "carried_forward": {}, "broker_reported": {}}


@router.put("/profile")
def put_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    tp = db.get(TaxProfile, user.id) or TaxProfile(user_id=user.id)
    for k, v in body.model_dump().items():
        setattr(tp, k, j(v) if isinstance(v, dict) else v)
    tp.updated_at = utcnow()
    db.merge(tp)
    db.commit()
    return row(db.get(TaxProfile, user.id))


@router.get("/rules")
def rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"rules": [row(r) for r in db.scalars(select(TaxRule).order_by(TaxRule.asset_type, TaxRule.term,
                                                                          TaxRule.effective_from))],
            "charges": [row(c) for c in db.scalars(select(ChargeSchedule).order_by(ChargeSchedule.effective_from))],
            "note": "Rules are dated and versioned; they must be reviewed whenever tax law or exchange charges change."}


