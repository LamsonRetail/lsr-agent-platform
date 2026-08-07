import { NextResponse } from "next/server";
import { adminPost } from "@/lib/platform";

export async function POST() {
  try {
    return NextResponse.json(await adminPost("/v1/cost/check-alerts", {}));
  } catch (e: any) {
    return NextResponse.json({ error: e.data ?? String(e) }, { status: e.status ?? 500 });
  }
}
