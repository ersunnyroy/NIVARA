"use client";

import { useState } from "react";
import { BellRing, Briefcase, LineChart, Newspaper, PieChart, Target, Trophy } from "lucide-react";
import {
  useMarketOverview,
  useNews,
  useOpportunities,
  usePortfolioDashboard,
  useTrackRecord,
} from "@/lib/hooks";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActionList } from "@/components/domain/ActionList";
import { MoversSwitch, MoversTable, SectorTable, type MoverTab } from "@/components/domain/market";
import { NewsList } from "@/components/domain/News";
import { OpportunitiesBlock } from "@/components/domain/OpportunitiesBlock";
import { PortfolioSummaryTiles } from "@/components/domain/PortfolioSummary";
import { RegimeCard } from "@/components/domain/RegimeCard";
import { TrackRecordStats } from "@/components/domain/TrackRecord";
import { Card, CardBody, CardHeader, DataStamp, EmptyState, ErrorState, SkeletonCard, SkeletonRows } from "@/components/ui";

export default function DashboardPage() {
  const overview = useMarketOverview();
  const opps = useOpportunities();
  const pf = usePortfolioDashboard();
  const news = useNews({ limit: 6 });
  const tr = useTrackRecord();
  const [mover, setMover] = useState<MoverTab>("gainers");

  const ov = overview.data;
  const hasPortfolio = (pf.data?.portfolios?.length ?? 0) > 0;

  return (
    <div className="space-y-4">
      <PageHeader title="Dashboard" description="Market context first, then ideas, then your money. Decision support — not advice." />

      {/* 1. Market regime */}
      {overview.isPending ? (
        <SkeletonCard lines={3} />
      ) : overview.isError ? (
        <Card>
          <CardHeader title="Market regime" />
          <CardBody>
            <ErrorState error={overview.error} onRetry={() => overview.refetch()} unavailableHint="An admin can run the EOD ingestion from Settings → Jobs." />
          </CardBody>
        </Card>
      ) : (
        <RegimeCard regime={ov?.regime} compact />
      )}

      {/* 2. Top 10 opportunities */}
      <Card>
        <CardHeader icon={<Target className="size-4" />} title="Top 10 opportunities" subtitle="Ranked by the NIVARA score after liquidity, data-quality and risk filters" href="/opportunities" />
        <OpportunitiesBlock query={opps} limit={10} />
      </Card>

      {/* 3 & 4. Portfolio summary + Action required */}
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader icon={<Briefcase className="size-4" />} title="My portfolio" subtitle="Gross and net shown together; tax is an estimate" href="/portfolio" />
          <CardBody>
            {pf.isPending ? (
              <SkeletonRows rows={2} />
            ) : pf.isError ? (
              <ErrorState error={pf.error} onRetry={() => pf.refetch()} />
            ) : !hasPortfolio ? (
              <EmptyState compact title="No portfolio yet">
                Create a portfolio and add your buy transactions under Portfolio to see invested, P&amp;L after charges and estimated tax.
              </EmptyState>
            ) : (
              <>
                <PortfolioSummaryTiles summary={pf.data.summary} dense />
                <DataStamp className="mt-3" asOf={pf.data.data_as_of ?? pf.data.summary?.data_as_of} kind="eod_close" label="Prices as of" />
              </>
            )}
          </CardBody>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader icon={<BellRing className="size-4" />} title="Action required" subtitle="Hold / trail / exit signals on your holdings" href="/portfolio#exits" />
          {pf.isPending ? (
            <SkeletonRows rows={3} className="p-4" />
          ) : pf.isError ? (
            <div className="p-4"><ErrorState error={pf.error} /></div>
          ) : (
            <ActionList items={pf.data.actions ?? []} limit={6} />
          )}
        </Card>
      </div>

      {/* 5 & 6. Movers + sectors */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            icon={<LineChart className="size-4" />}
            title="Market movers"
            href="/market"
            actions={<MoversSwitch value={mover} onChange={setMover} />}
          />
          {overview.isPending ? (
            <SkeletonRows rows={5} className="p-4" />
          ) : overview.isError ? (
            <div className="p-4"><ErrorState error={overview.error} /></div>
          ) : (
            <>
              <MoversTable rows={ov?.movers?.[mover]?.slice(0, 6)} showVolume={mover === "most_active"} />
              <DataStamp className="px-4 py-2" asOf={ov?.data_as_of} kind="eod_close" source={ov?.source ?? "NSE EOD"} />
            </>
          )}
        </Card>
        <Card>
          <CardHeader icon={<PieChart className="size-4" />} title="Sector performance" subtitle="Ranked by relative strength vs Nifty 50" href="/market" />
          {overview.isPending ? (
            <SkeletonRows rows={5} className="p-4" />
          ) : overview.isError ? (
            <div className="p-4"><ErrorState error={overview.error} /></div>
          ) : (
            <>
              <SectorTable rows={ov?.sectors} limit={6} />
              <DataStamp className="px-4 py-2" asOf={ov?.data_as_of} source="NSE sector indices" />
            </>
          )}
        </Card>
      </div>

      {/* 7 & 8. News + track record */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader icon={<Newspaper className="size-4" />} title="News" subtitle="Unverified sources are labelled" href="/news" />
          {news.isPending ? (
            <SkeletonRows rows={4} className="p-4" />
          ) : news.isError ? (
            <div className="p-4"><ErrorState error={news.error} /></div>
          ) : (
            <NewsList items={news.data} compact limit={5} />
          )}
        </Card>
        <Card>
          <CardHeader icon={<Trophy className="size-4" />} title="Recommendation performance" subtitle="How past ideas actually played out" href="/recommendations" />
          <CardBody>
            {tr.isPending ? <SkeletonRows rows={2} /> : tr.isError ? <ErrorState error={tr.error} /> : <TrackRecordStats tr={tr.data} compact />}
            {tr.data?.data_as_of ? <DataStamp className="mt-3" asOf={tr.data.data_as_of} /> : null}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
