import { NextResponse } from "next/server";
import { authHeaders } from "@/lib/session";
const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const r = await fetch(`${P}/v1/auth/change-password`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  return NextResponse.json(r.ok ? d : { error: d?.detail || "đổi mật khẩu thất bại" }, { status: r.status });
}
