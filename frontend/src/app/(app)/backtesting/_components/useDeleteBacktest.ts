"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ApiError } from "@/lib/api";

/** DELETE /backtests/{id} — not in shared hooks yet. */
export function useDeleteBacktest() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, number>({
    mutationFn: (id) => api.del(`/backtests/${id}`),
    onSuccess: async (_d, id) => {
      qc.removeQueries({ queryKey: ["backtests", "one", id] });
      await Promise.all([qc.invalidateQueries({ queryKey: ["backtests", "list"] }), qc.invalidateQueries({ queryKey: ["performance"] })]);
    },
  });
}
