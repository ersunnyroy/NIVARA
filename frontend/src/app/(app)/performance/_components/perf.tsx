"use client";

import { int, NA, num, pct, toNum } from "@/lib/format";
import type { Numeric, PerfStats } from "@/lib/types";
import { NAValue, Pct, Pnl, Stat, cn } from "@/components/ui";

/**
 * PerfStats as the backend actually returns it. Beyond types.ts the backend also sends:
 * net_pnl, best_pnl / worst_pnl (with best / worst being the symbol string), source,
 * return_pct_on_capital, ratios_note, sharpe_monthly_annualised, annual[].
 * The "backtest" kind is a different shape: { backtest_id, name, metrics: {train|validation|test|overall: …}, note }.
 */
export type PerfStatsX = PerfStats & {
  net_pnl?: Numeric;
  best_pnl?: Numeric;
  worst_pnl?: Numeric;
  source?: string | null;
  return_pct_on_capital?: number | null;
  ratios_note?: string | null;
  sharpe_monthly_annualised?: number | null;
  annual?: { year: string; pnl: Numeric }[];
  backtest_id?: number | null;
  name?: string | null;
  metrics?: Record<string, Record<string, unknown> | null> | null;
};

export function asPerf(v: unknown): PerfStatsX | null {
  if (!v || typeof v !== "object") return null;
  return v as PerfStatsX;
}

/** Backend reports win rate on a 0–100 scale. */
export function winRate(v: Numeric): string {
  const n = toNum(v);
  return n === null ? NA : pct(n, 1, false);
}

export function hasTrades(s: PerfStatsX | null | undefined): boolean {
  const n = toNum(s?.total_trades);
  return n !== null && n > 0;
}

/** "2026-03" → "Mar 26". Unknown formats pass through unchanged. */
export function monthLabel(m: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(m);
  if (!match) return m;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const idx = Number(match[2]) - 1;
  return names[idx] ? `${names[idx]} ${match[1].slice(2)}` : m;
}

type BestWorst = PerfStats["best"];

/** best/worst may be a number, a symbol string (with a separate *_pnl), or {symbol, pnl, return_pct}. */
export function BestWorstValue({ value, pnl }: { value: BestWorst | string | null | undefined; pnl?: Numeric }) {
  if (value && typeof value === "object") {
    return (
      <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
        {value.symbol ? <span className="font-semibold">{value.symbol}</span> : null}
        <Pnl value={value.pnl ?? null} className="text-sm" />
        {value.return_pct != null ? <Pct value={value.return_pct} className="text-xs" /> : null}
      </span>
    );
  }
  const asNum = toNum(value);
  if (typeof value === "string" && asNum === null) {
    return (
      <span className="inline-flex flex-wrap items-baseline gap-x-1.5">
        <span className="font-semibold">{value}</span>
        {toNum(pnl) !== null ? <Pnl value={pnl ?? null} className="text-sm" /> : null}
      </span>
    );
  }
  if (asNum !== null) return <Pnl value={asNum} />;
  if (toNum(pnl) !== null) return <Pnl value={pnl ?? null} />;
  return <NAValue />;
}

export function profitFactor(v: Numeric): string {
  return num(v, 2);
}

/** Drawdown shown as a loss (−x%) regardless of the sign convention of the source. */
export function Drawdown({ value }: { value: Numeric }) {
  const n = toNum(value);
  if (n === null) return <NAValue />;
  return <Pct value={-Math.abs(n)} />;
}

export function PerfStatGrid({ stats, className }: { stats: PerfStatsX; className?: string }) {
  const s = stats;
  return (
    <div className={cn("grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6", className)}>
      <Stat size="sm" label="Total trades" value={int(s.total_trades)} sub={`${int(s.wins)} wins · ${int(s.losses)} losses`} />
      <Stat size="sm" label="Win rate" value={winRate(s.win_rate ?? null)} />
      <Stat size="sm" label="Avg win" value={<Pnl value={s.avg_win ?? null} />} />
      <Stat size="sm" label="Avg loss" value={<Pnl value={s.avg_loss ?? null} />} />
      <Stat size="sm" label="Profit factor" value={profitFactor(s.profit_factor ?? null)} sub="gross wins ÷ gross losses" />
      <Stat size="sm" label="Expectancy" value={<Pnl value={s.expectancy ?? null} />} sub="avg net P&L per trade" />
      <Stat size="sm" label="Max drawdown" value={<Drawdown value={s.max_drawdown_pct ?? null} />} />
      <Stat
        size="sm"
        label="Avg holding"
        value={toNum(s.avg_holding_days) === null ? NA : `${num(s.avg_holding_days, 1)} days`}
        tone={toNum(s.avg_holding_days) === null ? "na" : undefined}
      />
      <Stat size="sm" label="Best trade" value={<BestWorstValue value={s.best} pnl={s.best_pnl} />} />
      <Stat size="sm" label="Worst trade" value={<BestWorstValue value={s.worst} pnl={s.worst_pnl} />} />
      {s.net_pnl !== undefined ? <Stat size="sm" label="Net P&L" value={<Pnl value={s.net_pnl ?? null} />} sub="after charges" /> : null}
      {s.return_pct_on_capital !== undefined ? (
        <Stat size="sm" label="Return on capital" value={<Pct value={s.return_pct_on_capital ?? null} />} />
      ) : null}
    </div>
  );
}
