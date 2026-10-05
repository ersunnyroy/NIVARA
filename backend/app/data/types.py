"""Provider-neutral data records. Every record carries provenance (source + timestamps).

Providers return these; services persist them. Nothing in this module fabricates data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class DataQuality(StrEnum):
    VERIFIED = "verified"  # official/primary source, parsed without issues
    PROVISIONAL = "provisional"  # official but marked provisional (e.g. FII/DII provisional figures)
    DERIVED = "derived"  # computed by us from verified inputs
    UNVERIFIED = "unverified"  # secondary source
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class Provenance:
    source: str  # e.g. "NSE CM bhavcopy (UDiFF)"
    retrieved_at: datetime
    data_timestamp: datetime | None = None  # when the data itself is "as of"
    url: str | None = None
    quality: DataQuality = DataQuality.VERIFIED


@dataclass(slots=True)
class SecurityInfo:
    symbol: str
    name: str
    series: str | None
    isin: str | None
    listing_date: date | None = None
    face_value: float | None = None
    industry: str | None = None
    exchange: str = "NSE"


@dataclass(slots=True)
class DailyBar:
    symbol: str
    series: str | None
    date: date
    open: float
    high: float
    low: float
    close: float
    prev_close: float | None
    volume: int
    turnover: float | None = None  # INR
    trades: int | None = None
    isin: str | None = None
    delivery_qty: int | None = None
    delivery_pct: float | None = None


@dataclass(slots=True)
class IndexBar:
    index_name: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    change_pct: float | None = None
    volume: float | None = None
    turnover_cr: float | None = None
    pe: float | None = None
    pb: float | None = None
    div_yield: float | None = None


@dataclass(slots=True)
class Quote:
    symbol: str
    ts: datetime
    ltp: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: int | None = None
    vwap: float | None = None
    is_delayed: bool = True


@dataclass(slots=True)
class FuturesRow:
    underlying: str
    instrument: str  # STF | IDF
    date: date
    expiry: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    settle: float | None
    underlying_price: float | None
    oi: int
    change_oi: int
    volume: int
    lot_size: int | None = None


@dataclass(slots=True)
class OptionRow:
    underlying: str
    instrument: str  # STO | IDO
    date: date
    expiry: date
    strike: float
    option_type: str  # CE | PE
    close: float | None
    settle: float | None
    underlying_price: float | None
    oi: int
    change_oi: int
    volume: int


@dataclass(slots=True)
class HolidayRecord:
    date: date
    description: str
    segment: str = "CM"
    exchange: str = "NSE"


@dataclass(slots=True)
class FlowRecord:
    date: date
    category: str  # FII | DII
    buy_value_cr: float
    sell_value_cr: float
    net_value_cr: float


@dataclass(slots=True)
class CorporateActionRecord:
    symbol: str
    subject: str
    ex_date: date | None
    record_date: date | None
    action_type: str  # dividend|split|bonus|rights|buyback|demerger|other
    ratio_from: float | None = None
    ratio_to: float | None = None
    amount: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResultFiling:
    """Pointer to a filed result (list endpoint)."""

    symbol: str
    period_end: date
    period_start: date | None
    consolidated: bool
    audited: bool | None
    is_bank: bool
    broadcast_at: datetime | None
    xbrl_url: str | None
    period_type: str = "quarterly"


@dataclass(slots=True)
class FinancialStatement:
    """Parsed numbers from a result XBRL. Values in absolute INR. None = not reported."""

    symbol: str
    period_start: date | None
    period_end: date
    consolidated: bool
    is_bank: bool
    revenue: float | None = None
    other_income: float | None = None
    total_income: float | None = None
    total_expenses: float | None = None
    finance_costs: float | None = None
    depreciation: float | None = None
    pbt: float | None = None
    tax: float | None = None
    pat: float | None = None
    pat_owners: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    paid_up_capital: float | None = None
    face_value: float | None = None
    debt_equity: float | None = None
    interest_coverage: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ebitda(self) -> float | None:
        if self.pbt is None or self.finance_costs is None or self.depreciation is None:
            return None
        return self.pbt + self.finance_costs + self.depreciation - (self.other_income or 0.0)

    @property
    def ebit(self) -> float | None:
        if self.pbt is None or self.finance_costs is None:
            return None
        return self.pbt + self.finance_costs


@dataclass(slots=True)
class ShareholdingRecord:
    symbol: str
    period_end: date
    promoter_pct: float | None
    public_pct: float | None
    broadcast_at: datetime | None
    xbrl_url: str | None = None
    promoter_pledged_pct: float | None = None
    fii_pct: float | None = None
    dii_pct: float | None = None
    mf_pct: float | None = None


@dataclass(slots=True)
class EventRecord:
    symbol: str
    event_date: date
    purpose: str
    description: str | None = None


@dataclass(slots=True)
class Announcement:
    """A primary-source filing/announcement (exchange RSS/API) or secondary news item."""

    headline: str
    published_at: datetime
    source: str
    source_tier: str  # primary | reputable | other
    url: str | None = None
    company: str | None = None
    symbol: str | None = None
    body: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResult:
    """Wrapper so callers always see provenance alongside data."""

    data: Any
    provenance: Provenance
    warnings: list[str] = field(default_factory=list)
