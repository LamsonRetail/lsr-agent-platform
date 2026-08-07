import { goldenCases, regressionRuns } from "@/lib/platform";
import { GoldenCaseForm } from "@/components/OpsActions";

export const dynamic = "force-dynamic";

export default async function GoldenPage() {
  const [cases, runs] = await Promise.all([goldenCases(), regressionRuns()]);
  return (
    <>
      <h1>Golden set &amp; Hồi quy</h1>
      <p className="lead">
        Bộ ca chuẩn để test hồi quy khi đổi prompt/model. Chấm deterministic
        (exact/regex/numeric/contains) + <code>llm_judge</code> (tùy chọn, cần cấu hình JUDGE_URL).
        Chạy hồi quy qua API <code>POST /v1/regression/run</code> (gửi answers theo case_id).
      </p>

      <GoldenCaseForm />

      <h3>Ca golden ({cases.length})</h3>
      <table>
        <thead><tr><th>ID</th><th>Skill</th><th>Prompt</th><th>Mong đợi</th><th>Kiểu</th><th>Active</th></tr></thead>
        <tbody>
          {cases.length === 0 && <tr><td colSpan={6} className="muted">Chưa có ca golden.</td></tr>}
          {cases.map((c: any) => (
            <tr key={c.case_id}>
              <td className="muted">{c.case_id}</td>
              <td>{c.skill}</td>
              <td style={{ maxWidth: 260 }}>{c.prompt}</td>
              <td style={{ maxWidth: 200 }} className="muted">{c.expected}</td>
              <td>{c.atype}</td>
              <td>{c.active ? "✓" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Lần chạy hồi quy gần đây</h3>
      <table>
        <thead><tr><th>Thời điểm</th><th>Đối tượng</th><th>Skill</th>
          <th className="n">Điểm</th><th className="n">Pass/Total</th><th>Kết quả</th><th>Bởi</th></tr></thead>
        <tbody>
          {runs.length === 0 && <tr><td colSpan={7} className="muted">Chưa có lần chạy nào.</td></tr>}
          {runs.map((r: any) => (
            <tr key={r.run_id}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(r.at).toLocaleString("vi-VN")}</td>
              <td>{r.target_type}: <span className="muted">{r.target_id || "—"}</span></td>
              <td>{r.skill || "—"}</td>
              <td className="n">{(Number(r.score) * 100).toFixed(0)}%</td>
              <td className="n">{r.n_pass}/{r.n_total}</td>
              <td><span className={`b b-${r.passed ? "good" : "critical"}`}>{r.passed ? "PASS" : "FAIL"}</span></td>
              <td className="muted">{r.run_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
