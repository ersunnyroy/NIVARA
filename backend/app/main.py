"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config.settings import get_settings
from app.core.logging import configure_logging, request_id_var
from app.core.ratelimit import limiter

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
log = logging.getLogger("nivara.http")

if settings.sentry_dsn:  # optional error tracking
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.05)
    except ImportError:  # pragma: no cover
        log.warning("SENTRY_DSN set but sentry-sdk not installed")

app = FastAPI(
    title="NIVARA — Indian Stock Intelligence API",
    version="0.1.0",
    description="Decision-support research platform. Not investment advice; no guaranteed returns.",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["content-type", "x-csrf-token", "authorization"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        ip = request.client.host if request.client else "?"
        if request.url.path.startswith(settings.api_prefix) and not request.url.path.endswith("/health"):
            ok, _ = limiter.hit(f"api:{ip}", settings.rate_limit_per_minute)
            if not ok:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"path": request.url.path})
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    finally:
        request_id_var.reset(token)
    ms = (time.perf_counter() - start) * 1000
    response.headers["x-request-id"] = rid
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["x-frame-options"] = "DENY"
    response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith(settings.api_prefix):
        response.headers["cache-control"] = "no-store"
    log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                               "ms": round(ms, 1)})
    return response


app.include_router(api_router, prefix=settings.api_prefix)
