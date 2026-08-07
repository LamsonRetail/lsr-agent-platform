import { NextResponse } from "next/server";
import { adminPost } from "@/lib/platform";

// Proxy admin 1 cửa: body { path, payload } -> Platform API (giữ token server-side).
const ALLOWED = [
  /^\/v1\/shared-beliefs$/,
  /^\/v1\/shared-beliefs\/suggest$/,
  /^\/v1\/shared-beliefs\/[^/]+\/delete$/,
  /^\/v1\/knowledge\/reviewers$/,
  /^\/v1\/knowledge\/reviewers\/remove$/,
  /^\/v1\/knowledge\/domains$/,
  /^\/v1\/knowledge\/domains\/[^/]+\/delete$/,
];

export async function POST(req: Request) {
  const { path, payload } = await req.json().catch(() => ({} as any));
  if (typeof path !== "string" || !ALLOWED.some((re) => re.test(path))) {
    return NextResponse.json({ error: "path không được phép" }, { status: 400 });
  }
  try {
    return NextResponse.json(await adminPost(path, payload ?? {}));
  } catch (e: any) {
    return NextResponse.json({ error: e.data ?? String(e) }, { status: e.status ?? 500 });
  }
}
