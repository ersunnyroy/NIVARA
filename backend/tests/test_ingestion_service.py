"""Ingestion services with stubbed providers (no network)."""
from datetime import date, datetime

from sqlalchemy import select

from app.core.timeutil import IST, utcnow
from app.data.types import CorporateActionRecord, DailyBar, IndexBar, Provenance, ProviderResult, SecurityInfo
from app.models import OHLCV, CorporateAction, IndexOHLCV, PriceAdjustment, Stock
from app.services import ingestion


class FakeMD:
    name = "fake"

    def __init__(self, bars):
        self._bars = bars

    def securities(self):
        return ProviderResult([SecurityInfo("ABC", "ABC Ltd", "EQ", "INE000000001")], Provenance("fake", utcnow()))

    def daily_bars(self, session):
        return ProviderResult([b for b in self._bars if b.date == session],
                              Provenance("fake bhavcopy", utcnow(), datetime(2026, 1, 1, 15, 30, tzinfo=IST)))

    def index_bars(self, session):
        return ProviderResult([IndexBar("Nifty 50", session, 1, 1, 1, 100.0)], Provenance("fake idx", utcnow()))

    def index_constituents(self, idx):
        return ProviderResult([SecurityInfo("ABC", "ABC Ltd", "EQ", None, industry="Information Technology")],
                              Provenance("fake", utcnow()))


class FakeCA:
    name = "fake"

    def corporate_actions(self, start, end):
        return ProviderResult([CorporateActionRecord("ABC", "Bonus 1:1", date(2026, 1, 6), None, "bonus", 1, 1)],
                              Provenance("fake ca", utcnow()))


class FakeFno:
    def lot_sizes(self):
        return ProviderResult({"ABC": 500}, Provenance("fake", utcnow()))


def test_eod_securities_and_corporate_action_adjustment(db, monkeypatch):
    bars = [DailyBar("ABC", "EQ", date(2026, 1, 5), 100, 101, 99, 100, 99, 1000, 1e5),
            DailyBar("ABC", "EQ", date(2026, 1, 6), 50, 51, 49, 50.5, 100, 2000, 1e5)]
    monkeypatch.setattr(ingestion.registry, "market_data", lambda: FakeMD(bars))
    monkeypatch.setattr(ingestion.registry, "corporate_actions", lambda: FakeCA())
    monkeypatch.setattr(ingestion.registry, "fno", lambda: FakeFno())
    out = ingestion.ingest_securities(db)
    assert out["securities"] == 1 and out["fno"] == 1
    st = db.scalar(select(Stock).where(Stock.symbol == "ABC"))
    assert st.is_fno and st.fno_lot_size == 500 and st.industry == "Information Technology"
    for d in (date(2026, 1, 5), date(2026, 1, 6)):
        ingestion.ingest_eod(db, d)
    assert db.query(OHLCV).count() == 2 and db.query(IndexOHLCV).count() == 2
    res = ingestion.ingest_corporate_actions(db, date(2026, 1, 1), date(2026, 1, 31))
    assert db.query(CorporateAction).count() == 1
    adj = db.scalar(select(PriceAdjustment))
    assert adj is not None and abs(adj.factor - 0.5) < 1e-9 and res["adjustments"]["applied"] == 1


def test_corporate_action_factor():
    f = ingestion.corporate_action_factor
    assert f("split", 10, 2) == 0.2
    assert f("bonus", 1, 1) == 0.5
    assert abs(f("bonus", 1, 2) - 2 / 3) < 1e-12
    assert f("dividend", 1, 1) is None and f("split", None, 2) is None


def test_upsert_dedupes_conflict_keys(db):
    from app.models import Exchange
    from app.repositories.upsert import upsert

    n = upsert(db, Exchange, [{"code": "MCX", "name": "a"}, {"code": "MCX", "name": "b"}], ["code"])
    db.commit()
    assert n == 1 and db.get(Exchange, "MCX").name == "b"
