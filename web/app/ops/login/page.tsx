"use client";

import { SignIn } from "@/components/sign-in";

export default function OpsLogin() {
  return (
    <SignIn
      title="Operator desk."
      lede="Sources, runs, prompts, evals. Separate token from the business briefing."
      label="Operator token"
      placeholder="OPS_TOKEN"
      endpoint="/api/ops/auth/login"
      bodyKey="token"
      next="/ops"
    />
  );
}
