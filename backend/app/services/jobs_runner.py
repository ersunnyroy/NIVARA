"""Named jobs runnable from the admin UI, the CLI or Celery."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import today_ist
from app.models import Stock

JOBS = ["seed", "securities", "holidays", "eod", "backfill", "fno", "fno_snapshots", "flows", "news",
        "corporate_actions", "event_calendar", "fundamentals", "breadth", "regime", "scan", "outcomes", "alerts",
        "paper", "pre_market", "post_market", "replay"]


def _d(v, default: date | None = None) -> date | None:
    return date.fromisoformat(v) if isinstance(v, str) and v else (v or default)


def run_named_job(db: Session, job: str, params: dict) -> dict:
    from app.services import ingestion
    from app.services.reference import seed_reference

    if job not in JOBS:
        raise ValueError(f"Unknown job {job!r}; choose from {JOBS}")
    if job == "seed":
        return seed_reference(db)
    if job == "securities":
        return ingestion.ingest_securities(db)
    if job == "holidays":
        return ingestion.ingest_holidays(db)
    if job in ("eod", "fno", "fno_snapshots", "breadth", "regime", "scan", "paper"):
        from app.market_calendar.calendar import load_calendar

        session = _d(params.get("date")) or date.fromisoformat(load_calendar(db).status()["last_completed_eod_session"])
        if job == "eod":
            return ingestion.ingest_eod(db, session)
        if job == "fno":
            return ingestion.ingest_fno(db, session)
        if job == "fno_snapshots":
            from app.services.fno_service import compute_snapshots

            return {"snapshots": compute_snapshots(db, session)}
        if job == "breadth":
            from app.services.market import compute_breadth

            b = compute_breadth(db, session)
            return {"advances": b.advances, "declines": b.declines} if b else {"error": "no data"}
        if job == "regime":
            from app.services.market import compute_and_store_regime

            r = compute_and_store_regime(db, session)
            return {"regime": r.regime, "confidence": r.confidence} if r else {"error": "index history missing"}
        if job == "scan":
            from app.services.scanner import run_scan

            run = run_scan(db, session, trigger=params.get("trigger", "manual"))
            return {"run_id": run.id, "status": run.status, "eligible": run.eligible_count, "notes": run.notes}
        if job == "paper":
            from app.paper.engine import process_paper_orders

            return process_paper_orders(db, session)
    if job == "backfill":
        end = _d(params.get("end"), today_ist() - timedelta(days=1))
        start = _d(params.get("start"), end - timedelta(days=int(params.get("days", 400))))
        return ingestion.backfill_eod(db, start, end)
    if job == "replay":
        return replay(db, _d(params.get("start")), _d(params.get("end")), int(params.get("every", 1)))
    if job == "flows":
        return ingestion.ingest_flows(db)
    if job == "news":
        return ingestion.ingest_news(db)
    if job == "corporate_actions":
        end = _d(params.get("end"), today_ist() + timedelta(days=30))
        return ingestion.ingest_corporate_actions(db, _d(params.get("start"), end - timedelta(days=400)), end)
    if job == "event_calendar":
        return ingestion.ingest_event_calendar(db)
    if job == "fundamentals":
        syms = params.get("symbols")
        if not syms:
            uni = params.get("universe", "nifty50")
            syms = [s.symbol for s in db.scalars(select(Stock)) if uni in (s.index_memberships or [])]
        return ingestion.ingest_fundamentals(db, syms)
    if job == "outcomes":
        from app.services.outcomes_service import update_outcomes

        return update_outcomes(db)
    if job == "alerts":
        from app.alerts.engine import evaluate_alerts

        return evaluate_alerts(db)
    if job == "pre_market":
        from app.workers.pipeline import pre_market

        return pre_market()
    if job == "post_market":
        from app.workers.pipeline import post_market

        return post_market(_d(params.get("date")))
    return {"error": "unhandled"}


def replay(db: Session, start: date | None, end: date | None, every: int = 1) -> dict:
    """Re-run the scanner for past sessions using only data available at each session (point-in-time).
    Runs are tagged trigger='replay' and reported separately from live recommendations."""
    from sqlalchemy import func

    from app.models import OHLCV, ScanRun
    from app.services.market import compute_and_store_regime, compute_breadth
    from app.services.outcomes_service import update_outcomes
    from app.services.scanner import run_scan

    days = [d for (d,) in db.execute(select(OHLCV.date).distinct().order_by(OHLCV.date))]
    end = end or db.scalar(select(func.max(OHLCV.date)))
    start = start or (days[-60] if len(days) > 60 else days[0])
    todo = [d for d in days if start <= d <= end][::max(every, 1)]
    done = []
    for d in todo:
        if db.scalar(select(ScanRun).where(ScanRun.trigger == "replay",
                                           ScanRun.data_as_of.is_not(None)).where(func.date(ScanRun.data_as_of) == d)):
            continue
        compute_breadth(db, d)
        compute_and_store_regime(db, d)
        run = run_scan(db, as_of=d, trigger="replay")
        done.append({"as_of": d.isoformat(), "status": run.status, "eligible": run.eligible_count})
    return {"replayed": len(done), "runs": done[-10:], "outcomes": update_outcomes(db)}
