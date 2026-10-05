"use client";

import { useState } from "react";
import { BellPlus, X } from "lucide-react";
import { useCreateAlert } from "@/lib/hooks";
import type { AlertType, StockSearchHit } from "@/lib/types";
import { StockSearch } from "@/components/domain/StockSearch";
import { Button, Checkbox, Field, Input, Select } from "@/components/ui";
import { ALERT_TYPE_KEYS, ALERT_TYPES, CHANNELS } from "./alertTypes";

function defaultsFor(t: AlertType): Record<string, string> {
  return Object.fromEntries(ALERT_TYPES[t].params.map((p) => [p.key, p.defaultValue ?? ""]));
}

export function CreateAlertForm({ serverTypes }: { serverTypes?: string[] }) {
  const create = useCreateAlert();
  const types = serverTypes?.length ? ALERT_TYPE_KEYS.filter((k) => serverTypes.includes(k)) : ALERT_TYPE_KEYS;
  const [type, setType] = useState<AlertType>("price_above");
  const [stock, setStock] = useState<StockSearchHit | null>(null);
  const [params, setParams] = useState<Record<string, string>>(() => defaultsFor("price_above"));
  const [channels, setChannels] = useState<string[]>(["in_app"]);
  const [cooldownH, setCooldownH] = useState("24");
  const [err, setErr] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const spec = ALERT_TYPES[type];

  function changeType(t: AlertType) {
    setType(t);
    setParams(defaultsFor(t));
    setErr(null);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setCreated(null);
    if (spec.needsSymbol && !stock) {
      setErr("Choose a stock for this alert type.");
      return;
    }
    const out: Record<string, number> = {};
    for (const p of spec.params) {
      const raw = (params[p.key] ?? "").trim();
      if (!raw) {
        if (p.required) {
          setErr(`${p.label} is required.`);
          return;
        }
        continue;
      }
      const n = Number(raw);
      if (!Number.isFinite(n) || (p.min !== undefined && n < p.min)) {
        setErr(`${p.label} must be a number${p.min !== undefined ? ` ≥ ${p.min}` : ""}.`);
        return;
      }
      out[p.key] = n;
    }
    if (type === "entry_zone" && out.entry_low !== undefined && out.entry_high !== undefined && out.entry_low > out.entry_high) {
      setErr("Entry low must not exceed entry high.");
      return;
    }
    if (!channels.length) {
      setErr("Select at least one delivery channel.");
      return;
    }
    const cd = Number(cooldownH);
    if (!Number.isFinite(cd) || cd * 60 < 5 || cd > 24 * 30) {
      setErr("Cooldown must be between 0.1 and 720 hours.");
      return;
    }
    const body = {
      symbol: spec.needsSymbol ? (stock?.symbol ?? null) : null,
      alert_type: type,
      params: out,
      channels,
      cooldown_minutes: Math.round(cd * 60),
    };
    create.mutate(body, {
      onSuccess: () => {
        setCreated(`${spec.label}${body.symbol ? ` for ${body.symbol}` : ""}`);
        setStock(null);
        setParams(defaultsFor(type));
      },
    });
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="Alert type" required hint={spec.description}>
        {(id) => (
          <Select id={id} value={type} onChange={(e) => changeType(e.target.value as AlertType)}>
            {types.map((k) => (
              <option key={k} value={k}>
                {ALERT_TYPES[k].label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      {spec.needsSymbol ? (
        <Field label="Stock" required>
          {(id) =>
            stock ? (
              <div className="flex h-9 items-center justify-between gap-2 rounded-lg border border-border-strong bg-surface-2 px-3 text-sm">
                <span className="min-w-0 truncate">
                  <span className="font-semibold">{stock.symbol}</span>
                  {stock.name ? <span className="text-muted"> · {stock.name}</span> : null}
                </span>
                <button
                  id={id}
                  type="button"
                  className="rounded p-0.5 text-muted hover:text-fg"
                  onClick={() => setStock(null)}
                  aria-label={`Clear selected stock ${stock.symbol}`}
                >
                  <X className="size-4" aria-hidden />
                </button>
              </div>
            ) : (
              <StockSearch id={id} ariaLabel="Stock for this alert" onSelect={(h) => setStock(h)} />
            )
          }
        </Field>
      ) : (
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">Market-wide alert — no stock needed.</p>
      )}

      {spec.params.length ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {spec.params.map((p) => (
            <Field key={`${type}-${p.key}`} label={p.label} required={p.required} hint={p.hint}>
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  inputMode="decimal"
                  min={p.min}
                  step={p.step}
                  required={p.required}
                  value={params[p.key] ?? ""}
                  onChange={(e) => setParams((s) => ({ ...s, [p.key]: e.target.value }))}
                />
              )}
            </Field>
          ))}
        </div>
      ) : null}

      <fieldset>
        <legend className="mb-1 text-xs font-medium text-muted">Delivery channels</legend>
        <div className="flex flex-wrap gap-4">
          {CHANNELS.map((c) => (
            <Checkbox
              key={c.key}
              label={c.label}
              checked={channels.includes(c.key)}
              onChange={(v) => setChannels((s) => (v ? [...s, c.key] : s.filter((x) => x !== c.key)))}
            />
          ))}
        </div>
        <p className="mt-1 text-[11px] text-subtle">Email and webhook delivery only work if an administrator has configured them.</p>
      </fieldset>

      <Field label="Cooldown (hours)" hint="Minimum time between repeat notifications for this rule.">
        {(id) => (
          <Input id={id} type="number" inputMode="decimal" min={0.1} max={720} step="any" value={cooldownH} onChange={(e) => setCooldownH(e.target.value)} className="sm:w-40" />
        )}
      </Field>

      {err || create.error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {err ?? create.error?.message}
        </p>
      ) : null}
      {created && !create.isPending ? (
        <p role="status" className="rounded-lg bg-up-soft px-3 py-2 text-xs text-up">
          Alert created: {created}.
        </p>
      ) : null}
      <Button type="submit" variant="primary" loading={create.isPending} icon={<BellPlus className="size-4" aria-hidden />} className="w-full sm:w-auto">
        Create alert
      </Button>
      <p className="text-[11px] text-muted">Alerts are evaluated on the server after data refreshes (EOD prices unless a live provider is configured).</p>
    </form>
  );
}
