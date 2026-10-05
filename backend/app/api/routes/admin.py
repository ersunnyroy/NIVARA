"""Settings (read: any user; write: admin) and admin endpoints: system health, data sources, users, jobs."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.analytics.config import DEFAULTS, load_config, validate_weights
from app.api.deps import client_ip, get_current_user, require_admin
from app.config.settings import get_settings
from app.core.audit import audit
from app.core.db import get_db, session_scope
from app.core.errors import bad_request, not_found
from app.core.security import hash_password, password_problems
from app.core.timeutil import utcnow
from app.market_calendar.calendar import load_calendar
from app.models import AppSetting, AuditLog, DataSource, IngestionRun, User
from app.schemas.dto import j, row
from app.services.jobs_runner import JOBS

log = logging.getLogger(__name__)
router = APIRouter(tags=["settings", "admin"])

CREDENTIALS = {
    "upstox_quotes": {"env": ["UPSTOX_ACCESS_TOKEN"], "attr": ["upstox_access_token"]},
    "kite_quotes": {"env": ["KITE_API_KEY", "KITE_ACCESS_TOKEN"], "attr": ["kite_api_key", "kite_access_token"]},
    "anthropic_ai": {"env": ["ANTHROPIC_API_KEY"], "attr": ["anthropic_api_key"]},
    "rss_secondary": {"env": ["NEWS_RSS_FEEDS"], "attr": ["news_rss_feeds"]},
}
EOD_KEYS = {"nse_cm_bhavcopy", "nse_indices", "nse_fo_bhavcopy"}


@router.get("/settings")
def get_settings_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    cfg = load_config(db)
    return {"config": cfg, "defaults": DEFAULTS, "editable": user.role == "admin",
            "versions": {r.key: r.version for r in db.scalars(select(AppSetting)) if r.key in DEFAULTS}}


@router.put("/settings/{key}")
def put_setting(key: str, value: dict, request: Request, user: User = Depends(require_admin),
                db: Session = Depends(get_db)) -> dict:
    if key not in DEFAULTS:
        raise bad_request(f"Unknown settings key; choose from {sorted(DEFAULTS)}")
    if key == "scoring_weights":
        try:
            value = validate_weights(value)
        except ValueError as e:
            raise bad_request(str(e)) from e
    s = db.get(AppSetting, key)
    if s is None:
        s = AppSetting(key=key, value=value, version=1, updated_at=utcnow(), updated_by=user.id)
        db.add(s)
    else:
        s.value, s.version, s.updated_at, s.updated_by = value, s.version + 1, utcnow(), user.id
    audit(db, "settings.update", user.id, "app_setting", key, {"value": value}, client_ip(request))
    db.commit()
    note = None
    if key == "scoring_weights":
        note = ("New weights apply to future scans. Historical recommendations keep the weights and scoring "
                "version recorded with them.")
    return {"key": key, "value": s.value, "version": s.version, "note": note}


def _status(src: DataSource, last_eod: date) -> str:
    if not src.is_enabled:
        return "DISABLED"
    if src.last_success_at is None:
        return "RED" if src.last_error_at else "YELLOW"
    if src.last_error_at and src.last_error_at > src.last_success_at:
        return "YELLOW"
    if src.key in EOD_KEYS:
        d = src.last_data_as_of.date() if src.last_data_as_of else None
        return "GREEN" if d and d >= last_eod else "YELLOW"
    age = (utcnow() - src.last_success_at).total_seconds() / 60
    return "GREEN" if age <= src.freshness_sla_minutes else "YELLOW" if age <= 3 * src.freshness_sla_minutes else "RED"


def _configured(key: str) -> bool | None:
    spec = CREDENTIALS.get(key)
    if not spec:
        return None
    s = get_settings()
    return all(bool(getattr(s, a)) for a in spec["attr"])


@router.get("/admin/system-health")
def health(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    cal = load_calendar(db)
    last_eod = date.fromisoformat(cal.status()["last_completed_eod_session"])
    comps = []
    for s in db.scalars(select(DataSource).order_by(DataSource.kind, DataSource.key)):
        st = _status(s, last_eod)
        if s.requires_credentials and not _configured(s.key):
            st = "DISABLED"
        comps.append({"key": s.key, "name": s.name, "kind": s.kind, "provider": s.provider, "status": st,
                      "last_success_at": j(s.last_success_at), "last_data_as_of": j(s.last_data_as_of),
                      "last_error_at": j(s.last_error_at), "last_error": s.last_error,
                      "sla_minutes": s.freshness_sla_minutes, "requires_credentials": s.requires_credentials,
                      "configured": _configured(s.key)})
    workers = {"status": "unknown"}
    try:
        from app.workers.celery_app import celery

        pong = celery.control.ping(timeout=1.0)
        workers = {"status": "GREEN" if pong else "RED", "workers": [next(iter(p)) for p in pong]}
    except Exception as e:
        workers = {"status": "RED", "error": type(e).__name__}
    dbinfo: dict = {}
    try:
        if db.get_bind().dialect.name == "postgresql":
            dbinfo["size"] = db.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
        for t in ("ohlcv", "index_ohlcv", "recommendations", "news", "financial_results", "option_chain"):
            dbinfo[f"rows_{t}"] = db.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        dbinfo["status"] = "GREEN"
    except Exception as e:
        dbinfo = {"status": "RED", "error": type(e).__name__}
    runs = db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(40)).all()
    group = {"market_data": "Market data", "fundamentals": "Fundamental data", "news": "News", "fno": "F&O",
             "ai": "AI", "flows": "FII/DII flows", "calendar": "Calendar", "reference": "Reference data",
             "corporate_actions": "Corporate actions"}
    rank = {"RED": 3, "YELLOW": 2, "GREEN": 1, "DISABLED": 0}
    summary: dict[str, str] = {}
    for c in comps:
        g = group.get(c["kind"], c["kind"])
        if c["status"] == "DISABLED" and g in summary:
            continue
        if g not in summary or (rank[c["status"]] > rank[summary[g]] and c["status"] != "DISABLED") or summary[g] == "DISABLED":
            summary[g] = c["status"]
    return {"summary": summary, "components": comps, "workers": workers, "database": dbinfo,
            "calendar": cal.status(), "ingestion_runs": [row(r) for r in runs]}


@router.get("/admin/data-sources")
def data_sources(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for s in db.scalars(select(DataSource).order_by(DataSource.kind)):
        d = row(s, {"encrypted_secret"})
        spec = CREDENTIALS.get(s.key)
        d["required_env"] = spec["env"] if spec else []
        d["configured"] = _configured(s.key)
        out.append(d)
    return out


class SourceUpdate(BaseModel):
    is_enabled: bool | None = None
    freshness_sla_minutes: int | None = Field(None, ge=1, le=60 * 24 * 60)


@router.put("/admin/data-sources/{key}")
def update_source(key: str, body: SourceUpdate, request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)) -> dict:
    s = db.scalar(select(DataSource).where(DataSource.key == key))
    if s is None:
        raise not_found("Data source")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    audit(db, "data_source.update", user.id, "data_source", key, body.model_dump(exclude_none=True), client_ip(request))
    db.commit()
    return row(s, {"encrypted_secret"})


class UserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    full_name: str | None = None
    role: str = Field("user", pattern="^(user|admin)$")


@router.get("/admin/users")
def users(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    return [row(u, {"password_hash"}) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/admin/users", status_code=201)
def create_user(body: UserIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise bad_request("User exists")
    probs = password_problems(body.password)
    if probs:
        raise HTTPException(422, "Password needs " + ", ".join(probs))
    u = User(email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name, role=body.role)
    db.add(u)
    db.flush()
    audit(db, "user.create", user.id, "user", u.id, {"email": u.email, "role": u.role}, client_ip(request))
    db.commit()
    return row(u, {"password_hash"})


@router.post("/admin/users/{uid}/deactivate")
def deactivate(uid: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, uid)
    if u is None:
        raise not_found("User")
    if u.id == user.id:
        raise bad_request("You cannot deactivate yourself")
    u.is_active = False
    audit(db, "user.deactivate", user.id, "user", uid, ip=client_ip(request))
    db.commit()
    return {"ok": True}


def _run_job_sync(job: str, params: dict) -> None:
    from app.services.jobs_runner import run_named_job

    try:
        with session_scope() as db:
            run_named_job(db, job, params)
    except Exception:
        log.exception("background job %s failed", job)


@router.post("/admin/jobs/{job}")
def trigger_job(job: str, request: Request, background: BackgroundTasks, params: dict | None = None,
                user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    if job not in JOBS:
        raise bad_request(f"Unknown job; choose from {JOBS}")
    params = params or {}
    audit(db, "job.trigger", user.id, "job", job, params, client_ip(request))
    db.commit()
    try:
        from app.workers.celery_app import celery

        if celery.control.ping(timeout=0.5):
            res = celery.send_task("nivara.job", args=[job, params])
            return {"queued": True, "via": "celery", "task_id": res.id}
    except Exception:
        pass
    background.add_task(_run_job_sync, job, params)
    return {"queued": True, "via": "in-process background task (no Celery worker reachable)"}


@router.get("/admin/jobs")
def job_list(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    since = utcnow() - timedelta(days=7)
    runs = db.scalars(select(IngestionRun).where(IngestionRun.started_at >= since)
                      .order_by(IngestionRun.started_at.desc()).limit(100)).all()
    return {"jobs": JOBS, "recent_runs": [row(r) for r in runs],
            "counts": dict(db.execute(select(IngestionRun.status, func.count()).where(IngestionRun.started_at >= since)
                                      .group_by(IngestionRun.status)).all())}


@router.get("/admin/audit-logs")
def audit_logs(limit: int = 200, user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    return [row(a) for a in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 1000)))]


@router.get("/admin/charges")
def charges(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    from app.models import ChargeSchedule

    return [row(c) for c in db.scalars(select(ChargeSchedule).order_by(ChargeSchedule.effective_from))]


@router.get("/meta/disclaimers")
def disclaimers() -> dict:
    from app.tax.common import DISCLAIMER

    return {
        "general": "Research & decision-support only. Not investment advice. No returns are guaranteed.",
        "tax": DISCLAIMER,
        "backtest": "Backtest results are simulated on historical data and do not guarantee future performance.",
        "regulatory": ("Personal research tool. Offering personalised recommendations to others may require SEBI "
                       "registration (Investment Adviser / Research Analyst). Automated order placement is not "
                       "implemented."),
    }
