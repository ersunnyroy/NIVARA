"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Clock,
  Gauge,
  Info,
  Sprout,
  Timer,
  XCircle,
} from "lucide-react";
import { useSimpleView } from "@/lib/hooks";
import type { SimpleLongIdea, SimpleShortIdea, SimpleView } from "@/lib/types";
import { dateIST, dateTimeIST, inr } from "@/lib/format";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DataUnavailable,
  ErrorState,
  SkeletonCard,
  TabPanel,
  Tabs,
  cn,
} from "@/components/ui";

type TabKey = "week" | "long" | "today";

const MOOD_TONE: Record<string, string> = {
  "STRONG BULLISH": "border-up/40 bg-up-soft text-up",
  BULLISH: "border-up/30 bg-up-soft text-up",
  NEUTRAL: "border-border-strong bg-surface-3 text-fg",
  BEARISH: "border-down/30 bg-down-soft text-down",
  "STRONG BEARISH": "border-down/40 bg-down-soft text-down",
};

function signedPct(v: number) {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;
}

function MoodCard({ mood }: { mood: SimpleView["market_mood"] }) {
  if (!mood) return <DataUnavailable message="Market mood is not available yet." />;
  return (
    <Card>
      <CardBody className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <Gauge className="mt-1 size-6 shrink-0 text-muted" aria-hidden />
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Market mood today</p>
            <p className={cn("mt-1 inline-flex rounded-lg border px-3 py-1 text-lg font-bold", MOOD_TONE[mood.regime] ?? "")}>
              {mood.label}
            </p>
            <p className="mt-2 text-sm text-fg">{mood.explanation}</p>
            <p className="mt-1 text-sm font-medium text-fg">{mood.advice}</p>
          </div>
        </div>
        {mood.suggested_max_invested_pct != null ? (
          <div className="shrink-0 rounded-lg border border-border bg-surface-2 px-4 py-3 text-center">
            <p className="text-xs text-muted">Suggested maximum</p>
            <p className="text-2xl font-bold text-fg">{Math.round(mood.suggested_max_invested_pct)}%</p>
            <p className="text-xs text-muted">of your stock money invested</p>
          </div>
        ) : null}
      </CardBody>
      <p className="border-t border-border px-4 py-2 text-xs text-muted">Based on market data as of {dateTimeIST(mood.as_of)}</p>
    </Card>
  );
}

function ToneBadge({ tone, children }: { tone: SimpleShortIdea["tone"]; children: React.ReactNode }) {
  return <Badge tone={tone === "buy" ? "up" : tone === "wait" ? "warn" : "down"}>{children}</Badge>;
}

function Bullets({ items, kind }: { items: string[]; kind: "good" | "bad" }) {
  const Icon = kind === "good" ? CheckCircle2 : AlertTriangle;
  return (
    <ul className="space-y-1.5">
      {items.map((t) => (
        <li key={t} className="flex gap-2 text-sm text-fg">
          <Icon className={cn("mt-0.5 size-4 shrink-0", kind === "good" ? "text-up" : "text-warn")} aria-hidden />
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
}

function ShortIdeaCard({ it }: { it: SimpleShortIdea }) {
  const [open, setOpen] = useState(false);
  const best = it.targets[it.targets.length - 1];
  return (
    <Card as="article">
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <Link href={`/stocks/${it.symbol}`} className="text-base font-semibold text-fg hover:underline">
              {it.company}
            </Link>
            <p className="text-xs text-muted">
              {it.symbol}
              {it.industry ? ` · ${it.industry}` : ""}
            </p>
          </div>
          <ToneBadge tone={it.tone}>{it.what_to_do}</ToneBadge>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <p className="text-xs text-muted">Price now</p>
            <p className="font-semibold text-fg">{inr(it.price_now)}</p>
            <p className="text-[11px] text-muted">
              {it.price_kind === "eod_close" ? "last closing price" : it.price_kind === "delayed_quote" ? "today, a few minutes delayed" : "live"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted">Buy between</p>
            <p className="font-semibold text-fg">
              {inr(it.buy_zone[0])} – {inr(it.buy_zone[1])}
            </p>
            <p className="text-[11px] text-muted">don&apos;t buy above {inr(it.do_not_buy_above)}</p>
          </div>
          <div>
            <p className="text-xs text-muted">Possible gain</p>
            <p className="font-semibold text-up">
              {it.targets.map((t) => signedPct(t.gain_pct)).join(" to ")}
            </p>
            <p className="text-[11px] text-muted">sell near {inr(best?.price)}</p>
          </div>
          <div>
            <p className="text-xs text-muted">Possible loss</p>
            <p className="font-semibold text-down">{signedPct(it.possible_loss_pct)}</p>
            <p className="text-[11px] text-muted">sell if below {inr(it.stop_loss)}</p>
          </div>
        </div>

        <p className="rounded-lg bg-surface-2 px-3 py-2 text-sm text-fg">{it.simple_plan}</p>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3.5" aria-hidden /> Usually held {it.holding_time}
          </span>
          <span>
            System confidence: <span className="font-semibold text-fg">{it.confidence}</span> ({it.confidence_score}/100)
          </span>
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="text-sm font-medium text-accent hover:underline"
        >
          {open ? "Hide details" : "Why this stock, and what could go wrong?"}
        </button>
        {open ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-up">Why it was picked</p>
              <Bullets items={it.why} kind="good" />
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-warn">What could go wrong</p>
              <Bullets items={it.what_could_go_wrong} kind="bad" />
            </div>
            {it.similar_past_ideas ? (
              <div className="md:col-span-2 rounded-lg border border-border bg-surface-2 p-3 text-sm">
                <p className="font-medium text-fg">How similar past ideas turned out</p>
                <p className="mt-1 text-muted">
                  Of {it.similar_past_ideas.bought} similar ideas that were bought:{" "}
                  <span className="font-semibold text-fg">{it.similar_past_ideas.made_money_pct}%</span> made money,{" "}
                  <span className="font-semibold text-fg">{it.similar_past_ideas.reached_first_target_pct}%</span> reached the
                  first profit target and{" "}
                  <span className="font-semibold text-fg">{it.similar_past_ideas.hit_stop_loss_pct}%</span> hit the stop-loss.
                  Average result: <span className="font-semibold text-fg">{signedPct(it.similar_past_ideas.average_result_pct)}</span>.
                </p>
                <p className="mt-1 text-xs text-subtle">{it.similar_past_ideas.note}</p>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function LongIdeaCard({ it }: { it: SimpleLongIdea }) {
  const r = it.past_yearly_range;
  return (
    <Card as="article">
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <Link href={`/stocks/${it.symbol}`} className="text-base font-semibold text-fg hover:underline">
              {it.company}
            </Link>
            <p className="text-xs text-muted">
              {it.symbol}
              {it.industry ? ` · ${it.industry}` : ""} · price {inr(it.price_now)} (close {dateIST(it.price_as_of)})
            </p>
          </div>
          <Badge tone={it.business_quality === "Strong" ? "up" : "info"}>
            Business: {it.business_quality} ({it.business_score}/100)
          </Badge>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-up">Good signs</p>
            <Bullets items={it.why.length ? it.why : ["Passed the business-strength checks"]} kind="good" />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-warn">Things to watch</p>
            <Bullets items={it.things_to_watch.length ? it.things_to_watch : ["No major concerns in the available data"]} kind="bad" />
          </div>
        </div>
        {r ? (
          <div className="rounded-lg border border-border bg-surface-2 p-3 text-sm">
            <p className="font-medium text-fg">What happened over 1-year periods in the past</p>
            <div className="mt-2 grid grid-cols-3 gap-2 text-center">
              <div>
                <p className="text-xs text-muted">Bad year</p>
                <p className={cn("font-semibold", r.worst_pct < 0 ? "text-down" : "text-up")}>{signedPct(r.worst_pct)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Typical year</p>
                <p className={cn("font-semibold", r.typical_pct < 0 ? "text-down" : "text-up")}>{signedPct(r.typical_pct)}</p>
              </div>
              <div>
                <p className="text-xs text-muted">Good year</p>
                <p className={cn("font-semibold", r.best_pct < 0 ? "text-down" : "text-up")}>{signedPct(r.best_pct)}</p>
              </div>
            </div>
            {r.biggest_fall_pct != null ? (
              <p className="mt-2 text-sm text-fg">
                Biggest fall from a high in this period:{" "}
                <span className="font-semibold text-down">{signedPct(r.biggest_fall_pct)}</span> — be ready for drops like this.
              </p>
            ) : null}
            <p className="mt-2 text-xs text-subtle">
              {r.note} Based on about {r.years_of_data} years of prices — the future can be better or worse.
            </p>
          </div>
        ) : null}
        <p className="text-sm text-fg">
          <Sprout className="mr-1 inline size-4 text-up" aria-hidden />
          {it.how_to_buy}
        </p>
        {it.latest_results ? (
          <p className="text-xs text-muted">
            Latest quarterly results ({it.latest_results_quarter}): {it.latest_results.toLowerCase()}. {it.data_note}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

export default function SimplePage() {
  const q = useSimpleView();
  const [tab, setTab] = useState<TabKey>("week");
  const v = q.data;
  const idBase = "simple-tabs";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Simple view"
        description="Plain-language ideas for everyday investors — what to look at, at what price, and when to sell."
      />

      <div className="flex gap-2 rounded-lg border border-warn/30 bg-warn-soft/40 px-4 py-3 text-sm text-fg" role="note">
        <Info className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
        <p>
          {v?.disclaimer ??
            "These are ideas from an automated research tool, not advice. No profit is guaranteed — you can lose money."}
        </p>
      </div>

      {q.isLoading ? (
        <SkeletonCard lines={6} />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : v ? (
        <>
          <MoodCard mood={v.market_mood} />

          <Tabs<TabKey>
            label="Idea type"
            idBase={idBase}
            value={tab}
            onChange={setTab}
            tabs={[
              { key: "week", label: "This week (short term)" },
              { key: "long", label: "Long term (1 year+)" },
              { key: "today", label: "Today (intraday)" },
            ]}
          />

          {tab === "week" ? (
            <TabPanel idBase={idBase} k="week" className="space-y-3">
              <p className="text-sm text-muted">
                Short-term ideas meant to be held for a few days to a few weeks. Buy only inside the buy zone and always
                use the stop-loss. {v.this_week.how_much}
              </p>
              {v.this_week.status !== "ok" ? (
                <DataUnavailable message={v.this_week.message ?? "No short-term ideas are available."} />
              ) : v.this_week.items.length === 0 ? (
                <Card>
                  <CardBody className="text-sm text-muted">
                    No stock passed all the checks today. Not buying is also a decision — it protects your money.
                  </CardBody>
                </Card>
              ) : (
                <>
                  <p className="flex items-center gap-1 text-xs text-muted">
                    <CalendarDays className="size-3.5" aria-hidden />
                    Ideas for the session of {dateIST(v.this_week.for_session)} · prices as of {dateTimeIST(v.this_week.data_as_of)}
                  </p>
                  <div className="grid gap-3 xl:grid-cols-2">
                    {v.this_week.items.map((it) => (
                      <ShortIdeaCard key={it.recommendation_id} it={it} />
                    ))}
                  </div>
                </>
              )}
            </TabPanel>
          ) : null}

          {tab === "long" ? (
            <TabPanel idBase={idBase} k="long" className="space-y-3">
              <p className="text-sm text-muted">{v.long_term.how_it_works}</p>
              {v.long_term.status !== "ok" ? (
                <DataUnavailable message={v.long_term.message ?? "Long-term ideas are not available yet."} />
              ) : (
                <div className="grid gap-3 xl:grid-cols-2">
                  {v.long_term.items.map((it) => (
                    <LongIdeaCard key={it.symbol} it={it} />
                  ))}
                </div>
              )}
            </TabPanel>
          ) : null}

          {tab === "today" ? (
            <TabPanel idBase={idBase} k="today" className="space-y-3">
              <Card>
                <CardHeader title="Intraday (buy and sell the same day)" icon={<Timer className="size-4" />} />
                <CardBody className="space-y-3 text-sm text-fg">
                  <p>{v.today_intraday.message}</p>
                  {v.today_intraday.how_to_enable ? <p className="text-muted">{v.today_intraday.how_to_enable}</p> : null}
                  {v.today_intraday.warning ? (
                    <p className="flex gap-2 rounded-lg bg-down-soft/50 px-3 py-2 text-fg">
                      <XCircle className="mt-0.5 size-4 shrink-0 text-down" aria-hidden />
                      {v.today_intraday.warning}
                    </p>
                  ) : null}
                  <p className="text-muted">
                    For today, you can still look at the{" "}
                    <button type="button" className="font-medium text-accent hover:underline" onClick={() => setTab("week")}>
                      short-term ideas
                    </button>{" "}
                    — their buy zones are valid from today&apos;s session.
                  </p>
                </CardBody>
              </Card>
            </TabPanel>
          ) : null}

          <Card>
            <CardHeader title="Simple meanings" icon={<BookOpen className="size-4" />} subtitle="Words used on this page" />
            <CardBody>
              <dl className="grid gap-3 sm:grid-cols-2">
                {v.glossary.map((g) => (
                  <div key={g.term}>
                    <dt className="text-sm font-semibold text-fg">{g.term}</dt>
                    <dd className="text-sm text-muted">{g.meaning}</dd>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>
          <p className="text-xs text-muted">
            Want the full technical detail? See <Link href="/opportunities" className="text-accent hover:underline">Opportunities</Link>{" "}
            and each stock&apos;s page.
          </p>
        </>
      ) : null}
    </div>
  );
}
