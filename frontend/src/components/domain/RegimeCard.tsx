"use client";

import { Gauge } from "lucide-react";
import { num, titleCase, toNum } from "@/lib/format";
import type { Regime, RegimeComponent } from "@/lib/types";
import { Card, CardBody, CardHeader, DataStamp, DataUnavailable, Stat, cn } from "@/components/ui";
import { Confidence, RegimeBadge } from "./badges";

export function regimeComponents(r?: Regime | null): RegimeComponent[] {
  const c = r?.components;
  if (!c) return [];
  if (Array.isArray(c)) return c;
  return c.items ?? [];
}

function norm(v: number | null | undefined): number | null {
  const n = toNum(v);
  if (n === null) return null;
  return Math.abs(n) <= 1 ? n * 100 : n;
}

/** Diverging bar centred at 0 (−100..+100) with explicit signed value. */
function VoteBar({ score }: { score: number | null }) {
  const s = score === null ? null : Math.max(-100, Math.min(100, score));
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-28 rounded-full bg-surface-3" aria-hidden>
        <span className="absolute left-1/2 top-[-2px] h-3 w-px bg-border-strong" />
        {s !== null ? (
          <span
            className={cn("absolute top-0 h-2", s >= 0 ? "rounded-r-full bg-up" : "rounded-l-full bg-down")}
            style={s >= 0 ? { left: "50%", width: `${s / 2}%` } : { right: "50%", width: `${-s / 2}%` }}
          />
        ) : null}
      </div>
      <span className={cn("num w-10 text-right text-xs font-semibold", s === null ? "text-subtle" : s > 0 ? "text-up" : s < 0 ? "text-down" : "text-muted")}>
        {s === null ? "n/a" : `${s > 0 ? "+" : s < 0 ? "−" : ""}${num(Math.abs(s), 0)}`}
      </span>
    </div>
  );
}

export function RegimeCard({ regime, compact, className }: { regime?: Regime | null; compact?: boolean; className?: string }) {
  const comps = regimeComponents(regime);
  const missing = regime?.missing_inputs ?? [];
  return (
    <Card className={className}>
      <CardHeader
        icon={<Gauge className="size-4" />}
        title="Market regime"
        subtitle="Weighted vote of independent inputs — never a single indicator"
        href={compact ? "/market" : undefined}
        hrefLabel="Market details"
      />
      <CardBody>
        {!regime || !regime.regime ? (
          <DataUnavailable
            message="No market regime has been computed yet."
            hint="An admin can run the EOD ingestion and regime jobs from Settings → Jobs."
          />
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row lg:gap-6">
            <div className="grid shrink-0 grid-cols-2 gap-4 lg:w-80">
              <div className="col-span-2">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Regime</p>
                <div className="mt-1 flex items-center gap-2">
                  <RegimeBadge regime={regime.regime} className="!px-2.5 !py-1 !text-sm" />
                  <span className="num text-xs text-muted">composite {regime.score == null ? "n/a" : `${(toNum(regime.score) ?? 0) > 0 ? "+" : ""}${num(regime.score, 0)}`} (−100…+100)</span>
                </div>
              </div>
              <Stat label="Confidence" value={<Confidence value={regime.confidence} />} />
              <Stat
                label="Recommended exposure"
                value={regime.recommended_exposure_pct == null ? "n/a" : `${num(regime.recommended_exposure_pct, 0)}%`}
                sub="of deployable capital"
              />
              <Stat label="Max positions" value={regime.max_positions ?? "n/a"} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted">Component votes</p>
              {comps.length ? (
                <ul className={cn("grid gap-x-6 gap-y-1.5", compact ? "sm:grid-cols-2" : "")}>
                  {comps.map((c) => {
                    const sc = norm(c.score);
                    return (
                      <li key={c.name} className="flex items-center justify-between gap-3 text-xs" title={c.reason ?? undefined}>
                        <span className="min-w-0">
                          <span className="font-medium text-fg">{titleCase(c.name)}</span>
                          {c.weight != null ? <span className="num ml-1 text-subtle">w {num(norm(c.weight) ?? 0, 0)}%</span> : null}
                          {!compact && c.reason ? <span className="block truncate text-muted">{c.reason}</span> : null}
                        </span>
                        <VoteBar score={sc} />
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-xs text-muted">No component detail reported.</p>
              )}
              {missing.length ? (
                <p className="mt-2 text-[11px] text-warn">
                  Missing inputs (excluded, not counted as zero): {missing.map(titleCase).join(", ")}
                </p>
              ) : null}
            </div>
          </div>
        )}
        <DataStamp className="mt-3" asOf={regime?.data_as_of ?? regime?.session_date} source={regime?.model_version ? `NIVARA regime model ${regime.model_version}` : undefined} />
      </CardBody>
    </Card>
  );
}
