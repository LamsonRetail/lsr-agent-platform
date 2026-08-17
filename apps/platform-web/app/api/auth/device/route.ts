import { NextResponse } from "next/server";
import { authHeaders, sessionToken } from "@/lib/session";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";

// Duyệt/từ chối phiên đăng nhập CLI — đi bằng PHIÊN của chính người duyệt.
export async function POST(req: Request) {
  if (!sessionToken()) return NextResponse.json({ error: "chưa đăng nhập" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const r = await fetch(`${P}/v1/auth/device/approve`, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ error: d?.detail || "không duyệt được" }, { status: r.status });
  return NextResponse.json(d);
}
