"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { holding, inr, rr, titleCase } from "@/lib/format";
import type { Recommendation } from "@/lib/types";
import { TableWrap, Td, Th, THead, Tr, cn } from "@/components/ui";
import { ActionBadge, Confidence, ScorePill, SuitabilityBadge } from "./badges";
import { RecommendationDetail } from "./RecommendationDetail";

export function OpportunitiesTable({
  items,
  expandable,
  disabled,
  limit,
}: {
  items: Recommendation[];
  expandable?: boolean;
  /** Stale data → show levels but disable action column. */
  disabled?: boolean;
  limit?: number;
}) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const rows = [...items].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999)).slice(0, limit ?? items.length);
  const toggle = (id: number) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const cols = expandable ? 14 : 13;

  return (
    <TableWrap label="Top opportunities">
      <THead>
        <tr>
          {expandable ? <Th className="w-8"><span className="sr-only">Expand</span></Th> : null}
          <Th align="right">Rank</Th>
          <Th>Stock</Th>
          <Th align="center">Score</Th>
          <Th>Setup</Th>
          <Th align="right">CMP</Th>
          <Th align="right">Entry zone</Th>
          <Th align="right">Stop</Th>
          <Th align="right">T1</Th>
          <Th align="right">T2</Th>
          <Th align="right">R:R</Th>
          <Th>Holding</Th>
          <Th>Confidence</Th>
          <Th>Action / suitability</Th>
        </tr>
      </THead>
      <tbody>
        {rows.map((r) => {
          const isOpen = open.has(r.id);
          return (
            <Fragment key={r.id}>
              <Tr className={cn(expandable && "cursor-pointer", isOpen && "bg-surface-2/60")} onClick={expandable ? () => toggle(r.id) : undefined}>
                {expandable ? (
                  <Td>
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-label={`${isOpen ? "Collapse" : "Expand"} details for ${r.symbol}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggle(r.id);
                      }}
                      className="rounded p-0.5 text-muted hover:text-fg"
                    >
                      {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </button>
                  </Td>
                ) : null}
                <Td align="right" className="font-semibold text-muted">
                  {r.rank ?? "–"}
                </Td>
                <Td className="min-w-40">
                  <Link
                    href={`/stocks/${encodeURIComponent(r.symbol)}`}
                    className="font-semibold text-fg hover:text-accent hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {r.symbol}
                  </Link>
                  <div className="max-w-52 truncate text-[11px] text-muted">{r.name ?? ""}{r.sector ? ` · ${r.sector}` : ""}</div>
                </Td>
                <Td align="center">
                  <ScorePill value={r.score} />
                </Td>
                <Td className="whitespace-nowrap text-xs">{titleCase(r.setup)}</Td>
                <Td align="right">{inr(r.cmp, 2)}</Td>
                <Td align="right" className="whitespace-nowrap">
                  {inr(r.entry_low, 2)}–{inr(r.entry_high, 2).replace("₹", "")}
                </Td>
                <Td align="right" className="text-down">
                  {inr(r.stop, 2)}
                </Td>
                <Td align="right" className="text-up">
                  {inr(r.target1, 2)}
                </Td>
                <Td align="right" className="text-up">
                  {inr(r.target2, 2)}
                </Td>
                <Td align="right">{rr(r.rr)}</Td>
                <Td className="whitespace-nowrap text-xs">{holding(r.holding_min_sessions, r.holding_max_sessions)}</Td>
                <Td>
                  <Confidence value={r.confidence} />
                </Td>
                <Td>
                  <div className="flex flex-wrap items-center gap-1">
                    {disabled ? <span className="text-[11px] font-semibold uppercase text-warn">Disabled (stale)</span> : <ActionBadge action={r.action} />}
                    <SuitabilityBadge value={r.suitability} />
                  </div>
                </Td>
              </Tr>
              {expandable && isOpen ? (
                <tr className="bg-surface-2/30">
                  <td colSpan={cols} className="border-b border-border p-0">
                    <RecommendationDetail rec={r} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          );
        })}
      </tbody>
    </TableWrap>
  );
}
