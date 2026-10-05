from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.backtesting.engine import STRATEGIES
from app.backtesting.service import create_backtest, execute_backtest
from app.core.db import get_db, session_scope
from app.core.errors import not_found
from app.models import Backtest, BacktestTrade, User
from app.schemas.dto import row

router = APIRouter(prefix="/backtests", tags=["backtesting"])
BANNER = ("BACKTEST PERFORMANCE — simulated on historical data. Past simulated results do not guarantee future "
          "returns. Judge the out-of-sample TEST split, not the training split.")


class BacktestIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strategy: str
    start_date: date
    end_date: date
    params: dict = {}
    universe: str = "liquid_pit"


def _run(bid: int) -> None:
    try:
        with session_scope() as db:
            execute_backtest(db, bid)
    except Exception:  # status/error is recorded on the backtest row
        logging.getLogger(__name__).exception("backtest %s failed", bid)


@router.get("")
def list_bt(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Backtest).where(Backtest.user_id == user.id).order_by(Backtest.created_at.desc())).all()
    return {"strategies": list(STRATEGIES), "banner": BANNER,
            "items": [row(b, {"equity_curve"}) for b in rows]}


@router.post("", status_code=201)
def create(body: BacktestIn, background: BackgroundTasks, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)) -> dict:
    try:
        bt = create_backtest(db, user.id, body.name, body.strategy, body.start_date, body.end_date, body.params,
                             body.universe)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    try:
        from app.workers.celery_app import celery

        if celery.control.ping(timeout=0.5):
            celery.send_task("nivara.backtest", args=[bt.id])
            return row(bt) | {"queued_via": "celery"}
    except Exception:
        pass
    background.add_task(_run, bt.id)
    return row(bt) | {"queued_via": "in-process"}


@router.get("/{bid}")
def get_bt(bid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    b = db.get(Backtest, bid)
    if b is None or b.user_id != user.id:
        raise not_found("Backtest")
    trades = db.scalars(select(BacktestTrade).where(BacktestTrade.backtest_id == b.id)
                        .order_by(BacktestTrade.entry_date)).all()
    return row(b) | {"trades": [row(t) for t in trades], "banner": BANNER}


@router.delete("/{bid}")
def delete_bt(bid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    b = db.get(Backtest, bid)
    if b is None or b.user_id != user.id:
        raise not_found("Backtest")
    db.delete(b)
    db.commit()
    return {"ok": True}
