/**
 * Fetch wrapper for the NIVARA API.
 *
 * - All calls go to same-origin `/api/*` (proxied to FastAPI by next.config rewrites) so the
 *   httpOnly session cookie is sent automatically.
 * - Every non-GET request carries `x-csrf-token` = value of the `nivara_csrf` cookie
 *   (double-submit CSRF, validated by the backend).
 * - 401 responses redirect to /login (except for the auth endpoints themselves).
 * - Errors are normalised into `ApiError` with the backend's `detail` message.
 */

export const API_BASE = "/api";
export const CSRF_COOKIE = "nivara_csrf";
export const CSRF_HEADER = "x-csrf-token";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly path: string;

  constructor(status: number, message: string, path: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.path = path;
  }

  /** Backend signalled the data needed for this view does not exist yet. */
  get isUnavailable(): boolean {
    return this.status === 503;
  }
  get isNotFound(): boolean {
    return this.status === 404;
  }
  get isForbidden(): boolean {
    return this.status === 403;
  }
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}${path.includes("?") ? "&" : "?"}${s}` : path;
}

function messageFrom(status: number, body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    const d = b.detail ?? b.message ?? b.error;
    if (typeof d === "string" && d.trim()) return d;
    if (Array.isArray(d)) {
      // FastAPI / Pydantic validation errors
      const parts = d
        .map((e) => {
          if (e && typeof e === "object") {
            const err = e as { loc?: unknown[]; msg?: string };
            const loc = Array.isArray(err.loc) ? err.loc.filter((x) => x !== "body").join(".") : "";
            return [loc, err.msg].filter(Boolean).join(": ");
          }
          return String(e);
        })
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
    if (d && typeof d === "object") {
      const inner = (d as Record<string, unknown>).message;
      if (typeof inner === "string") return inner;
    }
  }
  if (typeof body === "string" && body.trim() && body.length < 300 && !body.trim().startsWith("<")) return body.trim();
  if (status === 0) return "Cannot reach the NIVARA API. Is the backend running?";
  if (status === 502 || status === 504) return "The NIVARA API is not responding (gateway error). Is the backend running?";
  if (status === 500) return "The server hit an internal error.";
  return fallback;
}

const AUTH_PATHS = ["/auth/login", "/auth/register", "/auth/status", "/auth/me"];

function handleUnauthorized(path: string) {
  if (typeof window === "undefined") return;
  if (AUTH_PATHS.some((p) => path.startsWith(p))) return;
  const here = window.location.pathname;
  if (here.startsWith("/login")) return;
  const next = encodeURIComponent(here + window.location.search);
  // Hard navigation on purpose: drops all in-memory query state for the expired session.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${next}`);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const url = API_BASE + withQuery(path, opts.query);
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers ?? {}) };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
      signal: opts.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, messageFrom(0, null, "Network error"), path);
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    if (res.status === 401) handleUnauthorized(path);
    throw new ApiError(res.status, messageFrom(res.status, body, `${res.status} ${res.statusText || "Request failed"}`), path, body);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>(path, { method: "POST", body: body ?? {}, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body ?? {} }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function errorMessage(err: unknown): string {
  if (!err) return "";
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}

/** Accept either a bare array or a {items:[...]} / {results:[...]} envelope. */
export function asList<T>(v: unknown, ...keys: string[]): T[] {
  if (Array.isArray(v)) return v as T[];
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const k of [...keys, "items", "results", "data", "rows"]) {
      if (Array.isArray(o[k])) return o[k] as T[];
    }
  }
  return [];
}
