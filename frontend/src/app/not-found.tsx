import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-muted">404</p>
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link href="/dashboard" className="text-sm font-medium text-accent hover:underline">
        Back to dashboard
      </Link>
    </main>
  );
}
