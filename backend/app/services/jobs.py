"""Ingestion-run bookkeeping and data-source status updates."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import DataSource, IngestionRun

log = logging.getLogger(__name__)


class JobContext:
    def __init__(self, run: IngestionRun):
        self.run = run
        self.rows = 0
        self.details: dict = {}
        self.status = "ok"


@contextmanager
def job(db: Session, name: str, source_key: str | None = None):
    run = IngestionRun(job=name, started_at=utcnow(), status="running", rows=0, details={})
    db.add(run)
    db.commit()
    ctx = JobContext(run)
    try:
        yield ctx
        run.status = ctx.status
        run.rows = ctx.rows
        as_of = ctx.details.get("data_as_of_dt")
        run.details = {k: v for k, v in ctx.details.items() if k != "data_as_of_dt"}
        run.finished_at = utcnow()
        if source_key and ctx.status in ("ok", "partial"):
            mark_source(db, source_key, ok=True, data_as_of=as_of)
        db.commit()
    except Exception as e:
        db.rollback()
        run = db.merge(run)
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"[:2000]
        run.finished_at = utcnow()
        run.details = {k: v for k, v in ctx.details.items() if k != "data_as_of_dt"}
        if source_key:
            mark_source(db, source_key, ok=False, error=run.error)
        db.commit()
        log.warning("job failed", extra={"job": name, "error": run.error})
        raise


def mark_source(db: Session, key: str, ok: bool, error: str | None = None, data_as_of: datetime | None = None) -> None:
    src = db.scalar(select(DataSource).where(DataSource.key == key))
    if src is None:
        return
    if ok:
        src.last_success_at = utcnow()
        if data_as_of:
            src.last_data_as_of = data_as_of
    else:
        src.last_error_at = utcnow()
        src.last_error = (error or "")[:2000]
