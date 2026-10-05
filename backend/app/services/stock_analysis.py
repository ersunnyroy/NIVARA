"""On-demand single-stock analysis using the same evaluator as the scanner."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.config import load_config, validate_weights
from app.analytics.evaluate import ExternalInputs, evaluate
from app.analytics.sector import BENCHMARK, INDUSTRY_TO_INDEX, stock_relative_strength
from app.core.timeutil import ist_datetime
from app.market_calendar.calendar import CLOSE, load_calendar
from app.models import EventCalendar, NewsItem, SectorStrength, Signal, Stock
from app.news.classify import news_component
from app.services.fno_service import fno_component
from app.services.fundamentals_service import fundamental_view
from app.services.market import latest_regime
from app.services.prices import bars, index_series


def analyze(db: Session, stock: Stock, as_of: date | None = None) -> dict:
    df = bars(db, stock.id, end=as_of, lookback_days=560)
    if df.empty:
        return {"status": "data_unavailable", "message": "No price history ingested for this stock"}
    as_of = as_of or df.index[-1].date()
    df = df[df.index <= str(as_of)]
    cfg = load_config(db)
    regime = latest_regime(db)
    bench = index_series(db, [BENCHMARK], as_of, 400).get(BENCHMARK)
    rs_ex = stock_relative_strength(df["close"], bench) if bench is not None else None
    sig = db.scalar(select(Signal).where(Signal.stock_id == stock.id).order_by(Signal.id.desc()).limit(1))
    rs_rating = None
    if sig and sig.components.get("score"):
        for c in sig.components["score"]["components"]:
            if c["key"] == "relative_strength" and c["fraction"] is not None:
                rs_rating = round(100 * c["fraction"], 1)
    idx = INDUSTRY_TO_INDEX.get(stock.industry or "")
    sec = db.scalar(select(SectorStrength).where(SectorStrength.index_name == idx, SectorStrength.date <= as_of)
                    .order_by(SectorStrength.date.desc()).limit(1)) if idx else None
    as_of_dt = ist_datetime(as_of, CLOSE.hour, CLOSE.minute)
    news = db.scalars(select(NewsItem).where(NewsItem.stock_id == stock.id,
                                             NewsItem.published_at >= as_of_dt - timedelta(days=14))).all()
    cal = load_calendar(db)
    ev = db.scalar(select(EventCalendar.event_date).where(EventCalendar.stock_id == stock.id,
                                                          EventCalendar.event_date > as_of)
                   .order_by(EventCalendar.event_date).limit(1))
    fv = fundamental_view(db, stock.id, stock.symbol, as_of, float(df["close"].iloc[-1]))
    ext = ExternalInputs(
        rs_rating=rs_rating, rs_excess=rs_ex,
        fundamentals=(fv["score"], fv["reasons"], fv["cautions"],
                      None if fv["score"] is not None else "; ".join(fv["missing"][:2]) or "Insufficient fundamental data"),
        sector=(sec.score, sec.index_name) if sec else (None, None), news=news_component(news, as_of_dt),
        fno=fno_component(db, stock.symbol, stock.is_fno, as_of), is_fno=stock.is_fno,
        regime=regime.regime if regime else "NEUTRAL", regime_confidence=regime.confidence if regime else None,
        upcoming_results_in_sessions=cal.sessions_between(as_of, ev) if ev else None,
    )
    ev_res = evaluate(stock.symbol, df, as_of, ext, validate_weights(cfg["scoring_weights"]), cfg["risk_limits"],
                      cfg["exclusions"])
    return {"status": "ok", "as_of": as_of.isoformat(), "evaluation": ev_res, "fundamentals": fv,
            "rs_rating_source": "latest scan" if rs_rating is not None else None,
            "notes": ([] if rs_rating is not None else
                      ["Relative-strength rating needs a cross-sectional scan; shown as n/a until the scanner runs"])}
