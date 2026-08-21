import { NextResponse } from "next/server";
import { publicBase } from "@/lib/url";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";

// Bấm "Đăng nhập bằng Lark" → lấy URL authorize từ platform → đẩy trình duyệt sang Lark.
export async function GET(req: Request) {
  const base = publicBase(req);
  try {
    const r = await fetch(`${P}/v1/auth/lark/start`, {
      cache: "no-store",
      headers: GATEWAY ? { "X-Gateway-Token": GATEWAY } : {},
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.url) {
      const msg = encodeURIComponent(d?.detail || "Lark OAuth chưa sẵn sàng");
      return NextResponse.redirect(`${base}/login?err=${msg}`);
    }
    return NextResponse.redirect(d.url);
  } catch {
    return NextResponse.redirect(`${base}/login?err=` + encodeURIComponent("không gọi được platform"));
  }
}
