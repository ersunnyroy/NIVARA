import type { AlertType } from "@/lib/types";

export interface ParamSpec {
  key: string;
  label: string;
  required?: boolean;
  /** Pre-filled value (the backend's own default for this parameter). */
  defaultValue?: string;
  hint?: string;
  min?: number;
  step?: string;
}

export interface AlertTypeSpec {
  label: string;
  description: string;
  needsSymbol: boolean;
  params: ParamSpec[];
}

/**
 * Parameter keys match the backend rule engine (app/alerts/engine.py): price_above/below → `level`,
 * price_move → `pct`, score_change → `points`, unusual_volume → `multiple`; entry_zone/stop/target fall back
 * to the latest recommendation's levels when left blank.
 */
export const ALERT_TYPES: Record<AlertType, AlertTypeSpec> = {
  price_above: {
    label: "Price crosses above",
    description: "Fires when the price is at or above your level.",
    needsSymbol: true,
    params: [{ key: "level", label: "Price level (₹)", required: true, min: 0, step: "any" }],
  },
  price_below: {
    label: "Price falls below",
    description: "Fires when the price is at or below your level.",
    needsSymbol: true,
    params: [{ key: "level", label: "Price level (₹)", required: true, min: 0, step: "any" }],
  },
  price_move: {
    label: "Large daily move",
    description: "Fires when the day's change (up or down) is at least this many percent.",
    needsSymbol: true,
    params: [{ key: "pct", label: "Move threshold (%)", defaultValue: "5", min: 0, step: "any" }],
  },
  entry_zone: {
    label: "Enters entry zone",
    description: "Fires when the price is inside the entry range. Blank = use the latest recommendation's range.",
    needsSymbol: true,
    params: [
      { key: "entry_low", label: "Entry low (₹)", min: 0, step: "any", hint: "Optional" },
      { key: "entry_high", label: "Entry high (₹)", min: 0, step: "any", hint: "Optional" },
    ],
  },
  stop: {
    label: "Stop-loss hit",
    description: "Fires when the price is at or below the stop. Blank = latest recommendation's stop.",
    needsSymbol: true,
    params: [{ key: "stop", label: "Stop (₹)", min: 0, step: "any", hint: "Optional" }],
  },
  target: {
    label: "Target reached",
    description: "Fires when the price is at or above the target. Blank = latest recommendation's Target 1.",
    needsSymbol: true,
    params: [{ key: "target", label: "Target (₹)", min: 0, step: "any", hint: "Optional" }],
  },
  breakout: {
    label: "Breakout",
    description: "Close above the 20-day high (from EOD data).",
    needsSymbol: true,
    params: [],
  },
  breakdown: {
    label: "Breakdown",
    description: "Close below the 20-day low (from EOD data).",
    needsSymbol: true,
    params: [],
  },
  unusual_volume: {
    label: "Unusual volume",
    description: "Volume at least this multiple of the 20-day average.",
    needsSymbol: true,
    params: [{ key: "multiple", label: "Volume multiple (×)", defaultValue: "2.5", min: 1, step: "any" }],
  },
  major_news: {
    label: "Major news",
    description: "New medium/high-impact news for the stock.",
    needsSymbol: true,
    params: [],
  },
  results: {
    label: "Results announced",
    description: "New earnings / financial-results news for the stock.",
    needsSymbol: true,
    params: [],
  },
  score_change: {
    label: "Score change",
    description: "Opportunity score moved by at least this many points between scans.",
    needsSymbol: true,
    params: [{ key: "points", label: "Score change (points)", defaultValue: "10", min: 1, step: "any" }],
  },
  regime_change: {
    label: "Market regime change",
    description: "The market regime classification changed (market-wide; no symbol).",
    needsSymbol: false,
    params: [],
  },
};

export const ALERT_TYPE_KEYS = Object.keys(ALERT_TYPES) as AlertType[];

export function alertLabel(t?: string | null): string {
  if (!t) return "n/a";
  return (ALERT_TYPES as Record<string, AlertTypeSpec>)[t]?.label ?? t.replace(/_/g, " ");
}

export const CHANNELS = [
  { key: "in_app", label: "In-app" },
  { key: "email", label: "Email" },
  { key: "webhook", label: "Webhook" },
] as const;
