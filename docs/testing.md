# Testing

## Commands

Backend (from `backend/`, after `pip install -r requirements-dev.txt`):

```bash
.venv/bin/pytest                       # full suite
.venv/bin/pytest tests/test_tax_engine.py -q
.venv/bin/pytest --cov=app             # coverage (pytest-cov)
.venv/bin/ruff check app tests         # lint (rules in pyproject.toml)
```

At the time of writing the suite collects **258 tests, all passing** (about 8 s), from 224 test functions in 27
files (some are parametrized). `ruff check app tests` reports no findings.

Frontend (from `frontend/`):

```bash
npm run build && npm run lint
```

## Test environment

`tests/conftest.py`:

- Sets `ENVIRONMENT=test`, `DATABASE_URL=sqlite://`, an unreachable `REDIS_URL` (so the rate limiter uses
  in-process counters), `LOG_JSON=false` and an empty `ANTHROPIC_API_KEY` (AI disabled).
- `engine` fixture: a fresh in-memory SQLite database per test, created from the SQLAlchemy models.
- `db` fixture: a session with reference data seeded (`seed_reference`).
- `client`: FastAPI `TestClient` with the rate limiter reset; `auth_client`: registers the first (admin) user and
  sets the CSRF header.

No test makes network calls. NSE responses are served from real-format sample files in `tests/fixtures/nse/`
(bhavcopies, delivery file, index closes, F&O bhavcopy, lot sizes, constituents, RSS, holidays, flows, corporate
actions, event calendar, results filings, XBRL, shareholding) through a mocked HTTP transport.

### Synthetic data is test-only

`tests/synthetic.py` generates deterministic random-walk OHLCV series and `tests/helpers.py` inserts them as
stocks/index bars. Both are under `tests/` and are not imported by application code. The application never
generates or displays synthetic prices.

## What each test file covers

| File | Test functions | Covers |
|---|---|---|
| `test_ai_guardrails.py` | 3 | Invented numbers flagged, known numbers allowed, certainty language neutralised, nested objects |
| `test_analytics_levels.py` | 8 | Level ordering and methodology strings, ATR-banded (not fixed-%) stops, breakout anchoring, do-not-chase vs min R:R, wide-risk rejection, ₹0.05 tick rounding, position sizing and caps |
| `test_analytics_regime_eval.py` | 6 | Bullish vs bearish regime, no data → NEUTRAL with zero confidence, sector ranking and RS, evaluator look-ahead rejection, explained levels, insufficient history |
| `test_analytics_scoring.py` | 5 | Transparent bounded score, missing components lower confidence (except structural), bearish/stale penalties, overbought RSI, weight validation |
| `test_api_auth.py` | 7 | First-run registration then closed, weak password, CSRF on cookie mutations, login/logout/revocation, login rate limit, protected routes, admin-only routes |
| `test_api_portfolio_tax.py` | 4 | End-to-end transactions → FIFO → P&L → charges → tax, future trade date rejected, other users' portfolios hidden, tools endpoints |
| `test_backtest_engine.py` | 3 | Backtest runs and reports splits, future data cannot change past decisions, evaluate guard |
| `test_charges.py` | 14 | Hand-computed delivery/intraday/BSE charges, futures and options STT change on 2026-04-01, STT rounding, DP once per scrip per day, round trip, schedule selection by date and fallback, schedule shape, invalid input |
| `test_data_adjustments.py` | 3 | Split/bonus factor detection ignoring noise, back-adjustment of prices and volume, compounding |
| `test_data_client.py` | 24 | NSE client: 404 not cached, cache hits and TTL, request spacing, retries on 5xx/timeouts, cookie priming on 403, disable switches, UDiFF vs legacy URL selection, delivery merge and absence, bad zip not cached, index and constituents fallback, provisional flows, F&O and lots, partial results sources, corporate actions and RSS, broker credentials required, Upstox quote parsing (mocked), no real-time provider without credentials |
| `test_data_parsers.py` | 19 | Parsers for equity list, UDiFF and legacy bhavcopy, delivery, index closes, F&O, constituents, NSE and generic RSS/Atom, holidays, flows, corporate-action subjects and records, event calendar, shareholding, results-filing merge, XBRL (legacy and integrated, bank fallback, garbage input) |
| `test_fno_analytics.py` | 16 | OI buildup quadrants and wording, missing inputs, max pain, PCR and OI support/resistance, Black-Scholes and Black-76 IV round trips, IV edge cases, time to expiry, IV percentile, basis, near-month rollover, snapshot and score |
| `test_fundamental_results.py` | 8 | QoQ/YoY growth and margin change, loss-to-profit wording, classification bands, other-income flag, no consolidated/standalone mixing, QoQ fallback |
| `test_fundamental_scoring.py` | 9 | TTM needs four consecutive quarters, growth, P/E for negative EPS, consolidated preference, shareholding metrics, completeness and renormalisation, insufficient data, valuation vs sector/history, sector medians |
| `test_ingestion_service.py` | 2 | EOD + securities + corporate-action ingestion with stubbed providers (index membership, lot size, bars, split/bonus factor derived from a corporate action); corporate-action factor formula |
| `test_lots.py` | 11 | FIFO across lots, pro-rata charge allocation summing exactly, oversell, split, bonus (zero-cost lot, floor, ex-date buys), intraday same-day matching and carry-over, invalid segment |
| `test_market_calendar.py` | 4 | Weekends and holidays, phases and last EOD session, special sessions, session counting |
| `test_outcomes.py` | 7 | Entry then T2, stop before target on the same bar, gap through stop, trailing after T1, not triggered / invalidated, expiry, MFE/MAE |
| `test_paper_alerts.py` | 3 | Paper market order fills only on the next session's open, paper orders rejected on live portfolios, price alert fires once with cooldown |
| `test_portfolio_monitor.py` | 9 | Monitor P&L and distances, stop hit, partial profit at T1/T2, technical + regime exit, negative news exit, add-on-dip, missing levels, better-opportunity signal |
| `test_scanner.py` | 3 | No data → no recommendations, stale data disables recommendations, snapshot records versions and explanations |
| `test_settings.py` | 2 | Comma-separated, empty and JSON list settings; production refuses an empty/short `SECRET_KEY` |
| `test_tax_engine.py` | 26 | Hand-computed STCG/LTCG boundary, charges turning a flat trade into a loss, loss set-off and carry-forward, split-rate FY 2024-25, ₹1.25 lakh exemption, LTCL vs STCG, brought-forward losses, 15% surcharge cap, incomplete-profile flags, resident-only basic exemption, old-regime age flag, grandfathering (with/without FMV, after split), multi-year chaining, intraday with/without slab rate, speculative loss isolation, regime surcharge caps, tax allocation, net P&L, unrealized estimate |
| `test_tax_harvesting.py` | 2 | Harvest candidates, incomplete profile propagation |
| `test_tax_rules.py` | 7 | Rule look-up by transfer date, LTCG grandfather date and caps, missing rule, exemption by last day of year, basic exemption limits, version coercion from ORM-like rows, date helpers |
| `test_technical_indicators.py` | 11 | SMA/EMA, RSI range, ATR, MACD, Bollinger/Stochastic bounds, ADX/Supertrend, OBV and relative volume, volatility scale, causal rolling percentile, `compute_all` has no look-ahead, NaN → None |
| `test_technical_patterns.py` | 8 | Pivots need right-side confirmation, breakout with volume, breakdown, gap up, consolidation, confirmed double bottom, support/resistance split by price, output shape |

Areas without dedicated tests: ingestion jobs other than EOD/securities/corporate actions, Celery tasks and the
beat schedule, admin endpoints other than access control, AI client calls (only guardrails are tested), Kite quote
parsing, and the frontend (no frontend test runner is configured).

## Live smoke checks

Against a running stack with real data (not part of the automated suite):

```bash
# 1. liveness
curl -s localhost:8000/api/health
# expected: {"status":"ok", ... "checks":{"database":"ok","redis":"ok"}}

# 2. token for scripted calls
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"..."}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 3. data freshness and calendar
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/market/status
# check data.last_eod_date, data.is_current, data.sessions_behind, holidays_loaded

# 4. one EOD ingestion and a scan (from backend/)
.venv/bin/python -m app.cli job eod
.venv/bin/python -m app.cli job scan
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/opportunities | python3 -m json.tool | head -40

# 5. data-source health (admin)
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/admin/system-health | python3 -m json.tool | head -60
```

What to look for: the scan run's `status` (`ok`, `ok_no_candidates`, `data_stale`, `data_unavailable`) and
`notes`; `rejection_counts`; every recommendation carrying version fields, `data_as_of` and `missing_components`;
data sources GREEN or explainably YELLOW/DISABLED.
