"use client";

import { FormEvent, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button, Field, Input } from "./ui";

export function SignIn({
  title,
  lede,
  label,
  placeholder,
  endpoint,
  bodyKey,
  next,
}: {
  title: string;
  lede: string;
  label: string;
  placeholder: string;
  endpoint: string;
  bodyKey: string;
  next: string;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(endpoint, { method: "POST", body: JSON.stringify({ [bodyKey]: value }) });
      window.location.href = next;
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6">
      <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-copper-400">Radar</p>
      <h1 className="mt-4 font-serif text-5xl leading-none text-paper">{title}</h1>
      <p className="mt-4 text-mist">{lede}</p>
      <form onSubmit={(e) => void onSubmit(e)} className="mt-10 space-y-5">
        <Field label={label}>
          <Input
            type="password"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
          />
        </Field>
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
        <Button type="submit" disabled={busy || !value} className="w-full py-3">
          {busy ? "Checking…" : "Enter"}
        </Button>
      </form>
    </div>
  );
}
