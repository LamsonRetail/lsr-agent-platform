import { listTests, listAttempts, listTraining } from "@/lib/platform";
import { ReviewButton, AssignForm, GenerateForm, TrainingImportForm } from "@/components/Actions";

export const dynamic = "force-dynamic";

function statusBadge(s: string) {
  const kind = s === "active" ? "good" : s === "in_review" ? "warning" : "neutral";
  return <span className={`b b-${kind}`}>{s}</span>;
}

export default async function TestLearnPage() {
  const [tests, attempts, training] = await Promise.all([listTests(), listAttempts(), listTraining()]);
  const nActive = tests.filter((t: any) => t.status === "active").length;
  const nReview = tests.filter((t: any) => t.status === "draft" || t.status === "in_review").length;

  return (
    <>
      <h1>Test &amp; Learn</h1>
      <p className="lead">Sinh bài test (auto) → <b>người duyệt mới active</b> → giao cho agent/nhân sự → trượt thì training. Tất cả là thao tác thật qua Platform API.</p>

      <GenerateForm />

      <div className="kpis">
        <div className="kpi"><div className="l">Tổng bài test</div><div className="v">{tests.length}</div></div>
        <div className="kpi"><div className="l">Đang active</div><div className="v">{nActive}</div></div>
        <div className="kpi"><div className="l">Chờ review</div><div className="v">{nReview}</div></div>
      </div>

      <h3>Bài test</h3>
      <table>
        <thead><tr><th>Bài test</th><th>Nguồn</th><th>Trạng thái</th><th className="n">Số câu</th>
          <th>Người duyệt</th><th>Hành động</th></tr></thead>
        <tbody>
          {tests.length === 0 && <tr><td colSpan={6} className="muted">Chưa có bài test.</td></tr>}
          {tests.map((t: any) => (
            <tr key={t.test_id}>
              <td><b>{t.title}</b><div className="muted">{t.test_id}</div></td>
              <td><span className="b b-neutral">{t.source}</span></td>
              <td>{statusBadge(t.status)}</td>
              <td className="n">{t.num_questions ?? 0}</td>
              <td>{t.reviewed_by || "—"}</td>
              <td>{t.status === "active" ? <AssignForm testId={t.test_id} /> : <ReviewButton testId={t.test_id} />}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Kết quả làm bài</h3>
      <table>
        <thead><tr><th>Người làm</th><th>Loại</th><th>Bài</th><th>Điểm</th><th>Kết quả</th></tr></thead>
        <tbody>
          {attempts.length === 0 && <tr><td colSpan={5} className="muted">Chưa có lượt làm bài.</td></tr>}
          {attempts.map((a: any) => {
            const pct = Math.round((a.score || 0) * 100);
            return (
              <tr key={a.attempt_id}>
                <td><b>{a.taker_id}</b></td>
                <td><span className={`b ${a.taker_type === "agent" ? "b-series" : "b-neutral"}`}>{a.taker_type}</span></td>
                <td>{a.test_id}</td>
                <td><span className="bar"><i style={{ width: pct + "%" }} /><span>{pct}</span></span></td>
                <td><span className={`b ${a.passed ? "b-good" : "b-critical"}`}>{a.passed ? "pass" : "fail"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h3>Training (HR)</h3>
      <TrainingImportForm />
      <table>
        <thead><tr><th>Tài liệu</th><th>Tags</th><th>Nguồn</th><th>File</th></tr></thead>
        <tbody>
          {training.length === 0 && <tr><td colSpan={4} className="muted">Chưa có tài liệu.</td></tr>}
          {training.map((m: any) => (
            <tr key={m.material_id}>
              <td><b>{m.title}</b></td>
              <td>{(m.tags || []).join(", ")}</td>
              <td>{m.provided_by}</td>
              <td className="muted">{m.source_file || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
