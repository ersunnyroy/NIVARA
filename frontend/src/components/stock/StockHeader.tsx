"use client";

import Link from "next/link";
import { useState } from "react";
import { BellPlus, Star } from "lucide-react";
import { useAddWatchItem, useWatchlists } from "@/lib/hooks";
import { dateIST, inr, inrSigned, titleCase, toNum } from "@/lib/format";
import type { StockDetail } from "@/lib/types";
import { ScorePill } from "@/components/domain/badges";
import { Badge, Button, DataStamp, Pct, PriceKindBadge, Select } from "@/components/ui";

function WatchlistAdd({ symbol }: { symbol: string }) {
  const lists = useWatchlists();
  const add = useAddWatchItem();
  const [sel, setSel] = useState<string>("");
  const first = lists.data?.[0]?.id;
  const target = sel || (first != null ? String(first) : "");
  if (!lists.data?.length) return null;
  return (
    <div className="flex items-center gap-1">
      <Select aria-label="Watchlist" className="h-8 w-40 text-xs" value={target} onChange={(e) => setSel(e.target.value)}>
        {lists.data.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
      </Select>
      <Button
        size="sm"
        variant="outline"
        loading={add.isPending}
        icon={<Star className="size-3.5" aria-hidden />}
        onClick={() => target && add.mutate({ id: Number(target), symbol })}
      >
        {add.isSuccess ? "Added" : "Watch"}
      </Button>
      {add.isError ? <span className="text-[11px] text-down" role="alert">{add.error.message}</span> : null}
    </div>
  );
}

export function StockHeader({ s }: { s: StockDetail }) {
  const p = s.price;
  const price = toNum(p?.price);
  const prev = toNum(p?.prev_close);
  const chg = price !== null && prev !== null ? price - prev : null;
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-4 shadow-card lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">{s.name ?? s.symbol}</h1>
          {s.is_fno ? <Badge tone="info" size="xs">F&amp;O</Badge> : null}
        </div>
        <p className="mt-0.5 text-xs text-muted">
          <span className="font-mono font-semibold text-fg">{s.symbol}</span> · {s.exchange ?? "NSE"}
          {s.isin ? <> · ISIN {s.isin}</> : null}
          {s.sector ? <> · {s.sector}</> : null}
          {s.industry && s.industry !== s.sector ? <> · {s.industry}</> : null}
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-1">
          <span className="num text-3xl font-semibold">{price === null ? "n/a" : inr(price, 2)}</span>
          <span className="num pb-1 text-sm">
            {chg !== null ? <span className={chg >= 0 ? "text-up" : "text-down"}>{inrSigned(chg, 2)} </span> : null}
            <Pct value={p?.change_pct} />
          </span>
          <PriceKindBadge kind={p?.kind} className="mb-1.5" />
        </div>
        <DataStamp className="mt-1" asOf={p?.as_of} source={p?.source} />
        {p?.kind === "eod_close" ? <p className="mt-0.5 text-[11px] text-muted">End-of-day close — not a live price. Prev close {inr(prev, 2)}.</p> : null}
      </div>
      <div className="flex flex-col items-start gap-3 lg:items-end">
        <div className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted">Opportunity score</p>
            <p className="text-xs text-muted">
              {s.latest_signal ? `${titleCase(s.latest_signal.setup)} · ${dateIST(s.latest_signal.session_date)}` : "Not scored in the latest scan"}
            </p>
          </div>
          <ScorePill value={s.latest_signal?.score} className="text-lg" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <WatchlistAdd symbol={s.symbol} />
          <Link
            href={`/alerts?symbol=${encodeURIComponent(s.symbol)}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border-strong px-3 text-xs font-medium hover:bg-surface-2"
          >
            <BellPlus className="size-3.5" aria-hidden /> Alert
          </Link>
        </div>
      </div>
    </div>
  );
}
