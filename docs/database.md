# Database

PostgreSQL 16 via SQLAlchemy 2.x (sync) and Alembic. Models live in `backend/app/models/`; migrations in
`backend/alembic/versions/`. Tests run the same models on SQLite (`JSON` instead of `JSONB`).

## Conventions

- Timestamps are timezone-aware UTC (`DateTime(timezone=True)`); the API converts them to IST on output.
- Money and quantities in portfolio/tax tables use `Numeric(20, 4)`; tax rates use `Numeric(12, 8)`.
  Market-data prices use `Float`.
- JSON columns are `JSONB` on PostgreSQL.
- Market-data rows carry provenance: `source` and `retrieved_at` (and `source_url` where relevant).

## Migrations

| Revision | File | Content |
|---|---|---|
| `5c9a415c586e` | `20261005_5c9a415c586e_initial_schema.py` | All tables below |
| `0002_timescale` | `20261005_0002_timescale.py` | Optional TimescaleDB hypertables |
| `05b5d7bf5845` | `20261005_05b5d7bf5845_lot_buy_stt_and_grandfathering_fmv.py` | Adds `tax_lots.buy_stt` (default 0) and `transactions.fmv_31jan2018` |

`0002_timescale` checks `pg_available_extensions` for `timescaledb`. On plain PostgreSQL it is a no-op. When the
extension is available (`DB_IMAGE=timescale/timescaledb:latest-pg16` in `docker-compose.yml`) it runs
`CREATE EXTENSION IF NOT EXISTS timescaledb` and converts `ohlcv`, `index_ohlcv`, `option_chain` and `fno_data` into
hypertables on `date` with 180-day chunks. Its downgrade is a no-op. Because the migration runs only once, choose
the database image before the first `alembic upgrade head`.

`alembic check` against the current models reports no pending changes.

## Price storage: raw bars + adjustment factors

`ohlcv` stores daily bars exactly as published by the exchange (unadjusted). Split/bonus continuity is handled by
`price_adjustments`: a multiplicative factor applied to every bar strictly before `ex_date` (volumes are divided
by it).

- **Primary method (`method = "corporate_action"`)** — `app/services/ingestion.py::derive_adjustments_from_actions`,
  run automatically at the end of the `corporate_actions` job. It takes NSE corporate-action records of type
  `split` (factor = new face value ÷ old) and `bonus` a:b (factor = b ÷ (a + b)) whose ex-date has passed,
  de-duplicates repeated filings, multiplies the factors of actions sharing an ex-date (e.g. split and bonus on
  the same day), and checks the result against the observed close ratio across the ex-date. A factor that
  differs from the observed move by more than ±35% is not applied (logged for review); one without bars around the
  ex-date is applied and noted as not price-verified.
- **Fallback (`method = "exchange_prev_close"`)** — `derive_adjustments`, run after each EOD ingestion, compares
  the exchange-published previous close with the stored last close. The current NSE UDiFF bhavcopy does not adjust
  the previous close on ex-dates, so this finds nothing on current data; it is kept for sources that do.
- Adjusted series are computed on read (`app/services/prices.py::bars` / `bars_bulk`). When an `end` date is
  given, only adjustments with `ex_date <= end` are applied.

## Tables

### Reference and market data (`models/market.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `exchanges` | NSE / BSE | PK `code` | `name`, `timezone` |
| `sectors` | NSE industry → sector index used for strength | PK `id`; unique `name` | `index_name` |
| `stocks` | Security master | PK `id`; unique (`symbol`, `exchange_code`) | `isin`, `series`, `industry`, `sector_id`, `is_fno`, `fno_lot_size`, `index_memberships` (JSON), `is_active`, `is_suspended`, `surveillance_flags` (JSON), `meta` |
| `ohlcv` | Raw daily bars | PK (`stock_id`, `date`) | OHLC, `prev_close` (exchange-published), `volume`, `turnover` (INR), `trades`, `delivery_qty`, `delivery_pct`, `source`, `retrieved_at` |
| `index_ohlcv` | Daily index closes incl. India VIX | PK (`index_name`, `date`) | OHLC, `change_pct`, `turnover_cr`, `pe`, `pb`, `div_yield` |
| `prices` | Quote snapshots from a configured real-time provider | PK `id`; index `stock_id`, `ts` | `ltp`, `vwap`, `is_delayed`, `source` |
| `price_adjustments` | Split/bonus back-adjustment factors | PK `id`; unique (`stock_id`, `ex_date`) | `factor`, `method`, `note` |
| `corporate_actions` | Dividends, splits, bonus, rights, buybacks | PK `id`; unique (`stock_id`, `ex_date`, `subject`) | `action_type`, `ratio_from`, `ratio_to`, `amount`, `raw` |
| `market_holidays` | Exchange holidays and special sessions | PK (`exchange_code`, `date`, `segment`) | `is_special_session`, `session_open`, `session_close`, `source` (`nse` from the holiday master, `inferred` from a missing bhavcopy during backfill). Special-session rows (trading on a weekend/holiday) are not created by any job |
| `market_breadth` | Daily breadth | PK (`date`, `universe`) | advances/declines/unchanged, % above 20/50/200-DMA, new 52-week highs/lows |
| `institutional_flows` | FII/DII provisional cash flows | PK (`date`, `category`) | buy/sell/net (₹ crore) |
| `sector_strength` | Daily sector index ranking | PK (`date`, `index_name`) | `rank`, `score` (0–100), 1W/1M/3M returns, RS vs NIFTY, `trend`, `details` |
| `market_regimes` | Regime per session | PK `id`; index `session_date` | `regime`, `score`, `confidence`, `recommended_exposure_pct`, `max_positions`, `components`, `missing_inputs`, `model_version` |

### F&O (`models/fno.py`)

| Table | Purpose | Key | Notable columns |
|---|---|---|---|
| `fno_data` | Futures EOD rows | PK (`underlying`, `date`, `expiry`) | `instrument` (STF/IDF), OHLC, `settle`, `underlying_price`, `oi`, `change_oi`, `volume`, `lot_size` |
| `option_chain` | Option EOD rows (two nearest expiries kept) | PK (`underlying`, `date`, `expiry`, `strike`, `option_type`) | `close`, `settle`, `oi`, `change_oi`, `volume`, `iv` |
| `fno_snapshots` | Per-underlying daily analytics | PK (`underlying`, `date`) | basis, OI change, PCR (OI/volume), max pain, call resistance / put support, ATM IV, IV percentile, `buildup`, `interpretation`, `details` |

### Fundamentals (`models/fundamentals.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `financial_results` | One filed quarterly/annual result from NSE XBRL (absolute INR) | unique (`stock_id`, `period_end`, `consolidated`, `period_type`) | `broadcast_at` (point-in-time guard), revenue, other income, expenses, finance costs, depreciation, PBT, tax, PAT, EPS, `debt_equity`, `interest_coverage`, `classification`, `analysis`, `source_url` |
| `fundamentals` | Derived ratio snapshot as of a date | unique (`stock_id`, `as_of`) | `metrics`, `score`, `score_breakdown`, `completeness`. Defined but not written by any current job. |
| `shareholding` | Shareholding pattern | unique (`stock_id`, `period_end`) | promoter %, pledged %, FII %, DII %, MF %, public %, `broadcast_at` |
| `event_calendar` | Board meetings / results dates | unique (`stock_id`, `event_date`, `purpose`) | `purpose`, `description` |

### News (`models/news.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `news` | Announcements and secondary news | PK `id`; unique `dedupe_hash` | `source_tier` (`primary`/`reputable`/`other`), `event_type`, `sentiment` (−1..1), `impact`, `horizon`, `confidence`, `is_verified` (primary filings only), `classifier` |
| `news_sentiment` | AI analysis of a news item | PK `id`; FK `news_id` | `facts`, `interpretation`, `speculation` (kept separate), `summary`, `model`, `prompt_version`, `guardrail_flags` |

### Signals and recommendations (`models/signals.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `model_versions` | Registry of component versions and parameters | unique (`component`, `version`) | `params`, `is_active` |
| `technical_indicators` | Indicator snapshot per stock/date/version | PK (`stock_id`, `date`, `indicator_version`) | `values`, `patterns`. Defined but not written by any current job. |
| `recommendation_runs` | One execution of the Top-10 pipeline | PK `id`; index `session_date` | `status`, `universe_size`, `eligible_count`, `rejection_counts`, `regime_id`, all version fields, `weights`, `data_quality`, `notes`, `trigger` (`scheduled`/`manual`/`bootstrap`/`replay`) |
| `signals` | Score for every evaluated stock in a run | PK `id`; FK `run_id` | `score`, `setup`, `components`, `rejected`, `rejection_reasons` |
| `recommendations` | Immutable Top-10 snapshot | PK `id`; FK `run_id` | `rank`, `action`, `suitability`, `score`, `score_breakdown`, `confidence`, `setup`, `strategy`, `cmp`, entry/conservative zones, `no_chase_above`, `stop`, `trailing_stop_after_t1`, `target1..3`, `risk_pct`, `reward_pcts`, `rr`, holding range, `why`, `why_not`, `invalidation`, `methodology`, `data_sources`, `missing_components`, `market_regime`, `sector`, version fields, `ai_explanation` (currently not populated) |
| `recommendation_outcomes` | Simulated outcome of a recommendation | PK/FK `recommendation_id` | `status`, entry/exit date and price, `exit_reason`, T1/T2/T3/stop hit dates, `mfe_pct`, `mae_pct`, `return_pct`, `sessions_held` |

### Portfolio, journal and paper trading (`models/portfolio.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `portfolios` | User portfolios | PK `id`; FK `user_id` | `kind` (`live`/`paper`/`model`), `broker`, `charge_schedule_id`, `starting_cash` |
| `transactions` | Buy/sell orders entered by the user or paper engine | PK `id` | `side`, `quantity`, `price`, `trade_date`, `segment` (`delivery`/`intraday`), `exchange`, `charges_total`, `charges_breakdown`, `charges_source` (`estimated`/`user`), `source`, `fmv_31jan2018` (per share, buys only, for grandfathering) |
| `portfolio_positions` | User-managed stop/targets/thesis per holding | unique (`portfolio_id`, `stock_id`) | `stop`, `target1`, `target2`, `trailing_stop`, `recommendation_id`, `thesis` |
| `tax_lots` | FIFO lots, rebuilt from transactions | PK `id` | `acquired_date`, `quantity`, `remaining_quantity`, `cost_per_share`, `buy_charges` (incl. STT), `buy_stt`, `is_bonus`, `fmv_31jan2018` |
| `tax_calculations` | One FIFO match of a sell against a lot (model `RealizedGain`) | PK `id`; index `tax_year`, `sold_date` | sale/purchase value, buy/sell charges, `stt_total`, `capital_gain` (STT not deducted), `trading_pnl` (after all charges), `holding_days`, `term` (`STCG`/`LTCG`/`SPEC`), `flags` |
| `trades` | Trade journal (one round trip) | PK `id` | `kind` (`live`/`paper`/`system`/`user`), `origin`, `status`, entry/exit, `stop`, `target`, `market_regime`, `score_at_entry`, `recommendation_id`, `gross_pnl`, `charges`, `tax_estimate`, `net_pnl` |
| `paper_orders` | Simulated orders | PK `id` | `order_type` (`MARKET`/`LIMIT`), `limit_price`, `status`, `valid_till`, `fill_price`, `fill_note`, `transaction_id` |

`tax_lots` and `tax_calculations` for a holding are deleted and rebuilt from the full transaction history whenever
a transaction for that holding is added or deleted (`portfolio_service.rebuild_lots`).

### Tax and charges (`models/tax.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `tax_rules` | Dated capital-gains rules | unique (`rule_set_version`, `asset_type`, `term`, `effective_from`) | `effective_from`/`effective_to` (date of transfer), `holding_period_months`, `rate` (fraction; NULL = slab rate), `exemption_threshold`, `surcharge_cap`, `surcharge_slabs`, `cess_rate`, `grandfather_date`, `legal_reference`, `source_url`, `is_active` |
| `charges` | Dated brokerage + statutory charge schedules | PK `id` | `effective_from`/`effective_to`, `rates` (JSON, percent values), `source_url`, `notes`, `is_default` |
| `tax_profiles` | User facts the tax estimate depends on | PK/FK `user_id` | `residency`, `regime`, `other_taxable_income`, `slab_rate_for_business_income`, `carried_forward` (`STCL`/`LTCL`/`SPEC`), `broker_reported` |

See [tax-engine.md](tax-engine.md).

### Users, watchlists and alerts (`models/user.py`, `models/watch.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `users` | Accounts | unique `email` | `password_hash` (argon2id), `role` (`user`/`admin`), `is_active`, `last_login_at` |
| `user_sessions` | Server-side sessions so tokens can be revoked | PK `id` (random) | `expires_at`, `revoked_at`, `ip`, `user_agent` |
| `watchlists` | Named lists (six defaults created on first access) | unique (`user_id`, `name`) | `kind` |
| `watchlist_items` | Stocks in a list | unique (`watchlist_id`, `stock_id`) | `notes` |
| `alerts` | Alert definitions | PK `id` | `alert_type`, `params`, `channels`, `cooldown_minutes`, `last_triggered_at` |
| `alert_events` | Fired alerts | PK `id` | `title`, `message`, `data`, `delivery`, `read_at` |

### Backtests (`models/backtest.py`)

| Table | Purpose | Key | Notable columns |
|---|---|---|---|
| `backtests` | Backtest definition and results | PK `id` | `strategy`, `params`, `start_date`, `end_date`, `splits`, `status`, `metrics` (per split), `equity_curve`, `warnings`, `error`, `model_version` |
| `backtest_trades` | Simulated trades | PK `id`; FK `backtest_id` (cascade) | `split`, signal/entry/exit dates and prices, `quantity`, `gross_pnl`, `charges`, `net_pnl`, `exit_reason` |

### System (`models/system.py`)

| Table | Purpose | Key / unique | Notable columns |
|---|---|---|---|
| `data_sources` | Registry of data sources and their health | unique `key` | `kind`, `provider`, `is_enabled`, `requires_credentials`, `freshness_sla_minutes`, `last_success_at`, `last_data_as_of`, `last_error_at`, `last_error`, `terms_note`, `encrypted_secret` (unused; credentials come from environment variables) |
| `ingestion_runs` | One row per job execution | index `job`, `started_at` | `status` (`running`/`ok`/`partial`/`failed`/`skipped`), `rows`, `details`, `error` |
| `audit_logs` | Security-relevant actions | index `user_id`, `created_at` | `action`, `entity`, `entity_id`, `data` (sensitive keys redacted), `ip` |
| `app_settings` | Admin-configurable JSON settings | PK `key` | `value`, `version`, `updated_by` |

`app_settings` holds three kinds of keys:

- configuration keys from `app/analytics/config.py::DEFAULTS` (`scoring_weights`, `risk_limits`, `exclusions`,
  `regime`, `scanner`, `market_hours`, `ai`, `notifications`, `tax`), versioned on every update;
- `ai_cache:<SYMBOL>:<data date>` — cached AI analysis per stock and data date;
- `paper:<user_id>` — the user's paper-trading `follow_model` flag.

## Seed data

`python -m app.cli seed` (also run by the Docker backend on start, and as the first step of `bootstrap`) inserts
exchanges, sectors, the `data_sources` registry, `model_versions`, and — only if the tables are empty — the default
`tax_rules` and `charges`. Existing tax rules and charge schedules are never updated by seeding; a change to
`app/tax/defaults.py` must be applied to an existing database manually. No market data is seeded.
