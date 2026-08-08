import { brainGraph } from "@/lib/platform";
import Brain3D from "@/components/Brain3D";

export const dynamic = "force-dynamic";

export default async function Brain3DPage() {
  const data = await brainGraph();
  return (
    <>
      <h1>Shared Brain 3D</h1>
      <p className="lead">
        Đồ thị tri thức chung: <b>chuyên môn</b> · <b>shared belief</b> · <b>tri thức đã duyệt</b> · <b>team nguồn</b>.
        Xoay/zoom bằng chuột; <b>click một node</b> để xem chi tiết và mở nguồn Lark đối chứng.
        {data.nodes.length === 0 && " (Chưa có tri thức nào được duyệt — đồ thị sẽ hiện khi shared brain có dữ liệu.)"}
      </p>
      <Brain3D data={data} />
    </>
  );
}
