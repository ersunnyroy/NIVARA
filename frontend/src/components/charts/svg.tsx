"use client";

import { useEffect, useRef, useState } from "react";
import { dateIST, inrCompact, num, pct, toNum } from "@/lib/format";
import type { Numeric } from "@/lib/types";
import { cn } from "@/components/ui";

/** Container width via ResizeObserver (state only updated from the observer callback). */
function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cw = Math.floor(entries[0]?.contentRect.width ?? 0);
      setW((prev) => (prev === cw ? prev : cw));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/* ---------------------------------------------------------------- Sparkline */

export function Sparkline({
  values,
  width = 96,
  height = 28,
  className,
  label,
}: {
  values: (number | null | undefined)[];
  width?: number;
  height?: number;
  className?: string;
  label?: string;
}) {
  const pts = values.map((v) => (v == null || !Number.isFinite(v) ? null : v));
  const nums = pts.filter((v): v is number => v !== null);
  if (nums.length < 2) return <span className="text-[11px] text-subtle">n/a</span>;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const step = width / (pts.length - 1);
  let d = "";
  pts.forEach((v, i) => {
    if (v === null) return;
    const x = i * step;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    d += `${d ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const upTrend = nums[nums.length - 1] >= nums[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} role="img" aria-label={label ?? `Trend ${upTrend ? "up" : "down"}`}>
      <path d={d} fill="none" stroke={upTrend ? "var(--up)" : "var(--down)"} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* -------------------------------------------------------------- Equity curve */

export function EquityCurve({
  points,
  height = 220,
  className,
  label = "Equity curve",
  valueFormat = (v: number) => inrCompact(v),
  baseline,
}: {
  points: { date: string; value: Numeric }[];
  height?: number;
  className?: string;
  label?: string;
  valueFormat?: (v: number) => string;
  baseline?: number | null;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const data = points
    .map((p) => ({ date: p.date, value: toNum(p.value) }))
    .filter((p): p is { date: string; value: number } => p.value !== null);

  if (data.length < 2) {
    return (
      <div className={cn("flex items-center justify-center rounded-lg bg-surface-2 text-xs text-muted", className)} style={{ height }}>
        Not enough data points for an equity curve yet.
      </div>
    );
  }

  const padL = 56;
  const padR = 12;
  const padT = 10;
  const padB = 22;
  const w = Math.max(width, 200);
  const vals = data.map((d) => d.value);
  let min = Math.min(...vals, baseline ?? Infinity);
  let max = Math.max(...vals, baseline ?? -Infinity);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const x = (i: number) => padL + (i / (data.length - 1)) * (w - padL - padR);
  const y = (v: number) => padT + (1 - (v - min) / (max - min)) * (height - padT - padB);
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join("");
  const area = `${path}L${x(data.length - 1).toFixed(1)},${height - padB}L${padL},${height - padB}Z`;
  const ticks = [min, (min + max) / 2, max];
  const xTicks = [0, Math.floor((data.length - 1) / 2), data.length - 1];
  const last = data[data.length - 1].value;
  const first = data[0].value;
  const stroke = last >= first ? "var(--up)" : "var(--down)";

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    const i = Math.round(((px - padL) / (w - padL - padR)) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, i)));
  }

  const h = hover !== null ? data[hover] : null;
  return (
    <div ref={ref} className={cn("relative w-full", className)}>
      {width > 0 ? (
        <svg
          width={w}
          height={height}
          role="img"
          aria-label={`${label}: from ${valueFormat(first)} on ${dateIST(data[0].date)} to ${valueFormat(last)} on ${dateIST(data[data.length - 1].date)}`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          className="touch-none select-none"
        >
          {ticks.map((t, i) => (
            <g key={i}>
              <line x1={padL} x2={w - padR} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
              <text x={padL - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--chart-text)" className="num">
                {valueFormat(t)}
              </text>
            </g>
          ))}
          {baseline != null ? (
            <line x1={padL} x2={w - padR} y1={y(baseline)} y2={y(baseline)} stroke="var(--border-strong)" strokeDasharray="3 3" />
          ) : null}
          {xTicks.map((i, k) => (
            <text key={k} x={x(i)} y={height - 6} textAnchor={k === 0 ? "start" : k === 2 ? "end" : "middle"} fontSize={10} fill="var(--chart-text)">
              {dateIST(data[i].date)}
            </text>
          ))}
          <path d={area} fill={stroke} opacity={0.08} />
          <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" />
          {h && hover !== null ? (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={padT} y2={height - padB} stroke="var(--border-strong)" />
              <circle cx={x(hover)} cy={y(h.value)} r={4} fill={stroke} stroke="var(--surface)" strokeWidth={2} />
            </g>
          ) : null}
        </svg>
      ) : (
        <div style={{ height }} />
      )}
      {h && hover !== null ? (
        <div
          className="pointer-events-none absolute top-1 rounded-md border border-border bg-surface px-2 py-1 text-[11px] shadow-lg"
          style={{ left: Math.min(Math.max(x(hover) - 60, 0), w - 130) }}
        >
          <div className="text-muted">{dateIST(h.date)}</div>
          <div className="num font-semibold text-fg">{valueFormat(h.value)}</div>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------- Signed bars (P&L) */

export function SignedBars({
  data,
  height = 160,
  className,
  label = "Monthly P&L",
  format = (v: number) => inrCompact(v, true),
}: {
  data: { label: string; value: Numeric }[];
  height?: number;
  className?: string;
  label?: string;
  format?: (v: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const rows = data.map((d) => ({ label: d.label, value: toNum(d.value) }));
  const nums = rows.map((r) => r.value).filter((v): v is number => v !== null);
  if (!nums.length) {
    return <div className={cn("flex items-center justify-center rounded-lg bg-surface-2 text-xs text-muted", className)} style={{ height }}>No data yet.</div>;
  }
  const max = Math.max(...nums.map(Math.abs), 1);
  const padB = 18;
  const w = Math.max(width, 120);
  const zero = (height - padB) / 2;
  const slot = w / rows.length;
  const bw = Math.max(Math.min(slot - 2, 28), 2);
  const every = Math.ceil(rows.length / Math.max(Math.floor(w / 48), 1));
  return (
    <div ref={ref} className={cn("relative w-full", className)}>
      {width > 0 ? (
        <svg width={w} height={height} role="img" aria-label={label}>
          <line x1={0} x2={w} y1={zero} y2={zero} stroke="var(--border-strong)" />
          {rows.map((r, i) => {
            const cx = i * slot + slot / 2;
            if (r.value === null) return null;
            const hgt = (Math.abs(r.value) / max) * (zero - 4);
            const yTop = r.value >= 0 ? zero - hgt : zero;
            return (
              <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                <rect x={i * slot} y={0} width={slot} height={height - padB} fill="transparent" />
                <rect
                  x={cx - bw / 2}
                  y={yTop}
                  width={bw}
                  height={Math.max(hgt, 1)}
                  rx={Math.min(3, bw / 2)}
                  fill={r.value >= 0 ? "var(--up)" : "var(--down)"}
                  opacity={hover === null || hover === i ? 1 : 0.55}
                />
              </g>
            );
          })}
          {rows.map((r, i) =>
            i % every === 0 ? (
              <text key={`l${i}`} x={i * slot + slot / 2} y={height - 4} textAnchor="middle" fontSize={10} fill="var(--chart-text)">
                {r.label}
              </text>
            ) : null,
          )}
        </svg>
      ) : (
        <div style={{ height }} />
      )}
      {hover !== null && rows[hover] ? (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-border bg-surface px-2 py-1 text-[11px] shadow-lg"
          style={{ left: Math.min(Math.max(hover * slot + slot / 2 - 50, 0), w - 110) }}
        >
          <div className="text-muted">{rows[hover].label}</div>
          <div className={cn("num font-semibold", (rows[hover].value ?? 0) >= 0 ? "text-up" : "text-down")}>
            {rows[hover].value === null ? "n/a" : format(rows[hover].value as number)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------ Horizontal bars */

export function HBars({
  data,
  format = (v: number) => pct(v, 1, false),
  max,
  className,
  tone = "accent",
}: {
  data: { label: string; value: Numeric; note?: string }[];
  format?: (v: number) => string;
  max?: number;
  className?: string;
  tone?: "accent" | "signed";
}) {
  const vals = data.map((d) => toNum(d.value) ?? 0);
  const m = max ?? Math.max(...vals.map(Math.abs), 1);
  return (
    <ul className={cn("space-y-2", className)}>
      {data.map((d, i) => {
        const v = toNum(d.value);
        const frac = v === null ? 0 : Math.min(Math.abs(v) / m, 1);
        const color = tone === "signed" ? ((v ?? 0) >= 0 ? "bg-up" : "bg-down") : "bg-accent";
        return (
          <li key={d.label + i} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-xs" title={d.note}>
            <span className="truncate text-muted">{d.label}</span>
            <span className="h-2 overflow-hidden rounded-full bg-surface-3" aria-hidden>
              <span className={cn("block h-full rounded-full", color)} style={{ width: `${(frac * 100).toFixed(1)}%` }} />
            </span>
            <span className="num w-16 text-right font-medium">{v === null ? "n/a" : format(v)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Small meter 0..max (score / confidence). */
export function Meter({ value, max = 100, className, label }: { value: Numeric; max?: number; className?: string; label: string }) {
  const v = toNum(value);
  const frac = v === null ? 0 : Math.max(0, Math.min(v / max, 1));
  const color = v === null ? "bg-subtle" : frac >= 0.7 ? "bg-up" : frac >= 0.45 ? "bg-warn" : "bg-down";
  return (
    <span
      className={cn("inline-flex h-1.5 w-16 overflow-hidden rounded-full bg-surface-3", className)}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={v ?? undefined}
      aria-valuetext={v === null ? "not available" : `${num(v, 0)} of ${max}`}
    >
      <span className={cn("h-full rounded-full", color)} style={{ width: `${(frac * 100).toFixed(0)}%` }} />
    </span>
  );
}
