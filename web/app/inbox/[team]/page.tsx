"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { BusinessShell } from "@/components/shell";
import { ItemRow } from "@/components/item-card";
import { Banner, Empty, Input, Pill, Select, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { InboxPage } from "@/lib/types";

const VIEWS = [
  { id: "surfaced", label: "For you" },
  { id: "all", label: "Everything" },
  { id: "changes", label: "Wording changes" },
  { id: "starred", label: "Marked useful" },
];

export default function Inbox() {
  const params = useParams<{ team: string }>();
  const search = useSearchParams();
  const team = params.team;
  const [view, setView] = useState(search.get("view") || "surfaced");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [days, setDays] = useState("30");

  const path = useMemo(() => {
    const u = new URLSearchParams({ view, days });
    if (q.trim()) u.set("q", q.trim());
    if (category) u.set("category", category);
    return `/api/inbox/${team}?${u}`;
  }, [team, view, q, category, days]);

  const { data, error, loading, reload } = useApi<InboxPage>(path);

  return (
    <BusinessShell>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-copper-400">Inbox</p>
          <h1 className="mt-1 font-serif text-4xl">{data?.team.name || team}</h1>
          {data ? <p className="mt-2 max-w-xl text-sm text-mist">{data.team.lens}</p> : null}
        </div>
        {data ? (
          <div className="flex gap-2 text-xs text-mist">
            <Pill tone="copper">{data.counts.surfaced ?? 0} for you</Pill>
            <Pill>{data.counts.all ?? 0} total</Pill>
          </div>
        ) : null}
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setView(v.id)}
            className={`rounded-full px-3 py-1.5 text-sm ${view === v.id ? "bg-white/10 text-paper" : "text-mist hover:text-paper"}`}
          >
            {v.label}
          </button>
        ))}
        <span className="flex-1" />
        <Input
          placeholder="Search headlines"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-48 py-2"
        />
        <Select value={days} onChange={(e) => setDays(e.target.value)} className="w-28 py-2">
          <option value="7">7 days</option>
          <option value="30">30 days</option>
          <option value="90">90 days</option>
        </Select>
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-44 py-2">
          <option value="">All kinds</option>
          <option value="product_launch">Product launch</option>
          <option value="feature_update">Feature update</option>
          <option value="positioning_shift">Positioning shift</option>
          <option value="funding">Funding</option>
          <option value="partnership">Partnership</option>
          <option value="research">Research</option>
          <option value="hiring_signal">Hiring signal</option>
          <option value="compliance_or_certification">Compliance</option>
        </Select>
      </div>

      <div className="mt-8">
        {loading ? <Spinner label="Reading the inbox…" /> : null}
        {error ? <Banner tone="bad">{error}</Banner> : null}
        {data && !loading && data.items.length === 0 ? (
          <Empty title={view === "surfaced" ? "Nothing that needs you right now." : "No pieces in this view."}>
            {view === "surfaced"
              ? "Quiet is a feature. When something scores high enough for this team, it lands here — and in Slack if you turned that on."
              : "Try a wider window, or switch to Everything."}
          </Empty>
        ) : null}
        {data ? (
          <div className="space-y-3">
            {data.items.map((item) => (
              <ItemRow key={item.id} item={item} teamKey={team} onChange={reload} />
            ))}
          </div>
        ) : null}
      </div>
    </BusinessShell>
  );
}
