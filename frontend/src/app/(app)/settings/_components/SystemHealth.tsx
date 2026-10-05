"use client";

import { Activity, Cpu, Database, History } from "lucide-react";
import { useSystemHealth } from "@/lib/hooks";
import { dateTimeIST, int, titleCase } from "@/lib/format";
import type { HealthComponent, IngestionRun, SystemHealth as SystemHealthT } from "@/lib/types";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  EmptyState,
  ErrorState,
  NAValue,
  SkeletonCard,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { fetchedAt, isPlainObject, KV, StatusDot } from "./shared";

type ComponentX = HealthComponent & { provider?: string | null; last_error_at?: string | null; requires_credentials?: boolean; configured?: boolean | null };
type RunX = IngestionRun & { details?: Record<string, unknown> | null };
type HealthX = Omit<SystemHealthT, "components" | "ingestion_runs"> & {
  summary?: Record<string, string>;
  calendar?: Record<string, unknown>;
  components?: ComponentX[];
  ingestion_runs?: RunX[];
};

export function SystemHealth({ gotoJobs }: { gotoJobs: () => void }) {
  const q = useSystemHealth(true);
  if (q.isPending)
    return (
      <div className="space-y-4">
        <SkeletonCard lines={3} />
        <SkeletonCard lines={6} />
      </div>
    );
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const h = q.data as HealthX;
  const comps = h.components ?? [];
  const runs = h.ingestion_runs ?? [];
  const summary = Object.entries(h.summary ?? {});
  const jobsBtn = (
    <Button size="sm" variant="outline" onClick={gotoJobs}>
      Open Jobs
    </Button>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<Activity className="size-4" />}
          title="Overview"
          subtitle={
            <>
              {h.checked_at ? <DataStamp asOf={h.checked_at} label="Checked" /> : <span>Fetched {fetchedAt(q.dataUpdatedAt)} · refreshes every minute</span>}
            </>
          }
          actions={
            <Button size="xs" variant="outline" loading={q.isFetching} onClick={() => q.refetch()}>
              Refresh
            </Button>
          }
        />
        <CardBody>
          {summary.length ? (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {summary.map(([k, v]) => (
                <li key={k} className="rounded-lg border border-border p-2.5">
                  <p className="truncate text-[11px] font-medium uppercase tracking-wide text-muted">{k}</p>
                  <StatusDot status={v} className="mt-1" />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">No component summary reported.</p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Components" subtitle="GREEN = fresh within SLA · YELLOW = stale or recent error · RED = failing · DISABLED = off or missing credentials" />
        {comps.length === 0 ? (
          <CardBody>
            <EmptyState compact title="No data sources registered yet" action={jobsBtn}>
              Run the <strong>Seed reference data</strong> job, then Securities, Holidays and EOD ingestion.
            </EmptyState>
          </CardBody>
        ) : (
          <TableWrap label="Health components">
            <THead>
              <tr>
                <Th>Component</Th>
                <Th>Status</Th>
                <Th>Last success</Th>
                <Th>Last data as of</Th>
                <Th align="right">SLA</Th>
                <Th>Last error</Th>
              </tr>
            </THead>
            <tbody>
              {comps.map((c) => (
                <Tr key={c.key}>
                  <Td className="min-w-44">
                    <span className="block font-medium">{c.name ?? c.key}</span>
                    <span className="text-[11px] text-muted">
                      {c.kind ? titleCase(c.kind) : ""}
                      {c.provider ? ` · ${c.provider}` : ""}
                    </span>
                  </Td>
                  <Td>
                    <StatusDot status={c.status} />
                    {c.requires_credentials && c.configured === false ? <span className="block text-[11px] text-muted">credentials missing</span> : null}
                  </Td>
                  <Td className="whitespace-nowrap text-xs">{c.last_success_at ? dateTimeIST(c.last_success_at) : <span className="text-muted">Never</span>}</Td>
                  <Td className="whitespace-nowrap text-xs">{c.last_data_as_of ? dateTimeIST(c.last_data_as_of) : <NAValue />}</Td>
                  <Td align="right" className="text-xs">
                    {c.sla_minutes == null ? <NAValue /> : c.sla_minutes >= 120 ? `${int(c.sla_minutes / 60)} h` : `${int(c.sla_minutes)} min`}
                  </Td>
                  <Td className="max-w-80 text-xs">
                    {c.last_error ? (
                      <span className="line-clamp-3 break-words text-down" title={c.last_error}>
                        {c.last_error}
                        {c.last_error_at ? <span className="block text-muted">{dateTimeIST(c.last_error_at)}</span> : null}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader icon={<Cpu className="size-4" />} title="Workers" />
          <CardBody>
            <KV data={isPlainObject(h.workers) ? h.workers : null} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader icon={<Database className="size-4" />} title="Database" />
          <CardBody>
            <KV data={isPlainObject(h.database) ? h.database : null} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Market calendar" />
          <CardBody>
            <KV data={isPlainObject(h.calendar) ? h.calendar : null} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader icon={<History className="size-4" />} title="Recent ingestion runs" subtitle="Latest 40 runs, newest first." />
        {runs.length === 0 ? (
          <CardBody>
            <EmptyState compact title="No market data yet" action={jobsBtn}>
              No ingestion has run. Run Securities, Holidays, then <strong>EOD ingestion</strong> (or a Backfill) from the Jobs tab.
            </EmptyState>
          </CardBody>
        ) : (
          <TableWrap label="Ingestion runs">
            <THead>
              <tr>
                <Th>Job</Th>
                <Th>Status</Th>
                <Th>Started</Th>
                <Th>Finished</Th>
                <Th align="right">Rows</Th>
                <Th>Error / details</Th>
              </tr>
            </THead>
            <tbody>
              {runs.map((r, i) => {
                const rows = r.rows ?? r.rows_written;
                const details = isPlainObject(r.details) && Object.keys(r.details).length ? r.details : null;
                return (
                  <Tr key={r.id ?? i}>
                    <Td className="font-medium">
                      {r.job ?? r.source ?? <NAValue />}
                      {r.target_date ? <span className="block text-[11px] text-muted">{r.target_date}</span> : null}
                    </Td>
                    <Td>
                      <StatusDot status={r.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{r.started_at ? dateTimeIST(r.started_at) : <NAValue />}</Td>
                    <Td className="whitespace-nowrap text-xs">{r.finished_at ? dateTimeIST(r.finished_at) : <span className="text-muted">—</span>}</Td>
                    <Td align="right">{rows == null ? <NAValue /> : int(rows)}</Td>
                    <Td className="max-w-96 text-xs">
                      {r.error ? (
                        <span className="line-clamp-3 break-words text-down" title={r.error}>
                          {r.error}
                        </span>
                      ) : r.message ? (
                        <span className="text-fg/80">{r.message}</span>
                      ) : null}
                      {details ? (
                        <details className="mt-0.5">
                          <summary className="cursor-pointer text-muted">Details</summary>
                          <pre className="scroll-thin mt-1 max-h-48 overflow-auto rounded bg-surface-2 p-2 text-[10px]">{JSON.stringify(details, null, 2)}</pre>
                        </details>
                      ) : !r.error && !r.message ? (
                        <span className="text-muted">—</span>
                      ) : null}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </TableWrap>
        )}
      </Card>
    </div>
  );
}
