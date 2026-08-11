"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const STATUS_COLORS: Record<string, string> = {
  queued: "#4a7edb", running: "#c98a00", done: "#2e9e5b",
  dlq: "#d1495b", failed: "#d1495b", rejected: "#9d2f4f", unrouted: "#8a5a12",
};

export default function JobsConsole({ routes, jobs, agents, status }: {
  routes: any[]; jobs: any[]; agents: any[]; status: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [ch, setCh] = useState("lark");
  const [appId, setAppId] = useState("");
  const [chatId, setChatId] = useState("");
  const [agentId, setAgentId] = useState(agents?.[0]?.agent_id || "");

  async function call(path: string, payload: any = {}) {
    setBusy(true);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, payload }),
      });
      if (!r.ok) throw new Error((await r.json()).error || r.status);
      router.refresh();
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  const filters = ["", "queued", "running", "dlq", "unrouted", "done"];

  return (
    <div style={{ display: "grid", gap: 20 }}>
      {/* Routing bindings */}
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Routing bindings</h2>
        <div className="row" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end", marginBottom: 12 }}>
          <label>Kênh<br /><select value={ch} onChange={e => setCh(e.target.value)}>
            <option>lark</option><option>web</option><option>webhook</option><option>cron</option><option>a2a</option>
          </select></label>
          <label>app_id (Lark)<br /><input value={appId} onChange={e => setAppId(e.target.value)} placeholder="cli_..." /></label>
          <label>chat_id<br /><input value={chatId} onChange={e => setChatId(e.target.value)} placeholder="oc_... (trống = mọi chat)" /></label>
          <label>Agent<br /><select value={agentId} onChange={e => setAgentId(e.target.value)}>
            {agents.map((a: any) => <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>)}
          </select></label>
          <button className="btn btn-p" disabled={busy || !agentId}
            onClick={() => call("/v1/routing", { channel: ch, app_id: appId || null, chat_id: chatId || null, agent_id: agentId })}>
            + Thêm binding
          </button>
        </div>
        <table className="tbl">
          <thead><tr><th>ID</th><th>Kênh</th><th>app_id</th><th>chat_id</th><th>Agent</th><th>Trạng thái</th><th></th></tr></thead>
          <tbody>
            {routes.length === 0 && <tr><td colSpan={7} className="muted">Chưa có binding nào.</td></tr>}
            {routes.map((r: any) => (
              <tr key={r.id}>
                <td>{r.id}</td><td>{r.channel}</td><td className="mono">{r.app_id || "—"}</td>
                <td className="mono">{r.chat_id || "(mọi chat)"}</td><td className="mono">{r.agent_id}</td>
                <td>{r.active ? "✅ active" : "⏸ tắt"}</td>
                <td><button className="btn" disabled={busy} onClick={() => call(`/v1/routing/${r.id}/toggle`)}>
                  {r.active ? "Tắt" : "Bật"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Jobs / DLQ */}
      <section className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <h2 style={{ margin: 0 }}>Jobs &amp; DLQ</h2>
          <div style={{ display: "flex", gap: 6 }}>
            {filters.map(f => (
              <a key={f || "all"} href={f ? `/jobs?status=${f}` : "/jobs"}
                 className="btn" style={{ background: status === f ? "var(--accent,#b8791f)" : undefined,
                                          color: status === f ? "#fff" : undefined }}>
                {f || "tất cả"}</a>
            ))}
          </div>
        </div>
        <table className="tbl">
          <thead><tr><th>ID</th><th>Agent</th><th>Kênh</th><th>Trạng thái</th><th>Thử</th><th>Lỗi gần nhất</th><th></th></tr></thead>
          <tbody>
            {jobs.length === 0 && <tr><td colSpan={7} className="muted">Không có job.</td></tr>}
            {jobs.map((j: any) => (
              <tr key={j.id}>
                <td>{j.id}</td><td className="mono">{j.agent_id || "(unrouted)"}</td><td>{j.channel}</td>
                <td><span style={{ color: STATUS_COLORS[j.status] || "inherit", fontWeight: 600 }}>{j.status}</span></td>
                <td>{j.attempts}/{j.max_attempts}</td>
                <td className="muted" style={{ maxWidth: 280, fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{j.last_error || "—"}</td>
                <td>{["dlq", "failed", "rejected", "unrouted"].includes(j.status) &&
                  <button className="btn" disabled={busy} onClick={() => call(`/v1/jobs/${j.id}/replay`)}>Replay</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
