import { NextRequest } from "next/server";

const API = process.env.API_INTERNAL_URL || "http://localhost:8000";

async function proxy(req: NextRequest, path: string[]) {
  const url = new URL(req.url);
  const target = `${API}/api/${path.join("/")}${url.search}`;
  const headers = new Headers();
  const cookie = req.headers.get("cookie");
  const contentType = req.headers.get("content-type");
  const ops = req.headers.get("x-ops-token");
  if (cookie) headers.set("cookie", cookie);
  if (contentType) headers.set("content-type", contentType);
  if (ops) headers.set("x-ops-token", ops);

  const hasBody = !["GET", "HEAD"].includes(req.method);
  const res = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });

  const out = new Headers();
  res.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (["content-encoding", "transfer-encoding", "connection", "set-cookie"].includes(lower)) return;
    out.append(key, value);
  });
  for (const cookie of res.headers.getSetCookie()) out.append("set-cookie", cookie);
  return new Response(res.body, { status: res.status, headers: out });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
