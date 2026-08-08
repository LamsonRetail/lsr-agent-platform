import { brainItems, brainSkills, brainPolicies, brainLinks } from "@/lib/platform";
import BrainConsole from "@/components/BrainConsole";

export const dynamic = "force-dynamic";

export default async function BrainPage() {
  const [items, skills, policies, links] = await Promise.all([
    brainItems("?scope=shared"), brainSkills("?scope=shared"), brainPolicies(), brainLinks(),
  ]);
  return (
    <>
      <h1>Brain Console</h1>
      <p className="lead">
        Quản lý tri thức · kỹ năng · chính sách của tổ chức — nhiều góc nhìn, import, liên kết (graph),
        duyệt/sửa/xoá. Mỗi mục có link Lark đối chứng. (Đang thao tác quyền admin.)
      </p>
      <BrainConsole scope="shared" items={items} skills={skills} policies={policies} links={links} />
    </>
  );
}
