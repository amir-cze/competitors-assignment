"use client";

import { FormEvent, useState } from "react";
import { BusinessShell } from "@/components/shell";
import { Banner, Button, Card, Empty, Field, HealthDot, Input, Pill, Spinner } from "@/components/ui";
import { api, fmtWhen } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { Competitor, Discovery, SourceCandidate } from "@/lib/types";

export default function WatchlistPage() {
  const { data, error, loading, reload } = useApi<Competitor[]>("/api/competitors");
  const add = useBusy();
  const [url, setUrl] = useState("");
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});

  async function lookUp(e: FormEvent) {
    e.preventDefault();
    setDiscovery(null);
    const result = await add.run(() =>
      api<Discovery>("/api/competitors/discover", { method: "POST", body: JSON.stringify({ url }) }),
    );
    if (!result) return;
    setDiscovery(result);
    setName(result.site_name || hostname(url));
    setPicked(Object.fromEntries(result.candidates.map((c) => [c.url, c.recommended])));
  }

  async function save() {
    if (!discovery) return;
    const sources = discovery.candidates
      .filter((c) => picked[c.url])
      .map((c) => ({ kind: c.kind, url: c.url, label: c.label }));
    const row = await add.run(() =>
      api<Competitor>("/api/competitors", {
        method: "POST",
        body: JSON.stringify({ name, homepage_url: discovery.homepage_url, sources }),
      }),
    );
    if (!row) return;
    setDiscovery(null);
    setUrl("");
    reload();
  }

  return (
    <BusinessShell>
      <h1 className="font-serif text-4xl">Watchlist</h1>
      <p className="mt-2 max-w-xl text-mist">
        Paste a homepage. Radar looks for the blog, the changelog, the newsroom. You confirm. No RSS hunting.
      </p>

      <form onSubmit={(e) => void lookUp(e)} className="mt-8 flex flex-wrap gap-3">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://competitor.com"
          className="max-w-lg flex-1"
        />
        <Button type="submit" disabled={add.busy || !url.trim()}>
          {add.busy && !discovery ? "Looking…" : "Look up"}
        </Button>
      </form>
      {add.error ? <div className="mt-4"><Banner tone="bad">{add.error}</Banner></div> : null}

      {discovery ? (
        <Card className="mt-6">
          <p className="text-xs uppercase tracking-[0.16em] text-mist">Found on {discovery.homepage_url}</p>
          <Field label="Name on the watchlist" hint={`Took ${Math.round((discovery.elapsed_ms || 0) / 1000)}s`}>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 max-w-md" />
          </Field>
          {discovery.warnings.length ? (
            <p className="mt-3 text-sm text-amber-200">{discovery.warnings.join(" · ")}</p>
          ) : null}
          <ul className="mt-5 space-y-3">
            {discovery.candidates.length === 0 ? (
              <li className="text-sm text-mist">No obvious listing. You can still save the competitor and add a page to watch later.</li>
            ) : (
              discovery.candidates.map((c) => (
                <Candidate key={c.url} c={c} checked={!!picked[c.url]} onToggle={() => setPicked((p) => ({ ...p, [c.url]: !p[c.url] }))} />
              ))
            )}
          </ul>
          <div className="mt-5 flex gap-2">
            <Button onClick={() => void save()} disabled={add.busy || !name.trim()}>
              {add.busy ? "Saving…" : "Add to watchlist"}
            </Button>
            <Button variant="ghost" onClick={() => setDiscovery(null)}>
              Cancel
            </Button>
          </div>
        </Card>
      ) : null}

      <div className="mt-10">
        {loading ? <Spinner label="Loading watchlist…" /> : null}
        {error ? <Banner tone="bad">{error}</Banner> : null}
        {data && data.length === 0 && !discovery ? (
          <Empty title="No one is being watched yet.">Start with a homepage URL above.</Empty>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          {data?.map((c) => (
            <CompetitorCard key={c.id} competitor={c} onChange={reload} />
          ))}
        </div>
      </div>
    </BusinessShell>
  );
}

function Candidate({ c, checked, onToggle }: { c: SourceCandidate; checked: boolean; onToggle: () => void }) {
  return (
    <li className="flex gap-3 rounded-xl border border-white/5 p-3">
      <input type="checkbox" checked={checked} onChange={onToggle} className="mt-1 accent-copper-500" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{c.label}</span>
          <Pill>{c.kind.replace("_", " ")}</Pill>
          {c.recommended ? <Pill tone="copper">suggested</Pill> : null}
          {c.item_count ? <span className="text-xs text-mist">{c.item_count} recent</span> : null}
        </div>
        <p className="truncate text-xs text-mist">{c.url}</p>
        {c.sample_titles.length ? (
          <p className="mt-1 text-xs text-mist/80">{c.sample_titles.slice(0, 2).join(" · ")}</p>
        ) : null}
        {c.note ? <p className="mt-1 text-xs text-amber-200">{c.note}</p> : null}
      </div>
    </li>
  );
}

function CompetitorCard({ competitor, onChange }: { competitor: Competitor; onChange: () => void }) {
  const { run, busy, error } = useBusy();
  const [pageUrl, setPageUrl] = useState("");
  const [open, setOpen] = useState(false);

  async function patch(body: object) {
    await run(async () => {
      await api(`/api/competitors/${competitor.id}`, { method: "PATCH", body: JSON.stringify(body) });
      onChange();
    });
  }
  async function checkNow() {
    await run(async () => {
      await api(`/api/competitors/${competitor.id}/check-now`, { method: "POST" });
      onChange();
    });
  }
  async function watchPage(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      await api(`/api/competitors/${competitor.id}/watch-page`, {
        method: "POST",
        body: JSON.stringify({ url: pageUrl }),
      });
      setPageUrl("");
      onChange();
    });
  }
  async function remove() {
    if (!confirm(`Remove ${competitor.name} from the watchlist?`)) return;
    await run(async () => {
      await api(`/api/competitors/${competitor.id}`, { method: "DELETE" });
      onChange();
    });
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <HealthDot health={competitor.health} />
            <h2 className="font-serif text-2xl">{competitor.name}</h2>
            {competitor.muted ? <Pill tone="warn">muted</Pill> : null}
          </div>
          <a href={competitor.homepage_url} className="text-xs text-mist hover:text-copper-300" target="_blank" rel="noreferrer">
            {hostname(competitor.homepage_url)}
          </a>
        </div>
        <p className="text-right text-xs text-mist">
          {competitor.item_count} pieces
          <br />
          {competitor.last_item_at ? fmtWhen(competitor.last_item_at) : "nothing yet"}
        </p>
      </div>
      <ul className="mt-4 space-y-1.5 text-xs text-mist">
        {competitor.sources.map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <HealthDot health={s.health} />
            <span className="truncate">{s.label || s.url}</span>
            <span className="ml-auto">{s.kind.replace("_", " ")}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => void checkNow()}>
          Check now
        </Button>
        <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => void patch({ muted: !competitor.muted })}>
          {competitor.muted ? "Unmute" : "Mute"}
        </Button>
        <Button variant="quiet" className="text-xs" onClick={() => setOpen((v) => !v)}>
          Watch a page
        </Button>
        <Button variant="quiet" className="text-xs text-red-300" disabled={busy} onClick={() => void remove()}>
          Remove
        </Button>
      </div>
      {open ? (
        <form onSubmit={(e) => void watchPage(e)} className="mt-3 flex gap-2">
          <Input value={pageUrl} onChange={(e) => setPageUrl(e.target.value)} placeholder="https://…/pricing" className="py-2" />
          <Button type="submit" disabled={busy || !pageUrl}>
            Watch
          </Button>
        </form>
      ) : null}
      {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
    </Card>
  );
}

function hostname(url: string) {
  try {
    return new URL(url.startsWith("http") ? url : `https://${url}`).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
