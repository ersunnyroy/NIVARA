import { inrCompact, pct, tone, toNum } from "@/lib/format";
import type { PortfolioSummary as PS } from "@/lib/types";
import { Stat, cn } from "@/components/ui";
import { EstimatedTag } from "./badges";

/** Invested · Current · Gross P&L · Charges · Est. tax · Net P&L — gross always next to net. */
export function PortfolioSummaryTiles({ summary, className, dense }: { summary?: PS | null; className?: string; dense?: boolean }) {
  const s = summary ?? {};
  const realisedTax = toNum(s.estimated_tax_realized);
  const ifSold = toNum(s.estimated_tax_unrealized);
  const ifSoldText =
    ifSold === null ? "" : ifSold < 0 ? `if all sold now: saves ${inrCompact(-ifSold)}` : `if all sold now: +${inrCompact(ifSold)}`;
  const gross = toNum(s.gross_pnl);
  const invested = toNum(s.invested);
  const grossPct = gross !== null && invested ? (gross / invested) * 100 : null;
  return (
    <div className={cn("grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3", dense ? "xl:grid-cols-6" : "lg:grid-cols-6", className)}>
      <Stat label="Invested" value={inrCompact(s.invested)} />
      <Stat label="Current value" value={inrCompact(s.current_value)} />
      <Stat
        label="Gross P&L"
        value={inrCompact(s.gross_pnl, true)}
        tone={tone(s.gross_pnl)}
        sub={
          <>
            {grossPct === null ? "" : pct(grossPct)}
            {s.realized_gross_pnl != null ? ` · realised ${inrCompact(s.realized_gross_pnl, true)} (this FY)` : ""}
          </>
        }
      />
      <Stat label="Charges" value={inrCompact(s.charges_incl_estimated_exit)} sub="incl. estimated exit" />
      <Stat
        label="Est. tax"
        badge={<EstimatedTag />}
        value={realisedTax === null ? "n/a" : inrCompact(realisedTax)}
        sub={[s.tax_year ? `realised FY ${s.tax_year}` : "realised", ifSoldText].filter(Boolean).join(" · ") || undefined}
      />
      <Stat
        label="Net P&L"
        value={inrCompact(s.net_pnl, true)}
        tone={tone(s.net_pnl)}
        sub={s.net_return_pct == null ? "after charges & est. tax" : `${pct(s.net_return_pct)} after charges & est. tax`}
      />
    </div>
  );
}
