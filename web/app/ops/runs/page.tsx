"use client";

import { useState } from "react";
import { OpsShell } from "@/components/shell";
import { Banner, Card, Pill, Select, Spinner } from "@/components/ui";
import { fmtWhen } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { OpsRun } from "@/lib/types";

export default function OpsRunsPage() {
  const [status, setStatus] = useState("");
  const path = status ? `/api/ops/runs?status=${status}` : "/api/ops/runs";
  const { data, error, loading } = useApi<OpsRun[]>(path);
  const [openId, setOpenId] = useState<string | null>(null);
  const run = useApi<OpsRun>(openId ? `/api/ops/runs/${openId}` : null);

  return (
    <OpsShell>
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl">Runs</h1>
          <p className="mt-1 text-sm text-mist">Per-source timeline, errors, LLM cost.</p>
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40 py-2">
          <option value="">All statuses</option>
          <option value="ok">ok</option>
          <option value="error">error</option>
          <option value="running">running</option>
        </Select>
      </div>
      {loading ? <div className="mt-8"><Spinner /></div> : null}
      {error ? <div className="mt-6"><Banner tone="bad">{error}</Banner></div> : null}
      <div className="mt-6 space-y-2">
        {(data || []).map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setOpenId(r.id === openId ? null : r.id)}
            className="w-full rounded-xl border border-white/5 bg-ink-900/40 px-4 py-3 text-left text-sm hover:border-white/10"
          >
            <div className="flex flex-wrap items-center gap-3">
              <Pill tone={r.status === "ok" ? "ok" : r.status === "error" ? "bad" : "warn"}>{r.status}</Pill>
              <span className="font-medium">{r.competitor || r.source_id}</span>
              <span className="text-mist">{r.source_label || r.kind}</span>
              <span className="ml-auto font-mono text-xs text-mist">
                {fmtWhen(r.started_at)} · {r.duration_ms != null ? `${r.duration_ms}ms` : "…"} · {r.items_new}/{r.items_found} new · ${r.llm_cost_usd.toFixed(3)}
              </span>
            </div>
            {r.error ? <p className="mt-2 text-xs text-red-300">{r.error}</p> : null}
          </button>
        ))}
      </div>
      {openId && run.data ? (
        <Card className="mt-6">
          <p className="font-mono text-xs text-mist">
            {run.data.id} · {run.data.trigger} · HTTP {run.data.http_status ?? "—"}
          </p>
          <pre className="mt-3 max-h-96 overflow-auto font-mono text-xs leading-relaxed text-paper/80">
            {(run.data.log || []).map((l) => `${l.t}  ${l.msg}`).join("\n") || "No log."}
          </pre>
        </Card>
      ) : null}
    </OpsShell>
  );
}
