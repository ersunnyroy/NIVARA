"""Watchlists, alerts and news."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.engine import ALERT_TYPES
from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.core.timeutil import utcnow
from app.models import Alert, AlertEvent, NewsItem, Recommendation, Signal, User, Watchlist, WatchlistItem
from app.schemas.dto import price_dto, row
from app.services.prices import current_prices, stock_by_symbol

router = APIRouter(tags=["watchlists", "alerts", "news"])
DEFAULT_LISTS = [("My Watchlist", "custom"), ("Momentum", "momentum"), ("Breakouts", "breakouts"),
                 ("Long term", "long_term"), ("F&O", "fno"), ("Earnings", "earnings")]


def _ensure_defaults(db: Session, user: User) -> None:
    if db.scalar(select(Watchlist).where(Watchlist.user_id == user.id).limit(1)) is None:
        for name, kind in DEFAULT_LISTS:
            db.add(Watchlist(user_id=user.id, name=name, kind=kind, created_at=utcnow()))
        db.commit()


def _own(db: Session, user: User, wid: int) -> Watchlist:
    w = db.get(Watchlist, wid)
    if w is None or w.user_id != user.id:
        raise not_found("Watchlist")
    return w


@router.get("/watchlists")
def lists(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    _ensure_defaults(db, user)
    return [{"id": w.id, "name": w.name, "kind": w.kind, "count": len(w.items)}
            for w in db.scalars(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.id))]


class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field("custom", max_length=20)


@router.post("/watchlists", status_code=201)
def create_list(body: WatchlistIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.name == body.name)):
        raise bad_request("A watchlist with this name exists")
    w = Watchlist(user_id=user.id, name=body.name, kind=body.kind, created_at=utcnow())
    db.add(w)
    db.commit()
    return {"id": w.id, "name": w.name, "kind": w.kind, "count": 0}


@router.delete("/watchlists/{wid}")
def delete_list(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(_own(db, user, wid))
    db.commit()
    return {"ok": True}


@router.get("/watchlists/{wid}")
def get_list(wid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    w = _own(db, user, wid)
    ids = [i.stock_id for i in w.items]
    prices = current_prices(db, ids)
    items = []
    for i in w.items:
        sig = db.scalar(select(Signal).where(Signal.stock_id == i.stock_id).order_by(Signal.id.desc()).limit(1))
        rec = db.scalar(select(Recommendation).where(Recommendation.stock_id == i.stock_id)
                        .order_by(Recommendation.session_date.desc()).limit(1))
        cp = prices.get(i.stock_id)
        in_zone = bool(rec and cp and cp.price and rec.entry_low <= cp.price <= rec.entry_high)
        items.append({"symbol": i.stock.symbol, "name": i.stock.name, "sector": i.stock.industry,
                      "price": price_dto(cp) if cp else None, "change_pct": cp.change_pct if cp else None,
                      "score": sig.score if sig else None, "setup": sig.setup if sig else None,
                      "score_date": sig.session_date.isoformat() if sig else None, "in_entry_zone": in_zone,
                      "latest_recommendation": {"id": rec.id, "session_date": rec.session_date.isoformat(),
                                                "entry_low": rec.entry_low, "entry_high": rec.entry_high,
                                                "stop": rec.stop, "target1": rec.target1} if rec else None,
                      "notes": i.notes, "added_at": i.added_at.isoformat()})
    return {"id": w.id, "name": w.name, "kind": w.kind, "items": items}


class ItemIn(BaseModel):
    symbol: str
    notes: str | None = Field(None, max_length=2000)


@router.post("/watchlists/{wid}/items", status_code=201)
def add_item(wid: int, body: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    w = _own(db, user, wid)
    st = stock_by_symbol(db, body.symbol)
    if st is None:
        raise not_found(f"Stock {body.symbol}")
    if any(i.stock_id == st.id for i in w.items):
        return {"ok": True, "duplicate": True}
    db.add(WatchlistItem(watchlist_id=w.id, stock_id=st.id, notes=body.notes, added_at=utcnow()))
    db.commit()
    return {"ok": True}


@router.delete("/watchlists/{wid}/items/{symbol}")
def remove_item(wid: int, symbol: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    w = _own(db, user, wid)
    for i in list(w.items):
        if i.stock.symbol == symbol.upper():
            db.delete(i)
    db.commit()
    return {"ok": True}


class AlertIn(BaseModel):
    symbol: str | None = None
    alert_type: str
    params: dict = {}
    channels: list[str] = ["in_app"]
    cooldown_minutes: int = Field(24 * 60, ge=5, le=60 * 24 * 30)


@router.get("/alerts")
def alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id.desc())).all()
    return {"types": ALERT_TYPES, "alerts": [row(a) | {"symbol": a.stock.symbol if a.stock else None} for a in rows]}


@router.post("/alerts", status_code=201)
def create_alert(body: AlertIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if body.alert_type not in ALERT_TYPES:
        raise bad_request(f"alert_type must be one of {ALERT_TYPES}")
    if body.alert_type != "regime_change" and not body.symbol:
        raise bad_request("This alert type needs a symbol")
    sid = None
    if body.symbol:
        st = stock_by_symbol(db, body.symbol)
        if st is None:
            raise not_found(f"Stock {body.symbol}")
        sid = st.id
    a = Alert(user_id=user.id, stock_id=sid, alert_type=body.alert_type, params=body.params, channels=body.channels,
              cooldown_minutes=body.cooldown_minutes, created_at=utcnow())
    db.add(a)
    db.commit()
    return row(a)


@router.delete("/alerts/{aid}")
def delete_alert(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    a = db.get(Alert, aid)
    if a is None or a.user_id != user.id:
        raise not_found("Alert")
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/alerts/events")
def events(unread: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    q = select(AlertEvent).where(AlertEvent.user_id == user.id).order_by(AlertEvent.triggered_at.desc()).limit(200)
    if unread:
        q = q.where(AlertEvent.read_at.is_(None))
    return [row(e) for e in db.scalars(q)]


@router.post("/alerts/events/{eid}/read")
def mark_read(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    e = db.get(AlertEvent, eid)
    if e is None or e.user_id != user.id:
        raise not_found("Event")
    e.read_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/news")
def news(symbol: str | None = None, event_type: str | None = None, tier: str | None = None,
         limit: int = Query(50, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    from app.api.routes.stocks import news_dto

    q = select(NewsItem).order_by(NewsItem.published_at.desc())
    if symbol:
        q = q.where(NewsItem.symbol == symbol.upper())
    if event_type:
        q = q.where(NewsItem.event_type == event_type)
    if tier:
        q = q.where(NewsItem.source_tier == tier)
    return [news_dto(db, n) for n in db.scalars(q.limit(limit))]


@router.post("/news/{nid}/analyze")
def analyze_news(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.ai.client import AIUnavailable
    from app.ai.news import analyze_news as run
    from app.api.routes.stocks import news_dto

    n = db.get(NewsItem, nid)
    if n is None:
        raise not_found("News item")
    try:
        run(db, n)
    except AIUnavailable as e:
        return news_dto(db, n) | {"ai_error": str(e)}
    return news_dto(db, n)


