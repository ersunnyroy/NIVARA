from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

from app.data.nse import parsers as p
from app.data.rss import IST, parse_feed, parse_feed_datetime

FIX = Path(__file__).parent / "fixtures" / "nse"


def raw(name: str) -> bytes:
    return (FIX / name).read_bytes()


def load(name: str):
    return json.loads(raw(name))


def zipped(name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, raw(name))
    return buf.getvalue()


def test_primitives_dash_and_blank_are_none():
    assert p.num("-") is None and p.num("") is None and p.num(" NA ") is None
    assert p.num("1,234.50") == 1234.5 and p.num("-.88") == -0.88
    assert p.integer("16771221") == 16771221
    assert p.parse_date("30-JUN-2026") == date(2026, 6, 30)
    assert p.parse_date("01-10-2026") == date(2026, 10, 1)
    dt = p.parse_ist_datetime("17-Jul-2026 19:50:03")
    assert dt == datetime(2026, 7, 17, 19, 50, 3, tzinfo=IST)


def test_equity_list_strips_header_whitespace():
    rows = p.parse_equity_list(raw("equity_l.csv"))
    rel = next(r for r in rows if r.symbol == "RELIANCE")
    assert rel.isin == "INE002A01018" and rel.series == "EQ" and rel.face_value == 10.0
    assert rel.listing_date == date(1995, 11, 29)


def test_udiff_bhavcopy_from_zip_filters_series():
    bars = p.parse_cm_bhavcopy_udiff(zipped("cm_udiff_20261001.csv"))
    syms = {b.symbol: b for b in bars}
    assert "SGBJUN28" not in syms  # GB series dropped
    assert {"RELIANCE", "20MICRONS", "3IINFOLTD", "AAKAAR"} <= set(syms)
    rel = syms["RELIANCE"]
    assert (rel.open, rel.high, rel.low, rel.close, rel.prev_close) == (1180.10, 1183.90, 1160.80, 1167.70, 1187.00)
    assert rel.volume == 16771221 and rel.trades == 279428 and rel.date == date(2026, 10, 1)
    assert rel.delivery_qty is None
    all_series = p.parse_cm_bhavcopy_udiff(raw("cm_udiff_20261001.csv"), series=None)
    assert any(b.symbol == "SGBJUN28" for b in all_series)


def test_legacy_bhavcopy():
    bars = p.parse_cm_bhavcopy_legacy(raw("cm_legacy_28JUN2024.csv"))
    assert {b.symbol for b in bars} == {"RELIANCE", "INFY"}  # YR series dropped
    rel = next(b for b in bars if b.symbol == "RELIANCE")
    assert rel.date == date(2024, 6, 28) and rel.close == 3130.8 and rel.prev_close == 3061.1
    assert rel.volume == 14478668 and rel.isin == "INE002A01018"


def test_delivery_merge_handles_dash():
    bars = p.parse_cm_bhavcopy_udiff(raw("cm_udiff_20261001.csv"))
    deliv = p.parse_delivery(raw("sec_bhavdata_full_01102026.csv"))
    assert deliv[("3IINFOLTD", "BE")] == (None, None)
    assert p.merge_delivery(bars, deliv) == 3
    rel = next(b for b in bars if b.symbol == "RELIANCE")
    assert rel.delivery_qty == 10270423 and rel.delivery_pct == 61.24


def test_index_close_with_dash_values():
    bars = {b.index_name: b for b in p.parse_index_close(raw("ind_close_all_01102026.csv"))}
    assert bars["Nifty 50"].close == 22421.95 and bars["Nifty 50"].change_pct == -0.88
    vix = bars["India VIX"]
    assert vix.close == 14.46 and vix.pe is None and vix.volume is None and vix.turnover_cr is None


def test_fo_bhavcopy_and_lots():
    futs, opts = p.parse_fo_bhavcopy_udiff(raw("fo_udiff_20261001.csv"))
    assert {(f.underlying, f.instrument) for f in futs} == {("NIFTY", "IDF"), ("RELIANCE", "STF")}
    nf = next(f for f in futs if f.underlying == "NIFTY")
    assert nf.expiry == date(2026, 12, 29) and nf.lot_size == 65 and nf.oi == 201890
    assert {(o.underlying, o.option_type, o.strike) for o in opts} == {("RELIANCE", "CE", 1230.0), ("NIFTY", "PE", 20750.0)}
    lots = p.parse_lot_sizes(raw("fo_mktlots.csv"))
    assert lots == {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 500}


def test_index_constituents():
    rows = p.parse_index_constituents(raw("ind_nifty500list.csv"))
    assert rows[0].symbol == "360ONE" and rows[0].industry == "Financial Services" and rows[0].isin == "INE466L01038"


def test_nse_rss():
    items = p.parse_nse_rss(raw("online_announcements.xml"))
    assert len(items) == 3
    first = items[0]
    assert first.company == "Embassy Developments Limited"
    assert first.headline == "Embassy Developments Limited: Press Release"
    assert first.published_at == datetime(2026, 10, 5, 9, 3, 37, tzinfo=IST)
    assert first.source_tier == "primary" and first.symbol is None
    nav = items[2]
    assert nav.symbol == "PSUBANK" and nav.url is None


def test_generic_rss_rfc822_and_atom():
    rss = (
        b"<rss><channel><title>Feed</title><item><title>A</title><link>http://x/a</link>"
        b"<pubDate>Mon, 05 Oct 2026 09:11:57 +0530</pubDate></item>"
        b"<item><title>no date</title></item></channel></rss>"
    )
    items = parse_feed(rss)
    assert len(items) == 1 and items[0].source == "Feed" and items[0].published_at.utcoffset().seconds == 19800
    atom = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><title>F</title><entry><title>B</title>'
        b'<link href="http://x/b"/><updated>2026-10-05T03:00:00Z</updated></entry></feed>'
    )
    a = parse_feed(atom)[0]
    assert a.url == "http://x/b" and a.published_at.year == 2026
    assert parse_feed_datetime("garbage") is None


def test_holidays_and_flows():
    hols = p.parse_holidays(load("holidays.json"))
    assert [h.date for h in hols] == [date(2026, 1, 15), date(2026, 1, 26), date(2026, 2, 15)]
    assert all(h.segment == "CM" for h in hols)
    assert len(p.parse_holidays(load("holidays.json"), segment=None)) == 4
    flows = {f.category: f for f in p.parse_fii_dii(load("fiidii.json"))}
    assert flows["FII"].net_value_cr == -9484.22 and flows["DII"].buy_value_cr == 25420.04
    assert flows["FII"].date == date(2026, 10, 1)


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Dividend - Rs 60 Per Share", ("dividend", None, None, 60.0)),
        ("Interim Dividend - Re 0.30 Per Share", ("dividend", None, None, 0.30)),
        ("Interim Dividend - Rs 7.50 Per Share & Special Dividend Rs 86.50 Per Share", ("dividend", None, None, 94.0)),
        ("Dividend - Re 1 Per Sh", ("dividend", None, None, 1.0)),
        ("Intdividend - Rs 160 Per Share", ("dividend", None, None, 160.0)),
        ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", ("split", 10.0, 2.0, None)),
        ("Face Value Split (Sub-Division) - From Re 1/- Per Share To Re 0.10/- Per Share", ("split", 1.0, 0.10, None)),
        ("Bonus 1:1", ("bonus", 1.0, 1.0, None)),
        ("Bonus 3:2", ("bonus", 3.0, 2.0, None)),
        ("Scheme Of Arrangement - Bonus Ncrps 46:1", ("other", None, None, None)),
        ("Rights 3:8 @ Premium Rs 14/-", ("rights", 3.0, 8.0, 14.0)),
        ("Buy Back", ("buyback", None, None, None)),
        ("Demerger", ("demerger", None, None, None)),
        ("Annual General Meeting", ("other", None, None, None)),
    ],
)
def test_ca_subject_parsing(subject, expected):
    assert p.parse_ca_subject(subject) == expected


def test_corporate_actions_records():
    rows = p.parse_corporate_actions(load("corporate_actions.json"))
    pg = next(r for r in rows if r.symbol == "PGHH")
    assert pg.action_type == "dividend" and pg.amount == 60.0 and pg.ex_date == date(2026, 9, 1)
    assert pg.raw["isin"] == "INE179A01014"
    assert {r.action_type for r in rows} >= {"dividend", "split", "bonus", "rights", "buyback", "demerger", "other"}


def test_event_calendar_and_shareholding():
    ev = p.parse_event_calendar(load("event_calendar.json"))
    assert ev[0].symbol == "ARCIL" and ev[0].event_date == date(2026, 10, 6) and ev[0].purpose == "Financial Results"
    shp = p.parse_shareholding(load("shareholding_reliance.json"))
    assert shp[0].period_end == date(2026, 6, 30) and shp[0].promoter_pct == 50.48 and shp[0].public_pct == 49.52
    assert shp[0].broadcast_at == datetime(2026, 7, 16, 19, 24, 44, tzinfo=IST)


def test_result_filings_merge_prefers_integrated():
    legacy = p.parse_result_filings_legacy(load("results_legacy_reliance.json"))
    integrated = p.parse_integrated_filings(load("results_integrated_reliance.json"))
    assert legacy[0].period_start == date(2024, 10, 1) and legacy[0].consolidated is False
    assert integrated[0].period_end == date(2026, 6, 30) and integrated[0].consolidated is True
    assert integrated[0].audited is False and integrated[2].audited is True
    merged = p.merge_result_filings(legacy, integrated)
    assert len(merged) == 6 and merged[0].period_end == date(2026, 6, 30)

    # overlapping period: integrated must win, legacy period_start carried over
    overlap = p.parse_result_filings_legacy(load("results_legacy_reliance.json"))[1]
    overlap.period_end, overlap.period_start = date(2026, 6, 30), date(2026, 4, 1)
    merged = p.merge_result_filings([overlap], integrated)
    q1 = next(f for f in merged if f.period_end == date(2026, 6, 30) and f.consolidated)
    assert "INTEGRATED_FILING" in (q1.xbrl_url or "") and q1.period_start == date(2026, 4, 1)


def test_xbrl_legacy_picks_quarter_context_not_ytd():
    st = p.parse_xbrl_financials(raw("xbrl_reliance_q3fy25.xml"), "RELIANCE")
    # FourD (YTD) declares the same context period as OneD; its own DateOfStart fact (Apr-01) disambiguates.
    assert st.raw["context"] == "OneD"
    assert (st.period_start, st.period_end) == (date(2024, 10, 1), date(2024, 12, 31))
    assert st.consolidated is True and st.is_bank is False
    assert st.revenue == 2438650000000.0 and st.pat == 219300000000.0 and st.pat_owners == 185400000000.0
    assert st.eps_basic == 13.70 and st.face_value == 10.0 and st.paid_up_capital == 135320000000.0
    assert st.ebitda == st.pbt + st.finance_costs + st.depreciation - st.other_income


def test_xbrl_integrated_filing_namespace_agnostic():
    st = p.parse_xbrl_financials(raw("xbrl_reliance_integrated_q1fy27.xml"))
    assert st.symbol == "RELIANCE" and st.period_end == date(2026, 6, 30) and st.period_start == date(2026, 4, 1)
    assert st.revenue == 3118500000000.0 and st.eps_basic == 15.48 and st.debt_equity == 0.004
    assert st.interest_coverage == 0.0467


def test_xbrl_bank_fallback_and_unknown_none():
    doc = b"""<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:b="urn:bank">
    <x:context id="OneD"><x:entity/><x:period><x:startDate>2026-04-01</x:startDate><x:endDate>2026-06-30</x:endDate>
    </x:period></x:context>
    <b:DateOfStartOfReportingPeriod contextRef="OneD">2026-04-01</b:DateOfStartOfReportingPeriod>
    <b:DateOfEndOfReportingPeriod contextRef="OneD">2026-06-30</b:DateOfEndOfReportingPeriod>
    <b:InterestEarned contextRef="OneD">1000</b:InterestEarned>
    <b:InterestExpended contextRef="OneD">400</b:InterestExpended>
    </x:xbrl>"""
    st = p.parse_xbrl_financials(doc, "HDFCBANK")
    assert st.is_bank is True and st.revenue == 1000.0 and st.finance_costs is None and st.raw["InterestExpended"] == 400.0
    assert st.pat is None and st.depreciation is None and st.ebitda is None


def test_xbrl_garbage_raises():
    with pytest.raises(p.ParseError):
        p.parse_xbrl_financials(b"<html>not xbrl")
