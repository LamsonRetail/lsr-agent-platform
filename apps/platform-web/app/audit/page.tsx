import { auditLog } from "@/lib/platform";

export const dynamic = "force-dynamic";

const ACTION_LABEL: Record<string, string> = {
  register: "Đăng ký agent", set_status: "Đổi trạng thái", set_quota: "Đặt hạn mức",
  review_knowledge: "Duyệt tri thức", resolve_conflict: "Xử lý mâu thuẫn",
  upsert_belief: "Sửa shared belief", add_reviewer: "Cấp quyền reviewer",
  golden_case: "Thêm golden case", regression_run: "Chạy hồi quy", delete_agent: "Gỡ agent",
};

export default async function AuditPage() {
  const rows = await auditLog("?limit=200");
  return (
    <>
      <h1>Nhật ký thao tác (Audit log)</h1>
      <p className="lead">Ai làm gì, khi nào — toàn platform. Phục vụ quản trị &amp; tuân thủ.</p>
      <table>
        <thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Đối tượng</th><th>Chi tiết</th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={5} className="muted">Chưa có bản ghi.</td></tr>}
          {rows.map((r: any, i: number) => (
            <tr key={i}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(r.at).toLocaleString("vi-VN")}</td>
              <td>{r.actor}</td>
              <td><b>{ACTION_LABEL[r.action] || r.action}</b></td>
              <td>{r.target_type}: <span className="muted">{r.target_id}</span></td>
              <td className="muted" style={{ fontSize: 12 }}>
                {r.detail && Object.keys(r.detail).length > 0
                  ? Object.entries(r.detail).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" · ")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
