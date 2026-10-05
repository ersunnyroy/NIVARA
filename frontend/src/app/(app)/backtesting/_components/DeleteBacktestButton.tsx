"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui";
import { useDeleteBacktest } from "./useDeleteBacktest";

/** Two-step delete (click → confirm). Running jobs cannot be deleted from here. */
export function DeleteBacktestButton({ id, disabled, onDeleted }: { id: number; disabled?: boolean; onDeleted: () => void }) {
  const del = useDeleteBacktest();
  const [confirm, setConfirm] = useState(false);
  if (!confirm)
    return (
      <Button
        size="xs"
        variant="ghost"
        disabled={disabled}
        title={disabled ? "Wait for the run to finish before deleting" : undefined}
        icon={<Trash2 className="size-3" aria-hidden />}
        onClick={() => setConfirm(true)}
      >
        Delete
      </Button>
    );
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-down">{del.error ? `Delete failed: ${del.error.message}` : "Delete permanently?"}</span>
      <Button size="xs" variant="danger" loading={del.isPending} onClick={() => del.mutate(id, { onSuccess: onDeleted })}>
        Yes, delete
      </Button>
      <Button size="xs" variant="ghost" onClick={() => setConfirm(false)}>
        Keep
      </Button>
    </span>
  );
}
