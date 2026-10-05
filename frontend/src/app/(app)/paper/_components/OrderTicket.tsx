"use client";

import { useState } from "react";
import { CircleCheck, Send, X } from "lucide-react";
import { usePlacePaperOrder } from "@/lib/hooks";
import { toNum } from "@/lib/format";
import type { PaperOrderIn } from "@/lib/types";
import { Badge, Button, Field, Input, Segmented } from "@/components/ui";
import { StockSearch } from "@/components/domain/StockSearch";

const EMPTY = { qty: "", limit: "", stop: "", target: "" };

export function OrderTicket({ fillPolicy }: { fillPolicy: string }) {
  const [symbol, setSymbol] = useState<{ symbol: string; name?: string | null } | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [side, setSide] = useState<PaperOrderIn["side"]>("BUY");
  const [type, setType] = useState<PaperOrderIn["order_type"]>("MARKET");
  const [f, setF] = useState(EMPTY);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [placedNote, setPlacedNote] = useState<string | null>(null);
  const place = usePlacePaperOrder();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr(null);
    setPlacedNote(null);
    const qty = toNum(f.qty);
    const limit = toNum(f.limit);
    const stop = toNum(f.stop);
    const target = toNum(f.target);
    if (!symbol) return setLocalErr("Pick a stock first.");
    if (qty === null || qty <= 0 || !Number.isInteger(qty)) return setLocalErr("Quantity must be a whole number greater than 0.");
    if (type === "LIMIT" && (limit === null || limit <= 0)) return setLocalErr("LIMIT orders need a limit price greater than 0.");
    if (stop !== null && stop <= 0) return setLocalErr("Stop must be greater than 0.");
    if (target !== null && target <= 0) return setLocalErr("Target must be greater than 0.");
    const ref = type === "LIMIT" ? limit : null;
    if (side === "BUY" && ref !== null && stop !== null && stop >= ref) return setLocalErr("For a BUY, the stop should be below the limit price.");
    if (side === "BUY" && ref !== null && target !== null && target <= ref) return setLocalErr("For a BUY, the target should be above the limit price.");
    place.mutate(
      {
        symbol: symbol.symbol,
        side,
        quantity: qty,
        order_type: type,
        limit_price: type === "LIMIT" ? limit : null,
        stop,
        target,
      },
      {
        onSuccess: (o) => {
          const note = (o as { note?: string | null } | undefined)?.note;
          setPlacedNote(`${side} ${qty} ${symbol.symbol} (${type}) placed.${note ? ` ${note}` : ""}`);
          setF(EMPTY);
          setSymbol(null);
          setSearchKey((k) => k + 1);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3" aria-label="Paper order ticket">
      <Field label="Stock" required className="col-span-2" hint={symbol ? undefined : "Search by symbol or company name"}>
        {(id) =>
          symbol ? (
            <div className="flex h-9 items-center justify-between gap-2 rounded-lg border border-border-strong bg-surface-2 px-3">
              <span id={id} className="min-w-0 truncate text-sm">
                <span className="font-semibold">{symbol.symbol}</span>
                {symbol.name ? <span className="text-muted"> · {symbol.name}</span> : null}
              </span>
              <button
                type="button"
                className="rounded p-0.5 text-muted hover:bg-surface-3 hover:text-fg"
                aria-label="Change stock"
                onClick={() => {
                  setSymbol(null);
                  setSearchKey((k) => k + 1);
                }}
              >
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <StockSearch key={searchKey} id={id} onSelect={(h) => setSymbol({ symbol: h.symbol, name: h.name })} ariaLabel="Stock for paper order" />
          )
        }
      </Field>
      <div className="col-span-2 flex flex-wrap items-center gap-3">
        <div>
          <div className="mb-1 text-xs font-medium text-muted" id="paper-side-label">
            Side
          </div>
          <Segmented label="Order side" value={side} onChange={setSide} options={[{ key: "BUY", label: "BUY" }, { key: "SELL", label: "SELL" }]} />
        </div>
        <div>
          <div className="mb-1 text-xs font-medium text-muted">Order type</div>
          <Segmented label="Order type" value={type} onChange={setType} options={[{ key: "MARKET", label: "MARKET" }, { key: "LIMIT", label: "LIMIT" }]} />
        </div>
      </div>
      <Field label="Quantity" required>
        {(id) => <Input id={id} type="number" inputMode="numeric" min={1} step={1} value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} required />}
      </Field>
      {type === "LIMIT" ? (
        <Field label="Limit price (₹)" required>
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} step="any" value={f.limit} onChange={(e) => setF({ ...f, limit: e.target.value })} required />}
        </Field>
      ) : (
        <div className="self-end pb-2 text-xs text-muted">Fills at the next available EOD price.</div>
      )}
      <Field label="Stop (₹)" hint="Optional">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} step="any" value={f.stop} onChange={(e) => setF({ ...f, stop: e.target.value })} />}
      </Field>
      <Field label="Target (₹)" hint="Optional">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} step="any" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} />}
      </Field>
      <p className="col-span-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
        <Badge tone="violet" size="xs" className="mr-1.5">
          Fill policy
        </Badge>
        {fillPolicy}
      </p>
      {localErr || place.error ? (
        <p role="alert" className="col-span-2 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {localErr ?? place.error?.message}
        </p>
      ) : null}
      {placedNote ? (
        <p role="status" className="col-span-2 flex items-start gap-1.5 rounded-lg bg-up-soft px-3 py-2 text-xs text-up">
          <CircleCheck className="mt-px size-3.5 shrink-0" aria-hidden /> {placedNote}
        </p>
      ) : null}
      <div className="col-span-2 flex justify-end">
        <Button type="submit" variant="primary" loading={place.isPending} icon={<Send className="size-4" aria-hidden />}>
          Place paper {side.toLowerCase()} order
        </Button>
      </div>
    </form>
  );
}
