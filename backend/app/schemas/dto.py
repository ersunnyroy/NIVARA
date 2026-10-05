"""Serializers from ORM rows to API payloads (dates ISO, Decimals → float)."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.timeutil import to_ist


def j(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return to_ist(v).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: j(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [j(x) for x in v]
    if is_dataclass(v) and not isinstance(v, type):
        return j(asdict(v))
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def row(obj, exclude: set[str] | None = None) -> dict:
    cols = obj.__table__.columns.keys()
    return {c: j(getattr(obj, c)) for c in cols if not exclude or c not in exclude}


def outcome_dto(o) -> dict | None:
    if o is None:
        return None
    return row(o, {"recommendation_id"})


def rec_dto(r) -> dict:
    d = row(r)
    d.update(symbol=r.stock.symbol, name=r.stock.name, outcome=outcome_dto(r.outcome),
             reward_risk=f"1:{r.rr:.1f}", holding=f"{r.holding_min_sessions}-{r.holding_max_sessions} sessions")
    return d


def stock_brief(s) -> dict:
    return {"id": s.id, "symbol": s.symbol, "name": s.name, "sector": s.industry, "industry": s.industry,
            "is_fno": s.is_fno, "series": s.series, "isin": s.isin, "index_memberships": s.index_memberships or []}


def price_dto(cp) -> dict:
    return {"price": cp.price, "as_of": j(cp.as_of), "kind": cp.kind, "source": cp.source,
            "prev_close": cp.prev_close, "change_pct": cp.change_pct}
