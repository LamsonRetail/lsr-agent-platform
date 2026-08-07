import { NextResponse } from "next/server";
import { PLATFORM_URL } from "@/lib/platform";

// Review knowledge KHÔNG dùng admin token: quyền được kiểm theo domain của reviewer
// ở Platform API (403 nếu sai chuyên môn).
export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json().catch(() => ({}));
  const gw = process.env.LSR_GATEWAY_TOKEN;
  const r = await fetch(`${PLATFORM_URL}/v1/knowledge/items/${params.id}/review`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(gw ? { "X-Gateway-Token": gw } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return NextResponse.json(data, { status: r.status });
}
