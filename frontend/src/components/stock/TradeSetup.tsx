"use client";

import { Ban, Calculator, Receipt, ShieldX, TrendingUp } from "lucide-react";
import { useSettings, useTechnical } from "@/lib/hooks";
import { holding, inr, pct, rr, titleCase, toNum } from "@/lib/format";
import type { Numeric, Recommendation, ScoreBreakdown as ScoreBreakdownT, TechnicalSetup } from "@/lib/types";
import { ChargesCalculator, PositionSizer } from "@/components/domain/Tools";
import { ActionBadge, Confidence, ScorePill, SuitabilityBadge } from "@/components/domain/badges";
import { ScoreBreakdown } from "@/components/domain/ScoreBreakdown";
import { Card, CardBody, CardHeader, DataStamp, DataStatusBanner, Disclaimer, EmptyState, QueryState, SkeletonRows, cn } from "@/components/ui";

function Level({
  label,
  value,
  value2,
  method,
  tone,
  extra,
  icon,
}: {
  label: string;
  value: Numeric;
  value2?: Numeric;
  method?: string;
  tone?: "up" | "down" | "warn";
  extra?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  const missing = toNum(value) === null;
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {icon}
        {label}
      </p>
      <p className={cn("num mt-1 text-base font-semibold", missing ? "text-subtle" : tone === "up" ? "text-up" : tone === "down" ? "text-down" : tone === "warn" ? "text-warn" : "")}>
        {missing ? "n/a" : value2 !== undefined ? `${inr(value, 2)} – ${inr(value2, 2)}` : inr(value, 2)}
        {extra ? <span className="ml-1 text-xs font-normal">{extra}</span> : null}
      </p>
      {method ? <p className="mt-1 text-[11px] leading-relaxed text-muted">{method}</p> : null}
    </div>
  );
}

function rewardPct(s: Partial<Recommendation>, i: number): React.ReactNode {
  const v = s.reward_pcts?.[i];
  return v == null ? null : <span className="text-up">{pct(v)}</span>;
}

type NormSetup = Partial<Recommendation> & {
  breakdown?: ScoreBreakdownT | null;
  valid?: boolean;
  rejections?: string[];
  rejected?: boolean;
  rejection_reasons?: string[];
};

/** /technical returns level fields with slightly different names than a published Recommendation. */
function normalizeSetup(t: TechnicalSetup): NormSetup {
  const breakdown = t.score && typeof t.score === "object" ? t.score : (t.score_breakdown ?? null);
  const score = typeof t.score === "number" ? t.score : (breakdown?.total ?? null);
  return {
    ...t,
    score,
    breakdown,
    rr: t.rr ?? t.rr_t2 ?? null,
    holding_min_sessions: t.holding_min_sessions ?? t.holding_min ?? null,
    holding_max_sessions: t.holding_max_sessions ?? t.holding_max ?? null,
    methodology: { ...(t.methodology ?? {}), confidence_notes: t.methodology?.confidence_notes ?? t.confidence_notes },
  };
}

export function TradeSetupPanel({ symbol }: { symbol: string }) {
  const q = useTechnical(symbol);
  const settings = useSettings();
  const rl = (settings.data?.config?.risk_limits ?? settings.data?.risk_limits ?? {}) as Record<string, unknown>;
  return (
    <QueryState query={q} skeleton={<SkeletonRows rows={6} className="p-4" />} unavailableHint="Setups are computed after EOD ingestion.">
      {(t) => {
        const s = t.setup ? normalizeSetup(t.setup) : null;
        if (!s || toNum(s.entry_low) === null) {
          return (
            <div className="space-y-4">
              <DataStatusBanner status={t.status} message={t.message ?? undefined} />
              <EmptyState title="No active trade setup">
                The model does not currently see a valid setup for {symbol} (or the data is insufficient). That is a decision too — no trade.
              </EmptyState>
              <Card>
                <CardHeader icon={<Calculator className="size-4" />} title="Position-size calculator" />
                <CardBody>
                  <PositionSizer key={`${symbol}-empty`} capital={rl.capital as number} riskPct={rl.risk_per_trade_pct as number} maxPositionPct={rl.max_single_stock_pct as number} />
                </CardBody>
              </Card>
            </div>
          );
        }
        const m = s.methodology ?? {};
        const stale = t.status === "data_stale";
        return (
          <div className="space-y-4">
            <DataStatusBanner status={t.status} message={t.message ?? undefined} />
            <Card>
              <CardHeader
                icon={<TrendingUp className="size-4" />}
                title={`Trade setup — ${titleCase(s.setup)}`}
                subtitle={s.strategy ? `Strategy: ${titleCase(s.strategy)}` : undefined}
                actions={
                  <div className="flex flex-wrap items-center gap-2">
                    <ScorePill value={s.score} />
                    {stale ? <span className="text-[11px] font-semibold uppercase text-warn">Action disabled (stale)</span> : <ActionBadge action={s.action} />}
                    {s.suitability ? <SuitabilityBadge value={s.suitability} /> : <span className="text-[11px] text-muted">on-demand (not in Top 10)</span>}
                  </div>
                }
              />
              <CardBody className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Level label="Aggressive entry" value={s.aggressive_entry} method="Near CMP — accepts more risk for not missing the move." />
                  <Level label="Preferred entry zone" value={s.entry_low} value2={s.entry_high} method={m.entry} />
                  <Level label="Conservative zone" value={s.conservative_low} value2={s.conservative_high} method="Deeper pullback entry — better R:R, may not fill." />
                  <Level label="Do not chase above" value={s.no_chase_above} tone="warn" icon={<Ban className="size-3" aria-hidden />} method={m.no_chase} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Level label="Stop loss" value={s.stop} tone="down" icon={<ShieldX className="size-3" aria-hidden />} method={m.stop} extra={s.risk_pct != null ? <span className="text-down">{pct(-Math.abs(s.risk_pct))}</span> : null} />
                  <Level label="Trailing stop after T1" value={s.trailing_stop_after_t1} method={m.trailing} />
                  <Level label="Target 1" value={s.target1} tone="up" method={m.target1} extra={rewardPct(s, 0)} />
                  <Level label="Target 2" value={s.target2} tone="up" method={m.target2} extra={rewardPct(s, 1)} />
                  <Level label="Target 3" value={s.target3} tone="up" method={m.target3} extra={rewardPct(s, 2)} />
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Reward : risk</p>
                    <p className="num mt-1 text-base font-semibold">{rr(s.rr)}</p>
                    <p className="mt-1 text-[11px] text-muted">Measured from the preferred entry to Target 2 vs the stop.</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Expected holding</p>
                    <p className="mt-1 text-base font-semibold">{holding(s.holding_min_sessions, s.holding_max_sessions)}</p>
                    {m.holding ? <p className="mt-1 text-[11px] text-muted">{m.holding}</p> : null}
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Confidence</p>
                    <div className="mt-1"><Confidence value={s.confidence} /></div>
                    {m.confidence_notes?.length ? <p className="mt-1 text-[11px] text-muted">{m.confidence_notes.join(" ")}</p> : null}
                  </div>
                </div>
                {s.rejected || s.valid === false ? (
                  <p className="rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-xs text-warn" role="status">
                    <span className="font-semibold">Filtered out by the scanner: </span>
                    {[...(s.rejection_reasons ?? []), ...(s.rejections ?? [])].join("; ") || "did not pass all filters"} — levels shown for study only.
                  </p>
                ) : null}
                {s.why?.length || s.why_not?.length ? (
                  <div className="grid gap-3 text-xs sm:grid-cols-2">
                    <div>
                      <p className="mb-1 font-bold uppercase tracking-wide text-up">Why</p>
                      <ul className="list-inside list-disc space-y-0.5">{(s.why ?? []).map((w, i) => <li key={i}>{w}</li>)}</ul>
                    </div>
                    <div>
                      <p className="mb-1 font-bold uppercase tracking-wide text-down">Why not</p>
                      <ul className="list-inside list-disc space-y-0.5">{(s.why_not ?? []).map((w, i) => <li key={i}>{w}</li>)}</ul>
                    </div>
                  </div>
                ) : null}
                {s.breakdown?.components?.length ? (
                  <details className="rounded-md border border-border p-3">
                    <summary className="cursor-pointer text-xs font-semibold">Score breakdown ({s.score == null ? "n/a" : Math.round(Number(s.score))}/100)</summary>
                    <ScoreBreakdown className="mt-3" breakdown={s.breakdown} missing={s.missing_components} />
                  </details>
                ) : null}
                {m.expected_move ? <p className="rounded-md bg-surface-2 px-3 py-2 text-xs"><span className="font-semibold">Expected move: </span>{m.expected_move}</p> : null}
                {s.invalidation ? (
                  <p className="rounded-md border border-down/30 bg-down-soft/40 px-3 py-2 text-xs">
                    <span className="font-semibold text-down">Invalidation: </span>
                    {s.invalidation}
                  </p>
                ) : null}
                <DataStamp asOf={s.data_as_of ?? t.as_of} source={s.model_version ? `model ${s.model_version}` : "NIVARA levels engine (computed on demand from EOD data)"} />
                {t.disclaimer ? <p className="text-[11px] text-muted">{t.disclaimer}</p> : null}
              </CardBody>
            </Card>

            <div className="grid gap-4 xl:grid-cols-2">
              <Card>
                <CardHeader icon={<Calculator className="size-4" />} title="Position-size calculator" subtitle="Prefilled with this setup and your risk limits from Settings" />
                <CardBody>
                  <PositionSizer
                    key={`${symbol}-${s.entry_low}-${s.stop}-${String(rl.capital)}`}
                    entry={s.entry_high ?? s.entry_low}
                    stop={s.stop}
                    targets={[s.target1, s.target2, s.target3].filter((x) => toNum(x) !== null) as Numeric[]}
                    capital={(rl.capital as number) ?? 1_000_000}
                    riskPct={(rl.risk_per_trade_pct as number) ?? 1}
                    maxPositionPct={rl.max_single_stock_pct as number}
                  />
                </CardBody>
              </Card>
              <Card>
                <CardHeader icon={<Receipt className="size-4" />} title="Charges estimate" />
                <CardBody>
                  <ChargesCalculator key={symbol} price={s.entry_high ?? s.cmp} />
                </CardBody>
              </Card>
            </div>
            <Disclaimer>Levels are model outputs from historical price behaviour. Gaps can skip stops; position size assumes the stop fills at its price.</Disclaimer>
          </div>
        );
      }}
    </QueryState>
  );
}
