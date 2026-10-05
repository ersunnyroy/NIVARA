"""Portfolio accounting: transactions → FIFO lots → realized gains, holdings valuation, net P&L after
charges and estimated tax, and position monitoring. Gross P&L is always shown next to net P&L."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics.levels import SetupContext, compute_levels
from app.core.timeutil import fy_of, today_ist, utcnow
from app.models import (
    ChargeSchedule,
    CorporateAction,
    EventCalendar,
    NewsItem,
    Portfolio,
    PortfolioPosition,
    RealizedGain,
    Recommendation,
    Stock,
    TaxLot,
    TaxProfile,
    TaxRule,
    Transaction,
)
from app.portfolio.lots import CorpActionIn, Lot, TxnIn, average_cost, build_lots
from app.portfolio.monitor import PositionState, evaluate_position
from app.services.market import latest_regime
from app.services.prices import bars, current_prices
from app.tax.charges import ChargesEngine
from app.tax.common import DISCLAIMER
from app.tax.defaults import basic_exemption_limits, regime_surcharge_caps
from app.tax.engine import (
    RealizedContext,
    TaxProfileIn,
    capital_gain_for_match,
    compute_tax_year,
    net_pnl,
    unrealized_tax_estimate,
)
from app.tax.rules import RuleBook, TaxRuleSpec
from app.technical.indicators import compute_all, latest_values
from app.technical.patterns import analyze_price_action

ZERO = Decimal("0")


# ------------------------------------------------------------------ engines from DB config
def rulebook(db: Session) -> RuleBook:
    rows = db.scalars(select(TaxRule).where(TaxRule.is_active.is_(True))).all()
    if not rows:
        return RuleBook.default()
    return RuleBook([TaxRuleSpec.coerce(r) for r in rows], exemption_limits=basic_exemption_limits(),
                    regime_surcharge_caps=regime_surcharge_caps())


def charges_engine(db: Session, portfolio: Portfolio | None = None) -> ChargesEngine:
    q = select(ChargeSchedule)
    rows = db.scalars(q).all()
    if portfolio and portfolio.charge_schedule_id:
        chosen = [r for r in rows if r.id == portfolio.charge_schedule_id or r.name == next(
            (x.name for x in rows if x.id == portfolio.charge_schedule_id), None)]
        rows = chosen or rows
    else:
        rows = [r for r in rows if r.is_default] or rows
    return ChargesEngine(rows) if rows else ChargesEngine.default()


def tax_profile(db: Session, user_id: int) -> TaxProfileIn:
    tp = db.get(TaxProfile, user_id)
    if tp is None:
        return TaxProfileIn()
    cf = tp.carried_forward or {}
    dec = lambda v: None if v is None else Decimal(str(v))
    return TaxProfileIn(residency=tp.residency, regime=tp.regime, other_taxable_income=tp.other_taxable_income,
                        slab_rate_for_business_income=tp.slab_rate_for_business_income,
                        carried_forward_stcl=dec(cf.get("STCL")), carried_forward_ltcl=dec(cf.get("LTCL")),
                        carried_forward_speculative=dec(cf.get("SPEC")))


# ------------------------------------------------------------------ transactions & lots
def estimate_charges(db: Session, portfolio: Portfolio, side: str, qty: Decimal, price: Decimal, trade_date: date,
                     segment: str, exchange: str) -> dict:
    br = charges_engine(db, portfolio).compute(segment, side.upper(), qty, price, exchange, trade_date=trade_date)
    r = br.rounded()
    return {"total": r.total, "breakdown": r.to_dict(), "stt": r.stt}


def add_transaction(db: Session, portfolio: Portfolio, stock: Stock, side: str, quantity: Decimal, price: Decimal,
                    trade_date: date, segment: str = "delivery", exchange: str = "NSE", broker: str | None = None,
                    charges_total: Decimal | None = None, notes: str | None = None, source: str = "manual",
                    trade_time: str | None = None, fmv_31jan2018: Decimal | None = None) -> Transaction:
    if quantity <= 0 or price <= 0:
        raise ValueError("Quantity and price must be positive")
    est = estimate_charges(db, portfolio, side, quantity, price, trade_date, segment, exchange)
    breakdown = dict(est["breakdown"])
    if charges_total is not None:
        breakdown["user_total"] = str(charges_total)
        breakdown["note"] = "Total entered by user; component split is an estimate from the charge schedule"
    t = Transaction(portfolio_id=portfolio.id, stock_id=stock.id, side=side.upper(), quantity=quantity, price=price,
                    trade_date=trade_date, trade_time=trade_time, segment=segment, exchange=exchange,
                    broker=broker or portfolio.broker,
                    charges_total=charges_total if charges_total is not None else Decimal(str(est["total"])),
                    charges_breakdown=_jsonable(breakdown),
                    charges_source="user" if charges_total is not None else "estimated", source=source, notes=notes,
                    fmv_31jan2018=fmv_31jan2018 if side.upper() == "BUY" else None, created_at=utcnow())
    db.add(t)
    db.flush()
    try:
        rebuild_lots(db, portfolio.id, stock.id)
    except ValueError:
        db.rollback()
        raise
    return t


def _jsonable(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _jsonable(v)
        elif isinstance(v, list):
            out[k] = [str(x) if isinstance(x, Decimal) else x for x in v]
        else:
            out[k] = v
    return out


def _stt_of(t: Transaction) -> Decimal:
    v = (t.charges_breakdown or {}).get("stt")
    return Decimal(str(v)) if v is not None else ZERO


def rebuild_lots(db: Session, portfolio_id: int, stock_id: int) -> None:
    """Recompute FIFO lots and realized gains for one holding from its full transaction history."""
    stock = db.get(Stock, stock_id)
    txns = db.scalars(select(Transaction).where(Transaction.portfolio_id == portfolio_id,
                                                Transaction.stock_id == stock_id)
                      .order_by(Transaction.trade_date, Transaction.id)).all()
    db.execute(delete(RealizedGain).where(RealizedGain.portfolio_id == portfolio_id, RealizedGain.stock_id == stock_id))
    db.execute(delete(TaxLot).where(TaxLot.portfolio_id == portfolio_id, TaxLot.stock_id == stock_id))
    db.flush()
    if not txns:
        return
    first = txns[0].trade_date
    cas = [CorpActionIn(stock.symbol, c.ex_date, c.action_type, c.ratio_from, c.ratio_to)
           for c in db.scalars(select(CorporateAction).where(CorporateAction.stock_id == stock_id,
                                                             CorporateAction.action_type.in_(["split", "bonus"]),
                                                             CorporateAction.ex_date > first))
           if c.ex_date and c.ratio_from and c.ratio_to]
    ins = [TxnIn(id=t.id, symbol=stock.symbol, side=t.side, quantity=Decimal(t.quantity), price=Decimal(t.price),
                 trade_date=t.trade_date, charges=Decimal(t.charges_total or 0), stt=_stt_of(t), segment=t.segment,
                 fmv_31jan2018=t.fmv_31jan2018)
           for t in txns]
    ledger = build_lots(ins, cas)
    lot_ids: dict[str, int] = {}
    for lot in ledger.lots:
        row = TaxLot(portfolio_id=portfolio_id, stock_id=stock_id, buy_transaction_id=lot.buy_txn_id,
                     is_bonus=lot.is_bonus, acquired_date=lot.acquired_date, quantity=lot.quantity,
                     remaining_quantity=lot.remaining_quantity, cost_per_share=lot.cost_per_share,
                     buy_charges=lot.buy_charges, buy_stt=lot.buy_stt, fmv_31jan2018=lot.fmv_31jan2018)
        db.add(row)
        db.flush()
        lot_ids[lot.lot_id] = row.id
    rb = rulebook(db)
    for m in ledger.matches:
        gl = capital_gain_for_match(m, rb)
        db.add(RealizedGain(
            portfolio_id=portfolio_id, stock_id=stock_id, sell_transaction_id=m.sell_txn_id, lot_id=lot_ids[m.lot_id],
            quantity=m.quantity, acquired_date=m.acquired_date, sold_date=m.sold_date,
            purchase_value=m.purchase_value, sale_value=m.sale_value, buy_charges=m.buy_charges_alloc,
            sell_charges=m.sell_charges_alloc, stt_total=m.stt_alloc, capital_gain=gl.capital_gain,
            trading_pnl=m.trading_pnl, holding_days=m.holding_days, term=gl.term, tax_year=gl.tax_year,
            flags=list(gl.flags) + [f"incomplete: {r}" for r in gl.incomplete_reasons]))
    db.flush()


def _ledger(db: Session, portfolio_id: int, stock_id: int, symbol: str) -> list[Lot]:
    """Open lots as engine objects (from persisted tax_lots)."""
    return [Lot(lot_id=str(r.id), symbol=symbol, segment="delivery", acquired_date=r.acquired_date,
                quantity=Decimal(r.quantity), remaining_quantity=Decimal(r.remaining_quantity),
                cost_per_share=Decimal(r.cost_per_share), buy_charges=Decimal(r.buy_charges or 0),
                buy_stt=Decimal(r.buy_stt or 0),
                buy_txn_id=r.buy_transaction_id, is_bonus=r.is_bonus, fmv_31jan2018=r.fmv_31jan2018)
            for r in db.scalars(select(TaxLot).where(TaxLot.portfolio_id == portfolio_id, TaxLot.stock_id == stock_id,
                                                     TaxLot.remaining_quantity > 0))]


# ------------------------------------------------------------------ realized
def realized_lines(db: Session, portfolio_ids: list[int], tax_year: str | None = None):
    from app.tax.engine import GainLine  # noqa: F401  (type reference)

    q = select(RealizedGain).where(RealizedGain.portfolio_id.in_(portfolio_ids))
    if tax_year:
        q = q.where(RealizedGain.tax_year == tax_year)
    return db.scalars(q.order_by(RealizedGain.sold_date)).all()


def gain_lines_from_rows(db: Session, rows) -> list:
    """Rebuild engine GainLines from persisted realized rows (re-derived via the engine for consistency)."""
    from app.portfolio.lots import Match

    rb = rulebook(db)
    lines = []
    for r in rows:
        lot = db.get(TaxLot, r.lot_id)
        sym = db.get(Stock, r.stock_id).symbol
        buy_stt = (Decimal(lot.buy_stt or 0) * Decimal(r.quantity) / Decimal(lot.quantity)
                   if lot and lot.quantity else ZERO)
        m = Match(lot_id=str(r.lot_id), buy_txn_id=lot.buy_transaction_id if lot else None,
                  sell_txn_id=r.sell_transaction_id, symbol=sym, segment="intraday" if r.term == "SPEC" else "delivery",
                  quantity=Decimal(r.quantity), acquired_date=r.acquired_date, sold_date=r.sold_date,
                  cost_per_share=Decimal(r.purchase_value) / Decimal(r.quantity) if r.quantity else ZERO,
                  sell_price=Decimal(r.sale_value) / Decimal(r.quantity) if r.quantity else ZERO,
                  purchase_value=Decimal(r.purchase_value), sale_value=Decimal(r.sale_value),
                  buy_charges_alloc=Decimal(r.buy_charges), sell_charges_alloc=Decimal(r.sell_charges),
                  buy_stt_alloc=buy_stt, sell_stt_alloc=Decimal(r.stt_total or 0) - buy_stt,
                  holding_days=r.holding_days,
                  is_bonus=bool(lot.is_bonus) if lot else False, fmv_31jan2018=lot.fmv_31jan2018 if lot else None)
        lines.append(capital_gain_for_match(m, rb))
    return lines


# ------------------------------------------------------------------ holdings
def holdings(db: Session, portfolio: Portfolio, user_id: int, include_monitor: bool = True) -> dict:
    lots = db.scalars(select(TaxLot).where(TaxLot.portfolio_id == portfolio.id, TaxLot.remaining_quantity > 0)).all()
    by_stock: dict[int, list[TaxLot]] = defaultdict(list)
    for lot in lots:
        by_stock[lot.stock_id].append(lot)
    prices = current_prices(db, list(by_stock))
    rb = rulebook(db)
    ce = charges_engine(db, portfolio)
    profile = tax_profile(db, user_id)
    as_of = today_ist()
    ty = fy_of(as_of)
    realized_rows = realized_lines(db, [portfolio.id], ty)
    realized_ctx = RealizedContext(gain_lines_from_rows(db, realized_rows), profile)
    regime = latest_regime(db)
    positions = []
    tot = defaultdict(lambda: Decimal("0"))
    for sid in by_stock:
        st = db.get(Stock, sid)
        open_lots = _ledger(db, portfolio.id, sid, st.symbol)
        ac = average_cost(open_lots)
        cp = prices.get(sid)
        qty = ac.quantity
        invested = ac.total_cost_incl_charges
        pos = {"stock_id": sid, "symbol": st.symbol, "name": st.name, "sector": st.industry,
               "quantity": float(qty), "avg_cost": float(ac.average_price),
               "avg_cost_incl_charges": float(ac.average_price_incl_charges), "invested": float(invested),
               "lots": [{"lot_id": int(lot.lot_id), "acquired_date": lot.acquired_date.isoformat(),
                         "quantity": float(lot.remaining_quantity), "cost_per_share": float(lot.cost_per_share),
                         "is_bonus": lot.is_bonus} for lot in open_lots],
               "price": None, "price_as_of": None, "price_kind": cp.kind if cp else "unavailable",
               "price_source": cp.source if cp else None}
        if cp and cp.price is not None:
            ltp = Decimal(str(cp.price))
            value = ltp * qty
            gross = value - ac.total_cost
            sell = ce.compute("delivery", "SELL", qty, ltp, "NSE", trade_date=as_of).rounded()
            unreal = unrealized_tax_estimate([(lot, ltp) for lot in open_lots], as_of, rb, realized_ctx,
                                             charges_engine=ce)
            est_tax = Decimal(str(unreal.estimated_tax_if_sold))
            buy_ch = sum((lot.buy_charges for lot in open_lots), ZERO)
            np_ = net_pnl(gross, buy_ch + Decimal(str(sell.total)), est_tax)
            pos.update(price=float(ltp), price_as_of=cp.as_of.isoformat() if cp.as_of else None,
                       day_change_pct=cp.change_pct, current_value=float(value), gross_pnl=float(gross),
                       gross_pnl_pct=float(100 * gross / ac.total_cost) if ac.total_cost else None,
                       charges_paid=float(buy_ch), est_exit_charges=float(sell.total),
                       est_tax_if_sold=float(est_tax), tax_status=unreal.status,
                       tax_incomplete_reasons=unreal.incomplete_reasons,
                       tax_terms=sorted({ln.term for ln in unreal.lots}),
                       net_pnl=float(np_.net_after_tax), net_pnl_pct=float(100 * np_.net_after_tax / invested) if invested else None)
            tot["value"] += value
            tot["gross"] += gross
            tot["charges"] += buy_ch + Decimal(str(sell.total))
            tot["tax"] += est_tax
        tot["invested"] += invested
        tot["cost"] += ac.total_cost
        if include_monitor and pos["price"] is not None:
            res, levels = _monitor(db, portfolio.id, st, pos, regime)
            pos["monitor"] = asdict(res) | {"levels": levels}
        positions.append(pos)
    # Portfolio-level estimate in ONE pass so the annual LTCG exemption and set-offs are applied once
    # (per-position figures above are "if only this position were sold").
    all_lots = []
    for sid in by_stock:
        cp = prices.get(sid)
        if cp and cp.price is not None:
            all_lots += [(lot, Decimal(str(cp.price))) for lot in _ledger(db, portfolio.id, sid, db.get(Stock, sid).symbol)]
    port_unreal = unrealized_tax_estimate(all_lots, as_of, rb, realized_ctx, charges_engine=ce) if all_lots else None
    if port_unreal is not None:
        tot["tax"] = Decimal(str(port_unreal.estimated_tax_if_sold))
    realized_summary = summarize_realized(db, realized_rows, profile, ty)
    summary = {
        "invested": float(tot["invested"]), "current_value": float(tot["value"]),
        "unrealized_gross_pnl": float(tot["gross"]), "realized_gross_pnl": realized_summary["capital_gain_gross"],
        "realized_pnl_after_charges": realized_summary["trading_pnl"],
        "charges_incl_estimated_exit": float(tot["charges"]) + realized_summary["charges"],
        "estimated_tax_unrealized": float(tot["tax"]), "estimated_tax_realized": realized_summary["estimated_tax"],
        "tax_year": ty,
        "estimated_tax_unrealized_status": port_unreal.status if port_unreal else None,
        "estimated_tax_unrealized_incomplete_reasons": port_unreal.incomplete_reasons if port_unreal else [],
        "estimated_tax_unrealized_note": ("Change in this tax year's estimated tax if every open position were sold now. "
                                          "A negative value is an estimated tax saving (losses set off against gains "
                                          "already realized this year)."),
        "realized_scope": f"Realized figures cover tax year {ty}.",
    }
    summary["gross_pnl"] = summary["unrealized_gross_pnl"] + realized_summary["capital_gain_gross"]
    summary["net_pnl"] = (summary["unrealized_gross_pnl"] - float(tot["charges"]) - summary["estimated_tax_unrealized"]
                          + realized_summary["trading_pnl"] - summary["estimated_tax_realized"])
    summary["net_return_pct"] = 100 * summary["net_pnl"] / summary["invested"] if summary["invested"] else None
    stamps = [p["price_as_of"] for p in positions if p.get("price_as_of")]
    summary["data_as_of"] = min(stamps) if stamps else None  # oldest price used (conservative)
    summary["price_kinds"] = sorted({p["price_kind"] for p in positions})
    alloc = _risk(positions, summary["current_value"])
    return {"portfolio": {"id": portfolio.id, "name": portfolio.name, "kind": portfolio.kind},
            "data_as_of": summary["data_as_of"],
            "summary": summary, "positions": sorted(positions, key=lambda p: -(p.get("current_value") or 0)),
            "realized": realized_summary, "risk": alloc,
            "labels": {"tax": "ESTIMATED", "disclaimer": DISCLAIMER,
                       "unrealized_note": "Unrealized gains are informational and not necessarily currently taxable."}}


def summarize_realized(db: Session, rows, profile: TaxProfileIn, tax_year: str) -> dict:
    lines = gain_lines_from_rows(db, rows)
    res = compute_tax_year(lines, tax_year, profile, rulebook(db))
    gross = sum((Decimal(r.sale_value) - Decimal(r.purchase_value) for r in rows), ZERO)
    ch = sum((Decimal(r.buy_charges) + Decimal(r.sell_charges) for r in rows), ZERO)
    tp = sum((Decimal(r.trading_pnl) for r in rows), ZERO)
    return {"tax_year": tax_year, "capital_gain_gross": float(gross), "charges": float(ch), "trading_pnl": float(tp),
            "estimated_tax": float(res.total_tax_estimate), "status": res.status,
            "incomplete_reasons": res.incomplete_reasons, "net_after_tax": float(tp - res.total_tax_estimate)}


def _risk(positions: list[dict], total_value: float) -> dict:
    warnings, by_sector = [], defaultdict(float)
    for p in positions:
        v = p.get("current_value") or 0.0
        by_sector[p.get("sector") or "Unknown"] += v
        if total_value and v / total_value > 0.2:
            warnings.append(f"{p['symbol']} represents {100 * v / total_value:.0f}% of your portfolio.")
    for s, v in by_sector.items():
        if total_value and v / total_value > 0.35:
            warnings.append(f"{100 * v / total_value:.0f}% of your portfolio is exposed to one sector ({s}).")
    return {"sector_allocation": {k: round(100 * v / total_value, 2) if total_value else 0 for k, v in by_sector.items()},
            "warnings": warnings}


def _monitor(db: Session, portfolio_id: int, st: Stock, pos: dict, regime) -> tuple:
    pp = db.scalar(select(PortfolioPosition).where(PortfolioPosition.portfolio_id == portfolio_id,
                                                   PortfolioPosition.stock_id == st.id))
    df = bars(db, st.id, lookback_days=500)
    ind = latest_values(compute_all(df)) if len(df) >= 30 else {}
    stop = t1 = t2 = trail = None
    source = "none"
    if pp and (pp.stop or pp.target1):
        stop, t1, t2, trail, source = pp.stop, pp.target1, pp.target2, pp.trailing_stop, "user"
    elif pp and pp.recommendation_id:
        rec = db.get(Recommendation, pp.recommendation_id)
        if rec:
            stop, t1, t2, source = rec.stop, rec.target1, rec.target2, "recommendation"
    if source == "none" and ind.get("atr_14") and ind.get("ema_200"):
        pa = analyze_price_action(df)
        lv = compute_levels(SetupContext(cmp=pos["price"], atr=ind["atr_14"], ema20=ind.get("ema_20"),
                                         ema50=ind.get("ema_50"), supports=pa["supports"],
                                         resistances=pa["resistances"], last_swing_low=pa.get("last_swing_low"),
                                         high_52w=ind.get("high_52w"), hv_20=ind.get("hv_20"),
                                         patterns=pa["patterns"], regime=regime.regime if regime else "NEUTRAL"))
        stop, t1, t2, source = lv.stop, lv.target1, lv.target2, "system_suggested"
    since = utcnow() - timedelta(days=5)
    worst = db.scalar(select(NewsItem).where(NewsItem.stock_id == st.id, NewsItem.published_at >= since,
                                             NewsItem.impact.in_(["medium", "high"]))
                      .order_by(NewsItem.sentiment).limit(1))
    ev = db.scalar(select(EventCalendar.event_date).where(EventCalendar.stock_id == st.id,
                                                          EventCalendar.event_date >= today_ist())
                   .order_by(EventCalendar.event_date).limit(1))
    res = evaluate_position(PositionState(
        symbol=st.symbol, quantity=pos["quantity"], avg_cost=pos["avg_cost"], cmp=pos["price"], stop=stop, target1=t1,
        target2=t2, trailing_stop=trail, levels_source=source, ema20=ind.get("ema_20"), ema50=ind.get("ema_50"),
        atr=ind.get("atr_14"), rsi=ind.get("rsi_14"), supertrend_dir=ind.get("supertrend_dir"),
        macd_below_signal=(ind["macd"] < ind["macd_signal"]) if ind.get("macd") is not None and ind.get("macd_signal") is not None else None,
        regime=regime.regime if regime else None, worst_recent_news=worst.sentiment if worst else None,
        negative_news_headline=worst.headline[:140] if worst else None,
        upcoming_results_sessions=_cal(db).sessions_between(today_ist(), ev) if ev else None,
        current_score=_latest_score(db, st.id), best_alternative_score=_best_score(db),
        data_as_of=pos.get("price_as_of"),
    ))
    return res, {"stop": stop, "target1": t1, "target2": t2, "trailing_stop": trail, "source": source}


def _cal(db: Session):
    from app.market_calendar.calendar import load_calendar

    return load_calendar(db)


def _latest_score(db: Session, stock_id: int) -> float | None:
    from app.models import Signal

    return db.scalar(select(Signal.score).where(Signal.stock_id == stock_id).order_by(Signal.id.desc()).limit(1))


def _best_score(db: Session) -> float | None:
    from app.models import ScanRun

    run = db.scalar(select(ScanRun).where(ScanRun.status == "ok").order_by(ScanRun.generated_at.desc()).limit(1))
    if run is None:
        return None
    return db.scalar(select(Recommendation.score).where(Recommendation.run_id == run.id)
                     .order_by(Recommendation.score.desc()).limit(1))


def pooled_tax_estimates(db: Session, user_id: int, portfolio_ids: list[int]) -> dict:
    """Realized + unrealized tax for several portfolios together (one taxpayer ⇒ one exemption/set-off)."""
    as_of = today_ist()
    ty = fy_of(as_of)
    rb, ce, profile = rulebook(db), charges_engine(db), tax_profile(db, user_id)
    rows = realized_lines(db, portfolio_ids, ty) if portfolio_ids else []
    ctx = RealizedContext(gain_lines_from_rows(db, rows), profile)
    lots = db.scalars(select(TaxLot).where(TaxLot.portfolio_id.in_(portfolio_ids or [-1]),
                                           TaxLot.remaining_quantity > 0)).all()
    prices = current_prices(db, list({lot.stock_id for lot in lots}))
    items = []
    for pid, sid in {(lot.portfolio_id, lot.stock_id) for lot in lots}:
        cp = prices.get(sid)
        if cp and cp.price is not None:
            items += [(x, Decimal(str(cp.price))) for x in _ledger(db, pid, sid, db.get(Stock, sid).symbol)]
    unreal = unrealized_tax_estimate(items, as_of, rb, ctx, charges_engine=ce) if items else None
    realized = summarize_realized(db, rows, profile, ty)
    return {"tax_year": ty, "estimated_tax_realized": realized["estimated_tax"],
            "estimated_tax_unrealized": float(unreal.estimated_tax_if_sold) if unreal else 0.0,
            "status": unreal.status if unreal else realized["status"],
            "incomplete_reasons": (unreal.incomplete_reasons if unreal else []) + realized["incomplete_reasons"]}
