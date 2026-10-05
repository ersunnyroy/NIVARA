"""Compute and store per-underlying F&O snapshots from the stored EOD F&O bhavcopy."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.fno.analytics import fno_score, fno_snapshot
from app.models import FnoFuture, FnoSnapshot, OptionChainRow
from app.repositories.upsert import upsert

SNAPSHOT_COLS = ["spot", "fut_price", "basis", "basis_pct", "fut_oi", "fut_oi_change_pct", "fut_volume", "pcr_oi",
                 "pcr_volume", "max_pain", "call_resistance", "put_support", "atm_iv", "iv_percentile", "buildup",
                 "interpretation", "details"]


def compute_snapshots(db: Session, session: date, underlyings: list[str] | None = None) -> int:
    fut_rows = db.scalars(select(FnoFuture).where(FnoFuture.date <= session,
                                                   FnoFuture.date >= session - timedelta(days=45))).all()
    by_u: dict[str, list] = {}
    for f in fut_rows:
        by_u.setdefault(f.underlying, []).append(f)
    names = underlyings or sorted({f.underlying for f in fut_rows if f.date == session})
    rows = []
    for u in names:
        futs = by_u.get(u, [])
        today = [f for f in futs if f.date == session]
        if not today:
            continue
        opts = db.scalars(select(OptionChainRow).where(OptionChainRow.underlying == u,
                                                       OptionChainRow.date == session)).all()
        spot = next((f.underlying_price for f in today if f.underlying_price), None)
        prev = db.scalar(select(FnoSnapshot).where(FnoSnapshot.underlying == u, FnoSnapshot.date < session)
                         .order_by(FnoSnapshot.date.desc()).limit(1))
        hist = [r for (r,) in db.execute(select(FnoSnapshot.atm_iv).where(FnoSnapshot.underlying == u,
                                                                         FnoSnapshot.date < session)
                                         .order_by(FnoSnapshot.date.desc()).limit(252))]
        snap = fno_snapshot(u, session, futs, opts, spot, prev_snapshot=prev, iv_history=hist)
        d = snap.to_dict()
        rows.append({"underlying": u, "date": session, "computed_at": utcnow(),
                     **{k: d.get(k) for k in SNAPSHOT_COLS}})
    upsert(db, FnoSnapshot, rows, ["underlying", "date"])
    db.commit()
    return len(rows)


def fno_component(db: Session, symbol: str, is_fno: bool, as_of: date) -> tuple:
    if not is_fno:
        return (None, [], [], "Not an F&O stock")
    snap = db.scalar(select(FnoSnapshot).where(FnoSnapshot.underlying == symbol, FnoSnapshot.date <= as_of)
                     .order_by(FnoSnapshot.date.desc()).limit(1))
    if snap is None or (as_of - snap.date).days > 5:
        return (None, [], [], "F&O data unavailable for this session")
    score, reasons, missing = fno_score(snap)
    if score is None:
        return (None, [], [], "; ".join(missing) or "F&O score unavailable")
    pos = [r for r in reasons if re.search(r"\+\d", r)]
    neg = [r for r in reasons if re.search(r"[-−]\d", r)]
    return (score, pos[:3], neg[:3], None)


