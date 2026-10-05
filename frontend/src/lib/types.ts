/**
 * Central API types for the NIVARA backend.
 *
 * The backend is evolving, so almost everything is optional and nullable: UI code must treat missing
 * values as "n/a" (never zero). Monetary fields may arrive as numbers or as decimal strings (Pydantic
 * serialises Decimal as string) — always pass them through `toNum()` from `@/lib/format`.
 */

export type Numeric = number | string | null | undefined;
export type ISODate = string; // YYYY-MM-DD
export type ISODateTime = string;

/** Common data-quality status attached to many payloads. */
export type DataStatus = "ok" | "partial" | "data_unavailable" | "data_stale" | "error" | (string & {});

export type PriceKind = "eod_close" | "live_quote" | "delayed_quote" | (string & {});

/* ------------------------------------------------------------------ auth */

export interface User {
  id: number;
  email: string;
  full_name?: string | null;
  role: "admin" | "user" | (string & {});
}

export interface AuthStatus {
  registration_open: boolean;
}

export interface LoginResponse {
  user: User;
  csrf_token: string;
  expires_at?: string;
}

/* ---------------------------------------------------------------- market */

export type MarketPhase = "pre_market" | "pre_open" | "open" | "post_close" | "holiday" | "weekend" | (string & {});

export interface MarketStatus {
  phase?: MarketPhase;
  label?: string;
  now_ist?: ISODateTime;
  is_trading_day?: boolean;
  holiday_name?: string | null;
  last_completed_eod_session?: ISODate | null;
  target_session?: ISODate | null;
  next_session?: ISODate | null;
  data_freshness?: {
    status?: DataStatus;
    latest_eod_date?: ISODate | null;
    expected_eod_date?: ISODate | null;
    message?: string | null;
    [k: string]: unknown;
  } | null;
  freshness?: MarketStatus["data_freshness"];
  /** Actual backend shape: EOD data currency vs the calendar. */
  data?: {
    last_eod_date?: ISODate | null;
    is_current?: boolean;
    sessions_behind?: number | null;
    realtime_quotes?: boolean;
  } | null;
  date?: ISODate;
  is_open?: boolean;
  special_session?: string | null;
  next_trading_day?: ISODate | null;
  holidays_loaded?: boolean;
  hours?: { pre_open?: string; open?: string; close?: string } | null;
  data_as_of?: ISODateTime | null;
  [k: string]: unknown;
}

export interface RegimeComponent {
  name: string;
  score?: number | null;
  weight?: number | null;
  reason?: string | null;
  inputs?: Record<string, unknown> | null;
  available?: boolean;
}

export interface Regime {
  regime?: string | null;
  score?: number | null;
  confidence?: number | null;
  recommended_exposure_pct?: number | null;
  max_positions?: number | null;
  components?: RegimeComponent[] | { items?: RegimeComponent[] } | null;
  missing_inputs?: string[] | null;
  data_as_of?: ISODateTime | null;
  session_date?: ISODate | null;
  model_version?: string | null;
  status?: DataStatus;
}

export interface IndexQuote {
  name: string;
  close?: Numeric;
  change_pct?: number | null;
  date?: ISODate | null;
}

export interface Breadth {
  advances?: number | null;
  declines?: number | null;
  unchanged?: number | null;
  pct_above_20dma?: number | null;
  pct_above_50dma?: number | null;
  pct_above_200dma?: number | null;
  new_52w_highs?: number | null;
  new_52w_lows?: number | null;
  date?: ISODate | null;
}

export interface FlowRow {
  date: ISODate;
  category: string;
  buy_value_cr?: Numeric;
  sell_value_cr?: Numeric;
  net_value_cr?: Numeric;
}

export interface SectorRow {
  index_name: string;
  rank?: number | null;
  score?: number | null;
  ret_1w?: number | null;
  ret_1m?: number | null;
  ret_3m?: number | null;
  rs_vs_nifty_1m?: number | null;
  trend?: string | null;
}

export interface Mover {
  symbol: string;
  name?: string | null;
  close?: Numeric;
  change_pct?: number | null;
  volume?: number | null;
}

export interface MarketOverview {
  status?: DataStatus;
  message?: string | null;
  regime?: Regime | null;
  indices?: IndexQuote[];
  breadth?: Breadth | null;
  flows?: FlowRow[];
  sectors?: SectorRow[];
  movers?: { gainers?: Mover[]; losers?: Mover[]; most_active?: Mover[] } | null;
  data_as_of?: ISODateTime | null;
  source?: string | null;
}

/* -------------------------------------------------------- recommendations */

export type Action = "BUY" | "WAIT" | "HOLD" | "SELL" | (string & {});
export type Suitability = "observation" | "paper_trading" | "live_consideration" | (string & {});

export interface ScoreComponent {
  key: string;
  label?: string;
  fraction?: number | null;
  weight?: number | null;
  points?: number | null;
  reasons?: string[];
  cautions?: string[];
  missing_reason?: string | null;
}

export interface ScoreBreakdown {
  total?: number | null;
  earned?: number | null;
  available?: number | null;
  missing_weight?: number | null;
  components?: ScoreComponent[];
}

export interface Methodology {
  entry?: string;
  stop?: string;
  target1?: string;
  target2?: string;
  target3?: string;
  no_chase?: string;
  trailing?: string;
  expected_move?: string;
  holding?: string;
  confidence_notes?: string[];
  [k: string]: unknown;
}

export interface Outcome {
  status?: string;
  entry_price?: Numeric;
  exit_price?: Numeric;
  return_pct?: number | null;
  mfe_pct?: number | null;
  mae_pct?: number | null;
  t1_hit_date?: ISODate | null;
  t2_hit_date?: ISODate | null;
  stop_hit_date?: ISODate | null;
  exit_reason?: string | null;
  sessions_held?: number | null;
}

export interface MissingComponent {
  component: string;
  reason?: string | null;
}

export interface Recommendation {
  id: number;
  rank?: number | null;
  symbol: string;
  name?: string | null;
  sector?: string | null;
  action?: Action;
  suitability?: Suitability;
  score?: number | null;
  score_breakdown?: ScoreBreakdown | null;
  confidence?: number | null;
  setup?: string | null;
  strategy?: string | null;
  cmp?: Numeric;
  aggressive_entry?: Numeric;
  entry_low?: Numeric;
  entry_high?: Numeric;
  conservative_low?: Numeric;
  conservative_high?: Numeric;
  no_chase_above?: Numeric;
  stop?: Numeric;
  trailing_stop_after_t1?: Numeric;
  target1?: Numeric;
  target2?: Numeric;
  target3?: Numeric;
  risk_pct?: number | null;
  reward_pcts?: (number | null)[];
  rr?: number | null;
  holding_min_sessions?: number | null;
  holding_max_sessions?: number | null;
  why?: string[];
  why_not?: string[];
  invalidation?: string | null;
  methodology?: Methodology | null;
  data_sources?: (string | { name?: string; source?: string; as_of?: string })[];
  missing_components?: MissingComponent[];
  market_regime?: string | null;
  data_as_of?: ISODateTime | null;
  generated_at?: ISODateTime | null;
  session_date?: ISODate | null;
  model_version?: string | null;
  outcome?: Outcome | null;
}

export interface ScanRunInfo {
  id?: number;
  session_date?: ISODate | null;
  generated_at?: ISODateTime | null;
  data_as_of?: ISODateTime | null;
  status?: DataStatus;
  notes?: string[];
  universe_size?: number | null;
  eligible_count?: number | null;
  rejection_counts?: Record<string, number>;
  model_version?: string | null;
  scoring_version?: string | null;
  weights?: Record<string, number>;
}

export interface OpportunitiesResponse {
  run?: ScanRunInfo | null;
  items?: Recommendation[];
  status?: DataStatus;
  message?: string | null;
}

export interface BucketStat {
  bucket: string;
  count?: number | null;
  win_rate?: number | null;
  avg_return_pct?: number | null;
}

export interface TrackRecord {
  totals?: {
    count?: number | null;
    closed?: number | null;
    traded?: number | null;
    open?: number | null;
    not_triggered?: number | null;
    avg_sessions_held?: number | null;
    win_rate?: number | null;
    t1_hit_rate?: number | null;
    t2_hit_rate?: number | null;
    stop_hit_rate?: number | null;
    avg_return_pct?: number | null;
    avg_mfe_pct?: number | null;
    avg_mae_pct?: number | null;
  };
  by_regime?: BucketStat[];
  by_sector?: BucketStat[];
  by_strategy?: BucketStat[];
  by_confidence?: BucketStat[];
  by_holding?: BucketStat[];
  by_model_version?: BucketStat[];
  by_action?: BucketStat[];
  by_origin?: BucketStat[];
  note?: string | null;
  data_as_of?: ISODateTime | null;
}

/* ----------------------------------------------------------------- stocks */

export interface StockSearchHit {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  is_fno?: boolean;
}

export interface PriceInfo {
  price?: Numeric;
  as_of?: ISODateTime | null;
  kind?: PriceKind | null;
  source?: string | null;
  prev_close?: Numeric;
  change_pct?: number | null;
}

export interface StockDetail {
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  isin?: string | null;
  sector?: string | null;
  industry?: string | null;
  is_fno?: boolean;
  price?: PriceInfo | null;
  latest_signal?: { score?: number | null; setup?: string | null; session_date?: ISODate | null } | null;
}

export type ChartRange = "1D" | "5D" | "1M" | "3M" | "6M" | "1Y" | "3Y" | "5Y";

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
}

export interface LinePoint {
  time: string;
  value: number | null;
}

export interface BarsResponse {
  bars?: Bar[];
  overlays?: Partial<Record<
    "ema_20" | "ema_50" | "ema_200" | "sma_50" | "bb_upper" | "bb_lower" | "supertrend" | "vwap_20",
    LinePoint[]
  >>;
  panes?: Partial<Record<"rsi_14" | "macd" | "macd_signal" | "macd_hist", LinePoint[]>>;
  interval?: string;
  note?: string | null;
  source?: string | null;
  data_as_of?: ISODateTime | null;
}

/** Setup from /technical: level fields + score breakdown object (differs from Recommendation). */
export type TechnicalSetup = Omit<Partial<Recommendation>, "score"> & {
  score?: ScoreBreakdown | number | null;
  rr_t1?: number | null;
  rr_t2?: number | null;
  holding_min?: number | null;
  holding_max?: number | null;
  valid?: boolean;
  rejections?: string[];
  rejected?: boolean;
  rejection_reasons?: string[];
  confidence_notes?: string[];
};

export interface TechnicalResponse {
  indicators?: Record<string, unknown>;
  price_action?: {
    structure?: string | null;
    supports?: (number | { level?: number; price?: number; strength?: number; note?: string })[];
    resistances?: (number | { level?: number; price?: number; strength?: number; note?: string })[];
    patterns?: Record<string, unknown>;
  } | null;
  setup?: TechnicalSetup | null;
  as_of?: ISODateTime | null;
  notes?: string[];
  disclaimer?: string | null;
  status?: DataStatus;
  message?: string | null;
}

export interface FundamentalMetric {
  value?: Numeric;
  unit?: string | null;
  source?: string | null;
  period_end?: ISODate | null;
  note?: string | null;
}

export interface ResultRow {
  period_end: ISODate;
  revenue?: Numeric;
  ebitda?: Numeric;
  pat?: Numeric;
  eps_basic?: Numeric;
  consolidated?: boolean | null;
  broadcast_at?: ISODateTime | null;
  source_url?: string | null;
}

export interface Growth {
  metric?: string;
  current?: number | null;
  base?: number | null;
  base_period_end?: ISODate | null;
  pct?: number | null;
  description?: string | null;
}

export interface MarginInfo {
  metric?: string;
  current_pct?: number | null;
  prev_quarter_pct?: number | null;
  year_ago_pct?: number | null;
  change_bps_qoq?: number | null;
  change_bps_yoy?: number | null;
}

export interface ResultAnalysis {
  period_end?: ISODate | null;
  basis?: string | null;
  fiscal_quarter?: string | null;
  classification?: string | null;
  qoq?: Record<string, Growth | number | null>;
  yoy?: Record<string, Growth | number | null>;
  margins?: Record<string, MarginInfo | number | null> | null;
  other_income_share_pct?: number | null;
  flags?: ({ code?: string; severity?: string; message?: string } | string)[];
  points?: { rule?: string; input?: string; points?: number }[];
  total_points?: number | null;
  summary_text?: string | null;
}

export interface FundamentalsResponse {
  score?: number | null;
  completeness?: number | null;
  metrics?: Record<string, FundamentalMetric>;
  breakdown?: Record<string, unknown>;
  result_analysis?: ResultAnalysis | null;
  reasons?: string[];
  cautions?: string[];
  basis?: string | null;
  price_used?: PriceInfo | null;
  results?: ResultRow[];
  missing?: string[];
  notes?: string[];
  status?: DataStatus;
  as_of?: ISODateTime | null;
}

export interface AIAnalysis {
  status?: "ok" | "ai_not_configured" | "error" | (string & {});
  generated_at?: ISODateTime | null;
  model?: string | null;
  message?: string | null;
  sections?: {
    executive_summary?: string;
    bull_case?: string[];
    bear_case?: string[];
    technical?: string;
    fundamental?: string;
    news?: string;
    fno?: string;
    market_context?: string;
    entry?: string;
    stop?: string;
    targets?: string;
    risk_reward?: string;
    invalidation?: string;
    final_score?: string | number;
    [k: string]: unknown;
  } | null;
  citations?: { label: string; value?: unknown; source?: string | null; field?: string | null }[];
  data_as_of?: ISODateTime | null;
  disclaimer?: string | null;
  guardrail_flags?: string[];
  deterministic_fallback?: Record<string, unknown> | string | null;
}

export interface FnoSnapshot {
  date?: ISODate | null;
  underlying?: string;
  spot?: Numeric;
  fut_price?: Numeric;
  basis_pct?: number | null;
  fut_oi?: number | null;
  fut_oi_change_pct?: number | null;
  pcr_oi?: number | null;
  max_pain?: Numeric;
  call_resistance?: Numeric;
  put_support?: Numeric;
  atm_iv?: number | null;
  iv_percentile?: number | null;
  buildup?: string | null;
  interpretation?: string | null;
  [k: string]: unknown;
}

export interface StockFno {
  snapshot?: FnoSnapshot | null;
  history?: FnoSnapshot[];
  status?: DataStatus;
  message?: string | null;
}

export interface CorporateAction {
  id?: number;
  ex_date?: ISODate | null;
  record_date?: ISODate | null;
  action_type?: string | null;
  subject?: string | null;
  ratio_from?: number | null;
  ratio_to?: number | null;
  kind?: string | null;
  purpose?: string | null;
  details?: string | null;
  ratio?: string | null;
  amount?: Numeric;
  source?: string | null;
}

export interface ShareholdingRow {
  period_end?: ISODate | null;
  promoter_pct?: number | null;
  fii_pct?: number | null;
  dii_pct?: number | null;
  public_pct?: number | null;
  pledged_pct?: number | null;
  promoter_pledged_pct?: number | null;
  mf_pct?: number | null;
  source?: string | null;
  [k: string]: unknown;
}

/** GET /stocks/{symbol}/signals */
export interface StockSignals {
  recommendations?: Recommendation[];
  scores?: { session_date: ISODate; score?: number | null; setup?: string | null; rejected?: boolean }[];
}

export interface SignalRow {
  id?: number;
  session_date?: ISODate;
  score?: number | null;
  setup?: string | null;
  action?: Action;
  rank?: number | null;
  rejected?: boolean;
  rejection_reasons?: string[];
  outcome?: Outcome | null;
  recommendation_id?: number | null;
}

/* ------------------------------------------------------------------ tools */

export interface PositionSizeIn {
  capital: number;
  risk_pct: number;
  entry: number;
  stop: number;
  targets: number[];
  max_position_pct?: number;
}

export interface PositionSizeOut {
  quantity?: number;
  capital_required?: Numeric;
  max_loss?: Numeric;
  risk_per_share?: Numeric;
  potential_profits?: (Numeric | { target?: number; profit?: Numeric; rr?: number })[];
  capped_by?: string | null;
  notes?: string[];
}

export interface ChargesIn {
  segment: "delivery" | "intraday";
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  trade_date: ISODate;
  exchange: "NSE" | "BSE";
}

export interface ChargesOut {
  brokerage?: Numeric;
  stt?: Numeric;
  exchange_txn?: Numeric;
  sebi?: Numeric;
  stamp?: Numeric;
  gst?: Numeric;
  dp?: Numeric;
  total?: Numeric;
  schedule_name?: string | null;
  ipft?: Numeric;
  turnover?: Numeric;
  label?: string | null;
  notes?: string | string[] | null;
}

/* -------------------------------------------------------------- portfolio */

export interface Portfolio {
  id: number;
  name: string;
  kind?: "live" | "paper" | "model" | (string & {});
  broker?: string | null;
  created_at?: ISODateTime | null;
  summary?: PortfolioSummary | null;
}

export interface PortfolioSummary {
  invested?: Numeric;
  current_value?: Numeric;
  gross_pnl?: Numeric;
  unrealized_gross_pnl?: Numeric;
  realized_gross_pnl?: Numeric;
  charges_incl_estimated_exit?: Numeric;
  estimated_tax_unrealized?: Numeric;
  estimated_tax_realized?: Numeric;
  net_pnl?: Numeric;
  net_return_pct?: number | null;
  tax_year?: string | null;
  day_change?: Numeric;
  data_as_of?: ISODateTime | null;
}

export interface SellSignal {
  code: string;
  reason?: string | null;
}

export interface PositionMonitor {
  action?: string | null;
  severity?: "info" | "low" | "medium" | "high" | "critical" | (string & {}) | null;
  reasons?: string[];
  sell_signals?: SellSignal[];
  suggested_trailing_stop?: Numeric;
  partial_exit_pct?: number | null;
  pnl?: Numeric;
  pnl_pct?: number | null;
  distance_to_stop_pct?: number | null;
  distance_to_target_pct?: number | null;
  levels?: {
    stop?: Numeric;
    target1?: Numeric;
    target2?: Numeric;
    trailing_stop?: Numeric;
    source?: string | null;
  } | null;
}

export interface Lot {
  id?: number;
  lot_id?: number;
  is_bonus?: boolean;
  acquired_date?: ISODate;
  quantity?: Numeric;
  remaining_quantity?: Numeric;
  cost_per_share?: Numeric;
  holding_days?: number | null;
  term?: string | null;
  days_to_ltcg?: number | null;
}

export interface Position {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  quantity?: Numeric;
  avg_cost?: Numeric;
  invested?: Numeric;
  price?: Numeric;
  price_as_of?: ISODateTime | null;
  price_kind?: PriceKind | null;
  price_source?: string | null;
  day_change_pct?: number | null;
  current_value?: Numeric;
  gross_pnl?: Numeric;
  gross_pnl_pct?: number | null;
  charges_paid?: Numeric;
  est_exit_charges?: Numeric;
  est_tax_if_sold?: Numeric;
  tax_status?: string | null;
  tax_terms?: string[];
  tax_incomplete_reasons?: string[];
  avg_cost_incl_charges?: Numeric;
  net_pnl?: Numeric;
  net_pnl_pct?: number | null;
  lots?: Lot[];
  monitor?: PositionMonitor | null;
  thesis?: string | null;
}

export interface PortfolioDetail {
  portfolio?: Portfolio;
  summary?: PortfolioSummary;
  positions?: Position[];
  realized?: RealizedSummary | null;
  risk?: { sector_allocation?: Record<string, number>; warnings?: string[] } | null;
  labels?: { tax?: string; disclaimer?: string; unrealized_note?: string } | null;
  data_as_of?: ISODateTime | null;
}

export interface RealizedRow {
  symbol?: string;
  quantity?: Numeric;
  acquired_date?: ISODate;
  sold_date?: ISODate;
  purchase_value?: Numeric;
  sale_value?: Numeric;
  buy_charges?: Numeric;
  sell_charges?: Numeric;
  capital_gain?: Numeric;
  trading_pnl?: Numeric;
  holding_days?: number | null;
  term?: string | null;
  tax_year?: string | null;
  est_tax?: Numeric;
  flags?: string[];
}

/** GET /portfolios/{id}/realized */
export interface RealizedResponse {
  tax_year?: string;
  lines?: RealizedRow[];
  summary?: RealizedSummary | null;
}

export interface RealizedSummary {
  capital_gain_gross?: Numeric;
  trading_pnl?: Numeric;
  net_after_tax?: Numeric;
  status?: string;
  incomplete_reasons?: string[];
  tax_year?: string | null;
  totals?: Record<string, Numeric>;
  gross_pnl?: Numeric;
  charges?: Numeric;
  estimated_tax?: Numeric;
  net_pnl?: Numeric;
  rows?: RealizedRow[];
  items?: RealizedRow[];
  [k: string]: unknown;
}

export interface Transaction {
  id: number;
  symbol?: string;
  name?: string | null;
  side: "BUY" | "SELL" | (string & {});
  quantity: Numeric;
  price: Numeric;
  trade_date: ISODate;
  segment?: string;
  exchange?: string;
  broker?: string | null;
  charges_total?: Numeric;
  charges_source?: string | null;
  source?: string | null;
  notes?: string | null;
}

export interface TransactionIn {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  trade_date: ISODate;
  segment: "delivery" | "intraday";
  exchange: "NSE" | "BSE";
  broker?: string | null;
  charges_total?: number | null;
  notes?: string | null;
}

export interface PositionLevelsIn {
  stop?: number | null;
  target1?: number | null;
  target2?: number | null;
  trailing_stop?: number | null;
  thesis?: string | null;
}

export interface PortfolioActionItem {
  symbol: string;
  portfolio?: string | null;
  portfolio_id?: number | null;
  action?: string | null;
  severity?: string | null;
  reasons?: string[];
  sell_signals?: SellSignal[];
  suggested_trailing_stop?: Numeric;
  partial_exit_pct?: number | null;
  pnl?: Numeric;
  pnl_pct?: number | null;
}

export interface PortfolioDashboard {
  summary?: PortfolioSummary | null;
  actions?: PortfolioActionItem[];
  portfolios?: (Portfolio & { summary?: PortfolioSummary | null })[];
  data_as_of?: ISODateTime | null;
}

/* ------------------------------------------------------- trades & perf */

export type TradeKind = "live" | "paper" | "system" | "user" | (string & {});

export interface Trade {
  id: number;
  symbol?: string;
  stock?: string;
  kind?: TradeKind;
  status?: "open" | "closed" | (string & {});
  entry_date?: ISODate;
  entry_price?: Numeric;
  quantity?: Numeric;
  stop?: Numeric;
  target?: Numeric;
  exit_date?: ISODate | null;
  exit_price?: Numeric;
  reason_entry?: string | null;
  reason_exit?: string | null;
  market_regime?: string | null;
  score_at_entry?: number | null;
  gross_pnl?: Numeric;
  charges?: Numeric;
  tax_estimate?: Numeric;
  net_pnl?: Numeric;
  notes?: string | null;
}

export interface TradeIn {
  /** Required by POST/PUT /trades. */
  portfolio_id?: number;
  symbol: string;
  stock?: string;
  kind: TradeKind;
  entry_date: ISODate;
  entry_price: number;
  quantity: number;
  stop?: number | null;
  target?: number | null;
  exit_date?: ISODate | null;
  exit_price?: number | null;
  reason_entry?: string | null;
  reason_exit?: string | null;
  market_regime?: string | null;
  score_at_entry?: number | null;
  charges?: number | null;
  notes?: string | null;
}

export interface PerfStats {
  total_trades?: number | null;
  wins?: number | null;
  losses?: number | null;
  win_rate?: number | null;
  avg_win?: Numeric;
  avg_loss?: Numeric;
  profit_factor?: number | null;
  expectancy?: Numeric;
  max_drawdown_pct?: number | null;
  avg_holding_days?: number | null;
  best?: Numeric | { symbol?: string; pnl?: Numeric; return_pct?: number };
  worst?: Numeric | { symbol?: string; pnl?: Numeric; return_pct?: number };
  monthly?: { month: string; pnl: Numeric }[];
  equity_curve?: { date: string; value: Numeric }[];
  note?: string | null;
  data_as_of?: ISODateTime | null;
}

export interface PerformanceResponse {
  kinds?: Partial<Record<"backtest" | "paper" | "live" | "system" | "user", PerfStats | null>>;
  data_as_of?: ISODateTime | null;
}

/* -------------------------------------------------------------------- tax */

export interface TaxBucket {
  term?: string;
  bucket?: string;
  label?: string;
  gains?: Numeric;
  losses?: Numeric;
  net?: Numeric;
  after_set_off?: Numeric;
  exemption?: Numeric;
  taxable?: Numeric;
  rate?: number | null;
  rate_pct?: number | null;
  tax?: Numeric;
  [k: string]: unknown;
}

export interface TaxSummary {
  tax_year?: string;
  status?: DataStatus | "complete" | "incomplete";
  incomplete_reasons?: string[];
  totals?: Partial<Record<"STCG" | "LTCG" | "SPEC" | (string & {}), Numeric>>;
  buckets?: TaxBucket[];
  set_off_log?: (string | { from?: string; to?: string; amount?: Numeric; note?: string })[];
  exemption_used?: Numeric;
  total_tax_estimate?: Numeric;
  charges_total?: Numeric;
  gross_pnl?: Numeric;
  net_after_tax?: Numeric;
  carry_forward?: Record<string, Numeric>;
  broker_reported?: Record<string, Numeric> | null;
  label?: string;
  disclaimer?: string;
  rule_version?: string | null;
}

export interface HarvestCandidate {
  symbol: string;
  unrealized_loss?: Numeric;
  term?: string | null;
  holding_days?: number | null;
  potential_offset?: Numeric;
  tax_without?: Numeric;
  tax_with?: Numeric;
  tax_difference?: Numeric;
  label?: string | null;
  note?: string | null;
}

export interface TaxProfile {
  residency?: "resident" | "nri" | (string & {});
  regime?: "new" | "old" | (string & {});
  other_taxable_income?: Numeric;
  slab_rate_for_business_income?: number | null;
  carried_forward?: { STCL?: Numeric; LTCL?: Numeric };
}

/* ------------------------------------------------------- watchlists/alerts */

export interface Watchlist {
  id: number;
  name: string;
  kind?: string;
  item_count?: number;
  count?: number;
}

export interface WatchlistItem {
  symbol: string;
  name?: string | null;
  price?: PriceInfo | null;
  change_pct?: number | null;
  score?: number | null;
  setup?: string | null;
  in_entry_zone?: boolean | null;
  notes?: string | null;
}

export interface WatchlistDetail extends Watchlist {
  items?: WatchlistItem[];
}

export type AlertType =
  | "entry_zone" | "stop" | "target" | "breakout" | "breakdown" | "unusual_volume" | "major_news"
  | "results" | "price_move" | "score_change" | "regime_change" | "price_above" | "price_below";

export interface AlertRule {
  id: number;
  symbol?: string | null;
  alert_type: AlertType | (string & {});
  params?: Record<string, unknown>;
  channels?: string[];
  is_active?: boolean;
  created_at?: ISODateTime | null;
  last_triggered_at?: ISODateTime | null;
}

export interface AlertEvent {
  id: number;
  alert_id?: number | null;
  symbol?: string | null;
  alert_type?: string | null;
  title?: string | null;
  message?: string | null;
  severity?: string | null;
  created_at?: ISODateTime | null;
  triggered_at?: ISODateTime | null;
  read_at?: ISODateTime | null;
  is_read?: boolean;
}

/* ------------------------------------------------------------------- news */

export interface NewsItem {
  id: number | string;
  symbol?: string | null;
  company?: string | null;
  source?: string | null;
  source_tier?: number | string | null;
  verification?: string | null;
  headline: string;
  url?: string | null;
  published_at?: ISODateTime | null;
  event_type?: string | null;
  sentiment?: number | null;
  sentiment_label?: string | null;
  impact?: string | null;
  horizon?: string | null;
  confidence?: number | null;
  is_verified?: boolean | null;
  ai?: { facts?: string[]; interpretation?: string[]; speculation?: string[] } | null;
}

/* -------------------------------------------------------------------- F&O */

export interface FnoOverview {
  date?: ISODate | null;
  items?: FnoSnapshot[];
  status?: DataStatus;
  message?: string | null;
  source?: string | null;
}

/* -------------------------------------------------------------- backtests */

export interface BacktestMetrics {
  cagr?: number | null;
  win_rate?: number | null;
  profit_factor?: number | null;
  max_drawdown_pct?: number | null;
  sharpe?: number | null;
  sortino?: number | null;
  expectancy?: Numeric;
  trades?: number | null;
  total_return_pct?: number | null;
}

export interface Backtest {
  id: number;
  name?: string;
  strategy?: string;
  start_date?: ISODate;
  end_date?: ISODate;
  status?: "queued" | "running" | "done" | "completed" | "failed" | (string & {});
  created_at?: ISODateTime | null;
  finished_at?: ISODateTime | null;
  params?: Record<string, unknown>;
  universe?: string | null;
  error?: string | null;
}

export interface BacktestDetail extends Backtest {
  metrics?: Partial<Record<"train" | "validation" | "test" | (string & {}), BacktestMetrics | null>>;
  equity_curve?: { date: string; value: Numeric; split?: string }[];
  trades?: {
    symbol?: string;
    entry_date?: ISODate;
    exit_date?: ISODate;
    entry_price?: Numeric;
    exit_price?: Numeric;
    quantity?: Numeric;
    pnl?: Numeric;
    net_pnl?: Numeric;
    return_pct?: number | null;
    exit_reason?: string | null;
    split?: string | null;
  }[];
  warnings?: string[];
  splits?: Record<string, { start?: ISODate; end?: ISODate } | string | unknown>;
}

export interface BacktestIn {
  name: string;
  strategy: "ranking" | "breakout" | "momentum" | "mean_reversion" | "combined";
  start_date: ISODate;
  end_date: ISODate;
  params: { capital: number; risk_pct: number; max_positions: number; slippage_bps: number; top_n: number };
  universe: string;
}

/* ------------------------------------------------------------------ paper */

export interface PaperOrder {
  id: number;
  symbol?: string;
  side?: "BUY" | "SELL" | (string & {});
  quantity?: Numeric;
  order_type?: "MARKET" | "LIMIT" | (string & {});
  limit_price?: Numeric;
  stop?: Numeric;
  target?: Numeric;
  status?: string;
  created_at?: ISODateTime | null;
  filled_at?: ISODateTime | null;
  fill_price?: Numeric;
  fill_note?: string | null;
}

export interface PaperOrderIn {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price?: number | null;
  stop?: number | null;
  target?: number | null;
}

export interface PaperResponse {
  portfolio?: PortfolioDetail | null;
  orders?: PaperOrder[];
  follow_model?: boolean;
  comparison?: { model?: PerfStats | Record<string, unknown> | null; user?: PerfStats | Record<string, unknown> | null } | null;
  fill_policy?: string | null;
}

/* ----------------------------------------------------------- settings/admin */

export type SettingsMap = {
  scoring_weights?: Record<string, number>;
  risk_limits?: Record<string, unknown>;
  exclusions?: Record<string, unknown>;
  regime?: Record<string, unknown>;
  scanner?: Record<string, unknown>;
  market_hours?: Record<string, unknown>;
  ai?: Record<string, unknown>;
  notifications?: Record<string, unknown>;
  [k: string]: Record<string, unknown> | undefined;
};

/** GET /settings */
export interface SettingsResponse {
  config?: SettingsMap;
  defaults?: SettingsMap;
  editable?: boolean;
  versions?: Record<string, number>;
}

export type HealthStatus = "GREEN" | "YELLOW" | "RED" | "DISABLED" | (string & {});

export interface HealthComponent {
  key: string;
  name?: string;
  kind?: string;
  status: HealthStatus;
  last_success_at?: ISODateTime | null;
  last_data_as_of?: ISODateTime | null;
  last_error?: string | null;
  sla_minutes?: number | null;
  message?: string | null;
}

export interface IngestionRun {
  id?: number;
  job?: string;
  source?: string;
  status?: string;
  started_at?: ISODateTime | null;
  finished_at?: ISODateTime | null;
  rows?: number | null;
  rows_written?: number | null;
  error?: string | null;
  message?: string | null;
  target_date?: ISODate | null;
}

export interface SystemHealth {
  components?: HealthComponent[];
  workers?: Record<string, unknown>;
  database?: Record<string, unknown>;
  ingestion_runs?: IngestionRun[];
  checked_at?: ISODateTime | null;
}

export interface DataSource {
  key: string;
  name?: string;
  kind?: string;
  enabled?: boolean;
  configured?: boolean;
  required_env?: string[];
  missing_env?: string[];
  status?: HealthStatus | string;
  priority?: number | null;
  notes?: string | null;
  capabilities?: string[];
  [k: string]: unknown;
}

export interface AuditLog {
  id: number;
  at?: ISODateTime;
  created_at?: ISODateTime;
  user_id?: number | null;
  user_email?: string | null;
  action: string;
  entity?: string | null;
  entity_type?: string | null;
  entity_id?: string | number | null;
  details?: Record<string, unknown> | null;
  ip?: string | null;
}

export interface AdminUser extends User {
  is_active?: boolean;
  created_at?: ISODateTime | null;
  last_login_at?: ISODateTime | null;
}

export type JobName =
  | "securities" | "holidays" | "eod" | "backfill" | "fno" | "flows" | "news" | "corporate_actions"
  | "fundamentals" | "scan" | "outcomes" | "regime";

export interface JobResponse {
  ok?: boolean;
  job?: string;
  task_id?: string | null;
  status?: string;
  message?: string | null;
  [k: string]: unknown;
}
