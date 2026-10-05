"""Configured provider instances. All NSE providers share one polite (rate-limited, cached) client."""
from __future__ import annotations

from functools import lru_cache

from app.config.settings import get_settings
from app.data.brokers.kite import KiteProvider
from app.data.brokers.upstox import UpstoxProvider
from app.data.nse.client import NSEClient
from app.data.nse.provider import (
    NSEAnnouncementsProvider,
    NSECalendarProvider,
    NSECorporateActionProvider,
    NSEFlowsProvider,
    NSEFnoProvider,
    NSEFundamentalsProvider,
    NSEMarketDataProvider,
)
from app.data.providers.base import (
    CalendarProvider,
    CorporateActionProvider,
    FlowsProvider,
    FNOProvider,
    FundamentalDataProvider,
    MarketDataProvider,
    NewsProvider,
)
from app.data.rss import RSSNewsProvider


@lru_cache
def nse_client() -> NSEClient:
    return NSEClient(get_settings())


@lru_cache
def market_data() -> MarketDataProvider:
    return NSEMarketDataProvider(nse_client())


@lru_cache
def fundamentals() -> FundamentalDataProvider:
    return NSEFundamentalsProvider(nse_client())


@lru_cache
def corporate_actions() -> CorporateActionProvider:
    return NSECorporateActionProvider(nse_client())


def news() -> list[NewsProvider]:
    """Primary (NSE RSS) first, then configured secondary RSS feeds."""
    providers: list[NewsProvider] = [NSEAnnouncementsProvider(nse_client())]
    feeds = get_settings().news_rss_feeds
    if feeds:
        providers.append(RSSNewsProvider(feeds, source_tier="reputable"))
    return providers


@lru_cache
def fno() -> FNOProvider:
    return NSEFnoProvider(nse_client())


@lru_cache
def flows() -> FlowsProvider:
    return NSEFlowsProvider(nse_client())


@lru_cache
def calendar() -> CalendarProvider:
    return NSECalendarProvider(nse_client())


def realtime_quotes() -> MarketDataProvider | None:
    """Upstox if a token is configured, else Kite if key+token are configured, else None."""
    s = get_settings()
    if s.upstox_access_token:
        return UpstoxProvider(s.upstox_access_token)
    if s.kite_api_key and s.kite_access_token:
        return KiteProvider(s.kite_api_key, s.kite_access_token)
    return None


def reset() -> None:
    """Clear cached instances (tests / settings reload)."""
    for fn in (nse_client, market_data, fundamentals, corporate_actions, fno, flows, calendar):
        fn.cache_clear()
