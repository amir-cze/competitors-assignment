"use client";

import Link from "next/link";
import { BusinessShell } from "@/components/shell";
import { ItemRow } from "@/components/item-card";
import { Banner, Card, Empty, HealthDot, Pill, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { fmtWhen } from "@/lib/api";
import type { Overview } from "@/lib/types";

export default function BriefingPage() {
  const { data, error, loading, reload } = useApi<Overview>("/api/overview");
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <BusinessShell>
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-copper-400">{today}</p>
      <h1 className="mt-2 font-serif text-4xl text-paper md:text-5xl">This week’s briefing</h1>
      <p className="mt-3 max-w-2xl text-mist">
        Three inboxes, one watchlist. Radar only interrupts a team when the piece is actually for them.
      </p>

      {loading ? <div className="mt-10"><Spinner label="Gathering the briefing…" /></div> : null}
      {error ? <div className="mt-8"><Banner tone="bad">{error}</Banner></div> : null}

      {data ? (
        <div className="mt-10 space-y-10">
          <div className="flex flex-wrap gap-6 text-sm text-mist">
            <Stat n={data.competitor_count} label="on the watchlist" />
            <Stat n={data.items_7d} label="pieces this week" />
            <span className="inline-flex items-center gap-2">
              <HealthDot health={data.monitoring.running ? "healthy" : "checking"} />
              {data.monitoring.running ? "Monitoring" : "Waiting on the first check"}
              {data.monitoring.last_check ? ` · last ${fmtWhen(data.monitoring.last_check)}` : ""}
            </span>
          </div>

          {data.attention.length ? (
            <Banner>
              Needs a look: {data.attention.join(", ")}. Open the watchlist if a source has gone quiet.
            </Banner>
          ) : null}

          {data.teams.every((t) => t.items.length === 0) && data.competitor_count === 0 ? (
            <Empty title="Nothing on the watchlist yet.">
              Paste a competitor homepage. Radar finds the blog, the changelog, the newsroom — you pick what to keep.
              <div className="mt-5">
                <Link href="/watchlist" className="text-copper-300">
                  Add the first competitor →
                </Link>
              </div>
            </Empty>
          ) : (
            <div className="grid gap-6 lg:grid-cols-3">
              {data.teams.map(({ team, surfaced_7d, items }) => (
                <Card key={team.key} className="flex flex-col">
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className="font-serif text-2xl">{team.name}</h2>
                    <Pill tone="copper">{surfaced_7d} this week</Pill>
                  </div>
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-mist">{team.lens}</p>
                  <div className="mt-5 flex-1 space-y-3">
                    {items.length === 0 ? (
                      <p className="text-sm text-mist">Quiet for {team.name}. That is the point.</p>
                    ) : (
                      items.slice(0, 3).map((item) => (
                        <ItemRow key={item.id} item={item} teamKey={team.key} onChange={reload} />
                      ))
                    )}
                  </div>
                  <Link href={`/inbox/${team.key}`} className="mt-5 text-sm text-copper-300">
                    Open {team.name} inbox →
                  </Link>
                </Card>
              ))}
            </div>
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

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <span>
      <span className="font-serif text-lg text-paper">{n}</span> {label}
    </span>
  );
}
