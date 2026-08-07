"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

/** Ai đang duyệt — prototype: nhập email; bản thật sẽ lấy từ SSO. */
function useIdentity() {
  const [email, setEmail] = useState("");
  return { email, setEmail };
}

export function IdentityBar({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="card row" style={{ alignItems: "center" }}>
      <span className="muted">Bạn là</span>
      <input placeholder="email của bạn (reviewer / agent owner)" value={value}
        onChange={(e) => onChange(e.target.value)} style={{ width: 320 }} />
      <span className="muted">Quyền duyệt kiểm theo chuyên môn ở Platform API (403 nếu sai domain).</span>
    </div>
  );
}

export function ReviewPanel({ items, conflicts }: { items: any[]; conflicts: any[] }) {
  const router = useRouter();
  const { email, setEmail } = useIdentity();
  const [busy, setBusy] = useState<string>("");
  const [msg, setMsg] = useState<string>("");

  async function post(url: string, body: any, key: string) {
    if (!email) { setMsg("Nhập email của bạn trước."); return; }
    setBusy(key); setMsg("");
    try {
      const r = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j));
      setMsg("✓ Đã ghi nhận.");
      router.refresh();
    } catch (e: any) {
      setMsg("✗ " + String(e.message || e));
    } finally { setBusy(""); }
  }

  return (
    <>
      <IdentityBar value={email} onChange={setEmail} />
      {msg && <p className={msg.startsWith("✗") ? "err" : "muted"}>{msg}</p>}

      <h3>Kiến thức chờ duyệt ({items.length})</h3>
      <table>
        <thead><tr><th>Tiêu đề</th><th>Chuyên môn</th><th>Từ team</th><th>Hành động</th></tr></thead>
        <tbody>
          {items.length === 0 && <tr><td colSpan={4} className="muted">Không có mục nào chờ duyệt.</td></tr>}
          {items.map((it) => (
            <tr key={it.item_id}>
              <td><b>{it.title}</b><div className="muted">{it.item_id}</div></td>
              <td><span className="b b-series">{it.domain || "—"}</span></td>
              <td>{it.source_team || "—"}</td>
              <td className="row">
                <button className="btn btn-p" disabled={busy === it.item_id}
                  onClick={() => post(`/api/knowledge/${it.item_id}/review`,
                    { reviewer_email: email, decision: "approved" }, it.item_id)}>Duyệt</button>
                <button className="btn" disabled={busy === it.item_id}
                  onClick={() => post(`/api/knowledge/${it.item_id}/review`,
                    { reviewer_email: email, decision: "rejected" }, it.item_id)}>Từ chối</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Mâu thuẫn cần agent owner xác nhận ({conflicts.length})</h3>
      <table>
        <thead><tr><th>Agent / Team</th><th>Shared brain nói</th><th>Agent brain nói</th><th>Xác nhận</th></tr></thead>
        <tbody>
          {conflicts.length === 0 && <tr><td colSpan={4} className="muted">Không có mâu thuẫn nào.</td></tr>}
          {conflicts.map((c) => (
            <tr key={c.conflict_id}>
              <td><b>{c.agent_id || "—"}</b><div className="muted">{c.team_id} · owner {c.owner_email}</div></td>
              <td style={{ maxWidth: 260 }}>{c.shared_claim}</td>
              <td style={{ maxWidth: 260 }}>{c.agent_claim}</td>
              <td className="row">
                <button className="btn" disabled={busy === c.conflict_id}
                  onClick={() => post(`/api/conflicts/${c.conflict_id}/resolve`,
                    { decision: "resolved_keep_shared", owner_email: email }, c.conflict_id)}>Giữ shared</button>
                <button className="btn btn-p" disabled={busy === c.conflict_id}
                  onClick={() => post(`/api/conflicts/${c.conflict_id}/resolve`,
                    { decision: "resolved_update_shared", owner_email: email, domain: c.domain }, c.conflict_id)}>Cập nhật shared</button>
                <button className="btn" disabled={busy === c.conflict_id}
                  onClick={() => post(`/api/conflicts/${c.conflict_id}/resolve`,
                    { decision: "dismissed", owner_email: email }, c.conflict_id)}>Bỏ qua</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
