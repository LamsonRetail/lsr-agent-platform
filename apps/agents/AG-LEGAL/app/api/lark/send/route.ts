import { NextResponse } from "next/server";
import { larkSend } from "@/lib/lark";
export async function POST(req) {
  const { to, text, markdown, to_type } = await req.json().catch(() => ({}));
  if (!to || !(text || markdown)) return NextResponse.json({ error: "cần 'to' và text|markdown" }, { status: 400 });
  const d = await larkSend(to, text || "", { markdown, to_type });
  return NextResponse.json(d);
}
