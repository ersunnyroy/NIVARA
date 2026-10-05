import { Lock } from "lucide-react";
import { titleCase } from "@/lib/format";
import { cn, NAValue, TableWrap, Td, Th, THead, Tr } from "@/components/ui";

/* ------------------------------------------------------------ status dot */

const STATUS: Record<string, { dot: string; text: string; label: string }> = {
  GREEN: { dot: "bg-up", text: "text-up", label: "Green" },
  YELLOW: { dot: "bg-warn", text: "text-warn", label: "Yellow" },
  RED: { dot: "bg-down", text: "text-down", label: "Red" },
  DISABLED: { dot: "bg-subtle", text: "text-muted", label: "Disabled" },
  OK: { dot: "bg-up", text: "text-up", label: "OK" },
  FAILED: { dot: "bg-down", text: "text-down", label: "Failed" },
  ERROR: { dot: "bg-down", text: "text-down", label: "Error" },
  PARTIAL: { dot: "bg-warn", text: "text-warn", label: "Partial" },
  RUNNING: { dot: "bg-info", text: "text-info", label: "Running" },
  SKIPPED: { dot: "bg-subtle", text: "text-muted", label: "Skipped" },
};

/** Coloured dot + text label — status is never conveyed by colour alone. */
export function StatusDot({ status, className }: { status?: string | null; className?: string }) {
  if (!status) return <NAValue className={className} />;
  const s = STATUS[status.toUpperCase()] ?? { dot: "bg-subtle", text: "text-muted", label: titleCase(status) };
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold", s.text, className)}>
      <span className={cn("size-2.5 shrink-0 rounded-full", s.dot)} aria-hidden />
      {s.label}
    </span>
  );
}

/* ------------------------------------------------------------ admin note */

export function AdminOnly({ what }: { what?: string }) {
  return (
    <div role="note" className="flex items-start gap-2 rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-muted">
      <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold text-fg">Admin only</p>
        <p className="text-xs">{what ?? "This section"} is available to administrators. Ask your admin if you need changes here.</p>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- value fmt */

export function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

export function Cell({ v }: { v: unknown }) {
  if (v === null || v === undefined || v === "") return <NAValue />;
  if (typeof v === "boolean") return <span>{v ? "Yes" : "No"}</span>;
  if (typeof v === "number") return <span className="num">{v.toLocaleString("en-IN")}</span>;
  if (typeof v === "string") return <span className="break-words">{v}</span>;
  if (Array.isArray(v) && v.every((x) => typeof x !== "object" || x === null)) return <span>{v.map(String).join(", ") || "—"}</span>;
  const s = JSON.stringify(v);
  return (
    <code className="block max-w-xs truncate text-[11px] text-fg/80" title={s}>
      {s}
    </code>
  );
}

/** Key/value list for a flat-ish object. */
export function KV({ data, className }: { data?: Record<string, unknown> | null; className?: string }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <p className="text-xs text-muted">No details reported.</p>;
  return (
    <dl className={cn("grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[auto_1fr]", className)}>
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-xs font-medium text-muted sm:py-0.5">{titleCase(k)}</dt>
          <dd className="min-w-0 sm:py-0.5">{k.toLowerCase() === "status" && typeof v === "string" ? <StatusDot status={v} /> : <Cell v={v} />}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Table for an array of objects (union of keys as columns). */
export function ObjectTable({ rows, label }: { rows: Record<string, unknown>[]; label: string }) {
  const cols: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  return (
    <TableWrap label={label}>
      <THead>
        <tr>
          {cols.map((c) => (
            <Th key={c}>{titleCase(c)}</Th>
          ))}
        </tr>
      </THead>
      <tbody>
        {rows.map((r, i) => (
          <Tr key={i}>
            {cols.map((c) => (
              <Td key={c} className="max-w-72 text-xs">
                <Cell v={r[c]} />
              </Td>
            ))}
          </Tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

function isObjArray(v: unknown): v is Record<string, unknown>[] {
  return Array.isArray(v) && v.length > 0 && v.every(isPlainObject);
}

/** Readable rendering of an arbitrary JSON payload: tables for arrays of objects, else pretty JSON. */
export function JsonView({ data, label, omit = [] }: { data: unknown; label: string; omit?: string[] }) {
  if (isObjArray(data)) return <ObjectTable rows={data} label={label} />;
  if (Array.isArray(data) && data.length === 0) return <p className="px-4 py-3 text-xs text-muted">No entries.</p>;
  if (isPlainObject(data)) {
    const entries = Object.entries(data).filter(([k]) => !omit.includes(k));
    if (entries.some(([, v]) => isObjArray(v) || typeof v === "string")) {
      return (
        <div className="space-y-4">
          {entries.map(([k, v]) =>
            isObjArray(v) ? (
              <section key={k} aria-label={`${label}: ${titleCase(k)}`}>
                <h3 className="px-4 pb-1 text-xs font-semibold uppercase tracking-wide text-muted">{titleCase(k)}</h3>
                <ObjectTable rows={v} label={`${label}: ${titleCase(k)}`} />
              </section>
            ) : typeof v === "string" ? (
              <p key={k} className="px-4 text-xs text-muted">
                <span className="font-semibold text-fg">{titleCase(k)}:</span> {v}
              </p>
            ) : (
              <section key={k} className="px-4">
                <h3 className="pb-1 text-xs font-semibold uppercase tracking-wide text-muted">{titleCase(k)}</h3>
                <pre className="scroll-thin overflow-x-auto rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed">{JSON.stringify(v, null, 2)}</pre>
              </section>
            ),
          )}
        </div>
      );
    }
  }
  return (
    <pre className="scroll-thin mx-4 overflow-x-auto rounded-lg bg-surface-2 p-3 text-[11px] leading-relaxed" aria-label={label}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

/** Formats an epoch-ms number in IST without constructing Dates during render. */
const fetchedFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
export function fetchedAt(ms: number): string {
  return ms > 0 ? `${fetchedFmt.format(ms)} IST` : "n/a";
}
