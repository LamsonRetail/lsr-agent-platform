"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function ConnectorsConsole({ data, agents }: { data: any; agents: any[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [agentId, setAgentId] = useState(agents?.[0]?.agent_id || "");
  const [connId, setConnId] = useState(data?.connectors?.[0]?.connector_id || "");

  const grantsByConn: Record<string, string[]> = {};
  for (const g of data?.grants || []) {
    (grantsByConn[g.connector_id] ||= []).push(g.agent_id);
  }

  async function grant(revoke: boolean, aid = agentId, cid = connId) {
    setBusy(true);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: "/v1/connectors/grant", payload: { agent_id: aid, connector_id: cid, revoke } }),
      });
      if (!r.ok) throw new Error((await r.json()).error || r.status);
      router.refresh();
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Cấp / thu quyền</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
          <label>Agent<br />
            <select value={agentId} onChange={e => setAgentId(e.target.value)}>
              {agents.map((a: any) => <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>)}
            </select></label>
          <label>Connector<br />
            <select value={connId} onChange={e => setConnId(e.target.value)}>
              {(data?.connectors || []).map((c: any) =>
                <option key={c.connector_id} value={c.connector_id}>{c.connector_id} — {c.name}</option>)}
            </select></label>
          <button className="btn btn-p" disabled={busy} onClick={() => grant(false)}>✓ Cấp quyền</button>
          <button className="btn" disabled={busy} onClick={() => grant(true)}>✕ Thu quyền</button>
        </div>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Connector</h2>
        <table>
          <thead><tr><th>ID</th><th>Loại</th><th>Tên</th><th>Trạng thái</th><th>Bắt buộc quyền</th><th>Agent được cấp</th></tr></thead>
          <tbody>
            {(data?.connectors || []).map((c: any) => (
              <tr key={c.connector_id}>
                <td className="mono">{c.connector_id}</td><td>{c.kind}</td><td>{c.name}</td>
                <td>{c.status === "active" ? "✅ active" : "⏸ " + c.status}</td>
                <td>{c.enforce ? "có" : "không"}</td>
                <td style={{ fontSize: 12 }}>
                  {(grantsByConn[c.connector_id] || []).length === 0
                    ? <span className="muted">— chưa cấp cho ai —</span>
                    : (grantsByConn[c.connector_id] || []).map(a => (
                      <span key={a} className="mono" style={{ marginRight: 8 }}>
                        {a} <button className="btn" style={{ padding: "0 5px", fontSize: 11 }}
                          disabled={busy} onClick={() => grant(true, a, c.connector_id)}>✕</button>
                      </span>))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Mức dùng 7 ngày (theo connector · tool)</h2>
        <table>
          <thead><tr><th>Connector</th><th>Tool / Skill</th><th>Số lần</th><th>Lỗi</th><th>Trễ TB (ms)</th></tr></thead>
          <tbody>
            {(data?.usage_7d || []).length === 0 &&
              <tr><td colSpan={5} className="muted">Chưa có dữ liệu — usage sẽ xuất hiện khi agent gọi tool.</td></tr>}
            {(data?.usage_7d || []).map((u: any, i: number) => (
              <tr key={i}>
                <td className="mono">{u.connector_id}</td><td className="mono">{u.tool}</td>
                <td>{u.n}</td>
                <td style={{ color: u.n_err > 0 ? "#d1495b" : "inherit" }}>{u.n_err}</td>
                <td>{u.avg_ms ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
