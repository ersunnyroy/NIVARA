"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDownRight, ArrowUpRight, CornerLeftUp, CornerRightDown, Minus, Search, X } from "lucide-react";
import { useFnoOverview } from "@/lib/hooks";
import { num, ratioPct, titleCase, toNum } from "@/lib/format";
import type { FnoOverview, FnoSnapshot } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  DataStatusBanner,
  DataUnavailable,
  Disclaimer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Money,
  NAValue,
  Pct,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
  cn,
  type BadgeTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/PageHeader";

/** Fields the backend sends beyond types.ts. */
type FnoOverviewX = FnoOverview & { buildup_counts?: Record<string, number> | null; caveat?: string | null };

const JOB_HINT = "An admin can run the F&O job from Settings → Jobs.";

const DEFAULT_BUILDUPS = ["long_buildup", "short_buildup", "short_covering", "long_unwinding"];

const BUILDUP: Record<string, { label: string; tone: BadgeTone; icon: React.ElementType; hint: string }> = {
  long_buildup: { label: "Long buildup", tone: "up", icon: ArrowUpRight, hint: "Price ↑ and open interest ↑" },
  short_buildup: { label: "Short buildup", tone: "down", icon: ArrowDownRight, hint: "Price ↓ and open interest ↑" },
  short_covering: { label: "Short covering", tone: "info", icon: CornerRightDown, hint: "Price ↑ and open interest ↓" },
  long_unwinding: { label: "Long unwinding", tone: "warn", icon: CornerLeftUp, hint: "Price ↓ and open interest ↓" },
  neutral: { label: "Neutral", tone: "neutral", icon: Minus, hint: "No clear price/OI signal" },
};

function BuildupBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge tone="outline" size="xs">n/a</Badge>;
  const b = BUILDUP[value];
  if (!b)
    return (
      <Badge tone="outline" size="xs">
        {titleCase(value)}
      </Badge>
    );
  const Icon = b.icon;
  return (
    <Badge tone={b.tone} size="xs" title={b.hint}>
      <Icon className="size-3" aria-hidden />
      {b.label}
    </Badge>
  );
}

function Level({ v }: { v: FnoSnapshot["max_pain"] }) {
  return toNum(v) === null ? <NAValue /> : <span className="num">{num(v, 2)}</span>;
}

function FnoTable({ items }: { items: FnoSnapshot[] }) {
  return (
    <TableWrap label="F&O overview by underlying">
      <THead>
        <tr>
          <Th>Underlying</Th>
          <Th align="right">Spot</Th>
          <Th align="right">Future</Th>
          <Th align="right" title="(Future − spot) ÷ spot">
            Basis
          </Th>
          <Th align="right" title="Change in futures open interest vs previous session">
            Fut OI chg
          </Th>
          <Th align="right" title="Put-call ratio by open interest">
            PCR (OI)
          </Th>
          <Th align="right">Max pain</Th>
          <Th align="right" title="Strike with the highest call OI">
            Call resistance
          </Th>
          <Th align="right" title="Strike with the highest put OI">
            Put support
          </Th>
          <Th align="right">ATM IV</Th>
          <Th align="right" title="Share of past IV observations below today’s IV">
            IV %ile
          </Th>
          <Th>Buildup</Th>
          <Th>Interpretation</Th>
        </tr>
      </THead>
      <tbody>
        {items.map((r, i) => {
          const sym = r.underlying ?? null;
          return (
            <Tr key={`${sym ?? "row"}-${i}`}>
              <Td className="font-semibold">
                {sym ? (
                  <Link href={`/stocks/${encodeURIComponent(sym)}`} className="hover:text-accent hover:underline">
                    {sym}
                  </Link>
                ) : (
                  <NAValue />
                )}
              </Td>
              <Td align="right">
                <Money value={r.spot ?? null} />
              </Td>
              <Td align="right">
                <Money value={r.fut_price ?? null} />
              </Td>
              <Td align="right">
                <Pct value={r.basis_pct ?? null} plain />
              </Td>
              <Td align="right">
                <Pct value={r.fut_oi_change_pct ?? null} />
              </Td>
              <Td align="right">{toNum(r.pcr_oi) === null ? <NAValue /> : num(r.pcr_oi, 2)}</Td>
              <Td align="right">
                <Level v={r.max_pain} />
              </Td>
              <Td align="right">
                <Level v={r.call_resistance} />
              </Td>
              <Td align="right">
                <Level v={r.put_support} />
              </Td>
              <Td align="right">{toNum(r.atm_iv) === null ? <NAValue /> : ratioPct(r.atm_iv, 1)}</Td>
              <Td align="right">{toNum(r.iv_percentile) === null ? <NAValue reason="Insufficient IV history" /> : num(r.iv_percentile, 0)}</Td>
              <Td>
                <BuildupBadge value={r.buildup} />
              </Td>
              <Td className="min-w-64 max-w-md text-xs text-muted">{r.interpretation ?? <NAValue />}</Td>
            </Tr>
          );
        })}
      </tbody>
    </TableWrap>
  );
}

export default function FnoPage() {
  const [date, setDate] = useState("");
  const [buildup, setBuildup] = useState("all");
  const [search, setSearch] = useState("");
  const q = useFnoOverview(date || undefined);
  const data = q.data as FnoOverviewX | undefined;
  const items = data?.items ?? [];

  const counts: Record<string, number> = {};
  for (const it of items) {
    const k = it.buildup || "n/a";
    counts[k] = (counts[k] ?? 0) + 1;
  }
  const chipKeys = Array.from(new Set([...DEFAULT_BUILDUPS, ...items.map((i) => i.buildup).filter((b): b is string => !!b)]));
  const term = search.trim().toUpperCase();
  const filtered = items.filter((it) => (buildup === "all" || it.buildup === buildup) && (!term || (it.underlying ?? "").toUpperCase().includes(term)));
  const noData = !!data && items.length === 0;

  return (
    <div>
      <PageHeader
        title="F&O overview"
        description="End-of-day futures & options positioning per underlying: basis, open interest, PCR, max pain, IV and buildup."
        actions={
          <div className="flex items-end gap-2">
            <Field label="Session date" hint={date ? undefined : "Latest available"}>
              {(id) => <Input id={id} type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-40" />}
            </Field>
            {date ? (
              <Button variant="ghost" size="sm" className="mb-0.5" onClick={() => setDate("")} icon={<X className="size-3.5" aria-hidden />}>
                Latest
              </Button>
            ) : null}
          </div>
        }
      />

      <Disclaimer tone="warn" className="mb-4">
        Decision-support only, not advice. Derivatives are leveraged and carry high risk — losses can exceed your margin. Open interest is one input;
        never decide on OI alone.
      </Disclaimer>

      <Card>
        <CardHeader
          title="Underlyings"
          subtitle={data?.caveat ?? "Buildup is inferred from the change in futures price and open interest."}
          actions={
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden />
              <Input
                aria-label="Filter underlyings by symbol"
                placeholder="Filter symbol…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-8 w-44 pl-8 text-xs"
              />
            </div>
          }
        />
        <CardBody className="space-y-3">
          {q.isPending ? (
            <SkeletonRows rows={8} />
          ) : q.isError ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} unavailableHint={JOB_HINT} />
          ) : (
            <>
              <DataStamp label="F&O session" asOf={data?.date ?? null} source={data?.source ?? null} />
              {data?.status && data.status !== "ok" && !(noData && data.status === "data_unavailable") ? (
                <DataStatusBanner status={data.status} message={data.message ?? undefined} hint={JOB_HINT} />
              ) : null}
              {noData ? (
                <DataUnavailable
                  message={data?.message ?? (date ? `No F&O snapshot for ${date}. It may be a holiday or the job has not run for that session.` : "No F&O data has been ingested yet.")}
                  hint={JOB_HINT}
                />
              ) : (
                <>
                  <div role="radiogroup" aria-label="Filter by buildup" className="flex flex-wrap gap-1.5">
                    {["all", ...chipKeys].map((k) => {
                      const sel = buildup === k;
                      const n = k === "all" ? items.length : counts[k] ?? 0;
                      return (
                        <button
                          key={k}
                          type="button"
                          role="radio"
                          aria-checked={sel}
                          onClick={() => setBuildup(k)}
                          className={cn(
                            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                            sel ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:bg-surface-2 hover:text-fg",
                          )}
                        >
                          {k === "all" ? "All" : BUILDUP[k]?.label ?? titleCase(k)}
                          <span className="num rounded bg-surface-3 px-1 text-[10px] text-fg/80">{n}</span>
                        </button>
                      );
                    })}
                  </div>
                  {filtered.length === 0 ? (
                    <EmptyState compact title="No underlyings match">
                      Try another buildup filter or clear the symbol search.
                    </EmptyState>
                  ) : null}
                </>
              )}
            </>
          )}
        </CardBody>
        {!q.isPending && !q.isError && !noData && filtered.length > 0 ? (
          <div className="border-t border-border">
            <FnoTable items={filtered} />
          </div>
        ) : null}
      </Card>
    </div>
  );
}
