import { agentDetail, agentTraces, conflictsForAgent, auditForTarget, costSummary, healthAgents, agentLarkIdentities } from "@/lib/platform";
import AgentIdentity from "@/components/AgentIdentity";
import { StatusButton } from "@/components/Actions";
import { QuotaForm } from "@/components/CostActions";
import { AgentConflicts } from "@/components/AgentBackend";
import AgentChat from "@/components/AgentChat";
import Link from "next/link";

export const dynamic = "force-dynamic";

function money(n: number) { return "$" + (n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

export default async function AgentPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const [agent, traces, conflicts, audit, cost, health, identities] = await Promise.all([
    agentDetail(id), agentTraces(id, 20), conflictsForAgent(id), auditForTarget(id),
    costSummary(), healthAgents(), agentLarkIdentities(id),
  ]);

  if (!agent) {
    return (<><h1>Agent {id}</h1><p className="err">Không tìm thấy agent này trong registry.</p>
      <p><Link href="/">← về Platform</Link></p></>);
  }
  const c = (cost.agents || []).find((a: any) => a.agent_id === id) || { usd: 0, tokens: 0, runs: 0, pct: null, quota_usd: null, quota_tokens: null, alert_pct: null, models: {} };
  const h = (health.agents || []).find((a: any) => a.agent_id === id) || { health: "ok", silent_hours: null, last_trace: null };

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>{agent.name || id}</h1>
        <StatusButton agentId={id} status={agent.status} />
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>
        Console riêng của agent này — nằm trong platform, <b>không cần tài khoản Vercel/Supabase</b>.
        Kênh vào (Lark · Telegram) gán ở <a href="/jobs">Ingress</a>; sửa hành vi ở{" "}
        <a href={`/builder?agent=${id}`}>Builder</a>.
      </p>

      <AgentChat agentId={id} />
      <p className="lead">
        {id} · owner: {agent.owner || "—"} · squad: {agent.squad || "—"} ·
        deployment: {agent.deployment || "—"} · prompt: {agent.prompt_version || "—"}/{agent.prompt_ref || "—"} ·
        status: <b>{agent.status}</b> · health: <b>{h.health}</b>
      </p>

      {agent.backend_url ? (
        <div className="card" style={{ borderColor: "#4a7edb" }}>
          <b>Backend riêng của agent</b> (config, trang chi tiết, dashboard riêng):{" "}
          <a href={agent.backend_url} target="_blank" rel="noreferrer">{agent.backend_url} ↗</a>
          {agent.dashboard_url && <> · <a href={agent.dashboard_url} target="_blank" rel="noreferrer">Dashboard ↗</a></>}
          <div className="muted" style={{ fontSize: 12 }}>Trang dưới đây là bản overview do platform host.</div>
        </div>
      ) : (
        <div className="card">
          <span className="muted">Agent chưa đăng ký <b>backend_url</b> riêng — đang dùng trang overview của platform.
          Đăng ký backend qua <code>enroll</code>/<code>register</code> với trường <code>backend_url</code>.</span>
        </div>
      )}

      <AgentIdentity data={identities} />

      {/* ---------------- Dashboard ---------------- */}
      <h3>Dashboard (tháng {cost.period})</h3>
      <div className="kpis">
        <div className="kpi"><div className="l">Chi phí ước tính</div><div className="v">{money(c.usd)}</div></div>
        <div className="kpi"><div className="l">Token</div><div className="v">{(c.tokens || 0).toLocaleString()}</div></div>
        <div className="kpi"><div className="l">Số lần chạy</div><div className="v">{c.runs || 0}</div></div>
        <div className="kpi"><div className="l">Hạn mức đã dùng</div><div className="v">{c.pct != null ? c.pct + "%" : "—"}</div></div>
        <div className="kpi"><div className="l">Im lặng (h)</div><div className="v">{h.silent_hours ?? "—"}</div></div>
      </div>

      <h3>Trace gần đây</h3>
      <table>
        <thead><tr><th>Thời điểm</th><th>run_id</th><th className="n">Token</th><th className="n">Tool</th>
          <th className="n">ms</th><th>Trạng thái</th><th className="n">PII</th></tr></thead>
        <tbody>
          {(!traces || traces.length === 0) && <tr><td colSpan={7} className="muted">Chưa có trace.</td></tr>}
          {(traces || []).map((t: any) => (
            <tr key={t.run_id}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(t.received_at).toLocaleString("vi-VN")}</td>
              <td className="muted">{t.run_id}</td>
              <td className="n">{(t.total_tokens || 0).toLocaleString()}</td>
              <td className="n">{t.tool_calls || 0}</td>
              <td className="n">{t.duration_ms ?? "—"}</td>
              <td><span className={`b b-${t.status === "error" ? "critical" : "good"}`}>{t.status || "ok"}</span></td>
              <td className="n">{t.pii_flags > 0 ? <span className="b b-warn">{t.pii_flags}</span> : "0"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ---------------- Backend ---------------- */}
      <h2 id="backend" style={{ marginTop: 28 }}>Backend (điều khiển)</h2>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Hạn mức chi phí</h3>
        <QuotaForm agentId={id} usd={c.quota_usd} tokens={c.quota_tokens} alertPct={c.alert_pct} />
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Mâu thuẫn tri thức cần owner xác nhận</h3>
        <AgentConflicts conflicts={conflicts || []} />
      </div>

      <h3>Nhật ký thao tác (agent này)</h3>
      <table>
        <thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Chi tiết</th></tr></thead>
        <tbody>
          {(!audit || audit.length === 0) && <tr><td colSpan={4} className="muted">Chưa có.</td></tr>}
          {(audit || []).map((a: any, i: number) => (
            <tr key={i}>
              <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(a.at).toLocaleString("vi-VN")}</td>
              <td>{a.actor}</td><td><b>{a.action}</b></td>
              <td className="muted" style={{ fontSize: 12 }}>{a.detail ? Object.entries(a.detail).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" · ") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p style={{ marginTop: 16 }}><Link href="/">← về Platform</Link></p>
    </>
  );
}
