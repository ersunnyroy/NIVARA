import { Clock } from "lucide-react";
import { dateTimeIST, titleCase } from "@/lib/format";
import type { PriceKind } from "@/lib/types";
import { Badge } from "./Badge";
import { cn } from "./cn";

export function PriceKindBadge({ kind, className }: { kind?: PriceKind | null; className?: string }) {
  if (!kind) return <Badge tone="outline" size="xs" className={className} title="Price type not reported by the API">price type n/a</Badge>;
  if (kind === "eod_close")
    return (
      <Badge tone="neutral" size="xs" className={className} title="End-of-day closing price (not live)">
        EOD close
      </Badge>
    );
  if (kind === "live_quote")
    return (
      <Badge tone="up" size="xs" className={className} title="Live quote from a real-time provider">
        Live
      </Badge>
    );
  if (kind === "delayed_quote")
    return (
      <Badge tone="warn" size="xs" className={className} title="Delayed quote">
        Delayed
      </Badge>
    );
  return (
    <Badge tone="outline" size="xs" className={className}>
      {titleCase(kind)}
    </Badge>
  );
}

/** "Data as of … IST · source" — attach to every block that shows prices or numbers. */
export function DataStamp({
  asOf,
  source,
  kind,
  className,
  label = "Data as of",
}: {
  asOf?: string | null;
  source?: string | string[] | null;
  kind?: PriceKind | null;
  className?: string;
  label?: string;
}) {
  const src = Array.isArray(source) ? source.filter(Boolean).join(", ") : source;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted", className)}>
      <span className="inline-flex items-center gap-1">
        <Clock className="size-3" aria-hidden />
        {label}{" "}
        <span className={cn("num font-medium", asOf ? "text-fg/80" : "text-warn")}>{asOf ? dateTimeIST(asOf) : "unknown"}</span>
      </span>
      {src ? (
        <span>
          · Source: <span className="font-medium text-fg/80">{src}</span>
        </span>
      ) : null}
      {kind !== undefined ? <PriceKindBadge kind={kind} /> : null}
    </div>
  );
}
