import Link from "next/link";
import { Ban, CheckCircle2, Database, ShieldX, XCircle } from "lucide-react";
import { dateIST, holding, inr, pct, rr, titleCase } from "@/lib/format";
import type { Recommendation } from "@/lib/types";
import { Badge, DataStamp, Pct } from "@/components/ui";
import { ScoreBreakdown } from "./ScoreBreakdown";

function List({ items, empty, tone }: { items?: string[] | null; empty: string; tone: "up" | "down" }) {
  if (!items?.length) return <p className="text-xs text-muted">{empty}</p>;
  const Icon = tone === "up" ? CheckCircle2 : XCircle;
  return (
    <ul className="space-y-1.5">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2 text-xs leading-relaxed">
          <Icon className={tone === "up" ? "mt-0.5 size-3.5 shrink-0 text-up" : "mt-0.5 size-3.5 shrink-0 text-down"} aria-hidden />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
}

type SourceRef = NonNullable<Recommendation["data_sources"]>[number];

function sourceLabel(s: SourceRef): string {
  if (typeof s === "string") return s;
  return [s?.name ?? s?.source, s?.as_of ? `as of ${dateIST(s.as_of)}` : null].filter(Boolean).join(" ");
}

/** Expanded explanation for one recommendation: why, why not, invalidation, score, sources. */
export function RecommendationDetail({ rec }: { rec: Recommendation }) {
  const disabled = rec.action === "WAIT";
  return (
    <div className="grid gap-4 p-4 lg:grid-cols-3">
      <div className="space-y-4">
        <section>
          <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-up">Why buy</h4>
          <List items={rec.why} empty="No supporting reasons reported." tone="up" />
        </section>
        <section>
          <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-down">Why not buy</h4>
          <List items={rec.why_not} empty="No counter-arguments reported." tone="down" />
        </section>
      </div>
      <div className="space-y-4">
        <section className="rounded-lg border border-down/30 bg-down-soft/40 p-3">
          <h4 className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-down">
            <ShieldX className="size-3.5" aria-hidden /> Invalidation
          </h4>
          <p className="text-xs leading-relaxed">{rec.invalidation || "Not reported."}</p>
        </section>
        <section className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <div>
            <p className="text-muted">Aggressive entry</p>
            <p className="num font-medium">{inr(rec.aggressive_entry, 2)}</p>
          </div>
          <div>
            <p className="text-muted">Preferred entry zone</p>
            <p className="num font-medium">
              {inr(rec.entry_low, 2)} – {inr(rec.entry_high, 2)}
            </p>
          </div>
          <div>
            <p className="text-muted">Conservative zone</p>
            <p className="num font-medium">
              {rec.conservative_low == null ? "n/a" : `${inr(rec.conservative_low, 2)} – ${inr(rec.conservative_high, 2)}`}
            </p>
          </div>
          <div>
            <p className="flex items-center gap-1 text-muted">
              <Ban className="size-3" aria-hidden /> Do not chase above
            </p>
            <p className="num font-medium text-warn">{inr(rec.no_chase_above, 2)}</p>
          </div>
          <div>
            <p className="text-muted">Stop</p>
            <p className="num font-medium text-down">
              {inr(rec.stop, 2)} <span className="text-[11px] text-muted">({pct(rec.risk_pct == null ? null : -Math.abs(rec.risk_pct))})</span>
            </p>
          </div>
          <div>
            <p className="text-muted">Trailing after T1</p>
            <p className="num font-medium">{inr(rec.trailing_stop_after_t1, 2)}</p>
          </div>
          {(["target1", "target2", "target3"] as const).map((t, i) => (
            <div key={t}>
              <p className="text-muted">Target {i + 1}</p>
              <p className="num font-medium text-up">
                {inr(rec[t], 2)} {rec.reward_pcts?.[i] != null ? <Pct value={rec.reward_pcts[i]} className="text-[11px]" /> : null}
              </p>
            </div>
          ))}
          <div>
            <p className="text-muted">Reward : risk (T2)</p>
            <p className="num font-medium">{rr(rec.rr)}</p>
          </div>
          <div>
            <p className="text-muted">Holding period</p>
            <p className="font-medium">{holding(rec.holding_min_sessions, rec.holding_max_sessions)}</p>
          </div>
          <div>
            <p className="text-muted">Strategy</p>
            <p className="font-medium">{titleCase(rec.strategy)}</p>
          </div>
        </section>
        {disabled ? <p className="text-[11px] text-warn">Action is WAIT — conditions for entry are not yet met.</p> : null}
      </div>
      <div className="space-y-3">
        <section>
          <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted">Score breakdown</h4>
          <ScoreBreakdown breakdown={rec.score_breakdown} missing={rec.missing_components} />
        </section>
        {rec.missing_components?.length ? (
          <section>
            <h4 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-warn">Missing components</h4>
            <ul className="space-y-0.5 text-[11px] text-muted">
              {rec.missing_components.map((m) => (
                <li key={m.component}>
                  <span className="font-medium text-fg">{titleCase(m.component)}</span>: n/a — {m.reason ?? "not available"}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <section>
          <h4 className="mb-1 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-muted">
            <Database className="size-3" aria-hidden /> Data sources
          </h4>
          <div className="flex flex-wrap gap-1">
            {rec.data_sources?.length ? (
              rec.data_sources.map((s, i) => (
                <Badge key={i} tone="outline" size="xs" className="normal-case">
                  {sourceLabel(s)}
                </Badge>
              ))
            ) : (
              <span className="text-[11px] text-muted">Not reported</span>
            )}
          </div>
        </section>
        <DataStamp asOf={rec.data_as_of} source={rec.model_version ? `model ${rec.model_version}` : undefined} />
        <p className="text-[11px] text-muted">
          Generated {rec.generated_at ? dateIST(rec.generated_at) : "n/a"} · Regime at generation: {rec.market_regime ?? "n/a"} ·{" "}
          <Link className="text-accent hover:underline" href={`/stocks/${encodeURIComponent(rec.symbol)}?tab=setup`}>
            Open trade setup
          </Link>
        </p>
      </div>
    </div>
  );
}
