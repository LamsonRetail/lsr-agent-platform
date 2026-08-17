import { NextResponse } from "next/server";
import { authHeaders, sessionToken } from "@/lib/session";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";

// Admin duyệt/từ chối yêu cầu phân quyền — đi bằng phiên admin (API tự kiểm quyền + tách vai).
export async function POST(req: Request) {
  if (!sessionToken()) return NextResponse.json({ error: "chưa đăng nhập" }, { status: 401 });
  const { id, approve, note } = await req.json().catch(() => ({} as any));
  if (!id) return NextResponse.json({ error: "thiếu id" }, { status: 400 });
  const r = await fetch(`${P}/v1/roles/requests/${id}/decide`, {
    method: "POST", cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ approve, note }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ error: d?.detail || "duyệt thất bại" }, { status: r.status });
  return NextResponse.json(d);
}
