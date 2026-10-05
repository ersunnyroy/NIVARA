"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useStock } from "@/lib/hooks";
import { ChartPanel } from "@/components/stock/ChartPanel";
import {
  AIPanel,
  CorporateActionsPanel,
  FnoPanel,
  FundamentalPanel,
  NewsPanel,
  ResultsPanel,
  ShareholdingPanel,
  SignalsPanel,
  TechnicalPanel,
} from "@/components/stock/Panels";
import { StockHeader } from "@/components/stock/StockHeader";
import { TradeSetupPanel } from "@/components/stock/TradeSetup";
import { ErrorState, Skeleton, TabPanel, Tabs } from "@/components/ui";

const TABS = [
  { key: "technical", label: "Technical" },
  { key: "fundamental", label: "Fundamental" },
  { key: "news", label: "News" },
  { key: "fno", label: "F&O" },
  { key: "results", label: "Results" },
  { key: "shareholding", label: "Shareholding" },
  { key: "corporate-actions", label: "Corporate Actions" },
  { key: "ai", label: "AI Analysis" },
  { key: "setup", label: "Trade Setup" },
  { key: "signals", label: "Historical Signals" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function StockTabs({ symbol, isFno }: { symbol: string; isFno?: boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("tab");
  const tab: TabKey = (TABS.find((t) => t.key === raw)?.key ?? "technical") as TabKey;
  const setTab = (k: TabKey) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", k);
    router.replace(`${pathname}?${sp.toString()}`, { scroll: false });
  };
  const idBase = "stock-tabs";
  return (
    <div>
      <Tabs label="Stock research sections" idBase={idBase} tabs={[...TABS]} value={tab} onChange={setTab} />
      <TabPanel idBase={idBase} k={tab} className="pt-4">
        {tab === "technical" && <TechnicalPanel symbol={symbol} />}
        {tab === "fundamental" && <FundamentalPanel symbol={symbol} />}
        {tab === "news" && <NewsPanel symbol={symbol} />}
        {tab === "fno" && <FnoPanel symbol={symbol} isFno={isFno} />}
        {tab === "results" && <ResultsPanel symbol={symbol} />}
        {tab === "shareholding" && <ShareholdingPanel symbol={symbol} />}
        {tab === "corporate-actions" && <CorporateActionsPanel symbol={symbol} />}
        {tab === "ai" && <AIPanel symbol={symbol} />}
        {tab === "setup" && <TradeSetupPanel symbol={symbol} />}
        {tab === "signals" && <SignalsPanel symbol={symbol} />}
      </TabPanel>
    </div>
  );
}

export default function StockPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw ?? "").toUpperCase();
  const q = useStock(symbol);

  return (
    <div className="space-y-4">
      {q.isPending ? (
        <Skeleton className="h-36 w-full rounded-xl" />
      ) : q.isError ? (
        <ErrorState
          error={q.error}
          title={q.error.isNotFound ? `Stock “${symbol}” not found` : undefined}
          onRetry={() => q.refetch()}
          unavailableHint="Price data appears after EOD ingestion (Settings → Jobs)."
        />
      ) : (
        <StockHeader s={q.data} />
      )}
      <ChartPanel symbol={symbol} />
      <Suspense fallback={<Skeleton className="h-10 w-full" />}>
        <StockTabs symbol={symbol} isFno={q.data?.is_fno} />
      </Suspense>
    </div>
  );
}
