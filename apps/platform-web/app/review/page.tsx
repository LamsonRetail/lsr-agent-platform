import { pendingKnowledge, sharedBrain, reviewers, knowledgeDomains } from "@/lib/platform";
import { ReviewTabs } from "@/components/ReviewTabs";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const [items, brain, revs, domains] = await Promise.all([
    pendingKnowledge(), sharedBrain(), reviewers(), knowledgeDomains(),
  ]);

  return (
    <>
      <h1>Duyệt tri thức (LSR Brain)</h1>
      <p className="lead">
        LSR Brain chạy <b>hàng tuần (Chủ nhật 20h)</b>, tổng hợp second brain các team và
        <b> đề xuất</b> tri thức. Người phụ trách chuyên môn duyệt thì mới vào shared brain.
        Shared beliefs <b>chỉ admin</b> sửa.
        <br />
        <span className="muted">
          Mâu thuẫn giữa shared brain và brain của agent được xử lý ở <b>backend của từng
          agent</b> (agent owner xác nhận), không nằm ở đây.
        </span>
      </p>

      <div className="kpis">
        <div className="kpi"><div className="l">Chờ duyệt</div><div className="v">{items.length}</div></div>
        <div className="kpi"><div className="l">Shared beliefs</div><div className="v">{brain.beliefs?.length ?? 0}</div></div>
        <div className="kpi"><div className="l">Tri thức đã duyệt</div><div className="v">{brain.knowledge?.length ?? 0}</div></div>
        <div className="kpi"><div className="l">Chuyên môn</div><div className="v">{domains.length}</div></div>
      </div>

      <ReviewTabs items={items} beliefs={brain.beliefs ?? []} reviewers={revs} domains={domains} />
    </>
  );
}
