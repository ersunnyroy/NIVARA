# Architecture

NIVARA is a single-user-group research tool: a FastAPI backend (`backend/app`), Celery workers for scheduled
pipelines, PostgreSQL (optionally TimescaleDB) for storage, Redis for the Celery broker and rate-limit counters,
and a Next.js frontend (`frontend/`). It never places orders with a broker.

## Components

| Component | Code | Role |
|---|---|---|
| API | `backend/app/main.py`, `app/api/` | REST API under `/api`, auth, rate limiting, request IDs, security headers |
| Workers | `app/workers/celery_app.py`, `tasks.py`, `pipeline.py` | Celery beat schedule (IST) and the pre-market / intraday / post-market pipelines |
| Jobs | `app/services/jobs_runner.py`, `app/cli.py` | Named jobs runnable from CLI, admin API or Celery |
| Data providers | `app/data/` | NSE archives/website clients and parsers, optional Upstox/Kite quote adapters, RSS |
| Quantitative engine | `app/technical/`, `app/analytics/`, `app/fundamental/`, `app/fno/`, `app/news/` | Indicators, patterns, scoring, levels, regime, sector strength, fundamentals, F&O, news classification |
| Risk engine | `app/analytics/levels.py`, `app/portfolio/monitor.py`, scanner filters | Stops, reward:risk gates, position sizing, exit rules |
| Tax engine | `app/tax/`, `app/portfolio/lots.py` | Charges, FIFO lots, capital-gains classification, tax-year estimate |
| AI explanation layer | `app/ai/` | Optional Claude explanations of already-computed data, with guardrails |
| Paper trading | `app/paper/engine.py` | Simulated orders filled on EOD bars |
| Backtesting | `app/backtesting/` | Event-driven daily backtester sharing the live evaluator |
| Frontend | `frontend/src` | Next.js app; proxies `/api/*` to the backend |

## Layering

The design rule is that each layer may only consume the output of the layer before it, and never override it.

```
 NSE / broker / RSS data ──► stored with provenance (source, retrieved_at, data timestamp)
            │
            ▼
 1. Quantitative engine   indicators, patterns, component scores, regime, sector/RS, fundamentals, F&O, news
            │
            ▼
 2. Risk engine           entry/stop/targets, reward:risk and risk-% rejection, regime gating, position size,
            │             suitability tier, position-monitor exit rules
            ▼
 3. Tax engine            charges per order, FIFO lots, STCG/LTCG/SPEC classification, set-off, exemption,
            │             surcharge/cess, gross → charges → pre-tax → estimated tax → net
            ▼
 4. AI explanation layer  explains the fact sheet produced above; cannot change numbers (guardrails flag
                          any number not present in the input and strip certainty language)
```

- `app/ai/analysis.py` builds a fact sheet from the deterministic analysis and instructs the model to use only
  those numbers. `app/ai/guardrails.py` flags every number in the output that does not match a fact-sheet number
  (within rounding, ₹ crore/lakh and %/fraction conversions) and replaces certainty phrases ("guaranteed",
  "risk-free", "will definitely", ...).
- Without `ANTHROPIC_API_KEY` (or with `AI_ENABLED=false`) a deterministic template explanation is returned with
  status `ai_not_configured`. On API failure the template is returned with status `error`.
- The model is called only on explicit request (`POST /api/stocks/{symbol}/analysis`, `POST /api/news/{id}/analyze`).
  `GET /api/stocks/{symbol}/analysis` returns the cached explanation or the deterministic one with status
  `not_generated`.
- `app/portfolio/monitor.py` states that the AI layer "may explain these, but never overrides them".

## Daily Top-10 pipeline

Implemented in `app/services/scanner.py::run_scan`, normally triggered by the `post_market` pipeline.

1. **Load effective config** — defaults in `app/analytics/config.py` deep-merged with admin overrides from
   `app_settings`; weights are validated and normalised to sum to 100.
2. **Freshness check** — latest `ohlcv.date` is compared with the calendar's last completed EOD session.
   - No data: run stored with status `data_unavailable`, note `DATA UNAVAILABLE`, no recommendations.
   - Behind: status `data_stale`, note `DATA STALE — recommendation disabled`, no recommendations
     (except for `replay`/`backfill` triggers).
   - If the holiday calendar is not loaded, freshness is approximated (within 4 days) and a note says so.
3. **Market regime** — only a regime row computed for the exact `as_of` session is used; otherwise it is computed
   now. If index history is missing the regime is treated as `NEUTRAL` and a note is added.
4. **Universe** — active NSE stocks in the configured index (`exclusions.universe_index`, default `nifty500`),
   excluding disallowed series (only `EQ` by default), suspended stocks and stocks with surveillance flags.
5. **Liquidity / data-quality exclusions** (counted per reason in `rejection_counts`):
   no bar for the session, fewer than 220 sessions of history, close below ₹20, 20-session average traded value
   below ₹5 crore, any absolute daily move above 35% in the last 60 sessions (treated as unreliable data).
6. **Cross-sectional inputs** — relative strength vs NIFTY 50 (1W/1M/3M/6M excess returns, percentile-ranked),
   sector strength for the session, news published in the 14 days up to the session close, results dates in the
   next 21 days, point-in-time fundamentals, F&O snapshot.
7. **Per-stock evaluation** — `app/analytics/evaluate.py::evaluate` (the same function the backtester uses):
   indicators → price action → levels → score → confidence → hard filters → action.
8. **Reject and rank** — rejected setups and scores below `scanner.min_score` (55) are excluded; the rest are
   sorted by score then confidence.
9. **Diversify** — at most `scanner.max_per_sector` (3) names per industry, up to `scanner.top_n` (10).
10. **Persist an immutable snapshot** — a `recommendation_runs` row, a `signals` row for every evaluated stock,
    and a `recommendations` row for each selected stock, including all levels, the score breakdown, why / why-not,
    invalidation, methodology, data sources, missing components and version strings.
11. **Track outcomes separately** — `update_outcomes` simulates every recommendation forward on later EOD bars
    (`app/recommendations/outcomes.py`) and stores `recommendation_outcomes`.

If no stock passes, the run status is `ok_no_candidates` with the note
"No stock passed all filters today — no recommendation is better than a forced one."

## Scoring

`app/analytics/scoring.py`. Each component returns a fraction in [0, 1] plus reasons and cautions.
Points = fraction × weight. Components without data are shown as unavailable, excluded from the denominator,
and reduce confidence. Total = earned ÷ available weight × 100.

| Component | Default weight | Inputs |
|---|---|---|
| technical | 25 | EMA 20/50/200 stack, ADX and ±DI, Supertrend(10,3), swing structure, patterns, 52-week-high distance |
| momentum | 15 | RSI(14) band, MACD vs signal, ROC 12/63, Stochastic %K, Williams %R |
| volume | 10 | Relative volume, OBV and A/D trend, 20 vs 50-day average volume, delivery % vs its 20-day average |
| relative_strength | 10 | Cross-sectional RS rating (3M 40%, 6M 30%, 1M 20%, 1W 10%) |
| fundamentals | 15 | Fundamental score from filed quarterly results and shareholding (`app/fundamental/scoring.py`) |
| sector | 10 | Sector index strength (1M RS 40%, 3M RS 35%, 1W RS 10%, trend 15%) |
| news | 5 | Recency- and tier-weighted rule-based sentiment, 14-day lookback; 50 when there is no news |
| fno | 5 | F&O snapshot score (buildup, PCR, IV); structural "not an F&O stock" is not penalised |
| risk_reward | 5 | Reward:risk to Target 2 (scaled 1.2→3.0), ×0.8 when the stop is wider than 6% |

Weights are admin-editable (`PUT /api/settings/scoring_weights`); they are normalised to 100 and the new weights
apply to future scans only.

### Confidence

`confidence_from` (scoring.py), clipped to 5–95 (never 100):

- base = 0.55 × score + 0.25 × (100 × (1 − min(component dispersion ÷ 0.35, 1))) + 20
- −0.8 per unavailable weight point (excluding structurally missing components)
- −12 in a `BEARISH` regime, −20 in `STRONG BEARISH`, +4 in `STRONG BULLISH`, −4 if regime confidence < 50
- −25 if market data is not current

### Hard filters and action

`evaluate()` rejects (action `AVOID`) when any of these hold: fewer than ~200 sessions for indicators, close below
the 200-EMA in a bearish regime, RSI(14) above 82, a fresh breakdown below the 20-day low, or any levels rejection
(stop not below entry, risk above `max_risk_pct_per_setup` = 8%, reward:risk to T2 below `min_rr_t2` = 1.8).
Otherwise the action is `WAIT` when price is above the do-not-chase level, results are due within
`results_blackout_sessions` (2), or the regime is `STRONG BEARISH`; else `BUY`.

## Entry, stop and target methodology

`app/analytics/levels.py` (`LEVELS_VERSION = "levels-1.0"`). All levels are rounded to the ₹0.05 tick (stops
down). Every level carries a `methodology` string stored with the recommendation. ATR is floored at 0.3% of price.

| Level | Rule |
|---|---|
| Setup | Classified from detected patterns: breakout(+retest), bull flag, ascending triangle, confirmed double bottom, pullback to 20-EMA, consolidation, else trend continuation |
| Preferred entry zone | Breakout/pattern setups: anchored on the pattern level up to +0.5×ATR. Otherwise from the nearest support or 20-EMA (if within 1.5×ATR) up to +0.6×ATR, else CMP down to −0.5×ATR |
| Conservative zone | Retest of the pattern level (−0.4×ATR), or below the preferred zone (may extend to the 50-EMA) |
| Stop | Tightest structural stop (swing low − 0.25×ATR, support − 0.25×ATR, or breakout level − 1×ATR) whose distance from the entry mid is 1–3.5×ATR; else volatility stop = entry mid − k×ATR (k = 2.0, ×1.15 in bearish regimes) |
| Target 1 | First resistance between 1R and 2R, else 1.5R |
| Target 2 | Next resistance ≥ T1 + 0.5R and ≤ 3.5R, else max(2.5R, T1 + 0.75R) |
| Target 3 | min(3.5R, pattern measured move, next resistance beyond T2), at least T2 + 0.5R |
| Do-not-chase | Price above which reward:risk to T2 falls below `min_rr_t2`, capped at preferred-zone high + 1×ATR |
| Trailing stop after T1 | max(entry mid, T1 − 2×ATR) |
| Holding period | Sessions to T1 at 0.6×ATR/day (min) and to T2 at 0.35×ATR/day (max, ≤ 40); heuristic |

Position sizing (`position_size`, also `POST /api/tools/position-size`):
quantity = floor(capital × risk% ÷ (entry − stop)), reduced if it exceeds capital or `max_position_pct`.

## Market regime model

`app/analytics/regime.py` (`REGIME_VERSION = "regime-1.0"`): a weighted vote of independent components, each in
[−1, +1]. Missing inputs are excluded, weights renormalised, and listed in `missing_inputs`.

| Component | Weight | Input |
|---|---|---|
| nifty_trend | 0.22 | NIFTY 50 vs 50/200-EMA, 20 vs 50-EMA, 50-EMA slope (needs ≥ 210 sessions) |
| banknifty_trend | 0.10 | Same for Nifty Bank |
| breadth | 0.18 | Advance/decline ratio, % above 50-DMA and 200-DMA |
| vix | 0.14 | India VIX 1-year percentile and 10-day change |
| momentum | 0.12 | NIFTY RSI(14), 20-day return, DI direction |
| sector_participation | 0.12 | Share of sector indices in up vs down trend |
| flows | 0.08 | FII/DII provisional net flows, last 8 days |
| global | 0.04 | Global context — no provider is implemented, so this is always listed as missing |

Composite score (−100..+100) thresholds: ≥ 50 `STRONG BULLISH`, ≥ 20 `BULLISH`, > −20 `NEUTRAL`, > −50 `BEARISH`,
else `STRONG BEARISH`. Recommended exposure 90/70/50/25/10% and max positions 10/8/6/3/1 respectively.
Confidence (0–95) = 50% weighted agreement with the composite direction + 30% input coverage + 20% distance from the
nearest threshold. Exposure is multiplied by 0.8 when confidence is below 50.

## Versioning

Every `recommendation_runs` and `recommendations` row stores:

| Field | Current value | Source |
|---|---|---|
| `model_version` | `nivara-model-1.0` | `app/analytics/config.py` |
| `scoring_version` | `score-1.0` | `app/analytics/config.py` |
| `indicator_version` | `ind-1.0` | `app/technical/indicators.py` |
| `levels_version` | `levels-1.0` | `app/analytics/config.py` |
| `tax_rule_version` | `IN-2026.10` (rule set of the first stored tax rule) | `app/tax/defaults.py` |

The run also stores the normalised `weights` used. Market regime rows store `model_version` (`regime-1.0`).
Other versioned components: position monitor `monitor-1.0`, news classifier `rules-v1`, AI prompts `analysis-v1` /
`news-v1`. The `seed` job records versions and their parameters in `model_versions`.

## Data-failure handling

- Providers never fabricate data: they raise `DataUnavailable` / `NotConfigured` (`app/data/providers/base.py`).
- Each ingestion job writes an `ingestion_runs` row (`ok`, `partial`, `failed`) and updates `data_sources`
  (`last_success_at`, `last_data_as_of`, `last_error`). Pipeline steps are isolated: one failing step does not
  stop the others (`app/workers/pipeline.py`).
- Scan: no data → `DATA UNAVAILABLE`; data behind the expected session → `DATA STALE`, no recommendations.
- Partial data: an unavailable component (fundamentals, sector, relative strength, F&O for an F&O stock) is
  listed in `missing_components`, excluded from the score denominator, and lowers confidence.
- Prices are always returned with `kind` (`live_quote`, `delayed_quote`, `eod_close`, `unavailable`), `as_of` and
  `source`. EOD closes are never labelled live.
- `GET /api/market/status` reports `last_eod_date`, `is_current` and `sessions_behind`.

## Suitability tiers and track-record gate

`_suitability` in `app/services/scanner.py`:

| Tier | Condition |
|---|---|
| `observation` | action is not `BUY`, or confidence < 55 |
| `live_consideration` | confidence ≥ 70, missing weight ≤ 15 points, and at least `risk_limits.min_track_record_for_live` (30) closed recommendation outcomes exist |
| `paper_trading` | everything else; when capped by the track-record gate a note records the current count |

Closed outcomes are counted with statuses `target1`, `target2`, `target3`, `stopped`, `expired`, and only for
recommendations from live runs: runs triggered by `replay` or `backfill` are excluded from the gate.

## Recommendation outcome tracking

`app/recommendations/outcomes.py::simulate`, used by both the live track record and the backtester:

- Entry window: first 3 sessions from the recommendation's target session. Fill at the open if inside the zone,
  at `entry_high` if it opens above and trades down into the zone, at the open if it gaps below the zone but above
  the stop. An open at/below the stop before entry is `invalidated`; no fill in the window is `not_triggered`.
- Stop is checked before targets on the same bar; a gap through the stop exits at the open.
- After T1 the stop moves to `trailing_stop_after_t1`; exit fully at T2. No exit within `holding_max` sessions →
  exit at that close (`expired`, or `target1` if T1 was hit).
- MFE/MAE from bar highs/lows while open.

`GET /api/recommendations/track-record` aggregates by regime, sector, strategy, confidence bucket, holding bucket,
model version, action and origin. Recommendations from `replay`/`backfill` runs are labelled `historical_replay`
and reported separately from `live` ones.

## Position monitoring (when to sell)

`app/portfolio/monitor.py::evaluate_position` returns one of `EXIT`, `PARTIAL PROFIT`, `TRAIL STOP`,
`ADD ONLY ON DIP`, `WAIT`, `HOLD` with severity and reasons. Signals: stop hit, technical deterioration (below
50-EMA + Supertrend bearish + MACD below signal), negative high/medium-impact news, bearish regime while under
water, remaining reward < half the risk, better opportunity (the holding's latest scan score is below 45 and the best
score in the latest `ok` scan is at least 30 points higher), Target 1/2 reached. "Results in N sessions" counts
trading sessions. `EXIT` on stop hit, negative news
while losing, or two of {technical deterioration, regime, reward:risk}. Partial profit 30% at T1, 50% at T2.
Levels come from the user's position levels, else the linked recommendation, else system-suggested levels
(labelled as such). `GET /api/portfolio/exits` lists holdings with any exit signal.

## Frontend

Next.js 16 (App Router), React 19, TanStack Query, `lightweight-charts`, Tailwind CSS 4. `next.config.ts`
rewrites `/api/*` to `BACKEND_URL` so the browser talks to one origin; `src/proxy.ts` redirects page requests
without a `nivara_session` cookie to `/login` (the backend still validates every API call). The frontend is under
active development; see the README for the pages present.
