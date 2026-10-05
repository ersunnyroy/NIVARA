"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, History, Trophy, X } from "lucide-react";
import { useRecommendations, useTrackRecord } from "@/lib/hooks";
import { dateIST, inr, titleCase } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import { ActionBadge, ScorePill, SuitabilityBadge } from "@/components/domain/badges";
import { RecommendationDetail } from "@/components/domain/RecommendationDetail";
import { StockSearch } from "@/components/domain/StockSearch";
import { BucketTable, TrackRecordStats } from "@/components/domain/TrackRecord";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  Disclaimer,
  EmptyState,
  Field,
  Input,
  Pct,
  QueryState,
  SkeletonRows,
  TableWrap,
  TabPanel,
  Tabs,
  Td,
  Th,
  THead,
  Tr,
  cn,
} from "@/components/ui";

const BUCKETS = [
  { key: "by_regime", label: "By regime" },
  { key: "by_sector", label: "By sector" },
  { key: "by_strategy", label: "By strategy" },
  { key: "by_confidence", label: "By confidence" },
  { key: "by_holding", label: "By holding period" },
  { key: "by_action", label: "By action" },
  { key: "by_origin", label: "Live vs replay" },
  { key: "by_model_version", label: "By model version" },
] as const;
type BucketKey = (typeof BUCKETS)[number]["key"];

function outcomeTone(s?: string): "up" | "down" | "warn" | "neutral" {
  const x = (s ?? "").toLowerCase();
  if (x.includes("target") || x.includes("t1") || x.includes("t2") || x === "win") return "up";
  if (x.includes("stop") || x === "loss") return "down";
  if (x.includes("pending") || x.includes("open") || x.includes("not_triggered")) return "warn";
  return "neutral";
}

export default function RecommendationsPage() {
  const tr = useTrackRecord();
  const [symbol, setSymbol] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const hist = useRecommendations({ symbol: symbol || undefined, from: from || undefined, to: to || undefined });
  const [bucket, setBucket] = useState<BucketKey>("by_regime");
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader title="Recommendations & track record" description="Every idea NIVARA published, frozen at generation time, and how it actually played out." />
      <Disclaimer>Past outcomes of model ideas do not guarantee future results. Outcomes are evaluated on EOD data; intraday fills may differ.</Disclaimer>

      <Card>
        <CardHeader icon={<Trophy className="size-4" />} title="Track record" />
        <CardBody>
          <QueryState query={tr} skeleton={<SkeletonRows rows={2} />}>
            {(d) => (
              <>
                <TrackRecordStats tr={d} />
                {d.note ? <p className="mt-3 text-[11px] leading-relaxed text-muted">{d.note}</p> : null}
                {d.data_as_of ? <DataStamp className="mt-3" asOf={d.data_as_of} /> : null}
              </>
            )}
          </QueryState>
        </CardBody>
        {tr.data?.totals?.count ? (
          <div className="border-t border-border">
            <Tabs label="Track record breakdowns" idBase="tr" tabs={[...BUCKETS]} value={bucket} onChange={setBucket} className="px-2" />
            <TabPanel idBase="tr" k={bucket}>
              <BucketTable rows={tr.data[bucket]} label={BUCKETS.find((b) => b.key === bucket)?.label.replace("By ", "") ?? ""} />
            </TabPanel>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader icon={<History className="size-4" />} title="Recommendation history" />
        <CardBody className="flex flex-wrap items-end gap-3 border-b border-border">
          <Field label="Stock" className="w-60">
            {(id) => (
              <div className="flex items-center gap-1">
                <StockSearch id={id} onSelect={(h) => setSymbol(h.symbol)} placeholder={symbol || "Any stock"} />
                {symbol ? (
                  <Button size="xs" variant="ghost" aria-label="Clear stock filter" onClick={() => setSymbol("")}>
                    <X className="size-3.5" />
                  </Button>
                ) : null}
              </div>
            )}
          </Field>
          <Field label="From" className="w-40">
            {(id) => <Input id={id} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}
          </Field>
          <Field label="To" className="w-40">
            {(id) => <Input id={id} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}
          </Field>
          {symbol ? <Badge tone="accent">{symbol}</Badge> : null}
        </CardBody>
        <QueryState query={hist} skeleton={<SkeletonRows rows={6} className="p-4" />}>
          {(rows) =>
            rows.length ? (
              <TableWrap label="Recommendation history">
                <THead>
                  <tr>
                    <Th className="w-8"><span className="sr-only">Expand</span></Th>
                    <Th>Session</Th>
                    <Th>Stock</Th>
                    <Th>Action</Th>
                    <Th align="center">Score</Th>
                    <Th>Setup</Th>
                    <Th align="right">Entry</Th>
                    <Th align="right">Stop</Th>
                    <Th align="right">T1</Th>
                    <Th>Outcome</Th>
                    <Th align="right">Return</Th>
                    <Th align="right">MFE</Th>
                    <Th align="right">MAE</Th>
                  </tr>
                </THead>
                <tbody>
                  {rows.map((r) => {
                    const isOpen = open === r.id;
                    return (
                      <Fragment key={r.id}>
                        <Tr className={cn("cursor-pointer", isOpen && "bg-surface-2/60")} onClick={() => setOpen(isOpen ? null : r.id)}>
                          <Td>
                            <button
                              type="button"
                              aria-expanded={isOpen}
                              aria-label={`${isOpen ? "Collapse" : "Expand"} ${r.symbol}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpen(isOpen ? null : r.id);
                              }}
                              className="rounded p-0.5 text-muted"
                            >
                              {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                            </button>
                          </Td>
                          <Td className="whitespace-nowrap">{dateIST(r.session_date ?? r.generated_at)}</Td>
                          <Td>
                            <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:text-accent hover:underline">
                              {r.symbol}
                            </Link>
                          </Td>
                          <Td>
                            <div className="flex flex-wrap gap-1">
                              <ActionBadge action={r.action} />
                              <SuitabilityBadge value={r.suitability} />
                            </div>
                          </Td>
                          <Td align="center"><ScorePill value={r.score} /></Td>
                          <Td className="whitespace-nowrap text-xs">{titleCase(r.setup)}</Td>
                          <Td align="right" className="whitespace-nowrap">{inr(r.entry_low, 2)}–{inr(r.entry_high, 2).replace("₹", "")}</Td>
                          <Td align="right" className="text-down">{inr(r.stop, 2)}</Td>
                          <Td align="right" className="text-up">{inr(r.target1, 2)}</Td>
                          <Td>
                            {r.outcome?.status ? <Badge tone={outcomeTone(r.outcome.status)} size="xs">{titleCase(r.outcome.status)}</Badge> : <span className="text-xs text-subtle">pending</span>}
                          </Td>
                          <Td align="right"><Pct value={r.outcome?.return_pct} /></Td>
                          <Td align="right"><Pct value={r.outcome?.mfe_pct} /></Td>
                          <Td align="right"><Pct value={r.outcome?.mae_pct} /></Td>
                        </Tr>
                        {isOpen ? (
                          <tr>
                            <td colSpan={13} className="border-b border-border bg-surface-2/30 p-0">
                              <RecommendationDetail rec={r} />
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </TableWrap>
            ) : (
              <EmptyState title="No recommendations match">Recommendations are published by the daily scan. Widen the date range or clear the stock filter.</EmptyState>
            )
          }
        </QueryState>
      </Card>
    </div>
  );
}
