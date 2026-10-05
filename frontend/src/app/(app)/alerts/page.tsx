"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, BellRing, CheckCheck, Check, ListChecks, Trash2 } from "lucide-react";
import { api, asList, type ApiError } from "@/lib/api";
import { useAlertEvents, useDeleteAlert, useMarkAlertRead } from "@/lib/hooks";
import { dateTimeIST, inr, titleCase } from "@/lib/format";
import type { AlertEvent, AlertRule, PriceKind } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  cn,
  DataStamp,
  Dialog,
  EmptyState,
  ErrorState,
  NAValue,
  Segmented,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { CreateAlertForm } from "./_components/CreateAlertForm";
import { alertLabel } from "./_components/alertTypes";

type RuleX = AlertRule & { cooldown_minutes?: number | null };
type EventX = AlertEvent & { data?: Record<string, unknown> | null };

/**
 * GET /alerts returns `{ types: string[], alerts: AlertRule[] }`; the shared `useAlerts` hook unwraps with
 * `asList`, which does not look at the `alerts` key — so this page reads the envelope itself.
 * The key lives under ["alerts"] so create/delete mutations still invalidate it.
 */
function useAlertRules() {
  return useQuery<{ types: string[]; alerts: RuleX[] }, ApiError>({
    queryKey: ["alerts", "rules", "envelope"],
    queryFn: async ({ signal }) => {
      const r = await api.get<unknown>("/alerts", undefined, signal);
      const types = r && typeof r === "object" && !Array.isArray(r) && Array.isArray((r as { types?: unknown }).types) ? ((r as { types: string[] }).types) : [];
      return { types, alerts: asList<RuleX>(r, "alerts") };
    },
  });
}

function paramText(k: string, v: unknown): string {
  if (typeof v === "number") {
    if (["level", "entry_low", "entry_high", "stop", "target"].includes(k)) return `${titleCase(k)} ${inr(v)}`;
    if (k === "pct") return `Move ≥ ${v}%`;
    if (k === "points") return `Δ ≥ ${v} pts`;
    if (k === "multiple") return `Volume ≥ ${v}×`;
  }
  return `${titleCase(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`;
}

function cooldownText(m?: number | null): string | null {
  if (m == null) return null;
  return m % 60 === 0 ? `${m / 60}h cooldown` : `${m}m cooldown`;
}

function RulesCard({ rules }: { rules: RuleX[] }) {
  const del = useDeleteAlert();
  const [confirm, setConfirm] = useState<RuleX | null>(null);

  return (
    <Card>
      <CardHeader icon={<ListChecks className="size-4" />} title="Alert rules" subtitle={`${rules.length} rule${rules.length === 1 ? "" : "s"}`} />
      {rules.length === 0 ? (
        <CardBody>
          <EmptyState compact title="No alert rules yet">
            Create a rule with the form — e.g. “Price crosses above” for a breakout level, or “Market regime change”.
          </EmptyState>
        </CardBody>
      ) : (
        <TableWrap label="Alert rules">
          <THead>
            <tr>
              <Th>Symbol</Th>
              <Th>Type</Th>
              <Th>Parameters</Th>
              <Th>Channels</Th>
              <Th>Status</Th>
              <Th>Last triggered</Th>
              <Th align="right">
                <span className="sr-only">Actions</span>
              </Th>
            </tr>
          </THead>
          <tbody>
            {rules.map((r) => {
              const params = Object.entries(r.params ?? {});
              return (
                <Tr key={r.id}>
                  <Td className="font-semibold">
                    {r.symbol ? (
                      <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-accent hover:underline">
                        {r.symbol}
                      </Link>
                    ) : (
                      <span className="text-muted">Market</span>
                    )}
                  </Td>
                  <Td>{alertLabel(r.alert_type)}</Td>
                  <Td className="text-xs">
                    {params.length ? params.map(([k, v]) => <span key={k} className="mr-2 inline-block">{paramText(k, v)}</span>) : <span className="text-muted">Defaults</span>}
                    {cooldownText(r.cooldown_minutes) ? <span className="block text-[11px] text-muted">{cooldownText(r.cooldown_minutes)}</span> : null}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {(r.channels ?? []).length ? (
                        (r.channels ?? []).map((c) => (
                          <Badge key={c} tone="outline" size="xs">
                            {c.replace(/_/g, "-")}
                          </Badge>
                        ))
                      ) : (
                        <NAValue />
                      )}
                    </div>
                  </Td>
                  <Td>{r.is_active === false ? <Badge tone="neutral">Paused</Badge> : r.is_active ? <Badge tone="up">Active</Badge> : <NAValue />}</Td>
                  <Td className="whitespace-nowrap text-xs">{r.last_triggered_at ? dateTimeIST(r.last_triggered_at) : <span className="text-muted">Never</span>}</Td>
                  <Td align="right">
                    <Button
                      size="xs"
                      variant="ghost"
                      icon={<Trash2 className="size-3.5" aria-hidden />}
                      onClick={() => setConfirm(r)}
                      aria-label={`Delete ${alertLabel(r.alert_type)} alert${r.symbol ? ` for ${r.symbol}` : ""}`}
                    >
                      Delete
                    </Button>
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
      <Dialog
        open={confirm !== null}
        onClose={() => {
          setConfirm(null);
          del.reset();
        }}
        title="Delete alert rule?"
        description="This removes the rule and its past events. It cannot be undone."
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={del.isPending}
              icon={<Trash2 className="size-4" aria-hidden />}
              onClick={() => {
                if (!confirm) return;
                del.mutate(confirm.id, { onSuccess: () => setConfirm(null) });
              }}
            >
              Delete rule
            </Button>
          </>
        }
      >
        {confirm ? (
          <p className="text-sm">
            <span className="font-semibold">{alertLabel(confirm.alert_type)}</span>
            {confirm.symbol ? <> for <span className="font-semibold">{confirm.symbol}</span></> : " (market-wide)"}
          </p>
        ) : null}
        {del.error ? (
          <p role="alert" className="mt-2 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
            {del.error.message}
          </p>
        ) : null}
      </Dialog>
    </Card>
  );
}

function isUnread(e: AlertEvent) {
  return !(e.read_at || e.is_read);
}

function EventsCard() {
  const q = useAlertEvents();
  const mark = useMarkAlertRead();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [bulk, setBulk] = useState(false);
  const events = (q.data ?? []) as EventX[];
  const unread = events.filter(isUnread);
  const shown = filter === "unread" ? unread : events;

  async function markAll() {
    setBulk(true);
    try {
      for (const e of unread) await mark.mutateAsync(e.id);
    } catch {
      // error surfaced via mark.error
    } finally {
      setBulk(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<BellRing className="size-4" />}
        title="Alert events"
        subtitle={q.isSuccess ? `${unread.length} unread of ${events.length}` : undefined}
        actions={
          <>
            <Segmented
              size="xs"
              label="Filter events"
              value={filter}
              onChange={setFilter}
              options={[
                { key: "all", label: "All" },
                { key: "unread", label: `Unread${unread.length ? ` (${unread.length})` : ""}` },
              ]}
            />
            <Button size="xs" variant="outline" disabled={!unread.length} loading={bulk} onClick={markAll} icon={<CheckCheck className="size-3.5" aria-hidden />}>
              Mark all read
            </Button>
          </>
        }
      />
      <CardBody className="p-0">
        {q.isPending ? (
          <div className="p-4">
            <SkeletonRows rows={5} />
          </div>
        ) : q.isError ? (
          <div className="p-4">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </div>
        ) : shown.length === 0 ? (
          <EmptyState compact icon={<Bell className="size-6" />} title={filter === "unread" ? "No unread alerts" : "No alert events yet"}>
            {filter === "unread" ? "You're all caught up." : "Events appear here when one of your rules fires after a data refresh."}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border" aria-label="Alert events">
            {shown.map((e) => {
              const un = isUnread(e);
              const d = e.data ?? {};
              const asOf = typeof d.as_of === "string" ? d.as_of : null;
              const kind = typeof d.kind === "string" ? (d.kind as PriceKind) : undefined;
              const when = e.triggered_at ?? e.created_at;
              return (
                <li key={e.id} className={cn("flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start", un ? "border-l-4 border-l-accent bg-accent-soft/40" : "border-l-4 border-l-transparent")}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {un ? (
                        <Badge tone="accent" size="xs">
                          Unread
                        </Badge>
                      ) : (
                        <Badge tone="outline" size="xs">
                          Read
                        </Badge>
                      )}
                      <span className={cn("text-sm", un ? "font-semibold text-fg" : "text-fg/80")}>{e.title ?? alertLabel(e.alert_type)}</span>
                      {e.symbol ? (
                        <Link href={`/stocks/${encodeURIComponent(e.symbol)}`} className="text-xs font-semibold text-accent hover:underline">
                          {e.symbol}
                        </Link>
                      ) : null}
                      {e.severity ? <Badge tone={e.severity === "high" || e.severity === "critical" ? "down" : "neutral"} size="xs">{e.severity}</Badge> : null}
                    </div>
                    {e.message ? <p className={cn("mt-0.5 break-words text-xs", un ? "text-fg/90" : "text-muted")}>{e.message}</p> : null}
                    <p className="mt-1 text-[11px] text-muted">
                      {alertLabel(e.alert_type)} · triggered {when ? dateTimeIST(when) : "n/a"}
                      {e.read_at ? ` · read ${dateTimeIST(e.read_at)}` : ""}
                    </p>
                    {asOf || kind ? <DataStamp className="mt-1" asOf={asOf} kind={kind ?? null} label="Price data as of" /> : null}
                  </div>
                  {un ? (
                    <Button
                      size="xs"
                      variant="outline"
                      loading={mark.isPending && mark.variables === e.id}
                      onClick={() => mark.mutate(e.id)}
                      icon={<Check className="size-3.5" aria-hidden />}
                      aria-label={`Mark “${e.title ?? alertLabel(e.alert_type)}” as read`}
                    >
                      Mark read
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {mark.error ? (
          <p role="alert" className="mx-4 mb-3 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
            {mark.error.message}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

export default function AlertsPage() {
  const rules = useAlertRules();
  return (
    <div className="space-y-4">
      <PageHeader title="Alerts" description="Price, setup, news and regime alerts — evaluated on the server after each data refresh." />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader icon={<Bell className="size-4" />} title="Create alert" />
          <CardBody>
            <CreateAlertForm serverTypes={rules.data?.types} />
          </CardBody>
        </Card>
        <div className="min-w-0 space-y-4">
          {rules.isPending ? (
            <Card>
              <CardBody>
                <SkeletonRows rows={4} />
              </CardBody>
            </Card>
          ) : rules.isError ? (
            <ErrorState error={rules.error} onRetry={() => rules.refetch()} />
          ) : (
            <RulesCard rules={rules.data.alerts} />
          )}
          <EventsCard />
        </div>
      </div>
    </div>
  );
}
