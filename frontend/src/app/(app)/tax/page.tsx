"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, ListTree, Receipt, Scale, UserCog } from "lucide-react";
import { useSaveTaxProfile, useTaxProfile, useTaxSummary } from "@/lib/hooks";
import { fyFor, inrSigned, NA, pct, titleCase, todayIST, toNum } from "@/lib/format";
import type { Numeric } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { EstimatedTag } from "@/components/domain/badges";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DataStatusBanner,
  Disclaimer,
  EmptyState,
  ErrorState,
  Field,
  Money,
  NAValue,
  Pnl,
  QueryState,
  Select,
  SkeletonCard,
  SkeletonRows,
  Stat,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";
import { Harvesting } from "./_components/Harvesting";
import { TaxProfileForm } from "./_components/TaxProfileForm";
import type { TaxBucketX, TaxProfileX, TaxSummaryX, TermTotal } from "./_components/types";

/* ------------------------------------------------------------------ helpers */

function fyStart(fy: string): number | null {
  const y = Number(fy.slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

function fyLabel(start: number): string {
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

function fyOptions(current: string, available?: string[]): string[] {
  const s = fyStart(current);
  const base = s === null ? [current] : [0, 1, 2, 3].map((d) => fyLabel(s - d));
  return Array.from(new Set([...base, ...(available ?? [])])).sort().reverse();
}

/** Fractional (0.2) or percent (20) rate → "20.00%"; null → "slab rate". */
function rateText(b: TaxBucketX): string {
  const rp = toNum(b.rate_pct);
  if (rp !== null) return pct(rp, 2, false);
  const r = toNum(b.rate);
  if (r === null) return b.rate === null ? "slab rate" : NA;
  return pct(Math.abs(r) <= 1 ? r * 100 : r, 2, false);
}

function termParts(t: TermTotal | undefined): { gains: Numeric; losses: Numeric; net: Numeric } {
  if (t && typeof t === "object") return { gains: t.gross_gains, losses: t.gross_losses, net: t.net };
  return { gains: undefined, losses: undefined, net: t as Numeric };
}

const TERM_LABEL: Record<string, string> = {
  STCG: "Short-term capital gains",
  LTCG: "Long-term capital gains",
  SPEC: "Speculative (intraday) income",
};

function sumNums(...vals: Numeric[]): number | null {
  let total = 0;
  for (const v of vals) {
    const n = toNum(v);
    if (n === null) return null;
    total += n;
  }
  return total;
}

/* --------------------------------------------------------------- sections */

function StatusBanner({ s }: { s: TaxSummaryX }) {
  const reasons = s.incomplete_reasons ?? [];
  if (s.status === "incomplete" || reasons.length) {
    return (
      <div role="alert" className="rounded-xl border-2 border-warn/50 bg-warn-soft px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-warn">
          <AlertTriangle className="size-4" aria-hidden /> Tax estimate incomplete
        </p>
        <p className="mt-1 text-xs text-fg/80">{s.message ?? "Additional tax information is required for a complete estimate."}</p>
        {reasons.length ? (
          <ul className="mt-2 list-inside list-disc space-y-0.5 text-sm text-fg">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : null}
        <p className="mt-2 text-xs text-muted">Fill in the tax profile below to resolve missing facts.</p>
      </div>
    );
  }
  if (s.status === "complete" || s.status === "ok") {
    return (
      <p role="status" className="flex items-center gap-2 rounded-lg bg-up-soft px-3 py-2 text-xs font-medium text-up">
        <CheckCircle2 className="size-4" aria-hidden /> Estimate complete for the facts on record (still an estimate — not a filing).
      </p>
    );
  }
  return <DataStatusBanner status={s.status} message={s.message ?? undefined} />;
}

function TotalsCard({ s }: { s: TaxSummaryX }) {
  const totals = s.totals ?? {};
  const keys = Array.from(new Set(["STCG", "LTCG", "SPEC", ...Object.keys(totals)]));
  return (
    <Card>
      <CardHeader icon={<Scale className="size-4" />} title={`Realized gains by term — FY ${s.tax_year ?? NA}`} subtitle="Net = gross gains − gross losses within each term (before set-off)." />
      <CardBody>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {keys.map((k) => {
            const p = termParts(totals[k]);
            return (
              <div key={k} className="rounded-lg border border-border bg-surface-2/40 p-3">
                <Stat label={`${k} · ${TERM_LABEL[k] ?? titleCase(k)}`} value={<Pnl value={p.net} />} />
                <dl className="mt-2 grid grid-cols-2 gap-x-2 text-xs">
                  <dt className="text-muted">Gross gains</dt>
                  <dd className="text-right">
                    <Money value={p.gains} />
                  </dd>
                  <dt className="text-muted">Gross losses</dt>
                  <dd className="text-right">
                    <Money value={p.losses} />
                  </dd>
                </dl>
              </div>
            );
          })}
        </div>
      </CardBody>
    </Card>
  );
}

function BucketsCard({ s }: { s: TaxSummaryX }) {
  const buckets = s.buckets ?? [];
  const showNet = buckets.some((b) => b.net != null);
  const showSurcharge = buckets.some((b) => toNum(b.surcharge) || toNum(b.cess));
  return (
    <Card>
      <CardHeader
        icon={<ListTree className="size-4" />}
        title={
          <span className="inline-flex items-center gap-2">
            Tax buckets <EstimatedTag />
          </span>
        }
        subtitle="Losses are set off against the highest-rate gains first, as permitted; exemption applies to eligible LTCG."
      />
      {buckets.length === 0 ? (
        <CardBody>
          <EmptyState compact title="No taxable buckets for this year">
            No realized sales were found in your live portfolios for FY {s.tax_year ?? NA}. Record SELL transactions in Portfolio to see a tax estimate.
          </EmptyState>
        </CardBody>
      ) : (
        <TableWrap label="Tax buckets">
          <THead>
            <tr>
              <Th>Bucket</Th>
              <Th align="right">Gains</Th>
              <Th align="right">Losses set off</Th>
              {showNet ? <Th align="right">Net</Th> : null}
              <Th align="right">After set-off</Th>
              <Th align="right">Exemption</Th>
              <Th align="right">Taxable</Th>
              <Th align="right">Rate</Th>
              {showSurcharge ? <Th align="right">Surcharge + cess</Th> : null}
              <Th align="right">Tax (est.)</Th>
            </tr>
          </THead>
          <tbody>
            {buckets.map((b, i) => {
              const exemption = sumNums(b.exemption_applied ?? b.exemption, b.basic_exemption_applied ?? 0);
              return (
                <Tr key={b.key ?? i}>
                  <Td>
                    <span className="font-medium">{b.label ?? b.term ?? b.bucket ?? b.key ?? NA}</span>
                    {b.legal_reference ? <span className="block text-[11px] text-muted">{b.legal_reference}</span> : null}
                  </Td>
                  <Td align="right">
                    <Money value={b.gross_gains ?? b.gains} />
                  </Td>
                  <Td align="right">
                    <Money value={b.loss_set_off ?? b.losses} />
                  </Td>
                  {showNet ? (
                    <Td align="right">
                      <Pnl value={b.net} plain />
                    </Td>
                  ) : null}
                  <Td align="right">
                    <Money value={b.after_set_off} />
                  </Td>
                  <Td align="right">
                    <Money value={exemption} />
                  </Td>
                  <Td align="right">
                    <Money value={b.taxable} />
                  </Td>
                  <Td align="right">{rateText(b)}</Td>
                  {showSurcharge ? (
                    <Td align="right">
                      <Money value={sumNums(b.surcharge ?? 0, b.cess ?? 0)} />
                    </Td>
                  ) : null}
                  <Td align="right" className="font-semibold">
                    <Money value={b.total_tax ?? b.tax} />
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
    </Card>
  );
}

function OutcomeCard({ s }: { s: TaxSummaryX }) {
  const afterCharges = s.realized_trading_pnl_after_charges;
  const explicitGross = toNum(s.gross_pnl);
  const derivedGross = explicitGross === null ? sumNums(afterCharges, s.charges_total) : null;
  const gross = explicitGross ?? derivedGross;
  return (
    <Card>
      <CardHeader
        icon={<Receipt className="size-4" />}
        title={
          <span className="inline-flex items-center gap-2">
            Gross vs net — realized this year <EstimatedTag />
          </span>
        }
        subtitle="Gross P&L before charges, next to the net after charges and estimated tax."
      />
      <CardBody className="space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-border p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Gross</p>
            <dl className="mt-2 space-y-1.5 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Gross realized P&amp;L (before charges)</dt>
                <dd>
                  <Pnl value={gross} />
                </dd>
              </div>
              {derivedGross !== null ? <p className="text-[11px] text-subtle">Derived as P&amp;L after charges + charges.</p> : null}
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Charges paid (brokerage, STT, fees, GST, stamp)</dt>
                <dd>
                  <Money value={s.charges_total} />
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">P&amp;L after charges</dt>
                <dd>
                  <Pnl value={afterCharges} />
                </dd>
              </div>
            </dl>
          </div>
          <div className="rounded-lg border border-border p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Net after estimated tax</p>
            <dl className="mt-2 space-y-1.5 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="flex items-center gap-1.5 text-muted">
                  Estimated tax <EstimatedTag />
                </dt>
                <dd>
                  <Money value={s.total_tax_estimate} />
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Net P&amp;L after charges &amp; estimated tax</dt>
                <dd className="font-semibold">
                  <Pnl value={s.net_after_tax} />
                </dd>
              </div>
              {toNum(s.effective_rate) !== null ? (
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">Effective rate on gains</dt>
                  <dd className="num">{pct((toNum(s.effective_rate) as number) * (Math.abs(toNum(s.effective_rate) as number) <= 1 ? 100 : 1), 2, false)}</dd>
                </div>
              ) : null}
            </dl>
          </div>
        </div>

        <div className="rounded-lg border border-warn/30 bg-warn-soft/50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">Potential liability</p>
            <EstimatedTag />
          </div>
          <p className="num mt-1 text-2xl font-bold">
            <Money value={s.total_tax_estimate} />
          </p>
          <div className="mt-1 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Stat size="sm" label="Base tax" value={<Money value={s.base_tax} />} />
            <Stat size="sm" label="Surcharge" value={<Money value={s.surcharge} />} />
            <Stat size="sm" label="Cess" value={<Money value={s.cess} />} />
            <Stat
              size="sm"
              label="LTCG exemption used"
              value={<Money value={s.exemption_used} />}
              sub={toNum(s.exemption_limit) !== null ? <>of <Money value={s.exemption_limit} /> limit</> : undefined}
            />
          </div>
          <p className="mt-2 text-xs text-muted">{s.potential_liability_note ?? "Estimated tax on gains realized so far this tax year."}</p>
        </div>
      </CardBody>
    </Card>
  );
}

function BrokerCompare({ s }: { s: TaxSummaryX }) {
  const br = s.broker_reported;
  if (!br || typeof br !== "object" || !Object.keys(br).length) return null;
  const totals = s.totals ?? {};
  const rows = Object.entries(br).map(([k, v]) => {
    const ours = termParts(totals[k.toUpperCase()]).net;
    const b = toNum(v);
    const o = toNum(ours);
    return { k, broker: v, ours, diff: b !== null && o !== null ? o - b : null };
  });
  return (
    <Card>
      <CardHeader title="Broker-reported comparison" subtitle="Your broker's tax P&L figures (entered in the tax profile) vs NIVARA's computation." />
      <TableWrap label="Broker comparison">
        <THead>
          <tr>
            <Th>Item</Th>
            <Th align="right">Broker reported</Th>
            <Th align="right">NIVARA (net)</Th>
            <Th align="right">Difference</Th>
          </tr>
        </THead>
        <tbody>
          {rows.map((r) => (
            <Tr key={r.k}>
              <Td className="font-medium uppercase">{r.k}</Td>
              <Td align="right">{typeof r.broker === "object" && r.broker !== null ? <code className="text-xs">{JSON.stringify(r.broker)}</code> : <Pnl value={r.broker as Numeric} plain />}</Td>
              <Td align="right">
                <Pnl value={r.ours} plain />
              </Td>
              <Td align="right">
                <Pnl value={r.diff} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableWrap>
      <p className="px-4 py-2 text-[11px] text-muted">Differences usually come from cost basis (grandfathering, corporate actions) or charges treatment. Reconcile before filing.</p>
    </Card>
  );
}

function SetOffCarryForward({ s }: { s: TaxSummaryX }) {
  const log = s.set_off_log ?? [];
  const cf = s.carry_forward ?? {};
  const cfNotes = Array.isArray(cf.notes) ? (cf.notes as unknown[]).map(String) : [];
  const cfNums = Object.entries(cf).filter(([k]) => k !== "notes");
  const cfLabel: Record<string, string> = { stcl: "Short-term loss (STCL)", ltcl: "Long-term loss (LTCL)", speculative_loss: "Speculative loss" };
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Set-off log" subtitle="How losses were applied against gains this year." />
        <CardBody>
          {log.length === 0 ? (
            <p className="text-xs text-muted">No set-offs were needed (or there are no realized losses).</p>
          ) : (
            <ol className="list-inside list-decimal space-y-1 text-sm">
              {log.map((e, i) => (
                <li key={i}>
                  {typeof e === "string" ? (
                    e
                  ) : (
                    <>
                      {e.from ?? NA} → {e.to ?? NA}: <span className="num">{inrSigned(e.amount)}</span>
                      {e.note ? <span className="text-muted"> — {e.note}</span> : null}
                    </>
                  )}
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Carry forward to next year" subtitle="Unabsorbed losses (requires filing the return by the due date)." />
        <CardBody className="space-y-2">
          {cfNums.length === 0 ? (
            <p className="text-xs text-muted">No carry-forward reported.</p>
          ) : (
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {cfNums.map(([k, v]) => (
                <Stat key={k} size="sm" label={cfLabel[k] ?? k.toUpperCase()} value={<Money value={v as Numeric} />} />
              ))}
            </dl>
          )}
          {cfNotes.length ? (
            <ul className="list-inside list-disc text-xs text-muted">
              {cfNotes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

function BySymbol({ s }: { s: TaxSummaryX }) {
  const rows = s.by_symbol ?? [];
  if (!rows.length) return null;
  return (
    <Card>
      <CardHeader title="Realized capital gain by symbol" subtitle="Tax view (STT not deductible); charges shown separately." />
      <TableWrap label="Realized gains by symbol">
        <THead>
          <tr>
            <Th>Symbol</Th>
            <Th align="right">STCG</Th>
            <Th align="right">LTCG</Th>
            <Th align="right">Speculative</Th>
            <Th align="right">Charges</Th>
          </tr>
        </THead>
        <tbody>
          {rows.map((r, i) => (
            <Tr key={r.symbol ?? i}>
              <Td className="font-semibold">
                {r.symbol ? (
                  <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-accent hover:underline">
                    {r.symbol}
                  </Link>
                ) : (
                  <NAValue />
                )}
              </Td>
              <Td align="right">
                <Pnl value={r.STCG} />
              </Td>
              <Td align="right">
                <Pnl value={r.LTCG} />
              </Td>
              <Td align="right">
                <Pnl value={r.SPEC} />
              </Td>
              <Td align="right">
                <Money value={r.charges} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableWrap>
    </Card>
  );
}

function Summary({ fy }: { fy: string }) {
  const q = useTaxSummary(fy);
  if (q.isPending) {
    return (
      <div className="space-y-4">
        <SkeletonCard lines={2} />
        <SkeletonCard lines={5} />
      </div>
    );
  }
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data as TaxSummaryX;
  return (
    <div className="space-y-4">
      <StatusBanner s={s} />
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone="warn">{s.label ?? "ESTIMATED"}</Badge>
        <span>FY {s.tax_year ?? fy}</span>
        {s.rule_set_version ?? s.rule_version ? <span>· Tax rules version {s.rule_set_version ?? s.rule_version}</span> : null}
        <span>· Live portfolios only (paper trades excluded)</span>
      </div>
      <TotalsCard s={s} />
      <OutcomeCard s={s} />
      <BucketsCard s={s} />
      <BrokerCompare s={s} />
      <SetOffCarryForward s={s} />
      <BySymbol s={s} />
      {s.notes?.length ? (
        <Card>
          <CardHeader title="Notes from the tax engine" />
          <CardBody>
            <ul className="list-inside list-disc space-y-0.5 text-xs text-fg/80">
              {s.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
      <div className="space-y-2">
        {s.disclaimer ? <Disclaimer tone="warn">{s.disclaimer}</Disclaimer> : null}
        {s.not_a_filing_tool ? <Disclaimer>{s.not_a_filing_tool}</Disclaimer> : null}
      </div>
    </div>
  );
}

function FySelect({ fy, current, onChange }: { fy: string; current: string; onChange: (v: string) => void }) {
  // Re-uses the cached summary (same query key) to merge FYs that actually have realized trades.
  const q = useTaxSummary(fy);
  const opts = fyOptions(current, (q.data as TaxSummaryX | undefined)?.available_tax_years);
  return (
    <Field label="Financial year" className="w-40">
      {(id) => (
        <Select id={id} value={fy} onChange={(e) => onChange(e.target.value)}>
          {opts.map((o) => (
            <option key={o} value={o}>
              FY {o}
              {o === current ? " (current)" : ""}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}

export default function TaxPage() {
  const [current] = useState(() => fyFor(todayIST()));
  const [fy, setFy] = useState(current);
  const profile = useTaxProfile();
  const saveProfile = useSaveTaxProfile();

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tax Center"
        description="Estimated capital-gains tax on realized trades (Indian FY, April–March), set-offs, carry-forward and a loss-harvesting view."
        actions={<FySelect fy={fy} current={current} onChange={setFy} />}
      />

      <Summary fy={fy} />

      <Card>
        <CardHeader
          icon={<UserCog className="size-4" />}
          title="Tax profile"
          subtitle="Facts the estimate depends on. Missing facts make the estimate incomplete — values are never assumed."
        />
        <CardBody>
          <QueryState query={profile} skeleton={<SkeletonRows rows={4} />}>
            {(p) => <TaxProfileForm key={`${fy}:${JSON.stringify(p)}`} initial={p as TaxProfileX} fy={fy} save={saveProfile} />}
          </QueryState>
        </CardBody>
      </Card>

      <Harvesting />
    </div>
  );
}
