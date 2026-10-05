"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ApiError } from "@/lib/api";
import { dateIST } from "@/lib/format";
import type { OpportunitiesResponse } from "@/lib/types";
import { DataStamp, DataStatusBanner, DataUnavailable, ErrorState, SkeletonRows } from "@/components/ui";
import { OpportunitiesTable } from "./OpportunitiesTable";

/** Handles status (data_unavailable / data_stale), empty and error states around the table. */
export function OpportunitiesBlock({
  query,
  expandable,
  limit,
}: {
  query: UseQueryResult<OpportunitiesResponse, ApiError>;
  expandable?: boolean;
  limit?: number;
}) {
  if (query.isPending) return <SkeletonRows rows={6} className="p-4" />;
  if (query.isError)
    return (
      <div className="p-4">
        <ErrorState
          error={query.error}
          onRetry={() => query.refetch()}
          unavailableHint="An admin can run the EOD ingestion and the scan from Settings → Jobs."
        />
      </div>
    );
  const d = query.data;
  const run = d.run;
  const status = run?.status ?? d.status;
  const items = d.items ?? [];
  const stale = status === "data_stale";

  if (status === "data_unavailable" || (!run && !items.length)) {
    return (
      <div className="p-4">
        <DataUnavailable
          message={d.message ?? run?.notes?.join(" ") ?? "No opportunity scan has produced results yet."}
          hint="Opportunities are generated after the EOD data is ingested. An admin can run the EOD ingestion and the scan from Settings → Jobs."
        />
      </div>
    );
  }

  return (
    <div>
      {status && status !== "ok" ? (
        <div className="px-4 pt-4">
          <DataStatusBanner status={status} message={d.message ?? undefined} notes={run?.notes} />
        </div>
      ) : null}
      {items.length ? (
        <OpportunitiesTable items={items} expandable={expandable} disabled={stale} limit={limit} />
      ) : (
        <p className="px-4 py-6 text-center text-sm text-muted">
          The scan ran but no stock passed every filter{run?.session_date ? ` for ${dateIST(run.session_date)}` : ""}. That is a valid outcome — no trade is also a decision.
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2">
        <DataStamp asOf={run?.data_as_of} source="NSE EOD bhavcopy · NIVARA scanner" />
        <span className="text-[11px] text-muted">
          For session {run?.session_date ? dateIST(run.session_date) : "n/a"} · generated {run?.generated_at ? dateIST(run.generated_at) : "n/a"}
          {run?.model_version ? ` · ${run.model_version}` : ""}
        </span>
      </div>
    </div>
  );
}
