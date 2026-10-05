"""Daily pipeline stages. Each stage is safe to re-run; failures in one step don't block the others,
and the scan refuses to produce recommendations from missing/stale data."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.core.db import session_scope
from app.core.timeutil import now_ist
from app.market_calendar.calendar import load_calendar

log = logging.getLogger(__name__)


def _step(results: dict, name: str, fn, *args, **kwargs):
    try:
        results[name] = fn(*args, **kwargs)
    except Exception as e:
        log.warning("pipeline step %s failed: %s", name, e)
        results[name] = {"error": f"{type(e).__name__}: {e}"}
    return results[name]


def pre_market() -> dict:
    """Before market: calendar, flows, corporate events, announcements, F&O analytics for last session."""
    from app.services import ingestion
    from app.services.fno_service import compute_snapshots

    out: dict = {}
    with session_scope() as db:
        cal = load_calendar(db)
        today = now_ist().date()
        last = cal.previous_trading_day(today) if cal.is_trading_day(today) else cal.previous_trading_day(today + timedelta(days=1))
        _step(out, "holidays", ingestion.ingest_holidays, db)
        _step(out, "flows", ingestion.ingest_flows, db)
        _step(out, "corporate_actions", ingestion.ingest_corporate_actions, db, today - timedelta(days=7), today + timedelta(days=30))
        _step(out, "event_calendar", ingestion.ingest_event_calendar, db)
        _step(out, "news", ingestion.ingest_news, db)
        _step(out, "fno_snapshots", compute_snapshots, db, last)
    return out


def intraday() -> dict:
    """During market: refresh quotes (only if a real-time provider is configured), news, alerts."""
    from app.alerts.engine import evaluate_alerts
    from app.services import ingestion
    from app.services.quotes import refresh_quotes

    out: dict = {}
    with session_scope() as db:
        cal = load_calendar(db)
        if not cal.status()["is_open"]:
            return {"skipped": "market closed"}
        _step(out, "quotes", refresh_quotes, db)
        _step(out, "news", ingestion.ingest_news, db)
        _step(out, "alerts", evaluate_alerts, db)
    return out


def post_market(session: date | None = None) -> dict:
    """After market: EOD prices, F&O, breadth/sectors/regime, final scan, outcomes, alerts, snapshots."""
    from app.alerts.engine import evaluate_alerts
    from app.paper.engine import process_paper_orders
    from app.services import ingestion
    from app.services.fno_service import compute_snapshots
    from app.services.market import compute_and_store_regime, compute_breadth
    from app.services.outcomes_service import update_outcomes
    from app.services.scanner import run_scan

    out: dict = {}
    with session_scope() as db:
        cal = load_calendar(db)
        st = cal.status()
        session = session or date.fromisoformat(st["last_completed_eod_session"])
        if not cal.is_trading_day(session):
            return {"skipped": f"{session} is not a trading day"}
        out["session"] = session.isoformat()
        _step(out, "eod", ingestion.ingest_eod, db, session)
        _step(out, "fno", ingestion.ingest_fno, db, session)
        _step(out, "fno_snapshots", compute_snapshots, db, session)
        _step(out, "flows", ingestion.ingest_flows, db)
        _step(out, "breadth", lambda: bool(compute_breadth(db, session)))
        _step(out, "regime", lambda: getattr(compute_and_store_regime(db, session), "regime", None))
        _step(out, "outcomes", update_outcomes, db)
        _step(out, "scan", lambda: _scan_summary(run_scan(db, session, trigger="scheduled")))
        _step(out, "paper", process_paper_orders, db, session)
        _step(out, "alerts", evaluate_alerts, db)
    return out


def _scan_summary(run) -> dict:
    return {"run_id": run.id, "status": run.status, "eligible": run.eligible_count, "notes": run.notes}
