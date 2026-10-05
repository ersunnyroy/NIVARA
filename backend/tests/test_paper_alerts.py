from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models import OHLCV, Alert, AlertEvent, Trade, User
from app.paper import engine as paper
from tests.helpers import add_stock


def _user(db):
    u = User(email="p@example.com", password_hash="x", role="user")
    db.add(u)
    db.commit()
    return u


def test_paper_market_order_fills_next_session_open_only(db):
    st = add_stock(db, "PPP", n=40)
    u = _user(db)
    p = paper.get_portfolio(db, u.id, "paper")
    bars = db.scalars(select(OHLCV).where(OHLCV.stock_id == st.id).order_by(OHLCV.date)).all()
    o = paper.place_order(db, p, st, "BUY", Decimal(10), "MARKET", stop=bars[-1].low * 0.5, target=bars[-1].high * 3)
    # Pretend the order was placed the evening before bars[-2]'s session.
    o.created_at = utcnow().replace(year=bars[-2].date.year, month=bars[-2].date.month, day=bars[-2].date.day) - timedelta(days=1)
    db.commit()
    res = paper.process_paper_orders(db, bars[-2].date)
    assert res["filled"] == 1 and o.status == "filled" and o.fill_price == round(bars[-2].open, 2)
    assert paper.cash(db, p) < Decimal("1000000")
    tr = db.scalar(select(Trade).where(Trade.portfolio_id == p.id))
    assert tr.status == "open" and tr.kind == "paper"


def test_paper_rejects_live_portfolio(db):
    st = add_stock(db, "PPQ", n=10)
    u = _user(db)
    from app.models import Portfolio

    live = Portfolio(user_id=u.id, name="live", kind="live")
    db.add(live)
    db.commit()
    import pytest

    with pytest.raises(ValueError):
        paper.place_order(db, live, st, "BUY", Decimal(1))


def test_price_alert_fires_once_with_cooldown(db):
    from app.alerts.engine import evaluate_alerts

    st = add_stock(db, "ALR", n=30)
    u = _user(db)
    db.add(Alert(user_id=u.id, stock_id=st.id, alert_type="price_above", params={"level": 1.0}, channels=["in_app"],
                 created_at=utcnow()))
    db.commit()
    assert evaluate_alerts(db)["fired"] == 1
    assert evaluate_alerts(db)["fired"] == 0  # cooldown
    ev = db.scalar(select(AlertEvent))
    assert "ALR" in ev.title and ev.data["kind"] == "eod_close"
