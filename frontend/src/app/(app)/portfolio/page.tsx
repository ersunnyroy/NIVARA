"use client";

import Link from "next/link";
import { useState } from "react";
import { Briefcase, ChevronRight, Plus, Siren } from "lucide-react";
import { useCreatePortfolio, usePortfolioDashboard, usePortfolioExits, usePortfolios } from "@/lib/hooks";
import { inr, inrCompact } from "@/lib/format";
import type { Portfolio, PortfolioSummary } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActionList } from "@/components/domain/ActionList";
import { MonitorActionBadge } from "@/components/domain/badges";
import { PortfolioSummaryTiles } from "@/components/domain/PortfolioSummary";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  Dialog,
  Disclaimer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Pct,
  Pnl,
  QueryState,
  Select,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";

function CreatePortfolioDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"live" | "paper">("live");
  const [broker, setBroker] = useState("");
  const m = useCreatePortfolio();
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New portfolio"
      description="Live portfolios track your real holdings; paper portfolios are simulated."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={m.isPending}
            disabled={!name.trim()}
            onClick={() =>
              m.mutate(
                { name: name.trim(), kind, broker: broker.trim() || null },
                {
                  onSuccess: () => {
                    setName("");
                    setBroker("");
                    onClose();
                  },
                },
              )
            }
          >
            Create
          </Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" required className="sm:col-span-2">
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Zerodha long-term" autoFocus />}
        </Field>
        <Field label="Kind">
          {(id) => (
            <Select id={id} value={kind} onChange={(e) => setKind(e.target.value as "live" | "paper")}>
              <option value="live">Live (real money)</option>
              <option value="paper">Paper (simulated)</option>
            </Select>
          )}
        </Field>
        <Field label="Broker" hint="Used to pick the brokerage schedule for charges">
          {(id) => <Input id={id} value={broker} onChange={(e) => setBroker(e.target.value)} placeholder="e.g. Zerodha" />}
        </Field>
      </div>
      {m.isError ? <ErrorState className="mt-3" error={m.error} /> : null}
    </Dialog>
  );
}

function PortfolioRow({ p, s }: { p: Portfolio; s?: PortfolioSummary | null }) {
  return (
    <Tr>
      <Td>
        <Link href={`/portfolio/${p.id}`} className="inline-flex items-center gap-1 font-semibold hover:text-accent hover:underline">
          {p.name} <ChevronRight className="size-3.5" aria-hidden />
        </Link>
        <div className="text-[11px] text-muted">{p.broker ?? "—"}</div>
      </Td>
      <Td>
        <Badge tone={p.kind === "paper" ? "violet" : "accent"} size="xs">
          {p.kind ?? "live"}
        </Badge>
      </Td>
      <Td align="right">{inrCompact(s?.invested)}</Td>
      <Td align="right">{inrCompact(s?.current_value)}</Td>
      <Td align="right">
        <Pnl value={s?.gross_pnl} compact />
      </Td>
      <Td align="right">{inrCompact(s?.charges_incl_estimated_exit)}</Td>
      <Td align="right">{s?.estimated_tax_realized == null ? "n/a" : inrCompact(s.estimated_tax_realized)}</Td>
      <Td align="right" className="font-semibold">
        <Pnl value={s?.net_pnl} compact />
        <div className="text-[11px] font-normal">
          <Pct value={s?.net_return_pct} />
        </div>
      </Td>
    </Tr>
  );
}

export default function PortfolioPage() {
  const dash = usePortfolioDashboard();
  const list = usePortfolios();
  const exits = usePortfolioExits();
  const [open, setOpen] = useState(false);
  const summaries = new Map((dash.data?.portfolios ?? []).map((p) => [p.id, p.summary]));
  // The backend already filters to holdings where an exit condition fired.
  const exitRows = exits.data ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Portfolio"
        description="All portfolios at a glance — P&L after charges and estimated tax."
        actions={
          <Button variant="primary" size="sm" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setOpen(true)}>
            New portfolio
          </Button>
        }
      />
      <CreatePortfolioDialog open={open} onClose={() => setOpen(false)} />

      <Card>
        <CardHeader icon={<Briefcase className="size-4" />} title="Aggregate (all live portfolios)" subtitle="Gross P&L shown alongside net; tax is an ESTIMATE" />
        <CardBody>
          <QueryState query={dash} skeleton={<SkeletonRows rows={2} />}>
            {(d) => (
              <>
                <PortfolioSummaryTiles summary={d.summary} />
                <DataStamp className="mt-3" asOf={d.data_as_of ?? d.summary?.data_as_of} kind="eod_close" label="Prices as of" />
              </>
            )}
          </QueryState>
        </CardBody>
      </Card>

      <Card id="exits" className="border-down/40">
        <CardHeader
          icon={<Siren className="size-4 text-down" />}
          title={<span className="text-down">SELL / EXIT NOW</span>}
          subtitle="Holdings where a stop is breached, the thesis is invalidated or a sell signal fired"
        />
        {exits.isPending ? (
          <SkeletonRows rows={3} className="p-4" />
        ) : exits.isError ? (
          <div className="p-4"><ErrorState error={exits.error} onRetry={() => exits.refetch()} /></div>
        ) : !exitRows.length ? (
          <EmptyState compact title="Nothing flagged for exit">No holding currently breaches its stop or has an active sell signal.</EmptyState>
        ) : (
          <TableWrap label="Exit candidates">
            <THead>
              <tr>
                <Th>Stock</Th>
                <Th>Portfolio</Th>
                <Th>Action</Th>
                <Th>Reasons / sell signals</Th>
                <Th align="right">Suggested trail</Th>
                <Th align="right">Partial exit</Th>
                <Th align="right">P&amp;L</Th>
              </tr>
            </THead>
            <tbody>
              {exitRows.map((e, i) => (
                <Tr key={`${e.symbol}-${e.portfolio}-${i}`}>
                  <Td>
                    <Link href={`/stocks/${encodeURIComponent(e.symbol)}`} className="font-semibold hover:text-accent hover:underline">
                      {e.symbol}
                    </Link>
                  </Td>
                  <Td className="text-xs">{e.portfolio ?? "—"}</Td>
                  <Td><MonitorActionBadge action={e.action} severity={e.severity} /></Td>
                  <Td className="max-w-md text-xs">
                    {[...(e.reasons ?? []), ...(e.sell_signals ?? []).map((s) => s.reason ?? s.code)].join(" · ") || "—"}
                  </Td>
                  <Td align="right">{inr(e.suggested_trailing_stop, 2)}</Td>
                  <Td align="right">{e.partial_exit_pct == null ? "n/a" : `${e.partial_exit_pct}%`}</Td>
                  <Td align="right">
                    <Pnl value={e.pnl} compact />
                    <div className="text-[11px]"><Pct value={e.pnl_pct} /></div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>

      <Card>
        <CardHeader title="Portfolios" />
        <QueryState query={list} skeleton={<SkeletonRows rows={3} className="p-4" />}>
          {(ps) =>
            ps.length ? (
              <TableWrap label="Portfolios">
                <THead>
                  <tr>
                    <Th>Portfolio</Th>
                    <Th>Kind</Th>
                    <Th align="right">Invested</Th>
                    <Th align="right">Current</Th>
                    <Th align="right">Gross P&amp;L</Th>
                    <Th align="right">Charges</Th>
                    <Th align="right">Est. tax (realised)</Th>
                    <Th align="right">Net P&amp;L</Th>
                  </tr>
                </THead>
                <tbody>
                  {ps.map((p) => (
                    <PortfolioRow key={p.id} p={p} s={summaries.get(p.id) ?? p.summary} />
                  ))}
                </tbody>
              </TableWrap>
            ) : (
              <EmptyState
                title="No portfolios yet"
                action={
                  <Button variant="primary" size="sm" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setOpen(true)}>
                    Create your first portfolio
                  </Button>
                }
              >
                Create a portfolio, then add BUY/SELL transactions. NIVARA computes FIFO tax lots, charges and estimated tax, and monitors each holding.
              </EmptyState>
            )
          }
        </QueryState>
      </Card>

      <Card>
        <CardHeader title="All monitor actions" subtitle="Every holding across portfolios, most urgent first" />
        {dash.isPending ? <SkeletonRows rows={3} className="p-4" /> : dash.isError ? null : <ActionList items={dash.data.actions ?? []} />}
      </Card>
      <Disclaimer />
    </div>
  );
}
