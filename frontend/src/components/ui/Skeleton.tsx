import { cn } from "./cn";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton rounded-md", className)} />;
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-7 w-full" />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function SkeletonCard({ className, lines = 4 }: { className?: string; lines?: number }) {
  return (
    <div className={cn("rounded-xl border border-border bg-surface p-4", className)} role="status" aria-label="Loading">
      <Skeleton className="mb-4 h-4 w-40" />
      <SkeletonRows rows={lines} />
    </div>
  );
}
