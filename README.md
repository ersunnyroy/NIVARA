# NIVARA

A self-hosted research, trading-analysis and portfolio dashboard for Indian equities (NSE). It ranks daily swing
ideas from official exchange data, proposes entry, stop-loss and target levels with the method behind each one,
monitors your holdings for exit conditions, and estimates what you keep after brokerage, statutory charges and
income tax.

## What it is not

- **Not investment advice.** It is a personal research and decision-support tool. Every recommendation is a
  model output with its score, confidence, reasons against, and the data it was built from.
- **No guaranteed returns.** Track records and backtests are simulations on end-of-day data.
- **No automated order placement.** Nothing in the code sends orders to a broker. Paper trading is simulated.
- **Regulatory note.** Offering personalised recommendations to others may require SEBI registration as an
  Investment Adviser or Research Analyst. The tool is intended for your own use.
- **Tax figures are estimates** labelled `ESTIMATED`; verify with a qualified tax professional before filing.

## Features by question

| Question | What NIVARA provides |
|---|---|
| **What to buy?** | Daily Top-10 from the NIFTY 500 universe after liquidity and data-quality filters, scored 0–100 on technical, momentum, volume, relative strength, fundamentals, sector, news, F&O and risk/reward components with an explained breakdown; market regime model; sector strength; on-demand analysis of any stock; watchlists and alerts; optional AI explanations whose numbers are checked against the computed data |
| **At what price?** | Preferred and conservative entry zones, do-not-chase level, structural or ATR-based stop, three targets, reward:risk, expected holding period, invalidation condition, and a position-size calculator — each level with its methodology string |
| **When to sell?** | Position monitor per holding (`EXIT`, `PARTIAL PROFIT`, `TRAIL STOP`, `ADD ONLY ON DIP`, `WAIT`, `HOLD`) with reasons, a sell/exit list, suggested trailing stops, alerts for stop/target/breakdown/news/regime change |
| **How much will I actually make?** | Itemised brokerage, STT, exchange, SEBI, stamp duty, GST and DP charges from dated schedules; FIFO tax lots with split/bonus handling; STCG/LTCG/intraday classification, set-off, LTCG exemption, surcharge and cess from dated tax rules; gross → charges → pre-tax → estimated tax → net per holding and per tax year; tax-loss harvesting view |

**Simple view** (`/simple`): the same outputs in plain language for everyday investors — market mood with a
suggested maximum investment level; short-term ideas ("buy between ₹A and ₹B, sell if below ₹S, possible gain
+X% / possible loss −Y%, usually held N weeks") with how similar past ideas actually turned out; long-term ideas
from the strongest businesses in the NIFTY 100 with good signs, things to watch, the stock's historical 1-year
range and biggest fall; and an intraday tab that explains why no same-day ideas are given without live prices.
It adds no new predictions — every number comes from the engines above.

Supporting features: recommendation track record (simulated outcomes, live vs historical replay), backtesting with
train/validation/test splits, paper trading with an optional auto-following model portfolio, trade journal and
performance statistics, F&O analytics (OI buildup, PCR, max pain, IV), news from NSE announcements with
rule-based classification, admin system-health and job controls.

## Screenshots

No screenshots are included in the repository yet.

## Architecture in brief

```
NSE archives / website API ─┐
Upstox or Kite (optional) ──┼─► ingestion jobs (Celery, IST schedule) ─► PostgreSQL (+ optional TimescaleDB)
RSS feeds (optional) ───────┘                                                  │
                                                                               ▼
           quantitative engine → risk engine → tax engine → AI explanation layer (optional)
                                                                               │
                                       FastAPI /api  ◄──── Next.js frontend (proxies /api)
```

Details: [docs/architecture.md](docs/architecture.md).

## Quick start (local development)

Prerequisites: Python 3.12, Node.js 22 (the frontend image uses `node:22-alpine`), Docker with Compose (for
Postgres and Redis), internet access to `nsearchives.nseindia.com` and `www.nseindia.com`.

```bash
# 1. configuration
cp .env.example .env
#    optional for local development: an empty SECRET_KEY falls back to a development default.
#    Required (>= 32 random characters) when ENVIRONMENT=production:
#    python -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. database and cache (host ports 5442 and 6381)
docker compose up -d db redis

# 3. backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli bootstrap          # seed (+ BOOTSTRAP_ADMIN_* admin) + ~420 days of NSE EOD history + analytics + first scan
.venv/bin/uvicorn app.main:app --reload        # API docs: http://localhost:8000/api/docs

# 4. frontend (new terminal)
cd frontend
npm install
npm run dev                                    # http://localhost:3000
```

Open http://localhost:3000. The first account you register becomes the **admin**; registration then closes and
further users are created by the admin. If `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` are set, `bootstrap`
creates that admin instead.

The bootstrap downloads a little over a year of daily files from NSE at about one request per second, so it takes
a while on first run; files for past sessions are cached on disk afterwards. For scheduled daily updates, run a
Celery worker and beat (see [docs/deployment.md](docs/deployment.md)). Full Docker and production setup are also
described there.

## Environment variables

From `.env.example`. "Required" means the application does not work correctly without it in that context.

| Variable | Required | Default / example | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | no | `development` | `production` enables the `SECRET_KEY` start-up check and is set by the production compose override |
| `SECRET_KEY` | **production** (≥ 32 chars) | empty → development default | Signs session tokens and CSRF values. Production refuses to start if it is shorter than 32 characters or the development default |
| `ENCRYPTION_KEY` | no (reserved) | empty | Fernet key for secrets stored in the database; reserved, not used by any current code path |
| `COOKIE_SECURE` | production | `false` | `true` behind HTTPS (set by the production compose override) |
| `ALLOWED_ORIGINS` | no | `http://localhost:3000` | CORS origins, comma-separated or JSON list |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Docker | `nivara` | Database container credentials |
| `DB_PORT` / `REDIS_PORT` | no | `5442` / `6381` | Host ports for the dev containers |
| `DB_IMAGE` | no | `postgres:16-alpine` | Set `timescale/timescaledb:latest-pg16` to enable hypertables |
| `DATABASE_URL` | yes | `postgresql+psycopg://nivara:nivara@localhost:5442/nivara` | SQLAlchemy URL |
| `REDIS_URL` | yes (Celery) | `redis://localhost:6381/0` | Celery broker/results and rate-limit counters |
| `NSE_ENABLED` | no | `true` | Master switch for NSE fetching |
| `NSE_WEBSITE_API_ENABLED` | no | `true` | www.nseindia.com JSON endpoints (flows, corporate actions, results, shareholding, holidays) |
| `NSE_MIN_REQUEST_INTERVAL_SEC` | no | `1.0` | Minimum spacing between NSE requests |
| `DATA_CACHE_DIR` | no | `./var/cache` | On-disk NSE cache |
| `UPSTOX_ACCESS_TOKEN` | optional | empty | Real-time quotes via Upstox (daily token) |
| `KITE_API_KEY` / `KITE_ACCESS_TOKEN` | optional | empty | Real-time quotes via Zerodha Kite (daily token) |
| `NEWS_RSS_FEEDS` | optional | empty | Extra RSS feeds, comma-separated or JSON list |
| `ANTHROPIC_API_KEY` | optional | empty | Enables AI explanations |
| `AI_MODEL` / `AI_EFFORT` / `AI_ENABLED` | optional | `claude-opus-5-5` / `medium` / `true` | AI settings |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | optional | port `587` | Email alerts |
| `ALERT_WEBHOOK_URL` | optional | empty | Webhook alerts |
| `SENTRY_DSN` | optional | empty | Error tracking (`sentry-sdk` is in `requirements.txt`) |
| `LOG_LEVEL` / `LOG_JSON` | no | `INFO` / `true` | Logging |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | optional | empty | Admin created by `python -m app.cli seed` or `bootstrap` |

## External data sources and credentials

| Source | Credentials | Provides |
|---|---|---|
| NSE archives and website endpoints | none | EOD bhavcopy and delivery, index closes incl. India VIX, F&O bhavcopy, security master, index constituents, results XBRL, shareholding, corporate actions, board meetings, FII/DII provisional flows, holidays, announcements RSS |
| Upstox API v2 or Zerodha Kite Connect v3 | `UPSTOX_ACCESS_TOKEN`, or `KITE_API_KEY` + `KITE_ACCESS_TOKEN` | Real-time quotes during market hours (optional) |
| Anthropic API | `ANTHROPIC_API_KEY` | AI explanations of computed analysis (optional) |
| RSS feeds | none | Secondary news, labelled "not independently verified" (optional) |

NSE endpoints are public website and archive resources, not a licensed feed; the app fetches them slowly with
caching for personal research use. Review NSE's terms before any redistribution or commercial use. See
[docs/data-sources.md](docs/data-sources.md).

## Commands

```bash
# backend tests and lint (from backend/)
.venv/bin/pytest
.venv/bin/ruff check app tests

# frontend build and lint (from frontend/)
npm run build && npm run lint

# named jobs (from backend/)
.venv/bin/python -m app.cli job eod                 # latest EOD session
.venv/bin/python -m app.cli job scan                # run the Top-10 scanner
.venv/bin/python -m app.cli job fundamentals universe=nifty500
.venv/bin/python -m app.cli create-admin you@example.com
```

## Project layout

```
NIVARA/
├── .env.example
├── docker-compose.yml              # db, redis; backend/worker/beat/frontend under profile "app"
├── docker-compose.prod.yml         # production overrides + nginx
├── deploy/nginx/                   # reverse proxy config
├── docs/                           # this documentation
├── backend/
│   ├── Dockerfile
│   ├── alembic/                    # migrations (initial schema, optional TimescaleDB)
│   ├── app/
│   │   ├── main.py                 # FastAPI app, middleware
│   │   ├── cli.py                  # seed / create-admin / job / bootstrap
│   │   ├── api/                    # routers, auth dependencies
│   │   ├── config/                 # settings from environment
│   │   ├── core/                   # db, security, rate limiting, audit, logging, time helpers
│   │   ├── data/                   # NSE client/parsers/providers, Upstox/Kite adapters, RSS, adjustments
│   │   ├── models/                 # SQLAlchemy models
│   │   ├── technical/              # indicators, price-action patterns
│   │   ├── analytics/              # scoring, levels, regime, sector strength, evaluator, config
│   │   ├── fundamental/            # results analysis, fundamental score
│   │   ├── fno/                    # F&O analytics
│   │   ├── news/                   # rule-based news classification
│   │   ├── recommendations/        # outcome simulation
│   │   ├── portfolio/              # FIFO lots, position monitor
│   │   ├── tax/                    # charges, tax rules, tax engine, harvesting, defaults
│   │   ├── paper/                  # paper trading
│   │   ├── backtesting/            # backtester and service
│   │   ├── alerts/                 # alert rules and notifiers
│   │   ├── ai/                     # Claude client, analysis, guardrails
│   │   ├── market_calendar/        # NSE sessions and holidays
│   │   ├── services/               # ingestion, scanner, portfolio, market, jobs
│   │   └── workers/                # Celery app, tasks, pipelines
│   └── tests/                      # pytest suite, NSE fixtures, synthetic test data
└── frontend/                       # Next.js app (src/app pages, src/components, src/lib)
```

Frontend pages currently present under `frontend/src/app`: login, dashboard, market, opportunities, stocks and
stock detail, news, F&O, portfolio and portfolio detail, paper trading, trade journal, watchlists, alerts, Tax
Center, recommendation track record, performance, backtesting, settings. The frontend is under active
development.

## Known limitations

- **EOD only without a broker API.** Prices are official end-of-day closes, labelled with their date and source.
  Intraday charts and intraday VWAP are not available; live quotes need an Upstox or Kite token. Both broker
  adapters are tested only with mocked responses; validate them with real credentials before relying on them.
- **Fundamentals are limited to filed quarterly P&L items** and shareholding. Balance-sheet and cash-flow metrics
  (ROE, ROCE, P/B, FCF, EV/EBITDA) and analyst estimates are reported as unavailable. Sector-relative P/E is not
  computed (no sector medians are supplied to the fundamental score).
- **AI is optional.** Without an Anthropic key, deterministic explanations are shown. AI explanations are generated
  only on explicit request (`POST`), never by viewing a page.
- **Backfill takes time** and is deliberately rate-limited; NSE website endpoints can change format or block
  automated access, in which case data shows as unavailable or stale rather than being filled in.
- **History depth is limited by the sources.** The FII/DII endpoint returns only the latest day, so the regime's
  flows input is missing for past sessions until history accumulates; the NSE holiday master covers the current
  year only, so earlier holidays are inferred from missing bhavcopies; F&O history starts from 2024-07-08 (UDiFF
  format) and otherwise builds up from daily runs.
- **Split/bonus adjustment depends on corporate-action records.** The NSE UDiFF bhavcopy does not adjust the
  previous close on ex-dates, so factors come from NSE corporate actions and are applied only when they agree with
  the observed price move (see [docs/data-sources.md](docs/data-sources.md#splitbonus-adjustment)).
- **TimescaleDB is optional**; plain PostgreSQL works. Choose before the first migration.
- **No global market context provider**; the regime model lists that input as missing.
- **Surveillance flags (ASM/GSM) and suspensions** are not ingested, so those exclusions are inactive.
- **Special trading sessions** on weekends/holidays (e.g. Budget day) are discovered automatically during backfill: when a session's published previous closes disagree with our last stored closes for most stocks, the closed days in between are probed for a bhavcopy and any found are ingested and recorded as `market_holidays` rows with `is_special_session = true` (source `inferred`). The
  forward-looking calendar still relies on NSE's holiday master for announced special sessions.
- **Tax estimates** do not model rebate u/s 87A, marginal relief, rounding, DTAA or loss carry-forward expiry.
  Grandfathering needs the 31-Jan-2018 FMV, entered on the buy transaction.
- **Track record and backtests are simulations** on daily bars with conservative fill rules; backtests exclude
  fundamentals, news and F&O components.

## Documentation

- [Architecture](docs/architecture.md) — layers, Top-10 pipeline, scoring, levels, regime, versioning, data-failure handling
- [Database](docs/database.md) — every table, keys, raw bars and adjustments, migrations
- [API](docs/api.md) — every endpoint with auth and key fields
- [Data sources](docs/data-sources.md) — NSE endpoints, cadence, caching, quality labels, credentials, gaps
- [Tax engine](docs/tax-engine.md) — dated rules, charges, FIFO, set-off, worked example
- [Backtesting](docs/backtesting.md) — look-ahead prevention, fills, splits, metrics, BACKTEST vs PAPER vs LIVE
- [Deployment](docs/deployment.md) — local, Docker, production, bootstrap, backups, monitoring, upgrades
- [Security](docs/security.md) — auth, sessions, CSRF, rate limits, secrets, audit, known gaps
- [Testing](docs/testing.md) — commands, coverage per file, smoke checks
- [Frontend](frontend/README.md) — stack, scripts, `/api` rewrite, structure, client-side auth and CSRF
