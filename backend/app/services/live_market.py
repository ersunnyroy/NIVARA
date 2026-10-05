"""Intraday market snapshot from free NSE public endpoints (see app/data/nse/live.py).

Refreshed lazily when the app is used during market hours — at most once every REFRESH_SECONDS, in a background
thread so requests never wait on NSE. Stocks covered by the snapshot get a delayed quote in `prices`; all other
stocks keep showing the last official close (clearly labelled) until a broker feed is configured.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import session_scope
from app.core.timeutil import IST, utcnow
from app.data import registry
from app.data.nse.live import SOURCE, fetch_snapshot
from app.market_calendar.calendar import load_calendar
from app.models import AppSetting, PriceQuote, Stock
from app.schemas.dto import j

log = logging.getLogger(__name__)
REFRESH_SECONDS = 180
KEY = "live:market"
_lock = threading.Lock()
_last_attempt = 0.0


def _market_active(db: Session) -> bool:
    st = load_calendar(db).status()
    return st["phase"] in ("pre_open", "open") or (st["phase"] == "post_close" and st["is_trading_day"])


def refresh_now(db: Session) -> dict:
    snap = fetch_snapshot(registry.nse_client())
    if snap.as_of is None and not snap.quotes:
        return {"error": "; ".join(snap.warnings) or "no data"}
    smap = dict(db.execute(select(Stock.symbol, Stock.id).where(Stock.exchange_code == "NSE")).all())
    now = utcnow()
    n = 0
    for q in snap.quotes.values():
        sid = smap.get(q.symbol)
        if sid is None:
            continue
        db.add(PriceQuote(stock_id=sid, ts=q.ts, ltp=q.ltp, open=q.open, high=q.high, low=q.low, prev_close=q.prev_close,
                          volume=q.volume, vwap=None, source=SOURCE, retrieved_at=now, is_delayed=True))
        n += 1
    n500 = next((i for i in snap.indices if i.name == "NIFTY 500"), None)
    value = j({
        "as_of": snap.as_of, "retrieved_at": snap.retrieved_at, "source": SOURCE,
        "indices": [asdict(i) for i in snap.indices],
        "breadth_nifty500": {"advances": n500.advances, "declines": n500.declines} if n500 else None,
        "gainers": [asdict(snap.quotes[s]) for s in snap.gainers if s in snap.quotes][:10],
        "losers": [asdict(snap.quotes[s]) for s in snap.losers if s in snap.quotes][:10],
        "most_active": [asdict(snap.quotes[s]) for s in snap.most_active if s in snap.quotes][:10],
        "covered_stocks": n, "warnings": snap.warnings,
    })
    row = db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=value, updated_at=now))
    else:
        row.value, row.updated_at = value, now
    db.commit()
    return {"quotes": n, "indices": len(snap.indices), "as_of": value["as_of"], "warnings": snap.warnings}


def _worker() -> None:
    try:
        with session_scope() as db:
            res = refresh_now(db)
            log.info("live snapshot refreshed", extra={"result": res})
    except Exception as e:
        log.warning("live snapshot failed: %s", e)
    finally:
        _lock.release()


def maybe_refresh(db: Session) -> None:
    """Kick off a background refresh if the market is active and the snapshot is older than REFRESH_SECONDS."""
    global _last_attempt
    if time.monotonic() - _last_attempt < REFRESH_SECONDS:
        return
    try:
        if not _market_active(db):
            return
    except Exception:
        return
    if not _lock.acquire(blocking=False):
        return
    _last_attempt = time.monotonic()
    threading.Thread(target=_worker, name="nse-live-snapshot", daemon=True).start()


def live_market(db: Session) -> dict | None:
    """Latest snapshot if it belongs to today's session (IST)."""
    row = db.get(AppSetting, KEY)
    if row is None or not row.value.get("as_of"):
        return None
    from datetime import datetime

    as_of = datetime.fromisoformat(row.value["as_of"])
    if as_of.astimezone(IST).date() != utcnow().astimezone(IST).date():
        return None
    return row.value
