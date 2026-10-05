"""Trade performance statistics. Backtest, paper, system (model) and live results are never mixed."""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Backtest, Portfolio, RealizedGain, Trade

MIN_FOR_RATIOS = 20


def trade_stats(pnls: list[tuple], capital: float = 1_000_000.0) -> dict:
    """pnls: list of (exit_date, net_pnl, holding_days, label) sorted by exit date."""
    n = len(pnls)
    if n == 0:
        return {"total_trades": 0}
    vals = [p[1] for p in pnls]
    wins, losses = [v for v in vals if v > 0], [v for v in vals if v <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    equity, peak, mdd, curve = capital, capital, 0.0, []
    monthly: dict[str, float] = defaultdict(float)
    for d, v, _, _ in pnls:
        equity += v
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak if peak else 0)
        curve.append({"date": d.isoformat(), "value": round(equity, 2)})
        monthly[d.strftime("%Y-%m")] += v
    win_rate = len(wins) / n
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0
    out = {
        "total_trades": n, "wins": len(wins), "losses": len(losses), "win_rate": round(100 * win_rate, 2),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "expectancy": round(win_rate * avg_win + (1 - win_rate) * avg_loss, 2),
        "net_pnl": round(sum(vals), 2), "max_drawdown_pct": round(100 * mdd, 2),
        "avg_holding_days": round(mean(p[2] for p in pnls if p[2] is not None), 1) if any(p[2] is not None for p in pnls) else None,
        "best": max(pnls, key=lambda p: p[1])[3], "best_pnl": round(max(vals), 2),
        "worst": min(pnls, key=lambda p: p[1])[3], "worst_pnl": round(min(vals), 2),
        "monthly": [{"month": k, "pnl": round(v, 2)} for k, v in sorted(monthly.items())],
        "equity_curve": curve, "return_pct_on_capital": round(100 * sum(vals) / capital, 2),
    }
    months = [v / capital for v in monthly.values()]
    if len(months) >= 12 and pstdev(months) > 0:
        out["sharpe_monthly_annualised"] = round(mean(months) / pstdev(months) * math.sqrt(12), 2)
    elif n < MIN_FOR_RATIOS:
        out["ratios_note"] = f"Risk-adjusted ratios need ≥{MIN_FOR_RATIOS} trades / 12 months of data to be meaningful"
    years = defaultdict(float)
    for k, v in monthly.items():
        years[k[:4]] += v
    out["annual"] = [{"year": y, "pnl": round(v, 2)} for y, v in sorted(years.items())]
    return out


def performance(db: Session, user_id: int) -> dict:
    ports = {p.id: p for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user_id))}
    by_kind: dict[str, list] = defaultdict(list)
    for t in db.scalars(select(Trade).where(Trade.portfolio_id.in_(list(ports) or [-1]), Trade.status == "closed")
                        .order_by(Trade.exit_date)):
        kind = t.kind if t.kind in ("paper", "system") else ("live" if ports[t.portfolio_id].kind == "live" else t.kind)
        by_kind[kind].append((t.exit_date, float(t.net_pnl if t.net_pnl is not None else (t.gross_pnl or 0)),
                              (t.exit_date - t.entry_date).days, t.stock.symbol))
    out = {k: trade_stats(v) | {"source": "trade journal"} for k, v in by_kind.items()}
    live_ids = [pid for pid, p in ports.items() if p.kind == "live"]
    if live_ids:
        rows = db.scalars(select(RealizedGain).where(RealizedGain.portfolio_id.in_(live_ids))
                          .order_by(RealizedGain.sold_date)).all()
        if rows:
            from app.models import Stock

            pn = [(r.sold_date, float(r.trading_pnl), r.holding_days, db.get(Stock, r.stock_id).symbol) for r in rows]
            out["live_realized"] = trade_stats(pn) | {
                "source": "FIFO realized lots from live portfolios (after charges, before income tax)"}
    bt = db.scalar(select(Backtest).where(Backtest.status == "completed").order_by(Backtest.completed_at.desc()).limit(1))
    if bt:
        out["backtest"] = {"backtest_id": bt.id, "name": bt.name, "metrics": bt.metrics,
                           "note": "Simulated past performance; does not guarantee future results."}
    return {"kinds": out, "labels": {
        "backtest": "BACKTEST PERFORMANCE (simulated)", "paper": "PAPER TRADING PERFORMANCE (simulated fills)",
        "system": "MODEL PORTFOLIO (auto-followed recommendations, paper)", "live": "LIVE PERFORMANCE (your journal)",
        "live_realized": "LIVE PERFORMANCE (realized from your transactions)"}}
