"use client";

import Link from "next/link";
import { api, fmtWhen, kindLabel } from "@/lib/api";
import type { ItemCard } from "@/lib/types";
import { useBusy } from "@/lib/hooks";
import { Button, Pill, Score } from "./ui";

export function ItemRow({
  item,
  teamKey,
  href,
  onChange,
}: {
  item: ItemCard;
  teamKey?: string;
  href?: string;
  onChange?: () => void;
}) {
  const { run, busy } = useBusy();
  const assessment = item.assessment;
  const title = item.headline || item.title;
  const dest = href || `/items/${item.id}${teamKey ? `?team=${teamKey}` : ""}`;

  async function vote(verdict: "useful" | "not_useful") {
    if (!teamKey) return;
    await run(async () => {
      await api(`/api/items/${item.id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ team_key: teamKey, verdict }),
      });
      onChange?.();
    });
  }

  return (
    <article className="group grid grid-cols-[auto_1fr_auto] gap-4 rounded-2xl border border-white/[0.06] bg-ink-900/50 p-4 transition hover:border-white/10">
      <Score value={assessment?.relevance ?? item.max_relevance} />
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-mist">
          <span>{item.competitor_name}</span>
          <span>·</span>
          <span>{kindLabel(item.kind)}</span>
          {assessment?.category_label ? (
            <>
              <span>·</span>
              <span>{assessment.category_label}</span>
            </>
          ) : null}
          <span>·</span>
          <span>{fmtWhen(item.published_at || item.first_seen_at)}</span>
        </div>
        <Link href={dest} className="font-serif text-xl leading-snug text-paper hover:text-copper-300">
          {title}
        </Link>
        {assessment?.why ? <p className="mt-2 text-sm leading-relaxed text-mist">{assessment.why}</p> : item.summary ? <p className="mt-2 text-sm leading-relaxed text-mist">{item.summary}</p> : null}
        {assessment?.evidence_quote ? (
          <blockquote className="mt-3 border-l-2 border-copper-500/50 pl-3 font-serif text-sm italic text-paper/80">
            “{assessment.evidence_quote}”
          </blockquote>
        ) : null}
        {assessment?.topics_matched?.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {assessment.topics_matched.map((t) => (
              <Pill key={t}>{t}</Pill>
            ))}
          </div>
        ) : null}
      </div>
      <div className="flex flex-col items-end gap-2">
        {assessment?.route ? <RoutePill route={assessment.route} /> : null}
        {teamKey ? (
          <div className="flex gap-1">
            <Button
              variant={item.feedback?.verdict === "useful" ? "primary" : "ghost"}
              className="px-3 py-1 text-xs"
              disabled={busy}
              onClick={() => void vote("useful")}
              title="Useful"
            >
              Yes
            </Button>
            <Button
              variant={item.feedback?.verdict === "not_useful" ? "danger" : "ghost"}
              className="px-3 py-1 text-xs"
              disabled={busy}
              onClick={() => void vote("not_useful")}
              title="Not useful"
            >
              No
            </Button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function RoutePill({ route }: { route: string }) {
  if (route === "immediate") return <Pill tone="copper">Slack now</Pill>;
  if (route === "digest") return <Pill tone="mist">Daily digest</Pill>;
  return <Pill>Inbox only</Pill>;
}
