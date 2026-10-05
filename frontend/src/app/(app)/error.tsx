"use client";

import { ErrorState } from "@/components/ui";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="p-4">
      <ErrorState title="This page crashed" error={error} onRetry={reset} />
    </div>
  );
}
