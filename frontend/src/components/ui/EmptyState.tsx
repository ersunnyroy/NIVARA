import { Inbox } from "lucide-react";
import { cn } from "./cn";

export function EmptyState({
  title,
  children,
  icon,
  action,
  className,
  compact,
}: {
  title: React.ReactNode;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center", compact ? "gap-1.5 px-4 py-6" : "gap-2 px-6 py-10", className)}>
      <div className="text-subtle" aria-hidden>
        {icon ?? <Inbox className={compact ? "size-6" : "size-8"} />}
      </div>
      <p className="text-sm font-medium text-fg">{title}</p>
      {children ? <div className="max-w-md text-xs leading-relaxed text-muted">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
