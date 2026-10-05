"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Shield, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useLogout } from "@/lib/hooks";
import type { User } from "@/lib/types";
import { cn } from "@/components/ui";

export function UserMenu({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const logout = useLogout();
  const router = useRouter();
  const qc = useQueryClient();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initials = (user.full_name || user.email).split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex size-9 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent hover:brightness-95"
        aria-label="Account menu"
      >
        {initials || <UserRound className="size-4" />}
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 z-50 mt-2 w-64 rounded-xl border border-border bg-surface p-1.5 shadow-xl">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{user.full_name || "Signed in"}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
            <p className={cn("mt-1 inline-flex items-center gap-1 text-[11px] font-semibold uppercase", user.role === "admin" ? "text-violet" : "text-muted")}>
              <Shield className="size-3" aria-hidden /> {user.role}
            </p>
          </div>
          <div className="my-1 h-px bg-border" />
          <button
            role="menuitem"
            type="button"
            disabled={logout.isPending}
            onClick={() =>
              logout.mutate(undefined, {
                onSettled: () => {
                  qc.clear();
                  router.replace("/login");
                },
              })
            }
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-fg hover:bg-surface-2"
          >
            <LogOut className="size-4 text-muted" aria-hidden /> Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
