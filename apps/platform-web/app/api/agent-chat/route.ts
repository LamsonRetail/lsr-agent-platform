import { NextResponse } from "next/server";
import { adminPost, PLATFORM_URL } from "@/lib/platform";
import { authHeaders } from "@/lib/session";

// Chat thử với agent NGAY TRONG console — dùng admin token server-side, người dùng
// không cần token agent. Đi qua đúng ingress chung (Chat API) nên vẫn có
// telemetry/quota/audit/kill-switch như kênh thật.
export async function POST(req: Request) {
  const { agent_id, text, session_id } = await req.json().catch(() => ({} as any));
  if (!agent_id || !text) {
    return NextResponse.json({ error: "cần agent_id + text" }, { status: 400 });
  }
  try {
    const sent = await adminPost(`/v1/chat/${agent_id}/messages`, { text, session_id });
    // Chờ agent trả lời (poll job_events qua API kết quả) — tối đa ~20s.
    const sid = sent.session_id;
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 1000));
      const r = await fetch(`${PLATFORM_URL}/v1/jobs?agent_id=${agent_id}&limit=5`, {
        cache: "no-store",
        headers: authHeaders(),
      });
      const jobs = await r.json().catch(() => []);
      const job = (jobs || []).find((j: any) => j.session_id === sid);
      if (job && ["done", "failed", "dlq"].includes(job.status)) {
        const ev = await fetch(`${PLATFORM_URL}/v1/jobs/${job.id}/events`, {
          cache: "no-store",
          headers: authHeaders(),
        }).then((x) => x.json()).catch(() => []);
        const msg = (ev || []).filter((e: any) => e.kind === "message").pop();
        return NextResponse.json({
          session_id: sid,
          reply: msg?.data?.text || (job.status === "done" ? "(agent không trả nội dung)" : null),
          status: job.status,
          error: job.last_error,
        });
      }
    }
    return NextResponse.json({
      session_id: sid, reply: null, status: "timeout",
      error: "Agent chưa trả lời sau 20s — kiểm tra consumer có đang chạy không (Console → Ingress).",
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.data ?? String(e) }, { status: e.status ?? 500 });
  }
}
