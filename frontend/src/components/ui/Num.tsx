import { inr, inrCompact, inrSigned, NA, pct, tone, toNum } from "@/lib/format";
import type { Numeric } from "@/lib/types";
import { cn } from "./cn";

const toneCls = { up: "text-up", down: "text-down", flat: "text-muted", na: "text-subtle" } as const;

/** Signed percentage — colour AND explicit +/− sign (never colour alone). */
export function Pct({ value, digits = 2, className, plain }: { value: Numeric; digits?: number; className?: string; plain?: boolean }) {
  return <span className={cn("num whitespace-nowrap", !plain && toneCls[tone(value)], className)}>{pct(value, digits)}</span>;
}

/** Signed money (P&L). */
export function Pnl({
  value,
  compact,
  className,
  digits,
  plain,
}: {
  value: Numeric;
  compact?: boolean;
  className?: string;
  digits?: number;
  plain?: boolean;
}) {
  const text = compact ? inrCompact(value, true) : inrSigned(value, digits);
  return <span className={cn("num whitespace-nowrap", !plain && toneCls[tone(value)], className)}>{text}</span>;
}

/** Plain money; missing → n/a (muted). */
export function Money({ value, compact, digits, className }: { value: Numeric; compact?: boolean; digits?: number; className?: string }) {
  const n = toNum(value);
  if (n === null) return <NAValue className={className} />;
  return <span className={cn("num whitespace-nowrap", className)}>{compact ? inrCompact(n) : inr(n, digits)}</span>;
}

export function NAValue({ reason, className }: { reason?: string | null; className?: string }) {
  return (
    <span className={cn("whitespace-nowrap text-subtle", className)} title={reason ?? "Not available"}>
      {NA}
      {reason ? <span className="sr-only"> — {reason}</span> : null}
    </span>
  );
}
