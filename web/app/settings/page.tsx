"use client";

import { FormEvent, useState } from "react";
import { BusinessShell } from "@/components/shell";
import { Banner, Button, Card, Field, Input, Pill, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { Team, Topic } from "@/lib/types";

export default function SettingsPage() {
  const teams = useApi<Team[]>("/api/teams");
  const topics = useApi<Topic[]>("/api/topics");
  const [active, setActive] = useState("marketing");
  const team = teams.data?.find((t) => t.key === active) || teams.data?.[0];

  return (
    <BusinessShell>
      <h1 className="font-serif text-4xl">Settings</h1>
      <p className="mt-2 max-w-xl text-mist">
        Each team writes, in plain language, what they care about. Radar uses that — not a shared score — to decide who to interrupt.
      </p>
      <div className="mt-8 flex gap-2">
        {(teams.data || []).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActive(t.key)}
            className={`rounded-full px-4 py-1.5 text-sm ${t.key === (team?.key || active) ? "bg-white/10 text-paper" : "text-mist"}`}
          >
            {t.name}
          </button>
        ))}
      </div>
      {teams.loading || topics.loading ? <div className="mt-8"><Spinner /></div> : null}
      {teams.error ? <div className="mt-6"><Banner tone="bad">{teams.error}</Banner></div> : null}
      {team ? (
        <TeamSettings
          key={team.key}
          team={team}
          topics={topics.data || []}
          onSaved={() => {
            teams.reload();
            topics.reload();
          }}
        />
      ) : null}
    </BusinessShell>
  );
}

function TeamSettings({ team, topics, onSaved }: { team: Team; topics: Topic[]; onSaved: () => void }) {
  const { run, busy, error } = useBusy();
  const [lens, setLens] = useState(team.lens);
  const [immediate, setImmediate] = useState(String(team.immediate_threshold));
  const [digest, setDigest] = useState(String(team.digest_threshold));
  const [hour, setHour] = useState(String(team.digest_hour_utc));
  const [webhook, setWebhook] = useState("");
  const [slackOn, setSlackOn] = useState(team.slack_enabled);
  const [topicName, setTopicName] = useState("");
  const [preview, setPreview] = useState<{ items: { headline: string; competitor: string; relevance: number }[] } | null>(null);

  const mine = topics.filter((t) => t.team_key === team.key || !t.team_id);

  async function save() {
    await run(async () => {
      await api(`/api/teams/${team.key}`, {
        method: "PATCH",
        body: JSON.stringify({
          lens,
          immediate_threshold: Number(immediate),
          digest_threshold: Number(digest),
          digest_hour_utc: Number(hour),
          slack_enabled: slackOn,
          ...(webhook ? { slack_webhook: webhook } : {}),
        }),
      });
      setWebhook("");
      onSaved();
    });
  }

  async function testSlack() {
    await run(async () => {
      await api(`/api/teams/${team.key}/slack/test`, { method: "POST" });
    });
  }

  async function previewDigest() {
    const data = await run(() => api<{ items: { headline: string; competitor: string; relevance: number }[] }>(`/api/teams/${team.key}/digest/preview`));
    if (data) setPreview(data);
  }

  async function sendDigest() {
    await run(async () => {
      await api(`/api/teams/${team.key}/digest/send`, { method: "POST" });
    });
  }

  async function addTopic(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      await api("/api/topics", {
        method: "POST",
        body: JSON.stringify({ name: topicName, team_key: team.key }),
      });
      setTopicName("");
      onSaved();
    });
  }

  async function dropTopic(id: string) {
    await run(async () => {
      await api(`/api/topics/${id}`, { method: "DELETE" });
      onSaved();
    });
  }

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-2">
      <Card>
        <h2 className="font-serif text-2xl">What {team.name} cares about</h2>
        <p className="mt-1 text-sm text-mist">This paragraph is injected into the scoring prompt. Rewrite it like you would brief an analyst.</p>
        <Textarea className="mt-4 min-h-48 text-sm leading-relaxed" value={lens} onChange={(e) => setLens(e.target.value)} />
        <div className="mt-5">
          <div className="flex items-baseline justify-between">
            <p className="text-xs uppercase tracking-[0.16em] text-mist">Topics</p>
            <p className="text-xs text-mist/70">Click a topic to remove it · ◦ = shared by all teams</p>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {mine.map((t) => {
              const shared = !(t.team_key === team.key && t.team_id);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => void dropTopic(t.id)}
                  className="rounded-full bg-white/5 px-3 py-1 text-xs text-paper transition hover:bg-red-400/10 hover:text-red-200"
                  title={shared ? "Shared topic — click to remove for everyone" : "Click to remove"}
                >
                  {shared ? <span className="mr-1.5 text-mist">◦</span> : null}
                  {t.name}
                </button>
              );
            })}
          </div>
          <form onSubmit={(e) => void addTopic(e)} className="mt-3 flex gap-2">
            <Input value={topicName} onChange={(e) => setTopicName(e.target.value)} placeholder="Add a topic" className="py-2" />
            <Button type="submit" disabled={busy || topicName.trim().length < 2}>
              Add
            </Button>
          </form>
        </div>
      </Card>

      <Card>
        <h2 className="font-serif text-2xl">When to interrupt</h2>
        <div className="mt-4 grid grid-cols-3 gap-3">
          <Field label="Slack now" hint="75 = interrupt">
            <Input type="number" min={0} max={100} value={immediate} onChange={(e) => setImmediate(e.target.value)} />
          </Field>
          <Field label="Daily digest" hint="Below this stays in inbox">
            <Input type="number" min={0} max={100} value={digest} onChange={(e) => setDigest(e.target.value)} />
          </Field>
          <Field label="Digest hour UTC">
            <Input type="number" min={0} max={23} value={hour} onChange={(e) => setHour(e.target.value)} />
          </Field>
        </div>
        <label className="mt-5 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={slackOn} onChange={(e) => setSlackOn(e.target.checked)} className="accent-copper-500" />
          Send to Slack
        </label>
        <div className="mt-4">
          <Field label="Slack incoming webhook" hint={team.slack_webhook_masked ? `Connected · ${team.slack_webhook_masked}` : "Not connected"}>
            <Input
              value={webhook}
              onChange={(e) => setWebhook(e.target.value)}
              placeholder="https://hooks.slack.com/services/…"
            />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => void save()} disabled={busy}>
            Save
          </Button>
          <Button variant="ghost" disabled={busy || !team.slack_webhook_masked} onClick={() => void testSlack()}>
            Test Slack
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => void previewDigest()}>
            Preview digest
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => void sendDigest()}>
            Send digest now
          </Button>
        </div>
        {error ? <p className="mt-3 text-sm text-red-300">{error}</p> : null}
        {preview ? (
          <div className="mt-4 space-y-2 text-sm">
            {preview.items.length === 0 ? <p className="text-mist">Nothing queued for the digest.</p> : null}
            {preview.items.map((item, i) => (
              <p key={i}>
                <Pill tone="copper">{item.relevance}</Pill> {item.competitor}: {item.headline}
              </p>
            ))}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
