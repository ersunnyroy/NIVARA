"use client";

import { Plug } from "lucide-react";
import { useDataSources, useSaveDataSources, useSystemHealth } from "@/lib/hooks";
import { dateTimeIST, titleCase } from "@/lib/format";
import type { DataSource } from "@/lib/types";
import { Badge, Card, CardHeader, Checkbox, EmptyState, NAValue, QueryState, SkeletonRows, TableWrap, Td, Th, THead, Tr } from "@/components/ui";
import { StatusDot } from "./shared";

/** Backend row(DataSource) fields: `is_enabled` (not `enabled`), provider, requires_credentials, freshness_sla_minutes, ... */
type DataSourceX = DataSource & {
  provider?: string | null;
  is_enabled?: boolean;
  requires_credentials?: boolean;
  configured?: boolean | null;
  freshness_sla_minutes?: number | null;
  last_success_at?: string | null;
  last_data_as_of?: string | null;
  last_error_at?: string | null;
  last_error?: string | null;
  terms_note?: string | null;
};

function enabledOf(s: DataSourceX): boolean | null {
  if (typeof s.is_enabled === "boolean") return s.is_enabled;
  if (typeof s.enabled === "boolean") return s.enabled;
  return null;
}

function EnabledToggle({ s }: { s: DataSourceX }) {
  const save = useSaveDataSources();
  const on = enabledOf(s);
  if (on === null) return <NAValue />;
  // Optimistic display while the PUT is in flight.
  const shown = save.isPending && typeof save.variables?.body.is_enabled === "boolean" ? (save.variables.body.is_enabled as boolean) : on;
  return (
    <div className="flex flex-col gap-1">
      <Checkbox
        label={<span className="text-xs">{shown ? "Enabled" : "Disabled"}</span>}
        checked={shown}
        disabled={save.isPending}
        onChange={(v) => save.mutate({ key: s.key, body: { is_enabled: v } })}
      />
      {save.error ? (
        <span role="alert" className="text-[11px] text-down">
          {save.error.message}
        </span>
      ) : null}
    </div>
  );
}

function Credentials({ s }: { s: DataSourceX }) {
  const req = s.required_env ?? [];
  const missing = s.missing_env;
  if (!req.length && !s.requires_credentials) return <span className="text-xs text-muted">None required</span>;
  return (
    <div className="space-y-1 text-xs">
      {s.configured === true ? (
        <Badge tone="up" size="xs">
          Configured
        </Badge>
      ) : s.configured === false ? (
        <Badge tone="down" size="xs">
          Not configured
        </Badge>
      ) : (
        <Badge tone="outline" size="xs">
          Unknown
        </Badge>
      )}
      {req.length ? (
        <p className="text-muted">
          Env:{" "}
          {req.map((e) => (
            <code key={e} className="mr-1 rounded bg-surface-2 px-1 text-[10px] text-fg/80">
              {e}
            </code>
          ))}
        </p>
      ) : null}
      {missing?.length ? (
        <p className="text-down">
          Missing:{" "}
          {missing.map((e) => (
            <code key={e} className="mr-1 text-[10px]">
              {e}
            </code>
          ))}
        </p>
      ) : s.configured === false && req.length ? (
        <p className="text-down">Set the variable(s) above in the backend environment and restart.</p>
      ) : null}
    </div>
  );
}

export function DataProviders() {
  const q = useDataSources(true);
  const health = useSystemHealth(true);
  const statusByKey = new Map((health.data?.components ?? []).map((c) => [c.key, c.status]));

  return (
    <Card>
      <CardHeader
        icon={<Plug className="size-4" />}
        title="Data providers"
        subtitle="Enable or disable sources. Only environment-variable names are shown — secret values are never displayed."
      />
      <QueryState query={q} skeleton={<div className="p-4"><SkeletonRows rows={6} /></div>} className="m-4">
        {(rows) => {
          const list = rows as DataSourceX[];
          if (!list.length)
            return (
              <EmptyState compact title="No data sources registered">
                Run the <strong>Seed reference data</strong> job in the Jobs tab to register the default providers.
              </EmptyState>
            );
          return (
            <TableWrap label="Data providers">
              <THead>
                <tr>
                  <Th>Source</Th>
                  <Th>Kind</Th>
                  <Th>Enabled</Th>
                  <Th>Credentials</Th>
                  <Th>Status</Th>
                  <Th>Last success</Th>
                  <Th>Data as of</Th>
                  <Th>Last error</Th>
                </tr>
              </THead>
              <tbody>
                {list.map((s) => (
                  <Tr key={s.key}>
                    <Td className="min-w-48">
                      <span className="block font-medium">{s.name ?? s.key}</span>
                      <code className="text-[10px] text-subtle">{s.key}</code>
                      {s.provider ? <span className="block text-[11px] text-muted">{s.provider}</span> : null}
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{s.kind ? titleCase(s.kind) : <NAValue />}</Td>
                    <Td>
                      <EnabledToggle s={s} />
                    </Td>
                    <Td className="min-w-44">
                      <Credentials s={s} />
                    </Td>
                    <Td>
                      <StatusDot status={(s.status as string | undefined) ?? statusByKey.get(s.key) ?? null} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{s.last_success_at ? dateTimeIST(s.last_success_at) : <span className="text-muted">Never</span>}</Td>
                    <Td className="whitespace-nowrap text-xs">{s.last_data_as_of ? dateTimeIST(s.last_data_as_of) : <NAValue />}</Td>
                    <Td className="max-w-72 text-xs">
                      {s.last_error ? (
                        <span className="line-clamp-3 break-words text-down" title={s.last_error}>
                          {s.last_error}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </TableWrap>
          );
        }}
      </QueryState>
    </Card>
  );
}
