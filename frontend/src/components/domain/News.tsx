import { BadgeCheck, ExternalLink, FileQuestion, Lightbulb, MessageCircleWarning, ScrollText } from "lucide-react";
import { dateTimeIST, num, titleCase, toNum } from "@/lib/format";
import type { NewsItem } from "@/lib/types";
import { Badge, EmptyState, cn } from "@/components/ui";

function sentimentTone(n: NewsItem): "up" | "down" | "neutral" {
  const l = (n.sentiment_label ?? "").toLowerCase();
  const s = toNum(n.sentiment);
  if (l.includes("pos") || (s !== null && s > 0.15)) return "up";
  if (l.includes("neg") || (s !== null && s < -0.15)) return "down";
  return "neutral";
}

function Block({ kind, items }: { kind: "fact" | "interpretation" | "speculation"; items?: string[] }) {
  if (!items?.length) return null;
  const cfg = {
    fact: { label: "Fact", icon: ScrollText, cls: "border-info/40 bg-info-soft/60", head: "text-info" },
    interpretation: { label: "Interpretation", icon: Lightbulb, cls: "border-violet/40 bg-violet-soft/60", head: "text-violet" },
    speculation: { label: "Speculation", icon: MessageCircleWarning, cls: "border-warn/40 bg-warn-soft/60 border-dashed", head: "text-warn" },
  }[kind];
  const Icon = cfg.icon;
  return (
    <div className={cn("rounded-md border px-2.5 py-1.5", cfg.cls)}>
      <p className={cn("mb-0.5 flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest", cfg.head)}>
        <Icon className="size-3" aria-hidden /> {cfg.label}
      </p>
      <ul className="list-inside list-disc space-y-0.5 text-xs leading-relaxed text-fg/90">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

export function NewsCard({ item, compact }: { item: NewsItem; compact?: boolean }) {
  const tone = sentimentTone(item);
  const verified = item.is_verified === true || item.source_tier === "primary";
  return (
    <article className="px-4 py-3">
      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
        {item.symbol ? <Badge tone="accent" size="xs">{item.symbol}</Badge> : null}
        {item.event_type ? <Badge tone="neutral" size="xs">{titleCase(item.event_type)}</Badge> : null}
        <span className="font-medium text-fg/80">{item.source ?? "Unknown source"}</span>
        {verified ? (
          <span className="inline-flex items-center gap-0.5 text-up" title={item.verification ?? "Primary exchange filing"}>
            <BadgeCheck className="size-3" aria-hidden /> {item.verification ?? "verified"}
          </span>
        ) : (
          <Badge tone="warn" size="xs" className="normal-case" title={item.verification ?? "Source is not an exchange filing"}>
            <FileQuestion className="size-3" aria-hidden /> {item.source_tier === "reputable" ? "Not independently verified" : "Unverified source"}
          </Badge>
        )}
        <span>· {dateTimeIST(item.published_at)}</span>
      </div>
      <h3 className="text-sm font-medium leading-snug">
        {item.url ? (
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent hover:underline">
            {item.headline}
            <ExternalLink className="ml-1 inline size-3 text-subtle" aria-label="(opens in new tab)" />
          </a>
        ) : (
          item.headline
        )}
      </h3>
      <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
        {item.sentiment_label || item.sentiment != null ? (
          <Badge tone={tone} size="xs">
            {tone === "up" ? "▲" : tone === "down" ? "▼" : "■"} {item.sentiment_label ?? "sentiment"}
            {item.sentiment != null ? ` ${num(item.sentiment, 2)}` : ""}
          </Badge>
        ) : null}
        {item.impact ? <Badge tone="outline" size="xs">Impact: {item.impact}</Badge> : null}
        {item.horizon ? <Badge tone="outline" size="xs">Horizon: {item.horizon}</Badge> : null}
        {item.confidence != null ? <Badge tone="outline" size="xs">Conf. {num((toNum(item.confidence) ?? 0) <= 1 ? (toNum(item.confidence) ?? 0) * 100 : item.confidence, 0)}%</Badge> : null}
      </div>
      {!compact && item.ai ? (
        <div className="mt-2 grid gap-1.5 md:grid-cols-3">
          <Block kind="fact" items={item.ai.facts} />
          <Block kind="interpretation" items={item.ai.interpretation} />
          <Block kind="speculation" items={item.ai.speculation} />
        </div>
      ) : null}
    </article>
  );
}

export function NewsList({ items, compact, limit }: { items: NewsItem[]; compact?: boolean; limit?: number }) {
  if (!items.length)
    return (
      <EmptyState compact title="No news yet">
        News arrives from exchange announcements and configured RSS feeds. An admin can run the news job from Settings → Jobs.
      </EmptyState>
    );
  return (
    <div className="divide-y divide-border">
      {items.slice(0, limit ?? items.length).map((n) => (
        <NewsCard key={n.id} item={n} compact={compact} />
      ))}
    </div>
  );
}
