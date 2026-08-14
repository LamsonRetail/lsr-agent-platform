import { NextResponse } from "next/server";
import { authHeaders, sessionToken } from "@/lib/session";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";

// Gửi yêu cầu xin quyền — đi bằng PHIÊN của người dùng (platform tự kiểm & audit đúng người).
export async function POST(req: Request) {
  if (!sessionToken()) return NextResponse.json({ error: "chưa đăng nhập" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const r = await fetch(`${P}/v1/roles/request`, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ error: d?.detail || "gửi yêu cầu thất bại" }, { status: r.status });
  return NextResponse.json(d);
}
