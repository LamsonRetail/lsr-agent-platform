import { accountsList, listAgents } from "@/lib/platform";
import { me } from "@/lib/session";
import AccountsConsole from "@/components/AccountsConsole";

export const dynamic = "force-dynamic";

export default async function AccountsPage() {
  const u = await me();
  if (u?.platform_role !== "admin") {
    return (<><h1>Tài khoản</h1>
      <p className="err">Chỉ admin platform mới xem được trang này.</p></>);
  }
  const [accounts, agents] = await Promise.all([accountsList(), listAgents()]);
  return (
    <>
      <h1>Tài khoản &amp; phân quyền</h1>
      <p className="lead">
        3 vai trò: <b>admin</b> (toàn quyền, duyệt việc) · <b>moderator</b> (tạo/sửa agent,
        publish prod phải được admin duyệt) · <b>user</b> (chỉ xem). Quyền cấp theo{" "}
        <b>toàn platform</b> hoặc <b>từng agent</b> — quyền hiệu lực là cái cao hơn.
      </p>
      <AccountsConsole accounts={accounts} agents={agents} meEmail={u.email} />
    </>
  );
}
