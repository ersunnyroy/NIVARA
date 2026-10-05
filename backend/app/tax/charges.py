"""Brokerage + statutory charges engine (pure, dated schedules, Decimal money).

No rate is hard-coded here: every percentage comes from a dated :class:`ChargeSchedule` whose
``rates`` dict has exactly the shape persisted in the ``charges.rates`` DB column::

    {
      "stt_rounding": "rupee" | "paise",          # optional, default "rupee"; may be overridden per segment
      "equity_delivery": {
        "brokerage": {"type": "zero" | "flat" | "percent_capped" | "percent", "pct": "0.03", "cap": "20", "flat": "20"},
        "stt_buy_pct": "0.1", "stt_sell_pct": "0.1",     # percent values: 0.1 means 0.1 %
        "exchange_txn_pct": {"NSE": "0.00307", "BSE": "0.00375"},
        "sebi_per_crore": "10", "stamp_buy_pct": "0.015", "ipft_per_crore": "0",
        "gst_pct": "18",                                 # on brokerage + exchange txn + SEBI + IPFT
        "dp_charge_per_scrip_sell": "15.34"              # delivery sells only, once per scrip per day, GST-incl.
      },
      "equity_intraday": {...}, "futures": {...}, "options": {...}
    }

Turnover = quantity x price. For options the price is the *premium*, so every charge (incl. STT) is
on premium turnover. All outputs are estimates (``is_estimate=True``) — contract notes are authoritative.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.tax.common import HUNDRED, RUPEE, ZERO, D, inr, jsonable, money, parse_date

SEGMENTS = ("equity_delivery", "equity_intraday", "futures", "options")
SEGMENT_ALIASES = {
    "delivery": "equity_delivery",
    "cnc": "equity_delivery",
    "equity_delivery": "equity_delivery",
    "intraday": "equity_intraday",
    "mis": "equity_intraday",
    "equity_intraday": "equity_intraday",
    "futures": "futures",
    "future": "futures",
    "fut": "futures",
    "options": "options",
    "option": "options",
    "opt": "options",
}
PER_CRORE = Decimal(10000000)


def normalize_segment(segment: str) -> str:
    key = (segment or "").strip().lower()
    if key not in SEGMENT_ALIASES:
        raise ValueError(f"Unknown segment {segment!r}; expected one of {', '.join(SEGMENTS)}")
    return SEGMENT_ALIASES[key]


def normalize_side(side: str) -> str:
    s = (side or "").strip().upper()
    if s not in ("BUY", "SELL"):
        raise ValueError(f"Unknown side {side!r}; expected BUY or SELL")
    return s


@dataclass(frozen=True)
class ChargeSchedule:
    """A dated charge schedule (mirrors models.tax.ChargeSchedule)."""

    name: str
    effective_from: date
    effective_to: date | None = None
    rates: dict[str, Any] = field(default_factory=dict)
    broker: str | None = None
    source_url: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChargeSchedule:
        eff_from = parse_date(data.get("effective_from"))
        if eff_from is None:
            raise ValueError("Charge schedule requires effective_from")
        return cls(
            name=str(data["name"]),
            effective_from=eff_from,
            effective_to=parse_date(data.get("effective_to")),
            rates=dict(data.get("rates") or {}),
            broker=data.get("broker"),
            source_url=data.get("source_url"),
            notes=data.get("notes"),
        )

    @classmethod
    def coerce(cls, value: ChargeSchedule | Mapping[str, Any] | Any) -> ChargeSchedule:
        if isinstance(value, ChargeSchedule):
            return value
        if isinstance(value, Mapping):
            return cls.from_dict(value)
        # ORM row or any object with the same attribute names
        return cls.from_dict({k: getattr(value, k, None) for k in (
            "name", "effective_from", "effective_to", "rates", "broker", "source_url", "notes")})

    def covers(self, d: date) -> bool:
        return self.effective_from <= d and (self.effective_to is None or d <= self.effective_to)

    def segment_rates(self, segment: str) -> dict[str, Any]:
        seg = normalize_segment(segment)
        if seg not in self.rates:
            raise ValueError(f"Charge schedule {self.name!r} has no rates for segment {seg!r}")
        return self.rates[seg]

    def stt_rounding(self, segment: str) -> str:
        seg_rates = self.segment_rates(segment)
        mode = str(seg_rates.get("stt_rounding", self.rates.get("stt_rounding", "rupee"))).lower()
        if mode not in ("rupee", "paise"):
            raise ValueError(f"stt_rounding must be 'rupee' or 'paise', got {mode!r}")
        return mode


@dataclass
class ChargeBreakdown:
    """Per-order charges. Components are full precision; use :meth:`rounded` for contract-note style paise."""

    segment: str
    side: str
    exchange: str
    quantity: Decimal
    price: Decimal
    turnover: Decimal
    trade_date: date
    brokerage: Decimal
    stt: Decimal
    exchange_txn: Decimal
    sebi: Decimal
    stamp: Decimal
    ipft: Decimal
    gst: Decimal
    dp: Decimal
    total: Decimal
    schedule_name: str
    is_estimate: bool = True
    notes: list[str] = field(default_factory=list)

    COMPONENTS = ("brokerage", "stt", "exchange_txn", "sebi", "stamp", "ipft", "gst", "dp")

    @property
    def total_excl_stt(self) -> Decimal:
        return self.total - self.stt

    def rounded(self) -> ChargeBreakdown:
        """Each component rounded to paise (ROUND_HALF_UP); total = sum of rounded components."""
        values = {c: money(getattr(self, c)) for c in self.COMPONENTS}
        return replace(self, **values, total=sum(values.values(), ZERO), notes=list(self.notes))

    def to_dict(self) -> dict[str, Any]:
        out = jsonable(self.rounded())
        out["is_estimate"] = True
        return out


@dataclass
class RoundTripCharges:
    buy: ChargeBreakdown
    sell: ChargeBreakdown

    @property
    def total(self) -> Decimal:
        return self.buy.total + self.sell.total

    @property
    def stt_total(self) -> Decimal:
        return self.buy.stt + self.sell.stt

    @property
    def is_estimate(self) -> bool:
        return True


@dataclass(frozen=True)
class OrderIn:
    """One executed order, used by :meth:`ChargesEngine.compute_orders` (DP once per scrip per day)."""

    symbol: str
    segment: str
    side: str
    quantity: Decimal
    price: Decimal
    trade_date: date
    exchange: str = "NSE"


def _pct_of(turnover: Decimal, pct_value: Any) -> Decimal:
    return turnover * D(pct_value or 0) / HUNDRED


def _brokerage(turnover: Decimal, spec: Mapping[str, Any] | None) -> Decimal:
    if not spec:
        return ZERO
    kind = str(spec.get("type", "zero")).lower()
    if kind == "zero":
        return ZERO
    if kind == "flat":
        return D(spec.get("flat", 0))
    if kind == "percent":
        return _pct_of(turnover, spec.get("pct", 0))
    if kind == "percent_capped":
        raw = _pct_of(turnover, spec.get("pct", 0))
        cap = spec.get("cap")
        return raw if cap is None else min(raw, D(cap))
    raise ValueError(f"Unknown brokerage type {kind!r}")


def select_schedule(
    schedules: Iterable[ChargeSchedule | Mapping[str, Any]], trade_date: date, *, strict: bool = False
) -> tuple[ChargeSchedule, list[str]]:
    """Schedule effective on ``trade_date`` (effective_from <= d <= effective_to).

    If several cover the date, the most recently effective one wins. If none covers it and ``strict`` is False,
    the nearest schedule is used and a note explains this; with ``strict=True`` a ValueError is raised.
    """
    items = [ChargeSchedule.coerce(s) for s in schedules]
    if not items:
        raise ValueError("No charge schedules supplied")
    covering = [s for s in items if s.covers(trade_date)]
    if covering:
        return max(covering, key=lambda s: s.effective_from), []
    if strict:
        raise ValueError(f"No charge schedule covers trade date {trade_date.isoformat()}")
    nearest = min(
        items,
        key=lambda s: min(
            abs((s.effective_from - trade_date).days),
            abs(((s.effective_to or s.effective_from) - trade_date).days),
        ),
    )
    note = (
        f"No charge schedule covers {trade_date.isoformat()}; used nearest schedule "
        f"'{nearest.name}' effective {nearest.effective_from.isoformat()} — charges may differ."
    )
    return nearest, [note]


def compute_with_schedule(
    schedule: ChargeSchedule,
    segment: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    exchange: str = "NSE",
    *,
    trade_date: date,
    include_dp: bool = True,
) -> ChargeBreakdown:
    seg = normalize_segment(segment)
    side_u = normalize_side(side)
    qty, px = D(quantity), D(price)
    if qty <= 0:
        raise ValueError(f"Quantity must be positive, got {qty}")
    if px < 0:
        raise ValueError(f"Price must be non-negative, got {px}")
    exch = (exchange or "NSE").strip().upper()
    r = schedule.segment_rates(seg)
    notes: list[str] = []
    turnover = qty * px
    if seg == "options":
        notes.append("Options charges (incl. STT) computed on premium turnover.")

    brokerage = _brokerage(turnover, r.get("brokerage"))

    stt_pct = r.get("stt_buy_pct" if side_u == "BUY" else "stt_sell_pct", 0)
    stt_raw = _pct_of(turnover, stt_pct)
    if schedule.stt_rounding(seg) == "rupee":
        stt = stt_raw.quantize(RUPEE, rounding=ROUND_HALF_UP)
    else:
        stt = money(stt_raw)

    txn_map = r.get("exchange_txn_pct") or {}
    if exch not in txn_map:
        raise ValueError(f"Charge schedule {schedule.name!r} has no exchange transaction rate for {exch} ({seg})")
    exchange_txn = _pct_of(turnover, txn_map[exch])

    sebi = turnover * D(r.get("sebi_per_crore", 0)) / PER_CRORE
    stamp = _pct_of(turnover, r.get("stamp_buy_pct", 0)) if side_u == "BUY" else ZERO
    ipft = turnover * D(r.get("ipft_per_crore", 0)) / PER_CRORE
    gst = _pct_of(brokerage + exchange_txn + sebi + ipft, r.get("gst_pct", 0))

    dp = ZERO
    dp_rate = D(r.get("dp_charge_per_scrip_sell", 0))
    if seg == "equity_delivery" and side_u == "SELL" and dp_rate > 0:
        if include_dp:
            dp = dp_rate
            notes.append(f"DP charge {inr(dp_rate)} (GST-inclusive) is levied once per scrip per day on delivery sells.")
        else:
            notes.append("DP charge already applied to another sell of this scrip today.")

    total = brokerage + stt + exchange_txn + sebi + stamp + ipft + gst + dp
    return ChargeBreakdown(
        segment=seg,
        side=side_u,
        exchange=exch,
        quantity=qty,
        price=px,
        turnover=turnover,
        trade_date=trade_date,
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi=sebi,
        stamp=stamp,
        ipft=ipft,
        gst=gst,
        dp=dp,
        total=total,
        schedule_name=schedule.name,
        is_estimate=True,
        notes=notes,
    )


def compute_charges(
    segment: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    exchange: str = "NSE",
    *,
    trade_date: date,
    schedule: ChargeSchedule | Mapping[str, Any] | None = None,
    schedules: Iterable[ChargeSchedule | Mapping[str, Any]] | None = None,
    include_dp: bool = True,
    strict: bool = False,
) -> ChargeBreakdown:
    """Charges for one executed order. Pass either one ``schedule`` or a list of dated ``schedules``."""
    if schedule is not None:
        chosen, notes = ChargeSchedule.coerce(schedule), []
        if not chosen.covers(trade_date):
            notes.append(f"Schedule '{chosen.name}' is not effective on {trade_date.isoformat()}; used anyway.")
    elif schedules is not None:
        chosen, notes = select_schedule(schedules, trade_date, strict=strict)
    else:
        raise ValueError("Provide schedule= or schedules=")
    out = compute_with_schedule(
        chosen, segment, side, quantity, price, exchange, trade_date=trade_date, include_dp=include_dp
    )
    out.notes = notes + out.notes
    return out


class ChargesEngine:
    """Stateless calculator bound to a set of dated schedules."""

    def __init__(self, schedules: Iterable[ChargeSchedule | Mapping[str, Any]], *, strict: bool = False) -> None:
        self.schedules = [ChargeSchedule.coerce(s) for s in schedules]
        if not self.schedules:
            raise ValueError("ChargesEngine needs at least one schedule")
        self.strict = strict

    @classmethod
    def default(cls) -> ChargesEngine:
        from app.tax.defaults import default_charge_schedules

        return cls(default_charge_schedules())

    def schedule_for(self, trade_date: date) -> ChargeSchedule:
        return select_schedule(self.schedules, trade_date, strict=self.strict)[0]

    def compute(
        self,
        segment: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        exchange: str = "NSE",
        *,
        trade_date: date,
        include_dp: bool = True,
    ) -> ChargeBreakdown:
        return compute_charges(
            segment, side, quantity, price, exchange,
            trade_date=trade_date, schedules=self.schedules, include_dp=include_dp, strict=self.strict,
        )

    def compute_round_trip(
        self,
        segment: str,
        quantity: Decimal,
        buy_price: Decimal,
        sell_price: Decimal,
        exchange: str = "NSE",
        *,
        buy_date: date,
        sell_date: date | None = None,
    ) -> RoundTripCharges:
        buy = self.compute(segment, "BUY", quantity, buy_price, exchange, trade_date=buy_date)
        sell = self.compute(segment, "SELL", quantity, sell_price, exchange, trade_date=sell_date or buy_date)
        return RoundTripCharges(buy=buy, sell=sell)

    def compute_orders(self, orders: Iterable[OrderIn]) -> list[ChargeBreakdown]:
        """Charges for a batch of orders, applying the DP charge once per (scrip, day) on delivery sells.

        The first delivery sell of a scrip on a day carries the DP charge; later ones on the same day do not.
        Output order matches input order.
        """
        seen: set[tuple[str, date]] = set()
        out: list[ChargeBreakdown] = []
        for o in orders:
            seg = normalize_segment(o.segment)
            include_dp = True
            if seg == "equity_delivery" and normalize_side(o.side) == "SELL":
                key = (o.symbol.upper(), o.trade_date)
                include_dp = key not in seen
                seen.add(key)
            out.append(self.compute(seg, o.side, o.quantity, o.price, o.exchange,
                                    trade_date=o.trade_date, include_dp=include_dp))
        return out


def compute_round_trip(
    segment: str,
    quantity: Decimal,
    buy_price: Decimal,
    sell_price: Decimal,
    exchange: str = "NSE",
    *,
    buy_date: date,
    sell_date: date | None = None,
    schedules: Iterable[ChargeSchedule | Mapping[str, Any]],
) -> RoundTripCharges:
    return ChargesEngine(schedules).compute_round_trip(
        segment, quantity, buy_price, sell_price, exchange, buy_date=buy_date, sell_date=sell_date
    )
