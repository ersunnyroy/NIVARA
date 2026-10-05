from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.config.settings import Settings
from app.data.nse.client import NSEClient
from app.data.nse.provider import (
    NSEAnnouncementsProvider,
    NSECorporateActionProvider,
    NSEFlowsProvider,
    NSEFnoProvider,
    NSEFundamentalsProvider,
    NSEMarketDataProvider,
    cm_bhavcopy_url,
    delivery_url,
    index_close_url,
)
from app.data.providers.base import DataUnavailable, NotConfigured
from app.data.types import DataQuality

FIX = Path(__file__).parent / "fixtures" / "nse"


def zipped(name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, (FIX / name).read_bytes())
    return buf.getvalue()


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_client(tmp_path, routes, *, interval=0.0, website=True, clock: FakeClock | None = None):
    """routes: dict url -> (status, body) or callable(request) -> Response. Returns (client, calls)."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        r = routes.get(url)
        if r is None:
            return httpx.Response(404)
        if callable(r):
            return r(request)
        status, body = r
        return httpx.Response(status, content=body)

    settings = Settings(data_cache_dir=tmp_path, nse_min_request_interval_sec=interval, nse_website_api_enabled=website)
    fc = clock or FakeClock()
    client = NSEClient(
        settings, transport=httpx.MockTransport(handler), backoff=0.01, clock=fc.clock, sleep=fc.sleep
    )
    return client, calls


def test_404_raises_data_unavailable_and_is_not_cached(tmp_path):
    client, calls = make_client(tmp_path, {})
    with pytest.raises(DataUnavailable):
        client.fetch("https://nsearchives.nseindia.com/missing.csv")
    with pytest.raises(DataUnavailable):
        client.fetch("https://nsearchives.nseindia.com/missing.csv")
    assert len(calls) == 2  # no retries on 404, nothing cached


def test_cache_hit_avoids_second_request(tmp_path):
    url = "https://nsearchives.nseindia.com/content/x.csv"
    client, calls = make_client(tmp_path, {url: (200, b"a,b\n1,2\n")})
    first = client.fetch(url, ttl=None)
    second = client.fetch(url, ttl=None)
    assert first.content == second.content == b"a,b\n1,2\n"
    assert not first.from_cache and second.from_cache
    assert calls == [url]
    client.fetch(url, ttl=0)  # ttl<=0 bypasses cache
    assert len(calls) == 2


def test_ttl_expiry(tmp_path):
    import os
    import time

    url = "https://nsearchives.nseindia.com/content/y.csv"
    client, calls = make_client(tmp_path, {url: (200, b"x")})
    client.fetch(url, ttl=60)
    path = client._cache_path(url)
    old = time.time() - 120
    os.utime(path, (old, old))
    client.fetch(url, ttl=60)
    assert len(calls) == 2


def test_rate_limiter_spacing(tmp_path):
    fc = FakeClock()
    url = "https://nsearchives.nseindia.com/a"
    client, calls = make_client(tmp_path, {url: (200, b"x")}, interval=1.5, clock=fc)
    for _ in range(3):
        client.fetch(url, use_cache=False)
    assert len(calls) == 3
    assert fc.sleeps == [pytest.approx(1.5), pytest.approx(1.5)]


def test_retries_on_5xx_then_succeeds(tmp_path):
    url = "https://nsearchives.nseindia.com/b"
    seq = iter([503, 502, 200])

    def flaky(request):
        s = next(seq)
        return httpx.Response(s, content=b"ok" if s == 200 else b"")

    client, calls = make_client(tmp_path, {url: flaky})
    assert client.fetch(url).content == b"ok"
    assert len(calls) == 3


def test_retries_exhausted_raises(tmp_path):
    url = "https://nsearchives.nseindia.com/c"
    client, calls = make_client(tmp_path, {url: (500, b"")})
    with pytest.raises(DataUnavailable):
        client.fetch(url)
    assert len(calls) == client.max_retries + 1


def test_timeout_is_retried(tmp_path):
    url = "https://nsearchives.nseindia.com/d"
    state = {"n": 0}

    def slow(request):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, content=b"ok")

    client, _ = make_client(tmp_path, {url: slow})
    assert client.fetch(url).content == b"ok"


def test_www_403_primes_cookies_and_retries_once(tmp_path):
    api = "https://www.nseindia.com/api/fiidiiTradeReact"
    state = {"primed": False}

    def home(request):
        state["primed"] = True
        return httpx.Response(200, content=b"<html/>", headers={"set-cookie": "nsit=abc; Path=/"})

    def guarded(request):
        if not state["primed"]:
            return httpx.Response(403)
        assert "nsit=abc" in request.headers.get("cookie", "")
        return httpx.Response(200, content=(FIX / "fiidii.json").read_bytes())

    client, calls = make_client(tmp_path, {"https://www.nseindia.com/": home, api: guarded})
    data = client.get_json(api, ttl=60)
    assert data[0]["category"] == "DII"
    assert calls == [api, "https://www.nseindia.com/", api]


def test_www_still_forbidden_raises(tmp_path):
    api = "https://www.nseindia.com/api/x"
    client, calls = make_client(tmp_path, {"https://www.nseindia.com/": (403, b""), api: (403, b"")})
    with pytest.raises(DataUnavailable):
        client.fetch(api)
    assert calls == [api, "https://www.nseindia.com/", api]


def test_website_api_disabled_raises_not_configured(tmp_path):
    client, calls = make_client(tmp_path, {}, website=False)
    with pytest.raises(NotConfigured):
        client.fetch("https://www.nseindia.com/api/fiidiiTradeReact")
    assert calls == []
    with pytest.raises(NotConfigured):
        NSEFlowsProvider(client).institutional_flows()


# ---------------------------------------------------------------- providers
def test_bhavcopy_url_selection_legacy_vs_udiff():
    url, src = cm_bhavcopy_url(date(2024, 7, 8))
    assert url.endswith("/content/cm/BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip") and "UDiFF" in src
    url, src = cm_bhavcopy_url(date(2024, 7, 5))
    assert url.endswith("/content/historical/EQUITIES/2024/JUL/cm05JUL2024bhav.csv.zip") and "legacy" in src


def test_daily_bars_udiff_with_delivery(tmp_path):
    s = date(2026, 10, 1)
    routes = {
        cm_bhavcopy_url(s)[0]: (200, zipped("cm_udiff_20261001.csv")),
        delivery_url(s): (200, (FIX / "sec_bhavdata_full_01102026.csv").read_bytes()),
    }
    client, _ = make_client(tmp_path, routes)
    res = NSEMarketDataProvider(client).daily_bars(s)
    rel = next(b for b in res.data if b.symbol == "RELIANCE")
    assert rel.delivery_pct == 61.24 and res.warnings == []
    assert res.provenance.source == "NSE CM bhavcopy (UDiFF)" and res.provenance.quality == DataQuality.VERIFIED
    assert res.provenance.data_timestamp.hour == 15 and res.provenance.data_timestamp.minute == 30


def test_daily_bars_missing_delivery_still_returns_bars(tmp_path):
    s = date(2024, 6, 28)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cm28JUN2024bhav.csv", (FIX / "cm_legacy_28JUN2024.csv").read_bytes())
    client, calls = make_client(tmp_path, {cm_bhavcopy_url(s)[0]: (200, buf.getvalue())})
    res = NSEMarketDataProvider(client).daily_bars(s)
    assert len(res.data) == 2 and all(b.delivery_qty is None for b in res.data)
    assert res.warnings and "delivery" in res.warnings[0]
    assert res.provenance.source == "NSE CM bhavcopy (legacy)"
    assert any("cm28JUN2024bhav.csv.zip" in c for c in calls)


def test_daily_bars_missing_session_raises(tmp_path):
    client, _ = make_client(tmp_path, {})
    with pytest.raises(DataUnavailable):
        NSEMarketDataProvider(client).daily_bars(date(2026, 10, 2))


def test_bad_zip_is_not_cached(tmp_path):
    s = date(2026, 10, 1)
    url = cm_bhavcopy_url(s)[0]
    client, _ = make_client(tmp_path, {url: (200, b"PK\x03\x04garbage")})
    with pytest.raises(DataUnavailable):
        NSEMarketDataProvider(client).daily_bars(s)
    assert not client._cache_path(url).exists()


def test_index_bars(tmp_path):
    s = date(2026, 10, 1)
    client, _ = make_client(tmp_path, {index_close_url(s): (200, (FIX / "ind_close_all_01102026.csv").read_bytes())})
    res = NSEMarketDataProvider(client).index_bars(s)
    assert {b.index_name for b in res.data} == {"Nifty 50", "Nifty Bank", "India VIX"}


def test_index_constituents_falls_back_to_niftyindices(tmp_path):
    body = (FIX / "ind_nifty500list.csv").read_bytes()
    client, calls = make_client(
        tmp_path, {"https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv": (200, body)}
    )
    res = NSEMarketDataProvider(client).index_constituents("nifty500")
    assert res.data[0].symbol == "360ONE" and len(calls) == 2
    with pytest.raises(DataUnavailable):
        NSEMarketDataProvider(client).index_constituents("sensex")


def test_flows_are_provisional(tmp_path):
    client, _ = make_client(
        tmp_path, {"https://www.nseindia.com/api/fiidiiTradeReact": (200, (FIX / "fiidii.json").read_bytes())}
    )
    res = NSEFlowsProvider(client).institutional_flows()
    assert res.provenance.quality == DataQuality.PROVISIONAL and len(res.data) == 2


def test_fno_and_lots(tmp_path):
    s = date(2026, 10, 1)
    routes = {
        "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20261001_F_0000.csv.zip": (
            200, zipped("fo_udiff_20261001.csv"),
        ),
        "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv": (200, (FIX / "fo_mktlots.csv").read_bytes()),
    }
    client, _ = make_client(tmp_path, routes)
    prov = NSEFnoProvider(client)
    futs, opts = prov.fo_bhavcopy(s).data
    assert len(futs) == 2 and len(opts) == 2
    assert prov.lot_sizes().data["RELIANCE"] == 500
    with pytest.raises(DataUnavailable):
        prov.fo_bhavcopy(date(2024, 1, 5))


def test_result_filings_one_source_missing(tmp_path):
    q = "https://www.nseindia.com/api/integrated-filing-results?index=equities&type=Integrated+Filing-+Financials"
    client, _ = make_client(
        tmp_path, {f"{q}&symbol=RELIANCE": (200, (FIX / "results_integrated_reliance.json").read_bytes())}
    )
    res = NSEFundamentalsProvider(client).result_filings("RELIANCE")
    assert len(res.data) == 4 and res.warnings  # legacy list 404 → warning, not failure


def test_corporate_actions_and_announcements(tmp_path):
    ca_url = (
        "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
        "&from_date=01-09-2026&to_date=05-10-2026"
    )
    rss_url = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
    client, _ = make_client(
        tmp_path,
        {
            ca_url: (200, (FIX / "corporate_actions.json").read_bytes()),
            rss_url: (200, (FIX / "online_announcements.xml").read_bytes()),
        },
    )
    ca = NSECorporateActionProvider(client).corporate_actions(date(2026, 9, 1), date(2026, 10, 5))
    assert any(r.action_type == "split" for r in ca.data)
    news = NSEAnnouncementsProvider(client).latest()
    assert len(news.data) == 3 and len(news.warnings) == 2  # two other feeds 404
    assert news.data[0].published_at >= news.data[-1].published_at


# ---------------------------------------------------------------- brokers (mocked; untested against live APIs)
def test_brokers_require_credentials():
    from app.data.brokers.kite import KiteProvider
    from app.data.brokers.upstox import UpstoxProvider

    up = UpstoxProvider(access_token="", isin_by_symbol={"RELIANCE": "INE002A01018"})
    with pytest.raises(NotConfigured):
        up.quotes(["RELIANCE"])
    with pytest.raises(NotConfigured):
        up.daily_bars(date(2026, 10, 1))
    with pytest.raises(NotConfigured):
        KiteProvider(api_key="", access_token="").quotes(["RELIANCE"])


def test_upstox_quote_parsing_mocked():
    from app.data.brokers.upstox import UpstoxProvider

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["key"] = request.url.params["instrument_key"]
        return httpx.Response(200, json={"status": "success", "data": {"NSE_EQ:RELIANCE": {
            "instrument_token": "NSE_EQ|INE002A01018", "last_price": 1167.7, "net_change": -19.3, "volume": 100,
            "average_price": 1170.0, "ohlc": {"open": 1180.1, "high": 1183.9, "low": 1160.8, "close": 1167.7},
            "timestamp": "2026-10-01T15:30:00.000+05:30"}}})

    up = UpstoxProvider("tok", isin_by_symbol={"RELIANCE": "INE002A01018"},
                        client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = up.quotes(["RELIANCE", "UNKNOWN"])
    q = res.data[0]
    assert q.symbol == "RELIANCE" and q.prev_close == pytest.approx(1187.0) and not q.is_delayed
    assert seen == {"auth": "Bearer tok", "key": "NSE_EQ|INE002A01018"}
    assert any("UNKNOWN" in w for w in res.warnings)


def test_registry_realtime_none_without_credentials(monkeypatch):
    from app.data import registry

    monkeypatch.setattr(registry, "get_settings", lambda: Settings(upstox_access_token=None, kite_api_key=None,
                                                                   kite_access_token=None))
    assert registry.realtime_quotes() is None
    assert len(registry.news()) >= 1
