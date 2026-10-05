"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { applyTheme, useThemeMode, type ThemeMode } from "@/lib/theme";
import { cn } from "@/components/ui";

const ORDER: ThemeMode[] = ["system", "light", "dark"];
const ICON = { system: Monitor, light: Sun, dark: Moon } as const;
const LABEL = { system: "System theme", light: "Light theme", dark: "Dark theme" } as const;

export function ThemeToggle({ className }: { className?: string }) {
  const mode = useThemeMode();
  const Icon = ICON[mode];
  const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
  return (
    <button
      type="button"
      onClick={() => applyTheme(next)}
      className={cn("inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg", className)}
      aria-label={`${LABEL[mode]} — switch to ${LABEL[next].toLowerCase()}`}
      title={`${LABEL[mode]} (click for ${LABEL[next].toLowerCase()})`}
    >
      <Icon className="size-4" aria-hidden />
    </button>
  );
}
