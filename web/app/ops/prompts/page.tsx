"use client";

import { useMemo, useState } from "react";
import { OpsShell } from "@/components/shell";
import { Banner, Button, Card, Pill, Spinner, Textarea } from "@/components/ui";
import { api, fmtWhen } from "@/lib/api";
import { useApi, useBusy } from "@/lib/hooks";
import type { PromptVersion } from "@/lib/types";

export default function OpsPromptsPage() {
  const { data, error, loading, reload } = useApi<PromptVersion[]>("/api/ops/prompts");
  const { run, busy, error: actionError } = useBusy();
  const [draft, setDraft] = useState("");
  const [notes, setNotes] = useState("");
  const [left, setLeft] = useState<string | null>(null);
  const [right, setRight] = useState<string | null>(null);

  const a = data?.find((p) => p.id === left);
  const b = data?.find((p) => p.id === right);
  const active = data?.find((p) => p.active);

  async function create(activate: boolean) {
    await run(async () => {
      await api("/api/ops/prompts?activate=" + activate, {
        method: "POST",
        body: JSON.stringify({ content: draft, notes: notes || null }),
      });
      setDraft("");
      setNotes("");
      reload();
    });
  }

  async function activate(id: string) {
    await run(async () => {
      await api(`/api/ops/prompts/${id}/activate`, { method: "POST" });
      reload();
    });
  }

  return (
    <OpsShell>
      <h1 className="font-serif text-3xl">Prompts</h1>
      <p className="mt-1 text-sm text-mist">
        The scoring template is versioned. Lenses and topics stay with the business; this is the operator’s instruction.
      </p>
      {loading ? <div className="mt-8"><Spinner /></div> : null}
      {error ? <div className="mt-6"><Banner tone="bad">{error}</Banner></div> : null}
      {actionError ? <div className="mt-4"><Banner tone="bad">{actionError}</Banner></div> : null}

      {active ? (
        <Card className="mt-6">
          <div className="flex items-center gap-2">
            <h2 className="font-serif text-xl">Active v{active.version}</h2>
            <Pill tone="copper">{fmtWhen(active.created_at)}</Pill>
          </div>
          <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-paper/80">
            {active.content}
          </pre>
        </Card>
      ) : null}

      <Card className="mt-6">
        <h2 className="font-serif text-xl">New version</h2>
        <Textarea className="mt-3 min-h-48 font-mono text-xs" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Paste the next scoring prompt…" />
        <Textarea className="mt-3 min-h-16" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (why this version)" />
        <div className="mt-3 flex gap-2">
          <Button disabled={busy || draft.length < 50} onClick={() => void create(false)}>
            Save draft
          </Button>
          <Button variant="ghost" disabled={busy || draft.length < 50} onClick={() => void create(true)}>
            Save and activate
          </Button>
        </div>
      </Card>

      <div className="mt-6 grid gap-3">
        {(data || []).map((p) => (
          <div key={p.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-white/5 px-4 py-3 text-sm">
            <span className="font-mono">v{p.version}</span>
            {p.active ? <Pill tone="ok">active</Pill> : null}
            <span className="text-mist">{p.notes || "—"}</span>
            <span className="ml-auto text-xs text-mist">{fmtWhen(p.created_at)}</span>
            {!p.active ? (
              <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => void activate(p.id)}>
                Activate
              </Button>
            ) : null}
            <button type="button" className="text-xs text-copper-300" onClick={() => setLeft(p.id)}>
              diff left
            </button>
            <button type="button" className="text-xs text-copper-300" onClick={() => setRight(p.id)}>
              diff right
            </button>
          </div>
        ))}
      </div>

      {a && b ? <PromptDiff left={a} right={b} /> : null}
    </OpsShell>
  );
}

function PromptDiff({ left, right }: { left: PromptVersion; right: PromptVersion }) {
  const rows = useMemo(() => simpleDiff(left.content, right.content), [left, right]);
  return (
    <Card className="mt-6">
      <p className="font-mono text-xs text-mist">
        v{left.version} → v{right.version}
      </p>
      <pre className="mt-3 max-h-96 overflow-auto font-mono text-xs leading-relaxed">
        {rows.map((r, i) => (
          <div key={i} className={r.t === "+" ? "bg-emerald-400/10" : r.t === "-" ? "bg-red-400/10" : ""}>
            {r.t} {r.line}
          </div>
        ))}
      </pre>
    </Card>
  );
}

function simpleDiff(a: string, b: string) {
  const al = a.split("\n");
  const bl = b.split("\n");
  const out: { t: string; line: string }[] = [];
  const n = Math.max(al.length, bl.length);
  for (let i = 0; i < n; i++) {
    if (al[i] === bl[i]) out.push({ t: " ", line: al[i] ?? "" });
    else {
      if (al[i] != null) out.push({ t: "-", line: al[i] });
      if (bl[i] != null) out.push({ t: "+", line: bl[i] });
    }
  }
  return out;
}
