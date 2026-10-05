import { forwardRef, useId } from "react";
import { cn } from "./cn";

const base =
  "h-9 w-full min-w-0 rounded-lg border border-border-strong bg-surface px-3 text-sm text-fg placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(base, rest.type === "number" && "num", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cn(base, "h-auto min-h-[72px] py-2", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn(base, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
});

/** Label + control + hint/error. Pass a render function to receive the generated id. */
export function Field({
  label,
  hint,
  error,
  className,
  children,
  required,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  className?: string;
  required?: boolean;
  children: (id: string) => React.ReactNode;
}) {
  const id = useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}
        {required ? <span className="text-down"> *</span> : null}
      </label>
      {children(id)}
      {error ? (
        <p className="text-xs text-down" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  className,
  disabled,
}: {
  label: React.ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <label className={cn("inline-flex cursor-pointer select-none items-center gap-2 text-sm text-fg", disabled && "opacity-60", className)}>
      <input
        type="checkbox"
        className="size-4 rounded border-border-strong accent-[var(--accent)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}
