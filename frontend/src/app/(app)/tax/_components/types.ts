import type { HarvestCandidate, Numeric, TaxBucket, TaxProfile, TaxSummary } from "@/lib/types";

/**
 * Local extensions of the tax types: the backend (app/api/routes/tax.py + app/tax/engine.py) returns richer /
 * differently named fields than `@/lib/types` declares. Every field stays optional; UI falls back to n/a.
 */

export type TermTotal = Numeric | { gross_gains?: Numeric; gross_losses?: Numeric; net?: Numeric };

export interface TaxBucketX extends TaxBucket {
  key?: string;
  legal_reference?: string | null;
  gross_gains?: Numeric;
  loss_set_off?: Numeric;
  exemption_applied?: Numeric;
  basic_exemption_applied?: Numeric;
  base_tax?: Numeric;
  surcharge?: Numeric;
  surcharge_rate?: Numeric;
  cess?: Numeric;
  cess_rate?: Numeric;
  total_tax?: Numeric;
}

export interface BySymbolRow {
  symbol?: string;
  STCG?: Numeric;
  LTCG?: Numeric;
  SPEC?: Numeric;
  charges?: Numeric;
  [k: string]: unknown;
}

export interface TaxSummaryX extends Omit<TaxSummary, "totals" | "buckets" | "carry_forward" | "broker_reported" | "status"> {
  status?: string;
  message?: string | null;
  totals?: Record<string, TermTotal>;
  buckets?: TaxBucketX[];
  carry_forward?: Record<string, unknown> | null;
  broker_reported?: Record<string, unknown> | null;
  rule_set_version?: string | null;
  exemption_limit?: Numeric;
  basic_exemption_used?: Numeric;
  base_tax?: Numeric;
  surcharge?: Numeric;
  cess?: Numeric;
  effective_rate?: Numeric;
  notes?: string[];
  available_tax_years?: string[];
  realized_trading_pnl_after_charges?: Numeric;
  potential_liability_note?: string | null;
  not_a_filing_tool?: string | null;
  by_symbol?: BySymbolRow[];
  is_estimate?: boolean;
}

export interface HarvestCandidateX extends Omit<HarvestCandidate, "potential_offset"> {
  quantity?: Numeric;
  cost_of_acquisition?: Numeric;
  market_value?: Numeric;
  unrealized_gain?: Numeric;
  short_term_loss?: Numeric;
  long_term_loss?: Numeric;
  classification?: string | null;
  min_holding_days?: number | null;
  max_holding_days?: number | null;
  estimated_tax_without_sale?: Numeric;
  estimated_tax_with_sale?: Numeric;
  estimated_tax_impact?: Numeric;
  carry_forward_stcl_after?: Numeric;
  carry_forward_ltcl_after?: Numeric;
  status?: string | null;
  incomplete_reasons?: string[];
  notes?: string[];
  // backend sends a list of explanatory strings; types.ts declares a number
  potential_offset?: Numeric | string[];
}

export interface HarvestReportX {
  as_of?: string | null;
  tax_year?: string | null;
  candidates?: HarvestCandidateX[];
  status?: string | null;
  incomplete_reasons?: string[];
  message?: string | null;
  rule_set_version?: string | null;
  notes?: string[];
  label?: string | null;
  note?: string | null;
  estimate_label?: string | null;
  disclaimer?: string | null;
}

export interface TaxProfileX extends Omit<TaxProfile, "carried_forward" | "slab_rate_for_business_income"> {
  slab_rate_for_business_income?: Numeric;
  carried_forward?: Record<string, unknown> | null;
  broker_reported?: Record<string, unknown> | null;
  updated_at?: string | null;
}
