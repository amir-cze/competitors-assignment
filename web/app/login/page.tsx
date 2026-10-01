"use client";

import Link from "next/link";
import { SignIn } from "@/components/sign-in";

export default function LoginPage() {
  return (
    <>
      <SignIn
        title="The briefing is in."
        lede="A shared password for Marketing, Product and R&D. What competitors published that actually matters — not everything they published."
        label="Password"
        placeholder="Shared business password"
        endpoint="/api/auth/login"
        bodyKey="password"
        next="/"
      />
      <p className="fixed bottom-6 right-6 text-xs text-mist">
        Operator? <Link href="/ops/login" className="text-copper-300">Sign in to /ops</Link>
      </p>
    </>
  );
}
