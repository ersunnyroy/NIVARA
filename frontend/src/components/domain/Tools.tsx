"use client";

import { useState } from "react";
import { Calculator, Receipt } from "lucide-react";
import { useCharges, usePositionSize } from "@/lib/hooks";
import { inr, int, titleCase, toNum, todayIST } from "@/lib/format";
import type { ChargesIn, Numeric, PositionSizeOut } from "@/lib/types";
import { Button, Disclaimer, ErrorState, Field, Input, Select } from "@/components/ui";

function n(v: string): number | null {
  const x = toNum(v);
  return x;
}

function str(v: Numeric): string {
  const x = toNum(v);
  return x === null ? "" : String(x);
}

function profitLabel(p: NonNullable<PositionSizeOut["potential_profits"]>[number], i: number): React.ReactNode {
  if (p && typeof p === "object") {
    return (
      <>
        T{i + 1}
        {p.target != null ? ` @ ${inr(p.target, 2)}` : ""}: <span className="font-semibold text-up">{inr(p.profit)}</span>
        {p.rr != null ? <span className="text-muted"> (1:{p.rr})</span> : null}
      </>
    );
  }
  return (
    <>
      T{i + 1}: <span className="font-semibold text-up">{inr(p)}</span>
    </>
  );
}

/** Position-size calculator (POST /tools/position-size). Remount with a new `key` to re-prefill. */
export function PositionSizer({
  entry,
  stop,
  targets,
  capital = 1_000_000,
  riskPct = 1,
  maxPositionPct,
}: {
  entry?: Numeric;
  stop?: Numeric;
  targets?: Numeric[];
  capital?: Numeric;
  riskPct?: Numeric;
  maxPositionPct?: Numeric;
}) {
  const [f, setF] = useState({
    capital: str(capital),
    risk_pct: str(riskPct),
    entry: str(entry),
    stop: str(stop),
    targets: (targets ?? []).map(str).filter(Boolean).join(", "),
    max_position_pct: str(maxPositionPct ?? null),
  });
  const [err, setErr] = useState<string | null>(null);
  const m = usePositionSize();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const cap = n(f.capital);
    const rp = n(f.risk_pct);
    const en = n(f.entry);
    const st = n(f.stop);
    if (cap === null || rp === null || en === null || st === null) return setErr("Capital, risk %, entry and stop are required.");
    if (st >= en) return setErr("Stop must be below entry for a long position.");
    const tg = f.targets
      .split(/[,\s]+/)
      .map((x) => toNum(x))
      .filter((x): x is number => x !== null);
    const mp = n(f.max_position_pct);
    m.mutate({ capital: cap, risk_pct: rp, entry: en, stop: st, targets: tg, ...(mp !== null ? { max_position_pct: mp } : {}) });
  }

  const r = m.data;
  return (
    <div>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Capital (₹)" required>{(id) => <Input id={id} type="number" min={0} step="any" value={f.capital} onChange={set("capital")} />}</Field>
        <Field label="Risk per trade (%)" required>{(id) => <Input id={id} type="number" min={0} step="0.05" value={f.risk_pct} onChange={set("risk_pct")} />}</Field>
        <Field label="Max position (%)" hint="Optional cap">{(id) => <Input id={id} type="number" min={0} step="any" value={f.max_position_pct} onChange={set("max_position_pct")} />}</Field>
        <Field label="Entry (₹)" required>{(id) => <Input id={id} type="number" min={0} step="any" value={f.entry} onChange={set("entry")} />}</Field>
        <Field label="Stop (₹)" required>{(id) => <Input id={id} type="number" min={0} step="any" value={f.stop} onChange={set("stop")} />}</Field>
        <Field label="Targets (₹, comma-separated)">{(id) => <Input id={id} value={f.targets} onChange={set("targets")} placeholder="e.g. 1250, 1310" />}</Field>
        <div className="col-span-2 sm:col-span-3">
          <Button type="submit" variant="primary" size="sm" loading={m.isPending} icon={<Calculator className="size-3.5" aria-hidden />}>
            Calculate position size
          </Button>
        </div>
      </form>
      {err ? <p className="mt-2 text-xs text-down" role="alert">{err}</p> : null}
      {m.isError ? <ErrorState className="mt-3" error={m.error} /> : null}
      {r ? (
        <div className="mt-4 rounded-lg border border-border bg-surface-2/60 p-3 text-sm">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div><p className="text-xs text-muted">Quantity</p><p className="num text-lg font-semibold">{int(r.quantity)}</p></div>
            <div><p className="text-xs text-muted">Capital required</p><p className="num font-semibold">{inr(r.capital_required)}</p></div>
            <div><p className="text-xs text-muted">Max loss at stop</p><p className="num font-semibold text-down">{inr(r.max_loss)}</p></div>
            <div><p className="text-xs text-muted">Risk / share</p><p className="num font-semibold">{inr(r.risk_per_share, 2)}</p></div>
          </div>
          {r.potential_profits?.length ? (
            <ul className="num mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {r.potential_profits.map((p, i) => (
                <li key={i}>{profitLabel(p, i)}</li>
              ))}
            </ul>
          ) : null}
          {r.capped_by ? <p className="mt-2 text-xs text-warn">Quantity capped by: {titleCase(r.capped_by)}</p> : null}
          {r.notes?.length ? <ul className="mt-2 list-inside list-disc text-xs text-muted">{r.notes.map((x, i) => <li key={i}>{x}</li>)}</ul> : null}
          <p className="mt-2 text-[11px] text-muted">Gross figures before brokerage, statutory charges and tax. Potential profit is not a forecast.</p>
        </div>
      ) : null}
    </div>
  );
}

export function ChargesCalculator({ price, quantity }: { price?: Numeric; quantity?: Numeric }) {
  const [f, setF] = useState<{ segment: ChargesIn["segment"]; side: ChargesIn["side"]; exchange: ChargesIn["exchange"]; quantity: string; price: string; trade_date: string }>(
    () => ({ segment: "delivery", side: "BUY", exchange: "NSE", quantity: str(quantity ?? null), price: str(price ?? null), trade_date: todayIST() }),
  );
  const m = useCharges();
  const [err, setErr] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const q = toNum(f.quantity);
    const p = toNum(f.price);
    if (!q || !p) return setErr("Quantity and price are required.");
    m.mutate({ segment: f.segment, side: f.side, exchange: f.exchange, quantity: q, price: p, trade_date: f.trade_date });
  }
  const r = m.data;
  const rows: [string, Numeric][] = r
    ? [
        ["Brokerage", r.brokerage],
        ["STT", r.stt],
        ["Exchange txn", r.exchange_txn],
        ["SEBI fee", r.sebi],
        ["Stamp duty", r.stamp],
        ["GST", r.gst],
        ["DP charges", r.dp],
      ]
    : [];
  return (
    <div>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Segment">{(id) => (
          <Select id={id} value={f.segment} onChange={(e) => setF({ ...f, segment: e.target.value as ChargesIn["segment"] })}>
            <option value="delivery">Delivery</option>
            <option value="intraday">Intraday</option>
          </Select>
        )}</Field>
        <Field label="Side">{(id) => (
          <Select id={id} value={f.side} onChange={(e) => setF({ ...f, side: e.target.value as ChargesIn["side"] })}>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </Select>
        )}</Field>
        <Field label="Exchange">{(id) => (
          <Select id={id} value={f.exchange} onChange={(e) => setF({ ...f, exchange: e.target.value as ChargesIn["exchange"] })}>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </Select>
        )}</Field>
        <Field label="Quantity" required>{(id) => <Input id={id} type="number" min={1} step={1} value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} />}</Field>
        <Field label="Price (₹)" required>{(id) => <Input id={id} type="number" min={0} step="any" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />}</Field>
        <Field label="Trade date">{(id) => <Input id={id} type="date" value={f.trade_date} onChange={(e) => setF({ ...f, trade_date: e.target.value })} />}</Field>
        <div className="col-span-2 sm:col-span-3">
          <Button type="submit" size="sm" variant="outline" loading={m.isPending} icon={<Receipt className="size-3.5" aria-hidden />}>
            Estimate charges
          </Button>
        </div>
      </form>
      {err ? <p className="mt-2 text-xs text-down" role="alert">{err}</p> : null}
      {m.isError ? <ErrorState className="mt-3" error={m.error} /> : null}
      {r ? (
        <div className="mt-3 rounded-lg border border-border bg-surface-2/60 p-3">
          <dl className="num grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="text-muted">{k}</dt>
                <dd>{inr(v, 2)}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-2 font-semibold">
              <dt>Total</dt>
              <dd>{inr(r.total, 2)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-[11px] text-muted">
            Schedule: {r.schedule_name ?? "n/a"}
            {r.notes ? ` · ${Array.isArray(r.notes) ? r.notes.join("; ") : r.notes}` : ""}
          </p>
        </div>
      ) : null}
      <Disclaimer className="mt-3">Charges are estimates from the configured broker/statutory schedule; your contract note is authoritative.</Disclaimer>
    </div>
  );
}
