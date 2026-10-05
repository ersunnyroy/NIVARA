import { num, titleCase, toNum } from "@/lib/format";

/** Render an arbitrary scalar from an API dict (numbers with Indian grouping, booleans as Yes/No). */
export function scalar(v: unknown): string {
  if (v === null || v === undefined || v === "") return "n/a";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return num(v, Math.abs(v) >= 1000 ? 0 : 2);
  if (typeof v === "string") {
    const n = toNum(v);
    if (n !== null && /^-?[\d.,]+$/.test(v.trim())) return num(n, 2);
    return v;
  }
  if (Array.isArray(v)) return v.map(scalar).join(", ");
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("value" in o) return scalar(o.value) + (o.unit ? ` ${String(o.unit)}` : "");
    return Object.entries(o)
      .map(([k, x]) => `${titleCase(k)}: ${scalar(x)}`)
      .join(" · ");
  }
  return String(v);
}

export function KeyValueGrid({ data, className }: { data: Record<string, unknown>; className?: string }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <p className="text-xs text-muted">Nothing reported.</p>;
  return (
    <dl className={className ?? "grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"}>
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0 rounded-md bg-surface-2 px-2.5 py-1.5">
          <dt className="truncate text-[11px] text-muted" title={k}>
            {titleCase(k)}
          </dt>
          <dd className={`num truncate text-sm font-medium ${v === null || v === undefined ? "text-subtle" : ""}`} title={scalar(v)}>
            {scalar(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
