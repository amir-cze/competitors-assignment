"use client";

import Link from "next/link";
import { BusinessShell } from "@/components/shell";
import { ItemRow } from "@/components/item-card";
import { Banner, Card, Empty, HealthDot, Pill, Score, Spinner, cn } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { fmtWhen } from "@/lib/api";
import type { BriefingRow, Overview } from "@/lib/types";

export default function BriefingPage() {
  const { data, error, loading } = useApi<Overview>("/api/overview");
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <BusinessShell>
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-copper-400">{today}</p>
      <h1 className="mt-2 font-serif text-4xl text-paper md:text-5xl">This week’s briefing</h1>
      <p className="mt-3 max-w-2xl text-mist">
        Everything competitors published this week that mattered to someone here — each piece once, with who it
        concerns. The team inboxes are where you work through them.
      </p>

      {loading ? <div className="mt-10"><Spinner label="Gathering the briefing…" /></div> : null}
      {error ? <div className="mt-8"><Banner tone="bad">{error}</Banner></div> : null}

      {data ? (
        <div className="mt-10 space-y-12">
          <div className="flex flex-wrap gap-6 text-sm text-mist">
            <Stat n={data.competitor_count} label="on the watchlist" />
            <Stat n={data.items_7d} label="pieces seen this week" />
            <Stat n={data.highlights.length} label="worth someone’s time" />
            <span className="inline-flex items-center gap-2">
              <HealthDot health={data.monitoring.running ? "healthy" : "checking"} />
              {data.monitoring.running ? "Monitoring" : "Waiting on the first check"}
              {data.monitoring.last_check ? ` · last ${fmtWhen(data.monitoring.last_check)}` : ""}
            </span>
          </div>

          {data.attention.length ? (
            <Banner>
              Needs a look: {data.attention.join(", ")}. Open the <Link href="/watchlist" className="underline">watchlist</Link> —
              a source has gone quiet or changed shape.
            </Banner>
          ) : null}

          {data.competitor_count === 0 ? (
            <Empty title="Nothing on the watchlist yet.">
              Paste a competitor homepage. Radar finds the blog, the changelog, the newsroom — you pick what to keep.
              <div className="mt-5">
                <Link href="/watchlist" className="text-copper-300">
                  Add the first competitor →
                </Link>
              </div>
            </Empty>
          ) : (
            <>
              <section>
                <div className="grid gap-4 md:grid-cols-3">
                  {data.teams.map(({ team, surfaced_7d, immediate_7d, digest_7d }) => (
                    <Link key={team.key} href={`/inbox/${team.key}`} className="group">
                      <Card className="h-full transition group-hover:border-copper-500/40">
                        <div className="flex items-baseline justify-between gap-3">
                          <h2 className="font-serif text-2xl">{team.name}</h2>
                          <span className="font-serif text-3xl text-paper">{surfaced_7d}</span>
                        </div>
                        <p className="mt-1 text-sm text-mist">
                          {surfaced_7d === 0
                            ? "Quiet this week. That is the point."
                            : `${immediate_7d} interrupted · ${digest_7d} in the digest`}
                        </p>
                        <p className="mt-4 text-sm text-copper-300">Open inbox →</p>
                      </Card>
                    </Link>
                  ))}
                </div>
              </section>

              <section>
                <h2 className="font-serif text-2xl">What mattered</h2>
                <p className="mt-1 text-sm text-mist">Strongest first. The chips say which team it is for, and how strongly.</p>
                {data.highlights.length === 0 ? (
                  <p className="mt-6 text-sm text-mist">Nothing cleared a team’s bar this week.</p>
                ) : (
                  <div className="mt-5 divide-y divide-white/[0.06] rounded-2xl border border-white/[0.06] bg-ink-900/40">
                    {data.highlights.map((row) => (
                      <HighlightRow key={row.id} row={row} />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {data.recent_changes.length ? (
            <section>
              <h2 className="font-serif text-2xl">Wording that changed</h2>
              <p className="mt-1 text-sm text-mist">Watched pages whose claims shifted — not a new post, a rewrite.</p>
              <div className="mt-4 space-y-3">
                {data.recent_changes.map((item) => (
                  <ItemRow key={item.id} item={item} />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </BusinessShell>
  );
}

function HighlightRow({ row }: { row: BriefingRow }) {
  const top = row.teams[0];
  return (
    <div className="grid grid-cols-[auto_1fr] gap-4 p-4 md:grid-cols-[auto_1fr_auto] md:items-center">
      <Score value={top?.relevance ?? null} size="sm" />
      <div className="min-w-0">
        <div className="truncate text-[11px] uppercase tracking-[0.14em] text-mist">
          <span className="text-paper/80">{row.competitor_name}</span>
          {row.category_label ? <><span className="mx-1.5">·</span>{row.category_label}</> : null}
          <span className="mx-1.5">·</span>
          {fmtWhen(row.published_at)}
        </div>
        <Link
          href={`/items/${row.id}${top ? `?team=${top.team_key}` : ""}`}
          className="mt-1 block font-serif text-lg leading-snug text-paper hover:text-copper-300"
        >
          {row.title}
        </Link>
      </div>
      <div className="col-span-2 flex flex-wrap gap-1.5 md:col-span-1 md:justify-end">
        {row.teams.map((t) => (
          <Link key={t.team_key} href={`/inbox/${t.team_key}`} title={t.route === "immediate" ? "Sent to Slack" : "In the digest"}>
            <Pill tone={t.route === "immediate" ? "copper" : "mist"}>
              <span className={cn(t.route === "immediate" ? "" : "text-paper/80")}>{t.team_name}</span>
              <span className="ml-1.5 font-mono">{t.relevance}</span>
            </Pill>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <span>
      <span className="font-serif text-lg text-paper">{n}</span> {label}
    </span>
  );
}
