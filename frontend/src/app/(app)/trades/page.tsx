"use client";

import Link from "next/link";
import { useState } from "react";
import { NotebookPen, Pencil, Plus } from "lucide-react";
import { useTrades } from "@/lib/hooks";
import { dateIST, int, titleCase, toNum } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Dialog,
  EmptyState,
  ErrorState,
  Money,
  NAValue,
  Pnl,
  Segmented,
  SkeletonRows,
  TableWrap,
  Td,
  Th,
  THead,
  Tr,
  type BadgeTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/PageHeader";
import { EstimatedTag, RegimeBadge, ScorePill } from "@/components/domain/badges";
import { EDITABLE_KINDS, TradeForm, type TradeX } from "./_components/TradeForm";

type KindFilter = "all" | "live" | "paper" | "system" | "user";

const FILTERS: { key: KindFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "live", label: "Live" },
  { key: "paper", label: "Paper" },
  { key: "system", label: "System" },
  { key: "user", label: "User" },
];

const KIND_TONE: Record<string, BadgeTone> = { live: "up", paper: "violet", system: "info", user: "neutral" };

function KindBadge({ kind }: { kind?: string | null }) {
  if (!kind) return <Badge tone="outline" size="xs">n/a</Badge>;
  return (
    <Badge tone={KIND_TONE[kind] ?? "outline"} size="xs">
      {kind}
    </Badge>
  );
}

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <Badge tone="outline" size="xs">n/a</Badge>;
  return (
    <Badge tone={status === "open" ? "info" : status === "closed" ? "neutral" : "outline"} size="xs">
      {titleCase(status)}
    </Badge>
  );
}

const EMPTY_HINT: Record<KindFilter, string> = {
  all: "Add a trade to start your journal. Record why you entered and exited — the journal is how you learn what works.",
  live: "Log trades you took with real money (kind “live”).",
  paper: "Paper trades appear here when paper orders fill, or log them manually with kind “paper”.",
  system: "System trades are created automatically when “follow the model” is enabled on the Paper trading page.",
  user: "Trades you tag with kind “user” appear here.",
};

export default function TradesPage() {
  const [kind, setKind] = useState<KindFilter>("all");
  const [editing, setEditing] = useState<TradeX | "new" | null>(null);
  const q = useTrades(kind === "all" ? undefined : kind);
  const trades = (q.data ?? []) as TradeX[];
  const close = () => setEditing(null);
  const editingTrade = editing && editing !== "new" ? editing : undefined;

  return (
    <div>
      <PageHeader
        title="Trade journal"
        description="Every round trip with entry/exit reasons, regime and score at entry — gross and net P&L side by side."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            Add trade
          </Button>
        }
      />

      <Card>
        <CardHeader
          title="Trades"
          icon={<NotebookPen className="size-4" />}
          subtitle="Net P&L = gross − charges − estimated tax. Tax is an estimate."
          actions={<Segmented label="Filter by trade kind" value={kind} onChange={setKind} options={FILTERS} />}
        />
        {q.isPending ? (
          <div className="p-4">
            <SkeletonRows rows={6} />
          </div>
        ) : q.isError ? (
          <div className="p-4">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </div>
        ) : trades.length === 0 ? (
          <EmptyState
            title={kind === "all" ? "No trades yet" : `No ${kind} trades`}
            action={
              kind !== "system" ? (
                <Button size="sm" variant="outline" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => setEditing("new")}>
                  Add trade
                </Button>
              ) : undefined
            }
          >
            {EMPTY_HINT[kind]}
          </EmptyState>
        ) : (
          <TableWrap label="Trade journal">
            <THead>
              <tr>
                <Th>Stock</Th>
                <Th>Kind</Th>
                <Th>Status</Th>
                <Th>Entry date</Th>
                <Th align="right">Entry</Th>
                <Th align="right">Qty</Th>
                <Th align="right">Stop</Th>
                <Th align="right">Target</Th>
                <Th>Exit date</Th>
                <Th align="right">Exit</Th>
                <Th align="right">Gross P&amp;L</Th>
                <Th align="right">Charges</Th>
                <Th align="right">
                  <span className="inline-flex items-center gap-1">
                    Tax <EstimatedTag />
                  </span>
                </Th>
                <Th align="right">Net P&amp;L</Th>
                <Th>Regime</Th>
                <Th align="center">Score</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </THead>
            <tbody>
              {trades.map((t) => {
                const sym = t.symbol ?? t.stock ?? null;
                const editable = !t.kind || (EDITABLE_KINDS as readonly string[]).includes(t.kind);
                return (
                  <Tr key={t.id}>
                    <Td className="max-w-48">
                      {sym ? (
                        <Link href={`/stocks/${encodeURIComponent(sym)}`} className="font-semibold hover:text-accent hover:underline">
                          {sym}
                        </Link>
                      ) : (
                        <NAValue />
                      )}
                      {t.name ? <span className="block truncate text-xs text-muted">{t.name}</span> : null}
                    </Td>
                    <Td>
                      <KindBadge kind={t.kind} />
                    </Td>
                    <Td>
                      <StatusBadge status={t.status} />
                    </Td>
                    <Td className="num whitespace-nowrap">{dateIST(t.entry_date ?? null)}</Td>
                    <Td align="right">
                      <Money value={t.entry_price ?? null} />
                    </Td>
                    <Td align="right">{toNum(t.quantity) === null ? <NAValue /> : int(t.quantity)}</Td>
                    <Td align="right">
                      <Money value={t.stop ?? null} />
                    </Td>
                    <Td align="right">
                      <Money value={t.target ?? null} />
                    </Td>
                    <Td className="num whitespace-nowrap">{t.exit_date ? dateIST(t.exit_date) : <span className="text-muted">open</span>}</Td>
                    <Td align="right">
                      <Money value={t.exit_price ?? null} />
                    </Td>
                    <Td align="right">
                      <Pnl value={t.gross_pnl ?? null} />
                    </Td>
                    <Td align="right">
                      <Money value={t.charges ?? null} />
                    </Td>
                    <Td align="right">
                      <Money value={t.tax_estimate ?? null} />
                    </Td>
                    <Td align="right" className="font-semibold">
                      <Pnl value={t.net_pnl ?? null} />
                    </Td>
                    <Td>{t.market_regime ? <RegimeBadge regime={t.market_regime} /> : <NAValue />}</Td>
                    <Td align="center">
                      <ScorePill value={t.score_at_entry ?? null} />
                    </Td>
                    <Td>
                      {editable ? (
                        <Button
                          size="xs"
                          variant="ghost"
                          icon={<Pencil className="size-3" aria-hidden />}
                          onClick={() => setEditing(t)}
                          aria-label={`Edit trade ${sym ?? t.id}`}
                        >
                          Edit
                        </Button>
                      ) : (
                        <span className="text-[11px] text-subtle" title="System trades are generated by the model and cannot be edited">
                          model
                        </span>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </TableWrap>
        )}
      </Card>

      <Dialog
        open={editing !== null}
        onClose={close}
        title={editingTrade ? `Edit trade — ${editingTrade.symbol ?? editingTrade.stock ?? `#${editingTrade.id}`}` : "Add trade"}
        description="Leave exit date and price empty while the trade is open."
      >
        {editing !== null ? <TradeForm key={editingTrade ? editingTrade.id : "new"} trade={editingTrade} onDone={close} onCancel={close} /> : null}
      </Dialog>
    </div>
  );
}
