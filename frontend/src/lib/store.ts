"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

/**
 * Tiny localStorage-backed state via useSyncExternalStore: SSR renders the fallback,
 * the client re-renders with the stored value without hydration errors.
 */
const EVT = "nivara:storage";

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener(EVT, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(EVT, cb);
  };
}

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable — keep in-memory behaviour */
  }
  window.dispatchEvent(new Event(EVT));
}

export function useStoredState<T>(key: string, fallback: T): [T, (v: T) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => readRaw(key),
    () => null,
  );
  const value = useMemo<T>(() => {
    if (raw === null) return fallback;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
    // fallback is intentionally treated as a constant default
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw]);
  const set = useCallback((v: T) => writeStored(key, v), [key]);
  return [value, set];
}
