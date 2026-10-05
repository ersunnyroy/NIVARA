import { num, titleCase, toNum } from "@/lib/format";
import type { MissingComponent, ScoreBreakdown as SB } from "@/lib/types";
import { cn } from "@/components/ui";

export function ScoreBreakdown({
  breakdown,
  missing,
  className,
}: {
  breakdown?: SB | null;
  missing?: MissingComponent[] | null;
  className?: string;
}) {
  const comps = breakdown?.components ?? [];
  const missingMap = new Map((missing ?? []).map((m) => [m.component, m.reason]));
  if (!comps.length) return <p className={cn("text-xs text-muted", className)}>No score breakdown reported.</p>;
  return (
    <div className={className}>
      <ul className="space-y-2">
        {comps.map((c) => {
          const weight = toNum(c.weight);
          const pts = toNum(c.points);
          const reason = c.missing_reason ?? missingMap.get(c.key) ?? null;
          const na = reason != null || pts === null;
          const frac = !na && weight ? Math.max(0, Math.min(1, (pts as number) / weight)) : 0;
          return (
            <li key={c.key} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-fg">{c.label ?? titleCase(c.key)}</span>
                <span className="num">
                  {na ? (
                    <span className="text-subtle">n/a / {weight == null ? "?" : num(weight, 0)}</span>
                  ) : (
                    <>
                      <span className="font-semibold">{num(pts, 1, 0)}</span>
                      <span className="text-muted">/{weight == null ? "?" : num(weight, 0)}</span>
                    </>
                  )}
                </span>
              </div>
              <div
                className={cn("mt-1 h-1.5 overflow-hidden rounded-full", na ? "bg-[repeating-linear-gradient(135deg,var(--surface-3)_0_4px,transparent_4px_8px)]" : "bg-surface-3")}
                aria-hidden
              >
                {!na ? (
                  <span
                    className={cn("block h-full rounded-full", frac >= 0.7 ? "bg-up" : frac >= 0.4 ? "bg-warn" : "bg-down")}
                    style={{ width: `${(frac * 100).toFixed(0)}%` }}
                  />
                ) : null}
              </div>
              {na ? <p className="mt-0.5 text-[11px] text-warn">Not scored — {reason ?? "data not available"}</p> : null}
              {!na && (c.reasons?.length || c.cautions?.length) ? (
                <p className="mt-0.5 text-[11px] text-muted">
                  {(c.reasons ?? []).join("; ")}
                  {c.cautions?.length ? <span className="text-warn"> · Caution: {c.cautions.join("; ")}</span> : null}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
      <p className="num mt-3 border-t border-border pt-2 text-[11px] text-muted">
        Earned {num(breakdown?.earned, 1, 0)} of {num(breakdown?.available, 0)} available points
        {toNum(breakdown?.missing_weight) ? (
          <span className="text-warn"> · {num(breakdown?.missing_weight, 0)} points of weight missing (excluded, not scored as zero)</span>
        ) : null}
        {breakdown?.total != null ? <> · Total score {num(breakdown.total, 1, 0)}</> : null}
      </p>
    </div>
  );
}
