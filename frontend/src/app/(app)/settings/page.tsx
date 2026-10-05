"use client";

import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useMe, useSaveSetting, useSettings } from "@/lib/hooks";
import { titleCase } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Card, CardBody, CardHeader, ErrorState, SkeletonCard, TabPanel, Tabs, type TabItem } from "@/components/ui";
import { AuditLog, TaxRulesCharges } from "./_components/AuditRules";
import { GenericSettingEditor, saveNote, WeightsEditor } from "./_components/ConfigEditors";
import { DataProviders } from "./_components/DataProviders";
import { Jobs } from "./_components/Jobs";
import { AdminOnly, isPlainObject } from "./_components/shared";
import { SystemHealth } from "./_components/SystemHealth";
import { Users } from "./_components/Users";

/**
 * GET /settings returns `{ config, defaults, editable, versions }` (not a bare SettingsMap as typed in
 * `@/lib/types`); a bare map is still accepted defensively.
 */
interface SettingsEnvelope {
  config: Record<string, unknown>;
  defaults: Record<string, unknown> | null;
  editable: boolean | null;
  versions: Record<string, number>;
}

function parseSettings(raw: unknown): SettingsEnvelope {
  if (isPlainObject(raw) && isPlainObject(raw.config)) {
    return {
      config: raw.config,
      defaults: isPlainObject(raw.defaults) ? raw.defaults : null,
      editable: typeof raw.editable === "boolean" ? raw.editable : null,
      versions: isPlainObject(raw.versions) ? (raw.versions as Record<string, number>) : {},
    };
  }
  return { config: isPlainObject(raw) ? raw : {}, defaults: null, editable: null, versions: {} };
}

const CONFIG_SECTIONS: { key: string; label: string; description: string }[] = [
  { key: "risk_limits", label: "Risk limits", description: "Capital, risk per trade, reward:risk minimums and concentration limits used for sizing and setup rejection." },
  { key: "exclusions", label: "Exclusions", description: "Universe filters: minimum price, liquidity, history and surveillance exclusions." },
  { key: "regime", label: "Regime", description: "Market-regime component weights, score thresholds, and exposure / max-positions per regime." },
  { key: "scanner", label: "Scanner", description: "How many ideas to publish, per-sector cap and minimum score." },
  { key: "market_hours", label: "Market hours", description: "NSE session times (IST) used for status and scheduling." },
  { key: "ai", label: "AI", description: "AI explanations (requires an API key configured on the server)." },
  { key: "notifications", label: "Notifications", description: "Default alert delivery channels." },
];

const ADMIN_TABS: { key: string; label: string }[] = [
  { key: "providers", label: "Data providers" },
  { key: "health", label: "System health" },
  { key: "users", label: "Users" },
  { key: "jobs", label: "Jobs" },
  { key: "audit", label: "Audit log" },
  { key: "rules", label: "Tax rules & charges" },
];

const ID_BASE = "settings";

function ConfigPanel({
  tab,
  env,
  editable,
}: {
  tab: string;
  env: SettingsEnvelope;
  editable: boolean;
}) {
  // Owned here, not in the editors: they remount (new `key`) when the saved value is refetched.
  const save = useSaveSetting();
  const note = saveNote(save.data);
  const banner = save.isSuccess ? (
    <p role="status" className="mb-3 rounded-lg bg-up-soft px-3 py-2 text-xs text-up">
      Saved.{note ? ` ${note}` : ""}
    </p>
  ) : null;
  if (tab === "weights") {
    const value = isPlainObject(env.config.scoring_weights) ? env.config.scoring_weights : {};
    const defaults = isPlainObject(env.defaults?.scoring_weights) ? (env.defaults.scoring_weights as Record<string, unknown>) : null;
    return (
      <Card>
        <CardHeader
          icon={<SlidersHorizontal className="size-4" />}
          title="Scoring weights"
          subtitle="Relative importance of each component in the 0–100 opportunity score."
        />
        <CardBody>
          {banner}
          <WeightsEditor
            key={JSON.stringify(value)}
            initial={value}
            defaults={defaults}
            editable={editable}
            version={env.versions.scoring_weights ?? null}
            save={save}
          />
        </CardBody>
      </Card>
    );
  }
  const key = tab.startsWith("cfg:") ? tab.slice(4) : tab;
  const sec = CONFIG_SECTIONS.find((s) => s.key === key);
  const value = env.config[key];
  return (
    <Card>
      <CardHeader icon={<SlidersHorizontal className="size-4" />} title={sec?.label ?? titleCase(key)} subtitle={<code className="text-[11px]">{key}</code>} />
      <CardBody>
        {banner}
        {value === undefined ? (
          <p className="text-sm text-muted">This setting is not reported by the server.</p>
        ) : (
          <GenericSettingEditor
            key={JSON.stringify(value)}
            settingKey={key}
            initial={value}
            defaults={env.defaults?.[key]}
            editable={editable}
            version={env.versions[key] ?? null}
            description={sec?.description}
            save={save}
          />
        )}
      </CardBody>
    </Card>
  );
}

function AdminPanel({ tab, isAdmin, meLoading, goto }: { tab: string; isAdmin: boolean; meLoading: boolean; goto: (k: string) => void }) {
  const label = ADMIN_TABS.find((t) => t.key === tab)?.label;
  if (meLoading) return <SkeletonCard lines={4} />;
  if (!isAdmin) return <AdminOnly what={label} />;
  switch (tab) {
    case "providers":
      return <DataProviders />;
    case "health":
      return <SystemHealth gotoJobs={() => goto("jobs")} />;
    case "users":
      return <Users />;
    case "jobs":
      return <Jobs />;
    case "audit":
      return <AuditLog />;
    case "rules":
      return <TaxRulesCharges />;
    default:
      return null;
  }
}

export default function SettingsPage() {
  const me = useMe();
  const settings = useSettings();
  const [tab, setTab] = useState<string>("weights");

  const isAdmin = me.data?.role === "admin";
  const env = settings.data ? parseSettings(settings.data) : null;
  const editable = isAdmin && env?.editable !== false;

  const known = new Set(["scoring_weights", ...CONFIG_SECTIONS.map((s) => s.key)]);
  const extraKeys = env ? Object.keys(env.config).filter((k) => !known.has(k)) : [];
  const adminBadge = (
    <Badge tone="outline" size="xs">
      admin
    </Badge>
  );

  const tabs: TabItem<string>[] = [
    { key: "weights", label: "Scoring weights" },
    ...CONFIG_SECTIONS.map((s) => ({ key: s.key, label: s.label })),
    ...extraKeys.map((k) => ({ key: `cfg:${k}`, label: titleCase(k) })),
    ...ADMIN_TABS.map((t) => ({ key: t.key, label: t.label, badge: adminBadge })),
  ];
  const isAdminTab = ADMIN_TABS.some((t) => t.key === tab);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Settings"
        description={
          <>
            Model configuration{isAdmin ? ", data providers, system health, users and jobs" : ""}.{" "}
            {me.isSuccess && !isAdmin ? <span className="font-medium text-warn">Read-only — only administrators can change settings.</span> : null}
          </>
        }
      />
      <Tabs label="Settings sections" tabs={tabs} value={tab} onChange={setTab} idBase={ID_BASE} />
      <TabPanel idBase={ID_BASE} k={tab}>
        {isAdminTab ? (
          <AdminPanel tab={tab} isAdmin={isAdmin} meLoading={me.isPending} goto={setTab} />
        ) : settings.isPending || me.isPending ? (
          <SkeletonCard lines={6} />
        ) : settings.isError ? (
          <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
        ) : env ? (
          <>
            {!editable ? (
              <div className="mb-3">
                <AdminOnly what="Editing settings" />
              </div>
            ) : null}
            <ConfigPanel key={tab} tab={tab} env={env} editable={editable} />
          </>
        ) : null}
      </TabPanel>
    </div>
  );
}
