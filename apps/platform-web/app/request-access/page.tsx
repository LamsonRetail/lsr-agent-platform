import { authHeaders } from "@/lib/session";
import RequestAccessConsole from "@/components/RequestAccessConsole";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
export const dynamic = "force-dynamic";

export default async function RequestAccessPage({ searchParams }: { searchParams: { moi?: string } }) {
  let data: any = null;
  try {
    const r = await fetch(`${P}/v1/roles/catalog`, { cache: "no-store", headers: authHeaders() });
    if (r.ok) data = await r.json();
  } catch {}
  return (
    <div>
      <h1>Xin quyền truy cập</h1>
      <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
        Mặc định mọi tài khoản có quyền <b>user</b> (xem dashboard + config) trên tất cả agent.
        Cần chỉnh sửa/duyệt trên agent nào thì xin quyền tại đây — admin sẽ nhận thông báo và phê duyệt.
      </p>
      <RequestAccessConsole data={data} welcome={searchParams?.moi === "1"} />
    </div>
  );
}
