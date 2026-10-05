# API reference

FastAPI app in `backend/app/main.py`; routers in `backend/app/api/routes/`. All application routes are under
`/api`. Interactive OpenAPI docs: `GET /api/docs`, schema: `GET /api/openapi.json`.

## Conventions

- **Auth** column: `none` (public), `user` (any signed-in active user), `admin` (role `admin`).
- **Session**: `POST /api/auth/login` sets an httpOnly `nivara_session` cookie (signed JWT bound to a revocable
  server-side session) and a readable `nivara_csrf` cookie. It also returns `access_token` and `csrf_token`.
- **CSRF**: cookie-authenticated `POST`/`PUT`/`PATCH`/`DELETE` requests must send header `x-csrf-token` equal to the
  `nivara_csrf` cookie. Requests using `Authorization: Bearer <access_token>` are exempt.
- **Rate limits**: 240 requests/minute per client IP for `/api/*` except `/api/health` (HTTP 429 with
  `Retry-After: 60`); login is additionally limited to 10/minute per IP and per email. The client IP is the
  connection's peer address (behind the bundled nginx, uvicorn derives it from `X-Forwarded-For`, which nginx sets
  to the real remote address).
- **Responses**: JSON; dates ISO 8601; datetimes converted to IST; Decimals serialised as numbers. Every response
  carries `x-request-id`; API responses carry `cache-control: no-store`.
- **Errors**: `{"detail": "..."}` with 400/401/403/404/422/429; unhandled errors return 500 with `request_id`.
- Ownership: portfolio, transaction, trade, watchlist, alert and backtest routes return 404 for objects owned by
  another user.
- Labels: tax and charge figures are returned with `label: "ESTIMATED"` and a disclaimer.

## Health and meta

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | none | `status` `ok`/`degraded` with database and Redis checks |
| GET | `/api/meta/disclaimers` | none | General, tax, backtest and regulatory disclaimer texts |

## Auth (`routes/auth.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/auth/status` | none | `registration_open` is true only while no user exists |
| POST | `/api/auth/register` | none | First-run only; creates the first user as `admin`. Body: `email`, `password`, `full_name?`. Returns 403 once any user exists |
| POST | `/api/auth/login` | none | Body: `email`, `password`. Sets cookies; returns `user`, `csrf_token`, `access_token`, `expires_at` |
| POST | `/api/auth/logout` | user | Revokes the current session and clears cookies |
| GET | `/api/auth/me` | user | Current user (`id`, `email`, `full_name`, `role`) |
| POST | `/api/auth/password` | user | Body: `current_password`, `new_password`. Revokes the user's other sessions |

Password policy: at least 10 characters, mixed case, at least one digit.

## Market (`routes/market.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/market/status` | user | Calendar phase (pre-market/open/post-close/holiday/weekend), last completed EOD session, target session, `data.last_eod_date`, `is_current`, `sessions_behind`, `realtime_quotes` |
| GET | `/api/market/overview` | user | Latest regime, headline indices, breadth, last 10 FII/DII rows, sector ranking, top gainers/losers/most active (EQ, turnover > ₹5 cr). `status: data_unavailable` when no index data |
| GET | `/api/market/regime/history` | user | Query `days` (default 120) |

## Opportunities and recommendations (`routes/opportunities.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/opportunities` | user | Latest scan run and its ranked recommendations. Query `date` (session date). `status: no_runs` before the first scan |
| POST | `/api/opportunities/run` | admin | Runs the scanner now (synchronously) with trigger `manual` |
| GET | `/api/opportunities/runs` | user | Recent scan runs. Query `limit` (30) |
| GET | `/api/recommendations` | user | Recommendation history. Query `symbol`, `from`, `to`, `limit` (≤ 1000) |
| GET | `/api/recommendations/track-record` | user | Aggregated simulated outcomes. Query `origin` = `live` or `historical_replay` |
| GET | `/api/recommendations/{rec_id}` | user | One recommendation with its run and outcome |

## Stocks (`routes/stocks.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/stocks` | user | Search active NSE stocks by symbol/name. Query `q`, `limit` (≤ 100) |
| GET | `/api/stocks/{symbol}` | user | Stock detail, current price with provenance, latest signal |
| GET | `/api/stocks/{symbol}/bars` | user | Split/bonus-adjusted daily bars with EMA/SMA/Bollinger/Supertrend/rolling-VWAP overlays and RSI/MACD panes. Query `range` = `1D`,`5D`,`1M`,`3M`,`6M`,`1Y`,`3Y`,`5Y`. `1D`/`5D` return daily bars with a note (no intraday data) |
| GET | `/api/stocks/{symbol}/technical` | user | On-demand evaluation with the scanner's evaluator: indicators, price action, levels, score, confidence, action |
| GET | `/api/stocks/{symbol}/fundamentals` | user | Point-in-time fundamental view, metrics, missing items, last 12 filed results |
| GET | `/api/stocks/{symbol}/news` | user | News for the stock with verification label and latest AI analysis. Query `limit` |
| GET | `/api/stocks/{symbol}/fno` | user | Latest F&O snapshot and 60-day history (or `is_fno: false`) |
| GET | `/api/stocks/{symbol}/corporate-actions` | user | Up to 50 corporate actions |
| GET | `/api/stocks/{symbol}/shareholding` | user | Up to 12 shareholding periods |
| GET | `/api/stocks/{symbol}/signals` | user | Past recommendations and score history |
| GET | `/api/stocks/{symbol}/analysis` | user | Cached AI explanation for the stock's data date, else the deterministic explanation (status `not_generated` when AI is configured, `ai_not_configured` otherwise). Never calls the model |
| POST | `/api/stocks/{symbol}/analysis` | user | Generate or regenerate the AI explanation (calls the model when configured) and cache it |

## Tools (`routes/tools.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| POST | `/api/tools/position-size` | user | Body: `capital`, `risk_pct`, `entry`, `stop`, `targets[]`, `max_position_pct?`. Returns quantity, max loss, capital required, potential profits |
| POST | `/api/tools/charges` | user | Body: `segment` (`delivery`/`intraday`/`futures`/`options`), `side`, `quantity`, `price`, `trade_date`, `exchange` (`NSE`/`BSE`). Returns itemised estimated charges |

## Portfolio (`routes/portfolio.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/portfolios` | user | The user's portfolios |
| POST | `/api/portfolios` | user | Body: `name`, `kind` (`live`/`paper`), `broker?`, `starting_cash?`, `notes?` |
| DELETE | `/api/portfolios/{pid}` | user | Delete a portfolio and its transactions/lots |
| GET | `/api/portfolios/{pid}` | user | Holdings: FIFO lots, price with provenance, gross P&L, charges paid, estimated exit charges, estimated tax if only that position were sold, net P&L, monitor action, sector allocation warnings, realized summary. The summary's `estimated_tax_unrealized` is computed once over all open lots (with its own `status` and incomplete reasons) |
| GET | `/api/portfolios/{pid}/transactions` | user | Transactions, newest first |
| POST | `/api/portfolios/{pid}/transactions` | user | Body: `symbol`, `side`, `quantity`, `price`, `trade_date` (not in the future), `trade_time?`, `segment` (`delivery`/`intraday`), `exchange`, `broker?`, `charges_total?` (else estimated), `notes?`, `fmv_31jan2018?` (per-share FMV on 31-Jan-2018 for grandfathering; stored on buys only). Rebuilds lots; 422 on oversell |
| DELETE | `/api/portfolios/{pid}/transactions/{tid}` | user | Delete and rebuild lots (422 if the rebuild becomes invalid) |
| PUT | `/api/portfolios/{pid}/positions/{symbol}` | user | Body: `stop?`, `target1?`, `target2?`, `trailing_stop?`, `thesis?` — levels used by the monitor |
| GET | `/api/portfolios/{pid}/realized` | user | Realized FIFO matches and tax summary. Query `tax_year` (e.g. `2026-27`) |
| GET | `/api/portfolio/dashboard` | user | Sum of the per-portfolio summaries across live portfolios and the action list sorted by severity |
| GET | `/api/portfolio/exits` | user | Holdings (live and paper) with any exit signal, with reasons and suggested trailing stop |

## Trade journal and performance (`routes/journal.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/trades` | user | Query `kind`, `status` |
| POST | `/api/trades` | user | Body: `portfolio_id`, `symbol`, `kind`, `entry_date`, `entry_price`, `quantity`, `stop?`, `target?`, `exit_date?`, `exit_price?`, reasons, `market_regime?`, `score_at_entry?`, `recommendation_id?`, `charges?`, `notes?`, `attachment_url?`. Closed trades get estimated charges, tax and net P&L |
| PUT | `/api/trades/{tid}` | user | Same body as create |
| DELETE | `/api/trades/{tid}` | user | Delete a journal entry |
| GET | `/api/performance` | user | Performance statistics by trade kind. Query `kind` |

## Tax (`routes/tax.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/tax/summary` | user | Tax-year estimate over live portfolios: buckets, set-off log, exemption, surcharge, cess, carry-forward, completeness, charges, by-symbol totals. Query `tax_year` |
| GET | `/api/tax/harvesting` | user | Informational tax-loss harvesting view for open lots (not a sell recommendation) |
| GET | `/api/tax/profile` | user | The user's tax profile |
| PUT | `/api/tax/profile` | user | Body: `residency` (`resident`/`nri`), `regime` (`new`/`old`), `other_taxable_income`, `slab_rate_for_business_income` (0–1), `carried_forward` (`{"STCL": .., "LTCL": .., "SPEC": ..}`), `broker_reported` |
| GET | `/api/tax/rules` | user | All stored tax rules and charge schedules |

## Watchlists, alerts and news (`routes/watch.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/watchlists` | user | Lists (six defaults are created on first call) |
| POST | `/api/watchlists` | user | Body: `name`, `kind` |
| DELETE | `/api/watchlists/{wid}` | user | Delete a list |
| GET | `/api/watchlists/{wid}` | user | Items with price, latest score/setup, latest recommendation, `in_entry_zone` |
| POST | `/api/watchlists/{wid}/items` | user | Body: `symbol`, `notes?` |
| DELETE | `/api/watchlists/{wid}/items/{symbol}` | user | Remove a stock |
| GET | `/api/alerts` | user | Alert definitions and the list of supported `types` |
| POST | `/api/alerts` | user | Body: `symbol?` (required except `regime_change`), `alert_type`, `params`, `channels` (`in_app`/`email`/`webhook`), `cooldown_minutes` (5 – 43200) |
| DELETE | `/api/alerts/{aid}` | user | Delete an alert |
| GET | `/api/alerts/events` | user | Fired alerts (≤ 200). Query `unread` |
| POST | `/api/alerts/events/{eid}/read` | user | Mark read |
| GET | `/api/news` | user | Query `symbol`, `event_type`, `tier`, `limit` (≤ 200) |
| POST | `/api/news/{nid}/analyze` | user | AI FACT / INTERPRETATION / SPECULATION analysis of one item; returns `ai_error` when AI is unavailable |

Alert types: `entry_zone`, `stop`, `target`, `breakout`, `breakdown`, `unusual_volume`, `major_news`, `results`,
`price_move`, `score_change`, `regime_change`, `price_above`, `price_below`.

## F&O and paper trading (`routes/fno_paper.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/fno/overview` | user | All F&O snapshots for a date with buildup counts. Query `date`, `buildup` |
| GET | `/api/paper` | user | Paper and model portfolios, cash, orders, `follow_model`, model-vs-user comparison |
| POST | `/api/paper/orders` | user | Body: `symbol`, `side`, `quantity`, `order_type` (`MARKET`/`LIMIT`), `limit_price?`, `stop?`, `target?`, `valid_sessions` (1–20). Filled against the next session's EOD bar |
| DELETE | `/api/paper/orders/{oid}` | user | Cancel an open order |
| PUT | `/api/paper/settings` | user | Body: `follow_model` (auto-place model orders for new BUY recommendations) |

## Backtests (`routes/backtests.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/backtests` | user | The user's backtests (without equity curves), available `strategies`, banner text |
| POST | `/api/backtests` | user | Body: `name`, `strategy` (`combined`/`ranking`/`breakout`/`momentum`/`mean_reversion`), `start_date`, `end_date`, `params`, `universe`. Queued on Celery when a worker answers a ping, otherwise run as an in-process background task (`queued_via`) |
| GET | `/api/backtests/{bid}` | user | Metrics per split, equity curve, trades, warnings |
| DELETE | `/api/backtests/{bid}` | user | Delete |

Accepted `params` keys: `capital`, `risk_pct`, `max_positions`, `top_n`, `slippage_bps`, `universe_size`,
`min_score`. See [backtesting.md](backtesting.md).

## Settings and administration (`routes/admin.py`)

| Method | Path | Auth | Purpose / key fields |
|---|---|---|---|
| GET | `/api/settings` | user | Effective config, defaults, `editable` (admin), versions |
| PUT | `/api/settings/{key}` | admin | Body: JSON object for one of `scoring_weights`, `risk_limits`, `exclusions`, `regime`, `scanner`, `market_hours`, `ai`, `notifications`, `tax`. Weights are validated and normalised to 100. Increments the setting version; audited |
| GET | `/api/admin/system-health` | admin | Per-source status (`GREEN`/`YELLOW`/`RED`/`DISABLED`) with SLA, Celery worker ping, DB size and row counts, calendar, recent ingestion runs |
| GET | `/api/admin/data-sources` | admin | Data-source registry with required env vars and `configured` |
| PUT | `/api/admin/data-sources/{key}` | admin | Body: `is_enabled?`, `freshness_sla_minutes?` |
| GET | `/api/admin/users` | admin | Users (without password hashes) |
| POST | `/api/admin/users` | admin | Body: `email`, `password`, `full_name?`, `role` (`user`/`admin`) |
| POST | `/api/admin/users/{uid}/deactivate` | admin | Deactivate (not yourself) |
| POST | `/api/admin/jobs/{job}` | admin | Run a named job; optional JSON body of params. Sent to Celery if a worker answers, else run in-process |
| GET | `/api/admin/jobs` | admin | Job names, last 7 days of runs, counts by status |
| GET | `/api/admin/audit-logs` | admin | Query `limit` (≤ 1000) |
| GET | `/api/admin/charges` | admin | Stored charge schedules |

Job names (`app/services/jobs_runner.py::JOBS`): `seed`, `securities`, `holidays`, `eod`, `backfill`, `fno`,
`fno_snapshots`, `flows`, `news`, `corporate_actions`, `event_calendar`, `fundamentals`, `breadth`, `regime`,
`scan`, `outcomes`, `alerts`, `paper`, `pre_market`, `post_market`, `replay`. Common params: `date` (session),
`start`/`end`/`days` (backfill), `symbols` or `universe` (fundamentals), `start`/`end`/`every` (replay).

## Non-`/api` routes

FastAPI also registers `/docs/oauth2-redirect` and `/redoc` at the root path. The production nginx config only
routes `/api/` to the backend, so these are not reachable through it.
