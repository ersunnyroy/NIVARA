"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { useBacktests } from "@/lib/hooks";
import { dateIST, dateTimeIST, titleCase } from "@/lib/format";
import { Card, CardBody, CardHeader, EmptyState, ErrorState, SkeletonRows, cn } from "@/components/ui";
import { PageHeader } from "@/components/layout/PageHeader";
import { BacktestBanner } from "./_components/metrics";
import { BacktestStatusBadge } from "./_components/status";
import { CreateBacktestForm } from "./_components/CreateBacktestForm";
import { BacktestDetailView } from "./_components/BacktestDetailView";

export default function BacktestingPage() {
  const list = useBacktests();
  const [picked, setPicked] = useState<number | null>(null);
  const items = list.data ?? [];
  // Derived selection: explicit pick, otherwise the most recent run.
  const selected = picked ?? items[0]?.id ?? null;

  return (
    <div>
      <PageHeader
        title="Backtesting"
        description="Simulate a strategy on historical EOD data with charges and slippage, split into train / validation / out-of-sample test."
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader title="New backtest" icon={<FlaskConical className="size-4" />} />
            <CardBody>
              <CreateBacktestForm onCreated={setPicked} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Your backtests" subtitle="Queued and running jobs refresh automatically." />
            {list.isPending ? (
              <CardBody>
                <SkeletonRows rows={4} />
              </CardBody>
            ) : list.isError ? (
              <CardBody>
                <ErrorState error={list.error} onRetry={() => list.refetch()} />
              </CardBody>
            ) : items.length === 0 ? (
              <EmptyState compact title="No backtests yet">
                Fill in the form above to run your first backtest. It needs stored EOD history covering the chosen period (an admin can backfill it from
                Settings → Jobs).
              </EmptyState>
            ) : (
              <ul className="max-h-[28rem] divide-y divide-border overflow-y-auto" aria-label="Backtests">
                {items.map((b) => {
                  const sel = b.id === selected;
                  return (
                    <li key={b.id}>
                      <button
                        type="button"
                        aria-pressed={sel}
                        onClick={() => setPicked(b.id)}
                        className={cn(
                          "flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2",
                          sel && "bg-accent-soft/60 hover:bg-accent-soft",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{b.name ?? `Backtest #${b.id}`}</span>
                          <span className="block truncate text-xs text-muted">
                            {titleCase(b.strategy)} · {dateIST(b.start_date)} → {dateIST(b.end_date)}
                          </span>
                          <span className="block text-[11px] text-subtle">Created {dateTimeIST(b.created_at ?? null)}</span>
                        </span>
                        <BacktestStatusBadge status={b.status} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <div className="min-w-0">
          {selected !== null ? (
            <BacktestDetailView key={selected} id={selected} onDeleted={() => setPicked(null)} />
          ) : (
            <div className="space-y-4">
              <BacktestBanner />
              <Card>
                <EmptyState title="No backtest selected">Run a backtest or pick one from the list to see its metrics, equity curve and trades.</EmptyState>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
