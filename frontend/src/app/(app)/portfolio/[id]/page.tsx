"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ListPlus, PieChart, Receipt, Trash2, Wallet } from "lucide-react";
import { useAddTransaction, useDeleteTransaction, usePortfolio, useRealized, useTransactions } from "@/lib/hooks";
import { dateIST, fyFor, inr, int, titleCase, toNum, todayIST } from "@/lib/format";
import type { RealizedRow, RealizedSummary, TransactionIn } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { HBars } from "@/components/charts/svg";
import { EstimatedTag } from "@/components/domain/badges";
import { HoldingsTable } from "@/components/domain/Holdings";
import { PortfolioSummaryTiles } from "@/components/domain/PortfolioSummary";
import { StockSearch } from "@/components/domain/StockSearch";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  Disclaimer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Money,
  Pnl,
  QueryState,
  Select,
  SkeletonCard,
  SkeletonRows,
  Stat,
  TableWrap,
  Td,
  Textarea,
  Th,
  THead,
  Tr,
} from "@/components/ui";

/* ----------------------------------------------------------- add transaction */

function AddTransactionForm({ portfolioId, defaultBroker }: { portfolioId: string; defaultBroker?: string | null }) {
  const blank = () => ({
    symbol: "",
    side: "BUY" as TransactionIn["side"],
    quantity: "",
    price: "",
    trade_date: todayIST(),
    segment: "delivery" as TransactionIn["segment"],
    exchange: "NSE" as TransactionIn["exchange"],
    broker: defaultBroker ?? "",
    charges_total: "",
    notes: "",
  });
  const [f, setF] = useState(blank);
  const [searchKey, setSearchKey] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const m = useAddTransaction(portfolioId);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const q = toNum(f.quantity);
    const p = toNum(f.price);
    if (!f.symbol) return setErr("Pick a stock from the search list.");
    if (!q || q <= 0 || !Number.isInteger(q)) return setErr("Quantity must be a positive whole number.");
    if (!p || p <= 0) return setErr("Price must be positive.");
    const ch = toNum(f.charges_total);
    m.mutate(
      {
        symbol: f.symbol,
        side: f.side,
        quantity: q,
        price: p,
        trade_date: f.trade_date,
        segment: f.segment,
        exchange: f.exchange,
        broker: f.broker || null,
        charges_total: ch,
        notes: f.notes || null,
      },
      {
        onSuccess: () => {
          setF(blank());
          setSearchKey((k) => k + 1);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Field label="Stock" required className="col-span-2">
        {(id) => (
          <div>
            <StockSearch
              key={searchKey}
              id={id}
              clearOnSelect={false}
              onSelect={(h) => setF((x) => ({ ...x, symbol: h.symbol }))}
              placeholder="Search symbol or company"
            />
            {f.symbol ? <p className="mt-1 text-[11px] text-muted">Selected: <span className="font-semibold text-fg">{f.symbol}</span></p> : null}
          </div>
        )}
      </Field>
      <Field label="Side">
        {(id) => (
          <Select id={id} value={f.side} onChange={(e) => setF({ ...f, side: e.target.value as TransactionIn["side"] })}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </Select>
        )}
      </Field>
      <Field label="Trade date" required>
        {(id) => <Input id={id} type="date" value={f.trade_date} onChange={(e) => setF({ ...f, trade_date: e.target.value })} required />}
      </Field>
      <Field label="Quantity" required>
        {(id) => <Input id={id} type="number" min={1} step={1} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} required />}
      </Field>
      <Field label="Price (₹)" required>
        {(id) => <Input id={id} type="number" min={0} step="any" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} required />}
      </Field>
      <Field label="Segment">
        {(id) => (
          <Select id={id} value={f.segment} onChange={(e) => setF({ ...f, segment: e.target.value as TransactionIn["segment"] })}>
            <option value="delivery">Delivery (CNC)</option>
            <option value="intraday">Intraday (MIS)</option>
          </Select>
        )}
      </Field>
      <Field label="Exchange">
        {(id) => (
          <Select id={id} value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value as TransactionIn["exchange"] })}>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </Select>
        )}
      </Field>
      <Field label="Broker">
        {(id) => <Input id={id} value={f.broker} onChange={(e) => setF({ ...f, broker: e.target.value })} />}
      </Field>
      <Field label="Charges total (₹)" hint="Optional — leave blank to estimate from the schedule">
        {(id) => <Input id={id} type="number" min={0} step="any" value={f.charges_total} onChange={(e) => setF({ ...f, charges_total: e.target.value })} />}
      </Field>
      <Field label="Notes" className="col-span-2">
        {(id) => <Textarea id={id} rows={1} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />}
      </Field>
      <div className="col-span-2 flex items-center gap-3 md:col-span-4">
        <Button type="submit" variant="primary" size="sm" loading={m.isPending} icon={<ListPlus className="size-3.5" aria-hidden />}>
          Add transaction
        </Button>
        {m.isSuccess ? <span className="text-xs text-up" role="status">Transaction added — lots, charges and P&amp;L recomputed.</span> : null}
        {err ? <span className="text-xs text-down" role="alert">{err}</span> : null}
      </div>
      {m.isError ? <ErrorState className="col-span-2 md:col-span-4" error={m.error} /> : null}
    </form>
  );
}

/* --------------------------------------------------------------- transactions */

function TransactionsCard({ portfolioId }: { portfolioId: string }) {
  const q = useTransactions(portfolioId);
  const del = useDeleteTransaction(portfolioId);
  return (
    <Card>
      <CardHeader icon={<Receipt className="size-4" />} title="Transactions" subtitle="Deleting a transaction rebuilds FIFO lots and realised gains" />
      <QueryState query={q} skeleton={<SkeletonRows rows={4} className="p-4" />}>
        {(rows) =>
          rows.length ? (
            <TableWrap label="Transactions">
              <THead>
                <tr>
                  <Th>Date</Th>
                  <Th>Stock</Th>
                  <Th>Side</Th>
                  <Th align="right">Qty</Th>
                  <Th align="right">Price</Th>
                  <Th align="right">Value</Th>
                  <Th align="right">Charges</Th>
                  <Th>Segment</Th>
                  <Th>Broker</Th>
                  <Th>Notes</Th>
                  <Th><span className="sr-only">Delete</span></Th>
                </tr>
              </THead>
              <tbody>
                {[...rows]
                  .sort((a, b) => (a.trade_date < b.trade_date ? 1 : -1))
                  .map((t) => {
                    const value = (toNum(t.quantity) ?? 0) * (toNum(t.price) ?? 0);
                    return (
                      <Tr key={t.id}>
                        <Td className="whitespace-nowrap">{dateIST(t.trade_date)}</Td>
                        <Td className="font-semibold">{t.symbol ?? "—"}</Td>
                        <Td>
                          <Badge tone={t.side === "BUY" ? "up" : "down"} size="xs">
                            {t.side}
                          </Badge>
                        </Td>
                        <Td align="right">{int(t.quantity)}</Td>
                        <Td align="right">{inr(t.price, 2)}</Td>
                        <Td align="right">{inr(value)}</Td>
                        <Td align="right">
                          {inr(t.charges_total, 2)}
                          {t.charges_source ? <div className="text-[10px] text-muted">{t.charges_source}</div> : null}
                        </Td>
                        <Td className="text-xs">{titleCase(t.segment)}</Td>
                        <Td className="text-xs">{t.broker ?? "—"}</Td>
                        <Td className="max-w-48 truncate text-xs text-muted" title={t.notes ?? undefined}>
                          {t.notes ?? ""}
                        </Td>
                        <Td>
                          <Button
                            size="xs"
                            variant="ghost"
                            aria-label={`Delete ${t.side} ${t.symbol} on ${t.trade_date}`}
                            loading={del.isPending && del.variables === t.id}
                            onClick={() => {
                              if (window.confirm(`Delete ${t.side} ${int(t.quantity)} ${t.symbol} @ ${inr(t.price, 2)} on ${dateIST(t.trade_date)}?`)) del.mutate(t.id);
                            }}
                          >
                            <Trash2 className="size-3.5" aria-hidden />
                          </Button>
                        </Td>
                      </Tr>
                    );
                  })}
              </tbody>
            </TableWrap>
          ) : (
            <EmptyState compact title="No transactions yet">Use the form above to record your first BUY.</EmptyState>
          )
        }
      </QueryState>
      {del.isError ? <div className="p-4"><ErrorState error={del.error} /></div> : null}
    </Card>
  );
}

/* --------------------------------------------------------------- realised */

function fyOptions(): string[] {
  const cur = fyFor(todayIST());
  const start = Number(cur.slice(0, 4));
  return [0, 1, 2, 3].map((i) => `${start - i}-${String((start - i + 1) % 100).padStart(2, "0")}`);
}

function RealizedCard({ portfolioId }: { portfolioId: string }) {
  const [opts] = useState(fyOptions);
  const [fy, setFy] = useState(opts[0]);
  const q = useRealized(portfolioId, fy);
  return (
    <Card>
      <CardHeader
        icon={<Wallet className="size-4" />}
        title="Realised P&L"
        subtitle="Per FIFO lot; capital gain per tax rules (STT not deductible), trading P&L after all charges"
        actions={
          <Select aria-label="Financial year" className="h-8 w-28 text-xs" value={fy} onChange={(e) => setFy(e.target.value)}>
            {opts.map((o) => (
              <option key={o} value={o}>
                FY {o}
              </option>
            ))}
          </Select>
        }
      />
      <QueryState query={q} skeleton={<SkeletonRows rows={3} className="p-4" />}>
        {(d) => {
          const summary: RealizedSummary | null = d.summary ?? null;
          const rows: RealizedRow[] = d.lines ?? [];
          return (
            <>
              {summary ? (
                <CardBody className="border-b border-border">
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
                    <Stat size="sm" label="Gross capital gain" value={<Pnl value={summary.capital_gain_gross ?? summary.gross_pnl} />} />
                    <Stat size="sm" label="Charges" value={<Money value={summary.charges} />} />
                    <Stat size="sm" label="Trading P&L" sub="after all charges" value={<Pnl value={summary.trading_pnl} />} />
                    <Stat size="sm" label="Est. tax" badge={<EstimatedTag />} value={<Money value={summary.estimated_tax} />} />
                    <Stat size="sm" label="Net after tax" value={<Pnl value={summary.net_after_tax ?? summary.net_pnl} />} />
                  </div>
                  {summary.incomplete_reasons?.length ? (
                    <p className="mt-2 text-[11px] text-warn">Tax estimate incomplete: {summary.incomplete_reasons.join("; ")}</p>
                  ) : null}
                </CardBody>
              ) : null}
              {rows.length ? (
                <TableWrap label="Realised gains">
                  <THead>
                    <tr>
                      <Th>Stock</Th>
                      <Th>Bought</Th>
                      <Th>Sold</Th>
                      <Th align="right">Qty</Th>
                      <Th align="right">Buy value</Th>
                      <Th align="right">Sell value</Th>
                      <Th align="right">Charges</Th>
                      <Th align="right">Capital gain</Th>
                      <Th align="right">Trading P&amp;L</Th>
                      <Th>Term</Th>
                      <Th align="right">Days</Th>
                    </tr>
                  </THead>
                  <tbody>
                    {rows.map((r, i) => (
                      <Tr key={i}>
                        <Td className="font-semibold">{r.symbol ?? "—"}</Td>
                        <Td className="whitespace-nowrap text-xs">{dateIST(r.acquired_date)}</Td>
                        <Td className="whitespace-nowrap text-xs">{dateIST(r.sold_date)}</Td>
                        <Td align="right">{int(r.quantity)}</Td>
                        <Td align="right">{inr(r.purchase_value)}</Td>
                        <Td align="right">{inr(r.sale_value)}</Td>
                        <Td align="right">
                          {r.buy_charges == null && r.sell_charges == null ? "n/a" : inr((toNum(r.buy_charges) ?? 0) + (toNum(r.sell_charges) ?? 0), 2)}
                        </Td>
                        <Td align="right"><Pnl value={r.capital_gain} /></Td>
                        <Td align="right"><Pnl value={r.trading_pnl} /></Td>
                        <Td>
                          <Badge tone={r.term === "LTCG" ? "info" : r.term === "SPEC" ? "violet" : "neutral"} size="xs">
                            {r.term ?? "n/a"}
                          </Badge>
                        </Td>
                        <Td align="right">{r.holding_days ?? "n/a"}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <EmptyState compact title={`No realised trades in FY ${fy}`}>Realised gains appear once you record SELL transactions.</EmptyState>
              )}
            </>
          );
        }}
      </QueryState>
    </Card>
  );
}

/* ------------------------------------------------------------------- page */

export default function PortfolioDetailPage() {
  const { id } = useParams<{ id: string }>();
  const q = usePortfolio(id);
  const d = q.data;
  const alloc = Object.entries(d?.risk?.sector_allocation ?? {})
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => (toNum(b.value) ?? 0) - (toNum(a.value) ?? 0));

  return (
    <div className="space-y-4">
      <Link href="/portfolio" className="inline-flex items-center gap-1 text-xs text-muted hover:text-fg">
        <ArrowLeft className="size-3.5" aria-hidden /> All portfolios
      </Link>
      {q.isPending ? (
        <SkeletonCard lines={4} />
      ) : q.isError ? (
        <ErrorState error={q.error} title={q.error.isNotFound ? "Portfolio not found" : undefined} onRetry={() => q.refetch()} />
      ) : (
        <>
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                {d?.portfolio?.name ?? `Portfolio ${id}`}
                <Badge tone={d?.portfolio?.kind === "paper" ? "violet" : "accent"} size="xs">
                  {d?.portfolio?.kind ?? "live"}
                </Badge>
              </span>
            }
            description={d?.portfolio?.broker ? `Broker: ${d.portfolio.broker}` : undefined}
          />
          <Card>
            <CardBody>
              <PortfolioSummaryTiles summary={d?.summary} />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <DataStamp asOf={d?.data_as_of ?? d?.summary?.data_as_of} kind="eod_close" label="Prices as of" />
                {d?.labels?.unrealized_note ? <p className="text-[11px] text-muted">{d.labels.unrealized_note}</p> : null}
              </div>
              {d?.labels?.tax ? <p className="mt-2 text-[11px] text-warn">{d.labels.tax}</p> : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Holdings" subtitle="Click a row for its Portfolio Action Card: P&L after charges & tax, stop/targets and the monitor's recommendation" />
            <HoldingsTable positions={d?.positions ?? []} portfolioId={id} />
          </Card>

          {alloc.length || d?.risk?.warnings?.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader icon={<PieChart className="size-4" />} title="Sector allocation" />
                <CardBody>
                  {alloc.length ? (
                    <HBars data={alloc} format={(v) => `${v.toFixed(1)}%`} max={Math.max(...alloc.map((a) => toNum(a.value) ?? 0), 1)} />
                  ) : (
                    <p className="text-xs text-muted">n/a</p>
                  )}
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Risk warnings" />
                <CardBody>
                  {d?.risk?.warnings?.length ? (
                    <ul className="list-inside list-disc space-y-1 text-xs text-warn">
                      {d.risk.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted">No concentration or risk-limit breaches.</p>
                  )}
                </CardBody>
              </Card>
            </div>
          ) : null}
        </>
      )}

      <Card>
        <CardHeader icon={<ListPlus className="size-4" />} title="Add transaction" subtitle="Charges are estimated from the broker schedule unless you enter the contract-note total" />
        <CardBody>
          <AddTransactionForm portfolioId={id} defaultBroker={d?.portfolio?.broker} key={d?.portfolio?.broker ?? "nb"} />
        </CardBody>
      </Card>

      <TransactionsCard portfolioId={id} />
      <RealizedCard portfolioId={id} />
      <Disclaimer>{d?.labels?.disclaimer ?? undefined}</Disclaimer>
    </div>
  );
}
