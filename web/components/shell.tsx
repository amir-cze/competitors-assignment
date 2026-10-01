"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { cn } from "./ui";

const TEAMS = [
  { href: "/inbox/marketing", label: "Marketing" },
  { href: "/inbox/product", label: "Product" },
  { href: "/inbox/rnd", label: "R&D" },
];

export function Gate({
  mePath,
  children,
}: {
  mePath: string;
  children: ReactNode;
}) {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    api(mePath)
      .then(() => setOk(true))
      .catch(() => undefined);
  }, [mePath]);
  if (!ok) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-mist">
        Opening Radar…
      </div>
    );
  }
  return children;
}

export function BusinessShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <Gate mePath="/api/auth/me">
      <div className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-white/[0.05] bg-ink-950/85 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-4">
            <Link href="/" className="font-serif text-xl tracking-tight text-paper">
              Radar
            </Link>
            <nav className="flex flex-1 items-center gap-1 text-sm">
              <Nav href="/" active={path === "/"} label="Briefing" />
              {TEAMS.map((t) => (
                <Nav key={t.href} href={t.href} active={path === t.href} label={t.label} />
              ))}
              <span className="flex-1" />
              <Nav href="/watchlist" active={path.startsWith("/watchlist")} label="Watchlist" />
              <Nav href="/settings" active={path.startsWith("/settings")} label="Settings" />
              <button
                type="button"
                className="rounded-full px-3 py-1.5 text-mist hover:text-paper"
                onClick={async () => {
                  await api("/api/auth/logout", { method: "POST" });
                  window.location.href = "/login";
                }}
              >
                Sign out
              </button>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
      </div>
    </Gate>
  );
}

export function OpsShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  async function logout() {
    await api("/api/ops/auth/logout", { method: "POST" });
    window.location.href = "/ops/login";
  }
  return (
    <Gate mePath="/api/ops/auth/me">
      <div className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-white/[0.05] bg-ink-950/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
            <Link href="/ops" className="font-mono text-xs uppercase tracking-[0.22em] text-copper-400">
              Radar / ops
            </Link>
            <nav className="flex flex-1 items-center gap-1 text-sm">
              <Nav href="/ops" active={path === "/ops" || path.startsWith("/ops/system")} label="System" />
              <Nav href="/ops/sources" active={path.startsWith("/ops/sources")} label="Sources" />
              <Nav href="/ops/runs" active={path.startsWith("/ops/runs")} label="Runs" />
              <Nav href="/ops/prompts" active={path.startsWith("/ops/prompts")} label="Prompts" />
              <Nav href="/ops/evals" active={path.startsWith("/ops/evals")} label="Evals" />
              <span className="flex-1" />
              <Link href="/" className="rounded-full px-3 py-1.5 text-mist hover:text-paper">
                Business
              </Link>
              <button type="button" onClick={() => void logout()} className="rounded-full px-3 py-1.5 text-mist hover:text-paper">
                Sign out
              </button>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </div>
    </Gate>
  );
}

function Nav({ href, active, label }: { href: string; active: boolean; label: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-full px-3 py-1.5 transition",
        active ? "bg-white/5 text-paper" : "text-mist hover:text-paper",
      )}
    >
      {label}
    </Link>
  );
}
