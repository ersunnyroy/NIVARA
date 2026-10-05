from app.data.nse.live import fetch_snapshot
from app.data.providers.base import DataUnavailable


class FakeClient:
    def __init__(self, fail=()):
        self.fail = fail

    def get_json(self, url, ttl=None):
        if any(f in url for f in self.fail):
            raise DataUnavailable("blocked")
        if url.endswith("allIndices"):
            return {"timestamp": "05-Oct-2026 12:26", "data": [
                {"index": "NIFTY 50", "last": 22451.6, "percentChange": 0.13, "previousClose": 22421.95},
                {"index": "NIFTY 500", "last": 20000, "percentChange": -0.1, "advances": "210", "declines": "290"}]}
        if "variations" in url:
            return {"allSec": {"timestamp": "05-Oct-2026 12:26:47", "data": [
                {"symbol": "ABC", "series": "EQ", "ltp": 110.0, "prev_price": 100.0, "perChange": 10.0,
                 "open_price": 101, "high_price": 111, "low_price": 100, "trade_quantity": 5000}]}}
        if "most-active" in url:
            return {"data": [{"symbol": "ABC", "lastPrice": 110.0, "previousClose": 100.0, "pChange": 10.0,
                              "lastUpdateTime": "2026-10-05 12:26:46"},
                             {"symbol": "XYZ", "lastPrice": 50.5, "previousClose": 51.0, "pChange": -0.98,
                              "lastUpdateTime": "2026-10-05 12:26:46"}]}
        return {}


def test_snapshot_merges_sources_and_tags_lists():
    s = fetch_snapshot(FakeClient())
    assert s.as_of.hour == 12 and len(s.indices) == 2
    assert set(s.quotes) == {"ABC", "XYZ"}
    assert "top gainer" in s.quotes["ABC"].lists and any("most active" in t for t in s.quotes["ABC"].lists)
    assert s.gainers == ["ABC"] and s.warnings == []


def test_snapshot_degrades_when_a_source_fails():
    s = fetch_snapshot(FakeClient(fail=("variations",)))
    assert len(s.indices) == 2 and set(s.quotes) == {"ABC", "XYZ"}
    assert any("gainers" in w for w in s.warnings)
