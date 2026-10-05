"use client";

import { Activity, ArrowDownUp, BarChart3, CalendarClock, Landmark, PieChart } from "lucide-react";
import { useMarketOverview, useMarketStatus } from "@/lib/hooks";
import { dateIST, dateTimeIST, titleCase } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import { BreadthPanel, FlowsTable, IndicesStrip, MoversTable, SectorTable } from "@/components/domain/market";
import { RegimeCard } from "@/components/domain/RegimeCard";
import {
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  DataStatusBanner,
  ErrorState,
  QueryState,
  SkeletonCard,
  SkeletonRows,
  Stat,
} from "@/components/ui";

function StatusCard() {
  const q = useMarketStatus();
  return (
    <Card>
      <CardHeader icon={<CalendarClock className="size-4" />} title="Market calendar & data freshness" />
      <CardBody>
        <QueryState query={q} skeleton={<SkeletonRows rows={2} />}>
          {(s) => {
            const fresh = s.data_freshness ?? s.freshness;
            return (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat size="sm" label="Phase" value={s.label ?? titleCase(s.phase)} sub={s.holiday_name ?? undefined} />
                  <Stat size="sm" label="Last completed EOD session" value={dateIST(s.last_completed_eod_session)} />
                  <Stat size="sm" label="Ideas target session" value={dateIST(s.target_session)} />
                  <Stat
                    size="sm"
                    label="EOD data in database"
                    value={s.data ? (s.data.last_eod_date ? dateIST(s.data.last_eod_date) : "none") : fresh?.status ? titleCase(fresh.status) : "n/a"}
                    tone={s.data ? (s.data.is_current ? "up" : "warn") : fresh?.status === "ok" ? "up" : "na"}
                    sub={
                      s.data
                        ? s.data.is_current
                          ? "current"
                          : s.data.last_eod_date
                            ? `${s.data.sessions_behind ?? "?"} session(s) behind`
                            : "not ingested yet"
                        : undefined
                    }
                  />
                </div>
                {s.data && !s.data.last_eod_date ? (
                  <DataStatusBanner status="data_unavailable" message="No EOD bars have been ingested yet." hint="An admin can run the EOD ingestion / backfill from Settings → Jobs." />
                ) : s.data && s.data.is_current === false ? (
                  <DataStatusBanner status="data_stale" message={`Latest EOD data is ${s.data.sessions_behind ?? "some"} session(s) behind the last completed session. New recommendations are withheld until data catches up.`} />
                ) : fresh?.status && fresh.status !== "ok" ? (
                  <DataStatusBanner status={fresh.status} message={fresh.message ?? undefined} />
                ) : null}
                <p className="text-[11px] text-muted">
                  Now: {s.now_ist ? dateTimeIST(s.now_ist) : "n/a"} · NSE session {s.hours?.open ?? "09:15"}–{s.hours?.close ?? "15:30"} IST
                  {s.data ? ` · real-time quotes ${s.data.realtime_quotes ? "enabled" : "not configured"}` : ""} · EOD data is typically ready after the close; prices on this site are EOD closes unless marked Live.
                </p>
              </div>
            );
          }}
        </QueryState>
      </CardBody>
    </Card>
  );
}

export default function MarketPage() {
  const q = useMarketOverview();
  const ov = q.data;
  return (
    <div className="space-y-4">
      <PageHeader title="Market" description="Regime, breadth, institutional flows, sectors and movers — from end-of-day data." />
      <StatusCard />

      {q.isPending ? (
        <SkeletonCard lines={6} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} unavailableHint="An admin can run the EOD ingestion from Settings → Jobs." />
      ) : (
        <>
          {ov?.status && ov.status !== "ok" ? <DataStatusBanner status={ov.status} message={ov.message ?? undefined} /> : null}
          <Card>
            <CardHeader icon={<Landmark className="size-4" />} title="Indices" />
            <CardBody>
              <IndicesStrip indices={ov?.indices} />
              <DataStamp className="mt-2" asOf={ov?.data_as_of} kind="eod_close" source={ov?.source ?? "NSE indices"} />
            </CardBody>
          </Card>

          <RegimeCard regime={ov?.regime} />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader icon={<Activity className="size-4" />} title="Breadth" subtitle={ov?.breadth?.date ? `Session ${dateIST(ov.breadth.date)}` : undefined} />
              <CardBody>
                <BreadthPanel breadth={ov?.breadth} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader icon={<ArrowDownUp className="size-4" />} title="FII / DII flows" subtitle="Cash market, ₹ crore (provisional figures as published)" />
              <FlowsTable rows={ov?.flows} />
            </Card>
          </div>

          <Card>
            <CardHeader icon={<PieChart className="size-4" />} title="Sector strength" subtitle="Rank combines 1W/1M/3M returns and relative strength vs Nifty 50" />
            <SectorTable rows={ov?.sectors} />
            <DataStamp className="px-4 py-2" asOf={ov?.data_as_of} source="NSE sector indices" />
          </Card>

          <div className="grid gap-4 xl:grid-cols-3">
            {(
              [
                ["gainers", "Top gainers"],
                ["losers", "Top losers"],
                ["most_active", "Most active (value)"],
              ] as const
            ).map(([k, label]) => (
              <Card key={k}>
                <CardHeader icon={<BarChart3 className="size-4" />} title={label} />
                <MoversTable rows={ov?.movers?.[k]} showVolume={k === "most_active"} />
                <DataStamp className="px-4 py-2" asOf={ov?.data_as_of} kind="eod_close" />
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
