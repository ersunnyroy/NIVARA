"use client";

import { ExternalLink, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import {
  useAnalysis,
  useCorporateActions,
  useFundamentals,
  useRegenerateAnalysis,
  useShareholding,
  useSignals,
  useStockFno,
  useStockNews,
  useTechnical,
} from "@/lib/hooks";
import { dateIST, dateTimeIST, inr, num, pct, ratioPct, titleCase, toNum } from "@/lib/format";
import type { FnoSnapshot, Growth, MarginInfo, ShareholdingRow } from "@/lib/types";
import { NewsList } from "@/components/domain/News";
import { ActionBadge, ScorePill } from "@/components/domain/badges";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataStamp,
  DataStatusBanner,
  DataUnavailable,
  EmptyState,
  ErrorState,
  NAValue,
  Pct,
  QueryState,
  SkeletonRows,
  Stat,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { Sparkline } from "@/components/charts/svg";
import { KeyValueGrid, scalar } from "./util";

const skel = <SkeletonRows rows={5} className="p-4" />;

function level(v: unknown): { price: number | null; note?: string } {
  if (typeof v === "number") return { price: v };
  if (v && typeof v === "object") {
    const o = v as { level?: number; price?: number; note?: string; strength?: number; touches?: number; last_touch?: string };
    const bits = [o.touches != null ? `${o.touches} touch${o.touches === 1 ? "" : "es"}` : null, o.last_touch ? `last ${dateIST(o.last_touch)}` : null, o.strength != null ? `strength ${num(o.strength, 2)}` : null];
    return { price: toNum(o.level ?? o.price), note: o.note ?? (bits.filter(Boolean).join(" · ") || undefined) };
  }
  return { price: toNum(v as string) };
}

/* ---------------------------------------------------------------- Technical */

export function TechnicalPanel({ symbol }: { symbol: string }) {
  const q = useTechnical(symbol);
  return (
    <QueryState query={q} skeleton={skel} unavailableHint="Technical snapshots are computed after EOD ingestion.">
      {(t) => {
        if (t.status && t.status !== "ok") {
          return (
            <DataStatusBanner
              status={t.status}
              message={t.message ?? "Technical analysis is not available for this stock yet."}
              hint="Price history appears after EOD ingestion / backfill (Settings → Jobs)."
            />
          );
        }
        const pa = t.price_action;
        // Patterns arrive as {name: {detected, direction, level, ...}} (or plain flags).
        const patterns = Object.entries(pa?.patterns ?? {}).filter(([, v]) =>
          v && typeof v === "object" ? (v as { detected?: boolean }).detected !== false : v !== false && v !== null && v !== undefined,
        );
        const structure = pa?.structure as unknown;
        const structureLabel =
          structure && typeof structure === "object" ? (structure as { label?: string }).label : (structure as string | null | undefined);
        const structureFlags =
          structure && typeof structure === "object"
            ? Object.entries(structure as Record<string, unknown>).filter(([k, v]) => k !== "label" && v === true).map(([k]) => titleCase(k))
            : [];
        return (
          <div className="space-y-4">
            <DataStatusBanner status={t.status} message={t.message ?? undefined} />
            <Card>
              <CardHeader title="Indicators" subtitle="Daily timeframe, computed from adjusted EOD bars" />
              <CardBody>
                <KeyValueGrid data={t.indicators ?? {}} />
                {t.notes?.length ? <p className="mt-2 text-[11px] text-muted">{t.notes.join(" ")}</p> : null}
                <DataStamp className="mt-3" asOf={t.as_of} source="NIVARA indicators (EOD)" />
              </CardBody>
            </Card>
            <div className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader title="Price structure" />
                <CardBody className="text-sm">
                  {structureLabel ? titleCase(structureLabel) : <NAValue reason="Not computed" />}
                  {structureFlags.length ? <p className="mt-1 text-xs text-muted">{structureFlags.join(" · ")}</p> : null}
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Supports / resistances" />
                <CardBody className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <p className="mb-1 font-semibold text-up">Supports</p>
                    {pa?.supports?.length ? (
                      <ul className="num space-y-0.5">
                        {pa.supports.map((s, i) => {
                          const l = level(s);
                          return <li key={i}>{inr(l.price, 2)}{l.note ? <span className="block text-[10px] text-muted">{l.note}</span> : null}</li>;
                        })}
                      </ul>
                    ) : (
                      <NAValue />
                    )}
                  </div>
                  <div>
                    <p className="mb-1 font-semibold text-down">Resistances</p>
                    {pa?.resistances?.length ? (
                      <ul className="num space-y-0.5">
                        {pa.resistances.map((s, i) => {
                          const l = level(s);
                          return <li key={i}>{inr(l.price, 2)}{l.note ? <span className="block text-[10px] text-muted">{l.note}</span> : null}</li>;
                        })}
                      </ul>
                    ) : (
                      <NAValue />
                    )}
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardHeader title="Patterns detected" />
                <CardBody>
                  {patterns.length ? (
                    <ul className="flex flex-wrap gap-1">
                      {patterns.map(([k, v]) => {
                        const o = v && typeof v === "object" ? (v as { direction?: string; level?: number }) : null;
                        return (
                          <li key={k}>
                            <Badge tone={o?.direction === "bearish" ? "down" : o?.direction === "bullish" ? "up" : "accent"} size="xs" className="normal-case">
                              {titleCase(k)}
                              {o?.level != null ? ` @ ${inr(o.level, 2)}` : typeof v !== "boolean" && !o ? `: ${scalar(v)}` : ""}
                            </Badge>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted">No pattern flagged on the latest bar.</p>
                  )}
                </CardBody>
              </Card>
            </div>
            {t.setup ? (
              <Card>
                <CardHeader title="Current setup" subtitle={t.disclaimer ?? "See the Trade Setup tab for zones, targets and position sizing"} />
                <CardBody className="flex flex-wrap items-center gap-4 text-sm">
                  <ScorePill value={typeof t.setup.score === "object" ? t.setup.score?.total : t.setup.score} />
                  <span>{titleCase(t.setup.setup)}</span>
                  <ActionBadge action={t.setup.action} />
                  <span className="num text-xs text-muted">
                    Entry {inr(t.setup.entry_low, 2)}–{inr(t.setup.entry_high, 2)} · Stop {inr(t.setup.stop, 2)} · T1 {inr(t.setup.target1, 2)}
                  </span>
                </CardBody>
              </Card>
            ) : null}
          </div>
        );
      }}
    </QueryState>
  );
}

/* -------------------------------------------------------------- Fundamental */

export function FundamentalPanel({ symbol }: { symbol: string }) {
  const q = useFundamentals(symbol);
  return (
    <QueryState query={q} skeleton={skel} unavailableHint="Fundamentals load from exchange filings via the fundamentals job.">
      {(f) => {
        const metrics = Object.entries(f.metrics ?? {});
        const ra = f.result_analysis;
        return (
          <div className="space-y-4">
            <DataStatusBanner status={f.status} />
            <div className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader title="Fundamental score" />
                <CardBody className="grid grid-cols-2 gap-4">
                  <Stat label="Score" value={f.score == null ? "n/a" : num(f.score, 0)} sub="0–100" />
                  <Stat label="Data completeness" value={f.completeness == null ? "n/a" : pct((toNum(f.completeness) ?? 0) <= 1 ? (toNum(f.completeness) ?? 0) * 100 : f.completeness, 0, false)} />
                  {f.missing?.length ? (
                    <p className="col-span-2 text-[11px] text-warn">Missing (n/a, excluded from score): {f.missing.map((m) => (m.includes(" ") ? m : titleCase(m))).join("; ")}</p>
                  ) : null}
                </CardBody>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader title="Latest result analysis" subtitle={ra?.classification ? titleCase(ra.classification) : undefined} />
                <CardBody className="space-y-3 text-xs">
                  {ra ? (
                    <>
                      {ra.summary_text ? <p className="text-sm leading-relaxed">{ra.summary_text}</p> : null}
                      <p className="text-muted">
                        {ra.fiscal_quarter ? `${ra.fiscal_quarter} · ` : ""}Period ending {dateIST(ra.period_end)}
                        {ra.basis ? ` · ${ra.basis}` : ""}
                        {ra.total_points != null ? ` · result points ${ra.total_points}` : ""}
                      </p>
                      <div className="grid gap-3 sm:grid-cols-3">
                        {(["qoq", "yoy"] as const).map((k) =>
                          ra[k] && Object.keys(ra[k] ?? {}).length ? (
                            <div key={k}>
                              <p className="mb-1 font-semibold uppercase tracking-wide text-muted">{k === "qoq" ? "QoQ growth" : "YoY growth"}</p>
                              <ul className="space-y-0.5">
                                {Object.entries(ra[k] ?? {}).map(([m, v]) => {
                                  const g = v && typeof v === "object" ? (v as Growth) : null;
                                  const p = g ? g.pct : (v as number | null);
                                  return (
                                    <li key={m} className="flex justify-between gap-2" title={g?.description ?? undefined}>
                                      <span className="text-muted">{titleCase(m)}</span>
                                      {p == null ? <span className="text-subtle">{g?.description ?? "n/a"}</span> : <Pct value={p} digits={1} />}
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          ) : null,
                        )}
                        {ra.margins && Object.keys(ra.margins).length ? (
                          <div>
                            <p className="mb-1 font-semibold uppercase tracking-wide text-muted">Margins</p>
                            <ul className="space-y-0.5">
                              {Object.entries(ra.margins).map(([m, v]) => {
                                const mi = v && typeof v === "object" ? (v as MarginInfo) : null;
                                const cur = mi ? mi.current_pct : (v as number | null);
                                return (
                                  <li key={m} className="flex justify-between gap-2">
                                    <span className="text-muted">{titleCase(m)}</span>
                                    <span className="num">
                                      {cur == null ? "n/a" : pct(cur, 1, false)}
                                      {mi?.change_bps_yoy != null ? (
                                        <span className={mi.change_bps_yoy >= 0 ? "text-up" : "text-down"}>
                                          {" "}
                                          ({mi.change_bps_yoy >= 0 ? "+" : "\u2212"}
                                          {num(Math.abs(mi.change_bps_yoy), 0)} bps YoY)
                                        </span>
                                      ) : null}
                                    </span>
                                  </li>
                                );
                              })}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                      {ra.flags?.length ? (
                        <ul className="space-y-1">
                          {ra.flags.map((fl, i) => {
                            const o = typeof fl === "string" ? { message: fl, severity: "info" } : fl;
                            return (
                              <li key={i}>
                                <Badge tone={o.severity === "warning" ? "warn" : "info"} size="xs" className="normal-case">
                                  {o.message ?? o.code}
                                </Badge>
                              </li>
                            );
                          })}
                        </ul>
                      ) : null}
                      {ra.other_income_share_pct != null ? (
                        <p className="text-muted">Other income share of profit: {pct(ra.other_income_share_pct, 1, false)}</p>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-muted">No result analysis available.</p>
                  )}
                </CardBody>
              </Card>
            </div>
            <Card>
              <CardHeader title="Key metrics" subtitle="Each metric carries its own source and period" />
              {metrics.length ? (
                <TableWrap label="Fundamental metrics">
                  <THead>
                    <tr>
                      <Th>Metric</Th>
                      <Th align="right">Value</Th>
                      <Th>Period end</Th>
                      <Th>Source</Th>
                      <Th>Note</Th>
                    </tr>
                  </THead>
                  <tbody>
                    {metrics.map(([k, m]) => (
                      <Tr key={k}>
                        <Td className="font-medium">{titleCase(k)}</Td>
                        <Td align="right">{m?.value == null ? <NAValue reason={m?.note} /> : `${scalar(m.value)}${m.unit ? ` ${m.unit}` : ""}`}</Td>
                        <Td className="whitespace-nowrap text-xs">{dateIST(m?.period_end)}</Td>
                        <Td className="text-xs text-muted">{m?.source ?? "n/a"}</Td>
                        <Td className="text-xs text-muted">{m?.note ?? ""}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <EmptyState compact title="No fundamental metrics yet">An admin can run the fundamentals job from Settings → Jobs.</EmptyState>
              )}
            </Card>
            {f.reasons?.length || f.cautions?.length ? (
              <Card>
                <CardHeader title="Score drivers" />
                <CardBody className="grid gap-3 text-xs sm:grid-cols-2">
                  <ul className="list-inside list-disc space-y-0.5 text-up">{(f.reasons ?? []).map((r, i) => <li key={i}><span className="text-fg">{r}</span></li>)}</ul>
                  <ul className="list-inside list-disc space-y-0.5 text-warn">{(f.cautions ?? []).map((r, i) => <li key={i}><span className="text-fg">{r}</span></li>)}</ul>
                </CardBody>
              </Card>
            ) : null}
            {f.notes?.length ? (
              <ul className="list-inside list-disc text-xs text-muted">
                {f.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            ) : null}
            <DataStamp asOf={f.as_of ?? f.price_used?.as_of} source={`Exchange filings${f.basis ? ` (${f.basis})` : ""}; valuation uses ${f.price_used?.kind === "eod_close" ? "EOD close" : "latest price"}`} />
          </div>
        );
      }}
    </QueryState>
  );
}

/* ------------------------------------------------------------------ Results */

export function ResultsPanel({ symbol }: { symbol: string }) {
  const q = useFundamentals(symbol);
  return (
    <QueryState query={q} skeleton={skel}>
      {(f) =>
        f.results?.length ? (
          <Card>
            <CardHeader title="Quarterly results" subtitle="Figures as filed with the exchange (units as reported in the filing)" />
            <TableWrap label="Quarterly results">
              <THead>
                <tr>
                  <Th>Period end</Th>
                  <Th align="right">Revenue</Th>
                  <Th align="right">EBITDA</Th>
                  <Th align="right">PAT</Th>
                  <Th align="right">EPS (basic)</Th>
                  <Th>Basis</Th>
                  <Th>Filed</Th>
                  <Th>Source</Th>
                </tr>
              </THead>
              <tbody>
                {[...f.results]
                  .sort((a, b) => (a.period_end < b.period_end ? 1 : -1))
                  .map((r, i) => (
                    <Tr key={`${r.period_end}-${i}`}>
                      <Td className="whitespace-nowrap font-medium">{dateIST(r.period_end)}</Td>
                      <Td align="right">{num(r.revenue, 0)}</Td>
                      <Td align="right">{num(r.ebitda, 0)}</Td>
                      <Td align="right">{num(r.pat, 0)}</Td>
                      <Td align="right">{num(r.eps_basic, 2)}</Td>
                      <Td className="text-xs">{r.consolidated == null ? "n/a" : r.consolidated ? "Consolidated" : "Standalone"}</Td>
                      <Td className="whitespace-nowrap text-xs">{dateTimeIST(r.broadcast_at)}</Td>
                      <Td>
                        {r.source_url ? (
                          <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                            Filing <ExternalLink className="size-3" aria-hidden />
                          </a>
                        ) : (
                          <span className="text-xs text-subtle">n/a</span>
                        )}
                      </Td>
                    </Tr>
                  ))}
              </tbody>
            </TableWrap>
          </Card>
        ) : (
          <EmptyState title="No results filed yet">Quarterly results are ingested from exchange filings by the fundamentals job.</EmptyState>
        )
      }
    </QueryState>
  );
}

/* --------------------------------------------------------------------- News */

export function NewsPanel({ symbol }: { symbol: string }) {
  const q = useStockNews(symbol);
  return (
    <Card>
      <CardHeader title={`News & announcements — ${symbol}`} subtitle="AI summaries separate FACT, INTERPRETATION and SPECULATION" />
      <QueryState query={q} skeleton={skel}>
        {(items) => <NewsList items={items} />}
      </QueryState>
    </Card>
  );
}

/* ---------------------------------------------------------------------- F&O */

function FnoStats({ s }: { s: FnoSnapshot }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
      <Stat size="sm" label="Spot" value={inr(s.spot, 2)} />
      <Stat size="sm" label="Futures" value={inr(s.fut_price, 2)} sub={s.basis_pct == null ? undefined : `basis ${pct(s.basis_pct)}`} />
      <Stat size="sm" label="Fut OI change" value={<Pct value={s.fut_oi_change_pct} />} />
      <Stat size="sm" label="PCR (OI)" value={s.pcr_oi == null ? "n/a" : num(s.pcr_oi, 2)} />
      <Stat size="sm" label="Max pain" value={inr(s.max_pain, 0)} />
      <Stat size="sm" label="ATM IV" value={s.atm_iv == null ? "n/a" : ratioPct(s.atm_iv, 1)} sub={s.iv_percentile == null ? undefined : `IV pctl ${num(s.iv_percentile, 0)}`} />
      <Stat size="sm" label="Call resistance" value={inr(s.call_resistance, 0)} />
      <Stat size="sm" label="Put support" value={inr(s.put_support, 0)} />
      <Stat size="sm" label="Build-up" value={s.buildup ? titleCase(s.buildup) : "n/a"} />
    </div>
  );
}

export function FnoPanel({ symbol, isFno }: { symbol: string; isFno?: boolean }) {
  const q = useStockFno(symbol, isFno !== false);
  if (isFno === false)
    return (
      <EmptyState title="F&O: n/a">
        {symbol} is not in the NSE F&amp;O segment, so futures/options data does not exist for it. Its score excludes the F&amp;O component (n/a, not zero).
      </EmptyState>
    );
  return (
    <QueryState query={q} skeleton={skel} unavailableHint="An admin can run the F&O job from Settings → Jobs.">
      {(d) =>
        !d.snapshot ? (
          <DataUnavailable message={d.message ?? "No F&O snapshot for this stock yet."} hint="An admin can run the F&O job from Settings → Jobs." />
        ) : (
          <div className="space-y-4">
            <DataStatusBanner status={d.status} message={d.message ?? undefined} />
            <Card>
              <CardHeader title="Derivatives snapshot" subtitle="End-of-day F&O bhavcopy & option chain aggregates" />
              <CardBody>
                <FnoStats s={d.snapshot} />
                {d.snapshot.interpretation ? <p className="mt-3 rounded-md bg-surface-2 px-3 py-2 text-xs">{d.snapshot.interpretation}</p> : null}
                <DataStamp className="mt-3" asOf={d.snapshot.date} source="NSE F&O bhavcopy" kind="eod_close" />
              </CardBody>
            </Card>
            {d.history?.length ? (
              <Card>
                <CardHeader title="History" />
                <TableWrap label="F&O history">
                  <THead>
                    <tr>
                      <Th>Date</Th>
                      <Th align="right">Futures</Th>
                      <Th align="right">Basis</Th>
                      <Th align="right">OI chg</Th>
                      <Th align="right">PCR</Th>
                      <Th align="right">ATM IV</Th>
                      <Th>Build-up</Th>
                    </tr>
                  </THead>
                  <tbody>
                    {d.history.map((h, i) => (
                      <Tr key={`${h.date}-${i}`}>
                        <Td className="whitespace-nowrap">{dateIST(h.date)}</Td>
                        <Td align="right">{inr(h.fut_price, 2)}</Td>
                        <Td align="right"><Pct value={h.basis_pct} /></Td>
                        <Td align="right"><Pct value={h.fut_oi_change_pct} /></Td>
                        <Td align="right">{h.pcr_oi == null ? "n/a" : num(h.pcr_oi, 2)}</Td>
                        <Td align="right">{h.atm_iv == null ? "n/a" : ratioPct(h.atm_iv, 1)}</Td>
                        <Td className="text-xs">{h.buildup ? titleCase(h.buildup) : "n/a"}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </TableWrap>
              </Card>
            ) : null}
          </div>
        )
      }
    </QueryState>
  );
}

/* ------------------------------------------------------------- Shareholding */

const SH_COLS: [keyof ShareholdingRow, string][] = [
  ["promoter_pct", "Promoter"],
  ["fii_pct", "FII/FPI"],
  ["dii_pct", "DII"],
  ["public_pct", "Public"],
  ["mf_pct", "Mutual funds"],
  ["promoter_pledged_pct", "Pledged (of promoter)"],
];

export function ShareholdingPanel({ symbol }: { symbol: string }) {
  const q = useShareholding(symbol);
  return (
    <QueryState query={q} skeleton={skel}>
      {(rows) =>
        rows.length ? (
          <Card>
            <CardHeader title="Shareholding pattern" subtitle="Quarterly, as filed" />
            <TableWrap label="Shareholding pattern">
              <THead>
                <tr>
                  <Th>Quarter</Th>
                  {SH_COLS.map(([, l]) => (
                    <Th key={l} align="right">{l}</Th>
                  ))}
                  <Th>Source</Th>
                </tr>
              </THead>
              <tbody>
                {rows.map((r, i) => (
                  <Tr key={`${r.period_end}-${i}`}>
                    <Td className="whitespace-nowrap font-medium">{dateIST(r.period_end)}</Td>
                    {SH_COLS.map(([k, l]) => {
                      const v = toNum(r[k] as number | null | undefined);
                      return (
                        <Td key={l} align="right">
                          {v === null ? <NAValue /> : pct(v, 2, false)}
                        </Td>
                      );
                    })}
                    <Td className="text-xs text-muted">{r.source ?? "n/a"}</Td>
                  </Tr>
                ))}
              </tbody>
            </TableWrap>
          </Card>
        ) : (
          <EmptyState title="No shareholding data yet">Shareholding patterns are loaded from quarterly exchange filings.</EmptyState>
        )
      }
    </QueryState>
  );
}

/* -------------------------------------------------------- Corporate actions */

export function CorporateActionsPanel({ symbol }: { symbol: string }) {
  const q = useCorporateActions(symbol);
  return (
    <QueryState query={q} skeleton={skel}>
      {(rows) =>
        rows.length ? (
          <Card>
            <CardHeader title="Corporate actions" subtitle="Splits, bonuses and dividends are applied to price history (adjusted bars)" />
            <TableWrap label="Corporate actions">
              <THead>
                <tr>
                  <Th>Ex-date</Th>
                  <Th>Type</Th>
                  <Th>Details</Th>
                  <Th align="right">Amount / ratio</Th>
                  <Th>Record date</Th>
                  <Th>Source</Th>
                </tr>
              </THead>
              <tbody>
                {rows.map((c, i) => (
                  <Tr key={c.id ?? i}>
                    <Td className="whitespace-nowrap">{dateIST(c.ex_date)}</Td>
                    <Td><Badge tone="neutral" size="xs">{titleCase(c.action_type ?? c.kind ?? "action")}</Badge></Td>
                    <Td className="max-w-md text-xs">{c.subject ?? c.purpose ?? c.details ?? "—"}</Td>
                    <Td align="right">
                      {c.ratio ?? (c.ratio_from != null && c.ratio_to != null ? `${num(c.ratio_from, 0)}:${num(c.ratio_to, 0)}` : c.amount != null ? inr(c.amount, 2) : "n/a")}
                    </Td>
                    <Td className="whitespace-nowrap text-xs">{dateIST(c.record_date)}</Td>
                    <Td className="text-xs text-muted">{c.source ?? "n/a"}</Td>
                  </Tr>
                ))}
              </tbody>
            </TableWrap>
          </Card>
        ) : (
          <EmptyState title="No corporate actions on record">An admin can run the corporate_actions job from Settings → Jobs.</EmptyState>
        )
      }
    </QueryState>
  );
}

/* -------------------------------------------------------------- AI analysis */

const AI_SECTIONS: [string, string][] = [
  ["technical", "Technical"],
  ["fundamental", "Fundamental"],
  ["news", "News"],
  ["fno", "F&O"],
  ["market_context", "Market context"],
  ["entry", "Entry"],
  ["stop", "Stop"],
  ["targets", "Targets"],
  ["risk_reward", "Risk / reward"],
  ["invalidation", "Invalidation"],
  ["final_score", "Final score"],
];

export function AIPanel({ symbol }: { symbol: string }) {
  const q = useAnalysis(symbol);
  const regen = useRegenerateAnalysis(symbol);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">
          The AI explains NIVARA&apos;s computed fact sheet only; numbers it cannot trace to that data are flagged by guardrails. It can be wrong — verify against the figures.
        </p>
        <Button size="sm" variant="outline" loading={regen.isPending} icon={<RefreshCw className="size-3.5" aria-hidden />} onClick={() => regen.mutate()}>
          Regenerate
        </Button>
      </div>
      {regen.isError ? <ErrorState error={regen.error} title="Regeneration failed" /> : null}
      <QueryState query={q} skeleton={skel}>
        {(a) => {
          if (!a.sections) {
            return (
              <DataStatusBanner
                status={a.status === "data_stale" ? "data_stale" : "data_unavailable"}
                message={a.message ?? "Analysis is not available for this stock yet."}
                hint="It needs ingested price history (Settings → Jobs)."
              />
            );
          }
          const s = a.sections;
          const citations = a.citations ?? (Array.isArray(s.citations) ? (s.citations as NonNullable<typeof a.citations>) : []);
          const fallbackOnly = a.status === "ai_not_configured" || a.status === "error";
          return (
            <div className="space-y-4">
              {a.status === "ai_not_configured" ? (
                <div className="rounded-lg border border-info/40 bg-info-soft px-3 py-2 text-xs text-info" role="status">
                  <p className="flex items-center gap-1 font-semibold">
                    <Sparkles className="size-3.5" aria-hidden /> AI not configured — showing the deterministic, rule-based summary
                  </p>
                  <p className="mt-0.5">{a.message ?? "An administrator can set ANTHROPIC_API_KEY to enable AI explanations."}</p>
                </div>
              ) : a.status === "error" ? (
                <ErrorState title="AI provider failed — showing the deterministic summary instead" message={a.message ?? "The AI provider returned an error."} />
              ) : null}
              {a.guardrail_flags?.length ? (
                <div className="rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-xs text-warn" role="alert">
                  <p className="flex items-center gap-1 font-semibold">
                    <ShieldAlert className="size-3.5" aria-hidden /> Guardrail flags ({a.guardrail_flags.length})
                  </p>
                  <ul className="mt-1 list-inside list-disc">
                    {a.guardrail_flags.map((g, i) => (
                      <li key={i}>{g}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {s.executive_summary ? (
                <Card>
                  <CardHeader icon={<Sparkles className="size-4" />} title="Executive summary" subtitle={fallbackOnly ? "Deterministic (no language model)" : `AI · ${a.model ?? "model n/a"}`} />
                  <CardBody className="text-sm leading-relaxed">{s.executive_summary}</CardBody>
                </Card>
              ) : null}
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <CardHeader title={<span className="text-up">Bull case</span>} />
                  <CardBody>
                    {s.bull_case?.length ? <ul className="list-inside list-disc space-y-1 text-xs">{s.bull_case.map((b, i) => <li key={i}>{b}</li>)}</ul> : <p className="text-xs text-muted">n/a</p>}
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title={<span className="text-down">Bear case</span>} />
                  <CardBody>
                    {s.bear_case?.length ? <ul className="list-inside list-disc space-y-1 text-xs">{s.bear_case.map((b, i) => <li key={i}>{b}</li>)}</ul> : <p className="text-xs text-muted">n/a</p>}
                  </CardBody>
                </Card>
              </div>
              <Card>
                <CardBody className="grid gap-x-6 gap-y-3 md:grid-cols-2">
                  {AI_SECTIONS.map(([k, label]) =>
                    s[k] != null && s[k] !== "" ? (
                      <div key={k}>
                        <p className="text-[11px] font-bold uppercase tracking-wide text-muted">{label}</p>
                        <p className="mt-0.5 text-xs leading-relaxed">{scalar(s[k])}</p>
                      </div>
                    ) : null,
                  )}
                </CardBody>
              </Card>
              {citations.length ? (
                <Card>
                  <CardHeader title="Citations" subtitle="Fact-sheet fields the explanation relies on" />
                  <TableWrap label="AI citations">
                    <THead>
                      <tr>
                        <Th>Item</Th>
                        <Th>Field / value</Th>
                        <Th>Source</Th>
                      </tr>
                    </THead>
                    <tbody>
                      {citations.map((c, i) => (
                        <Tr key={i}>
                          <Td className="text-xs">{c.label}</Td>
                          <Td className="font-mono text-xs">{c.field ?? scalar(c.value)}</Td>
                          <Td className="text-xs text-muted">{c.source ?? "NIVARA fact sheet"}</Td>
                        </Tr>
                      ))}
                    </tbody>
                  </TableWrap>
                </Card>
              ) : null}
              <DataStamp asOf={a.data_as_of} source="NIVARA fact sheet" />
              <p className="text-[11px] text-muted">
                Generated {dateTimeIST(a.generated_at)} · {a.disclaimer ?? "AI output is research assistance, not investment advice."}
              </p>
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}

/* --------------------------------------------------------- Historical signals */

export function SignalsPanel({ symbol }: { symbol: string }) {
  const q = useSignals(symbol);
  return (
    <QueryState query={q} skeleton={skel}>
      {(d) => {
        const recs = d.recommendations ?? [];
        const scores = d.scores ?? [];
        if (!recs.length && !scores.length)
          return <EmptyState title="No signals recorded yet">Signals accumulate as the daily scan evaluates this stock.</EmptyState>;
        return (
          <div className="space-y-4">
            {scores.length ? (
              <Card>
                <CardHeader title="Score history" subtitle={`${scores.length} scans · latest ${dateIST(scores[scores.length - 1]?.session_date)}`} />
                <CardBody className="flex flex-wrap items-center gap-4">
                  <Sparkline values={scores.map((x) => (x.score == null ? null : Number(x.score)))} width={280} height={48} label="Opportunity score history" />
                  <div className="text-xs text-muted">
                    Latest score <ScorePill value={scores[scores.length - 1]?.score} /> · {scores.filter((x) => x.rejected).length} of {scores.length} scans rejected by filters
                  </div>
                </CardBody>
              </Card>
            ) : null}
            <Card>
              <CardHeader title="Published recommendations" subtitle="Ideas that made the Top 10, and how they played out" />
              {recs.length ? (
                <TableWrap label="Historical recommendations">
                  <THead>
                    <tr>
                      <Th>Session</Th>
                      <Th align="right">Rank</Th>
                      <Th align="center">Score</Th>
                      <Th>Setup</Th>
                      <Th>Action</Th>
                      <Th align="right">Entry</Th>
                      <Th align="right">Stop</Th>
                      <Th>Outcome</Th>
                      <Th align="right">Return</Th>
                    </tr>
                  </THead>
                  <tbody>
                    {recs.map((r) => (
                      <Tr key={r.id}>
                        <Td className="whitespace-nowrap">{dateIST(r.session_date)}</Td>
                        <Td align="right">{r.rank ?? "–"}</Td>
                        <Td align="center"><ScorePill value={r.score} /></Td>
                        <Td className="text-xs">{titleCase(r.setup)}</Td>
                        <Td><ActionBadge action={r.action} /></Td>
                        <Td align="right" className="whitespace-nowrap">{inr(r.entry_low, 2)}–{inr(r.entry_high, 2).replace("₹", "")}</Td>
                        <Td align="right">{inr(r.stop, 2)}</Td>
                        <Td className="text-xs">{r.outcome?.status ? titleCase(r.outcome.status) : "pending"}</Td>
                        <Td align="right"><Pct value={r.outcome?.return_pct} /></Td>
                      </Tr>
                    ))}
                  </tbody>
                </TableWrap>
              ) : (
                <p className="px-4 py-3 text-xs text-muted">{symbol} has not appeared in a published Top 10 yet.</p>
              )}
            </Card>
          </div>
        );
      }}
    </QueryState>
  );
}
