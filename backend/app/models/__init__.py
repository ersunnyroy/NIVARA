"""Import all models so Base.metadata is complete (Alembic, tests)."""
from app.models.backtest import Backtest, BacktestTrade
from app.models.base import Base
from app.models.fno import FnoFuture, FnoSnapshot, OptionChainRow
from app.models.fundamentals import EventCalendar, FinancialResult, FundamentalSnapshot, Shareholding
from app.models.market import (
    OHLCV,
    CorporateAction,
    Exchange,
    IndexOHLCV,
    InstitutionalFlow,
    MarketBreadth,
    MarketHoliday,
    MarketRegime,
    PriceAdjustment,
    PriceQuote,
    Sector,
    SectorStrength,
    Stock,
)
from app.models.news import NewsItem, NewsSentiment
from app.models.portfolio import PaperOrder, Portfolio, PortfolioPosition, RealizedGain, TaxLot, Trade, Transaction
from app.models.signals import (
    ModelVersion,
    Recommendation,
    RecommendationOutcome,
    ScanRun,
    Signal,
    TechnicalSnapshot,
)
from app.models.system import AppSetting, AuditLog, DataSource, IngestionRun
from app.models.tax import ChargeSchedule, TaxProfile, TaxRule
from app.models.user import User, UserSession
from app.models.watch import Alert, AlertEvent, Watchlist, WatchlistItem

__all__ = [
    "OHLCV",
    "Alembic",
    "Alert",
    "AlertEvent",
    "AppSetting",
    "AuditLog",
    "Backtest",
    "BacktestTrade",
    "Base",
    "ChargeSchedule",
    "CorporateAction",
    "DataSource",
    "EventCalendar",
    "Exchange",
    "FinancialResult",
    "FnoFuture",
    "FnoSnapshot",
    "FundamentalSnapshot",
    "IndexOHLCV",
    "IngestionRun",
    "InstitutionalFlow",
    "MarketBreadth",
    "MarketHoliday",
    "MarketRegime",
    "ModelVersion",
    "NewsItem",
    "NewsSentiment",
    "OptionChainRow",
    "PaperOrder",
    "Portfolio",
    "PortfolioPosition",
    "PriceAdjustment",
    "PriceQuote",
    "RealizedGain",
    "Recommendation",
    "RecommendationOutcome",
    "ScanRun",
    "Sector",
    "SectorStrength",
    "Shareholding",
    "Signal",
    "Stock",
    "TaxLot",
    "TaxProfile",
    "TaxRule",
    "TechnicalSnapshot",
    "Trade",
    "Transaction",
    "User",
    "UserSession",
    "Watchlist",
    "WatchlistItem",
]
