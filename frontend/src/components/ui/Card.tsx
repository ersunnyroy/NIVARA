import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "./cn";

export function Card({
  className,
  children,
  as: Tag = "section",
  ...rest
}: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" }) {
  return (
    <Tag className={cn("min-w-0 rounded-xl border border-border bg-surface shadow-card", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  subtitle,
  icon,
  actions,
  href,
  hrefLabel = "View all",
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  href?: string;
  hrefLabel?: string;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-3 gap-y-2 border-b border-border px-4 py-3", className)}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
          {icon ? <span className="text-muted" aria-hidden>{icon}</span> : null}
          {title}
        </h2>
        {subtitle ? <div className="mt-0.5 text-xs text-muted">{subtitle}</div> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {href ? (
          <Link href={href} className="inline-flex items-center gap-0.5 rounded text-xs font-medium text-accent hover:underline">
            {hrefLabel}
            <ChevronRight className="size-3.5" aria-hidden />
          </Link>
        ) : null}
      </div>
    </header>
  );
}

export function CardBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("p-4", className)}>{children}</div>;
}

export function CardFooter({ className, children }: { className?: string; children: React.ReactNode }) {
  return <footer className={cn("border-t border-border px-4 py-2.5 text-xs text-muted", className)}>{children}</footer>;
}
