"use client";

import { useState } from "react";
import { OpsShell } from "@/components/shell";
import { Banner, Button, Card, HealthDot, Pill, Spinner } from "@/components/ui";
import { api, fmtWhen } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { OpsSource } from "@/lib/types";

export default function OpsSourcesPage() {
  const { data, error, loading, reload } = useApi<OpsSource[]>("/api/ops/sources");
  const { run, busy, error: actionError } = useBusy();
  const [log, setLog] = useState<{ id: string; lines: { t: string; msg: string }[] } | null>(null);

  async function act(id: string, path: string, method = "POST") {
    const result = await run(() => api<Record<string, unknown>>(`/api/ops/sources/${id}${path}`, { method }));
    if (path === "/run" && result && Array.isArray(result.log)) {
      setLog({ id, lines: result.log as { t: string; msg: string }[] });
    }
    reload();
  }

  async function toggle(s: OpsSource) {
    await run(() =>
      api(`/api/ops/sources/${s.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !s.enabled }) }),
    );
    reload();
  }

  return (
    <OpsShell>
      <h1 className="font-serif text-3xl">Sources</h1>
      <p className="mt-1 text-sm text-mist">Adapter, health, yield. Force a run when a listing looks dead.</p>
      {loading ? <div className="mt-8"><Spinner /></div> : null}
      {error ? <div className="mt-6"><Banner tone="bad">{error}</Banner></div> : null}
      {actionError ? <div className="mt-4"><Banner tone="bad">{actionError}</Banner></div> : null}
      <div className="mt-6 overflow-x-auto rounded-2xl border border-white/[0.06]">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-ink-900 text-xs uppercase tracking-[0.14em] text-mist">
            <tr>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Kind</th>
              <th className="px-4 py-3">Health</th>
              <th className="px-4 py-3">Last</th>
              <th className="px-4 py-3">Yield</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(data || []).map((s) => (
              <tr key={s.id} className="border-t border-white/5">
                <td className="px-4 py-3">
                  <div className="font-medium">{s.competitor}</div>
                  <div className="max-w-xs truncate font-mono text-xs text-mist">{s.label || s.url}</div>
                </td>
                <td className="px-4 py-3">
                  <Pill>{s.kind}</Pill>
                  {!s.enabled ? <Pill tone="warn">off</Pill> : null}
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-2">
                    <HealthDot health={s.health} />
                    {s.health}
                  </span>
                  {s.last_error ? <p className="max-w-xs truncate text-xs text-red-300">{s.last_error}</p> : null}
                </td>
                <td className="px-4 py-3 text-xs text-mist">
                  {fmtWhen(s.last_success_at || s.last_run_at)}
                  <br />
                  next {fmtWhen(s.next_run_at)}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-mist">
                  {s.yield_trend.slice(0, 5).map((y) => `${y.new}/${y.found}`).join(" · ") || "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" className="px-2 py-1 text-xs" disabled={busy} onClick={() => void act(s.id, "/run")}>
                      Run
                    </Button>
                    <Button variant="quiet" className="px-2 py-1 text-xs" disabled={busy} onClick={() => void toggle(s)}>
                      {s.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button variant="quiet" className="px-2 py-1 text-xs" disabled={busy} onClick={() => void act(s.id, "/reset-recipe")}>
                      Reset recipe
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {log ? (
        <Card className="mt-6">
          <p className="font-mono text-xs text-mist">Run log · {log.id}</p>
          <pre className="mt-3 max-h-80 overflow-auto font-mono text-xs leading-relaxed text-paper/80">
            {log.lines.map((l) => `${l.t}  ${l.msg}`).join("\n")}
          </pre>
        </Card>
      ) : null}
    </OpsShell>
  );
}
