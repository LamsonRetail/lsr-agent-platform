import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";

export async function POST(req: Request) {
  const { email, password } = await req.json().catch(() => ({} as any));
  const r = await fetch(`${P}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(GATEWAY ? { "X-Gateway-Token": GATEWAY } : {}) },
    body: JSON.stringify({ email, password }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ error: d?.detail || "đăng nhập thất bại" }, { status: r.status });

  const res = NextResponse.json({
    ok: true, name: d.name, role: d.role, must_change_pw: d.must_change_pw,
  });
  // Token chỉ nằm trong cookie httpOnly — JS phía client không đọc được.
  res.cookies.set(SESSION_COOKIE, d.token, {
    httpOnly: true, sameSite: "lax", secure: true, path: "/",
    maxAge: (d.expires_hours || 12) * 3600,
  });
  return res;
}
