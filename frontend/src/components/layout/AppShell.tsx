"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, MoreHorizontal, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { ALL_NAV, MOBILE_PRIMARY, NAV_GROUPS, isActive } from "@/lib/nav";
import { useStoredState } from "@/lib/store";
import { StockSearch } from "@/components/domain/StockSearch";
import { ErrorState, GLOBAL_DISCLAIMER, Skeleton, cn } from "@/components/ui";
import { AlertsBell } from "./AlertsBell";
import { MarketStatusPill } from "./MarketStatusPill";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";

function Logo({ collapsed }: { collapsed?: boolean }) {
  return (
    <Link href="/dashboard" className="flex items-center gap-2 rounded-lg px-1" aria-label="NIVARA home">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-sm font-black text-accent-fg">N</span>
      {!collapsed ? (
        <span className="leading-tight">
          <span className="block text-sm font-bold tracking-[0.2em]">NIVARA</span>
          <span className="block text-[10px] text-muted">Research · Decision support</span>
        </span>
      ) : null}
    </Link>
  );
}

function NavList({ pathname, collapsed, onNavigate }: { pathname: string; collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-4">
      {NAV_GROUPS.map((g) => (
        <div key={g.label}>
          {!collapsed ? <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-subtle">{g.label}</p> : <div className="mx-3 mb-1 h-px bg-border" />}
          <ul className="flex flex-col gap-0.5">
            {g.items.map((it) => {
              const active = isActive(pathname, it.href);
              const Icon = it.icon;
              return (
                <li key={it.href}>
                  <Link
                    href={it.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={collapsed ? it.label : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                      collapsed && "justify-center px-0",
                      active ? "bg-accent-soft font-semibold text-accent" : "text-muted hover:bg-surface-2 hover:text-fg",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden />
                    {!collapsed ? <span className="truncate">{it.label}</span> : <span className="sr-only">{it.label}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const me = useMe();
  const [collapsed, setCollapsed] = useStoredState<boolean>("nivara-sidebar-collapsed", false);
  const [drawer, setDrawer] = useState(false);
  const unauth = me.error instanceof ApiError && me.error.status === 401;

  useEffect(() => {
    if (unauth) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [unauth, router, pathname]);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawer]);

  if (me.isPending || unauth) {
    return (
      <div className="flex min-h-dvh items-center justify-center" role="status" aria-label="Checking session">
        <div className="flex flex-col items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-accent text-lg font-black text-accent-fg">N</span>
          <Skeleton className="h-2 w-32" />
          <span className="sr-only">Checking your session…</span>
        </div>
      </div>
    );
  }

  if (me.isError) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center gap-4 p-6">
        <Logo />
        <ErrorState error={me.error} title="Cannot verify your session" onRetry={() => me.refetch()} />
        <p className="text-xs text-muted">
          The NIVARA API did not respond. If you are running locally, start the backend on port 8000 (or set <code>BACKEND_URL</code>).
        </p>
      </div>
    );
  }

  const user = me.data;
  const mobilePrimary = ALL_NAV.filter((n) => MOBILE_PRIMARY.includes(n.href));

  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>

      {/* Desktop / tablet sidebar */}
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border bg-surface md:flex",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div className={cn("flex h-14 items-center border-b border-border px-3", collapsed ? "justify-center" : "justify-between")}>
          <Logo collapsed={collapsed} />
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto px-2 py-4">
          <NavList pathname={pathname} collapsed={collapsed} />
        </div>
        <div className={cn("border-t border-border p-2", collapsed && "flex justify-center")}>
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-surface-2 hover:text-fg"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen className="size-4" aria-hidden /> : <PanelLeftClose className="size-4" aria-hidden />}
            {!collapsed ? "Collapse" : null}
          </button>
        </div>
      </aside>

      {/* Mobile drawer */}
      {drawer ? (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-black/50" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-border px-3">
              <Logo />
              <button type="button" onClick={() => setDrawer(false)} className="rounded-lg p-2 text-muted hover:bg-surface-2" aria-label="Close navigation">
                <X className="size-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 py-4">
              <NavList pathname={pathname} onNavigate={() => setDrawer(false)} />
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-border bg-surface/90 px-3 backdrop-blur sm:px-4">
          <button type="button" className="rounded-lg p-2 text-muted hover:bg-surface-2 md:hidden" onClick={() => setDrawer(true)} aria-label="Open navigation">
            <Menu className="size-5" />
          </button>
          <StockSearch
            className="w-full max-w-xs sm:max-w-sm"
            placeholder="Search stock (e.g. RELIANCE)"
            onSelect={(h) => router.push(`/stocks/${encodeURIComponent(h.symbol)}`)}
          />
          <div className="hidden min-w-0 lg:block">
            <MarketStatusPill />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <AlertsBell />
            <UserMenu user={user} />
          </div>
        </header>

        <div className="border-b border-border bg-surface px-3 py-1.5 lg:hidden">
          <MarketStatusPill className="border-0 px-0" />
        </div>

        <main id="main" className="mx-auto w-full min-w-0 max-w-[1600px] flex-1 px-3 py-4 pb-24 sm:px-4 md:pb-6 lg:px-6">
          {children}
        </main>

        <footer className="border-t border-border bg-surface px-4 py-3 pb-20 text-center text-[11px] leading-relaxed text-muted md:pb-3" role="contentinfo">
          <strong className="font-semibold text-fg/80">NIVARA</strong> · {GLOBAL_DISCLAIMER}
        </footer>
      </div>

      {/* Mobile bottom nav */}
      <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-border bg-surface/95 backdrop-blur md:hidden">
        {mobilePrimary.map((it) => {
          const Icon = it.icon;
          const active = isActive(pathname, it.href);
          return (
            <Link
              key={it.href}
              href={it.href}
              aria-current={active ? "page" : undefined}
              className={cn("flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium", active ? "text-accent" : "text-muted")}
            >
              <Icon className="size-5" aria-hidden />
              {it.label}
            </Link>
          );
        })}
        <button type="button" onClick={() => setDrawer(true)} className="flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium text-muted" aria-label="More navigation">
          <MoreHorizontal className="size-5" aria-hidden />
          More
        </button>
      </nav>
    </div>
  );
}
