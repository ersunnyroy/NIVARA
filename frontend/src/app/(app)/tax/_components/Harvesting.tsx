"use client";

import Link from "next/link";
import { Scissors } from "lucide-react";
import { useHarvesting } from "@/lib/hooks";
import { int, titleCase } from "@/lib/format";
import { EstimatedTag } from "@/components/domain/badges";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  Disclaimer,
  EmptyState,
  Money,
  NAValue,
  Pnl,
  QueryState,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import type { HarvestCandidateX, HarvestReportX } from "./types";

const PLANNING = "Tax planning estimate — verify with a qualified tax professional.";
const NOT_SELL = "Not a sell recommendation";

function holdingDays(c: HarvestCandidateX) {
  if (c.min_holding_days != null && c.max_holding_days != null) {
    return c.min_holding_days === c.max_holding_days ? int(c.min_holding_days) : `${int(c.min_holding_days)}–${int(c.max_holding_days)}`;
  }
  const v = c.holding_days ?? c.min_holding_days ?? c.max_holding_days;
  return v == null ? <NAValue /> : int(v);
}

function Offset({ v }: { v: HarvestCandidateX["potential_offset"] }) {
  if (Array.isArray(v)) {
    if (!v.length) return <NAValue />;
    return (
      <ul className="max-w-xs list-inside list-disc space-y-0.5 whitespace-normal text-xs text-fg/80">
        {v.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    );
  }
  return <Money value={v} />;
}

export function Harvesting() {
  const q = useHarvesting();
  return (
    <Card>
      <CardHeader
        icon={<Scissors className="size-4" />}
        title={
          <span className="inline-flex items-center gap-2">
            Tax-loss harvesting view <EstimatedTag />
          </span>
        }
        subtitle="Positions with an unrealized capital loss, and the estimated effect on this year's tax if the whole position were sold at the last price."
      />
      <CardBody className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <Disclaimer tone="warn">{PLANNING}</Disclaimer>
          <Disclaimer tone="warn">{NOT_SELL}. This is informational only; wash-sale style repurchases and transaction costs are your responsibility.</Disclaimer>
        </div>
        <QueryState query={q} skeleton={<SkeletonRows rows={4} />}>
          {(raw) => {
            const d = raw as HarvestReportX;
            const rows = d.candidates ?? [];
            return (
              <div className="space-y-3">
                {d.status === "incomplete" || d.incomplete_reasons?.length ? (
                  <div role="status" className="rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-xs text-warn">
                    <p className="font-semibold uppercase tracking-wide">Estimate incomplete</p>
                    {d.message ? <p className="mt-0.5 text-fg/80">{d.message}</p> : null}
                    {d.incomplete_reasons?.length ? (
                      <ul className="mt-1 list-inside list-disc text-fg/80">
                        {d.incomplete_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
                {rows.length === 0 ? (
                  <EmptyState compact title="No positions with an unrealized loss">
                    Only live-portfolio positions with a current price and an unrealized capital loss appear here. Add transactions in Portfolio if
                    none are recorded yet.
                  </EmptyState>
                ) : (
                  <TableWrap label="Tax-loss harvesting candidates">
                    <THead>
                      <tr>
                        <Th>Symbol</Th>
                        <Th align="right">Unrealized loss</Th>
                        <Th>Term</Th>
                        <Th align="right">Holding days</Th>
                        <Th>Potential offset</Th>
                        <Th align="right">Est. tax without sale</Th>
                        <Th align="right">Est. tax with sale</Th>
                        <Th align="right">Est. tax difference</Th>
                      </tr>
                    </THead>
                    <tbody>
                      {rows.map((c, i) => (
                        <Tr key={`${c.symbol}-${i}`}>
                          <Td className="font-semibold">
                            <Link href={`/stocks/${encodeURIComponent(c.symbol)}`} className="text-accent hover:underline">
                              {c.symbol}
                            </Link>
                            {c.status === "incomplete" ? (
                              <Badge tone="warn" size="xs" className="ml-1.5" title={(c.incomplete_reasons ?? []).join("; ")}>
                                incomplete
                              </Badge>
                            ) : null}
                          </Td>
                          <Td align="right">
                            <Money value={c.unrealized_loss} />
                          </Td>
                          <Td>{c.classification ?? c.term ? titleCase(c.classification ?? c.term) : <NAValue />}</Td>
                          <Td align="right">{holdingDays(c)}</Td>
                          <Td>
                            <Offset v={c.potential_offset} />
                          </Td>
                          <Td align="right">
                            <Money value={c.estimated_tax_without_sale ?? c.tax_without} />
                          </Td>
                          <Td align="right">
                            <Money value={c.estimated_tax_with_sale ?? c.tax_with} />
                          </Td>
                          <Td align="right">
                            <Pnl value={c.estimated_tax_impact ?? c.tax_difference} plain />
                          </Td>
                        </Tr>
                      ))}
                    </tbody>
                  </TableWrap>
                )}
                {rows.length ? (
                  <p className="text-[11px] text-muted">
                    Tax difference = estimated tax with the hypothetical sale − without it (a negative figure means a lower estimated tax).
                  </p>
                ) : null}
                {d.notes?.length ? (
                  <ul className="list-inside list-disc text-xs text-muted">
                    {d.notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                ) : null}
                <DataStamp asOf={d.as_of} label="Prices as of" source={d.rule_set_version ? `tax rules ${d.rule_set_version}` : undefined} />
                {d.label && d.label !== PLANNING ? <p className="text-xs text-muted">{d.label}</p> : null}
                {d.disclaimer ? <Disclaimer>{d.disclaimer}</Disclaimer> : null}
              </div>
            );
          }}
        </QueryState>
      </CardBody>
    </Card>
  );
}
