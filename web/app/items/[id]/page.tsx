"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";
import { BusinessShell } from "@/components/shell";
import { RoutePill } from "@/components/item-card";
import { Banner, Button, Card, Pill, Score, Spinner, Textarea } from "@/components/ui";
import { api, fmtWhen, kindLabel } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { ItemDetail } from "@/lib/types";

export default function ItemPage() {
  const { id } = useParams<{ id: string }>();
  const team = useSearchParams().get("team") || "";
  const { data, error, loading, reload } = useApi<ItemDetail>(`/api/items/${id}`);
  const { run, busy, error: voteError } = useBusy();
  const [reason, setReason] = useState("");

  async function vote(verdict: "useful" | "not_useful") {
    if (!team) return;
    await run(async () => {
      await api(`/api/items/${id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ team_key: team, verdict, reason: reason || null }),
      });
      reload();
    });
  }

  return (
    <BusinessShell>
      {loading ? <Spinner /> : null}
      {error ? <Banner tone="bad">{error}</Banner> : null}
      {data ? (
        <article className="grid gap-8 lg:grid-cols-[1fr_280px]">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist">
              {data.competitor_name} · {kindLabel(data.kind)} · {fmtWhen(data.published_at || data.first_seen_at)}
            </p>
            <h1 className="mt-3 font-serif text-4xl leading-tight">{data.headline || data.title}</h1>
            <div className="mt-4 flex flex-wrap gap-2">
              {data.primary_category ? <Pill>{data.primary_category.replaceAll("_", " ")}</Pill> : null}
              <a href={data.canonical_url} target="_blank" rel="noreferrer" className="text-sm text-copper-300">
                Original →
              </a>
            </div>
            {data.summary ? <p className="mt-6 text-lg leading-relaxed text-mist">{data.summary}</p> : null}

            {data.page_diff ? (
              <section className="mt-10">
                <h2 className="font-serif text-2xl">What the wording did</h2>
                <p className="mt-1 text-sm text-mist">
                  {data.page_diff.page_label || "Watched page"} · {data.page_diff.changed_chars} characters moved
                </p>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <DiffCol label="Taken out" lines={data.page_diff.removed} tone="removed" />
                  <DiffCol label="Put in" lines={data.page_diff.added} tone="added" />
                </div>
              </section>
            ) : null}

            <section className="mt-10 space-y-4">
              <h2 className="font-serif text-2xl">Why it matters, by team</h2>
              {data.assessments.length === 0 ? (
                <p className="text-sm text-mist">Not scored yet — it will land once the worker catches up.</p>
              ) : (
                data.assessments.map((a) => (
                  <Card key={a.team_key} className="grid grid-cols-[auto_1fr] gap-4">
                    <Score value={a.relevance} />
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{a.team_name}</span>
                        <RoutePill route={a.route} />
                        <Pill>{a.category_label}</Pill>
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-paper/90">{a.why}</p>
                      {a.evidence_quote ? (
                        <blockquote className="mt-3 border-l-2 border-copper-500/50 pl-3 font-serif italic text-paper/80">
                          “{a.evidence_quote}”
                        </blockquote>
                      ) : null}
                    </div>
                  </Card>
                ))
              )}
            </section>

            {data.content_excerpt ? (
              <section className="mt-10">
                <h2 className="font-serif text-2xl">Excerpt</h2>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-mist">{data.content_excerpt}</p>
              </section>
            ) : null}
          </div>

          <aside className="space-y-4">
            {team ? (
              <Card>
                <p className="text-xs uppercase tracking-[0.16em] text-mist">Was this useful for {team}?</p>
                <p className="mt-2 text-sm text-mist">Your mark trains the next scoring pass.</p>
                <Textarea
                  className="mt-3 min-h-20"
                  placeholder="Optional: why"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <div className="mt-3 flex gap-2">
                  <Button disabled={busy} onClick={() => void vote("useful")}>
                    Yes
                  </Button>
                  <Button variant="ghost" disabled={busy} onClick={() => void vote("not_useful")}>
                    No
                  </Button>
                </div>
                {voteError ? <p className="mt-2 text-xs text-red-300">{voteError}</p> : null}
                {data.feedback.find((f) => f.team_key === team) ? (
                  <p className="mt-3 text-xs text-mist">
                    Marked {data.feedback.find((f) => f.team_key === team)?.verdict.replace("_", " ")}
                  </p>
                ) : null}
              </Card>
            ) : (
              <Card>
                <p className="text-sm text-mist">Open from a team inbox to mark whether it was useful.</p>
                <div className="mt-3 flex flex-col gap-1 text-sm">
                  <Link href={`/inbox/marketing`} className="text-copper-300">Marketing inbox</Link>
                  <Link href={`/inbox/product`} className="text-copper-300">Product inbox</Link>
                  <Link href={`/inbox/rnd`} className="text-copper-300">R&D inbox</Link>
                </div>
              </Card>
            )}
            <Card>
              <p className="text-xs uppercase tracking-[0.16em] text-mist">Seen on</p>
              <ul className="mt-2 space-y-1 text-xs text-mist">
                {data.sources.map((s) => (
                  <li key={s} className="truncate">
                    {s}
                  </li>
                ))}
              </ul>
            </Card>
          </aside>
        </article>
      ) : null}
    </BusinessShell>
  );
}

function DiffCol({ label, lines, tone }: { label: string; lines: string[]; tone: "added" | "removed" }) {
  return (
    <div className={`rounded-xl border p-4 ${tone === "added" ? "border-emerald-400/20 bg-emerald-400/5" : "border-red-400/20 bg-red-400/5"}`}>
      <p className="text-xs uppercase tracking-[0.16em] text-mist">{label}</p>
      <ul className="mt-3 space-y-2 text-sm">
        {(lines.length ? lines : ["—"]).map((line, i) => (
          <li key={i} className="leading-relaxed">
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}
