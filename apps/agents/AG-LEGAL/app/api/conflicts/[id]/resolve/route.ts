import { NextResponse } from "next/server";
import { PLATFORM_URL } from "@/lib/platform";
export async function POST(req, { params }) {
  const body = await req.json().catch(() => ({}));
  const tok = process.env.LSR_AGENT_TOKEN || "";
  const r = await fetch(PLATFORM_URL + "/v1/self/conflicts/" + params.id + "/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(tok ? { Authorization: "Bearer " + tok } : {}) },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return NextResponse.json(data, { status: r.status });
}
