"""Paper trading — simulated orders only. NEVER places real orders.

Fills use only data available after the order was placed: orders are filled against the first EOD bar
of a session that starts after the order's creation time (MARKET at that open; LIMIT BUY if the bar
trades at/below the limit, at min(open, limit)). Stops/targets on paper positions are checked on later
bars with the same conservative rules as the recommendation tracker (stop first, gaps fill at open).

A per-user "model" portfolio can auto-follow every BUY recommendation (system trades) so model
performance can be compared with the user's own paper/live decisions.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.config import load_config
from app.analytics.levels import position_size
from app.core.timeutil import IST, ist_datetime, utcnow
from app.market_calendar.calendar import OPEN, load_calendar
from app.models import OHLCV, AppSetting, PaperOrder, Portfolio, Recommendation, Stock, Trade, Transaction
from app.services.portfolio_service import add_transaction

DEFAULT_CAPITAL = Decimal("1000000")


def get_portfolio(db: Session, user_id: int, kind: str = "paper") -> Portfolio:
    p = db.scalar(select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.kind == kind))
    if p is None:
        p = Portfolio(user_id=user_id, name="Paper portfolio" if kind == "paper" else "Model portfolio (auto)",
                      kind=kind, starting_cash=DEFAULT_CAPITAL, broker="paper")
        db.add(p)
        db.flush()
    return p


def cash(db: Session, p: Portfolio) -> Decimal:
    c = Decimal(p.starting_cash or DEFAULT_CAPITAL)
    for t in db.scalars(select(Transaction).where(Transaction.portfolio_id == p.id)):
        amt = Decimal(t.quantity) * Decimal(t.price)
        c += (-amt if t.side == "BUY" else amt) - Decimal(t.charges_total or 0)
    return c


def follow_model_enabled(db: Session, user_id: int) -> bool:
    s = db.get(AppSetting, f"paper:{user_id}")
    return bool(s and s.value.get("follow_model"))


def set_follow_model(db: Session, user_id: int, enabled: bool) -> None:
    s = db.get(AppSetting, f"paper:{user_id}")
    if s is None:
        s = AppSetting(key=f"paper:{user_id}", value={}, updated_at=utcnow(), updated_by=user_id)
        db.add(s)
    s.value = {**(s.value or {}), "follow_model": enabled}
    s.updated_at = utcnow()


def place_order(db: Session, p: Portfolio, stock: Stock, side: str, qty: Decimal, order_type: str = "MARKET",
                limit_price: float | None = None, stop: float | None = None, target: float | None = None,
                valid_sessions: int = 3, recommendation_id: int | None = None) -> PaperOrder:
    if p.kind not in ("paper", "model"):
        raise ValueError("Paper orders are only allowed on paper/model portfolios")
    if qty <= 0:
        raise ValueError("Quantity must be positive")
    if order_type == "LIMIT" and not limit_price:
        raise ValueError("LIMIT orders need a limit price")
    cal = load_calendar(db)
    valid = utcnow().astimezone(IST).date()
    for _ in range(valid_sessions):
        valid = cal.next_trading_day(valid)
    o = PaperOrder(portfolio_id=p.id, stock_id=stock.id, side=side.upper(), quantity=qty, order_type=order_type,
                   limit_price=limit_price, stop=stop, target=target, status="open", valid_till=valid,
                   created_at=utcnow(), recommendation_id=recommendation_id)
    db.add(o)
    db.flush()
    return o


def _bar(db: Session, stock_id: int, d: date) -> OHLCV | None:
    return db.get(OHLCV, {"stock_id": stock_id, "date": d})


def process_paper_orders(db: Session, session: date) -> dict:
    """Fill/expire open paper orders on `session`'s bar, then manage stops/targets of open paper trades."""
    filled = expired = exits = 0
    session_open = ist_datetime(session, OPEN.hour, OPEN.minute)
    for o in db.scalars(select(PaperOrder).where(PaperOrder.status == "open")).all():
        if o.created_at.astimezone(IST) >= session_open:
            continue  # placed after this session opened → not eligible for this bar (no look-ahead)
        b = _bar(db, o.stock_id, session)
        if b is None:
            if o.valid_till and session > o.valid_till:
                o.status, expired = "expired", expired + 1
            continue
        px = None
        if o.order_type == "MARKET":
            px = b.open
        elif o.side == "BUY" and b.low <= o.limit_price:
            px = min(b.open, o.limit_price)
        elif o.side == "SELL" and b.high >= o.limit_price:
            px = max(b.open, o.limit_price)
        if px is None:
            if o.valid_till and session >= o.valid_till:
                o.status, expired = "expired", expired + 1
            continue
        p = db.get(Portfolio, o.portfolio_id)
        if o.side == "BUY" and Decimal(str(px)) * Decimal(o.quantity) > cash(db, p):
            o.status, o.fill_note = "cancelled", "Insufficient paper cash"
            continue
        t = add_transaction(db, p, o.stock, o.side, Decimal(o.quantity), Decimal(str(round(px, 2))), session,
                            source="paper", notes=f"paper order #{o.id}")
        o.status, o.fill_price, o.filled_at, o.transaction_id = "filled", round(px, 2), utcnow(), t.id
        o.fill_note = "Filled on EOD bar (open/limit rule)"
        if o.side == "BUY":
            rec = db.get(Recommendation, o.recommendation_id) if o.recommendation_id else None
            db.add(Trade(portfolio_id=p.id, stock_id=o.stock_id, kind=p.kind if p.kind == "paper" else "system",
                         origin="system" if p.kind == "model" else "user", status="open", entry_date=session,
                         entry_price=Decimal(str(round(px, 2))), quantity=o.quantity, stop=o.stop, target=o.target,
                         recommendation_id=o.recommendation_id, market_regime=rec.market_regime if rec else None,
                         score_at_entry=rec.score if rec else None,
                         reason_entry=(rec.setup if rec else "Manual paper order")))
        filled += 1
    # Stops / targets on open paper & model trades (bars strictly after the entry session).
    for tr in db.scalars(select(Trade).where(Trade.status == "open", Trade.kind.in_(["paper", "system"]))).all():
        if session <= tr.entry_date:
            continue
        b = _bar(db, tr.stock_id, session)
        if b is None:
            continue
        exit_px = reason = None
        if tr.stop and b.low <= tr.stop:
            exit_px, reason = min(b.open, tr.stop), "Stop loss hit"
        elif tr.target and b.high >= tr.target:
            exit_px, reason = max(b.open, tr.target), "Target reached"
        if exit_px is None:
            continue
        p = db.get(Portfolio, tr.portfolio_id)
        t = add_transaction(db, p, tr.stock, "SELL", Decimal(tr.quantity), Decimal(str(round(exit_px, 2))), session,
                            source="paper", notes=f"auto exit: {reason}")
        close_trade(db, tr, session, Decimal(str(round(exit_px, 2))), reason, t)
        exits += 1
    follow = follow_model(db, session)
    db.commit()
    return {"filled": filled, "expired": expired, "exits": exits, "model_orders": follow}


def close_trade(db: Session, tr: Trade, exit_date: date, exit_price: Decimal, reason: str, sell_txn: Transaction) -> None:
    from app.services.portfolio_service import charges_engine

    qty = Decimal(tr.quantity)
    gross = (exit_price - Decimal(tr.entry_price)) * qty
    ce = charges_engine(db)
    buy = ce.compute("delivery", "BUY", qty, Decimal(tr.entry_price), "NSE", trade_date=tr.entry_date).rounded()
    charges = Decimal(str(buy.total)) + Decimal(sell_txn.charges_total or 0)
    tr.status, tr.exit_date, tr.exit_price, tr.reason_exit = "closed", exit_date, exit_price, reason
    tr.gross_pnl, tr.charges = gross, charges
    # Indicative per-trade tax at the applicable rate on positive gains (portfolio-level set-off and exemption
    # are handled in the Tax Center; this is labelled an estimate).
    from app.services.portfolio_service import rulebook
    from app.tax.engine import classify

    rb = rulebook(db)
    term = classify(tr.entry_date, exit_date, "listed_equity_stt_paid", rb)
    rule = rb.rule_for("listed_equity_stt_paid", term, exit_date)
    rate = Decimal(str(rule.rate or 0))
    tr.tax_estimate = max(gross - charges, Decimal("0")) * rate * (1 + Decimal(str(rule.cess_rate)))
    tr.net_pnl = gross - charges - tr.tax_estimate


def follow_model(db: Session, session: date) -> int:
    """For users with follow_model on: place limit orders for the latest BUY recommendations."""
    users = [int(s.key.split(":")[1]) for s in db.scalars(select(AppSetting).where(AppSetting.key.like("paper:%")))
             if s.value.get("follow_model")]
    if not users:
        return 0
    cfg = load_config(db)["risk_limits"]
    recs = db.scalars(select(Recommendation).where(Recommendation.session_date > session,
                                                   Recommendation.action == "BUY")).unique().all()
    n = 0
    for uid in users:
        p = get_portfolio(db, uid, "model")
        have = {o.recommendation_id for o in db.scalars(select(PaperOrder).where(PaperOrder.portfolio_id == p.id))}
        capital = float(cash(db, p))
        for r in recs:
            if r.id in have or capital <= 0:
                continue
            ps = position_size(float(p.starting_cash or DEFAULT_CAPITAL), float(cfg["risk_per_trade_pct"]),
                               r.entry_high, r.stop, max_position_pct=float(cfg["max_single_stock_pct"]))
            if ps.quantity <= 0 or ps.capital_required > capital:
                continue
            place_order(db, p, r.stock, "BUY", Decimal(ps.quantity), "LIMIT", r.entry_high, r.stop, r.target2,
                        valid_sessions=3, recommendation_id=r.id)
            capital -= ps.capital_required
            n += 1
    return n


