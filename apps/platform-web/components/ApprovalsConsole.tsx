"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const ST: Record<string, string> = {
  pending: "#c98a00", approved: "#2e9e5b", rejected: "#8a8f98",
  expired: "#8a8f98", auto: "#4a7edb",
};
const RISK: Record<string, string> = { high: "#d1495b", low: "#4a7edb" };

export default function ApprovalsConsole({ actions, kpi }: { actions: any[]; kpi: any }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const pending = actions.filter((a: any) => a.status === "pending");
  const history = actions.filter((a: any) => a.status !== "pending").slice(0, 20);

  async function call(path: string, payload: any = {}) {
    setBusy(true);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, payload }),
      });
      if (!r.ok) throw new Error(JSON.stringify((await r.json()).error));
      router.refresh();
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Chờ duyệt {pending.length > 0 && <span style={{ color: "#c98a00" }}>({pending.length})</span>}</h2>
        {pending.length === 0
          ? <p className="muted">Không có đề xuất nào đang chờ.</p>
          : <table>
            <thead><tr><th>#</th><th>Đề xuất bởi</th><th>Hành động</th><th>Lý do</th><th>Hết hạn</th><th></th></tr></thead>
            <tbody>
              {pending.map((a: any) => (
                <tr key={a.id}>
                  <td>{a.id}</td>
                  <td className="mono">{a.proposed_by}</td>
                  <td>
                    <span style={{ color: RISK[a.risk], fontWeight: 600 }}>{a.action}</span>
                    <div className="mono muted" style={{ fontSize: 11 }}>{JSON.stringify(a.params)}</div>
                  </td>
                  <td style={{ fontSize: 12, maxWidth: 260 }}>{a.reason || "—"}</td>
                  <td className="muted" style={{ fontSize: 12 }}>
                    {a.expires_at ? new Date(a.expires_at).toLocaleString("vi") : "—"}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button className="btn btn-p" disabled={busy}
                      onClick={() => call(`/v1/actions/${a.id}/decide`, { decision: "approve" })}>Duyệt</button>
                    <button className="btn" disabled={busy}
                      onClick={() => call(`/v1/actions/${a.id}/decide`, { decision: "reject" })}>Từ chối</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>}
      </section>

      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>KPI 7 ngày (theo agent)</h2>
          <button className="btn" disabled={busy} onClick={() => call("/v1/mart/rebuild", {})}>↻ Dựng lại mart</button>
        </div>
        <table>
          <thead><tr><th>Agent</th><th>Lượt chạy</th><th>Token</th><th>Chi phí ước (USD)</th><th>Lỗi</th><th>Tool</th><th>A2A gọi đi</th><th>Điểm eval</th></tr></thead>
          <tbody>
            {(kpi?.by_agent || []).length === 0 &&
              <tr><td colSpan={8} className="muted">Chưa có dữ liệu — bấm “Dựng lại mart”.</td></tr>}
            {(kpi?.by_agent || []).map((a: any) => (
              <tr key={a.agent_id}>
                <td className="mono">{a.agent_id}</td>
                <td>{a.runs ?? 0}</td>
                <td>{Number(a.tokens ?? 0).toLocaleString("vi")}</td>
                <td>${Number(a.cost_usd ?? 0).toFixed(4)}</td>
                <td style={{ color: a.errors > 0 ? "#d1495b" : "inherit" }}>{a.errors ?? 0}</td>
                <td>{a.tool_calls ?? 0}</td>
                <td>{a.a2a_out ?? 0}</td>
                <td>{a.eval_score != null ? Number(a.eval_score).toFixed(2) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Lịch sử quyết định</h2>
        <table>
          <thead><tr><th>#</th><th>Hành động</th><th>Đề xuất</th><th>Trạng thái</th><th>Người duyệt</th><th>Kết quả</th></tr></thead>
          <tbody>
            {history.length === 0 && <tr><td colSpan={6} className="muted">Chưa có.</td></tr>}
            {history.map((a: any) => (
              <tr key={a.id}>
                <td>{a.id}</td><td className="mono">{a.action}</td>
                <td className="mono" style={{ fontSize: 12 }}>{a.proposed_by}</td>
                <td><span style={{ color: ST[a.status], fontWeight: 600 }}>{a.status}</span></td>
                <td className="mono" style={{ fontSize: 12 }}>{a.approver || "—"}</td>
                <td className="mono muted" style={{ fontSize: 11, maxWidth: 220 }}>
                  {a.result ? JSON.stringify(a.result).slice(0, 90) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
