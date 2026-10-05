"use client";

import Link from "next/link";
import { useState } from "react";
import { ListPlus, Plus, Star, Trash2 } from "lucide-react";
import { useAddWatchItem, useCreateWatchlist, useRemoveWatchItem, useWatchlist, useWatchlists } from "@/lib/hooks";
import { dateIST, dateTimeIST, titleCase } from "@/lib/format";
import type { Watchlist, WatchlistDetail, WatchlistItem } from "@/lib/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScorePill } from "@/components/domain/badges";
import { StockSearch } from "@/components/domain/StockSearch";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  cn,
  DataStamp,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Money,
  NAValue,
  Pct,
  PriceKindBadge,
  Select,
  SkeletonCard,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ui";

/** Backend returns `count` (not `item_count`) and extra per-item fields. */
type WatchlistX = Watchlist & { count?: number | null };
type ItemX = WatchlistItem & { sector?: string | null; score_date?: string | null; added_at?: string | null };

const KINDS: { value: string; label: string }[] = [
  { value: "custom", label: "Custom" },
  { value: "momentum", label: "Momentum" },
  { value: "breakouts", label: "Breakouts" },
  { value: "long_term", label: "Long term" },
  { value: "fno", label: "F&O" },
  { value: "earnings", label: "Earnings" },
];

function latestAsOf(items: ItemX[]): string | null {
  let best: string | null = null;
  let bestT = -Infinity;
  for (const it of items) {
    const a = it.price?.as_of;
    if (!a) continue;
    const t = Date.parse(a);
    if (Number.isFinite(t) && t > bestT) {
      bestT = t;
      best = a;
    }
  }
  return best;
}

function CreateListForm() {
  const create = useCreateWatchlist();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("custom");
  const [done, setDone] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setDone(null);
    const n = name.trim();
    if (!n) return;
    create.mutate(
      { name: n, kind },
      {
        onSuccess: () => {
          setDone(n);
          setName("");
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <Field label="New list name" required>
        {(id) => <Input id={id} required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Pharma ideas" />}
      </Field>
      <Field label="Kind">
        {(id) => (
          <Select id={id} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      {create.error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {create.error.message}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="text-xs text-up">
          Created “{done}”.
        </p>
      ) : null}
      <Button type="submit" size="sm" variant="primary" loading={create.isPending} icon={<ListPlus className="size-4" aria-hidden />} className="w-full">
        Create list
      </Button>
    </form>
  );
}

function ListPicker({ lists, value, onChange }: { lists: WatchlistX[]; value: number | null; onChange: (id: number) => void }) {
  return (
    <nav aria-label="Watchlists">
      <ul className="scroll-thin flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
        {lists.map((w) => {
          const sel = w.id === value;
          const count = w.count ?? w.item_count;
          return (
            <li key={w.id} className="shrink-0">
              <button
                type="button"
                aria-pressed={sel}
                onClick={() => onChange(w.id)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  sel ? "bg-accent-soft font-semibold text-accent" : "text-fg hover:bg-surface-2",
                )}
              >
                <span className="truncate">{w.name}</span>
                <span className="num text-xs text-muted">{count == null ? "" : count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function RemoveButton({ listId, symbol }: { listId: number; symbol: string }) {
  const rm = useRemoveWatchItem();
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        size="xs"
        variant="ghost"
        loading={rm.isPending}
        onClick={() => rm.mutate({ id: listId, symbol })}
        icon={<Trash2 className="size-3.5" aria-hidden />}
        aria-label={`Remove ${symbol} from watchlist`}
      >
        Remove
      </Button>
      {rm.error ? (
        <span role="alert" className="text-[11px] text-down">
          {rm.error.message}
        </span>
      ) : null}
    </div>
  );
}

function ItemsTable({ list }: { list: WatchlistDetail }) {
  const items = (list.items ?? []) as ItemX[];
  if (!items.length) {
    return (
      <EmptyState compact icon={<Star className="size-6" />} title="This list is empty">
        Use the search box above to add NSE stocks. Prices, scores and entry-zone status appear once EOD data and a scan exist.
      </EmptyState>
    );
  }
  const asOf = latestAsOf(items);
  return (
    <>
      <TableWrap label={`${list.name} items`}>
        <THead>
          <tr>
            <Th>Symbol</Th>
            <Th>Name</Th>
            <Th align="right">Price</Th>
            <Th align="right">Change</Th>
            <Th align="center">Score</Th>
            <Th>Setup</Th>
            <Th>Entry zone</Th>
            <Th>Notes</Th>
            <Th align="right">
              <span className="sr-only">Actions</span>
            </Th>
          </tr>
        </THead>
        <tbody>
          {items.map((it) => {
            const change = it.change_pct ?? it.price?.change_pct ?? null;
            return (
              <Tr key={it.symbol}>
                <Td className="font-semibold">
                  <Link href={`/stocks/${encodeURIComponent(it.symbol)}`} className="text-accent hover:underline">
                    {it.symbol}
                  </Link>
                </Td>
                <Td className="max-w-56">
                  <span className="block truncate">{it.name ?? <NAValue />}</span>
                  {it.sector ? <span className="block truncate text-[11px] text-muted">{it.sector}</span> : null}
                </Td>
                <Td align="right">
                  <div className="flex flex-col items-end gap-0.5">
                    <Money value={it.price?.price} />
                    <span className="flex items-center gap-1">
                      <PriceKindBadge kind={it.price?.kind} />
                    </span>
                    <span className="text-[10px] font-normal text-muted" title={it.price?.source ?? undefined}>
                      {it.price?.as_of ? dateTimeIST(it.price.as_of) : "as of n/a"}
                    </span>
                  </div>
                </Td>
                <Td align="right">
                  <Pct value={change} />
                </Td>
                <Td align="center">
                  <ScorePill value={it.score} />
                  {it.score_date ? <span className="mt-0.5 block text-[10px] text-muted">{dateIST(it.score_date)}</span> : null}
                </Td>
                <Td>{it.setup ? titleCase(it.setup) : <NAValue />}</Td>
                <Td>
                  {it.in_entry_zone === true ? (
                    <Badge tone="up">In entry zone</Badge>
                  ) : it.in_entry_zone === false ? (
                    <span className="text-muted" aria-label="Not in entry zone">
                      —
                    </span>
                  ) : (
                    <NAValue />
                  )}
                </Td>
                <Td className="max-w-64 whitespace-normal text-xs text-fg/80">{it.notes ? it.notes : <span className="text-muted">—</span>}</Td>
                <Td align="right">
                  <RemoveButton listId={list.id} symbol={it.symbol} />
                </Td>
              </Tr>
            );
          })}
        </tbody>
      </TableWrap>
      <div className="px-4 py-2">
        <DataStamp asOf={asOf} label="Latest price as of" />
        <p className="mt-1 text-[11px] text-muted">
          Each price shows its own type and timestamp. “In entry zone” compares the current price to the latest recommendation&apos;s entry range — it is not a
          buy signal.
        </p>
      </div>
    </>
  );
}

function ListDetail({ id }: { id: number }) {
  const q = useWatchlist(id);
  const add = useAddWatchItem();
  const [added, setAdded] = useState<string | null>(null);

  return (
    <Card>
      {q.isPending ? (
        <CardBody>
          <SkeletonRows rows={6} />
        </CardBody>
      ) : q.isError ? (
        <CardBody>
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        </CardBody>
      ) : (
        <>
          <CardHeader
            icon={<Star className="size-4" />}
            title={q.data.name}
            subtitle={
              <>
                {q.data.kind ? `${titleCase(q.data.kind)} · ` : ""}
                {(q.data.items ?? []).length} item{(q.data.items ?? []).length === 1 ? "" : "s"}
              </>
            }
          />
          <div className="border-b border-border px-4 py-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <label className="text-xs font-medium text-muted sm:w-24" htmlFor="watch-add">
                <span className="inline-flex items-center gap-1">
                  <Plus className="size-3.5" aria-hidden /> Add stock
                </span>
              </label>
              <StockSearch
                id="watch-add"
                className="flex-1"
                ariaLabel={`Add a stock to ${q.data.name}`}
                placeholder="Search NSE symbol or company…"
                onSelect={(h) => {
                  setAdded(null);
                  add.mutate({ id, symbol: h.symbol }, { onSuccess: () => setAdded(h.symbol) });
                }}
              />
            </div>
            {add.isPending ? <p className="mt-1 text-xs text-muted">Adding…</p> : null}
            {add.error ? (
              <p role="alert" className="mt-1 text-xs text-down">
                {add.error.message}
              </p>
            ) : null}
            {added && !add.isPending && !add.error ? (
              <p role="status" className="mt-1 text-xs text-up">
                Added {added}.
              </p>
            ) : null}
          </div>
          <ItemsTable list={q.data} />
        </>
      )}
    </Card>
  );
}

export default function WatchlistPage() {
  const q = useWatchlists();
  const [selected, setSelected] = useState<number | null>(null);
  const lists = (q.data ?? []) as WatchlistX[];
  const active = selected !== null && lists.some((l) => l.id === selected) ? selected : (lists[0]?.id ?? null);

  return (
    <div className="space-y-4">
      <PageHeader title="Watchlists" description="Track stocks with their latest EOD price, opportunity score, setup and entry-zone status." />
      {q.isPending ? (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <SkeletonCard lines={6} />
          <SkeletonCard lines={6} />
        </div>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <div className="space-y-4">
            <Card>
              <CardHeader title="Your lists" />
              <CardBody className="p-2">
                {lists.length ? (
                  <ListPicker lists={lists} value={active} onChange={setSelected} />
                ) : (
                  <EmptyState compact title="No watchlists yet">
                    Default lists (My Watchlist, Momentum, Breakouts, Long term, F&amp;O, Earnings) are created automatically by the server. Create one below if
                    none appear.
                  </EmptyState>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Create a list" />
              <CardBody>
                <CreateListForm />
              </CardBody>
            </Card>
          </div>
          <div className="min-w-0">
            {active !== null ? (
              <ListDetail key={active} id={active} />
            ) : (
              <Card>
                <CardBody>
                  <EmptyState title="Select or create a watchlist">Pick a list on the left, or create a new one.</EmptyState>
                </CardBody>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
