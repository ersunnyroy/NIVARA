"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { useStockSearch } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Card, EmptyState, ErrorState, Input, SkeletonRows, TableWrap, Td, Th, THead, Tr } from "@/components/ui";

export default function StocksPage() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 250);
    return () => clearTimeout(t);
  }, [text]);
  const res = useStockSearch(q, 50);

  return (
    <div className="space-y-4">
      <PageHeader title="Stocks" description="Search the NSE securities master by symbol or company name." />
      <div className="relative max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden />
        <Input
          aria-label="Search stocks by symbol or name"
          placeholder="e.g. RELIANCE, HDFC Bank, TCS…"
          className="h-11 pl-9 text-base"
          value={text}
          autoFocus
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <Card>
        {!q ? (
          <EmptyState title="Start typing to search">
            Open any stock for its chart, technicals, fundamentals, news, F&amp;O data, AI analysis and a trade-setup with position sizing.
          </EmptyState>
        ) : res.isPending ? (
          <SkeletonRows rows={6} className="p-4" />
        ) : res.isError ? (
          <div className="p-4">
            <ErrorState error={res.error} onRetry={() => res.refetch()} />
          </div>
        ) : !res.data.length ? (
          <EmptyState title={`No stocks match “${q}”`}>
            If the list is empty for every query, the securities master has not been loaded yet — an admin can run the “securities” job from Settings → Jobs.
          </EmptyState>
        ) : (
          <TableWrap label="Search results">
            <THead>
              <tr>
                <Th>Symbol</Th>
                <Th>Company</Th>
                <Th>Sector</Th>
                <Th>Segment</Th>
              </tr>
            </THead>
            <tbody>
              {res.data.map((s) => (
                <Tr key={s.symbol}>
                  <Td>
                    <Link href={`/stocks/${encodeURIComponent(s.symbol)}`} className="font-semibold text-accent hover:underline">
                      {s.symbol}
                    </Link>
                  </Td>
                  <Td>{s.name ?? "—"}</Td>
                  <Td className="text-muted">{s.sector ?? "n/a"}</Td>
                  <Td>{s.is_fno ? <Badge tone="info" size="xs">F&amp;O</Badge> : <span className="text-xs text-muted">Cash</span>}</Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>
    </div>
  );
}
