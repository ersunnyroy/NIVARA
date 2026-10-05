"use client";

import Link from "next/link";
import { usePerformance } from "@/lib/hooks";
import { int } from "@/lib/format";
import { Badge, Card, CardBody, CardHeader, DataStamp, Disclaimer, EmptyState, QueryState, SkeletonCard, type BadgeTone } from "@/components/ui";
import { PageHeader } from "@/components/layout/PageHeader";
import { EquityCurve, SignedBars } from "@/components/charts/svg";
import { BacktestMetricsTable, normaliseMetrics } from "../backtesting/_components/metrics";
import { asPerf, hasTrades, monthLabel, PerfStatGrid, type PerfStatsX } from "./_components/perf";

type KindKey = "live" | "paper" | "backtest" | "system" | "user";

const KINDS: { key: KindKey; label: string; tone: BadgeTone; title: string; subtitle: string; empty: React.ReactNode; optional?: boolean }[] = [
  {
    key: "live",
    label: "LIVE",
    tone: "up",
    title: "Live performance",
    subtitle: "Your real trades with real money — from the trade journal and realised lots in your live portfolios.",
    empty: (
      <>
        Log closed trades in the <Link className="text-accent hover:underline" href="/trades">trade journal</Link> (kind “live”) or record BUY/SELL
        transactions in a live portfolio. Statistics appear once at least one trade is closed.
      </>
    ),
  },
  {
    key: "paper",
    label: "PAPER",
    tone: "violet",
    title: "Paper trading performance",
    subtitle: "Simulated fills on real end-of-day prices. No real orders were placed.",
    empty: (
      <>
        Place orders on the <Link className="text-accent hover:underline" href="/paper">paper trading</Link> page. Orders fill against the next
        session’s official EOD bar; stats appear once a paper trade closes.
      </>
    ),
  },
  {
    key: "backtest",
    label: "BACKTEST",
    tone: "warn",
    title: "Backtest performance (simulated)",
    subtitle: "Historical simulation of a strategy. Past simulated results do not guarantee future returns.",
    empty: (
      <>
        Run a backtest on the <Link className="text-accent hover:underline" href="/backtesting">backtesting</Link> page. The most recent completed run
        is summarised here.
      </>
    ),
  },
  {
    key: "system",
    label: "SYSTEM",
    tone: "info",
    title: "Model recommendations (system)",
    subtitle: "Recommendations auto-followed in the model paper portfolio — how the model itself would have done.",
    empty: (
      <>
        Enable “follow model” on the <Link className="text-accent hover:underline" href="/paper">paper trading</Link> page. The model portfolio then
        paper-trades every BUY recommendation; stats appear once those trades close.
      </>
    ),
    optional: true,
  },
  {
    key: "user",
    label: "USER",
    tone: "neutral",
    title: "User-tagged trades",
    subtitle: "Trades you logged in the journal with kind “user”.",
    empty: <>Log trades with kind “user” in the trade journal.</>,
    optional: true,
  },
];

function lastDate(s: PerfStatsX): string | null {
  const c = s.equity_curve;
  return c && c.length ? c[c.length - 1].date : null;
}

function StatsBody({ stats, fallbackAsOf }: { stats: PerfStatsX; fallbackAsOf?: string | null }) {
  const asOf = stats.data_as_of ?? fallbackAsOf ?? null;
  const through = lastDate(stats);
  const monthly = (stats.monthly ?? []).map((m) => ({ label: monthLabel(m.month), value: m.pnl }));
  const note = stats.note ?? stats.ratios_note;
  return (
    <div className="space-y-4">
      <PerfStatGrid stats={stats} />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Equity curve</h3>
          <EquityCurve points={stats.equity_curve ?? []} height={200} />
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Monthly net P&amp;L</h3>
          <SignedBars data={monthly} height={200} label="Monthly net P&L" />
        </div>
      </div>
      {note ? <p className="text-xs text-muted">{note}</p> : null}
      {asOf ? (
        <DataStamp asOf={asOf} source={stats.source ?? null} />
      ) : through ? (
        <DataStamp label="Through last closed trade" asOf={through} source={stats.source ?? null} />
      ) : (
        <DataStamp asOf={null} source={stats.source ?? null} />
      )}
    </div>
  );
}

function BacktestBody({ stats, fallbackAsOf }: { stats: PerfStatsX; fallbackAsOf?: string | null }) {
  const metrics = normaliseMetrics(stats.metrics);
  const hasMetrics = Object.keys(metrics).length > 0;
  return (
    <div className="space-y-4">
      {stats.name || stats.backtest_id != null ? (
        <p className="text-sm">
          Latest completed run:{" "}
          {stats.backtest_id != null ? (
            <Link href="/backtesting" className="font-medium text-accent hover:underline">
              {stats.name ?? `Backtest #${stats.backtest_id}`}
            </Link>
          ) : (
            <span className="font-medium">{stats.name}</span>
          )}
        </p>
      ) : null}
      {hasMetrics ? <BacktestMetricsTable metrics={metrics} label="Latest backtest metrics" /> : null}
      {hasTrades(stats) ? <StatsBody stats={stats} fallbackAsOf={fallbackAsOf} /> : null}
      {!hasMetrics && !hasTrades(stats) ? <p className="text-xs text-muted">The latest backtest reported no metrics.</p> : null}
    </div>
  );
}

export default function PerformancePage() {
  const q = usePerformance();
  return (
    <div>
      <PageHeader
        title="Performance"
        description="Live, paper, backtest and model results are kept strictly separate — they are never mixed into one number."
      />
      <QueryState
        query={q}
        skeleton={
          <div className="space-y-4">
            <SkeletonCard lines={5} />
            <SkeletonCard lines={5} />
            <SkeletonCard lines={5} />
          </div>
        }
      >
        {(data) => {
          const kinds = (data.kinds ?? {}) as Record<string, unknown>;
          const labels = ((data as { labels?: Record<string, string> }).labels ?? {}) as Record<string, string>;
          const liveRealized = asPerf(kinds.live_realized);
          return (
            <div className="space-y-4">
              {KINDS.map((k) => {
                const stats = asPerf(kinds[k.key]);
                if (k.optional && !stats) return null;
                const isBacktest = k.key === "backtest";
                const populated = isBacktest ? !!stats && (Object.keys(normaliseMetrics(stats.metrics)).length > 0 || hasTrades(stats)) : hasTrades(stats);
                const showRealized = k.key === "live" && hasTrades(liveRealized);
                return (
                  <Card key={k.key} aria-labelledby={`perf-${k.key}`} className={isBacktest ? "border-warn/40" : undefined}>
                    <CardHeader
                      title={
                        <span id={`perf-${k.key}`} className="flex flex-wrap items-center gap-2">
                          <Badge tone={k.tone}>{k.label}</Badge>
                          {labels[k.key] ?? k.title}
                        </span>
                      }
                      subtitle={k.subtitle}
                      actions={stats && hasTrades(stats) ? <span className="text-xs text-muted">{int(stats.total_trades)} closed trades</span> : null}
                    />
                    <CardBody className="space-y-4">
                      {isBacktest ? (
                        <Disclaimer tone="warn">
                          BACKTEST PERFORMANCE — past simulated results do not guarantee future returns.
                          {stats?.note ? ` ${stats.note}` : ""}
                        </Disclaimer>
                      ) : null}
                      {k.key === "paper" || k.key === "system" ? (
                        <p className="text-xs text-muted">Simulated — fills are modelled on official end-of-day prices; no real orders were placed.</p>
                      ) : null}
                      {populated && stats ? (
                        isBacktest ? (
                          <BacktestBody stats={stats} fallbackAsOf={data.data_as_of} />
                        ) : (
                          <StatsBody stats={stats} fallbackAsOf={data.data_as_of} />
                        )
                      ) : !showRealized ? (
                        <EmptyState compact title={stats ? "No closed trades yet" : "No data yet"}>
                          {k.empty}
                        </EmptyState>
                      ) : null}
                      {showRealized && liveRealized ? (
                        <div className="space-y-3 border-t border-border pt-4">
                          <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                            <Badge tone="up" size="xs">
                              LIVE
                            </Badge>
                            {labels.live_realized ?? "Realised from your live portfolio transactions"}
                          </h3>
                          <p className="text-xs text-muted">FIFO-matched lots: after charges, before income tax.</p>
                          <StatsBody stats={liveRealized} fallbackAsOf={data.data_as_of} />
                        </div>
                      ) : null}
                    </CardBody>
                  </Card>
                );
              })}
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}
