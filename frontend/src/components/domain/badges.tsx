import { CircleAlert, CircleCheck, CircleMinus, CircleX, Eye, FlaskConical, Rocket } from "lucide-react";
import { titleCase, toNum } from "@/lib/format";
import type { Numeric } from "@/lib/types";
import { Badge, cn, type BadgeTone } from "@/components/ui";
import { Meter } from "@/components/charts/svg";

const ACTION_TONE: Record<string, BadgeTone> = { BUY: "up", WAIT: "warn", HOLD: "info", SELL: "down", AVOID: "down" };

export function ActionBadge({ action, className }: { action?: string | null; className?: string }) {
  if (!action) return <Badge tone="outline" className={className}>n/a</Badge>;
  const a = action.toUpperCase();
  return (
    <Badge tone={ACTION_TONE[a] ?? "neutral"} className={className}>
      {a}
    </Badge>
  );
}

const SUIT: Record<string, { label: string; tone: BadgeTone; icon: React.ElementType; hint: string }> = {
  observation: { label: "Observation", tone: "neutral", icon: Eye, hint: "Watch only — model track record or data quality not sufficient for trading." },
  paper_trading: { label: "Paper trading", tone: "violet", icon: FlaskConical, hint: "Suitable for paper trading to build a track record." },
  live_consideration: { label: "Live consideration", tone: "accent", icon: Rocket, hint: "May be considered for live capital after your own review. Not advice." },
};

export function SuitabilityBadge({ value, className }: { value?: string | null; className?: string }) {
  if (!value) return <Badge tone="outline" className={className}>suitability n/a</Badge>;
  const s = SUIT[value] ?? { label: titleCase(value), tone: "neutral" as BadgeTone, icon: Eye, hint: "" };
  const Icon = s.icon;
  return (
    <Badge tone={s.tone} className={className} title={s.hint}>
      <Icon className="size-3" aria-hidden />
      {s.label}
    </Badge>
  );
}

/** Normalise 0..1 or 0..100 to 0..100. */
export function to100(v: Numeric): number | null {
  const n = toNum(v);
  if (n === null) return null;
  return Math.abs(n) <= 1 ? n * 100 : n;
}

/** Backend confidence is on a 0–100 scale. */
export function Confidence({ value, className, showMeter = true }: { value: Numeric; className?: string; showMeter?: boolean }) {
  const v = toNum(value);
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="num text-sm font-medium">{v === null ? <span className="text-subtle">n/a</span> : <>{Math.round(v)}<span className="text-xs text-muted">/100</span></>}</span>
      {showMeter ? <Meter value={v} label="Confidence" /> : null}
    </span>
  );
}

export function ScorePill({ value, className }: { value: Numeric; className?: string }) {
  const v = toNum(value);
  const tone = v === null ? "text-subtle bg-surface-3" : v >= 70 ? "text-up bg-up-soft" : v >= 55 ? "text-warn bg-warn-soft" : "text-down bg-down-soft";
  return (
    <span className={cn("num inline-flex min-w-10 justify-center rounded-md px-1.5 py-0.5 text-sm font-bold", tone, className)} title="Opportunity score (0–100)">
      {v === null ? "n/a" : Math.round(v)}
    </span>
  );
}

export type ActionLevel = "ok" | "caution" | "danger" | "neutral";

export function monitorLevel(action?: string | null, severity?: string | null): ActionLevel {
  const a = (action ?? "").toUpperCase();
  const s = (severity ?? "").toLowerCase();
  if (a.includes("EXIT") || a === "SELL" || s === "high" || s === "critical") return "danger";
  if (/(TRAIL|PARTIAL|BOOK|REVIEW|WATCH|TIGHTEN|REDUCE|CAUTION|WAIT)/.test(a) || s === "medium" || s === "warning") return "caution";
  if (a.includes("HOLD") || a === "ADD" || s === "low" || s === "info") return "ok";
  return "neutral";
}

const LEVEL = {
  ok: { icon: CircleCheck, cls: "text-up bg-up-soft", dot: "bg-up" },
  caution: { icon: CircleAlert, cls: "text-warn bg-warn-soft", dot: "bg-warn" },
  danger: { icon: CircleX, cls: "text-down bg-down-soft", dot: "bg-down" },
  neutral: { icon: CircleMinus, cls: "text-muted bg-surface-3", dot: "bg-subtle" },
} as const;

/** 🟢 HOLD / 🟡 TRAIL STOP / 🔴 EXIT — icon + text + colour, never colour alone. */
export function MonitorActionBadge({ action, severity, className }: { action?: string | null; severity?: string | null; className?: string }) {
  const lvl = monitorLevel(action, severity);
  const L = LEVEL[lvl];
  const Icon = L.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide", L.cls, className)}>
      <Icon className="size-3.5" aria-hidden />
      {action ? action.replace(/_/g, " ") : "No action"}
    </span>
  );
}

export function EstimatedTag({ className }: { className?: string }) {
  return (
    <Badge tone="warn" size="xs" className={className} title="Estimate based on configured tax rules — verify with a qualified tax professional">
      Estimated
    </Badge>
  );
}

export function RegimeBadge({ regime, className }: { regime?: string | null; className?: string }) {
  if (!regime) return <Badge tone="outline" className={className}>regime n/a</Badge>;
  const r = regime.toUpperCase();
  const tone: BadgeTone = r.includes("BULL") ? "up" : r.includes("BEAR") ? "down" : "warn";
  return <Badge tone={tone} className={className}>{r}</Badge>;
}
