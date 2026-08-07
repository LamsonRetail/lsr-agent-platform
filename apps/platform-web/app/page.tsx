import { listAgents, tokenStats } from "@/lib/platform";
import { StatusButton } from "@/components/Actions";

export const dynamic = "force-dynamic";

function badge(status: string) {
  const kind = status === "active" ? "good" : status === "deactivated" ? "critical" : "neutral";
  return <span className={`b b-${kind}`}>{status}</span>;
}

export default async function PlatformPage() {
  const [agents, stats] = await Promise.all([listAgents(), tokenStats()]);
  const smap: Record<string, any> = {};
  for (const s of stats) smap[s.agent_id] = s;
  const totalTokens = stats.reduce((a: number, s: any) => a + (s.total_tokens || 0), 0);
  const nActive = agents.filter((a: any) => a.status === "active").length;

  return (
    <>
      <h1>Platform Dashboard</h1>
      <p className="lead">Tổng hợp agent (dữ liệu live từ Platform API + collector). Active/Deactivate là thao tác thật.</p>
      <div className="kpis">
        <div className="kpi"><div className="l">Tổng agent</div><div className="v">{agents.length}</div></div>
        <div className="kpi"><div className="l">Đang active</div><div className="v">{nActive}</div></div>
        <div className="kpi"><div className="l">Tổng token</div><div className="v">{totalTokens.toLocaleString()}</div></div>
      </div>

      <h3>Agents</h3>
      <table>
        <thead><tr><th>Agent</th><th>Squad</th><th>Owner</th><th>Status</th>
          <th className="n">Token</th><th className="n">Runs</th><th className="n">PII đã che</th><th>Hành động</th></tr></thead>
        <tbody>
          {agents.length === 0 && <tr><td colSpan={8} className="muted">Chưa có agent nào đăng ký.</td></tr>}
          {agents.map((a: any) => {
            const pii = smap[a.agent_id]?.pii_flags || 0;
            return (
            <tr key={a.agent_id}>
              <td><b>{a.name || a.agent_id}</b><div className="muted">{a.agent_id}</div></td>
              <td>{a.squad || "—"}</td>
              <td>{a.owner || "—"}</td>
              <td>{badge(a.status)}</td>
              <td className="n">{(smap[a.agent_id]?.total_tokens || 0).toLocaleString()}</td>
              <td className="n">{smap[a.agent_id]?.runs || 0}</td>
              <td className="n">{pii > 0 ? <span className="b b-warn">{pii}</span> : "0"}</td>
              <td><StatusButton agentId={a.agent_id} status={a.status} /></td>
            </tr>
          );})}
        </tbody>
      </table>
    </>
  );
}
