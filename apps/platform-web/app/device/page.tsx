import DeviceApprove from "@/components/DeviceApprove";
import { me } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function DevicePage({ searchParams }: { searchParams: { code?: string } }) {
  const u = await me();
  return (
    <div style={{ maxWidth: 460, margin: "6vh auto" }}>
      <h1>Duyệt đăng nhập CLI</h1>
      <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
        Terminal / Claude Code của bạn đang xin quyền dùng platform <b>với đúng vai trò của
        bạn</b>. Chỉ duyệt khi mã bên dưới khớp với mã hiện trên màn hình terminal.
      </p>
      <DeviceApprove code={searchParams?.code || ""} email={u?.email || ""} />
    </div>
  );
}
