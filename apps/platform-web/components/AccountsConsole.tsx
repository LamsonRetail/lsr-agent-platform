"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const ROLE_COLOR: Record<string, string> = { admin: "#d1495b", moderator: "#c98a00", user: "#4a7edb" };

export default function AccountsConsole({ accounts, agents, meEmail }:
  { accounts: any[]; agents: any[]; meEmail: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [tempPw, setTempPw] = useState<{ email: string; pw: string } | null>(null);
  const [nEmail, setNEmail] = useState(""); const [nName, setNName] = useState("");
  const [nRole, setNRole] = useState("user"); const [nScope, setNScope] = useState("*");

  async function call(path: string, payload: any = {}) {
    setBusy(true);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, payload }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.error === "string" ? d.error : JSON.stringify(d.error));
      router.refresh();
      return d;
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  async function createAcc() {
    const payload: any = { email: nEmail, name: nName || nEmail, role: nRole };
    if (nScope !== "*") { payload.scope_type = "agent"; payload.scope_id = nScope; }
    const d = await call("/v1/accounts", payload);
    if (d?.temp_password) { setTempPw({ email: d.email, pw: d.temp_password }); setNEmail(""); setNName(""); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      {tempPw && (
        <div className="card" style={{ borderColor: "#c98a00" }}>
          <b>Mật khẩu tạm cho {tempPw.email}</b>
          <p className="mono" style={{ fontSize: 16, margin: "6px 0" }}>{tempPw.pw}</p>
          <p className="muted" style={{ fontSize: 12 }}>
            Chỉ hiện MỘT LẦN — chuyển cho người dùng qua kênh riêng. Họ phải đổi khi đăng nhập.
          </p>
          <button className="btn" onClick={() => setTempPw(null)}>Đã lưu, đóng</button>
        </div>
      )}

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Tạo tài khoản</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
          Nhân viên có Lark <b>không cần tạo tay</b>: bấm "Đăng nhập bằng Lark" là tài khoản
          tự mở với quyền <b>user trên mọi agent</b>, rồi tự xin thêm quyền ở trang Xin quyền.
          Chỉ tạo tay khi cần tài khoản mật khẩu (service/ngoại lệ).
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap" }}>
          <label>Email<br /><input value={nEmail} onChange={e => setNEmail(e.target.value)} placeholder="ten@hapas.vn" /></label>
          <label>Tên<br /><input value={nName} onChange={e => setNName(e.target.value)} placeholder="Họ tên" /></label>
          <label>Vai trò<br /><select value={nRole} onChange={e => setNRole(e.target.value)}>
            <option value="user">user — chỉ xem</option>
            <option value="moderator">moderator — tạo/sửa agent</option>
            <option value="admin">admin — toàn quyền</option>
          </select></label>
          <label>Phạm vi<br /><select value={nScope} onChange={e => setNScope(e.target.value)}>
            <option value="*">Toàn platform</option>
            {agents.map((a: any) => <option key={a.agent_id} value={a.agent_id}>Chỉ {a.agent_id}</option>)}
          </select></label>
          <button className="btn btn-p" disabled={busy || !nEmail.includes("@")} onClick={createAcc}>+ Tạo</button>
        </div>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Tài khoản ({accounts.length})</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
          <b>Telegram</b>: để nhận cảnh báo của AG-OPS/AG-EVAL và bấm Duyệt/Từ chối ngay trong chat.
          Cách lấy chat id: mở <b>@LSRAdminBot</b> → bấm Start → gửi <code>/id</code>. Hoặc để người dùng
          tự nối bằng <code>/dangky &lt;email&gt; &lt;mã&gt;</code>.
        </p>
        <table>
          <thead><tr><th>Email</th><th>Tên</th><th>Đăng nhập</th><th>Vai trò (nhiều vai cùng lúc)</th><th>Telegram</th><th>Trạng thái</th><th>Đăng nhập cuối</th><th></th></tr></thead>
          <tbody>
            {accounts.map((a: any) => (
              <tr key={a.email}>
                <td className="mono" style={{ fontSize: 12 }}>{a.email}{a.email === meEmail && " (bạn)"}</td>
                <td>{a.name}</td>
                <td style={{ fontSize: 12 }}>
                  {a.auth_via === "lark"
                    ? <span title="tự mở qua đăng nhập Lark — không dùng mật khẩu">🔵 Lark</span>
                    : <span title="tài khoản mật khẩu">🔑 mật khẩu</span>}
                  {a.lark_linked && a.auth_via !== "lark" &&
                    <div className="muted" style={{ fontSize: 10 }}>đã liên kết Lark</div>}
                </td>
                <td style={{ fontSize: 12 }}>
                  {(a.roles || []).length === 0 &&
                    <span className="muted" title="quyền mặc định của mọi tài khoản trên mọi agent">
                      user <span style={{ fontSize: 10 }}>(mặc định — mọi agent)</span></span>}
                  {(a.roles || []).map((r: any, i: number) => (
                    <div key={i}>
                      <span style={{ color: ROLE_COLOR[r.role], fontWeight: 600 }}>{r.role}</span>
                      <span className="muted"> · {r.scope_type === "platform" ? "toàn platform" : r.scope_id}</span>
                      <button className="btn" style={{ padding: "0 5px", fontSize: 11, marginLeft: 4 }}
                        disabled={busy}
                        onClick={() => call(`/v1/accounts/${a.email}/roles`,
                          { scope_type: r.scope_type, scope_id: r.scope_id, revoke: true })}>✕</button>
                    </div>
                  ))}
                  <AddRole email={a.email} agents={agents} onDone={call} busy={busy} />
                </td>
                <td><TelegramCell email={a.email} chatId={a.telegram_chat_id} onSave={call} busy={busy} /></td>
                <td>{a.status === "active" ? "✅ hoạt động" : "⏸ đã khoá"}
                  {a.must_change_pw && <div className="muted" style={{ fontSize: 11 }}>chờ đổi mật khẩu</div>}</td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {a.last_login_at ? new Date(a.last_login_at).toLocaleString("vi") : "chưa đăng nhập"}</td>
                <td style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  <button className="btn" disabled={busy || a.email === meEmail}
                    onClick={() => call(`/v1/accounts/${a.email}/status`,
                      { status: a.status === "active" ? "disabled" : "active" })}>
                    {a.status === "active" ? "Khoá" : "Mở"}</button>
                  {a.auth_via !== "lark" && (
                    <button className="btn" disabled={busy}
                      onClick={async () => {
                        const d = await call(`/v1/accounts/${a.email}/reset-password`);
                        if (d?.temp_password) setTempPw({ email: a.email, pw: d.temp_password });
                      }}>Reset MK</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function TelegramCell({ email, chatId, onSave, busy }:
  { email: string; chatId: string | null; onSave: Function; busy: boolean }) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(chatId || "");
  if (!edit) {
    return (
      <span style={{ fontSize: 12 }}>
        {chatId
          ? <span className="mono" title="đã nối — nhận cảnh báo & nút duyệt việc">✅ {chatId}</span>
          : <span className="muted">chưa nối</span>}
        <button className="btn" style={{ padding: "0 6px", fontSize: 11, marginLeft: 6 }}
          onClick={() => setEdit(true)}>sửa</button>
      </span>
    );
  }
  return (
    <span style={{ display: "inline-flex", gap: 4 }}>
      <input value={v} onChange={e => setV(e.target.value)} placeholder="chat id"
             style={{ width: 110, fontSize: 12 }} />
      <button className="btn" style={{ fontSize: 11 }} disabled={busy}
        onClick={() => { onSave(`/v1/accounts/${email}/update`, { telegram_chat_id: v || null }); setEdit(false); }}>
        Lưu</button>
      <button className="btn" style={{ fontSize: 11 }} onClick={() => { setV(chatId || ""); setEdit(false); }}>✕</button>
    </span>
  );
}

function AddRole({ email, agents, onDone, busy }:
  { email: string; agents: any[]; onDone: Function; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState("moderator");
  const [scope, setScope] = useState("*");
  if (!open) return <button className="btn" style={{ padding: "0 6px", fontSize: 11, marginTop: 3 }}
    onClick={() => setOpen(true)}>+ vai trò</button>;
  return (
    <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
      <select value={role} onChange={e => setRole(e.target.value)} style={{ fontSize: 11 }}>
        <option value="user">user</option><option value="moderator">moderator</option><option value="admin">admin</option>
      </select>
      <select value={scope} onChange={e => setScope(e.target.value)} style={{ fontSize: 11 }}>
        <option value="*">toàn platform</option>
        {agents.map((a: any) => <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>)}
      </select>
      <button className="btn" style={{ fontSize: 11 }} disabled={busy} onClick={() => {
        onDone(`/v1/accounts/${email}/roles`, scope === "*"
          ? { scope_type: "platform", scope_id: "*", role }
          : { scope_type: "agent", scope_id: scope, role });
        setOpen(false);
      }}>Lưu</button>
      <button className="btn" style={{ fontSize: 11 }} onClick={() => setOpen(false)}>✕</button>
    </div>
  );
}
