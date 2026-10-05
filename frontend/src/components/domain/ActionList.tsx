import Link from "next/link";
import { inrCompact } from "@/lib/format";
import type { PortfolioActionItem } from "@/lib/types";
import { EmptyState, Pct, cn } from "@/components/ui";
import { MonitorActionBadge, monitorLevel } from "./badges";

const ORDER = { danger: 0, caution: 1, neutral: 2, ok: 3 } as const;

export function sortActions<T extends { action?: string | null; severity?: string | null }>(items: T[]): T[] {
  return [...items].sort((a, b) => ORDER[monitorLevel(a.action, a.severity)] - ORDER[monitorLevel(b.action, b.severity)]);
}

export function ActionList({ items, limit, className }: { items: PortfolioActionItem[]; limit?: number; className?: string }) {
  const rows = sortActions(items).slice(0, limit ?? items.length);
  if (!rows.length)
    return (
      <EmptyState compact title="No actions required">
        Holdings with stops, targets or sell signals will show here. Add transactions in Portfolio to start monitoring.
      </EmptyState>
    );
  return (
    <ul className={cn("divide-y divide-border", className)}>
      {rows.map((a, i) => (
        <li key={`${a.symbol}-${a.portfolio ?? ""}-${i}`} className="flex flex-col gap-1 px-4 py-2.5 sm:flex-row sm:items-start sm:gap-3">
          <div className="flex w-full items-center gap-2 sm:w-56 sm:shrink-0">
            <MonitorActionBadge action={a.action} severity={a.severity} />
            <Link href={`/stocks/${encodeURIComponent(a.symbol)}`} className="font-semibold hover:text-accent hover:underline">
              {a.symbol}
            </Link>
            {a.portfolio ? <span className="truncate text-[11px] text-muted">{a.portfolio}</span> : null}
          </div>
          <div className="min-w-0 flex-1 text-xs text-fg/80">
            {(a.reasons ?? []).slice(0, 3).join(" · ") || (a.sell_signals ?? []).map((s) => s.reason ?? s.code).join(" · ") || "—"}
            {a.suggested_trailing_stop != null ? <span className="text-muted"> · Suggested trailing stop {inrCompact(a.suggested_trailing_stop)}</span> : null}
            {a.partial_exit_pct != null ? <span className="text-muted"> · Partial exit {a.partial_exit_pct}%</span> : null}
          </div>
          {a.pnl_pct != null ? <Pct value={a.pnl_pct} className="text-xs font-medium" /> : null}
        </li>
      ))}
    </ul>
  );
}
