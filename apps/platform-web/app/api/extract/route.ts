import { NextResponse } from "next/server";
import { adminForm } from "@/lib/platform";

// Nhận file (PDF/DOCX/TXT) từ trình duyệt → chuyển sang Platform API trích text server-side.
export async function POST(req: Request) {
  try {
    const inForm = await req.formData();
    const file = inForm.get("file");
    if (!file) return NextResponse.json({ error: "thiếu file" }, { status: 422 });
    const out = new FormData();
    out.append("file", file as Blob, (file as any).name || "upload");
    return NextResponse.json(await adminForm("/v1/extract", out));
  } catch (e: any) {
    return NextResponse.json({ error: e.data ?? String(e) }, { status: e.status ?? 500 });
  }
}
