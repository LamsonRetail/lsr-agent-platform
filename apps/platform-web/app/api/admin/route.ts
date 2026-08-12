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
  // Brain v2
  /^\/v1\/brain\/items$/,
  /^\/v1\/brain\/items\/[^/]+\/review$/,
  /^\/v1\/brain\/items\/[^/]+\/delete$/,
  /^\/v1\/brain\/skills$/,
  /^\/v1\/brain\/links$/,
  /^\/v1\/brain\/links\/[^/]+\/confirm$/,
  /^\/v1\/brain\/links\/[^/]+\/delete$/,
  // P1: ingress — routing + jobs/DLQ
  /^\/v1\/routing$/,
  /^\/v1\/routing\/[^/]+\/toggle$/,
  /^\/v1\/jobs\/[^/]+\/replay$/,
  // P2: model auth — credential status (secret KHÔNG bao giờ qua đây; chỉ trạng thái)
  /^\/v1\/model-auth\/credentials\/[^/]+\/status$/,
  // P3: agent versions — tạo draft / publish / rollback
  /^\/v1\/agents\/[^/]+\/versions$/,
  /^\/v1\/agents\/[^/]+\/versions\/[0-9]+\/publish$/,
  /^\/v1\/agents\/[^/]+\/rollback$/,
  // P5/P6: cấp-thu quyền connector và quyền gọi agent-agent
  /^\/v1\/connectors\/grant$/,
  /^\/v1\/a2a\/grant$/,
  // P7: duyệt/từ chối đề xuất của platform agent + dựng lại mart
  /^\/v1\/actions\/[0-9]+\/decide$/,
  /^\/v1\/mart\/rebuild$/,
  // P9: tạo agent no-code + sửa use case/test case
  /^\/v1\/agents\/nocode$/,
  /^\/v1\/agents\/[^/]+\/spec$/,
  // P8: quản lý tài khoản + phân quyền (API tự kiểm quyền admin)
  /^\/v1\/accounts$/,
  /^\/v1\/accounts\/[^/]+\/roles$/,
  /^\/v1\/accounts\/[^/]+\/update$/,
  /^\/v1\/accounts\/[^/]+\/status$/,
  /^\/v1\/accounts\/[^/]+\/reset-password$/,
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
