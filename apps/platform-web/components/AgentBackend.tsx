"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

// Backend riêng của agent: owner xử lý mâu thuẫn (conflict) shared brain vs brain agent.
export function AgentConflicts({ conflicts }: { conflicts: any[] }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  async function resolve(id: string, decision: string, domain?: string) {
    setBusy(id); setErr("");
    try {
      const r = await fetch(`/api/conflicts/${id}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, owner_email: email || undefined, domain }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.error === "string" ? j.error : JSON.stringify(j.error));
      router.refresh();
    } catch (e: any) { setErr(String(e.message || e)); } finally { setBusy(""); }
  }

  if (!conflicts.length) return <p className="muted">Không có mâu thuẫn nào cần xử lý.</p>;
  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="email owner (xác nhận)" value={email}
          onChange={(e) => setEmail(e.target.value)} style={{ width: 240 }} />
        {err && <span className="err">{err}</span>}
      </div>
      {conflicts.map((c: any) => (
        <div key={c.conflict_id} className="card" style={{ marginBottom: 8 }}>
          <div className="muted" style={{ fontSize: 12 }}>{c.conflict_id} · domain: {c.domain || "—"}</div>
          <div><b>Agent nói:</b> {c.agent_claim}</div>
          <div><b>Shared nói:</b> {c.shared_claim}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn" disabled={busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_keep_shared")}>Giữ shared</button>
            <button className="btn" disabled={busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_update_shared", c.domain)}>Cập nhật shared</button>
            <button className="btn" disabled={busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "dismissed")}>Bỏ qua</button>
          </div>
        </div>
      ))}
    </>
  );
}
