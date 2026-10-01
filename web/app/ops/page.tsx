"use client";

import { OpsShell } from "@/components/shell";
import { Banner, Button, Card, HealthDot, Pill, Spinner } from "@/components/ui";
import { api, fmtWhen } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";

type SystemStatus = {
  version: string;
  environment: string;
  worker: { heartbeat_at: string | null; alive: boolean; meta: Record<string, unknown> | null };
  queue: { due_sources: number; pending_items: number };
  sources_by_health: Record<string, number>;
  runs_24h: Record<string, number>;
    llm: {
      today_usd?: number;
      daily_budget_usd?: number;
      total_usd?: number;
      configured?: boolean;
      model?: string;
      provider_blocked_until?: string | null;
      provider_block_reason?: string | null;
    };
  checks: Record<string, unknown>;
  config: Record<string, unknown>;
};

type UsageRow = { day: string; purpose: string; cost_usd: number; calls: number };

export default function OpsSystemPage() {
  const sys = useApi<SystemStatus>("/api/ops/system");
  const usage = useApi<UsageRow[]>("/api/ops/llm-usage?days=7");
  const { run, busy, error } = useBusy();

  async function checks() {
    await run(() => api("/api/ops/system/checks", { method: "POST" }));
    sys.reload();
  }
  async function scorePending() {
    await run(() => api("/api/ops/system/score-pending", { method: "POST" }));
    sys.reload();
  }

  const d = sys.data;
  return (
    <OpsShell>
      <h1 className="font-serif text-3xl">System</h1>
      <p className="mt-1 text-sm text-mist">Heartbeat, queue, spend, integration checks. The 3 a.m. page.</p>
      {sys.loading ? <div className="mt-8"><Spinner /></div> : null}
      {sys.error ? <div className="mt-6"><Banner tone="bad">{sys.error}</Banner></div> : null}
      {d ? (
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <Card>
            <p className="text-xs uppercase tracking-[0.16em] text-mist">Worker</p>
            <div className="mt-3 flex items-center gap-2">
              <HealthDot health={d.worker.alive ? "healthy" : "attention"} />
              <span className="font-serif text-2xl">{d.worker.alive ? "Alive" : "Quiet"}</span>
            </div>
            <p className="mt-2 text-xs text-mist">Last beat {fmtWhen(d.worker.heartbeat_at)}</p>
            <p className="mt-1 font-mono text-xs text-mist">
              {d.environment} · v{d.version}
            </p>
          </Card>
          <Card>
            <p className="text-xs uppercase tracking-[0.16em] text-mist">Queue</p>
            <p className="mt-3 font-serif text-2xl">{d.queue.due_sources} due</p>
            <p className="text-sm text-mist">{d.queue.pending_items} items waiting to be scored</p>
            <Button className="mt-4 text-xs" variant="ghost" disabled={busy} onClick={() => void scorePending()}>
              Score pending now
            </Button>
          </Card>
          <Card>
            <p className="text-xs uppercase tracking-[0.16em] text-mist">LLM today</p>
            <p className="mt-3 font-serif text-2xl">${Number(d.llm.today_usd ?? 0).toFixed(2)}</p>
            <p className="text-sm text-mist">
              budget ${Number(d.llm.daily_budget_usd ?? 0).toFixed(2)} · {String(d.checks.model || "")}
            </p>
            {d.llm.provider_blocked_until ? (
              <p className="mt-3 text-xs text-amber-200">
                {d.llm.provider_block_reason}. Scoring paused until {fmtWhen(d.llm.provider_blocked_until)}; new items
                are parked, not lost.
              </p>
            ) : null}
          </Card>
        </div>
      ) : null}

      {d ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Card>
            <div className="flex items-center justify-between">
              <h2 className="font-serif text-xl">Checks</h2>
              <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => void checks()}>
                Ping live
              </Button>
            </div>
            {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
            <dl className="mt-4 space-y-2 font-mono text-xs">
              {Object.entries(d.checks).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-mist">{k}</dt>
                  <dd className="text-right text-paper">{fmtCheck(v)}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card>
            <h2 className="font-serif text-xl">Health / runs 24h</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(d.sources_by_health).map(([k, n]) => (
                <Pill key={k} tone={k === "healthy" ? "ok" : k === "failing" ? "bad" : "warn"}>
                  {k} {n}
                </Pill>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(d.runs_24h).map(([k, n]) => (
                <Pill key={k}>{k} {n}</Pill>
              ))}
            </div>
            <h3 className="mt-6 text-xs uppercase tracking-[0.16em] text-mist">Spend, 7 days</h3>
            <ul className="mt-2 space-y-1 font-mono text-xs text-mist">
              {(usage.data || []).map((row, i) => (
                <li key={i}>
                  {row.day} · {row.purpose} · ${row.cost_usd.toFixed(3)} · {row.calls} calls
                </li>
              ))}
              {!usage.data?.length ? <li>No LLM calls yet.</li> : null}
            </ul>
          </Card>
        </div>
      ) : null}
    </OpsShell>
  );
}

function fmtCheck(v: unknown): string {
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (v == null) return "—";
  return String(v);
}
