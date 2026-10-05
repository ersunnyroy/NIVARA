from __future__ import annotations

from datetime import date

from app.core.db import session_scope
from app.workers import pipeline
from app.workers.celery_app import celery


@celery.task(name="nivara.pre_market")
def pre_market() -> dict:
    return pipeline.pre_market()


@celery.task(name="nivara.intraday")
def intraday() -> dict:
    return pipeline.intraday()


@celery.task(name="nivara.post_market")
def post_market(session: str | None = None) -> dict:
    return pipeline.post_market(date.fromisoformat(session) if session else None)


@celery.task(name="nivara.news")
def news() -> dict:
    from app.services.ingestion import ingest_news

    with session_scope() as db:
        return ingest_news(db)


@celery.task(name="nivara.securities")
def securities() -> dict:
    from app.services.ingestion import ingest_securities

    with session_scope() as db:
        return ingest_securities(db)


@celery.task(name="nivara.fundamentals_refresh")
def fundamentals_refresh(universe: str = "nifty500") -> dict:
    from sqlalchemy import select

    from app.models import Stock
    from app.services.ingestion import ingest_fundamentals

    with session_scope() as db:
        syms = [s.symbol for s in db.scalars(select(Stock)) if universe in (s.index_memberships or [])]
        return ingest_fundamentals(db, syms)


@celery.task(name="nivara.backfill")
def backfill(start: str, end: str) -> dict:
    from app.services.ingestion import backfill_eod

    with session_scope() as db:
        return backfill_eod(db, date.fromisoformat(start), date.fromisoformat(end))


@celery.task(name="nivara.backtest")
def run_backtest(backtest_id: int) -> dict:
    from app.backtesting.service import execute_backtest

    with session_scope() as db:
        return execute_backtest(db, backtest_id)


@celery.task(name="nivara.job")
def run_job(job: str, params: dict | None = None) -> dict:
    from app.services.jobs_runner import run_named_job

    with session_scope() as db:
        return run_named_job(db, job, params or {})
