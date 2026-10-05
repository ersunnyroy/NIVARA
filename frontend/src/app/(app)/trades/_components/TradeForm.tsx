"use client";

import { useState } from "react";
import { Save, Trash2, X } from "lucide-react";
import { useCreateTrade, usePortfolios, useUpdateTrade } from "@/lib/hooks";
import { todayIST, toNum } from "@/lib/format";
import type { Numeric, Trade, TradeIn } from "@/lib/types";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { StockSearch } from "@/components/domain/StockSearch";
import { useDeleteTrade } from "./useDeleteTrade";

/** Trade as returned by the backend (adds portfolio_id and name). */
export type TradeX = Trade & { portfolio_id?: number | null; name?: string | null };

/** Backend TradeIn additionally requires portfolio_id (not in types.ts). */
type TradeInX = TradeIn & { portfolio_id: number };

/** Kinds a user may set; "system" trades are created by the model only. */
export const EDITABLE_KINDS = ["live", "paper", "user"] as const;

const REGIMES = ["", "STRONG BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG BEARISH"];

function s(v: Numeric): string {
  const n = toNum(v);
  return n === null ? "" : String(n);
}

function initial(trade?: TradeX) {
  return {
    portfolio_id: trade?.portfolio_id != null ? String(trade.portfolio_id) : "",
    symbol: trade?.symbol ?? trade?.stock ?? "",
    kind: (trade?.kind && (EDITABLE_KINDS as readonly string[]).includes(trade.kind) ? trade.kind : "live") as string,
    entry_date: trade?.entry_date ?? todayIST(),
    entry_price: s(trade?.entry_price),
    quantity: s(trade?.quantity),
    stop: s(trade?.stop),
    target: s(trade?.target),
    exit_date: trade?.exit_date ?? "",
    exit_price: s(trade?.exit_price),
    reason_entry: trade?.reason_entry ?? "",
    reason_exit: trade?.reason_exit ?? "",
    market_regime: trade?.market_regime ?? "",
    score_at_entry: s(trade?.score_at_entry),
    charges: s(trade?.charges),
    notes: trade?.notes ?? "",
  };
}

type FormState = ReturnType<typeof initial>;

/**
 * Add / edit form. Mount with `key={trade?.id ?? "new"}` so the initial state is seeded per trade
 * (no props→state syncing in effects).
 */
export function TradeForm({ trade, onDone, onCancel }: { trade?: TradeX; onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState<FormState>(() => initial(trade));
  const [localErr, setLocalErr] = useState<string | null>(null);
  const portfolios = usePortfolios();
  const create = useCreateTrade();
  const update = useUpdateTrade();
  const del = useDeleteTrade();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const mut = trade ? update : create;
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => ({ ...p, [k]: v }));

  const eligible = (portfolios.data ?? []).filter((p) => p.kind !== "model");
  const portfolioId = f.portfolio_id || (eligible.length === 1 ? String(eligible[0].id) : "");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr(null);
    const pid = toNum(portfolioId);
    const entry = toNum(f.entry_price);
    const qty = toNum(f.quantity);
    const exitPrice = toNum(f.exit_price);
    const score = toNum(f.score_at_entry);
    const charges = toNum(f.charges);
    if (pid === null) return setLocalErr("Choose the portfolio this trade belongs to.");
    if (!f.symbol.trim()) return setLocalErr("Pick a stock.");
    if (!f.entry_date) return setLocalErr("Entry date is required.");
    if (entry === null || entry <= 0) return setLocalErr("Entry price must be greater than 0.");
    if (qty === null || qty <= 0) return setLocalErr("Quantity must be greater than 0.");
    if ((f.exit_date && exitPrice === null) || (!f.exit_date && exitPrice !== null))
      return setLocalErr("To close a trade, enter both exit date and exit price (leave both empty for an open trade).");
    if (exitPrice !== null && exitPrice <= 0) return setLocalErr("Exit price must be greater than 0.");
    if (f.exit_date && f.exit_date < f.entry_date) return setLocalErr("Exit date cannot be before the entry date.");
    if (charges !== null && charges < 0) return setLocalErr("Charges cannot be negative.");
    if (score !== null && (score < 0 || score > 100)) return setLocalErr("Score at entry must be between 0 and 100.");

    const body: TradeInX = {
      portfolio_id: pid,
      symbol: f.symbol.trim().toUpperCase(),
      kind: f.kind,
      entry_date: f.entry_date,
      entry_price: entry,
      quantity: qty,
      stop: toNum(f.stop),
      target: toNum(f.target),
      exit_date: f.exit_date || null,
      exit_price: exitPrice,
      reason_entry: f.reason_entry.trim() || null,
      reason_exit: f.reason_exit.trim() || null,
      market_regime: f.market_regime || null,
      score_at_entry: score,
      charges,
      notes: f.notes.trim() || null,
    };
    if (trade) update.mutate({ id: trade.id, body }, { onSuccess: onDone });
    else create.mutate(body, { onSuccess: onDone });
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label={trade ? "Edit trade" : "Add trade"}>
      <Field label="Stock" required>
        {(id) =>
          trade ? (
            <Input id={id} value={f.symbol} readOnly disabled aria-readonly />
          ) : f.symbol ? (
            <div className="flex h-9 items-center justify-between gap-2 rounded-lg border border-border-strong bg-surface-2 px-3">
              <span id={id} className="text-sm font-semibold">
                {f.symbol}
              </span>
              <button type="button" className="rounded p-0.5 text-muted hover:bg-surface-3 hover:text-fg" aria-label="Change stock" onClick={() => set("symbol", "")}>
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <StockSearch id={id} onSelect={(h) => set("symbol", h.symbol)} ariaLabel="Stock" />
          )
        }
      </Field>
      <Field
        label="Portfolio"
        required
        error={portfolios.isError ? portfolios.error.message : undefined}
        hint={!portfolios.isPending && eligible.length === 0 ? "Create a portfolio first on the Portfolio page." : undefined}
      >
        {(id) => (
          <Select id={id} value={portfolioId} onChange={(e) => set("portfolio_id", e.target.value)} required disabled={portfolios.isPending}>
            <option value="">{portfolios.isPending ? "Loading…" : "Select portfolio"}</option>
            {eligible.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.kind ? ` (${p.kind})` : ""}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Kind" required hint="live = real money · paper = simulated · user = your own tag">
        {(id) => (
          <Select id={id} value={f.kind} onChange={(e) => set("kind", e.target.value)}>
            {EDITABLE_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Market regime at entry">
        {(id) => (
          <Select id={id} value={f.market_regime} onChange={(e) => set("market_regime", e.target.value)}>
            {Array.from(new Set([...REGIMES, f.market_regime])).map((r) => (
              <option key={r || "none"} value={r}>
                {r ? r.replace(/_/g, " ") : "Not recorded"}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Entry date" required>
        {(id) => <Input id={id} type="date" value={f.entry_date} onChange={(e) => set("entry_date", e.target.value)} required />}
      </Field>
      <Field label="Entry price (₹)" required>
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} step="any" value={f.entry_price} onChange={(e) => set("entry_price", e.target.value)} required />}
      </Field>
      <Field label="Quantity" required>
        {(id) => <Input id={id} type="number" inputMode="numeric" min={1} step="any" value={f.quantity} onChange={(e) => set("quantity", e.target.value)} required />}
      </Field>
      <Field label="Score at entry" hint="0–100, optional">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0} max={100} step="any" value={f.score_at_entry} onChange={(e) => set("score_at_entry", e.target.value)} />}
      </Field>
      <Field label="Stop (₹)">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={f.stop} onChange={(e) => set("stop", e.target.value)} />}
      </Field>
      <Field label="Target (₹)">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={f.target} onChange={(e) => set("target", e.target.value)} />}
      </Field>
      <Field label="Exit date" hint="Leave empty while the trade is open">
        {(id) => <Input id={id} type="date" value={f.exit_date} min={f.entry_date || undefined} onChange={(e) => set("exit_date", e.target.value)} />}
      </Field>
      <Field label="Exit price (₹)">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} step="any" value={f.exit_price} onChange={(e) => set("exit_price", e.target.value)} />}
      </Field>
      <Field label="Charges (₹)" hint="Leave empty to estimate from the charge schedule" className="sm:col-span-2">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={f.charges} onChange={(e) => set("charges", e.target.value)} />}
      </Field>
      <Field label="Reason for entry" className="sm:col-span-2">
        {(id) => <Textarea id={id} rows={2} maxLength={4000} value={f.reason_entry} onChange={(e) => set("reason_entry", e.target.value)} />}
      </Field>
      <Field label="Reason for exit" className="sm:col-span-2">
        {(id) => <Textarea id={id} rows={2} maxLength={4000} value={f.reason_exit} onChange={(e) => set("reason_exit", e.target.value)} />}
      </Field>
      <Field label="Notes" className="sm:col-span-2">
        {(id) => <Textarea id={id} rows={2} maxLength={8000} value={f.notes} onChange={(e) => set("notes", e.target.value)} />}
      </Field>
      {localErr || mut.error || del.error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down sm:col-span-2">
          {localErr ?? mut.error?.message ?? (del.error ? `Delete failed: ${del.error.message}` : null)}
        </p>
      ) : null}
      <p className="text-xs text-muted sm:col-span-2">
        Gross P&amp;L, charges, estimated tax and net P&amp;L are computed by the server when the trade is closed.
      </p>
      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3 sm:col-span-2">
        {trade ? (
          <div className="mr-auto flex items-center gap-2">
            {confirmDelete ? (
              <>
                <span className="text-xs text-down">Delete this trade permanently?</span>
                <Button
                  type="button"
                  variant="danger"
                  size="sm"
                  loading={del.isPending}
                  onClick={() => del.mutate(trade.id, { onSuccess: onDone })}
                >
                  Yes, delete
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                  Keep
                </Button>
              </>
            ) : (
              <Button type="button" variant="ghost" size="sm" icon={<Trash2 className="size-3.5" aria-hidden />} onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            )}
          </div>
        ) : null}
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={mut.isPending} icon={<Save className="size-4" aria-hidden />}>
          {trade ? "Save changes" : "Add trade"}
        </Button>
      </div>
    </form>
  );
}
