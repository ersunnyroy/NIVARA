"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LogIn, UserPlus } from "lucide-react";
import { useAuthStatus, useLogin, useRegister } from "@/lib/hooks";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button, Disclaimer, ErrorState, Field, Input, Skeleton } from "@/components/ui";

function safeNext(v: string | null): string {
  if (!v || !v.startsWith("/") || v.startsWith("//") || v.startsWith("/login")) return "/dashboard";
  return v;
}

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const status = useAuthStatus();
  const login = useLogin();
  const register = useRegister();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localErr, setLocalErr] = useState<string | null>(null);

  const registering = status.data?.registration_open === true;
  const mut = registering ? register : login;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalErr(null);
    if (registering) {
      if (password !== confirm) {
        setLocalErr("Passwords do not match.");
        return;
      }
      register.mutate({ email, password, full_name: fullName }, { onSuccess: () => router.replace(next) });
    } else {
      login.mutate({ email, password }, { onSuccess: () => router.replace(next) });
    }
  }

  return (
    <div className="w-full max-w-sm">
      <div className="mb-6 flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-accent text-lg font-black text-accent-fg">N</span>
        <div>
          <h1 className="text-lg font-bold tracking-[0.2em]">NIVARA</h1>
          <p className="text-xs text-muted">Indian equity research · trading analysis · portfolio</p>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-surface p-6 shadow-card">
        {status.isPending ? (
          <div className="space-y-3" role="status" aria-label="Loading">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : (
          <>
            <h2 className="text-base font-semibold">{registering ? "Create the first (admin) account" : "Sign in"}</h2>
            <p className="mt-1 text-xs text-muted">
              {registering
                ? "No users exist yet. The first account becomes the administrator; further users are created from Settings."
                : "Use the account your administrator created for you."}
            </p>
            {status.isError ? (
              <ErrorState className="mt-3" error={status.error} title="Cannot reach the API" onRetry={() => status.refetch()} />
            ) : null}
            <form onSubmit={submit} className="mt-5 flex flex-col gap-3" noValidate={false}>
              {registering ? (
                <Field label="Full name">
                  {(id) => <Input id={id} value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />}
                </Field>
              ) : null}
              <Field label="Email" required>
                {(id) => (
                  <Input id={id} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
                )}
              </Field>
              <Field label="Password" required hint={registering ? "At least 10 characters, mixed case and a digit." : undefined}>
                {(id) => (
                  <Input
                    id={id}
                    type="password"
                    required
                    minLength={registering ? 10 : 1}
                    autoComplete={registering ? "new-password" : "current-password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>
              {registering ? (
                <Field label="Confirm password" required>
                  {(id) => (
                    <Input id={id} type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
                  )}
                </Field>
              ) : null}
              {localErr || mut.error ? (
                <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
                  {localErr ?? mut.error?.message}
                </p>
              ) : null}
              <Button
                type="submit"
                variant="primary"
                loading={mut.isPending}
                icon={registering ? <UserPlus className="size-4" aria-hidden /> : <LogIn className="size-4" aria-hidden />}
                className="mt-1 w-full"
              >
                {registering ? "Create admin account" : "Sign in"}
              </Button>
            </form>
          </>
        )}
      </div>
      <Disclaimer className="mt-4" />
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center p-4">
      <div className="absolute right-3 top-3">
        <ThemeToggle />
      </div>
      <Suspense fallback={<Skeleton className="h-96 w-full max-w-sm" />}>
        <LoginInner />
      </Suspense>
    </main>
  );
}
