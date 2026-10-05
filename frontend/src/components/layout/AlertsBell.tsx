"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { useAlertEvents } from "@/lib/hooks";

export function AlertsBell() {
  const q = useAlertEvents();
  const unread = (q.data ?? []).filter((e) => !(e.read_at || e.is_read)).length;
  return (
    <Link
      href="/alerts"
      className="relative inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
      aria-label={unread ? `Alerts: ${unread} unread` : "Alerts"}
    >
      <Bell className="size-4" aria-hidden />
      {unread ? (
        <span className="num absolute right-1 top-1 min-w-4 rounded-full bg-down px-1 text-center text-[10px] font-bold leading-4 text-white">
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Link>
  );
}
