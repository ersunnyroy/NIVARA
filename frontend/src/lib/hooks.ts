"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { ApiError, api, asList } from "./api";
import type * as T from "./types";

type QOpts<D> = Omit<UseQueryOptions<D, ApiError, D, QueryKey>, "queryKey" | "queryFn">;

function useApi<D>(key: QueryKey, path: string | null, query?: Record<string, string | number | boolean | null | undefined>, opts?: QOpts<D>) {
  return useQuery<D, ApiError>({
    queryKey: key,
    queryFn: ({ signal }) => api.get<D>(path as string, query, signal),
    enabled: path !== null && (opts?.enabled ?? true),
    ...opts,
  });
}

function useListApi<D>(key: QueryKey, path: string | null, query?: Record<string, string | number | boolean | null | undefined>, opts?: QOpts<D[]>) {
  return useQuery<D[], ApiError>({
    queryKey: key,
    queryFn: async ({ signal }) => asList<D>(await api.get<unknown>(path as string, query, signal)),
    enabled: path !== null && (opts?.enabled ?? true),
    ...opts,
  });
}

/** Mutation that invalidates the given query-key prefixes on success. */
function useApiMutation<In, Out>(fn: (input: In) => Promise<Out>, invalidate: QueryKey[] = []) {
  const qc = useQueryClient();
  return useMutation<Out, ApiError, In>({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: k })));
    },
  });
}

const enc = encodeURIComponent;

/* ---------------------------------------------------------------- auth */

export const useAuthStatus = () => useApi<T.AuthStatus>(["auth", "status"], "/auth/status", undefined, { retry: 1 });

export const useMe = () =>
  useApi<T.User>(["auth", "me"], "/auth/me", undefined, {
    retry: (count, err) => !(err instanceof ApiError && (err.status === 401 || err.status === 403)) && count < 2,
    staleTime: 5 * 60_000,
  });

export function useLogin() {
  const qc = useQueryClient();
  return useMutation<T.LoginResponse, ApiError, { email: string; password: string }>({
    mutationFn: (b) => api.post<T.LoginResponse>("/auth/login", b),
    onSuccess: (r) => {
      qc.clear();
      if (r?.user) qc.setQueryData(["auth", "me"], r.user);
    },
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation<T.LoginResponse, ApiError, { email: string; password: string; full_name: string }>({
    mutationFn: (b) => api.post<T.LoginResponse>("/auth/register", b),
    onSuccess: (r) => {
      qc.clear();
      if (r?.user) qc.setQueryData(["auth", "me"], r.user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, void>({
    mutationFn: () => api.post("/auth/logout"),
    onSettled: () => qc.clear(),
  });
}

/* -------------------------------------------------------------- market */

export const useMarketStatus = () =>
  useApi<T.MarketStatus>(["market", "status"], "/market/status", undefined, { refetchInterval: 60_000 });

export const useMarketOverview = () => useApi<T.MarketOverview>(["market", "overview"], "/market/overview");

/* -------------------------------------------------------- opportunities */

export const useOpportunities = (date?: string) =>
  useApi<T.OpportunitiesResponse>(["opportunities", date ?? "latest"], "/opportunities", { date });

export const useRunScan = () =>
  useApiMutation<void, unknown>(() => api.post("/opportunities/run"), [["opportunities"], ["recommendations"]]);

export const useRecommendations = (q: { symbol?: string; from?: string; to?: string }) =>
  useListApi<T.Recommendation>(["recommendations", "list", q], "/recommendations", q, { placeholderData: keepPreviousData });

export const useRecommendation = (id: number | string | null) =>
  useApi<T.Recommendation>(["recommendations", "one", id], id == null ? null : `/recommendations/${id}`);

export const useTrackRecord = () => useApi<T.TrackRecord>(["recommendations", "track-record"], "/recommendations/track-record");

/* -------------------------------------------------------------- stocks */

export const useStockSearch = (q: string, limit = 12) =>
  useListApi<T.StockSearchHit>(["stocks", "search", q, limit], q.trim().length >= 1 ? "/stocks" : null, { q: q.trim(), limit }, {
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

export const useStock = (symbol: string) => useApi<T.StockDetail>(["stock", symbol, "detail"], `/stocks/${enc(symbol)}`);

export const useBars = (symbol: string, range: T.ChartRange) =>
  useApi<T.BarsResponse>(["stock", symbol, "bars", range], `/stocks/${enc(symbol)}/bars`, { range }, { placeholderData: keepPreviousData });

export const useTechnical = (symbol: string, enabled = true) =>
  useApi<T.TechnicalResponse>(["stock", symbol, "technical"], `/stocks/${enc(symbol)}/technical`, undefined, { enabled });

export const useFundamentals = (symbol: string, enabled = true) =>
  useApi<T.FundamentalsResponse>(["stock", symbol, "fundamentals"], `/stocks/${enc(symbol)}/fundamentals`, undefined, { enabled });

export const useStockNews = (symbol: string, enabled = true) =>
  useListApi<T.NewsItem>(["stock", symbol, "news"], `/stocks/${enc(symbol)}/news`, undefined, { enabled });

export const useStockFno = (symbol: string, enabled = true) =>
  useApi<T.StockFno>(["stock", symbol, "fno"], `/stocks/${enc(symbol)}/fno`, undefined, { enabled });

export const useCorporateActions = (symbol: string, enabled = true) =>
  useListApi<T.CorporateAction>(["stock", symbol, "ca"], `/stocks/${enc(symbol)}/corporate-actions`, undefined, { enabled });

export const useShareholding = (symbol: string, enabled = true) =>
  useListApi<T.ShareholdingRow>(["stock", symbol, "shareholding"], `/stocks/${enc(symbol)}/shareholding`, undefined, { enabled });

export const useSignals = (symbol: string, enabled = true) =>
  useApi<T.StockSignals>(["stock", symbol, "signals"], `/stocks/${enc(symbol)}/signals`, undefined, { enabled });

export const useAnalysis = (symbol: string, enabled = true) =>
  useApi<T.AIAnalysis>(["stock", symbol, "analysis"], `/stocks/${enc(symbol)}/analysis`, undefined, { enabled, retry: false });

export function useRegenerateAnalysis(symbol: string) {
  const qc = useQueryClient();
  return useMutation<T.AIAnalysis, ApiError, void>({
    mutationFn: () => api.post<T.AIAnalysis>(`/stocks/${enc(symbol)}/analysis`),
    onSuccess: (data) => qc.setQueryData(["stock", symbol, "analysis"], data),
  });
}

/* --------------------------------------------------------------- tools */

export const usePositionSize = () =>
  useMutation<T.PositionSizeOut, ApiError, T.PositionSizeIn>({ mutationFn: (b) => api.post("/tools/position-size", b) });

export const useCharges = () =>
  useMutation<T.ChargesOut, ApiError, T.ChargesIn>({ mutationFn: (b) => api.post("/tools/charges", b) });

/* ----------------------------------------------------------- portfolio */

export const usePortfolios = () => useListApi<T.Portfolio>(["portfolios", "list"], "/portfolios");

export const useCreatePortfolio = () =>
  useApiMutation<{ name: string; kind: "live" | "paper"; broker?: string | null }, T.Portfolio>(
    (b) => api.post("/portfolios", b),
    [["portfolios"], ["portfolio-dashboard"]],
  );

export const usePortfolio = (id: number | string) =>
  useApi<T.PortfolioDetail>(["portfolios", "one", String(id)], `/portfolios/${enc(String(id))}`);

export const useTransactions = (id: number | string) =>
  useListApi<T.Transaction>(["portfolios", "one", String(id), "transactions"], `/portfolios/${enc(String(id))}/transactions`);

export const useAddTransaction = (id: number | string) =>
  useApiMutation<T.TransactionIn, T.Transaction>(
    (b) => api.post(`/portfolios/${enc(String(id))}/transactions`, b),
    [["portfolios"], ["portfolio-dashboard"], ["portfolio-exits"], ["tax"]],
  );

export const useDeleteTransaction = (id: number | string) =>
  useApiMutation<number, unknown>(
    (tid) => api.del(`/portfolios/${enc(String(id))}/transactions/${tid}`),
    [["portfolios"], ["portfolio-dashboard"], ["portfolio-exits"], ["tax"]],
  );

export const useSetPositionLevels = (id: number | string) =>
  useApiMutation<{ symbol: string; levels: T.PositionLevelsIn }, unknown>(
    ({ symbol, levels }) => api.put(`/portfolios/${enc(String(id))}/positions/${enc(symbol)}`, levels),
    [["portfolios"], ["portfolio-dashboard"], ["portfolio-exits"]],
  );

export const useRealized = (id: number | string, taxYear?: string) =>
  useApi<T.RealizedResponse>(
    ["portfolios", "one", String(id), "realized", taxYear ?? "current"],
    `/portfolios/${enc(String(id))}/realized`,
    { tax_year: taxYear },
  );

export const usePortfolioDashboard = () => useApi<T.PortfolioDashboard>(["portfolio-dashboard"], "/portfolio/dashboard");

export const usePortfolioExits = () => useListApi<T.PortfolioActionItem>(["portfolio-exits"], "/portfolio/exits");

/* ------------------------------------------------------ trades & perf */

export const useTrades = (kind?: string) => useListApi<T.Trade>(["trades", kind ?? "all"], "/trades", { kind });

export const useCreateTrade = () => useApiMutation<T.TradeIn, T.Trade>((b) => api.post("/trades", b), [["trades"], ["performance"]]);

export const useUpdateTrade = () =>
  useApiMutation<{ id: number; body: Partial<T.TradeIn> }, T.Trade>(({ id, body }) => api.put(`/trades/${id}`, body), [["trades"], ["performance"]]);

export const usePerformance = (kind?: string) => useApi<T.PerformanceResponse>(["performance", kind ?? "all"], "/performance", { kind });

/* ----------------------------------------------------------------- tax */

export const useTaxSummary = (taxYear: string) => useApi<T.TaxSummary>(["tax", "summary", taxYear], "/tax/summary", { tax_year: taxYear });

export const useHarvesting = () =>
  useApi<{ candidates?: T.HarvestCandidate[]; label?: string; note?: string; disclaimer?: string }>(["tax", "harvesting"], "/tax/harvesting");

export const useTaxProfile = () => useApi<T.TaxProfile>(["tax", "profile"], "/tax/profile");

export const useSaveTaxProfile = () => useApiMutation<T.TaxProfile, T.TaxProfile>((b) => api.put("/tax/profile", b), [["tax"]]);

export const useTaxRules = (enabled = true) => useApi<unknown>(["tax", "rules"], "/tax/rules", undefined, { enabled });

/* ----------------------------------------------------------- watchlists */

export const useWatchlists = () => useListApi<T.Watchlist>(["watchlists", "list"], "/watchlists");

export const useWatchlist = (id: number | null) =>
  useApi<T.WatchlistDetail>(["watchlists", "one", id], id == null ? null : `/watchlists/${id}`);

export const useCreateWatchlist = () =>
  useApiMutation<{ name: string; kind: string }, T.Watchlist>((b) => api.post("/watchlists", b), [["watchlists"]]);

export const useAddWatchItem = () =>
  useApiMutation<{ id: number; symbol: string }, unknown>(({ id, symbol }) => api.post(`/watchlists/${id}/items`, { symbol }), [["watchlists"]]);

export const useRemoveWatchItem = () =>
  useApiMutation<{ id: number; symbol: string }, unknown>(({ id, symbol }) => api.del(`/watchlists/${id}/items/${enc(symbol)}`), [["watchlists"]]);

/* -------------------------------------------------------------- alerts */

export const useAlerts = () =>
  useQuery<T.AlertRule[], ApiError>({
    queryKey: ["alerts", "rules"],
    queryFn: async ({ signal }) => asList<T.AlertRule>(await api.get<unknown>("/alerts", undefined, signal), "alerts"),
  });

export const useCreateAlert = () =>
  useApiMutation<{ symbol?: string | null; alert_type: string; params: Record<string, unknown>; channels: string[] }, T.AlertRule>(
    (b) => api.post("/alerts", b),
    [["alerts"]],
  );

export const useDeleteAlert = () => useApiMutation<number, unknown>((id) => api.del(`/alerts/${id}`), [["alerts"]]);

export const useAlertEvents = () =>
  useListApi<T.AlertEvent>(["alerts", "events"], "/alerts/events", undefined, { refetchInterval: 120_000 });

export const useMarkAlertRead = () => useApiMutation<number, unknown>((id) => api.post(`/alerts/events/${id}/read`), [["alerts", "events"]]);

/* ---------------------------------------------------------------- news */

export const useNews = (q: { symbol?: string; event_type?: string; limit?: number }) =>
  useListApi<T.NewsItem>(["news", q], "/news", q, { placeholderData: keepPreviousData });

/* ----------------------------------------------------------------- F&O */

export const useFnoOverview = (date?: string) => useApi<T.FnoOverview>(["fno", date ?? "latest"], "/fno/overview", { date });

/* ----------------------------------------------------------- backtests */

export const useBacktests = () =>
  useListApi<T.Backtest>(["backtests", "list"], "/backtests", undefined, {
    refetchInterval: (q) => (q.state.data?.some((b) => b.status === "queued" || b.status === "running") ? 5000 : false),
  });

export const useBacktest = (id: number | null) =>
  useApi<T.BacktestDetail>(["backtests", "one", id], id == null ? null : `/backtests/${id}`, undefined, {
    refetchInterval: (q) => (q.state.data?.status === "queued" || q.state.data?.status === "running" ? 4000 : false),
  });

export const useCreateBacktest = () => useApiMutation<T.BacktestIn, T.Backtest>((b) => api.post("/backtests", b), [["backtests"]]);

/* --------------------------------------------------------------- paper */

export const usePaper = () => useApi<T.PaperResponse>(["paper"], "/paper");

export const usePlacePaperOrder = () =>
  useApiMutation<T.PaperOrderIn, T.PaperOrder>((b) => api.post("/paper/orders", b), [["paper"], ["performance"]]);

export const useCancelPaperOrder = () => useApiMutation<number, unknown>((id) => api.del(`/paper/orders/${id}`), [["paper"]]);

export const useSetFollowModel = () =>
  useApiMutation<boolean, unknown>((follow_model) => api.put("/paper/settings", { follow_model }), [["paper"]]);

/* ----------------------------------------------------- settings & admin */

export const useSettings = () => useApi<T.SettingsResponse & T.SettingsMap>(["settings"], "/settings");

export const useSaveSetting = () =>
  useApiMutation<{ key: string; value: unknown }, unknown>(({ key, value }) => api.put(`/settings/${enc(key)}`, value), [["settings"]]);

export const useSystemHealth = (enabled = true) =>
  useApi<T.SystemHealth>(["admin", "health"], "/admin/system-health", undefined, { enabled, refetchInterval: 60_000 });

export const useDataSources = (enabled = true) =>
  useListApi<T.DataSource>(["admin", "data-sources"], "/admin/data-sources", undefined, { enabled });

/** PUT /admin/data-sources/{key} — one provider at a time. */
export const useSaveDataSources = () =>
  useApiMutation<{ key: string; body: Record<string, unknown> }, unknown>(
    ({ key, body }) => api.put(`/admin/data-sources/${enc(key)}`, body),
    [["admin", "data-sources"], ["admin", "health"]],
  );

export const useAdminUsers = (enabled = true) => useListApi<T.AdminUser>(["admin", "users"], "/admin/users", undefined, { enabled });

export const useCreateUser = () =>
  useApiMutation<{ email: string; password: string; full_name?: string; role: string }, T.AdminUser>(
    (b) => api.post("/admin/users", b),
    [["admin", "users"]],
  );

export const useRunJob = () =>
  useApiMutation<{ job: T.JobName; params?: Record<string, unknown> }, T.JobResponse>(
    ({ job, params }) => api.post(`/admin/jobs/${job}`, params ?? {}),
    [["admin", "health"]],
  );

export const useAuditLogs = (enabled = true) => useListApi<T.AuditLog>(["admin", "audit"], "/admin/audit-logs", { limit: 100 }, { enabled });

export const useAdminCharges = (enabled = true) => useApi<unknown>(["admin", "charges"], "/admin/charges", undefined, { enabled });

export const useSimpleView = () => useApi<T.SimpleView>(["simple"], "/simple");
