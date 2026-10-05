import { cn } from "./cn";

export type BadgeTone = "neutral" | "up" | "down" | "warn" | "info" | "accent" | "violet" | "outline";

const tones: Record<BadgeTone, string> = {
  neutral: "bg-surface-3 text-fg/80",
  up: "bg-up-soft text-up",
  down: "bg-down-soft text-down",
  warn: "bg-warn-soft text-warn",
  info: "bg-info-soft text-info",
  accent: "bg-accent-soft text-accent",
  violet: "bg-violet-soft text-violet",
  outline: "border border-border-strong text-muted",
};

export function Badge({
  tone = "neutral",
  className,
  children,
  title,
  size = "sm",
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
  title?: string;
  size?: "xs" | "sm";
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md font-semibold uppercase tracking-wide",
        size === "xs" ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-[11px]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
