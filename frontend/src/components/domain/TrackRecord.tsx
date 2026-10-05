import { int, pct, toNum } from "@/lib/format";
import type { BucketStat, TrackRecord } from "@/lib/types";
import { EmptyState, Pct, Stat, TableWrap, Td, Th, THead, Tr } from "@/components/ui";

export function rate(v: number | null | undefined): string {
  // Backend reports rates on a 0–100 scale.
  const n = toNum(v ?? null);
  return n === null ? "n/a" : pct(n, 1, false);
}

export function TrackRecordStats({ tr, compact }: { tr?: TrackRecord | null; compact?: boolean }) {
  const t = tr?.totals;
  if (!t || !t.count) {
    return (
      <EmptyState compact title="No track record yet">
        Outcomes are evaluated after recommendations play out (T1/T2/stop hit or holding window ends). Paper-trade ideas in the meantime.
      </EmptyState>
    );
  }
  return (
    <div className={compact ? "grid grid-cols-2 gap-4 sm:grid-cols-4" : "grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5"}>
      <Stat size="sm" label="Ideas / traded / closed" value={`${int(t.count)} / ${int(t.traded)} / ${int(t.closed)}`} sub={t.open != null ? `${int(t.open)} open · ${int(t.not_triggered)} not triggered` : undefined} />
      <Stat size="sm" label="Win rate" value={rate(t.win_rate)} />
      <Stat size="sm" label="T1 hit rate" value={rate(t.t1_hit_rate)} />
      <Stat size="sm" label="Avg return" value={<Pct value={t.avg_return_pct} />} />
      {!compact ? (
        <>
          <Stat size="sm" label="T2 hit rate" value={rate(t.t2_hit_rate)} />
          <Stat size="sm" label="Stop hit rate" value={rate(t.stop_hit_rate)} />
          <Stat size="sm" label="Avg MFE" value={<Pct value={t.avg_mfe_pct} />} sub="max favourable excursion" />
          <Stat size="sm" label="Avg MAE" value={<Pct value={t.avg_mae_pct} />} sub="max adverse excursion" />
        </>
      ) : null}
    </div>
  );
}

export function BucketTable({ rows, label }: { rows?: BucketStat[]; label: string }) {
  if (!rows?.length) return <p className="px-4 py-3 text-xs text-muted">No closed outcomes in this breakdown yet.</p>;
  return (
    <TableWrap label={label}>
      <THead>
        <tr>
          <Th>{label}</Th>
          <Th align="right">Count</Th>
          <Th align="right">Win rate</Th>
          <Th align="right">Avg return</Th>
        </tr>
      </THead>
      <tbody>
        {rows.map((r) => (
          <Tr key={r.bucket}>
            <Td className="font-medium">{r.bucket}</Td>
            <Td align="right">{int(r.count)}</Td>
            <Td align="right">{rate(r.win_rate)}</Td>
            <Td align="right">
              <Pct value={r.avg_return_pct} />
            </Td>
          </Tr>
        ))}
      </tbody>
    </TableWrap>
  );
}
