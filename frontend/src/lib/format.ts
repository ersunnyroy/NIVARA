import type { Numeric } from "./types";

/** Placeholder for any missing value. Never substitute 0 for missing data. */
export const NA = "n/a";
export const MINUS = "−"; // typographic minus

export function toNum(v: Numeric | unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const n = Number(v.replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function isNum(v: unknown): boolean {
  return toNum(v) !== null;
}

const inrFmt = new Map<string, Intl.NumberFormat>();
function nf(min: number, max: number): Intl.NumberFormat {
  const key = `${min}:${max}`;
  let f = inrFmt.get(key);
  if (!f) {
    f = new Intl.NumberFormat("en-IN", { minimumFractionDigits: min, maximumFractionDigits: max });
    inrFmt.set(key, f);
  }
  return f;
}

/** Indian digit grouping: 1240000 → "12,40,000". */
export function num(v: Numeric | unknown, digits = 2, minDigits?: number): string {
  const n = toNum(v);
  if (n === null) return NA;
  const s = nf(minDigits ?? Math.min(digits, 2), digits).format(Math.abs(n));
  return n < 0 ? `${MINUS}${s}` : s;
}

export function int(v: Numeric | unknown): string {
  return num(v, 0, 0);
}

/** ₹12,40,000 (or ₹1,234.50 for prices). `digits` defaults to 2 for < 1 lakh, else 0. */
export function inr(v: Numeric | unknown, digits?: number): string {
  const n = toNum(v);
  if (n === null) return NA;
  const d = digits ?? (Math.abs(n) >= 100000 ? 0 : 2);
  const s = nf(d, d).format(Math.abs(n));
  return n < 0 ? `${MINUS}₹${s}` : `₹${s}`;
}

/** Signed INR: +₹1,200 / −₹540. */
export function inrSigned(v: Numeric | unknown, digits?: number): string {
  const n = toNum(v);
  if (n === null) return NA;
  if (n === 0) return inr(0, digits);
  return n > 0 ? `+${inr(n, digits)}` : inr(n, digits);
}

/** Compact INR: ₹10.8L / ₹1.2Cr / ₹85.4K. */
export function inrCompact(v: Numeric | unknown, signed = false): string {
  const n = toNum(v);
  if (n === null) return NA;
  const a = Math.abs(n);
  let s: string;
  if (a >= 1e7) s = `₹${trim(a / 1e7, a >= 1e9 ? 0 : a >= 1e8 ? 1 : 2)}Cr`;
  else if (a >= 1e5) s = `₹${trim(a / 1e5, a >= 1e6 ? 1 : 2)}L`;
  else if (a >= 1e3) s = `₹${trim(a / 1e3, 1)}K`;
  else s = `₹${trim(a, a < 100 ? 2 : 0)}`;
  if (n < 0) return `${MINUS}${s}`;
  if (signed && n > 0) return `+${s}`;
  return s;
}

/** Values already expressed in crore (e.g. FII flows). */
export function crore(v: Numeric | unknown, signed = true): string {
  const n = toNum(v);
  if (n === null) return NA;
  const s = `₹${nf(0, 0).format(Math.abs(n))} Cr`;
  if (n < 0) return `${MINUS}${s}`;
  return signed && n > 0 ? `+${s}` : s;
}

function trim(n: number, d: number): string {
  return nf(0, d).format(n);
}

/** Percentage with explicit sign: +2.35% / −1.10%. */
export function pct(v: Numeric | unknown, digits = 2, signed = true): string {
  const n = toNum(v);
  if (n === null) return NA;
  const s = nf(digits, digits).format(Math.abs(n));
  if (n < 0) return `${MINUS}${s}%`;
  if (n > 0 && signed) return `+${s}%`;
  return `${s}%`;
}

/** Fraction (0..1) as percent, unsigned. Accepts already-percent values (>1). */
export function ratioPct(v: Numeric | unknown, digits = 1): string {
  const n = toNum(v);
  if (n === null) return NA;
  const p = Math.abs(n) <= 1 ? n * 100 : n;
  return pct(p, digits, false);
}

export function compactNum(v: Numeric | unknown): string {
  const n = toNum(v);
  if (n === null) return NA;
  const a = Math.abs(n);
  let s: string;
  if (a >= 1e7) s = `${trim(a / 1e7, 2)}Cr`;
  else if (a >= 1e5) s = `${trim(a / 1e5, 2)}L`;
  else if (a >= 1e3) s = `${trim(a / 1e3, 1)}K`;
  else s = trim(a, 0);
  return n < 0 ? `${MINUS}${s}` : s;
}

export function rr(v: Numeric | unknown): string {
  const n = toNum(v);
  return n === null ? NA : `1:${nf(1, 2).format(n)}`;
}

/** Tone for a signed value: "up" | "down" | "flat" | "na". */
export type Tone = "up" | "down" | "flat" | "na";
export function tone(v: Numeric | unknown): Tone {
  const n = toNum(v);
  if (n === null) return "na";
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "flat";
}

/* ------------------------------------------------------------- dates (IST) */

const IST = "Asia/Kolkata";
const dtFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: IST,
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dFmt = new Intl.DateTimeFormat("en-IN", { timeZone: IST, day: "2-digit", month: "short", year: "numeric" });
const dFmtUTC = new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" });

function parseDate(v: string | null | undefined): { d: Date; dateOnly: boolean } | null {
  if (!v) return null;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(v);
  // Date-only strings are calendar dates (session dates) — never shift them across time zones.
  const d = new Date(dateOnly ? `${v}T00:00:00Z` : v);
  return Number.isNaN(d.getTime()) ? null : { d, dateOnly };
}

/** "05 Oct 2026, 15:30 IST" — or "05 Oct 2026" for date-only values. */
export function dateTimeIST(v: string | null | undefined): string {
  const p = parseDate(v);
  if (!p) return NA;
  if (p.dateOnly) return dFmtUTC.format(p.d);
  return `${dtFmt.format(p.d)} IST`;
}

export function dateIST(v: string | null | undefined): string {
  const p = parseDate(v);
  if (!p) return NA;
  return p.dateOnly ? dFmtUTC.format(p.d) : dFmt.format(p.d);
}

/** Relative "3h ago" for timestamps; caller passes `now` to stay pure during render. */
export function ago(v: string | null | undefined, now: number): string {
  const p = parseDate(v);
  if (!p) return NA;
  const s = Math.round((now - p.d.getTime()) / 1000);
  if (s < 0) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/** Today's date in IST as YYYY-MM-DD (call from effects/handlers, not render). */
export function todayIST(): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  return parts; // en-CA gives YYYY-MM-DD
}

/** Indian financial year label (e.g. "2026-27") for a YYYY-MM-DD date. */
export function fyFor(isoDate: string): string {
  const [y, m] = isoDate.split("-").map(Number);
  const start = m >= 4 ? y : y - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

export function titleCase(v: unknown): string {
  if (v === null || v === undefined || v === "") return NA;
  const s = typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : JSON.stringify(v);
  return s
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function holding(min?: number | null, max?: number | null): string {
  if (min == null && max == null) return NA;
  if (min != null && max != null) return min === max ? `${min} sessions` : `${min}–${max} sessions`;
  return `${min ?? max} sessions`;
}
