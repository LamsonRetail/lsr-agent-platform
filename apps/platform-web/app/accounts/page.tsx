import { accountsList, listAgents } from "@/lib/platform";
import { me, authHeaders } from "@/lib/session";
import AccountsConsole from "@/components/AccountsConsole";
import RoleRequestsPanel from "@/components/RoleRequestsPanel";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
export const dynamic = "force-dynamic";

async function pendingRoleRequests(): Promise<any[]> {
  try {
    const r = await fetch(`${P}/v1/roles/requests?status=pending`,
                          { cache: "no-store", headers: authHeaders() });
    return r.ok ? await r.json() : [];
  } catch { return []; }
}

export default async function AccountsPage() {
  const u = await me();
  if (u?.platform_role !== "admin") {
    return (<><h1>Tài khoản</h1>
      <p className="err">Chỉ admin platform mới xem được trang này.</p></>);
  }
  const [accounts, agents, roleRequests] = await Promise.all([
    accountsList(), listAgents(), pendingRoleRequests()]);
  return (
    <>
      <h1>Tài khoản &amp; phân quyền</h1>
      <p className="lead">
        3 vai trò: <b>admin</b> (toàn quyền, duyệt việc) · <b>moderator</b> (tạo/sửa agent,
        publish prod phải được admin duyệt) · <b>user</b> (chỉ xem — MẶC ĐỊNH cho mọi tài
        khoản trên mọi agent). Quyền cấp theo <b>toàn platform</b> hoặc <b>từng agent</b> —
        một người có thể là user platform, admin agent này và moderator agent khác.
      </p>
      <RoleRequestsPanel requests={roleRequests} />
      <AccountsConsole accounts={accounts} agents={agents} meEmail={u.email} />
    </>
  );
}
