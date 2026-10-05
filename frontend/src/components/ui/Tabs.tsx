"use client";

import { useId, useRef } from "react";
import { cn } from "./cn";

export interface TabItem<K extends string = string> {
  key: K;
  label: React.ReactNode;
  badge?: React.ReactNode;
}

/** Accessible tablist (roving focus with arrow keys). Render panels with <TabPanel>. */
export function Tabs<K extends string>({
  tabs,
  value,
  onChange,
  className,
  label,
  idBase,
}: {
  tabs: TabItem<K>[];
  value: K;
  onChange: (k: K) => void;
  className?: string;
  label: string;
  idBase?: string;
}) {
  const gen = useId();
  const base = idBase ?? gen;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: React.KeyboardEvent, i: number) {
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next >= 0) {
      e.preventDefault();
      onChange(tabs[next].key);
      refs.current[next]?.focus();
    }
  }

  return (
    <div className={cn("scroll-thin overflow-x-auto", className)}>
      <div role="tablist" aria-label={label} className="flex min-w-max gap-1 border-b border-border">
        {tabs.map((t, i) => {
          const sel = t.key === value;
          return (
            <button
              key={t.key}
              ref={(el) => {
                refs.current[i] = el;
              }}
              role="tab"
              type="button"
              id={`${base}-tab-${t.key}`}
              aria-selected={sel}
              aria-controls={`${base}-panel-${t.key}`}
              tabIndex={sel ? 0 : -1}
              onClick={() => onChange(t.key)}
              onKeyDown={(e) => onKey(e, i)}
              className={cn(
                "-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                sel ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg",
              )}
            >
              {t.label}
              {t.badge}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TabPanel({ idBase, k, children, className }: { idBase: string; k: string; children: React.ReactNode; className?: string }) {
  return (
    <div role="tabpanel" id={`${idBase}-panel-${k}`} aria-labelledby={`${idBase}-tab-${k}`} tabIndex={0} className={cn("focus-visible:outline-none", className)}>
      {children}
    </div>
  );
}

/** Compact segmented control (e.g. chart ranges). */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  label,
  className,
  size = "sm",
}: {
  options: { key: K; label: React.ReactNode }[];
  value: K;
  onChange: (k: K) => void;
  label: string;
  className?: string;
  size?: "xs" | "sm";
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex flex-wrap rounded-lg border border-border bg-surface-2 p-0.5", className)}>
      {options.map((o) => {
        const sel = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="radio"
            aria-checked={sel}
            onClick={() => onChange(o.key)}
            className={cn(
              "rounded-md font-medium transition-colors",
              size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
              sel ? "bg-surface text-fg shadow-card" : "text-muted hover:text-fg",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
