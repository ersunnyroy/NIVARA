import { ShieldAlert } from "lucide-react";
import { cn } from "./cn";

export const GLOBAL_DISCLAIMER =
  "Research & decision-support only. Not investment advice. No returns are guaranteed. Tax figures are estimates — verify with a qualified tax professional.";

export function Disclaimer({ children, className, tone = "muted" }: { children?: React.ReactNode; className?: string; tone?: "muted" | "warn" }) {
  return (
    <p
      className={cn(
        "flex items-start gap-2 rounded-lg px-3 py-2 text-xs leading-relaxed",
        tone === "warn" ? "border border-warn/30 bg-warn-soft text-warn" : "bg-surface-2 text-muted",
        className,
      )}
    >
      <ShieldAlert className="mt-px size-3.5 shrink-0" aria-hidden />
      <span>{children ?? GLOBAL_DISCLAIMER}</span>
    </p>
  );
}
