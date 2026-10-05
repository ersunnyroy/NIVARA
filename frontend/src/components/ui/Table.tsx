import { cn } from "./cn";

/** Horizontal scroll stays inside the card; the page never scrolls sideways. */
export function TableWrap({ children, className, label }: { children: React.ReactNode; className?: string; label?: string }) {
  return (
    <div className={cn("scroll-thin w-full overflow-x-auto", className)} role="region" aria-label={label} tabIndex={label ? 0 : undefined}>
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return <thead className="bg-surface-2/60 text-left text-[11px] uppercase tracking-wide text-muted">{children}</thead>;
}

export function Th({
  children,
  className,
  align = "left",
  ...rest
}: React.ThHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  return (
    <th
      scope="col"
      className={cn(
        "whitespace-nowrap border-b border-border px-3 py-2 font-semibold",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  className,
  align = "left",
  ...rest
}: React.TdHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  return (
    <td
      className={cn(
        "border-b border-border px-3 py-2 align-middle",
        align === "right" && "num text-right",
        align === "center" && "text-center",
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}

export function Tr({ children, className, ...rest }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn("transition-colors hover:bg-surface-2/50", className)} {...rest}>
      {children}
    </tr>
  );
}
