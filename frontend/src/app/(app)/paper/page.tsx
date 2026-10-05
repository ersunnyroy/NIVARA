"use client";

import Link from "next/link";
import { FlaskConical, Bot, ReceiptText, X } from "lucide-react";
import { useCancelPaperOrder, usePaper, useSetFollowModel } from "@/lib/hooks";
import { dateIST, dateTimeIST, int, num, titleCase, toNum } from "@/lib/format";
import type { Numeric, PaperOrder, PaperResponse, PortfolioDetail } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  EmptyState,
  Money,
  NAValue,
  Pnl,
  QueryState,
  SkeletonCard,
  Stat,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
  cn,
  type BadgeTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/PageHeader";
import { PortfolioSummaryTiles } from "@/components/domain/PortfolioSummary";
import { HoldingsTable } from "@/components/domain/Holdings";
import { OrderTicket } from "./_components/OrderTicket";
import { asPerf, BestWorstValue, Drawdown, hasTrades, profitFactor, winRate, type PerfStatsX } from "../performance/_components/perf";

/** Fields the backend sends beyond types.ts. */
type PaperOrderX = PaperOrder & { portfolio?: "paper" | "model" | (string & {}); valid_till?: string | null };
type PaperX = Omit<PaperResponse, "orders"> & {
  orders?: PaperOrderX[];
  model_portfolio?: PortfolioDetail | null;
  cash?: Numeric;
  model_cash?: Numeric;
  notice?: string | null;
};

const DEFAULT_FILL_POLICY =
  "MARKET orders fill at the next available end-of-day price (the next session’s official EOD bar). LIMIT orders fill only if that bar trades through your limit. Unfilled orders expire after a few sessions.";

const STATUS_TONE: Record<string, BadgeTone> = { open: "info", filled: "up", cancelled: "neutral", expired: "warn", rejected: "down" };

function latestAsOf(d?: PortfolioDetail | null): string | null {
  if (!d) return null;
  const direct = d.data_as_of ?? d.summary?.data_as_of ?? null;
  if (direct) return direct;
  const stamps = (d.positions ?? []).map((p) => p.price_as_of).filter((v): v is string => typeof v === "string" && v.length > 0);
  return stamps.length ? stamps.reduce((a, b) => (a > b ? a : b)) : null;
}

function FollowModelToggle({ value }: { value: boolean | undefined }) {
  const m = useSetFollowModel();
  const on = value === true;
  return (
    <Card>
      <CardHeader title="Follow the model" icon={<Bot className="size-4" />} subtitle="Automatic paper-trading of model recommendations" />
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span id="follow-model-label" className="text-sm font-medium">
            Auto-follow BUY recommendations
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-labelledby="follow-model-label"
            disabled={m.isPending || value === undefined}
            onClick={() => m.mutate(!on)}
            className={cn(
              "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:opacity-60",
              on ? "border-accent bg-accent" : "border-border-strong bg-surface-3",
            )}
          >
            <span className={cn("inline-block size-4 rounded-full bg-surface shadow transition-transform", on ? "translate-x-6" : "translate-x-1")} />
          </button>
        </div>
        <p className="text-xs font-medium">{value === undefined ? "Status not reported by the API." : on ? "ON — the model portfolio is following recommendations." : "OFF"}</p>
        <p className="text-xs leading-relaxed text-muted">
          When on, every BUY recommendation is placed as a paper order in a separate <strong>model portfolio</strong> using its suggested entry, stop and
          targets. Your own paper portfolio is untouched. This builds an honest track record of the model (shown as SYSTEM on the{" "}
          <Link href="/performance" className="text-accent hover:underline">
            performance
          </Link>{" "}
          page) to compare against your own decisions.
        </p>
        {m.error ? (
          <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
            {m.error.message}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

const CMP_ROWS: { label: string; render: (s: PerfStatsX) => React.ReactNode }[] = [
  { label: "Closed trades", render: (s) => (toNum(s.total_trades) === null ? <NAValue /> : int(s.total_trades)) },
  { label: "Wins / losses", render: (s) => (toNum(s.wins) === null && toNum(s.losses) === null ? <NAValue /> : `${int(s.wins)} / ${int(s.losses)}`) },
  { label: "Win rate", render: (s) => winRate(s.win_rate ?? null) },
  { label: "Avg win", render: (s) => <Pnl value={s.avg_win ?? null} /> },
  { label: "Avg loss", render: (s) => <Pnl value={s.avg_loss ?? null} /> },
  { label: "Profit factor", render: (s) => profitFactor(s.profit_factor ?? null) },
  { label: "Expectancy", render: (s) => <Pnl value={s.expectancy ?? null} /> },
  { label: "Net P&L", render: (s) => <Pnl value={s.net_pnl ?? null} /> },
  { label: "Max drawdown", render: (s) => <Drawdown value={s.max_drawdown_pct ?? null} /> },
  { label: "Avg holding", render: (s) => (toNum(s.avg_holding_days) === null ? <NAValue /> : `${num(s.avg_holding_days, 1)} days`) },
  { label: "Best trade", render: (s) => <BestWorstValue value={s.best} pnl={s.best_pnl} /> },
  { label: "Worst trade", render: (s) => <BestWorstValue value={s.worst} pnl={s.worst_pnl} /> },
];

function Comparison({ data }: { data: PaperX }) {
  const model = asPerf(data.comparison?.model);
  const user = asPerf(data.comparison?.user);
  const any = hasTrades(model) || hasTrades(user);
  return (
    <Card>
      <CardHeader title="Model vs you" subtitle="Closed paper trades only: the auto-followed model portfolio against your own paper decisions." />
      {!any ? (
        <EmptyState compact title="Nothing to compare yet">
          Comparison fills in once paper trades close — yours from the order ticket, the model’s when “follow the model” is on.
        </EmptyState>
      ) : (
        <TableWrap label="Model vs user comparison">
          <THead>
            <tr>
              <Th>Metric</Th>
              <Th align="right">
                <Badge tone="info" size="xs">
                  Model (system)
                </Badge>
              </Th>
              <Th align="right">
                <Badge tone="violet" size="xs">
                  You (paper)
                </Badge>
              </Th>
            </tr>
          </THead>
          <tbody>
            {CMP_ROWS.map((r) => (
              <Tr key={r.label}>
                <Td className="text-muted">{r.label}</Td>
                <Td align="right">{model && hasTrades(model) ? r.render(model) : <NAValue reason="No closed model trades" />}</Td>
                <Td align="right">{user && hasTrades(user) ? r.render(user) : <NAValue reason="No closed paper trades" />}</Td>
              </Tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {data.model_portfolio?.summary ? (
        <CardBody className="space-y-2 border-t border-border">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Model portfolio (open + realised)</h3>
          <PortfolioSummaryTiles summary={data.model_portfolio.summary} dense />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {data.model_cash !== undefined ? (
              <span className="text-xs text-muted">
                Cash: <Money value={data.model_cash ?? null} className="font-medium text-fg" />
              </span>
            ) : null}
            <DataStamp asOf={latestAsOf(data.model_portfolio)} />
          </div>
        </CardBody>
      ) : null}
    </Card>
  );
}

function OrdersTable({ orders }: { orders: PaperOrderX[] }) {
  const cancel = useCancelPaperOrder();
  if (!orders.length)
    return (
      <EmptyState compact title="No paper orders yet" icon={<ReceiptText className="size-6" />}>
        Use the order ticket to place your first simulated order.
      </EmptyState>
    );
  return (
    <>
      {cancel.error ? (
        <p role="alert" className="mx-4 mt-3 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          Cancel failed: {cancel.error.message}
        </p>
      ) : null}
      <TableWrap label="Paper orders">
        <THead>
          <tr>
            <Th>Placed</Th>
            <Th>Stock</Th>
            <Th>Book</Th>
            <Th>Side</Th>
            <Th align="right">Qty</Th>
            <Th>Type</Th>
            <Th align="right">Limit</Th>
            <Th align="right">Stop</Th>
            <Th align="right">Target</Th>
            <Th>Status</Th>
            <Th align="right">Fill price</Th>
            <Th>Filled / note</Th>
            <Th>
              <span className="sr-only">Actions</span>
            </Th>
          </tr>
        </THead>
        <tbody>
          {orders.map((o) => {
            const status = (o.status ?? "").toLowerCase();
            const cancellable = status === "open" && o.portfolio !== "model";
            const cancelling = cancel.isPending && cancel.variables === o.id;
            return (
              <Tr key={o.id}>
                <Td className="num whitespace-nowrap text-xs">{dateTimeIST(o.created_at ?? null)}</Td>
                <Td className="font-semibold">
                  {o.symbol ? (
                    <Link href={`/stocks/${encodeURIComponent(o.symbol)}`} className="hover:text-accent hover:underline">
                      {o.symbol}
                    </Link>
                  ) : (
                    <NAValue />
                  )}
                </Td>
                <Td>
                  {o.portfolio === "model" ? (
                    <Badge tone="info" size="xs">
                      Model
                    </Badge>
                  ) : (
                    <Badge tone="violet" size="xs">
                      You
                    </Badge>
                  )}
                </Td>
                <Td>
                  <Badge tone={o.side === "BUY" ? "up" : o.side === "SELL" ? "down" : "outline"} size="xs">
                    {o.side ?? "n/a"}
                  </Badge>
                </Td>
                <Td align="right">{toNum(o.quantity) === null ? <NAValue /> : int(o.quantity)}</Td>
                <Td className="text-xs">{o.order_type ?? <NAValue />}</Td>
                <Td align="right">{o.order_type === "LIMIT" ? <Money value={o.limit_price ?? null} /> : <span className="text-subtle">—</span>}</Td>
                <Td align="right">
                  <Money value={o.stop ?? null} />
                </Td>
                <Td align="right">
                  <Money value={o.target ?? null} />
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[status] ?? "outline"} size="xs">
                    {o.status ? titleCase(o.status) : "n/a"}
                  </Badge>
                  {status === "open" && o.valid_till ? <span className="block text-[10px] text-subtle">valid till {dateIST(o.valid_till)}</span> : null}
                </Td>
                <Td align="right">
                  <Money value={o.fill_price ?? null} />
                </Td>
                <Td className="max-w-64 text-xs text-muted">
                  {o.filled_at ? <span className="num block whitespace-nowrap">{dateTimeIST(o.filled_at)}</span> : null}
                  {o.fill_note ? <span className="block">{o.fill_note}</span> : null}
                  {!o.filled_at && !o.fill_note ? <span className="text-subtle">—</span> : null}
                </Td>
                <Td>
                  {cancellable ? (
                    <Button
                      size="xs"
                      variant="outline"
                      loading={cancelling}
                      disabled={cancel.isPending}
                      icon={<X className="size-3" aria-hidden />}
                      onClick={() => cancel.mutate(o.id)}
                      aria-label={`Cancel paper order ${o.side ?? ""} ${o.symbol ?? ""}`}
                    >
                      Cancel
                    </Button>
                  ) : null}
                </Td>
              </Tr>
            );
          })}
        </tbody>
      </TableWrap>
    </>
  );
}

export default function PaperPage() {
  const q = usePaper();
  return (
    <div>
      <PageHeader title="Paper trading" description="Practise and validate ideas with simulated money before risking real capital." />
      <div className="mb-4 flex items-start gap-3 rounded-lg border-2 border-violet/40 bg-violet-soft px-4 py-3 text-violet" role="note">
        <FlaskConical className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-bold uppercase tracking-wide">Paper trading = simulated. No real orders are ever placed.</p>
          <p className="mt-0.5 text-xs text-fg/80">
            Orders are filled against official end-of-day prices with modelled charges. Results are not live performance and are reported separately.
            {q.data && (q.data as PaperX).notice ? ` ${(q.data as PaperX).notice}` : ""}
          </p>
        </div>
      </div>
      <QueryState
        query={q}
        skeleton={
          <div className="space-y-4">
            <SkeletonCard lines={3} />
            <SkeletonCard lines={6} />
          </div>
        }
      >
        {(raw) => {
          const data = raw as PaperX;
          const pf = data.portfolio;
          const positions = pf?.positions ?? [];
          const fillPolicy = data.fill_policy ?? DEFAULT_FILL_POLICY;
          return (
            <div className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
                <div className="min-w-0 space-y-4">
                  <Card>
                    <CardHeader title={pf?.portfolio?.name ?? "Paper portfolio"} subtitle="Your simulated portfolio" />
                    <CardBody className="space-y-3">
                      {pf ? (
                        <>
                          <PortfolioSummaryTiles summary={pf.summary} />
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                            {data.cash !== undefined ? (
                              <Stat size="sm" label="Available cash (simulated)" value={<Money value={data.cash ?? null} />} />
                            ) : null}
                          </div>
                          <DataStamp asOf={latestAsOf(pf)} label="Prices as of" />
                        </>
                      ) : (
                        <EmptyState compact title="Paper portfolio not available">
                          The API did not return a paper portfolio. It is created automatically the first time you place a paper order.
                        </EmptyState>
                      )}
                    </CardBody>
                    {pf ? (
                      <div className="border-t border-border">
                        <HoldingsTable positions={positions} portfolioId={pf.portfolio?.id} />
                      </div>
                    ) : null}
                  </Card>
                </div>
                <div className="min-w-0 space-y-4">
                  <Card>
                    <CardHeader title="Order ticket" icon={<ReceiptText className="size-4" />} subtitle="Simulated order — nothing is sent to a broker" />
                    <CardBody>
                      <OrderTicket fillPolicy={fillPolicy} />
                    </CardBody>
                  </Card>
                  <FollowModelToggle value={typeof data.follow_model === "boolean" ? data.follow_model : undefined} />
                </div>
              </div>

              <Card>
                <CardHeader title="Orders" subtitle="Your paper orders and those placed by the model portfolio. Open orders can be cancelled." />
                <OrdersTable orders={data.orders ?? []} />
              </Card>

              <Comparison data={data} />
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}
