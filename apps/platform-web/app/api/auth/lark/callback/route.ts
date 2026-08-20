import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";
import { publicBase } from "@/lib/url";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";

// Lark redirect về đây sau khi người dùng đồng ý. Đổi code lấy phiên (server-to-server —
// session token không bao giờ xuất hiện trên URL trình duyệt), set cookie httpOnly.
export async function GET(req: Request) {
  const u = new URL(req.url);
  const base = publicBase(req);
  const code = u.searchParams.get("code") || "";
  const state = u.searchParams.get("state") || "";
  // C8 (User Identity Broker) dùng CHUNG redirect URI này vì Lark chỉ nhận URI đã đăng
  // ký trong console. State của C8 bắt đầu bằng "u", state đăng nhập là timestamp — và
  // hai luồng ký HMAC khác nhau nên platform vẫn từ chối nếu bị tráo.
  if (state.startsWith("u")) {
    try {
      const r = await fetch(`${P}/v1/lark/user/authorize/callback`, {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", ...(GATEWAY ? { "X-Gateway-Token": GATEWAY } : {}) },
        body: JSON.stringify({ code, state }),
      });
      const d = await r.json().catch(() => ({}));
      const qs = r.ok
        ? `ok=${encodeURIComponent(d.subject || "")}`
        : `err=${encodeURIComponent(d?.detail || "Lark từ chối")}`;
      return NextResponse.redirect(`${base}/lark-user?${qs}`);
    } catch {
      return NextResponse.redirect(`${base}/lark-user?err=` + encodeURIComponent("không gọi được platform"));
    }
  }
  try {
    const r = await fetch(`${P}/v1/auth/lark/callback`, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(GATEWAY ? { "X-Gateway-Token": GATEWAY } : {}) },
      body: JSON.stringify({ code, state }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = encodeURIComponent(d?.detail || "đăng nhập Lark thất bại");
      return NextResponse.redirect(`${base}/login?err=${msg}`);
    }
    // Tài khoản mới (hoặc chưa được cấp vai trò riêng) → đưa đến trang xin quyền.
    const dest = d.provisioned || !d.has_roles ? "/request-access?moi=1" : "/";
    const res = NextResponse.redirect(`${base}${dest}`);
    res.cookies.set(SESSION_COOKIE, d.token, {
      httpOnly: true, sameSite: "lax", secure: true, path: "/",
      maxAge: (d.expires_hours || 12) * 3600,
    });
    return res;
  } catch {
    return NextResponse.redirect(`${base}/login?err=` + encodeURIComponent("không gọi được platform"));
  }
}
