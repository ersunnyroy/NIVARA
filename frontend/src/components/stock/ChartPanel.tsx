"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { Info } from "lucide-react";
import { useBars } from "@/lib/hooks";
import { useResolvedTheme } from "@/lib/theme";
import type { ChartRange } from "@/lib/types";
import { Card, DataStamp, EmptyState, ErrorState, Segmented, Skeleton, cn } from "@/components/ui";
import { OVERLAY_LEGEND, overlayColor, type IndicatorKey } from "@/components/charts/CandleChart";

const CandleChart = dynamic(() => import("@/components/charts/CandleChart").then((m) => m.CandleChart), {
  ssr: false,
  loading: () => <Skeleton className="h-[420px] w-full" />,
});

const RANGES: ChartRange[] = ["1D", "5D", "1M", "3M", "6M", "1Y", "3Y", "5Y"];
const INDICATORS: { key: IndicatorKey; label: string }[] = [
  { key: "ema", label: "EMA" },
  { key: "sma", label: "SMA" },
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
  { key: "volume", label: "Volume" },
  { key: "vwap", label: "VWAP" },
  { key: "bb", label: "Bollinger" },
  { key: "supertrend", label: "Supertrend" },
];
const LEGEND_FOR: Partial<Record<IndicatorKey, string[]>> = {
  ema: ["ema_20", "ema_50", "ema_200"],
  sma: ["sma_50"],
  vwap: ["vwap_20"],
  bb: ["bb_upper"],
  supertrend: ["supertrend"],
};

export function ChartPanel({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<ChartRange>("6M");
  const [ind, setInd] = useState<Set<IndicatorKey>>(() => new Set<IndicatorKey>(["ema", "volume"]));
  const q = useBars(symbol, range);
  const theme = useResolvedTheme();
  const toggle = (k: IndicatorKey) =>
    setInd((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });
  const subPanes = (ind.has("rsi") ? 1 : 0) + (ind.has("macd") ? 1 : 0);
  const height = 420 + subPanes * 120;
  const legend = [...ind].flatMap((k) => LEGEND_FOR[k] ?? []);

  return (
    <Card>
      <div className="flex flex-col gap-2 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <Segmented label="Chart range" options={RANGES.map((r) => ({ key: r, label: r }))} value={range} onChange={setRange} size="xs" />
        <div className="flex flex-wrap gap-1" role="group" aria-label="Indicators">
          {INDICATORS.map((i) => {
            const on = ind.has(i.key);
            return (
              <button
                key={i.key}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(i.key)}
                className={cn(
                  "rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors",
                  on ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-fg",
                )}
              >
                {i.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="px-2 pt-2">
        {legend.length ? (
          <ul className="mb-1 flex flex-wrap gap-x-3 gap-y-1 px-2 text-[11px] text-muted" aria-label="Chart legend">
            {legend.map((k) => (
              <li key={k} className="inline-flex items-center gap-1">
                <span
                  className="inline-block h-0.5 w-4 rounded"
                  style={{ background: overlayColor(k, theme), borderTop: OVERLAY_LEGEND[k]?.dashed ? "1px dashed" : undefined }}
                  aria-hidden
                />
                {OVERLAY_LEGEND[k]?.label ?? k}
              </li>
            ))}
          </ul>
        ) : null}
        {q.isPending ? (
          <Skeleton className="h-[420px] w-full" />
        ) : q.isError ? (
          <div className="p-2">
            <ErrorState error={q.error} onRetry={() => q.refetch()} unavailableHint="Price history appears after EOD ingestion / backfill (Settings → Jobs)." />
          </div>
        ) : !q.data.bars?.length ? (
          <EmptyState title="No price history for this range">An admin can run the backfill job from Settings → Jobs to load historical EOD bars.</EmptyState>
        ) : (
          <div className={cn("transition-opacity", q.isPlaceholderData && "opacity-60")}>
            <CandleChart data={q.data} indicators={ind} height={height} />
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2">
        <DataStamp
          asOf={q.data?.data_as_of ?? q.data?.bars?.[q.data.bars.length - 1]?.time}
          source={q.data?.source ?? "NSE EOD"}
          kind={q.data?.interval === "1d" || !q.data?.interval ? "eod_close" : "live_quote"}
          label="Last bar"
        />
        <span className="text-[11px] text-muted">Interval: {q.data?.interval ?? "n/a"}</span>
      </div>
      {q.data?.note ? (
        <p className="flex items-start gap-1.5 border-t border-border bg-info-soft/50 px-4 py-2 text-[11px] text-info">
          <Info className="mt-px size-3.5 shrink-0" aria-hidden /> {q.data.note}
        </p>
      ) : null}
    </Card>
  );
}
