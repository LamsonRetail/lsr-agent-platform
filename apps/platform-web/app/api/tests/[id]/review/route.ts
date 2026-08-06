import { NextResponse } from "next/server";
import { adminPost } from "@/lib/platform";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const body = await req.json().catch(() => ({}));
  try {
    return NextResponse.json(await adminPost(`/v1/tests/${params.id}/review`, body));
  } catch (e: any) {
    return NextResponse.json({ error: e.data ?? String(e) }, { status: e.status ?? 500 });
  }
}
