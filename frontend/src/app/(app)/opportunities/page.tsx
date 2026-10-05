"use client";

import { useState } from "react";
import { Filter, Play, Target } from "lucide-react";
import { useMe, useOpportunities, useRunScan } from "@/lib/hooks";
import { dateTimeIST, int, num, titleCase } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import { OpportunitiesBlock } from "@/components/domain/OpportunitiesBlock";
import { HBars } from "@/components/charts/svg";
import { Button, Card, CardBody, CardHeader, Disclaimer, Field, Input, Stat } from "@/components/ui";

export default function OpportunitiesPage() {
  const [date, setDate] = useState("");
  const q = useOpportunities(date || undefined);
  const me = useMe();
  const scan = useRunScan();
  const isAdmin = me.data?.role === "admin";
  const run = q.data?.run;
  const rejections = Object.entries(run?.rejection_counts ?? {}).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  const weights = Object.entries(run?.weights ?? {});

  return (
    <div className="space-y-4">
      <PageHeader
        title="Opportunities"
        description="Top-ranked setups for the next session. Expand a row for WHY BUY, WHY NOT, invalidation and the full score breakdown."
        actions={
          <>
            <Field label="Session date" className="w-44">
              {(id) => <Input id={id} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
            </Field>
            {date ? (
              <Button variant="ghost" size="sm" className="self-end" onClick={() => setDate("")}>
                Latest
              </Button>
            ) : null}
            {isAdmin ? (
              <Button
                className="self-end"
                variant="primary"
                size="sm"
                loading={scan.isPending}
                icon={<Play className="size-3.5" aria-hidden />}
                onClick={() => scan.mutate()}
              >
                Run scan
              </Button>
            ) : null}
          </>
        }
      />
      {scan.isError ? <p role="alert" className="text-xs text-down">Scan failed: {scan.error.message}</p> : null}
      {scan.isSuccess ? <p role="status" className="text-xs text-up">Scan triggered. Results appear here when the run completes.</p> : null}

      <Disclaimer tone="warn">
        These are ranked research ideas, not instructions to trade. Respect the stop, never chase above the no-chase level, and size positions so a stop-out costs ≤ your risk budget.
      </Disclaimer>

      <Card>
        <CardHeader icon={<Target className="size-4" />} title="Ranked opportunities" subtitle="Score = weighted components; missing components are excluded (n/a), never scored as zero" />
        <OpportunitiesBlock query={q} expandable />
      </Card>

      {run ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader title="Run metadata" />
            <CardBody className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Stat size="sm" label="Status" value={titleCase(run.status)} tone={run.status === "ok" ? "up" : "warn"} />
                <Stat size="sm" label="Run id" value={run.id ?? "n/a"} />
                <Stat size="sm" label="Universe" value={int(run.universe_size)} />
                <Stat size="sm" label="Eligible" value={int(run.eligible_count)} />
              </div>
              <dl className="space-y-1 text-xs">
                <div className="flex justify-between gap-2"><dt className="text-muted">Generated</dt><dd>{dateTimeIST(run.generated_at)}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-muted">Data as of</dt><dd>{dateTimeIST(run.data_as_of)}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-muted">Model</dt><dd className="font-mono">{run.model_version ?? "n/a"}</dd></div>
                <div className="flex justify-between gap-2"><dt className="text-muted">Scoring</dt><dd className="font-mono">{run.scoring_version ?? "n/a"}</dd></div>
              </dl>
              {run.notes?.length ? (
                <ul className="list-inside list-disc text-xs text-muted">
                  {run.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              ) : null}
            </CardBody>
          </Card>
          <Card>
            <CardHeader icon={<Filter className="size-4" />} title="Why stocks were rejected" subtitle="Counts per filter in this run" />
            <CardBody>
              {rejections.length ? (
                <HBars data={rejections.map(([k, v]) => ({ label: titleCase(k), value: v }))} format={(v) => int(v)} />
              ) : (
                <p className="text-xs text-muted">No rejection counts reported.</p>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Scoring weights used" subtitle="Snapshot stored with the run" />
            <CardBody>
              {weights.length ? (
                <HBars data={weights.map(([k, v]) => ({ label: titleCase(k), value: v }))} format={(v) => num(v, 0)} max={Math.max(...weights.map(([, v]) => Number(v) || 0), 1)} />
              ) : (
                <p className="text-xs text-muted">Weights not reported.</p>
              )}
            </CardBody>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
