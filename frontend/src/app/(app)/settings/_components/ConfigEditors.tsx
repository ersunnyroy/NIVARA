"use client";

import { useState } from "react";
import { AlertTriangle, RotateCcw, Save } from "lucide-react";
import { useSaveSetting } from "@/lib/hooks";
import { num, titleCase } from "@/lib/format";
import { Badge, Button, Checkbox, cn, Field, Input, TableWrap, Td, Textarea, Th, THead, Tr } from "@/components/ui";
import { isPlainObject } from "./shared";

/* ------------------------------------------------------------- save bar */

/**
 * The save mutation is owned by the (stable) parent panel: editors remount when the saved value is refetched,
 * so success/error state must outlive them.
 */
export type SaveMutation = ReturnType<typeof useSaveSetting>;

export function saveNote(data: unknown): string | null {
  if (isPlainObject(data) && typeof data.note === "string") return data.note;
  return null;
}

function SaveBar({
  editable,
  pending,
  disabled,
  error,
  onSave,
  onResetLoaded,
  onLoadDefaults,
  version,
}: {
  editable: boolean;
  pending: boolean;
  disabled?: boolean;
  error?: string | null;
  onSave: () => void;
  onResetLoaded: () => void;
  onLoadDefaults?: () => void;
  version?: number | null;
}) {
  return (
    <div className="space-y-2 border-t border-border pt-3">
      {error ? (
        <p role="alert" className="rounded-lg bg-down-soft px-3 py-2 text-xs text-down">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] text-muted">{version != null ? `Stored version ${version}` : "Using built-in defaults (never saved)"}</span>
        {editable ? (
          <div className="flex flex-wrap gap-2">
            {onLoadDefaults ? (
              <Button size="sm" variant="ghost" onClick={onLoadDefaults}>
                Load defaults
              </Button>
            ) : null}
            <Button size="sm" variant="outline" onClick={onResetLoaded} icon={<RotateCcw className="size-3.5" aria-hidden />}>
              Discard changes
            </Button>
            <Button size="sm" variant="primary" onClick={onSave} loading={pending} disabled={disabled} icon={<Save className="size-3.5" aria-hidden />}>
              Save
            </Button>
          </div>
        ) : (
          <Badge tone="outline">Admin only — read-only</Badge>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------- scoring weights */

export function WeightsEditor({
  initial,
  defaults,
  editable,
  version,
  save,
}: {
  initial: Record<string, unknown>;
  defaults?: Record<string, unknown> | null;
  editable: boolean;
  version?: number | null;
  save: SaveMutation;
}) {
  const keys = Array.from(new Set([...Object.keys(defaults ?? {}), ...Object.keys(initial)]));
  const toText = (src: Record<string, unknown>) => Object.fromEntries(keys.map((k) => [k, typeof src[k] === "number" ? String(src[k]) : String(src[k] ?? "")]));
  const [text, setText] = useState<Record<string, string>>(() => toText(initial));

  const parsed = keys.map((k) => {
    const raw = (text[k] ?? "").trim();
    const n = raw === "" ? Number.NaN : Number(raw);
    return { k, n, ok: Number.isFinite(n) && n >= 0 };
  });
  const invalid = parsed.filter((p) => !p.ok);
  const sum = parsed.reduce((a, p) => a + (p.ok ? p.n : 0), 0);
  const off = Math.abs(sum - 100) > 0.005;

  function doSave() {
    if (invalid.length || sum <= 0) return;
    save.mutate({ key: "scoring_weights", value: Object.fromEntries(parsed.map((p) => [p.k, p.n])) });
  }

  return (
    <div className="space-y-4">
      <fieldset disabled={!editable} className="min-w-0">
        <legend className="sr-only">Scoring weights</legend>
        <TableWrap label="Scoring weights">
          <THead>
            <tr>
              <Th>Component</Th>
              <Th align="right">Weight</Th>
              <Th align="right">Share of total</Th>
              <Th align="right">Default</Th>
            </tr>
          </THead>
          <tbody>
            {parsed.map((p) => {
              const id = `w-${p.k}`;
              return (
                <Tr key={p.k}>
                  <Td>
                    <label htmlFor={id} className="font-medium">
                      {titleCase(p.k)}
                    </label>
                    <code className="ml-2 text-[10px] text-subtle">{p.k}</code>
                  </Td>
                  <Td align="right">
                    <Input
                      id={id}
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="any"
                      className={cn("ml-auto w-24 text-right", !p.ok && "border-down")}
                      aria-invalid={!p.ok || undefined}
                      value={text[p.k] ?? ""}
                      onChange={(e) => setText((s) => ({ ...s, [p.k]: e.target.value }))}
                    />
                  </Td>
                  <Td align="right" className="text-muted">
                    {p.ok && sum > 0 ? `${num((p.n / sum) * 100, 1, 1)}%` : "n/a"}
                  </Td>
                  <Td align="right" className="text-muted">
                    {typeof defaults?.[p.k] === "number" ? num(defaults[p.k], 2, 0) : "n/a"}
                  </Td>
                </Tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="font-semibold">
              <Td>Total</Td>
              <Td align="right" className={off ? "text-warn" : "text-up"} aria-live="polite">
                {num(sum, 2, 0)}
              </Td>
              <Td align="right" className="text-muted">
                100%
              </Td>
              <Td />
            </tr>
          </tfoot>
        </TableWrap>
      </fieldset>
      {invalid.length ? (
        <p role="alert" className="text-xs text-down">
          Every weight must be a number ≥ 0 ({invalid.map((p) => titleCase(p.k)).join(", ")}).
        </p>
      ) : off ? (
        <p role="status" className="flex items-start gap-2 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-warn">
          <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
          <span>
            Weights sum to <span className="num font-semibold">{num(sum, 2, 0)}</span>, not 100. The server rescales them proportionally to 100 on save (see
            “Share of total”). Adjust them if you want exact values.
          </span>
        </p>
      ) : null}
      <p className="text-[11px] text-muted">New weights apply to future scans only; past recommendations keep the weights recorded with them.</p>
      <SaveBar
        editable={editable}
        pending={save.isPending}
        disabled={invalid.length > 0 || sum <= 0}
        error={save.error?.message}
        onSave={doSave}
        onResetLoaded={() => {
          setText(toText(initial));
          save.reset();
        }}
        onLoadDefaults={defaults ? () => setText(toText(defaults)) : undefined}
        version={version}
      />
    </div>
  );
}

/* ------------------------------------------------------- generic editors */

type Validity = (path: string, error: string | null) => void;

function NumberLeaf({ id, value, onChange, onValidity, path }: { id: string; value: number; onChange: (v: number) => void; onValidity: Validity; path: string }) {
  const [text, setText] = useState(() => String(value));
  const bad = text.trim() === "" || !Number.isFinite(Number(text));
  return (
    <Input
      id={id}
      type="number"
      inputMode="decimal"
      step="any"
      value={text}
      aria-invalid={bad || undefined}
      className={cn(bad && "border-down")}
      onChange={(e) => {
        const t = e.target.value;
        setText(t);
        const n = Number(t);
        if (t.trim() !== "" && Number.isFinite(n)) {
          onValidity(path, null);
          onChange(n);
        } else onValidity(path, "must be a number");
      }}
    />
  );
}

function ArrayLeaf({ id, value, onChange, onValidity, path }: { id: string; value: unknown[]; onChange: (v: unknown[]) => void; onValidity: Validity; path: string }) {
  const numeric = value.length > 0 && value.every((x) => typeof x === "number");
  const [text, setText] = useState(() => value.map(String).join(", "));
  return (
    <Input
      id={id}
      value={text}
      onChange={(e) => {
        const t = e.target.value;
        setText(t);
        const parts = t
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        if (numeric) {
          const nums = parts.map(Number);
          if (nums.some((n) => !Number.isFinite(n))) {
            onValidity(path, "must be comma-separated numbers");
            return;
          }
          onValidity(path, null);
          onChange(nums);
        } else {
          onValidity(path, null);
          onChange(parts);
        }
      }}
    />
  );
}

function JsonLeaf({ id, value, onChange, onValidity, path }: { id: string; value: unknown; onChange: (v: unknown) => void; onValidity: Validity; path: string }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      <Textarea
        id={id}
        rows={Math.min(12, Math.max(3, text.split("\n").length))}
        className="font-mono text-xs"
        value={text}
        aria-invalid={!!err || undefined}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          try {
            const v = JSON.parse(t) as unknown;
            setErr(null);
            onValidity(path, null);
            onChange(v);
          } catch {
            setErr("Invalid JSON");
            onValidity(path, "is not valid JSON");
          }
        }}
      />
      {err ? <span className="text-xs text-down">{err}</span> : null}
    </>
  );
}

function ValueEditor({
  name,
  path,
  value,
  onChange,
  onValidity,
  depth,
}: {
  name: string;
  path: string;
  value: unknown;
  onChange: (v: unknown) => void;
  onValidity: Validity;
  depth: number;
}) {
  const label = (
    <>
      {titleCase(name)} <code className="ml-1 text-[10px] font-normal text-subtle">{name}</code>
    </>
  );

  if (isPlainObject(value)) {
    return (
      <fieldset className={cn("min-w-0 rounded-lg border border-border p-3", depth > 0 && "bg-surface-2/30")}>
        <legend className="px-1 text-xs font-semibold text-fg">{label}</legend>
        <ObjectFields path={path} value={value} onChange={onChange} onValidity={onValidity} depth={depth + 1} />
      </fieldset>
    );
  }
  if (typeof value === "boolean") {
    return (
      <div className="flex min-h-9 items-end pb-1">
        <Checkbox label={label} checked={value} onChange={(v) => onChange(v)} />
      </div>
    );
  }
  if (typeof value === "number") {
    return <Field label={label}>{(id) => <NumberLeaf id={id} path={path} value={value} onChange={onChange} onValidity={onValidity} />}</Field>;
  }
  if (typeof value === "string") {
    const isTime = /^\d{2}:\d{2}$/.test(value);
    return (
      <Field label={label} hint={isTime ? "IST, 24-hour" : undefined}>
        {(id) => <Input id={id} type={isTime ? "time" : "text"} value={value} onChange={(e) => onChange(e.target.value)} />}
      </Field>
    );
  }
  if (Array.isArray(value) && value.every((x) => typeof x === "string" || typeof x === "number")) {
    return (
      <Field label={label} hint="Comma-separated list">
        {(id) => <ArrayLeaf id={id} path={path} value={value} onChange={onChange} onValidity={onValidity} />}
      </Field>
    );
  }
  return (
    <Field label={label} hint="Complex value — edit as JSON" className="sm:col-span-2">
      {(id) => <JsonLeaf id={id} path={path} value={value} onChange={onChange} onValidity={onValidity} />}
    </Field>
  );
}

function ObjectFields({
  path,
  value,
  onChange,
  onValidity,
  depth,
}: {
  path: string;
  value: Record<string, unknown>;
  onChange: (v: unknown) => void;
  onValidity: Validity;
  depth: number;
}) {
  const entries = Object.entries(value);
  if (!entries.length) return <p className="text-xs text-muted">No fields.</p>;
  const scalars = entries.filter(([, v]) => !isPlainObject(v));
  const objects = entries.filter(([, v]) => isPlainObject(v));
  const child = (k: string, v: unknown) => (
    <ValueEditor
      key={k}
      name={k}
      path={path ? `${path}.${k}` : k}
      value={v}
      depth={depth}
      onValidity={onValidity}
      onChange={(nv) => onChange({ ...value, [k]: nv })}
    />
  );
  return (
    <div className="space-y-3">
      {scalars.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{scalars.map(([k, v]) => child(k, v))}</div> : null}
      {objects.map(([k, v]) => child(k, v))}
    </div>
  );
}

/** Generic editor for one settings key; renders numbers/booleans/strings/arrays/nested objects by type. */
export function GenericSettingEditor({
  settingKey,
  initial,
  defaults,
  editable,
  version,
  description,
  save,
}: {
  settingKey: string;
  initial: unknown;
  defaults?: unknown;
  editable: boolean;
  version?: number | null;
  description?: string;
  save: SaveMutation;
}) {
  const [draft, setDraft] = useState<unknown>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [gen, setGen] = useState(0);

  const onValidity: Validity = (path, error) =>
    setErrors((s) => {
      if (!error && !(path in s)) return s;
      const next = { ...s };
      if (error) next[path] = error;
      else delete next[path];
      return next;
    });

  function reset(to: unknown) {
    setDraft(to);
    setErrors({});
    setGen((g) => g + 1);
    save.reset();
  }

  const errList = Object.entries(errors);
  const isObj = isPlainObject(draft);

  return (
    <div className="space-y-4">
      {description ? <p className="text-xs text-muted">{description}</p> : null}
      <fieldset disabled={!editable} className="min-w-0" key={gen}>
        <legend className="sr-only">{titleCase(settingKey)}</legend>
        {isObj ? (
          <ObjectFields
            path=""
            value={draft as Record<string, unknown>}
            depth={0}
            onValidity={onValidity}
            onChange={setDraft}
          />
        ) : (
          <ValueEditor name={settingKey} path={settingKey} value={draft} depth={0} onValidity={onValidity} onChange={setDraft} />
        )}
      </fieldset>
      {errList.length ? (
        <ul role="alert" className="list-inside list-disc text-xs text-down">
          {errList.map(([p, e]) => (
            <li key={p}>
              <code>{p}</code> {e}
            </li>
          ))}
        </ul>
      ) : null}
      <SaveBar
        editable={editable}
        pending={save.isPending}
        disabled={errList.length > 0 || !isObj}
        error={save.error?.message ?? (!isObj && editable ? "This setting must be a JSON object to be saved." : null)}
        onSave={() => save.mutate({ key: settingKey, value: draft })}
        onResetLoaded={() => reset(initial)}
        onLoadDefaults={defaults !== undefined ? () => reset(defaults) : undefined}
        version={version}
      />
    </div>
  );
}
