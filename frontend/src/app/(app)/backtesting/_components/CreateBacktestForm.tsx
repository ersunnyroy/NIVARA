"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { useCreateBacktest } from "@/lib/hooks";
import { todayIST, toNum } from "@/lib/format";
import type { BacktestIn } from "@/lib/types";
import { Button, Field, Input, Select } from "@/components/ui";

const STRATEGIES: { key: BacktestIn["strategy"]; label: string; hint: string }[] = [
  { key: "ranking", label: "Ranking", hint: "Buy the top-N ranked opportunities each session" },
  { key: "breakout", label: "Breakout", hint: "Breakouts from consolidation on volume" },
  { key: "momentum", label: "Momentum", hint: "Relative-strength / trend-following" },
  { key: "mean_reversion", label: "Mean reversion", hint: "Pullbacks within an uptrend" },
  { key: "combined", label: "Combined", hint: "Blend of all setups using the scoring model" },
];

// The engine selects a point-in-time liquid universe each day (avoids survivorship bias from today's index lists).
const UNIVERSES = ["liquid_pit"];

function shiftYears(iso: string, years: number): string {
  const [y, m, d] = iso.split("-");
  return `${Number(y) + years}-${m}-${d === "29" && m === "02" ? "28" : d}`;
}

function initialForm() {
  const today = todayIST();
  return {
    name: "",
    strategy: "combined" as BacktestIn["strategy"],
    start_date: shiftYears(today, -3),
    end_date: today,
    capital: "1000000",
    risk_pct: "1",
    max_positions: "8",
    slippage_bps: "10",
    top_n: "5",
    universe: "liquid_pit",
  };
}

export function CreateBacktestForm({ onCreated }: { onCreated: (id: number) => void }) {
  const [f, setF] = useState(initialForm);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const create = useCreateBacktest();
  const set = <K extends keyof ReturnType<typeof initialForm>>(k: K, v: ReturnType<typeof initialForm>[K]) =>
    setF((prev) => ({ ...prev, [k]: v }));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr(null);
    const capital = toNum(f.capital);
    const risk = toNum(f.risk_pct);
    const maxPos = toNum(f.max_positions);
    const slip = toNum(f.slippage_bps);
    const topN = toNum(f.top_n);
    if (!f.name.trim()) return setLocalErr("Give the backtest a name.");
    if (!f.start_date || !f.end_date || f.end_date <= f.start_date) return setLocalErr("End date must be after the start date.");
    if (capital === null || capital <= 0) return setLocalErr("Capital must be a positive amount.");
    if (risk === null || risk <= 0 || risk > 10) return setLocalErr("Risk per trade must be between 0 and 10%.");
    if (maxPos === null || maxPos < 1 || !Number.isInteger(maxPos)) return setLocalErr("Max positions must be a whole number ≥ 1.");
    if (slip === null || slip < 0) return setLocalErr("Slippage must be ≥ 0 bps.");
    if (topN === null || topN < 1 || !Number.isInteger(topN)) return setLocalErr("Top N must be a whole number ≥ 1.");
    if (!f.universe.trim()) return setLocalErr("Choose a universe.");
    create.mutate(
      {
        name: f.name.trim(),
        strategy: f.strategy,
        start_date: f.start_date,
        end_date: f.end_date,
        params: { capital, risk_pct: risk, max_positions: maxPos, slippage_bps: slip, top_n: topN },
        universe: f.universe.trim(),
      },
      {
        onSuccess: (bt) => {
          if (bt && typeof bt.id === "number") onCreated(bt.id);
          setF((prev) => ({ ...prev, name: "" }));
        },
      },
    );
  }

  const strat = STRATEGIES.find((s) => s.key === f.strategy);

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3" aria-label="Create backtest">
      <Field label="Name" required className="col-span-2">
        {(id) => <Input id={id} value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Combined 3y, 1% risk" required maxLength={120} />}
      </Field>
      <Field label="Strategy" required className="col-span-2" hint={strat?.hint}>
        {(id) => (
          <Select id={id} value={f.strategy} onChange={(e) => set("strategy", e.target.value as BacktestIn["strategy"])}>
            {STRATEGIES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Start date" required>
        {(id) => <Input id={id} type="date" value={f.start_date} onChange={(e) => set("start_date", e.target.value)} required />}
      </Field>
      <Field label="End date" required>
        {(id) => <Input id={id} type="date" value={f.end_date} onChange={(e) => set("end_date", e.target.value)} required />}
      </Field>
      <Field label="Capital (₹)" required>
        {(id) => <Input id={id} type="number" inputMode="decimal" min={1} step="any" value={f.capital} onChange={(e) => set("capital", e.target.value)} required />}
      </Field>
      <Field label="Risk per trade (%)" required>
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0.01} max={10} step="any" value={f.risk_pct} onChange={(e) => set("risk_pct", e.target.value)} required />}
      </Field>
      <Field label="Max positions" required>
        {(id) => <Input id={id} type="number" inputMode="numeric" min={1} step={1} value={f.max_positions} onChange={(e) => set("max_positions", e.target.value)} required />}
      </Field>
      <Field label="Top N per session" required>
        {(id) => <Input id={id} type="number" inputMode="numeric" min={1} step={1} value={f.top_n} onChange={(e) => set("top_n", e.target.value)} required />}
      </Field>
      <Field label="Slippage (bps)" required hint="10 bps = 0.10% per side">
        {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={f.slippage_bps} onChange={(e) => set("slippage_bps", e.target.value)} required />}
      </Field>
      <Field label="Universe" required>
        {(id) => (
          <>
            <Input id={id} list={`${id}-list`} value={f.universe} onChange={(e) => set("universe", e.target.value)} required />
            <datalist id={`${id}-list`}>
              {UNIVERSES.map((u) => (
                <option key={u} value={u} />
              ))}
            </datalist>
          </>
        )}
      </Field>
      {localErr || create.error ? (
        <p role="alert" className="col-span-2 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {localErr ?? create.error?.message}
        </p>
      ) : null}
      <div className="col-span-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">Data is split chronologically into train / validation / out-of-sample test.</p>
        <Button type="submit" variant="primary" loading={create.isPending} icon={<Play className="size-4" aria-hidden />}>
          Run backtest
        </Button>
      </div>
    </form>
  );
}
