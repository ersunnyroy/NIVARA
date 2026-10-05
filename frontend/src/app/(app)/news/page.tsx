"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { useNews } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/PageHeader";
import { NewsList } from "@/components/domain/News";
import { StockSearch } from "@/components/domain/StockSearch";
import { Badge, Button, Card, CardBody, Disclaimer, Field, QueryState, Select, SkeletonRows } from "@/components/ui";

// Mirrors backend/app/news/classify.py categories.
const EVENT_TYPES = [
  "earnings",
  "order_win",
  "acquisition",
  "merger",
  "demerger",
  "management_change",
  "regulatory",
  "litigation",
  "promoter_transaction",
  "fundraising",
  "dividend",
  "buyback",
  "bonus",
  "split",
  "credit_rating",
  "government_policy",
  "sector_development",
  "other",
];

export default function NewsPage() {
  const [symbol, setSymbol] = useState("");
  const [eventType, setEventType] = useState("");
  const [limit, setLimit] = useState(50);
  const q = useNews({ symbol: symbol || undefined, event_type: eventType || undefined, limit });

  return (
    <div className="space-y-4">
      <PageHeader title="News" description="Exchange announcements and configured news feeds, classified by event type, sentiment and impact." />
      <Disclaimer>
        AI summaries separate FACT (what was reported), INTERPRETATION (what it may mean) and SPECULATION (unconfirmed). Unverified sources are labelled — check the original before acting.
      </Disclaimer>
      <Card>
        <CardBody className="flex flex-wrap items-end gap-3 border-b border-border">
          <Field label="Stock" className="w-60">
            {(id) => <StockSearch id={id} onSelect={(h) => setSymbol(h.symbol)} placeholder={symbol || "All stocks"} />}
          </Field>
          {symbol ? (
            <Badge tone="accent">
              {symbol}
              <button type="button" aria-label="Clear stock filter" onClick={() => setSymbol("")}>
                <X className="size-3" />
              </button>
            </Badge>
          ) : null}
          <Field label="Event type" className="w-48">
            {(id) => (
              <Select id={id} value={eventType} onChange={(e) => setEventType(e.target.value)}>
                <option value="">All events</option>
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {symbol || eventType ? (
            <Button size="sm" variant="ghost" onClick={() => { setSymbol(""); setEventType(""); }}>
              Reset
            </Button>
          ) : null}
        </CardBody>
        <QueryState query={q} skeleton={<SkeletonRows rows={8} className="p-4" />}>
          {(items) => (
            <>
              <NewsList items={items} />
              {items.length >= limit && limit < 200 ? (
                <div className="border-t border-border p-3 text-center">
                  <Button size="sm" variant="outline" loading={q.isFetching} onClick={() => setLimit((l) => Math.min(l + 50, 200))}>
                    Load more
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </QueryState>
      </Card>
    </div>
  );
}
