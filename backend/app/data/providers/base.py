"""Provider abstraction layer. Swap implementations without touching analytics.

Contract for all providers:
* Never fabricate data. If data is unavailable raise `DataUnavailable` (or return an empty result
  with a warning) — callers decide how to degrade (e.g. reduce confidence, disable recommendation).
* Respect the upstream's terms, robots.txt and rate limits; cache aggressively.
* Return provider-neutral records from `app.data.types` with `Provenance`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.data.types import ProviderResult


class ProviderError(Exception):
    pass


class DataUnavailable(ProviderError):
    """The requested data does not exist (yet) or the source is unreachable."""


class NotConfigured(ProviderError):
    """Provider needs credentials/config that are not set."""


class MarketDataProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def securities(self) -> ProviderResult:  # list[SecurityInfo]
        ...

    @abstractmethod
    def daily_bars(self, session: date) -> ProviderResult:  # list[DailyBar], whole market for that session
        ...

    @abstractmethod
    def index_bars(self, session: date) -> ProviderResult:  # list[IndexBar]
        ...

    def history(self, symbol: str, start: date, end: date) -> ProviderResult:  # list[DailyBar]
        raise NotConfigured(f"{self.name} does not provide per-symbol history")

    def quotes(self, symbols: list[str]) -> ProviderResult:  # list[Quote]
        raise NotConfigured(f"{self.name} does not provide live/delayed quotes")

    def index_constituents(self, index: str) -> ProviderResult:  # list[SecurityInfo] with industry
        raise NotConfigured(f"{self.name} does not provide index constituents")


class FundamentalDataProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def result_filings(self, symbol: str) -> ProviderResult:  # list[ResultFiling]
        ...

    @abstractmethod
    def financial_statement(self, filing) -> ProviderResult:  # FinancialStatement
        ...

    def shareholding(self, symbol: str) -> ProviderResult:  # list[ShareholdingRecord]
        raise NotConfigured(f"{self.name} does not provide shareholding")


class CorporateActionProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def corporate_actions(self, start: date, end: date) -> ProviderResult:  # list[CorporateActionRecord]
        ...

    def event_calendar(self) -> ProviderResult:  # list[EventRecord]
        raise NotConfigured(f"{self.name} does not provide an event calendar")


class NewsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def latest(self) -> ProviderResult:  # list[Announcement]
        ...


class FNOProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def fo_bhavcopy(self, session: date) -> ProviderResult:  # (list[FuturesRow], list[OptionRow])
        ...

    def lot_sizes(self) -> ProviderResult:  # dict[symbol, lot]
        raise NotConfigured(f"{self.name} does not provide lot sizes")


class FlowsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def institutional_flows(self) -> ProviderResult:  # list[FlowRecord]
        ...


class CalendarProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def holidays(self) -> ProviderResult:  # list[HolidayRecord]
        ...
