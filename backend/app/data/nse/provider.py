"""NSE implementations of the provider ABCs (official exchange data only)."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, TypeVar
from urllib.parse import urlencode

from app.data.nse import parsers as p
from app.data.nse.client import FetchResult, NSEClient
from app.data.providers.base import (
    CalendarProvider,
    CorporateActionProvider,
    DataUnavailable,
    FlowsProvider,
    FNOProvider,
    FundamentalDataProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.data.rss import IST
from app.data.types import DataQuality, FinancialStatement, Provenance, ProviderResult, ResultFiling

logger = logging.getLogger(__name__)

T = TypeVar("T")

ARCHIVES = "https://nsearchives.nseindia.com"
WWW_API = "https://www.nseindia.com/api"
UDIFF_START = date(2024, 7, 8)  # first session published in the UDiFF bhavcopy format

HOUR = 3600.0
DAY = 24 * HOUR

INDEX_LISTS: dict[str, str] = {
    "nifty50": "ind_nifty50list.csv",
    "niftynext50": "ind_niftynext50list.csv",
    "nifty100": "ind_nifty100list.csv",
    "nifty200": "ind_nifty200list.csv",
    "nifty500": "ind_nifty500list.csv",
}
RSS_FEEDS: dict[str, str] = {
    "NSE announcements": f"{ARCHIVES}/content/RSS/Online_announcements.xml",
    "NSE financial results": f"{ARCHIVES}/content/RSS/Financial_Results.xml",
    "NSE corporate actions": f"{ARCHIVES}/content/RSS/Corporate_action.xml",
}


# ------------------------------------------------------------------ URL builders
def cm_bhavcopy_url(session: date) -> tuple[str, str]:
    """(url, source name) — UDiFF from 2024-07-08, legacy before."""
    if session >= UDIFF_START:
        return (
            f"{ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{session:%Y%m%d}_F_0000.csv.zip",
            "NSE CM bhavcopy (UDiFF)",
        )
    mon = session.strftime("%b").upper()
    return (
        f"{ARCHIVES}/content/historical/EQUITIES/{session:%Y}/{mon}/cm{session:%d}{mon}{session:%Y}bhav.csv.zip",
        "NSE CM bhavcopy (legacy)",
    )


def delivery_url(session: date) -> str:
    return f"{ARCHIVES}/products/content/sec_bhavdata_full_{session:%d%m%Y}.csv"


def index_close_url(session: date) -> str:
    return f"{ARCHIVES}/content/indices/ind_close_all_{session:%d%m%Y}.csv"


def fo_bhavcopy_url(session: date) -> str:
    return f"{ARCHIVES}/content/fo/BhavCopy_NSE_FO_0_0_0_{session:%Y%m%d}_F_0000.csv.zip"


def session_close(session: date) -> datetime:
    """EOD files are 'as of' the 15:30 IST close."""
    return datetime.combine(session, time(15, 30), IST)


def _today_ist() -> date:
    return datetime.now(IST).date()


def _archive_ttl(session: date) -> float | None:
    """Past-session archive files are immutable → cache forever; today's may still be (re)published."""
    return None if session < _today_ist() else HOUR


class _NSEBase:
    name = "nse"

    def __init__(self, client: NSEClient | None = None) -> None:
        self.client = client or NSEClient()

    def _parse(self, res: FetchResult, fn: Callable[[bytes], T]) -> T:
        try:
            return fn(res.content)
        except (p.ParseError, ValueError, KeyError) as exc:
            self.client.invalidate(res.url)
            raise DataUnavailable(f"unexpected format at {res.url}: {exc}") from exc

    @staticmethod
    def _prov(
        res: FetchResult, source: str, data_ts: datetime | None = None, quality: DataQuality = DataQuality.VERIFIED
    ) -> Provenance:
        return Provenance(source=source, retrieved_at=res.retrieved_at, data_timestamp=data_ts, url=res.url,
                          quality=quality)


# ------------------------------------------------------------------ market data
class NSEMarketDataProvider(_NSEBase, MarketDataProvider):
    """EOD market data from NSE archives: securities, bhavcopy (+delivery), index closes, constituents."""

    name = "nse"

    def securities(self) -> ProviderResult:
        res = self.client.fetch(f"{ARCHIVES}/content/equities/EQUITY_L.csv", ttl=12 * HOUR)
        return ProviderResult(self._parse(res, p.parse_equity_list), self._prov(res, "NSE equity list (EQUITY_L)"))

    def daily_bars(self, session: date) -> ProviderResult:
        url, source = cm_bhavcopy_url(session)
        res = self.client.fetch(url, ttl=_archive_ttl(session))
        parser = p.parse_cm_bhavcopy_udiff if session >= UDIFF_START else p.parse_cm_bhavcopy_legacy
        bars = self._parse(res, parser)
        if not bars:
            raise DataUnavailable(f"no equity rows in {url}")
        warnings: list[str] = []
        try:
            dres = self.client.fetch(delivery_url(session), ttl=_archive_ttl(session))
            matched = p.merge_delivery(bars, self._parse(dres, p.parse_delivery))
            if matched < len(bars):
                logger.debug("delivery matched %d/%d bars for %s", matched, len(bars), session)
        except DataUnavailable as exc:
            logger.warning("delivery data unavailable for %s: %s", session, exc)
            warnings.append(f"delivery data unavailable for {session.isoformat()}; delivery fields are None")
        return ProviderResult(bars, self._prov(res, source, session_close(session)), warnings)

    def index_bars(self, session: date) -> ProviderResult:
        res = self.client.fetch(index_close_url(session), ttl=_archive_ttl(session))
        bars = self._parse(res, p.parse_index_close)
        if not bars:
            raise DataUnavailable(f"no index rows for {session}")
        return ProviderResult(bars, self._prov(res, "NSE index closing values", session_close(session)))

    def index_constituents(self, index: str) -> ProviderResult:
        key = index.lower().replace(" ", "").replace("_", "")
        fname = INDEX_LISTS.get(key)
        if fname is None:
            raise DataUnavailable(f"unknown index {index!r}; supported: {sorted(INDEX_LISTS)}")
        urls = [f"{ARCHIVES}/content/indices/{fname}", f"https://www.niftyindices.com/IndexConstituent/{fname}"]
        last: Exception | None = None
        for url in urls:
            try:
                res = self.client.fetch(url, ttl=DAY)
                rows = self._parse(res, p.parse_index_constituents)
                if rows:
                    return ProviderResult(rows, self._prov(res, f"NSE Indices constituents ({key})"))
            except DataUnavailable as exc:
                last = exc
        raise DataUnavailable(f"constituents unavailable for {index}: {last}")


# ------------------------------------------------------------------ fundamentals
class NSEFundamentalsProvider(_NSEBase, FundamentalDataProvider):
    """Result filings (legacy + integrated filing lists), XBRL statements and shareholding (www API)."""

    def result_filings(self, symbol: str) -> ProviderResult:
        q_legacy = urlencode({"index": "equities", "symbol": symbol, "period": "Quarterly"})
        q_int = urlencode({"index": "equities", "type": "Integrated Filing- Financials", "symbol": symbol})
        legacy_url = f"{WWW_API}/corporates-financial-results?{q_legacy}"
        int_url = f"{WWW_API}/integrated-filing-results?{q_int}"
        warnings: list[str] = []
        legacy: list[ResultFiling] = []
        integrated: list[ResultFiling] = []
        main: FetchResult | None = None
        for url, fn, sink in (
            (int_url, p.parse_integrated_filings, integrated),
            (legacy_url, p.parse_result_filings_legacy, legacy),
        ):
            try:
                res = self.client.fetch(url, ttl=6 * HOUR)
                sink.extend(self._parse(res, lambda b, fn=fn: fn(_json(b))))
                main = main or res
            except DataUnavailable as exc:
                warnings.append(f"{url}: {exc}")
        if main is None:
            raise DataUnavailable(f"no result filings for {symbol}: {'; '.join(warnings)}")
        merged = [f for f in p.merge_result_filings(legacy, integrated) if f.symbol.upper() == symbol.upper()]
        latest = max((f.broadcast_at for f in merged if f.broadcast_at), default=None)
        return ProviderResult(merged, self._prov(main, "NSE financial results filings", latest), warnings)

    def financial_statement(self, filing: ResultFiling) -> ProviderResult:
        if not filing.xbrl_url:
            raise DataUnavailable(f"no XBRL for {filing.symbol} {filing.period_end}")
        res = self.client.fetch(filing.xbrl_url, ttl=None)
        stmt: FinancialStatement = self._parse(
            res,
            lambda b: p.parse_xbrl_financials(b, filing.symbol, consolidated=filing.consolidated, is_bank=filing.is_bank),
        )
        warnings: list[str] = []
        if stmt.period_end != filing.period_end:
            warnings.append(f"XBRL period end {stmt.period_end} differs from listing {filing.period_end}")
        return ProviderResult(stmt, self._prov(res, "NSE results XBRL", filing.broadcast_at), warnings)

    def shareholding(self, symbol: str) -> ProviderResult:
        url = f"{WWW_API}/corporate-share-holdings-master?{urlencode({'index': 'equities', 'symbol': symbol})}"
        res = self.client.fetch(url, ttl=12 * HOUR)
        rows = self._parse(res, lambda b: p.parse_shareholding(_json(b)))
        latest = max((r.broadcast_at for r in rows if r.broadcast_at), default=None)
        return ProviderResult(rows, self._prov(res, "NSE shareholding pattern", latest))


# ------------------------------------------------------------------ corporate actions
class NSECorporateActionProvider(_NSEBase, CorporateActionProvider):
    def corporate_actions(self, start: date, end: date) -> ProviderResult:
        q = urlencode({"index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{end:%d-%m-%Y}"})
        res = self.client.fetch(f"{WWW_API}/corporates-corporateActions?{q}", ttl=6 * HOUR)
        rows = self._parse(res, lambda b: p.parse_corporate_actions(_json(b)))
        return ProviderResult(rows, self._prov(res, "NSE corporate actions"))

    def event_calendar(self) -> ProviderResult:
        res = self.client.fetch(f"{WWW_API}/event-calendar?index=equities", ttl=6 * HOUR)
        rows = self._parse(res, lambda b: p.parse_event_calendar(_json(b)))
        return ProviderResult(rows, self._prov(res, "NSE event calendar (board meetings)"))


# ------------------------------------------------------------------ announcements
class NSEAnnouncementsProvider(_NSEBase, NewsProvider):
    """Primary-source exchange announcements from the NSE RSS feeds."""

    name = "nse_rss"

    def __init__(self, client: NSEClient | None = None, feeds: dict[str, str] | None = None) -> None:
        super().__init__(client)
        self.feeds = feeds or RSS_FEEDS

    def latest(self) -> ProviderResult:
        items = []
        warnings: list[str] = []
        first: FetchResult | None = None
        for source, url in self.feeds.items():
            try:
                res = self.client.fetch(url, ttl=300)
                items.extend(self._parse(res, lambda b, s=source, u=url: p.parse_nse_rss(b, source=s, feed_url=u)))
                first = first or res
            except DataUnavailable as exc:
                warnings.append(f"{source}: {exc}")
        if first is None:
            raise DataUnavailable("all NSE RSS feeds failed: " + "; ".join(warnings))
        items.sort(key=lambda a: a.published_at, reverse=True)
        latest = items[0].published_at if items else None
        prov = self._prov(first, "NSE RSS announcements", latest)
        prov.url = None if len(self.feeds) > 1 else prov.url
        return ProviderResult(items, prov, warnings)


# ------------------------------------------------------------------ F&O
class NSEFnoProvider(_NSEBase, FNOProvider):
    def fo_bhavcopy(self, session: date) -> ProviderResult:
        if session < UDIFF_START:
            raise DataUnavailable("F&O bhavcopy before 2024-07-08 (legacy format) is not supported")
        res = self.client.fetch(fo_bhavcopy_url(session), ttl=_archive_ttl(session))
        futs, opts = self._parse(res, p.parse_fo_bhavcopy_udiff)
        if not futs and not opts:
            raise DataUnavailable(f"no F&O rows for {session}")
        return ProviderResult((futs, opts), self._prov(res, "NSE F&O bhavcopy (UDiFF)", session_close(session)))

    def lot_sizes(self) -> ProviderResult:
        res = self.client.fetch(f"{ARCHIVES}/content/fo/fo_mktlots.csv", ttl=12 * HOUR)
        return ProviderResult(self._parse(res, p.parse_lot_sizes), self._prov(res, "NSE F&O market lots"))


# ------------------------------------------------------------------ flows / calendar
class NSEFlowsProvider(_NSEBase, FlowsProvider):
    def institutional_flows(self) -> ProviderResult:
        res = self.client.fetch(f"{WWW_API}/fiidiiTradeReact", ttl=30 * 60)
        rows = self._parse(res, lambda b: p.parse_fii_dii(_json(b)))
        if not rows:
            raise DataUnavailable("FII/DII flows empty")
        ts = session_close(max(r.date for r in rows))
        return ProviderResult(
            rows, self._prov(res, "NSE FII/DII provisional trading activity", ts, DataQuality.PROVISIONAL),
            ["FII/DII figures are provisional (exchange-reported, ₹ crore)"],
        )


class NSECalendarProvider(_NSEBase, CalendarProvider):
    def __init__(self, client: NSEClient | None = None, segment: str = "CM") -> None:
        super().__init__(client)
        self.segment = segment

    def holidays(self) -> ProviderResult:
        res = self.client.fetch(f"{WWW_API}/holiday-master?type=trading", ttl=DAY)
        rows = self._parse(res, lambda b: p.parse_holidays(_json(b), self.segment))
        return ProviderResult(rows, self._prov(res, "NSE trading holidays"))


def _json(b: bytes) -> Any:
    return json.loads(b)


__all__ = [
    "NSEAnnouncementsProvider",
    "NSECalendarProvider",
    "NSECorporateActionProvider",
    "NSEFlowsProvider",
    "NSEFnoProvider",
    "NSEFundamentalsProvider",
    "NSEMarketDataProvider",
    "cm_bhavcopy_url",
    "delivery_url",
    "fo_bhavcopy_url",
    "index_close_url",
    "session_close",
]
