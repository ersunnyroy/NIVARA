"""Track what happened after every recommendation, and aggregate the model's track record."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recommendation, RecommendationOutcome, ScanRun
from app.recommendations.outcomes import Outcome, TradePlan, simulate
from app.services.prices import bars

CLOSED = {"not_triggered", "invalidated", "target1", "target2", "stopped", "expired"}
TRADED = {"target1", "target2", "stopped", "expired"}


def plan_of(r: Recommendation) -> TradePlan:
    return TradePlan(entry_low=r.entry_low, entry_high=r.entry_high, stop=r.stop, target1=r.target1,
                     target2=r.target2, target3=r.target3, trailing_after_t1=r.trailing_stop_after_t1,
                     holding_max=r.holding_max_sessions)


def update_outcomes(db: Session) -> dict:
    recs = db.scalars(select(Recommendation)).unique().all()
    n_upd = n_closed = 0
    for r in recs:
        oc = r.outcome
        if oc is not None and oc.status in CLOSED:
            continue
        df = bars(db, r.stock_id, lookback_days=4000)
        df = df[df.index >= str(r.session_date)]
        res: Outcome = simulate(plan_of(r), df) if not df.empty else Outcome()
        if oc is None:
            oc = RecommendationOutcome(recommendation_id=r.id)
            db.add(oc)
        for k, v in asdict(res).items():
            setattr(oc, k, v)
        n_upd += 1
        n_closed += res.status in CLOSED
    db.commit()
    return {"updated": n_upd, "newly_closed": n_closed}


def _bucket_conf(c: float) -> str:
    return "<55" if c < 55 else "55-64" if c < 65 else "65-74" if c < 75 else "75+"


def _bucket_hold(r: Recommendation) -> str:
    m = r.holding_max_sessions
    return "≤5 sessions" if m <= 5 else "6-15 sessions" if m <= 15 else "16+ sessions"


def _stats(items: list[tuple[Recommendation, RecommendationOutcome]]) -> dict:
    traded = [(r, o) for r, o in items if o and o.status in TRADED and o.return_pct is not None]
    closed = [(r, o) for r, o in items if o and o.status in CLOSED]
    n = len(traded)
    rets = [o.return_pct for _, o in traded]
    wins = [x for x in rets if x > 0]
    return {
        "count": len(items), "closed": len(closed), "traded": n,
        "not_triggered": sum(1 for _, o in closed if o.status in ("not_triggered", "invalidated")),
        "open": sum(1 for _, o in items if o and o.status == "open"),
        "win_rate": round(100 * len(wins) / n, 1) if n else None,
        "t1_hit_rate": round(100 * sum(1 for _, o in traded if o.t1_hit_date) / n, 1) if n else None,
        "t2_hit_rate": round(100 * sum(1 for _, o in traded if o.t2_hit_date) / n, 1) if n else None,
        "stop_hit_rate": round(100 * sum(1 for _, o in traded if o.status == "stopped") / n, 1) if n else None,
        "avg_return_pct": round(sum(rets) / n, 2) if n else None,
        "avg_mfe_pct": round(sum(o.mfe_pct or 0 for _, o in traded) / n, 2) if n else None,
        "avg_mae_pct": round(sum(o.mae_pct or 0 for _, o in traded) / n, 2) if n else None,
        "avg_sessions_held": round(sum(o.sessions_held or 0 for _, o in traded) / n, 1) if n else None,
    }


def _origin(db: Session, cache: dict, run_id: int) -> str:
    if run_id not in cache:
        run = db.get(ScanRun, run_id)
        cache[run_id] = "historical_replay" if run and run.trigger in ("replay", "backfill") else "live"
    return cache[run_id]


def track_record(db: Session, origin: str | None = None) -> dict:
    recs = db.scalars(select(Recommendation)).unique().all()
    cache: dict[int, str] = {}
    if origin:
        recs = [r for r in recs if _origin(db, cache, r.run_id) == origin]
    items = [(r, r.outcome) for r in recs]
    groups = {"by_regime": lambda r: r.market_regime or "unknown", "by_sector": lambda r: r.sector or "unknown",
              "by_strategy": lambda r: r.strategy, "by_confidence": lambda r: _bucket_conf(r.confidence),
              "by_holding": _bucket_hold, "by_model_version": lambda r: r.model_version,
              "by_action": lambda r: r.action, "by_origin": lambda r: _origin(db, cache, r.run_id)}
    out = {"totals": _stats(items), "note": (
        "Outcomes are simulated on official EOD bars with conservative rules (stop checked before target on the "
        "same bar). This is the model's paper track record, not live trading performance. 'historical_replay' "
        "ideas were generated after the fact from point-in-time data and are reported separately from 'live' ideas.")}
    for name, key in groups.items():
        g = defaultdict(list)
        for r, o in items:
            g[key(r)].append((r, o))
        out[name] = sorted([{"bucket": k, **_stats(v)} for k, v in g.items()], key=lambda x: -x["count"])
    return out
