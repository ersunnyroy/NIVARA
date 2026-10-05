"use client";

import { Loader2, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useStockSearch } from "@/lib/hooks";
import type { StockSearchHit } from "@/lib/types";
import { Badge, cn } from "@/components/ui";

/** Accessible combobox searching /api/stocks. */
export function StockSearch({
  onSelect,
  placeholder = "Search NSE stocks…",
  className,
  inputClassName,
  autoFocus,
  initial = "",
  clearOnSelect = true,
  id,
  ariaLabel = "Search stocks",
  required,
}: {
  onSelect: (hit: StockSearchHit) => void;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
  autoFocus?: boolean;
  initial?: string;
  clearOnSelect?: boolean;
  id?: string;
  ariaLabel?: string;
  required?: boolean;
}) {
  const [text, setText] = useState(initial);
  const [q, setQ] = useState(initial);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setQ(text), 200);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const search = useStockSearch(q, 10);
  const hits = q.trim() ? search.data ?? [] : [];
  const showList = open && text.trim().length > 0;

  function choose(h: StockSearchHit) {
    onSelect(h);
    setOpen(false);
    setText(clearOnSelect ? "" : h.symbol);
    setActive(0);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, Math.max(hits.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      if (showList && hits[active]) {
        e.preventDefault();
        choose(hits[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={wrap} className={cn("relative min-w-0", className)}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden />
      <input
        id={id}
        type="text"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && hits[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        autoFocus={autoFocus}
        required={required}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        className={cn(
          "h-9 w-full rounded-lg border border-border-strong bg-surface pl-8 pr-8 text-sm text-fg placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
          inputClassName,
        )}
      />
      {search.isFetching ? <Loader2 className="absolute right-2.5 top-1/2 size-4 -translate-y-1/2 animate-spin text-subtle" aria-hidden /> : null}
      {showList ? (
        <ul id={listId} role="listbox" className="absolute z-50 mt-1 max-h-80 w-full min-w-64 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-xl">
          {search.isError ? (
            <li className="px-3 py-2 text-xs text-down">{search.error.message}</li>
          ) : hits.length === 0 ? (
            <li className="px-3 py-2 text-xs text-muted">{search.isFetching || q !== text ? "Searching…" : "No matching stocks. Has the securities master been loaded?"}</li>
          ) : (
            hits.map((h, i) => (
              <li
                key={h.symbol}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(h);
                }}
                onMouseEnter={() => setActive(i)}
                className={cn("flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2", i === active && "bg-surface-2")}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{h.symbol}</span>
                  <span className="block truncate text-xs text-muted">
                    {h.name ?? ""}
                    {h.sector ? ` · ${h.sector}` : ""}
                  </span>
                </span>
                {h.is_fno ? <Badge tone="info" size="xs">F&amp;O</Badge> : null}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
