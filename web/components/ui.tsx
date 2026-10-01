import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "quiet" }) {
  const styles = {
    primary: "bg-copper-500 text-ink-950 hover:bg-copper-400 disabled:opacity-50",
    ghost: "border border-white/10 text-paper hover:border-copper-500/50 hover:text-copper-300",
    quiet: "text-mist hover:text-paper",
    danger: "border border-red-400/30 text-red-300 hover:bg-red-400/10",
  }[variant];
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed",
        styles,
        className,
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs uppercase tracking-[0.16em] text-mist">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-mist/80">{hint}</span> : null}
    </label>
  );
}

const inputClass =
  "w-full rounded-xl border border-white/10 bg-ink-900 px-3 py-2.5 text-paper outline-none ring-copper-500/40 placeholder:text-mist/50 focus:ring-2";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputClass, props.className)} {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(inputClass, "min-h-32 resize-y", props.className)} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(inputClass, props.className)} {...props} />;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-2xl border border-white/[0.06] bg-ink-900/70 p-5 shadow-card", className)}>
      {children}
    </div>
  );
}

export function Pill({
  children,
  tone = "mist",
}: {
  children: ReactNode;
  tone?: "mist" | "copper" | "ok" | "warn" | "bad";
}) {
  const color = {
    mist: "bg-white/5 text-mist",
    copper: "bg-copper-500/15 text-copper-300",
    ok: "bg-emerald-400/10 text-emerald-300",
    warn: "bg-amber-400/10 text-amber-200",
    bad: "bg-red-400/10 text-red-300",
  }[tone];
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium tracking-wide", color)}>
      {children}
    </span>
  );
}

export function Score({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="font-mono text-xs text-mist">—</span>;
  return (
    <span className="score-ring grid h-11 w-11 shrink-0 place-items-center rounded-full" style={{ ["--score" as string]: value }}>
      <span className="grid h-9 w-9 place-items-center rounded-full bg-ink-900 font-serif text-sm text-paper">{value}</span>
    </span>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 px-8 py-16 text-center">
      <p className="font-serif text-2xl text-paper">{title}</p>
      {children ? <div className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-mist">{children}</div> : null}
    </div>
  );
}

export function Banner({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "bad" | "ok" }) {
  const color = { warn: "border-amber-400/20 bg-amber-400/5 text-amber-100", bad: "border-red-400/20 bg-red-400/5 text-red-200", ok: "border-emerald-400/20 bg-emerald-400/5 text-emerald-200" }[tone];
  return <div className={cn("rounded-xl border px-4 py-3 text-sm", color)}>{children}</div>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-mist">
      <span className="h-3 w-3 animate-pulse rounded-full bg-copper-500" />
      {label}
    </div>
  );
}

export function HealthDot({ health }: { health: string }) {
  const tone = health === "healthy" ? "bg-emerald-400" : health === "attention" || health === "failing" ? "bg-amber-400" : "bg-mist";
  return <span className={cn("inline-block h-2 w-2 rounded-full", tone)} title={health} />;
}
