"use client";

import { FormEvent, useState } from "react";
import { OpsShell } from "@/components/shell";
import { Banner, Button, Card, Field, Input, Pill, Spinner, Textarea } from "@/components/ui";
import { api, fmtWhen } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { EvalDashboard } from "@/lib/types";

type Golden = {
  id: string;
  item_id: string | null;
  competitor: string;
  title: string;
  labels: Record<string, boolean>;
  origin: string;
  kind: string;
  created_at: string;
};

export default function OpsEvalsPage() {
  const dash = useApi<EvalDashboard>("/api/ops/evals");
  const golden = useApi<Golden[]>("/api/ops/evals/golden/items");
  const { run, busy, error } = useBusy();
  const [manual, setManual] = useState({ competitor_name: "", title: "", content_text: "", marketing: true, product: true, rnd: false });

  async function runEval() {
    await run(async () => {
      await api("/api/ops/evals/run", { method: "POST" });
      dash.reload();
    });
  }

  async function promote(itemId: string) {
    await run(async () => {
      await api("/api/ops/evals/golden", { method: "POST", body: JSON.stringify({ item_id: itemId }) });
      dash.reload();
      golden.reload();
    });
  }

  async function removeGolden(g: Golden) {
    if (!confirm(`Remove "${g.title}" from the golden set?`)) return;
    await run(async () => {
      await api(`/api/ops/evals/golden/${g.id}`, { method: "DELETE" });
      golden.reload();
      dash.reload();
    });
  }

  async function addManual(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      await api("/api/ops/evals/golden/manual", {
        method: "POST",
        body: JSON.stringify({
          competitor_name: manual.competitor_name,
          title: manual.title,
          content_text: manual.content_text,
          labels: { marketing: manual.marketing, product: manual.product, rnd: manual.rnd },
        }),
      });
      setManual({ competitor_name: "", title: "", content_text: "", marketing: true, product: true, rnd: false });
      golden.reload();
      dash.reload();
    });
  }

  const d = dash.data;
  return (
    <OpsShell>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl">Evaluation</h1>
          <p className="mt-1 max-w-xl text-sm text-mist">
            Precision and recall against the golden set, plus live thumbs from the inbox. This is how we know the scoring is useful.
          </p>
        </div>
        <Button disabled={busy} onClick={() => void runEval()}>
          {busy ? "Running…" : "Run golden eval"}
        </Button>
      </div>
      {dash.loading ? <div className="mt-8"><Spinner /></div> : null}
      {dash.error ? <div className="mt-6"><Banner tone="bad">{dash.error}</Banner></div> : null}
      {error ? <div className="mt-4"><Banner tone="bad">{error}</Banner></div> : null}

      {d ? (
        <>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {Object.entries(d.live.teams).map(([key, t]) => (
              <Card key={key}>
                <p className="text-xs uppercase tracking-[0.16em] text-mist">{t.name}</p>
                <p className="mt-2 font-serif text-3xl">{pct(t.surfaced_precision)}</p>
                <p className="text-sm text-mist">precision on surfaced items</p>
                <p className="mt-3 text-xs text-mist">
                  recall proxy {pct(t.recall_proxy)} · {t.feedback_count} marks · {t.missed_useful} missed-useful
                </p>
              </Card>
            ))}
          </div>
          <p className="mt-4 text-xs text-mist">
            Golden set: {d.golden_count} items
            {Object.entries(d.golden_by_origin).map(([k, n]) => ` · ${k} ${n}`).join("")}
          </p>

          <h2 className="mt-10 font-serif text-2xl">History</h2>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-white/[0.06]">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-900 text-xs uppercase tracking-[0.14em] text-mist">
                <tr>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3">Prompt</th>
                  <th className="px-4 py-3">n</th>
                  <th className="px-4 py-3">Teams</th>
                  <th className="px-4 py-3">Cost</th>
                </tr>
              </thead>
              <tbody>
                {d.history.map((h) => (
                  <tr key={h.id} className="border-t border-white/5">
                    <td className="px-4 py-3 text-xs">{fmtWhen(h.run_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs">v{h.prompt_version ?? "—"}</td>
                    <td className="px-4 py-3">{h.n_items}</td>
                    <td className="px-4 py-3 text-xs">
                      {Object.entries(h.metrics).map(([k, m]) => (
                        <span key={k} className="mr-3">
                          {k} P{pct(m.precision)} R{pct(m.recall)}
                        </span>
                      ))}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">${h.cost_usd.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="mt-10 font-serif text-2xl">Disagreements</h2>
          <p className="text-sm text-mist">Surfaced but marked not useful, or useful but left in the archive. Promote into the golden set.</p>
          <div className="mt-3 space-y-2">
            {d.disagreements.length === 0 ? <p className="text-sm text-mist">None yet — feedback will land here.</p> : null}
            {d.disagreements.map((row) => (
              <div key={row.feedback_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-white/5 px-4 py-3 text-sm">
                <Pill tone={row.kind === "missed" ? "warn" : "bad"}>{row.kind.replace("_", " ")}</Pill>
                <span className="font-medium">{row.competitor}</span>
                <span className="flex-1">{row.headline}</span>
                <span className="text-xs text-mist">{row.team_name} · {row.verdict} · score {row.relevance}</span>
                {row.promoted ? (
                  <Pill tone="ok">in golden</Pill>
                ) : (
                  <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => void promote(row.item_id)}>
                    Promote
                  </Button>
                )}
              </div>
            ))}
          </div>
        </>
      ) : null}

      <h2 className="mt-10 font-serif text-2xl">Golden set</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-white/[0.06]">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-900 text-xs uppercase tracking-[0.14em] text-mist">
            <tr>
              <th className="px-4 py-3">Item</th>
              <th className="px-4 py-3">Labels</th>
              <th className="px-4 py-3">Origin</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(golden.data || []).map((g) => (
              <tr key={g.id} className="border-t border-white/5">
                <td className="px-4 py-3">
                  <div className="font-medium">{g.competitor}</div>
                  <div className="text-xs text-mist">{g.title}</div>
                </td>
                <td className="px-4 py-3 text-xs">
                  {Object.entries(g.labels).map(([k, v]) => (
                    <Pill key={k} tone={v ? "ok" : "mist"}>
                      {k}:{v ? "yes" : "no"}
                    </Pill>
                  ))}
                </td>
                <td className="px-4 py-3 font-mono text-xs">{g.origin}</td>
                <td className="px-4 py-3 text-right">
                  <Button variant="quiet" className="px-2 py-1 text-xs text-red-300" disabled={busy} onClick={() => void removeGolden(g)}>
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Card className="mt-6">
        <h3 className="font-serif text-xl">Add a labeled example</h3>
        <form onSubmit={(e) => void addManual(e)} className="mt-4 grid gap-3 md:grid-cols-2">
          <Field label="Competitor">
            <Input value={manual.competitor_name} onChange={(e) => setManual((m) => ({ ...m, competitor_name: e.target.value }))} />
          </Field>
          <Field label="Title">
            <Input value={manual.title} onChange={(e) => setManual((m) => ({ ...m, title: e.target.value }))} />
          </Field>
          <div className="md:col-span-2">
            <Field label="Content">
              <Textarea value={manual.content_text} onChange={(e) => setManual((m) => ({ ...m, content_text: e.target.value }))} />
            </Field>
          </div>
          <div className="flex gap-4 text-sm">
            {(["marketing", "product", "rnd"] as const).map((k) => (
              <label key={k} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={manual[k]}
                  onChange={(e) => setManual((m) => ({ ...m, [k]: e.target.checked }))}
                  className="accent-copper-500"
                />
                useful for {k}
              </label>
            ))}
          </div>
          <div>
            <Button type="submit" disabled={busy || !manual.title || !manual.content_text}>
              Add to golden set
            </Button>
          </div>
        </form>
      </Card>
    </OpsShell>
  );
}

function pct(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n * 100)}%`;
}
