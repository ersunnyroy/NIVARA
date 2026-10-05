import { cn } from "./cn";

export function Stat({
  label,
  value,
  sub,
  tone,
  className,
  badge,
  size = "md",
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "up" | "down" | "flat" | "na" | "warn";
  className?: string;
  badge?: React.ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
        <span className="truncate">{label}</span>
        {badge}
      </div>
      <div
        className={cn(
          "num mt-1 truncate font-semibold",
          size === "lg" ? "text-2xl" : size === "sm" ? "text-sm" : "text-lg",
          tone === "up" && "text-up",
          tone === "down" && "text-down",
          tone === "warn" && "text-warn",
          tone === "na" && "text-subtle",
        )}
      >
        {value}
      </div>
      {sub ? <div className="num mt-0.5 truncate text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

export function StatGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-6", className)}>{children}</div>;
}
