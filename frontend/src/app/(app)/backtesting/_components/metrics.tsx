"use client";

import { AlertTriangle, FlaskConical } from "lucide-react";
import { dateIST, int, num, toNum } from "@/lib/format";
import type { BacktestMetrics, Numeric } from "@/lib/types";
import { Badge, NAValue, Pct, Pnl, TableWrap, Td, Th, THead, cn } from "@/components/ui";

/** Per-split metrics as the backend returns them (superset of BacktestMetrics). */
export type SplitMetrics = BacktestMetrics & {
  start?: string | null;
  end?: string | null;
  return_pct?: number | null;
  start_equity?: Numeric;
  end_equity?: Numeric;
  avg_holding_sessions?: number | null;
  charges?: Numeric;
  note?: string | null;
};

export const SPLIT_ORDER = ["test", "validation", "train", "overall"] as const;

export const SPLIT_LABEL: Record<string, string> = {
  test: "Out-of-sample TEST",
  validation: "Validation",
  train: "Train (in-sample)",
  overall: "Overall",
};

export function orderedSplits(keys: string[]): string[] {
  const known = SPLIT_ORDER.filter((k) => keys.includes(k)) as string[];
  const rest = keys.filter((k) => !(SPLIT_ORDER as readonly string[]).includes(k)).sort();
  return [...known, ...rest];
}

export function BacktestBanner({ text, className }: { text?: string | null; className?: string }) {
  return (
    <div role="note" className={cn("rounded-lg border-2 border-warn/50 bg-warn-soft px-4 py-3 text-warn", className)}>
      <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide">
        <FlaskConical className="size-4 shrink-0" aria-hidden />
        Backtest performance — past simulated results do not guarantee future returns
      </p>
      <p className="mt-1 text-xs text-fg/80">
        {text ??
          "Simulated on historical data with modelled charges and slippage. Judge the out-of-sample TEST split, not the training split."}
      </p>
    </div>
  );
}

function rate(v: Numeric): React.ReactNode {
  // Backend reports rates on a 0–100 scale.
  const n = toNum(v);
  return n === null ? <NAValue /> : `${num(n, 1)}%`;
}

function plain(v: Numeric, digits = 2): React.ReactNode {
  return toNum(v) === null ? <NAValue /> : num(v, digits);
}

function dd(v: Numeric): React.ReactNode {
  const n = toNum(v);
  return n === null ? <NAValue /> : <Pct value={-Math.abs(n)} />;
}

const ROWS: { key: string; label: string; hint?: string; render: (m: SplitMetrics) => React.ReactNode }[] = [
  { key: "cagr", label: "CAGR", render: (m) => <Pct value={m.cagr ?? null} /> },
  { key: "return", label: "Total return", render: (m) => <Pct value={m.return_pct ?? m.total_return_pct ?? null} /> },
  { key: "win_rate", label: "Win rate", render: (m) => rate(m.win_rate ?? null) },
  { key: "profit_factor", label: "Profit factor", hint: "gross wins ÷ gross losses", render: (m) => plain(m.profit_factor ?? null) },
  { key: "max_drawdown_pct", label: "Max drawdown", render: (m) => dd(m.max_drawdown_pct ?? null) },
  { key: "sharpe", label: "Sharpe", render: (m) => plain(m.sharpe ?? null) },
  { key: "sortino", label: "Sortino", render: (m) => plain(m.sortino ?? null) },
  { key: "expectancy", label: "Expectancy", hint: "avg net P&L per trade", render: (m) => <Pnl value={m.expectancy ?? null} /> },
  { key: "trades", label: "Trades", render: (m) => (toNum(m.trades) === null ? <NAValue /> : int(m.trades)) },
  {
    key: "period",
    label: "Period",
    render: (m) => (m.start || m.end ? <span className="whitespace-nowrap">{dateIST(m.start)} → {dateIST(m.end)}</span> : <NAValue />),
  },
];

export function BacktestMetricsTable({
  metrics,
  label = "Backtest metrics by split",
}: {
  metrics: Record<string, SplitMetrics | null | undefined>;
  label?: string;
}) {
  const splits = orderedSplits(Object.keys(metrics));
  if (!splits.length) return <p className="text-xs text-muted">No metrics recorded for this backtest yet.</p>;
  const notes = splits
    .map((s) => ({ s, note: metrics[s]?.note }))
    .filter((x): x is { s: string; note: string } => typeof x.note === "string" && x.note.length > 0);
  return (
    <div className="space-y-2">
      <TableWrap label={label}>
        <THead>
          <tr>
            <Th>Metric</Th>
            {splits.map((s) => (
              <Th
                key={s}
                align="right"
                className={cn(s === "test" && "border-x-2 border-t-2 border-accent bg-accent-soft text-accent", s === "overall" && "opacity-70")}
              >
                <span className="inline-flex items-center gap-1.5">
                  {SPLIT_LABEL[s] ?? s}
                  {s === "test" ? (
                    <Badge tone="accent" size="xs">
                      judge this
                    </Badge>
                  ) : null}
                </span>
              </Th>
            ))}
          </tr>
        </THead>
        <tbody>
          {ROWS.map((r, ri) => (
            <tr key={r.key}>
              <Td className="whitespace-nowrap text-muted">
                {r.label}
                {r.hint ? <span className="block text-[10px] text-subtle">{r.hint}</span> : null}
              </Td>
              {splits.map((s) => {
                const m = metrics[s];
                return (
                  <Td
                    key={s}
                    align="right"
                    className={cn(
                      s === "test" && "border-x-2 border-accent bg-accent-soft/50 font-semibold",
                      s === "test" && ri === ROWS.length - 1 && "border-b-2",
                      s === "overall" && "text-muted",
                    )}
                  >
                    {m ? r.render(m) : <NAValue reason="No metrics for this split" />}
                  </Td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </TableWrap>
      {notes.length ? (
        <ul className="space-y-1">
          {notes.map((n) => (
            <li key={n.s} className="flex items-start gap-1.5 text-xs text-warn">
              <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
              <span>
                <span className="font-semibold">{SPLIT_LABEL[n.s] ?? n.s}:</span> {n.note}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Normalise the `metrics` blob (object of splits, or a flat metrics object) into split → metrics. */
export function normaliseMetrics(v: unknown): Record<string, SplitMetrics | null> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const o = v as Record<string, unknown>;
  const splitKeys = Object.keys(o).filter((k) => o[k] !== null && typeof o[k] === "object" && !Array.isArray(o[k]));
  if (splitKeys.length) {
    const out: Record<string, SplitMetrics | null> = {};
    for (const k of splitKeys) out[k] = o[k] as SplitMetrics;
    return out;
  }
  // Flat metrics with no split breakdown.
  return Object.keys(o).length ? { overall: o as SplitMetrics } : {};
}
