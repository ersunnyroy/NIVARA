from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import audit
from app.core.db import get_db
from app.core.errors import not_found
from app.models import Recommendation, ScanRun, Stock, User
from app.schemas.dto import rec_dto, row
from app.services.outcomes_service import track_record

router = APIRouter(tags=["opportunities"], dependencies=[Depends(get_current_user)])


def run_dto(r: ScanRun | None) -> dict | None:
    return row(r) if r else None


@router.get("/opportunities")
def opportunities(date_: date | None = Query(None, alias="date"), db: Session = Depends(get_db)) -> dict:
    q = select(ScanRun).order_by(ScanRun.generated_at.desc())
    if date_:
        q = q.where(ScanRun.session_date == date_)
    run = db.scalar(q.limit(1))
    if run is None:
        return {"run": None, "items": [], "status": "no_runs",
                "message": "No scan has been run yet. Ingest market data and run the scanner (Settings → Jobs)."}
    items = db.scalars(select(Recommendation).where(Recommendation.run_id == run.id)
                       .order_by(Recommendation.rank)).unique().all()
    return {"run": run_dto(run), "items": [rec_dto(r) for r in items], "status": run.status}


@router.post("/opportunities/run")
def trigger_scan(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    from app.services.scanner import run_scan

    run = run_scan(db, trigger="manual")
    audit(db, "scan.manual", user.id, "recommendation_run", run.id)
    db.commit()
    return {"run": run_dto(run)}


@router.get("/opportunities/runs")
def runs(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    return [run_dto(r) for r in db.scalars(select(ScanRun).order_by(ScanRun.generated_at.desc()).limit(limit))]


@router.get("/recommendations")
def history(symbol: str | None = None, from_: date | None = Query(None, alias="from"),
            to: date | None = None, limit: int = Query(200, le=1000), db: Session = Depends(get_db)) -> list[dict]:
    q = select(Recommendation).order_by(Recommendation.session_date.desc(), Recommendation.rank)
    if symbol:
        q = q.join(Stock, Stock.id == Recommendation.stock_id).where(Stock.symbol == symbol.upper())
    if from_:
        q = q.where(Recommendation.session_date >= from_)
    if to:
        q = q.where(Recommendation.session_date <= to)
    return [rec_dto(r) for r in db.scalars(q.limit(limit)).unique()]


@router.get("/recommendations/track-record")
def record(db: Session = Depends(get_db)) -> dict:
    return track_record(db)


@router.get("/recommendations/{rec_id}")
def get_rec(rec_id: int, db: Session = Depends(get_db)) -> dict:
    r = db.get(Recommendation, rec_id)
    if r is None:
        raise not_found("Recommendation")
    d = rec_dto(r)
    d["run"] = run_dto(db.get(ScanRun, r.run_id))
    return d


