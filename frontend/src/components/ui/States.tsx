"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, CloudOff, Lock, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api";
import type { DataStatus } from "@/lib/types";
import { Button } from "./Button";
import { cn } from "./cn";
import { SkeletonRows } from "./Skeleton";

/** Prominent "DATA UNAVAILABLE" state. */
export function DataUnavailable({ message, hint, className }: { message?: React.ReactNode; hint?: React.ReactNode; className?: string }) {
  return (
    <div role="alert" className={cn("rounded-lg border-2 border-dashed border-down/40 bg-down-soft/60 px-4 py-5 text-center", className)}>
      <div className="flex items-center justify-center gap-2 text-sm font-bold uppercase tracking-widest text-down">
        <CloudOff className="size-4" aria-hidden /> Data unavailable
      </div>
      {message ? <p className="mx-auto mt-1.5 max-w-xl text-xs text-fg/80">{message}</p> : null}
      {hint ? <p className="mx-auto mt-1 max-w-xl text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

/** "DATA STALE — recommendation disabled" banner. */
export function DataStale({ message, className }: { message?: React.ReactNode; className?: string }) {
  return (
    <div role="alert" className={cn("rounded-lg border border-warn/40 bg-warn-soft px-4 py-3", className)}>
      <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-warn">
        <AlertTriangle className="size-4" aria-hidden /> Data stale — recommendation disabled
      </div>
      {message ? <p className="mt-1 text-xs text-fg/80">{message}</p> : null}
    </div>
  );
}

/** Banner for any payload-level `status`. Renders nothing for ok/undefined. */
export function DataStatusBanner({
  status,
  message,
  notes,
  hint,
  className,
}: {
  status?: DataStatus | null;
  message?: React.ReactNode;
  notes?: string[] | null;
  hint?: React.ReactNode;
  className?: string;
}) {
  const extra = notes?.length ? (
    <ul className="mt-1 list-inside list-disc text-left">
      {notes.map((n, i) => (
        <li key={i}>{n}</li>
      ))}
    </ul>
  ) : null;
  if (status === "data_unavailable")
    return (
      <DataUnavailable
        className={className}
        message={
          <>
            {message}
            {extra}
          </>
        }
        hint={hint}
      />
    );
  if (status === "data_stale")
    return (
      <DataStale
        className={className}
        message={
          <>
            {message}
            {extra}
          </>
        }
      />
    );
  if (status === "partial")
    return (
      <div className={cn("rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-warn", className)} role="status">
        <span className="font-semibold uppercase tracking-wide">Partial data</span>
        {message ? <> — {message}</> : null}
        {extra}
      </div>
    );
  if (status === "error")
    return <ErrorState className={className} title="Run reported an error" message={typeof message === "string" ? message : undefined} />;
  return null;
}

export function ErrorState({
  error,
  title,
  message,
  onRetry,
  className,
  unavailableHint,
}: {
  error?: unknown;
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
  unavailableHint?: React.ReactNode;
}) {
  const api = error instanceof ApiError ? error : null;
  if (api?.isUnavailable) return <DataUnavailable className={className} message={api.message} hint={unavailableHint} />;
  const msg = message ?? (error instanceof Error ? error.message : error ? String(error) : "Something went wrong.");
  const forbidden = api?.isForbidden;
  return (
    <div role="alert" className={cn("flex flex-col items-start gap-2 rounded-lg border border-down/30 bg-down-soft/50 px-4 py-3 sm:flex-row sm:items-center", className)}>
      {forbidden ? <Lock className="size-4 shrink-0 text-down" aria-hidden /> : <AlertOctagon className="size-4 shrink-0 text-down" aria-hidden />}
      <div className="min-w-0 flex-1 text-xs">
        <p className="font-semibold text-down">
          {title ?? (forbidden ? "Not permitted" : api?.isNotFound ? "Not found" : api?.isNetwork ? "API unreachable" : "Could not load data")}
          {api && api.status > 0 ? <span className="ml-1 font-normal text-muted">(HTTP {api.status})</span> : null}
        </p>
        <p className="mt-0.5 break-words text-fg/80">{msg}</p>
      </div>
      {onRetry ? (
        <Button size="xs" variant="outline" onClick={onRetry} icon={<RefreshCw className="size-3" aria-hidden />}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

/** Generic loading / error wrapper for a react-query result. */
export function QueryState<D>({
  query,
  children,
  skeleton,
  className,
  unavailableHint,
}: {
  query: UseQueryResult<D, ApiError>;
  children: (data: D) => React.ReactNode;
  skeleton?: React.ReactNode;
  className?: string;
  unavailableHint?: React.ReactNode;
}) {
  if (query.isPending) return <>{skeleton ?? <SkeletonRows rows={4} className={className} />}</>;
  if (query.isError)
    return <ErrorState error={query.error} onRetry={() => query.refetch()} className={className} unavailableHint={unavailableHint} />;
  return <>{children(query.data)}</>;
}
