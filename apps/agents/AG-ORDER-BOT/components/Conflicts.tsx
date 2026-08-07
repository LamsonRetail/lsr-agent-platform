"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

/** Mâu thuẫn shared brain vs brain của agent — CHỈ agent owner xác nhận (ở backend agent). */
export default function Conflicts({ conflicts, ownerHint }) {
  const router = useRouter();
  const [email, setEmail] = useState(ownerHint || "");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  async function resolve(id, decision) {
    setBusy(id); setMsg("");
    try {
      const r = await fetch("/api/conflicts/" + id + "/resolve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, owner_email: email }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j));
      setMsg("✓ Đã xác nhận."); router.refresh();
    } catch (e) { setMsg("✗ " + String(e.message || e)); } finally { setBusy(""); }
  }
  return (<>
    <h3>Mâu thuẫn cần xác nhận ({conflicts.length})</h3>
    <div className="row" style={{ marginBottom: 10 }}>
      <span className="m">Owner xác nhận:</span>
      <input value={email} onChange={(e) => setEmail(e.target.value)}
        placeholder="email agent owner" style={{ width: 260 }} />
    </div>
    {msg && <p className="m">{msg}</p>}
    <table><thead><tr><th>Shared brain nói</th><th>Agent brain nói</th><th>Xác nhận</th></tr></thead>
    <tbody>
      {conflicts.length === 0 && <tr><td colSpan={3} className="m">Không có mâu thuẫn nào.</td></tr>}
      {conflicts.map((c) => (
        <tr key={c.conflict_id}>
          <td>{c.shared_claim}</td>
          <td>{c.agent_claim}</td>
          <td>
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_keep_shared")}>Giữ shared</button>{" "}
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_update_shared")}>Đề xuất cập nhật</button>{" "}
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "dismissed")}>Bỏ qua</button>
          </td>
        </tr>
      ))}
    </tbody></table>
  </>);
}
