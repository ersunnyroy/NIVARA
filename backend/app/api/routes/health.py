from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.db import get_db
from app.core.timeutil import utcnow

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    out = {"status": "ok", "time": utcnow().isoformat(), "checks": {}}
    try:
        db.execute(text("SELECT 1"))
        out["checks"]["database"] = "ok"
    except Exception as e:
        out["checks"]["database"] = f"error: {type(e).__name__}"
        out["status"] = "degraded"
    try:
        import redis

        redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5).ping()
        out["checks"]["redis"] = "ok"
    except Exception as e:
        out["checks"]["redis"] = f"unavailable: {type(e).__name__}"
        out["status"] = "degraded"
    return out
