import { CircleCheck, CircleX, Clock, Loader2 } from "lucide-react";
import { titleCase } from "@/lib/format";
import { Badge } from "@/components/ui";

export function isActive(status?: string | null): boolean {
  return status === "queued" || status === "running";
}

export function isDone(status?: string | null): boolean {
  return status === "done" || status === "completed";
}

/** queued / running / done / failed — icon + text, never colour alone. */
export function BacktestStatusBadge({ status }: { status?: string | null }) {
  if (!status) return <Badge tone="outline">status n/a</Badge>;
  if (status === "queued")
    return (
      <Badge tone="neutral">
        <Clock className="size-3" aria-hidden /> Queued
      </Badge>
    );
  if (status === "running")
    return (
      <Badge tone="info">
        <Loader2 className="size-3 animate-spin" aria-hidden /> Running
      </Badge>
    );
  if (isDone(status))
    return (
      <Badge tone="up">
        <CircleCheck className="size-3" aria-hidden /> Done
      </Badge>
    );
  if (status === "failed")
    return (
      <Badge tone="down">
        <CircleX className="size-3" aria-hidden /> Failed
      </Badge>
    );
  return <Badge tone="outline">{titleCase(status)}</Badge>;
}
