import { me } from "@/lib/session";
import NoCodeWizard from "@/components/NoCodeWizard";

export const dynamic = "force-dynamic";

export default async function NewAgentPage() {
  const u = await me();
  if (!u?.can_create_agent) {
    return (<><h1>Tạo agent</h1>
      <p className="err">Cần quyền moderator trở lên. Liên hệ admin để được cấp quyền.</p></>);
  }
  return (
    <>
      <h1>Tạo agent mới (không cần code)</h1>
      <p className="lead">
        Điền use case → test case → hành vi → kênh. Platform tự chạy agent, bạn không phải
        viết dòng code nào. Publish lên <b>prod</b> sẽ cần admin duyệt.
      </p>
      <NoCodeWizard defaultOwner={u.email} />
    </>
  );
}
