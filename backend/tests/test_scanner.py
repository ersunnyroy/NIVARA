from datetime import datetime, timedelta

from app.core.timeutil import IST
from app.models import MarketHoliday
from app.services.scanner import run_scan
from tests.helpers import add_index, add_stock, last_date


def test_no_data_means_no_recommendations(db):
    run = run_scan(db)
    assert run.status == "data_unavailable"
    assert "DATA UNAVAILABLE" in run.notes[0]


def test_stale_data_disables_recommendations(db):
    add_stock(db, "OLDCO", n=260, start="2024-01-01")
    run = run_scan(db, now=datetime(2026, 10, 5, 20, 0, tzinfo=IST))
    assert run.status == "data_stale" and "DATA STALE" in run.notes[0]


def test_scan_snapshot_records_versions_and_explanations(db):
    for i, sym in enumerate(("AAA", "BBB", "CCC", "DDD")):
        add_stock(db, sym, n=320, drift=0.002 + i * 0.0005, seed=10 + i)
    add_index(db, n=320)
    d = last_date(db)
    db.add(MarketHoliday(exchange_code="NSE", date=d - timedelta(days=400), segment="CM", description="x"))
    db.commit()
    now = datetime(d.year, d.month, d.day, 20, 0, tzinfo=IST)
    run = run_scan(db, as_of=d, now=now, trigger="test")
    assert run.status in ("ok", "ok_no_candidates")
    assert run.model_version and run.scoring_version and run.indicator_version and run.weights
    assert run.universe_size >= 4
    from app.models import Recommendation, Signal

    sigs = db.query(Signal).filter(Signal.run_id == run.id).all()
    assert len(sigs) == run.eligible_count
    for rec in db.query(Recommendation).filter(Recommendation.run_id == run.id):
        assert rec.why_not and rec.invalidation.startswith("Setup becomes invalid")
        assert rec.stop < rec.entry_low <= rec.entry_high < rec.target1
        assert rec.suitability in ("observation", "paper_trading")  # no track record yet → never live
        assert rec.data_sources and rec.score_breakdown["components"]
