# Data sources

All market data comes from official NSE public files and website endpoints, fetched by a polite, caching client.
Real-time quotes and AI are optional and need credentials. Providers implement the interfaces in
`backend/app/data/providers/base.py` and are wired in `backend/app/data/registry.py`.

Provider contract (from `providers/base.py`): never fabricate data; raise `DataUnavailable` or return an empty
result with a warning; respect upstream terms, robots.txt and rate limits; cache aggressively; return records with
provenance (`source`, `retrieved_at`, `data_timestamp`, `url`, `quality`).

## NSE client behaviour

`app/data/nse/client.py::NSEClient` (one shared instance per process):

| Aspect | Behaviour |
|---|---|
| Rate limit | Minimum interval between requests, thread-safe: `NSE_MIN_REQUEST_INTERVAL_SEC` (default 1.0 s) |
| User agent | Browser-like UA ending `NIVARA-research/0.1` (`nse_user_agent` setting) |
| Retries | Up to 3 retries with exponential backoff (1 s, 2 s, 4 s) on 5xx, timeouts and transport errors; never on 4xx |
| www.nseindia.com | Sends `Referer`; on 401/403 primes cookies once via the home page and retries once |
| Not found | 404 and other 4xx raise `DataUnavailable` |
| Disk cache | `DATA_CACHE_DIR/nse/<host>/<sha256(url)>`; `ttl=None` caches forever, otherwise expires after the TTL |
| Parse failures | Cached entry is invalidated and `DataUnavailable` raised |
| Switches | `NSE_ENABLED=false` disables all NSE fetches; `NSE_WEBSITE_API_ENABLED=false` disables www.nseindia.com JSON endpoints |

Past-session archive files are immutable and cached forever; the current day's files are cached for 1 hour.

## NSE endpoints used

Base URLs: archives `https://nsearchives.nseindia.com`, website API `https://www.nseindia.com/api`.

| Data | URL pattern | Cache TTL | Provides | Data-source key |
|---|---|---|---|---|
| Equity master | `/content/equities/EQUITY_L.csv` | 12 h | Symbol, name, series, ISIN, listing date, face value | `nse_securities` |
| Index constituents | `/content/indices/ind_<index>list.csv` (fallback `https://www.niftyindices.com/IndexConstituent/<file>`) for nifty50, niftynext50, nifty100, nifty200, nifty500 | 1 day | Index membership and NSE industry | `nse_index_constituents` |
| CM bhavcopy (UDiFF, sessions from 2024-07-08) | `/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip` | forever (past) / 1 h (today) | Daily OHLC, previous close, volume, turnover, trades for all equities | `nse_cm_bhavcopy` |
| CM bhavcopy (legacy, before 2024-07-08) | `/content/historical/EQUITIES/<YYYY>/<MON>/cm<DD><MON><YYYY>bhav.csv.zip` | as above | As above | `nse_cm_bhavcopy` |
| Delivery data | `/products/content/sec_bhavdata_full_<DDMMYYYY>.csv` | as above | Delivery quantity and % (missing → fields are `None` with a warning) | `nse_cm_bhavcopy` |
| Index closes | `/content/indices/ind_close_all_<DDMMYYYY>.csv` | as above | All NSE indices incl. India VIX: OHLC, change %, P/E, P/B, dividend yield | `nse_indices` |
| F&O bhavcopy (UDiFF only) | `/content/fo/BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip` | as above | Futures and options EOD rows, OI, change in OI, settlement. Sessions before 2024-07-08 are not supported | `nse_fo_bhavcopy` |
| F&O lot sizes | `/content/fo/fo_mktlots.csv` | 12 h | F&O eligibility and lot size | `nse_securities` |
| Financial results list | `/api/corporates-financial-results?index=equities&symbol=<S>&period=Quarterly` and `/api/integrated-filing-results?index=equities&type=Integrated Filing- Financials&symbol=<S>` | 6 h | Filing list with broadcast time and XBRL link (integrated filings preferred on merge) | `nse_results` |
| Results XBRL | URL from the filing list | forever | Quarterly P&L line items, EPS, paid-up capital, reported debt/equity and interest coverage | `nse_results` |
| Shareholding | `/api/corporate-share-holdings-master?index=equities&symbol=<S>` | 12 h | Promoter, pledge, FII, DII, MF, public % | `nse_shareholding` |
| Corporate actions | `/api/corporates-corporateActions?index=equities&from_date=<DD-MM-YYYY>&to_date=<DD-MM-YYYY>` | 6 h | Dividends, splits, bonus, rights, buybacks with parsed ratios | `nse_corporate_actions` |
| Event calendar | `/api/event-calendar?index=equities` | 6 h | Board meetings / results dates | `nse_event_calendar` |
| FII/DII flows | `/api/fiidiiTradeReact` | 30 min | Provisional cash-market buy/sell/net (₹ crore) for the **latest day only**, labelled `provisional` | `nse_flows` |
| Holidays | `/api/holiday-master?type=trading` | 1 day | Trading holidays (CM segment) for the current year | `nse_holidays` |
| Announcements RSS | `/content/RSS/Online_announcements.xml`, `/content/RSS/Financial_Results.xml`, `/content/RSS/Corporate_action.xml` | 5 min | Primary-source corporate announcements | `nse_announcements` |

### History limits of these endpoints

- **Holidays:** the holiday master covers the current year. During `backfill`, a past weekday with no published
  bhavcopy is recorded as a holiday with `source = "inferred"` so historical session arithmetic stays correct.
- **Special sessions** (trading on a weekend or holiday, e.g. the Union Budget session on Sunday 1 Feb 2026) are
  discovered automatically during backfill: when a session's published previous closes disagree with our last stored closes for most stocks, the closed days in between are probed for a bhavcopy and any found are ingested and recorded as `market_holidays` rows with `is_special_session = true` (source `inferred`).
- **FII/DII flows:** the endpoint returns only the latest day, so history accumulates one day per run. For
  earlier sessions the regime's `flows` component is listed as missing.

### Current database coverage

At the time of writing the development database holds EOD bars from 2025-07-01 to 2026-10-01 (312 sessions,
including the 2026-02-01 Budget-day special session), 6 inferred and 21 NSE-sourced holiday rows, 122
corporate-action adjustment factors, and FII/DII flows for one day (2026-10-01). These figures describe one
installation, not a guarantee.

## Refresh cadence

Celery beat (`app/workers/celery_app.py`, timezone Asia/Kolkata):

| Schedule (IST) | Task | Steps |
|---|---|---|
| Mon–Fri 08:15 | `nivara.pre_market` | holidays, FII/DII flows, corporate actions (−7 to +30 days) followed by split/bonus factor derivation, event calendar, news, F&O snapshots for the last session |
| Mon–Fri every 5 min, 09:00–15:55 | `nivara.intraday` | Skipped unless the calendar says the market is open. Quotes (only with a broker provider), news, alerts |
| Mon–Fri 19:00 and 21:30 (retry) | `nivara.post_market` | EOD bars + delivery + indices, F&O bhavcopy, F&O snapshots, flows, breadth, sector strength + regime, outcomes, Top-10 scan, paper orders, alerts |
| Every 20 min | `nivara.news` | NSE RSS + configured secondary feeds |
| Saturday 06:00 | `nivara.fundamentals_refresh` | Result filings, XBRL and shareholding for `nifty500` members |
| Saturday 07:00 | `nivara.securities` | Equity master, index constituents, lot sizes |

Every step is idempotent (upserts) and isolated; failures are recorded in `ingestion_runs` and `data_sources`.

Fundamentals ingestion makes up to 2 filing-list requests, up to 9 XBRL downloads (skipping periods already
stored) and 1 shareholding request per symbol, each subject to the request interval.

## Split/bonus adjustment

Stored bars are raw; adjustment factors live in `price_adjustments` and are applied on read
([database.md](database.md#price-storage-raw-bars--adjustment-factors)).

- The NSE UDiFF bhavcopy does **not** adjust `PrvsClsgPric` on ex-dates, so previous-close detection
  (`app/data/adjustments.py::detect_adjustments`) finds nothing on current data.
- Factors therefore come from NSE corporate-action records (`derive_adjustments_from_actions`, run after every
  `corporate_actions` job): split factor = new face value ÷ old face value; bonus a:b factor = b ÷ (a + b); split and
  bonus on the same ex-date are multiplied; duplicate filings are counted once; only ex-dates that have passed are
  applied.
- Each factor is checked against the observed close ratio across the ex-date and skipped if they differ by more
  than ±35% (the record may be mis-dated or mis-parsed). Factors with no bars around the ex-date are applied and
  noted as not price-verified.
- Rights issues, demergers and dividends are not adjusted.

## Data-quality labels

| Where | Values |
|---|---|
| Provenance quality (`app/data/types.py::DataQuality`) | `verified`, `provisional`, `derived`, `unverified`, `stale`, `unavailable` |
| Price kind (`services/prices.py`) | `live_quote`, `delayed_quote`, `eod_close`, `unavailable` — always shown with `as_of` and `source` |
| News | `source_tier` `primary` (exchange filing; `is_verified = true`), `reputable` (configured RSS, "not independently verified"), `other` |
| Scan run status | `data_unavailable`, `data_stale`, `ok`, `ok_no_candidates` |
| Admin source status | `GREEN`, `YELLOW`, `RED`, `DISABLED` (EOD sources are GREEN only when their data date ≥ the last completed session; others compare age with the SLA) |

## Terms of use

Every NSE data-source row is seeded with this note (`app/services/reference.py`):

> Official NSE public archives/website endpoints. Low request rate with on-disk caching; personal research use.
> Review NSE terms of use before any redistribution or commercial use.

The www.nseindia.com JSON endpoints are website APIs, not a licensed data feed. They can change format or block
automated access; when that happens the affected jobs fail with `DataUnavailable` and the UI shows the data as
unavailable or stale. For redistribution or commercial use, obtain a licensed feed.

## Optional real-time quotes (Upstox / Zerodha Kite)

Only one is used. `registry.realtime_quotes()` prefers Upstox when its token is set, else Kite when both Kite
values are set, else returns `None` and the app is EOD-only (`/api/market/status` reports
`realtime_quotes: false`).

| Provider | Env vars | Endpoints | Notes |
|---|---|---|---|
| Upstox API v2 | `UPSTOX_ACCESS_TOKEN` (daily token) | `https://api.upstox.com/v2/market-quote/quotes`, `/historical-candle/...` | Instrument keys are `NSE_EQ|<ISIN>` |
| Zerodha Kite Connect v3 | `KITE_API_KEY`, `KITE_ACCESS_TOKEN` (daily token) | `https://api.kite.trade/quote`, `/instruments/NSE`, `/instruments/historical/<token>/day` | |

Quotes are refreshed by the intraday task for held stocks, watchlist stocks and the latest recommendations
(up to 400 symbols) and stored in `prices`. For Upstox the symbol → ISIN map is filled from the `stocks` table before
each request. Each refresh updates the `upstox_quotes` / `kite_quotes` data-source status (success or error). A quote is used as the current price only if it is at most 20 minutes
old. Both adapter docstrings say to validate with real credentials before relying on them; they are tested only
with mocked HTTP. Tokens are never logged. EOD bars, indices and the security master always come from NSE.

## Secondary news (RSS)

`NEWS_RSS_FEEDS` adds RSS/Atom feeds (`app/data/rss.py`) with tier `reputable`. They are fetched with a 20 s
timeout and no NSE-style rate limiting or disk cache. Only add feeds whose terms permit this use.

## AI (Anthropic API)

| Setting | Default | Use |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables AI explanations (`app/ai/client.py`) |
| `AI_MODEL` | `claude-opus-5-5` | Model requested |
| `AI_EFFORT` | `medium` | Effort setting sent with each request |
| `AI_ENABLED` | `true` | Master switch |

Requests use structured JSON-schema output, cache the static system prompt, and are made only on demand
(stock analysis page, news analysis). The fact sheet sent to the model contains computed data only. Without a key,
deterministic explanations are shown.

## Not available without paid or licensed sources

The code explicitly returns "not available" for these; nothing is estimated in their place:

| Data | Status in NIVARA |
|---|---|
| Analyst estimates / consensus | Not in any feed (`app/fundamental/results.py`) |
| Intraday bars and intraday VWAP | Not available; `1D`/`5D` charts show daily bars, VWAP is a rolling 20-day volume-weighted price |
| Live quotes | Only with an Upstox or Kite token |
| Balance-sheet and cash-flow metrics (P/B, ROE, ROCE, operating cash flow, FCF, dividend yield, EV/EBITDA, net debt) | Quarterly XBRL P&L filings do not contain them; these metrics are `None` with the note "requires balance sheet / cash-flow data — not in quarterly filing feed" (EV/EBITDA: "net debt unknown"). Debt/equity is used only when the filing reports it; interest coverage is taken as reported or derived as TTM EBIT ÷ TTM finance costs |
| Global market context | No provider; the regime's `global` component is always listed as missing |
| F&O history before 2024-07-08 | Legacy F&O bhavcopy format not supported |
| Surveillance (ASM/GSM) flags, suspensions | Columns exist but no ingestion job populates them |
| FII/DII history | Endpoint returns the latest day only |
| Holiday master for past years | Inferred from missing bhavcopies |
