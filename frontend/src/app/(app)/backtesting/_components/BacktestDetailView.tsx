"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useBacktest } from "@/lib/hooks";
import { dateIST, inr, int, num, titleCase, toNum } from "@/lib/format";
import type { BacktestDetail, Numeric } from "@/lib/types";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  EmptyState,
  ErrorState,
  Money,
  NAValue,
  Pct,
  Pnl,
  Segmented,
  SkeletonCard,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { EquityCurve } from "@/components/charts/svg";
import { BacktestBanner, BacktestMetricsTable, normaliseMetrics, SPLIT_LABEL } from "./metrics";
import { BacktestStatusBadge, isActive } from "./status";
import { DeleteBacktestButton } from "./DeleteBacktestButton";

/** Fields the backend sends beyond types.ts (equity points carry `equity`, not `value`). */
type BTTradeX = NonNullable<BacktestDetail["trades"]>[number] & {
  gross_pnl?: Numeric;
  charges?: Numeric;
  holding_sessions?: number | null;
  score?: number | null;
  signal_date?: string | null;
};
type BTDetailX = Omit<BacktestDetail, "equity_curve" | "trades"> & {
  equity_curve?: { date: string; value?: Numeric; equity?: Numeric; split?: string | null }[];
  trades?: BTTradeX[];
  completed_at?: string | null;
  model_version?: string | null;
  banner?: string | null;
};

const MAX_TRADE_ROWS = 500;

type TradeSplit = "all" | "test" | "validation" | "train";
const TRADE_SPLITS: { key: TradeSplit; label: string }[] = [
  { key: "all", label: "All" },
  { key: "test", label: "Test (OOS)" },
  { key: "validation", label: "Validation" },
  { key: "train", label: "Train" },
];

function splitRanges(d: BTDetailX, metrics: ReturnType<typeof normaliseMetrics>): { split: string; start?: string | null; end?: string | null }[] {
  const out: { split: string; start?: string | null; end?: string | null }[] = [];
  const s = (d.splits ?? {}) as Record<string, unknown>;
  for (const k of ["test", "validation", "train"]) {
    const m = metrics[k];
    const raw = s[k];
    if (m && (m.start || m.end)) out.push({ split: k, start: m.start, end: m.end });
    else if (raw && typeof raw === "object") {
      const r = raw as { start?: string; end?: string };
      out.push({ split: k, start: r.start, end: r.end });
    }
  }
  if (out.length) return out;
  // Backend may only send boundaries: { train_end, validation_end }.
  const trainEnd = typeof s.train_end === "string" ? s.train_end : null;
  const valEnd = typeof s.validation_end === "string" ? s.validation_end : null;
  if (trainEnd || valEnd) {
    return [
      { split: "test", start: valEnd ? `after ${valEnd}` : null, end: d.end_date },
      { split: "validation", start: trainEnd ? `after ${trainEnd}` : null, end: valEnd },
      { split: "train", start: d.start_date, end: trainEnd },
    ];
  }
  return [];
}

function fmtBound(v?: string | null): string {
  if (!v) return "n/a";
  if (v.startsWith("after ")) return `after ${dateIST(v.slice(6))}`;
  return dateIST(v);
}

function SplitBadge({ split }: { split?: string | null }) {
  if (!split) return <NAValue />;
  return (
    <Badge tone={split === "test" ? "accent" : split === "validation" ? "info" : "neutral"} size="xs">
      {split === "test" ? "Test (OOS)" : titleCase(split)}
    </Badge>
  );
}

function ParamsList({ params, universe }: { params?: Record<string, unknown>; universe?: string | null }) {
  const p = params ?? {};
  const items: [string, React.ReactNode][] = [
    ["Capital", <Money key="c" value={toNum(p.capital)} />],
    ["Risk / trade", toNum(p.risk_pct) === null ? <NAValue key="r" /> : `${num(p.risk_pct, 2)}%`],
    ["Max positions", toNum(p.max_positions) === null ? <NAValue key="m" /> : int(p.max_positions)],
    ["Top N", toNum(p.top_n) === null ? <NAValue key="t" /> : int(p.top_n)],
    ["Slippage", toNum(p.slippage_bps) === null ? <NAValue key="s" /> : `${num(p.slippage_bps, 1)} bps`],
    ["Universe", universe ?? (typeof p.universe === "string" ? p.universe : <NAValue key="u" />)],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-muted">{k}</dt>
          <dd className="num truncate font-medium">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function BacktestDetailView({ id, onDeleted }: { id: number; onDeleted: () => void }) {
  const q = useBacktest(id);
  const [tradeSplit, setTradeSplit] = useState<TradeSplit>("all");

  if (q.isPending)
    return (
      <div className="space-y-4">
        <BacktestBanner />
        <SkeletonCard lines={8} />
      </div>
    );
  if (q.isError)
    return (
      <div className="space-y-4">
        <BacktestBanner />
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      </div>
    );

  const d = q.data as BTDetailX;
  const metrics = normaliseMetrics(d.metrics);
  const hasMetrics = Object.keys(metrics).length > 0;
  const ranges = splitRanges(d, metrics);
  const curve = (d.equity_curve ?? []).map((p) => ({ date: p.date, value: p.value ?? p.equity ?? null, split: p.split }));
  const warnings = (d.warnings ?? []).filter((w) => typeof w === "string" && w.trim());
  const trades = d.trades ?? [];
  const filteredTrades = tradeSplit === "all" ? trades : trades.filter((t) => t.split === tradeSplit);
  const shownTrades = filteredTrades.slice(0, MAX_TRADE_ROWS);
  const capital = toNum(d.params?.capital);
  const finishedAt = d.completed_at ?? d.finished_at ?? null;
  const lastCurveDate = curve.length ? curve[curve.length - 1].date : null;

  return (
    <div className="space-y-4">
      <BacktestBanner text={d.banner} />
      <Card>
        <CardHeader
          title={
            <span className="flex flex-wrap items-center gap-2">
              {d.name ?? `Backtest #${d.id}`}
              <BacktestStatusBadge status={d.status} />
            </span>
          }
          subtitle={
            <>
              {titleCase(d.strategy)} · {dateIST(d.start_date)} → {dateIST(d.end_date)}
              {d.model_version ? ` · model ${d.model_version}` : ""}
            </>
          }
          actions={<DeleteBacktestButton id={d.id} disabled={isActive(d.status)} onDeleted={onDeleted} />}
        />
        <CardBody className="space-y-3">
          <ParamsList params={d.params} universe={d.universe} />
          <DataStamp label={finishedAt ? "Completed" : "Created"} asOf={finishedAt ?? d.created_at ?? null} source="Simulated on stored EOD history" />
          {isActive(d.status) ? (
            <p className="flex items-center gap-2 rounded-lg bg-info-soft px-3 py-2 text-xs text-info" role="status">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              {d.status === "queued" ? "Queued — waiting for a worker." : "Running — this page refreshes automatically."}
            </p>
          ) : null}
          {d.status === "failed" ? <ErrorState title="Backtest failed" message={d.error ?? "The backtest failed without an error message."} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Metrics by split" subtitle="Out-of-sample TEST first — the only split the strategy never saw during tuning." />
        <CardBody>
          {hasMetrics ? (
            <BacktestMetricsTable metrics={metrics} />
          ) : (
            <EmptyState compact title="No metrics yet">
              {isActive(d.status) ? "Metrics appear once the run completes." : "This run did not record any metrics."}
            </EmptyState>
          )}
        </CardBody>
      </Card>

      {warnings.length ? (
        <Card className="border-warn/40">
          <CardHeader title={<span className="text-warn">Warnings</span>} icon={<AlertTriangle className="size-4 text-warn" />} subtitle="Read these before trusting any number above." />
          <CardBody>
            <ul className="space-y-1.5">
              {warnings.map((w, i) => {
                const overfit = /overfit|over-fit|curve.?fit/i.test(w);
                return (
                  <li key={i} className="flex items-start gap-2 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
                    <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
                    <span>
                      {overfit ? <span className="mr-1 font-bold uppercase">Overfitting risk:</span> : null}
                      <span className="text-fg/80">{w}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Splits" subtitle="Chronological train → validation → out-of-sample test." />
        <CardBody>
          {ranges.length ? (
            <ul className="grid gap-2 sm:grid-cols-3">
              {ranges.map((r) => (
                <li key={r.split} className={r.split === "test" ? "rounded-lg border-2 border-accent bg-accent-soft/50 p-3" : "rounded-lg border border-border p-3"}>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{SPLIT_LABEL[r.split] ?? r.split}</div>
                  <div className="num mt-1 text-sm font-medium">
                    {fmtBound(r.start)} → {fmtBound(r.end)}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">Split boundaries not reported{isActive(d.status) ? " yet" : ""}.</p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Equity curve (simulated)"
          subtitle={capital !== null ? `Dashed line = starting capital ${inr(capital)}. Charges and slippage included; income tax not deducted.` : "Charges and slippage included; income tax not deducted."}
        />
        <CardBody className="space-y-2">
          <EquityCurve points={curve} baseline={capital} label="Simulated backtest equity" />
          {lastCurveDate ? <DataStamp label="Simulated through" asOf={lastCurveDate} /> : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={`Trades (${int(trades.length)})`}
          subtitle="Simulated round trips. Net = after modelled charges."
          actions={
            trades.length ? (
              <Segmented
                label="Filter trades by split"
                size="xs"
                value={tradeSplit}
                onChange={setTradeSplit}
                options={TRADE_SPLITS}
              />
            ) : null
          }
        />
        {trades.length === 0 ? (
          <EmptyState compact title="No trades">
            {isActive(d.status) ? "Trades appear once the run completes." : "The strategy did not take any trades in this period."}
          </EmptyState>
        ) : (
          <>
            <TableWrap label="Backtest trades">
              <THead>
                <tr>
                  <Th>Stock</Th>
                  <Th>Split</Th>
                  <Th>Entry</Th>
                  <Th align="right">Entry price</Th>
                  <Th>Exit</Th>
                  <Th align="right">Exit price</Th>
                  <Th align="right">Qty</Th>
                  <Th align="right">Gross P&amp;L</Th>
                  <Th align="right">Charges</Th>
                  <Th align="right">Net P&amp;L</Th>
                  <Th align="right">Return</Th>
                  <Th align="right">Held</Th>
                  <Th>Exit reason</Th>
                </tr>
              </THead>
              <tbody>
                {shownTrades.map((t, i) => (
                  <Tr key={`${t.symbol}-${t.entry_date}-${i}`}>
                    <Td className="font-semibold">
                      {t.symbol ? (
                        <Link href={`/stocks/${encodeURIComponent(t.symbol)}`} className="hover:text-accent hover:underline">
                          {t.symbol}
                        </Link>
                      ) : (
                        <NAValue />
                      )}
                    </Td>
                    <Td>
                      <SplitBadge split={t.split} />
                    </Td>
                    <Td className="num whitespace-nowrap">{dateIST(t.entry_date)}</Td>
                    <Td align="right">
                      <Money value={t.entry_price ?? null} />
                    </Td>
                    <Td className="num whitespace-nowrap">{t.exit_date ? dateIST(t.exit_date) : <span className="text-muted">open</span>}</Td>
                    <Td align="right">
                      <Money value={t.exit_price ?? null} />
                    </Td>
                    <Td align="right">{toNum(t.quantity) === null ? <NAValue /> : int(t.quantity)}</Td>
                    <Td align="right">
                      <Pnl value={t.gross_pnl ?? t.pnl ?? null} />
                    </Td>
                    <Td align="right">
                      <Money value={t.charges ?? null} />
                    </Td>
                    <Td align="right" className="font-semibold">
                      <Pnl value={t.net_pnl ?? null} />
                    </Td>
                    <Td align="right">
                      <Pct value={t.return_pct ?? null} />
                    </Td>
                    <Td align="right">{toNum(t.holding_sessions) === null ? <NAValue /> : `${int(t.holding_sessions)}d`}</Td>
                    <Td className="whitespace-nowrap text-xs text-muted">{t.exit_reason ? titleCase(t.exit_reason) : <NAValue />}</Td>
                  </Tr>
                ))}
              </tbody>
            </TableWrap>
            {filteredTrades.length > MAX_TRADE_ROWS ? (
              <p className="border-t border-border px-4 py-2 text-xs text-muted">
                Showing the first {int(MAX_TRADE_ROWS)} of {int(filteredTrades.length)} trades.
              </p>
            ) : null}
            {filteredTrades.length === 0 ? <p className="px-4 py-3 text-xs text-muted">No trades in this split.</p> : null}
          </>
        )}
      </Card>
    </div>
  );
}
