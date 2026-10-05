from datetime import datetime, timedelta

from app.core.timeutil import IST
from app.models import MarketHoliday
from app.services.scanner import run_scan
from tests.helpers import add_index, add_stock, last_date


def test_simple_view_without_data_is_honest(auth_client):
    v = auth_client.get("/api/simple").json()
    assert v["this_week"]["status"] == "data_unavailable"
    assert v["today_intraday"]["status"] == "needs_live_data"
    assert "not advice" in v["disclaimer"] and v["glossary"]


def test_simple_view_translates_scan(auth_client, db):
    for i, sym in enumerate(("AAA", "BBB", "CCC")):
        add_stock(db, sym, n=320, drift=0.003 + i * 0.0005, seed=40 + i)
    add_index(db, n=320)
    d = last_date(db)
    db.add(MarketHoliday(exchange_code="NSE", date=d - timedelta(days=500), segment="CM", description="x"))
    db.commit()
    run_scan(db, as_of=d, now=datetime(d.year, d.month, d.day, 20, 0, tzinfo=IST), trigger="test")
    v = auth_client.get("/api/simple?refresh=true").json()
    for it in v["this_week"]["items"]:
        assert it["possible_loss_pct"] < 0 and all(t["gain_pct"] > 0 for t in it["targets"])
        assert it["what_could_go_wrong"] and it["simple_plan"].startswith("If you buy between")
        assert it["tone"] in ("buy", "wait", "avoid")
