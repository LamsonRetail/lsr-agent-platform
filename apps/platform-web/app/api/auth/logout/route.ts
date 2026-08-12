import { NextResponse } from "next/server";
import { SESSION_COOKIE, authHeaders } from "@/lib/session";
const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";

export async function POST() {
  try { await fetch(`${P}/v1/auth/logout`, { method: "POST", headers: authHeaders() }); } catch {}
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
