"use client";

import { FileClock, Landmark, Receipt } from "lucide-react";
import { useAdminCharges, useAuditLogs, useTaxRules } from "@/lib/hooks";
import { dateTimeIST } from "@/lib/format";
import type { AuditLog as AuditLogT } from "@/lib/types";
import { Card, CardHeader, EmptyState, NAValue, QueryState, SkeletonRows, TableWrap, Td, Th, THead, Tr } from "@/components/ui";
import { isPlainObject, JsonView } from "./shared";

/** Backend row(AuditLog) carries `data` (not `details`) and `entity`/`entity_id`. */
type AuditX = AuditLogT & { data?: Record<string, unknown> | null };

const skeleton = (
  <div className="p-4">
    <SkeletonRows rows={5} />
  </div>
);

export function AuditLog() {
  const q = useAuditLogs(true);
  return (
    <Card>
      <CardHeader icon={<FileClock className="size-4" />} title="Audit log" subtitle="Latest 100 administrative and security-relevant actions." />
      <QueryState query={q} skeleton={skeleton} className="m-4">
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState compact title="No audit entries yet">Settings changes, user creation and job triggers are recorded here.</EmptyState>
          ) : (
            <TableWrap label="Audit log">
              <THead>
                <tr>
                  <Th>When</Th>
                  <Th>User</Th>
                  <Th>Action</Th>
                  <Th>Entity</Th>
                  <Th>IP</Th>
                  <Th>Details</Th>
                </tr>
              </THead>
              <tbody>
                {(rows as AuditX[]).map((a) => {
                  const when = a.created_at ?? a.at;
                  const det = a.details ?? a.data;
                  const entity = a.entity ?? a.entity_type;
                  return (
                    <Tr key={a.id}>
                      <Td className="whitespace-nowrap text-xs">{when ? dateTimeIST(when) : <NAValue />}</Td>
                      <Td className="text-xs">{a.user_email ?? (a.user_id != null ? `#${a.user_id}` : <span className="text-muted">system</span>)}</Td>
                      <Td>
                        <code className="text-xs">{a.action}</code>
                      </Td>
                      <Td className="text-xs">
                        {entity ?? <span className="text-muted">—</span>}
                        {a.entity_id != null ? <span className="text-muted"> · {String(a.entity_id)}</span> : null}
                      </Td>
                      <Td className="whitespace-nowrap text-xs">{a.ip ?? <span className="text-muted">—</span>}</Td>
                      <Td className="max-w-96 text-xs">
                        {isPlainObject(det) && Object.keys(det).length ? (
                          <details>
                            <summary className="cursor-pointer truncate text-muted">{JSON.stringify(det).slice(0, 80)}</summary>
                            <pre className="scroll-thin mt-1 max-h-56 overflow-auto rounded bg-surface-2 p-2 text-[10px]">{JSON.stringify(det, null, 2)}</pre>
                          </details>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </TableWrap>
          )
        }
      </QueryState>
    </Card>
  );
}

export function TaxRulesCharges() {
  const rules = useTaxRules(true);
  const charges = useAdminCharges(true);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          icon={<Landmark className="size-4" />}
          title="Tax rules"
          subtitle="Read-only. Dated and versioned rules used by the tax estimator — review whenever tax law changes."
        />
        <div className="py-3">
          <QueryState query={rules} skeleton={skeleton} className="mx-4">
            {(d) =>
              (isPlainObject(d) && Array.isArray(d.rules) && d.rules.length === 0) || (Array.isArray(d) && d.length === 0) ? (
                <EmptyState compact title="No tax rules loaded">Run the “Seed reference data” job to load the default rules.</EmptyState>
              ) : (
                // charges are shown from /admin/charges below
                <JsonView data={d} label="Tax rules" omit={["charges"]} />
              )
            }
          </QueryState>
        </div>
      </Card>
      <Card>
        <CardHeader icon={<Receipt className="size-4" />} title="Charge schedules" subtitle="Read-only. Brokerage, STT, exchange, SEBI, stamp duty and GST rates by effective date." />
        <div className="py-3">
          <QueryState query={charges} skeleton={skeleton} className="mx-4">
            {(d) =>
              Array.isArray(d) && d.length === 0 ? (
                <EmptyState compact title="No charge schedules loaded">Run the “Seed reference data” job to load the default schedules.</EmptyState>
              ) : (
                <JsonView data={d} label="Charge schedules" />
              )
            }
          </QueryState>
        </div>
      </Card>
    </div>
  );
}
