"use client";

import { useState } from "react";
import { Play, Workflow } from "lucide-react";
import { useRunJob } from "@/lib/hooks";
import type { JobName } from "@/lib/types";
import { Button, Card, CardBody, CardHeader, Dialog, Field, Input } from "@/components/ui";

type ParamKind = "none" | "date" | "backfill" | "fundamentals";

interface JobSpec {
  job: string;
  label: string;
  description: string;
  params: ParamKind;
  confirm?: string;
}

const CORE: JobSpec[] = [
  { job: "securities", label: "Securities master", description: "Download the NSE equity list (symbols, ISIN, series). Run first.", params: "none" },
  { job: "holidays", label: "Market holidays", description: "Refresh the NSE trading-holiday calendar.", params: "none" },
  { job: "eod", label: "EOD ingestion", description: "Load end-of-day bhavcopy prices and index closes for a session (default: last completed).", params: "date" },
  {
    job: "backfill",
    label: "Historical backfill",
    description: "Download EOD history for many past sessions (needed for indicators). Slow and network-heavy.",
    params: "backfill",
    confirm: "Backfill downloads one bhavcopy per trading day for the whole range. It can take a long time and hits NSE archives repeatedly.",
  },
  { job: "fno", label: "F&O bhavcopy", description: "Load futures & options EOD data for a session.", params: "date" },
  { job: "flows", label: "FII / DII flows", description: "Fetch institutional cash-market flows.", params: "none" },
  { job: "news", label: "News", description: "Pull exchange announcements and configured RSS feeds.", params: "none" },
  { job: "corporate_actions", label: "Corporate actions", description: "Dividends, splits, bonuses (past ~400 days to +30 days).", params: "none" },
  { job: "fundamentals", label: "Fundamentals", description: "Fetch financial results for an index universe.", params: "fundamentals" },
  { job: "regime", label: "Market regime", description: "Recompute the market regime for a session.", params: "date" },
  { job: "scan", label: "Opportunity scan", description: "Score the universe and generate ranked ideas for a session.", params: "date" },
  { job: "outcomes", label: "Recommendation outcomes", description: "Update target / stop hits for past recommendations (track record).", params: "none" },
];

/** Other jobs the backend accepts (not in the shared JobName type yet). */
const EXTRA: JobSpec[] = [
  { job: "seed", label: "Seed reference data", description: "Register default data sources, tax rules and charge schedules. Safe to re-run.", params: "none" },
  { job: "breadth", label: "Market breadth", description: "Recompute advances/declines and DMA breadth for a session.", params: "date" },
  { job: "fno_snapshots", label: "F&O snapshots", description: "Derive PCR, max pain, OI build-up from loaded F&O data.", params: "date" },
  { job: "event_calendar", label: "Event calendar", description: "Upcoming board meetings / results dates.", params: "none" },
  { job: "alerts", label: "Evaluate alerts", description: "Run all users' alert rules now.", params: "none" },
  { job: "paper", label: "Paper orders", description: "Fill pending paper-trading orders against a session's prices.", params: "date" },
];

function JobRow({ spec }: { spec: JobSpec }) {
  const run = useRunJob();
  const [date, setDate] = useState("");
  const [days, setDays] = useState("400");
  const [universe, setUniverse] = useState("nifty50");
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function params(): Record<string, unknown> | null {
    if (spec.params === "date") return date ? { date } : {};
    if (spec.params === "backfill") {
      const n = Number(days);
      if (!Number.isInteger(n) || n < 1 || n > 4000) {
        setErr("Days must be a whole number between 1 and 4000.");
        return null;
      }
      return { days: n };
    }
    if (spec.params === "fundamentals") return universe.trim() ? { universe: universe.trim() } : {};
    return {};
  }

  function go() {
    setErr(null);
    const p = params();
    if (p === null) return;
    run.mutate({ job: spec.job as JobName, params: p });
    setConfirming(false);
  }

  return (
    <li className="flex flex-col gap-3 py-3 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">
          {spec.label} <code className="ml-1 text-[10px] font-normal text-subtle">{spec.job}</code>
        </p>
        <p className="text-xs text-muted">{spec.description}</p>
        {run.isSuccess ? (
          <pre className="scroll-thin mt-2 max-h-40 overflow-auto rounded-lg bg-up-soft/60 p-2 text-[11px] text-fg" aria-label={`${spec.label} response`}>
            {JSON.stringify(run.data, null, 2)}
          </pre>
        ) : null}
        {run.error || err ? (
          <p role="alert" className="mt-2 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
            {err ?? run.error?.message}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        {spec.params === "date" ? (
          <Field label="Session (optional)" className="w-40">
            {(id) => <Input id={id} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
          </Field>
        ) : spec.params === "backfill" ? (
          <Field label="Days of history" className="w-32">
            {(id) => <Input id={id} type="number" min={1} max={4000} step={1} value={days} onChange={(e) => setDays(e.target.value)} />}
          </Field>
        ) : spec.params === "fundamentals" ? (
          <Field label="Universe" className="w-36">
            {(id) => <Input id={id} value={universe} onChange={(e) => setUniverse(e.target.value)} placeholder="nifty50" />}
          </Field>
        ) : null}
        <Button
          size="sm"
          variant={spec.confirm ? "outline" : "secondary"}
          loading={run.isPending}
          icon={<Play className="size-3.5" aria-hidden />}
          onClick={() => (spec.confirm ? setConfirming(true) : go())}
          aria-label={`Run ${spec.label}`}
        >
          Run
        </Button>
      </div>
      {spec.confirm ? (
        <Dialog
          open={confirming}
          onClose={() => setConfirming(false)}
          title={`Run ${spec.label}?`}
          description={spec.confirm}
          footer={
            <>
              <Button variant="outline" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={go} icon={<Play className="size-4" aria-hidden />}>
                Run {spec.label.toLowerCase()}
              </Button>
            </>
          }
        >
          <p className="text-sm">
            Range: last <span className="num font-semibold">{days || "?"}</span> calendar days, ending yesterday (IST).
          </p>
        </Dialog>
      ) : null}
    </li>
  );
}

export function Jobs() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<Workflow className="size-4" />}
          title="Jobs"
          subtitle="Jobs are queued to the worker (or run in the API process if no worker is reachable). Check System health → Recent ingestion runs for results."
        />
        <CardBody className="py-1">
          <p className="mt-2 rounded-lg bg-info-soft px-3 py-2 text-xs text-info">
            First-time setup order: Seed reference data → Securities master → Market holidays → Historical backfill → EOD ingestion → Market regime →
            Opportunity scan.
          </p>
          <ul className="divide-y divide-border">
            {CORE.map((s) => (
              <JobRow key={s.job} spec={s} />
            ))}
          </ul>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Other jobs" subtitle="Maintenance jobs also accepted by the backend." />
        <CardBody className="py-1">
          <ul className="divide-y divide-border">
            {EXTRA.map((s) => (
              <JobRow key={s.job} spec={s} />
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
