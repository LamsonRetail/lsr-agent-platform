import { NextResponse } from "next/server";
import { PLATFORM_URL, AGENT_TOKEN } from "@/lib/platform";
export async function POST(req) {
  const { path, payload } = await req.json().catch(() => ({}));
  if (typeof path !== "string" || !path.startsWith("/v1/self/brain/")) return NextResponse.json({ error: "path không hợp lệ" }, { status: 400 });
  const r = await fetch(PLATFORM_URL + path, { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + AGENT_TOKEN }, body: JSON.stringify(payload || {}) });
  const d = await r.json().catch(() => ({})); return NextResponse.json(d, { status: r.status });
}
