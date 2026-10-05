"""Free intraday snapshots from NSE's public website endpoints that are served openly (no bot challenge).

Coverage is partial by design of the source: every NSE index (with per-index advances/declines), plus the stocks
that appear in NSE's live top-gainers / top-losers / most-active lists. Values are a few minutes delayed and are
labelled as such. Per-stock quote endpoints that sit behind bot protection are deliberately NOT used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.timeutil import IST, utcnow
from app.data.nse.client import NSEClient
from app.data.providers.base import ProviderError

BASE = "https://www.nseindia.com/api"
SOURCE = "NSE website live snapshot (delayed, partial coverage)"
MOVER_GROUPS = ("NIFTY", "NIFTYNEXT50", "FOSec", "SecGtr20", "allSec")


@dataclass(slots=True)
class LiveIndex:
    name: str
    last: float
    change_pct: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    advances: int | None
    declines: int | None


@dataclass(slots=True)
class LiveQuote:
    symbol: str
    ltp: float
    prev_close: float | None
    open: float | None
    high: float | None
    low: float | None
    volume: int | None
    change_pct: float | None
    ts: datetime
    lists: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LiveSnapshot:
    as_of: datetime | None
    indices: list[LiveIndex]
    quotes: dict[str, LiveQuote]
    gainers: list[str]
    losers: list[str]
    most_active: list[str]
    retrieved_at: datetime
    warnings: list[str]


def _f(v) -> float | None:
    try:
        return None if v in (None, "", "-") else float(v)
    except (TypeError, ValueError):
        return None


def _ts(s: str | None) -> datetime | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST) if s else None
        except ValueError:
            continue
    return None


def fetch_snapshot(client: NSEClient, ttl: float = 150.0) -> LiveSnapshot:
    warnings: list[str] = []
    indices: list[LiveIndex] = []
    as_of = None
    quotes: dict[str, LiveQuote] = {}
    gainers: list[str] = []
    losers: list[str] = []
    active: list[str] = []
    try:
        d = client.get_json(f"{BASE}/allIndices", ttl=ttl)
        as_of = _ts(d.get("timestamp"))
        for r in d.get("data", []):
            last = _f(r.get("last"))
            if last is None:
                continue
            indices.append(LiveIndex(r.get("index"), last, _f(r.get("percentChange")), _f(r.get("open")),
                                     _f(r.get("high")), _f(r.get("low")), _f(r.get("previousClose")),
                                     int(_f(r.get("advances")) or 0) if r.get("advances") not in (None, "") else None,
                                     int(_f(r.get("declines")) or 0) if r.get("declines") not in (None, "") else None))
    except ProviderError as e:
        warnings.append(f"indices: {e}")

    def add(symbol: str, ltp, prev, op, hi, lo, vol, chg, ts, tag: str) -> None:
        ltp = _f(ltp)
        if not symbol or ltp is None:
            return
        q = quotes.get(symbol)
        if q is None:
            q = quotes[symbol] = LiveQuote(symbol, ltp, _f(prev), _f(op), _f(hi), _f(lo),
                                           int(_f(vol)) if _f(vol) is not None else None, _f(chg), ts or as_of or utcnow())
        q.lists.append(tag)

    for kind, bucket in (("gainers", gainers), ("loosers", losers)):
        try:
            d = client.get_json(f"{BASE}/live-analysis-variations?index={kind}", ttl=ttl)
            for g in MOVER_GROUPS:
                grp = d.get(g) or {}
                ts = _ts(grp.get("timestamp"))
                for r in grp.get("data", []):
                    if r.get("series") not in (None, "EQ", "BE"):
                        continue
                    add(r.get("symbol"), r.get("ltp"), r.get("prev_price"), r.get("open_price"), r.get("high_price"),
                        r.get("low_price"), r.get("trade_quantity"), r.get("perChange"), ts,
                        "top gainer" if kind == "gainers" else "top loser")
                    if g == "allSec" or g == "NIFTY":
                        bucket.append(r.get("symbol"))
        except ProviderError as e:
            warnings.append(f"{kind}: {e}")
    for kind in ("value", "volume"):
        try:
            d = client.get_json(f"{BASE}/live-analysis-most-active-securities?index={kind}", ttl=ttl)
            for r in d.get("data", []):
                add(r.get("symbol"), r.get("lastPrice"), r.get("previousClose"), r.get("open"), r.get("dayHigh"),
                    r.get("dayLow"), r.get("totalTradedVolume"), r.get("pChange"), _ts(r.get("lastUpdateTime")),
                    f"most active by {kind}")
                if r.get("symbol") not in active:
                    active.append(r.get("symbol"))
        except ProviderError as e:
            warnings.append(f"most active {kind}: {e}")
    return LiveSnapshot(as_of, indices, quotes, list(dict.fromkeys(gainers)), list(dict.fromkeys(losers)), active,
                        utcnow(), warnings)
