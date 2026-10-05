"use client";

import { useMarketStatus } from "@/lib/hooks";
import { dateIST, titleCase } from "@/lib/format";
import { cn } from "@/components/ui";

const PHASE: Record<string, { label: string; cls: string }> = {
  open: { label: "Market open", cls: "bg-up" },
  pre_open: { label: "Pre-open", cls: "bg-warn" },
  pre_market: { label: "Pre-market", cls: "bg-subtle" },
  post_close: { label: "Closed (post-close)", cls: "bg-subtle" },
  holiday: { label: "Holiday", cls: "bg-violet" },
  weekend: { label: "Weekend", cls: "bg-subtle" },
};

export function MarketStatusPill({ className }: { className?: string }) {
  const q = useMarketStatus();
  if (q.isPending) return <span className={cn("skeleton h-7 w-40 rounded-full", className)} aria-hidden />;
  if (q.isError)
    return (
      <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border border-border px-2.5 text-[11px] text-muted", className)} title={q.error.message}>
        <span className="size-2 rounded-full bg-down" aria-hidden /> Market status unavailable
      </span>
    );
  const s = q.data;
  const phase = s.phase ? PHASE[s.phase] ?? { label: titleCase(s.phase), cls: "bg-subtle" } : { label: "Status n/a", cls: "bg-subtle" };
  const fresh = s.data_freshness ?? s.freshness;
  const behind = s.data?.is_current === false;
  const noData = s.data != null && !s.data.last_eod_date;
  const stale = behind || noData || fresh?.status === "data_stale" || fresh?.status === "data_unavailable";
  const staleLabel = noData || fresh?.status === "data_unavailable" ? "no data" : behind && s.data?.sessions_behind ? `stale ${s.data.sessions_behind}d` : "stale";
  return (
    <span
      className={cn("inline-flex h-7 max-w-full items-center gap-2 truncate rounded-full border border-border bg-surface px-2.5 text-[11px] text-muted", className)}
      title={fresh?.message ?? (s.data ? `Latest EOD in database: ${s.data.last_eod_date ?? "none"}${s.data.realtime_quotes ? " · real-time quotes enabled" : ""}` : undefined)}
    >
      <span className={cn("size-2 shrink-0 rounded-full", phase.cls)} aria-hidden />
      <span className="font-medium text-fg">{s.label ?? phase.label}</span>
      {s.holiday_name ? <span className="hidden sm:inline">· {s.holiday_name}</span> : null}
      <span className="hidden md:inline">
        · EOD <span className="num text-fg/80">{s.last_completed_eod_session ? dateIST(s.last_completed_eod_session) : "n/a"}</span>
      </span>
      {s.data?.live_snapshot?.available && s.data.live_snapshot.as_of ? (
        <span className="hidden lg:inline" title={s.data.live_snapshot.source}>
          · Live <span className="num text-fg/80">{new Date(s.data.live_snapshot.as_of).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })}</span>
        </span>
      ) : null}
      {stale ? <span className="font-semibold uppercase text-warn">{staleLabel}</span> : null}
    </span>
  );
}
