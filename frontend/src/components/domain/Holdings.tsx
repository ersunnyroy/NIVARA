"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, Save } from "lucide-react";
import { useSetPositionLevels } from "@/lib/hooks";
import { dateIST, inr, int, num, pct, titleCase, toNum } from "@/lib/format";
import type { Numeric, Position } from "@/lib/types";
import {
  Button,
  DataStamp,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Money,
  Pct,
  Pnl,
  PriceKindBadge,
  TableWrap,
  Td,
  Textarea,
  Th,
  THead,
  Tr,
  cn,
} from "@/components/ui";
import { EstimatedTag, MonitorActionBadge } from "./badges";

function str(v: Numeric): string {
  const n = toNum(v);
  return n === null ? "" : String(n);
}

function LevelsForm({ portfolioId, position }: { portfolioId: number | string; position: Position }) {
  const lv = position.monitor?.levels ?? {};
  const [f, setF] = useState({
    stop: str(lv.stop),
    target1: str(lv.target1),
    target2: str(lv.target2),
    trailing_stop: str(lv.trailing_stop),
    thesis: position.thesis ?? "",
  });
  const m = useSetPositionLevels(portfolioId);
  const numOrNull = (s: string) => toNum(s);
  return (
    <form
      className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate({
          symbol: position.symbol,
          levels: {
            stop: numOrNull(f.stop),
            target1: numOrNull(f.target1),
            target2: numOrNull(f.target2),
            trailing_stop: numOrNull(f.trailing_stop),
            thesis: f.thesis || null,
          },
        });
      }}
    >
      {(["stop", "target1", "target2", "trailing_stop"] as const).map((k) => (
        <Field key={k} label={`${titleCase(k)} (₹)`}>
          {(id) => <Input id={id} type="number" step="any" min={0} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}
        </Field>
      ))}
      <Field label="Thesis / notes" className="col-span-2 sm:col-span-4">
        {(id) => <Textarea id={id} rows={2} value={f.thesis} onChange={(e) => setF({ ...f, thesis: e.target.value })} />}
      </Field>
      <div className="col-span-2 flex items-center gap-2 sm:col-span-4">
        <Button type="submit" size="sm" variant="primary" loading={m.isPending} icon={<Save className="size-3.5" aria-hidden />}>
          Save levels
        </Button>
        {m.isSuccess ? <span className="text-xs text-up">Saved.</span> : null}
      </div>
      {m.isError ? <ErrorState className="col-span-2 sm:col-span-4" error={m.error} /> : null}
    </form>
  );
}

/** Portfolio Action Card — the expanded per-holding view. */
export function PositionActionCard({ position: p, portfolioId }: { position: Position; portfolioId?: number | string }) {
  const mon = p.monitor;
  const lv = mon?.levels;
  return (
    <div className="grid gap-4 p-4 lg:grid-cols-3">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <MonitorActionBadge action={mon?.action} severity={mon?.severity} />
          {mon?.partial_exit_pct != null ? <span className="text-xs text-warn">Partial exit suggested: {num(mon.partial_exit_pct, 0)}%</span> : null}
        </div>
        {mon?.reasons?.length ? (
          <ul className="list-inside list-disc space-y-0.5 text-xs leading-relaxed">
            {mon.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">No monitor reasons reported.</p>
        )}
        {mon?.sell_signals?.length ? (
          <div className="rounded-md border border-down/30 bg-down-soft/50 p-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-down">Sell signals</p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {mon.sell_signals.map((s, i) => (
                <li key={i}>
                  <span className="font-mono text-[10px] text-muted">{s.code}</span> {s.reason}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="text-[11px] text-muted">Monitor output is decision support, not an instruction to trade.</p>
      </section>

      <section>
        <dl className="num grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          <dt className="text-muted">Quantity</dt>
          <dd className="text-right">{int(p.quantity)}</dd>
          <dt className="text-muted">Avg buy</dt>
          <dd className="text-right">{inr(p.avg_cost, 2)}</dd>
          <dt className="text-muted">CMP</dt>
          <dd className="text-right">
            {inr(p.price, 2)} <PriceKindBadge kind={p.price_kind} />
          </dd>
          <dt className="text-muted">Invested</dt>
          <dd className="text-right">{inr(p.invested)}</dd>
          <dt className="text-muted">Current value</dt>
          <dd className="text-right">{inr(p.current_value)}</dd>
          <dt className="text-muted">Gross P&amp;L</dt>
          <dd className="text-right">
            <Pnl value={p.gross_pnl} /> <Pct value={p.gross_pnl_pct} className="text-[11px]" />
          </dd>
          <dt className="text-muted">Charges paid</dt>
          <dd className="text-right">{inr(p.charges_paid, 2)}</dd>
          <dt className="text-muted">Est. exit charges</dt>
          <dd className="text-right">{inr(p.est_exit_charges, 2)}</dd>
          <dt className="flex items-center gap-1 text-muted">
            Est. tax if sold <EstimatedTag />
          </dt>
          <dd className="text-right">{inr(p.est_tax_if_sold, 2)}</dd>
          <dt className="font-semibold">NET P&amp;L</dt>
          <dd className="text-right font-semibold">
            <Pnl value={p.net_pnl} /> <Pct value={p.net_pnl_pct} className="text-[11px]" />
          </dd>
        </dl>
        <p className="mt-2 text-[11px] text-muted">
          Tax status: {p.tax_status ? titleCase(p.tax_status) : "n/a"}
          {p.tax_terms?.length ? ` (${p.tax_terms.join(", ")})` : ""}
        </p>
        {p.tax_incomplete_reasons?.length ? (
          <p className="mt-1 text-[11px] text-warn">Tax estimate incomplete: {p.tax_incomplete_reasons.join("; ")}</p>
        ) : null}
        <DataStamp className="mt-1" asOf={p.price_as_of} source={p.price_source} label="Price as of" />
      </section>

      <section className="space-y-3">
        <dl className="num grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          <dt className="text-muted">Stop</dt>
          <dd className="text-right text-down">{inr(lv?.stop, 2)}</dd>
          <dt className="text-muted">Distance to stop</dt>
          <dd className="text-right">{mon?.distance_to_stop_pct == null ? "n/a" : pct(mon.distance_to_stop_pct)}</dd>
          <dt className="text-muted">Target 1 / 2</dt>
          <dd className="text-right text-up">
            {inr(lv?.target1, 2)} / {inr(lv?.target2, 2)}
          </dd>
          <dt className="text-muted">Distance to target</dt>
          <dd className="text-right">{mon?.distance_to_target_pct == null ? "n/a" : pct(mon.distance_to_target_pct)}</dd>
          <dt className="text-muted">Trailing stop</dt>
          <dd className="text-right">{inr(lv?.trailing_stop, 2)}</dd>
          <dt className="text-muted">Suggested trail</dt>
          <dd className="text-right">{inr(mon?.suggested_trailing_stop, 2)}</dd>
          <dt className="text-muted">Levels source</dt>
          <dd className="text-right">{lv?.source ? titleCase(lv.source) : "n/a"}</dd>
        </dl>
        {p.lots?.length ? (
          <details className="text-xs">
            <summary className="cursor-pointer font-medium text-muted">Tax lots ({p.lots.length})</summary>
            <ul className="num mt-1 space-y-0.5">
              {p.lots.map((l, i) => (
                <li key={l.lot_id ?? l.id ?? i} className="flex justify-between gap-2">
                  <span>{dateIST(l.acquired_date)} · {int(l.remaining_quantity ?? l.quantity)} @ {inr(l.cost_per_share, 2)}
                    {l.is_bonus ? " (bonus)" : ""}</span>
                  <span className="text-muted">
                    {l.term ?? ""}
                    {l.days_to_ltcg != null && l.days_to_ltcg > 0 ? ` · LTCG in ${l.days_to_ltcg}d` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        {portfolioId != null ? (
          <details className="rounded-md border border-border p-2">
            <summary className="cursor-pointer text-xs font-medium">Set stop / targets</summary>
            <div className="mt-2">
              <LevelsForm portfolioId={portfolioId} position={p} />
            </div>
          </details>
        ) : null}
      </section>
    </div>
  );
}

export function HoldingsTable({ positions, portfolioId }: { positions: Position[]; portfolioId?: number | string }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!positions.length)
    return (
      <EmptyState compact title="No open holdings">
        Add a BUY transaction to start tracking a position, its P&amp;L after charges and its estimated tax.
      </EmptyState>
    );
  return (
    <TableWrap label="Holdings">
      <THead>
        <tr>
          <Th className="w-8"><span className="sr-only">Expand</span></Th>
          <Th>Stock</Th>
          <Th align="right">Qty</Th>
          <Th align="right">Avg buy</Th>
          <Th align="right">CMP</Th>
          <Th align="right">Day</Th>
          <Th align="right">Invested</Th>
          <Th align="right">Value</Th>
          <Th align="right">Gross P&amp;L</Th>
          <Th align="right">Charges</Th>
          <Th align="right">Est. tax</Th>
          <Th align="right">Net P&amp;L</Th>
          <Th>Action</Th>
        </tr>
      </THead>
      <tbody>
        {positions.map((p) => {
          const isOpen = open === p.symbol;
          const charges = (toNum(p.charges_paid) ?? 0) + (toNum(p.est_exit_charges) ?? 0);
          const hasCharges = p.charges_paid != null || p.est_exit_charges != null;
          return (
            <Fragment key={p.symbol}>
              <Tr className={cn("cursor-pointer", isOpen && "bg-surface-2/60")} onClick={() => setOpen(isOpen ? null : p.symbol)}>
                <Td>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-label={`${isOpen ? "Collapse" : "Expand"} action card for ${p.symbol}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpen(isOpen ? null : p.symbol);
                    }}
                    className="rounded p-0.5 text-muted hover:text-fg"
                  >
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  </button>
                </Td>
                <Td className="min-w-32">
                  <Link href={`/stocks/${encodeURIComponent(p.symbol)}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:text-accent hover:underline">
                    {p.symbol}
                  </Link>
                  <div className="max-w-44 truncate text-[11px] text-muted">{p.name ?? p.sector ?? ""}</div>
                </Td>
                <Td align="right">{int(p.quantity)}</Td>
                <Td align="right">{inr(p.avg_cost, 2)}</Td>
                <Td align="right">
                  <div>{inr(p.price, 2)}</div>
                  <PriceKindBadge kind={p.price_kind} />
                </Td>
                <Td align="right"><Pct value={p.day_change_pct} /></Td>
                <Td align="right"><Money value={p.invested} /></Td>
                <Td align="right"><Money value={p.current_value} /></Td>
                <Td align="right">
                  <Pnl value={p.gross_pnl} />
                  <div className="text-[11px]"><Pct value={p.gross_pnl_pct} /></div>
                </Td>
                <Td align="right">{hasCharges ? inr(charges, 2) : <span className="text-subtle">n/a</span>}</Td>
                <Td align="right" title="Estimated tax if sold today">
                  <Money value={p.est_tax_if_sold} />
                </Td>
                <Td align="right" className="font-semibold">
                  <Pnl value={p.net_pnl} />
                  <div className="text-[11px] font-normal"><Pct value={p.net_pnl_pct} /></div>
                </Td>
                <Td>
                  <MonitorActionBadge action={p.monitor?.action} severity={p.monitor?.severity} />
                </Td>
              </Tr>
              {isOpen ? (
                <tr className="bg-surface-2/30">
                  <td colSpan={13} className="border-b border-border p-0">
                    <PositionActionCard position={p} portfolioId={portfolioId} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          );
        })}
      </tbody>
    </TableWrap>
  );
}
