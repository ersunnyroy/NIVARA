"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UserMinus, UserPlus, Users as UsersIcon } from "lucide-react";
import { api, type ApiError } from "@/lib/api";
import { useAdminUsers, useCreateUser, useMe } from "@/lib/hooks";
import { dateTimeIST } from "@/lib/format";
import { Badge, Button, Card, CardBody, CardHeader, Dialog, EmptyState, Field, Input, NAValue, QueryState, Select, SkeletonRows, TableWrap, Td, Th, THead, Tr } from "@/components/ui";
import type { AdminUser } from "@/lib/types";

/** POST /admin/users/{uid}/deactivate has no shared hook yet. */
function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, number>({
    mutationFn: (uid) => api.post(`/admin/users/${uid}/deactivate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}

function CreateUserForm() {
  const create = useCreateUser();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [done, setDone] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setDone(null);
    create.mutate(
      { email: email.trim(), full_name: fullName.trim() || undefined, password, role },
      {
        onSuccess: (u) => {
          setDone(u?.email ?? email.trim());
          setEmail("");
          setFullName("");
          setPassword("");
          setRole("user");
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Email" required>
          {(id) => <Input id={id} type="email" required autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <Field label="Full name">
          {(id) => <Input id={id} autoComplete="off" value={fullName} onChange={(e) => setFullName(e.target.value)} />}
        </Field>
        <Field label="Initial password" required hint="At least 10 characters, mixed case and a digit. Share it securely.">
          {(id) => <Input id={id} type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
        </Field>
        <Field label="Role">
          {(id) => (
            <Select id={id} value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </Select>
          )}
        </Field>
      </div>
      {create.error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {create.error.message}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="rounded-lg bg-up-soft px-3 py-2 text-xs text-up">
          Created user {done}.
        </p>
      ) : null}
      <Button type="submit" variant="primary" loading={create.isPending} icon={<UserPlus className="size-4" aria-hidden />}>
        Create user
      </Button>
    </form>
  );
}

export function Users() {
  const q = useAdminUsers(true);
  const me = useMe();
  const deact = useDeactivateUser();
  const [confirm, setConfirm] = useState<AdminUser | null>(null);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader icon={<UsersIcon className="size-4" />} title="Users" />
        <QueryState query={q} skeleton={<div className="p-4"><SkeletonRows rows={4} /></div>} className="m-4">
          {(users) =>
            users.length === 0 ? (
              <EmptyState compact title="No users">Create the first additional user below.</EmptyState>
            ) : (
              <TableWrap label="Users">
                <THead>
                  <tr>
                    <Th>Email</Th>
                    <Th>Name</Th>
                    <Th>Role</Th>
                    <Th>Status</Th>
                    <Th>Created</Th>
                    <Th>Last login</Th>
                    <Th align="right">
                      <span className="sr-only">Actions</span>
                    </Th>
                  </tr>
                </THead>
                <tbody>
                  {users.map((u) => (
                    <Tr key={u.id}>
                      <Td className="font-medium">{u.email}</Td>
                      <Td>{u.full_name ?? <NAValue />}</Td>
                      <Td>
                        <Badge tone={u.role === "admin" ? "violet" : "neutral"}>{u.role}</Badge>
                      </Td>
                      <Td>{u.is_active === false ? <Badge tone="down">Inactive</Badge> : u.is_active ? <Badge tone="up">Active</Badge> : <NAValue />}</Td>
                      <Td className="whitespace-nowrap text-xs">{u.created_at ? dateTimeIST(u.created_at) : <NAValue />}</Td>
                      <Td className="whitespace-nowrap text-xs">{u.last_login_at ? dateTimeIST(u.last_login_at) : <span className="text-muted">Never</span>}</Td>
                      <Td align="right">
                        {u.is_active !== false && u.id !== me.data?.id ? (
                          <Button size="xs" variant="ghost" icon={<UserMinus className="size-3.5" aria-hidden />} onClick={() => setConfirm(u)} aria-label={`Deactivate ${u.email}`}>
                            Deactivate
                          </Button>
                        ) : null}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </TableWrap>
            )
          }
        </QueryState>
      </Card>
      <Card>
        <CardHeader icon={<UserPlus className="size-4" />} title="Create user" subtitle="Public registration is closed after the first admin; new accounts are created here." />
        <CardBody>
          <CreateUserForm />
        </CardBody>
      </Card>
      <Dialog
        open={confirm !== null}
        onClose={() => {
          setConfirm(null);
          deact.reset();
        }}
        title="Deactivate user?"
        description="The user will no longer be able to sign in. Their data is kept."
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deact.isPending} onClick={() => confirm && deact.mutate(confirm.id, { onSuccess: () => setConfirm(null) })}>
              Deactivate
            </Button>
          </>
        }
      >
        <p className="text-sm">{confirm?.email}</p>
        {deact.error ? (
          <p role="alert" className="mt-2 rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
            {deact.error.message}
          </p>
        ) : null}
      </Dialog>
    </div>
  );
}
