"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (count, err) => {
              // Don't hammer the API for client errors or "no data yet".
              if (err instanceof ApiError && (err.status === 0 || (err.status >= 400 && err.status < 500) || err.status === 503)) {
                return err.status === 0 && count < 1;
              }
              return count < 2;
            },
          },
          mutations: { retry: false },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
