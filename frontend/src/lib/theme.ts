"use client";

import { useSyncExternalStore } from "react";

export type ThemeMode = "light" | "dark" | "system";
export const THEME_KEY = "nivara-theme";

/** Runs before first paint (inlined in <head>) — keep in sync with applyTheme(). */
export const THEME_SCRIPT = `(function(){try{var m=localStorage.getItem("${THEME_KEY}");var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=(m==="light"||m==="dark")?m:(d?"dark":"light");document.documentElement.setAttribute("data-theme",t);document.documentElement.setAttribute("data-theme-mode",m==="light"||m==="dark"?m:"system");}catch(e){}})();`;

const EVT = "nivara:theme";

export function getMode(): ThemeMode {
  if (typeof document === "undefined") return "system";
  const m = document.documentElement.getAttribute("data-theme-mode");
  return m === "light" || m === "dark" ? m : "system";
}

export function getResolved(): "light" | "dark" {
  if (typeof document === "undefined") return "light";
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function applyTheme(mode: ThemeMode) {
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = mode === "system" ? (dark ? "dark" : "light") : mode;
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.setAttribute("data-theme-mode", mode);
  try {
    if (mode === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, mode);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(EVT));
}

function subscribe(cb: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onSystem = () => {
    if (getMode() === "system") applyTheme("system");
    else cb();
  };
  mq.addEventListener("change", onSystem);
  window.addEventListener(EVT, cb);
  return () => {
    mq.removeEventListener("change", onSystem);
    window.removeEventListener(EVT, cb);
  };
}

export function useThemeMode(): ThemeMode {
  return useSyncExternalStore(subscribe, getMode, () => "system");
}

export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, getResolved, () => "light");
}
