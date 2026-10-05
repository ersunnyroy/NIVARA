import Link from "next/link";
import { compactNum, crore, dateIST, inr, int, pct, titleCase, toNum } from "@/lib/format";
import type { Breadth, FlowRow, IndexQuote, Mover, SectorRow } from "@/lib/types";
import { EmptyState, NAValue, Pct, Segmented, TableWrap, Td, Th, THead, Tr, cn } from "@/components/ui";

export function IndicesStrip({ indices }: { indices?: IndexQuote[] }) {
  if (!indices?.length) return <EmptyState compact title="No index data yet">Run the EOD ingestion job to load index closes.</EmptyState>;
  return (
    <div className="scroll-thin flex gap-2 overflow-x-auto pb-1">
      {indices.map((i) => (
        <div key={i.name} className="min-w-36 shrink-0 rounded-lg border border-border bg-surface-2/50 px-3 py-2">
          <p className="truncate text-[11px] font-medium text-muted">{i.name}</p>
          <p className="num text-sm font-semibold">{i.close == null ? "n/a" : inr(i.close, 2).replace("₹", "")}</p>
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <Pct value={i.change_pct} />
            <span className="text-subtle">{i.date ? dateIST(i.date) : ""}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function MoversTable({ rows, showVolume }: { rows?: Mover[]; showVolume?: boolean }) {
  if (!rows?.length) return <EmptyState compact title="No movers available">EOD bars are needed to compute movers.</EmptyState>;
  return (
    <TableWrap>
      <THead>
        <tr>
          <Th>Stock</Th>
          <Th align="right">Close</Th>
          <Th align="right">Change</Th>
          {showVolume ? <Th align="right">Volume</Th> : null}
        </tr>
      </THead>
      <tbody>
        {rows.map((m) => (
          <Tr key={m.symbol}>
            <Td>
              <Link href={`/stocks/${encodeURIComponent(m.symbol)}`} className="font-semibold hover:text-accent hover:underline">
                {m.symbol}
              </Link>
              <div className="max-w-40 truncate text-[11px] text-muted">{m.name}</div>
            </Td>
            <Td align="right">{inr(m.close, 2)}</Td>
            <Td align="right">
              <Pct value={m.change_pct} />
            </Td>
            {showVolume ? <Td align="right">{compactNum(m.volume)}</Td> : null}
          </Tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

export type MoverTab = "gainers" | "losers" | "most_active";

export function MoversSwitch({ value, onChange }: { value: MoverTab; onChange: (v: MoverTab) => void }) {
  return (
    <Segmented
      size="xs"
      label="Mover list"
      value={value}
      onChange={onChange}
      options={[
        { key: "gainers", label: "Gainers" },
        { key: "losers", label: "Losers" },
        { key: "most_active", label: "Most active" },
      ]}
    />
  );
}

export function SectorTable({ rows, limit }: { rows?: SectorRow[]; limit?: number }) {
  if (!rows?.length) return <EmptyState compact title="No sector strength data">Sector indices are computed after EOD ingestion.</EmptyState>;
  const sorted = [...rows].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)).slice(0, limit ?? rows.length);
  return (
    <TableWrap label="Sector performance">
      <THead>
        <tr>
          <Th align="right">#</Th>
          <Th>Sector</Th>
          <Th align="right">1W</Th>
          <Th align="right">1M</Th>
          <Th align="right">3M</Th>
          <Th align="right">RS vs Nifty 1M</Th>
          <Th>Trend</Th>
        </tr>
      </THead>
      <tbody>
        {sorted.map((s) => (
          <Tr key={s.index_name}>
            <Td align="right" className="text-muted">
              {s.rank ?? "–"}
            </Td>
            <Td className="whitespace-nowrap font-medium">{s.index_name}</Td>
            <Td align="right"><Pct value={s.ret_1w} /></Td>
            <Td align="right"><Pct value={s.ret_1m} /></Td>
            <Td align="right"><Pct value={s.ret_3m} /></Td>
            <Td align="right"><Pct value={s.rs_vs_nifty_1m} /></Td>
            <Td className="whitespace-nowrap text-xs">{s.trend ? titleCase(s.trend) : <NAValue />}</Td>
          </Tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

export function BreadthPanel({ breadth }: { breadth?: Breadth | null }) {
  if (!breadth) return <EmptyState compact title="No breadth data">Breadth is computed from the EOD bhavcopy.</EmptyState>;
  const adv = toNum(breadth.advances);
  const dec = toNum(breadth.declines);
  const unch = toNum(breadth.unchanged) ?? 0;
  const total = adv !== null && dec !== null ? adv + dec + unch : null;
  return (
    <div className="space-y-3">
      {total ? (
        <div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-3" aria-hidden>
            <span className="bg-up" style={{ width: `${((adv as number) / total) * 100}%` }} />
            <span className="bg-subtle/50" style={{ width: `${(unch / total) * 100}%` }} />
            <span className="bg-down" style={{ width: `${((dec as number) / total) * 100}%` }} />
          </div>
          <div className="num mt-1 flex justify-between text-[11px]">
            <span className="text-up">▲ {int(adv)} advances</span>
            <span className="text-muted">{int(unch)} unch.</span>
            <span className="text-down">▼ {int(dec)} declines</span>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted">Advance/decline: n/a</p>
      )}
      <dl className="grid grid-cols-2 gap-2 text-xs">
        {[
          ["% above 50-DMA", breadth.pct_above_50dma == null ? null : pct(breadth.pct_above_50dma, 1, false)],
          ["% above 200-DMA", breadth.pct_above_200dma == null ? null : pct(breadth.pct_above_200dma, 1, false)],
          ["New 52w highs", breadth.new_52w_highs == null ? null : int(breadth.new_52w_highs)],
          ["New 52w lows", breadth.new_52w_lows == null ? null : int(breadth.new_52w_lows)],
        ].map(([k, v]) => (
          <div key={k as string} className="rounded-md bg-surface-2 px-2 py-1.5">
            <dt className="text-muted">{k}</dt>
            <dd className="num font-semibold">{v ?? <NAValue />}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function FlowsTable({ rows, limit = 10 }: { rows?: FlowRow[]; limit?: number }) {
  if (!rows?.length) return <EmptyState compact title="No FII/DII flow data">Run the flows ingestion job.</EmptyState>;
  const sorted = [...rows].sort((a, b) => (a.date < b.date ? 1 : -1)).slice(0, limit);
  return (
    <TableWrap label="Institutional flows">
      <THead>
        <tr>
          <Th>Date</Th>
          <Th>Category</Th>
          <Th align="right">Buy</Th>
          <Th align="right">Sell</Th>
          <Th align="right">Net</Th>
        </tr>
      </THead>
      <tbody>
        {sorted.map((f, i) => {
          const n = toNum(f.net_value_cr);
          return (
            <Tr key={`${f.date}-${f.category}-${i}`}>
              <Td className="whitespace-nowrap">{dateIST(f.date)}</Td>
              <Td>{f.category}</Td>
              <Td align="right">{crore(f.buy_value_cr, false)}</Td>
              <Td align="right">{crore(f.sell_value_cr, false)}</Td>
              <Td align="right" className={cn("font-semibold", n === null ? "text-subtle" : n >= 0 ? "text-up" : "text-down")}>
                {crore(f.net_value_cr)}
              </Td>
            </Tr>
          );
        })}
      </tbody>
    </TableWrap>
  );
}
