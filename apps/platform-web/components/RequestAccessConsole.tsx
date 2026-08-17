"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const ROLE_VI: Record<string, string> = { user: "user (xem)", moderator: "moderator (sửa config)", admin: "admin (toàn quyền)" };
const ST_COLOR: Record<string, string> = { pending: "#c98a00", approved: "#2e9e5b", rejected: "#d1495b" };

export default function RequestAccessConsole({ data, welcome }: { data: any; welcome?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [role, setRole] = useState<Record<string, string>>({});
  const [reason, setReason] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  if (!data) return <p className="err">Không tải được danh sách agent — thử tải lại trang.</p>;
  const agents: any[] = data.agents || [];
  const requests: any[] = data.requests || [];
  const pendingOf = (id: string) => requests.find((q) => q.scope_id === id && q.status === "pending");

  async function send(agentId: string) {
    setBusy(agentId); setMsg("");
    try {
      const r = await fetch("/api/roles/request", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope_type: "agent", scope_id: agentId,
          role: role[agentId] || "moderator", reason: reason[agentId] || "",
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "gửi thất bại");
      setMsg(`✅ Đã gửi yêu cầu #${d.id} — admin sẽ nhận thông báo và duyệt.`);
      router.refresh();
    } catch (e: any) { setMsg(`❌ ${e.message || e}`); } finally { setBusy(""); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      {welcome && (
        <div className="card" style={{ borderColor: "#2e9e5b", margin: 0 }}>
          <b style={{ color: "#2e9e5b" }}>👋 Chào mừng đến LSR Agent Platform!</b>
          <p style={{ fontSize: 13, margin: "6px 0 0" }}>
            Bạn đang có quyền <b>user</b> trên tất cả agent — xem được dashboard và cấu hình.
            Nếu cần sửa config hay duyệt việc trên agent nào, gửi yêu cầu bên dưới.
          </p>
        </div>
      )}
      {msg && <div className="card" style={{ margin: 0, fontSize: 13 }}>{msg}</div>}

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Danh sách agent</h2>
        <table>
          <thead>
            <tr><th>Agent</th><th>Bot trong Lark</th><th>Quyền hiện tại</th><th>Quyền cần xin</th><th>Lý do</th><th></th></tr>
          </thead>
          <tbody>
            {agents.length === 0 && <tr><td colSpan={6} className="muted">Chưa có agent nào.</td></tr>}
            {agents.map((a) => {
              const pend = pendingOf(a.agent_id);
              const eff = a.effective_role || data.default_role || "user";
              const maxed = eff === "admin";
              return (
                <tr key={a.agent_id}>
                  <td><span className="mono">{a.agent_id}</span><br />
                    <span className="muted" style={{ fontSize: 12 }}>{a.name}{a.squad ? ` · ${a.squad}` : ""}</span></td>
                  <td style={{ fontSize: 13 }}>{a.lark_bot_name || <span className="muted">—</span>}</td>
                  <td><b>{eff}</b>{!a.my_role && <span className="muted" style={{ fontSize: 11 }}> (mặc định)</span>}</td>
                  {pend ? (
                    <td colSpan={3} style={{ fontSize: 13, color: ST_COLOR.pending }}>
                      ⏳ Đang chờ duyệt: <b>{pend.role}</b> (yêu cầu #{pend.id})
                    </td>
                  ) : maxed ? (
                    <td colSpan={3} className="muted" style={{ fontSize: 13 }}>đã là admin</td>
                  ) : (
                    <>
                      <td>
                        <select value={role[a.agent_id] || "moderator"}
                                onChange={(e) => setRole({ ...role, [a.agent_id]: e.target.value })}>
                          {eff !== "moderator" && <option value="moderator">{ROLE_VI.moderator}</option>}
                          <option value="admin">{ROLE_VI.admin}</option>
                        </select>
                      </td>
                      <td><input value={reason[a.agent_id] || ""} placeholder="vd: tôi là owner squad này"
                                 onChange={(e) => setReason({ ...reason, [a.agent_id]: e.target.value })}
                                 style={{ width: 180 }} /></td>
                      <td><button className="btn btn-p" disabled={busy === a.agent_id}
                                  onClick={() => send(a.agent_id)}>Gửi</button></td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {requests.length > 0 && (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Yêu cầu của tôi</h2>
          <table>
            <thead><tr><th>#</th><th>Phạm vi</th><th>Quyền</th><th>Trạng thái</th><th>Người duyệt</th><th>Ghi chú</th></tr></thead>
            <tbody>
              {requests.map((q) => (
                <tr key={q.id}>
                  <td>{q.id}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{q.scope_type === "platform" ? "PLATFORM" : q.scope_id}</td>
                  <td>{q.role}</td>
                  <td style={{ color: ST_COLOR[q.status] || "inherit", fontWeight: 600 }}>{q.status}</td>
                  <td className="mono" style={{ fontSize: 12 }}>{q.decided_by || "—"}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{q.decide_note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
