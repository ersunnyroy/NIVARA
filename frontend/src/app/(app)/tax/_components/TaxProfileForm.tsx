"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import { useSaveTaxProfile } from "@/lib/hooks";
import { dateTimeIST, toNum } from "@/lib/format";
import type { TaxProfile } from "@/lib/types";
import { Button, Field, Input, Select } from "@/components/ui";
import type { TaxProfileX } from "./types";

function str(v: unknown): string {
  const n = toNum(v);
  return n === null ? "" : String(n);
}

/** Empty input → null (never 0). Invalid → NaN so validation can flag it. */
function parse(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Number(s.replace(/,/g, ""));
  return Number.isFinite(n) ? n : Number.NaN;
}

function asObj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? { ...(v as Record<string, unknown>) } : {};
}

/** Mounted only once the profile has loaded; `initial` seeds the form state (remount via `key` to reset). */
/** The mutation is owned by the parent: this form remounts when the saved profile is refetched. */
export type SaveProfileMutation = ReturnType<typeof useSaveTaxProfile>;

export function TaxProfileForm({ initial, fy, save }: { initial: TaxProfileX; fy: string; save: SaveProfileMutation }) {
  const cf = asObj(initial.carried_forward);
  const br = asObj(asObj(initial.broker_reported)[fy]);
  const slab = toNum(initial.slab_rate_for_business_income);

  const [residency, setResidency] = useState<string>(initial.residency ?? "");
  const [regime, setRegime] = useState<string>(initial.regime ?? "");
  const [other, setOther] = useState(str(initial.other_taxable_income));
  const [slabPct, setSlabPct] = useState(slab === null ? "" : String(Math.round(slab * 100 * 100) / 100));
  const [stcl, setStcl] = useState(str(cf.STCL));
  const [ltcl, setLtcl] = useState(str(cf.LTCL));
  const [spec, setSpec] = useState(str(cf.SPEC));
  const [brStcg, setBrStcg] = useState(str(br.stcg ?? br.STCG));
  const [brLtcg, setBrLtcg] = useState(str(br.ltcg ?? br.LTCG));
  const [err, setErr] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const vals = {
      other: parse(other),
      slab: parse(slabPct),
      stcl: parse(stcl),
      ltcl: parse(ltcl),
      spec: parse(spec),
      brStcg: parse(brStcg),
      brLtcg: parse(brLtcg),
    };
    if (Object.values(vals).some((v) => v !== null && Number.isNaN(v))) {
      setErr("One of the amounts is not a valid number.");
      return;
    }
    if (vals.slab !== null && (vals.slab < 0 || vals.slab > 100)) {
      setErr("Slab rate must be between 0 and 100%.");
      return;
    }
    if ([vals.other, vals.stcl, vals.ltcl, vals.spec].some((v) => v !== null && v < 0)) {
      setErr("Income and carried-forward losses cannot be negative (enter loss amounts as positive numbers).");
      return;
    }

    // Preserve keys we do not edit (e.g. carried_forward.from_years, other years' broker figures).
    const carried: Record<string, unknown> = { ...cf };
    for (const [k, v] of [["STCL", vals.stcl], ["LTCL", vals.ltcl], ["SPEC", vals.spec]] as const) {
      if (v === null) delete carried[k];
      else carried[k] = v;
    }
    const brokerAll = asObj(initial.broker_reported);
    const brokerFy: Record<string, unknown> = { ...br };
    for (const [k, v] of [["stcg", vals.brStcg], ["ltcg", vals.brLtcg]] as const) {
      delete brokerFy[k.toUpperCase()];
      if (v === null) delete brokerFy[k];
      else brokerFy[k] = v;
    }
    if (Object.keys(brokerFy).length) brokerAll[fy] = brokerFy;
    else delete brokerAll[fy];

    const body = {
      residency: residency || null,
      regime: regime || null,
      other_taxable_income: vals.other,
      slab_rate_for_business_income: vals.slab === null ? null : vals.slab / 100,
      carried_forward: carried,
      // The backend PUT replaces every field, so broker_reported must always be sent back.
      broker_reported: brokerAll,
    };
    save.mutate(body as unknown as TaxProfile);
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Residency" hint="Missing facts mark the estimate incomplete.">
          {(id) => (
            <Select id={id} value={residency} onChange={(e) => setResidency(e.target.value)}>
              <option value="">Not set</option>
              <option value="resident">Resident</option>
              <option value="nri">NRI</option>
            </Select>
          )}
        </Field>
        <Field label="Tax regime">
          {(id) => (
            <Select id={id} value={regime} onChange={(e) => setRegime(e.target.value)}>
              <option value="">Not set</option>
              <option value="new">New regime</option>
              <option value="old">Old regime</option>
            </Select>
          )}
        </Field>
        <Field label="Other taxable income (₹)" hint="Excluding these capital gains. Leave blank if unknown.">
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={other} onChange={(e) => setOther(e.target.value)} />}
        </Field>
        <Field label="Slab rate for business / speculative income (%)" hint="e.g. 30 for 30%. Stored as a fraction.">
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0} max={100} step="any" value={slabPct} onChange={(e) => setSlabPct(e.target.value)} />}
        </Field>
        <Field label="Carried-forward short-term loss (STCL, ₹)">
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={stcl} onChange={(e) => setStcl(e.target.value)} />}
        </Field>
        <Field label="Carried-forward long-term loss (LTCL, ₹)">
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={ltcl} onChange={(e) => setLtcl(e.target.value)} />}
        </Field>
        <Field label="Carried-forward speculative loss (₹)">
          {(id) => <Input id={id} type="number" inputMode="decimal" min={0} step="any" value={spec} onChange={(e) => setSpec(e.target.value)} />}
        </Field>
        <Field label={`Broker-reported STCG for FY ${fy} (₹)`} hint="Optional — from your broker's tax P&L, for comparison.">
          {(id) => <Input id={id} type="number" inputMode="decimal" step="any" value={brStcg} onChange={(e) => setBrStcg(e.target.value)} />}
        </Field>
        <Field label={`Broker-reported LTCG for FY ${fy} (₹)`}>
          {(id) => <Input id={id} type="number" inputMode="decimal" step="any" value={brLtcg} onChange={(e) => setBrLtcg(e.target.value)} />}
        </Field>
      </div>
      {err || save.error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {err ?? save.error?.message}
        </p>
      ) : null}
      {save.isSuccess ? (
        <p role="status" className="rounded-lg bg-up-soft px-3 py-2 text-xs text-up">
          Tax profile saved. Estimates have been refreshed.
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-muted">Last updated: {initial.updated_at ? dateTimeIST(initial.updated_at) : "never"}</p>
        <Button type="submit" variant="primary" loading={save.isPending} icon={<Save className="size-4" aria-hidden />}>
          Save tax profile
        </Button>
      </div>
    </form>
  );
}
