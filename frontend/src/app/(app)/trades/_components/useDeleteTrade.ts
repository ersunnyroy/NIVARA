"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ApiError } from "@/lib/api";

/** DELETE /trades/{id} — not in shared hooks yet. */
export function useDeleteTrade() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, number>({
    mutationFn: (id) => api.del(`/trades/${id}`),
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ["trades"] }), qc.invalidateQueries({ queryKey: ["performance"] })]);
    },
  });
}
