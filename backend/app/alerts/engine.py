"""Alert evaluation. Each alert type is a small rule over stored data; new types register in RULES."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.notifiers import dispatch
from app.core.timeutil import utcnow
from app.models import Alert, AlertEvent, MarketRegime, NewsItem, Recommendation, Signal, User
from app.services.prices import bars, current_price
from app.technical.indicators import relative_volume
from app.technical.patterns import detect_breakout

ALERT_TYPES = ["entry_zone", "stop", "target", "breakout", "breakdown", "unusual_volume", "major_news", "results",
               "price_move", "score_change", "regime_change", "price_above", "price_below"]


def _latest_rec(db: Session, stock_id: int) -> Recommendation | None:
    return db.scalar(select(Recommendation).where(Recommendation.stock_id == stock_id)
                     .order_by(Recommendation.session_date.desc()).limit(1))


def _rule(db: Session, a: Alert) -> tuple[str, str, dict] | None:
    p = a.params or {}
    if a.alert_type == "regime_change":
        rows = db.scalars(select(MarketRegime).order_by(MarketRegime.session_date.desc(), MarketRegime.id.desc()).limit(2)).all()
        if len(rows) == 2 and rows[0].regime != rows[1].regime:
            return ("Market regime changed", f"{rows[1].regime} → {rows[0].regime} (confidence {rows[0].confidence:.0f})",
                    {"from": rows[1].regime, "to": rows[0].regime, "session": rows[0].session_date.isoformat()})
        return None
    if a.stock_id is None:
        return None
    sym = a.stock.symbol
    cp = current_price(db, a.stock_id)
    if cp.price is None:
        return None
    px = cp.price
    stamp = {"price": px, "as_of": cp.as_of.isoformat() if cp.as_of else None, "kind": cp.kind}
    t = a.alert_type
    if t in ("price_above", "price_below"):
        lvl = float(p.get("level", 0))
        if (t == "price_above" and px >= lvl) or (t == "price_below" and px <= lvl):
            return (f"{sym} {'above' if t == 'price_above' else 'below'} ₹{lvl:,.2f}", f"Price ₹{px:,.2f} ({cp.kind})", stamp)
    if t in ("entry_zone", "stop", "target"):
        rec = _latest_rec(db, a.stock_id)
        lo, hi = p.get("entry_low", rec.entry_low if rec else None), p.get("entry_high", rec.entry_high if rec else None)
        stop, tgt = p.get("stop", rec.stop if rec else None), p.get("target", rec.target1 if rec else None)
        if t == "entry_zone" and lo and hi and lo <= px <= hi:
            return (f"{sym} in entry zone", f"₹{px:,.2f} within ₹{lo:,.2f}–₹{hi:,.2f}", stamp)
        if t == "stop" and stop and px <= stop:
            return (f"{sym} at/below stop", f"₹{px:,.2f} ≤ stop ₹{stop:,.2f}", stamp)
        if t == "target" and tgt and px >= tgt:
            return (f"{sym} reached target", f"₹{px:,.2f} ≥ target ₹{tgt:,.2f}", stamp)
        return None
    if t == "price_move" and cp.change_pct is not None and abs(cp.change_pct) >= float(p.get("pct", 5)):
        return (f"{sym} moved {cp.change_pct:+.2f}%", f"Price ₹{px:,.2f}", stamp)
    if t in ("breakout", "breakdown", "unusual_volume"):
        df = bars(db, a.stock_id, lookback_days=120)
        if len(df) < 25:
            return None
        if t == "unusual_volume":
            rv = float(relative_volume(df["volume"]).iloc[-1])
            if rv >= float(p.get("multiple", 2.5)):
                return (f"{sym} unusual volume", f"Volume {rv:.1f}× the 20-day average", stamp | {"rel_volume": rv})
            return None
        bo, bd = detect_breakout(df)
        det = bo if t == "breakout" else bd
        if det.detected:
            return (f"{sym} {t}", f"Close ₹{df['close'].iloc[-1]:,.2f} vs 20-day {'high' if t == 'breakout' else 'low'} ₹{det.level:,.2f}",
                    stamp | det.details)
        return None
    if t in ("major_news", "results"):
        since = a.last_triggered_at or (utcnow() - timedelta(days=1))
        q = select(NewsItem).where(NewsItem.stock_id == a.stock_id, NewsItem.retrieved_at > since)
        q = q.where(NewsItem.event_type == "earnings") if t == "results" else q.where(NewsItem.impact.in_(["medium", "high"]))
        n = db.scalar(q.order_by(NewsItem.published_at.desc()).limit(1))
        if n:
            return (f"{sym}: {n.event_type.replace('_', ' ')}", f"{n.headline[:200]} ({n.source})", {"news_id": n.id, "url": n.url})
        return None
    if t == "score_change":
        rows = db.scalars(select(Signal).where(Signal.stock_id == a.stock_id).order_by(Signal.id.desc()).limit(2)).all()
        if len(rows) == 2 and abs(rows[0].score - rows[1].score) >= float(p.get("points", 10)):
            return (f"{sym} score changed", f"{rows[1].score:.0f} → {rows[0].score:.0f}", {"from": rows[1].score, "to": rows[0].score})
    return None


RULES: dict[str, Callable] = dict.fromkeys(ALERT_TYPES, _rule)


def evaluate_alerts(db: Session) -> dict:
    now = utcnow()
    fired = 0
    for a in db.scalars(select(Alert).where(Alert.is_active.is_(True))).all():
        if a.last_triggered_at and now - a.last_triggered_at < timedelta(minutes=a.cooldown_minutes):
            continue
        hit = RULES.get(a.alert_type, _rule)(db, a)
        if not hit:
            continue
        title, msg, data = hit
        user = db.get(User, a.user_id)
        delivery = dispatch(a.channels or ["in_app"], user.email if user else None, title, msg, data)
        db.add(AlertEvent(alert_id=a.id, user_id=a.user_id, alert_type=a.alert_type, title=title, message=msg,
                          data=data, triggered_at=now, delivery=delivery))
        a.last_triggered_at = now
        if (a.params or {}).get("once"):
            a.is_active = False
        fired += 1
    db.commit()
    return {"fired": fired}
