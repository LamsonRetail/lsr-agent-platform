import { NextResponse } from "next/server";
import { publicBase } from "@/lib/url";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";

// C8 — User Identity Broker: Lark redirect về đây sau khi ADMIN đăng nhập bằng chính
// account của agent (vd ann_legal@hapas.vn) và bấm đồng ý. Route này chỉ chuyển code
// về platform; token do platform giữ (mã hoá) — trình duyệt và console KHÔNG thấy token,
// và cũng không đặt cookie phiên nào (đây không phải luồng đăng nhập console).
export async function GET(req: Request) {
  const u = new URL(req.url);
  const base = publicBase(req);
  const code = u.searchParams.get("code") || "";
  const state = u.searchParams.get("state") || "";
  const err = (m: string) => NextResponse.redirect(`${base}/lark-user?err=${encodeURIComponent(m)}`);
  if (!code || !state) return err("thiếu code/state");
  try {
    const r = await fetch(`${P}/v1/lark/user/authorize/callback`, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(GATEWAY ? { "X-Gateway-Token": GATEWAY } : {}) },
      body: JSON.stringify({ code, state }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return err(d?.detail || "Lark từ chối");
    return NextResponse.redirect(`${base}/lark-user?ok=${encodeURIComponent(d.subject || "")}`);
  } catch {
    return err("không gọi được platform");
  }
}
