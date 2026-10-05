from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics.levels import position_size
from app.api.deps import get_current_user
from app.core.db import get_db
from app.schemas.dto import j
from app.services.portfolio_service import charges_engine

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(get_current_user)])


class SizeIn(BaseModel):
    capital: float = Field(gt=0)
    risk_pct: float = Field(gt=0, le=100)
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    targets: list[float] = []
    max_position_pct: float | None = Field(None, gt=0, le=100)


@router.post("/position-size")
def size(body: SizeIn) -> dict:
    try:
        return j(position_size(body.capital, body.risk_pct, body.entry, body.stop, body.targets, body.max_position_pct))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


class ChargesIn(BaseModel):
    segment: str = Field("delivery", pattern="^(delivery|intraday|futures|options|equity_delivery|equity_intraday)$")
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    trade_date: date
    exchange: str = Field("NSE", pattern="^(NSE|BSE)$")


@router.post("/charges")
def charges(body: ChargesIn, db: Session = Depends(get_db)) -> dict:
    br = charges_engine(db).compute(body.segment, body.side, body.quantity, body.price, body.exchange,
                                    trade_date=body.trade_date).rounded()
    return j(br.to_dict()) | {"label": "ESTIMATED — verify against your broker's contract note"}
