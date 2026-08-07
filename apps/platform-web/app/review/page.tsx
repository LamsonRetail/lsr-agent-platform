import { pendingKnowledge, openConflicts, sharedBrain, reviewers } from "@/lib/platform";
import { ReviewPanel } from "@/components/ReviewActions";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const [items, conflicts, brain, revs] = await Promise.all([
    pendingKnowledge(), openConflicts(), sharedBrain(), reviewers(),
  ]);

  return (
    <>
      <h1>Duyệt tri thức (LSR Brain)</h1>
      <p className="lead">
        LSR Brain chạy <b>hàng tuần (Chủ nhật 20h)</b>, tổng hợp second brain các team
        và <b>đề xuất</b> tri thức. Người phụ trách chuyên môn duyệt thì mới vào shared brain.
        Shared beliefs <b>chỉ admin</b> sửa.
      </p>

      <div className="kpis">
        <div className="kpi"><div className="l">Chờ duyệt</div><div className="v">{items.length}</div></div>
        <div className="kpi"><div className="l">Mâu thuẫn mở</div><div className="v">{conflicts.length}</div></div>
        <div className="kpi"><div className="l">Shared beliefs</div><div className="v">{brain.beliefs?.length ?? 0}</div></div>
        <div className="kpi"><div className="l">Tri thức đã duyệt</div><div className="v">{brain.knowledge?.length ?? 0}</div></div>
      </div>

      <ReviewPanel items={items} conflicts={conflicts} />

      <h3>Người phụ trách theo chuyên môn</h3>
      <table>
        <thead><tr><th>Email</th><th>Chuyên môn (domain)</th><th>Do ai cấp</th></tr></thead>
        <tbody>
          {revs.length === 0 && <tr><td colSpan={3} className="muted">Chưa cấp quyền cho ai. Admin dùng POST /v1/knowledge/reviewers.</td></tr>}
          {revs.map((r: any, i: number) => (
            <tr key={i}><td>{r.email}</td><td><span className="b b-series">{r.domain}</span></td><td className="muted">{r.added_by}</td></tr>
          ))}
        </tbody>
      </table>

      <h3>Shared beliefs (chỉ admin sửa)</h3>
      <table>
        <thead><tr><th>Niềm tin</th><th>Chuyên môn</th><th className="n">Version</th></tr></thead>
        <tbody>
          {(brain.beliefs ?? []).length === 0 && <tr><td colSpan={3} className="muted">Chưa có belief nào.</td></tr>}
          {(brain.beliefs ?? []).map((b: any) => (
            <tr key={b.belief_id}>
              <td><b>{b.title || b.belief_id}</b><div className="muted">{b.statement}</div></td>
              <td>{b.domain || "—"}</td>
              <td className="n">v{b.version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
