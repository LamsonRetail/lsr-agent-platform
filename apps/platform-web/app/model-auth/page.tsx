import { modelCredentials } from "@/lib/platform";
import ModelAuthConsole from "@/components/ModelAuthConsole";

export const dynamic = "force-dynamic";

export default async function ModelAuthPage() {
  const data = await modelCredentials();
  return (
    <>
      <h1>Model Auth · Pool credential</h1>
      <p className="lead">
        Agent lấy quyền gọi model theo bậc thang: subscription riêng → pool chung → API (litellm).
        Hết hạn mức thì account vào cooldown và tự chuyển account khác. Secret chỉ nằm trên VM —
        bảng này chỉ hiển thị trạng thái, không bao giờ lộ token.
      </p>
      <ModelAuthConsole data={data} />
    </>
  );
}
