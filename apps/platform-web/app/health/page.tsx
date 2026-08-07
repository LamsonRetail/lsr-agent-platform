import { healthAgents } from "@/lib/platform";
import { HealthCheckButton } from "@/components/OpsActions";

export const dynamic = "force-dynamic";

function healthBadge(h: string) {
  if (h === "ok") return <span className="b b-good">ok</span>;
  if (h === "silent") return <span className="b b-warn">im lặng</span>;
  if (h === "never") return <span className="b b-critical">chưa trace</span>;
  return <span className="b b-neutral">{h}</span>;
}

export default async function HealthPage() {
  const data = await healthAgents();
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Sức khoẻ agent</h1>
        <HealthCheckButton />
      </div>
      <p className="lead">
        Agent <b>active</b> nhưng không gửi trace quá <b>{data.threshold_hours}h</b> → cảnh báo Lark cho owner
        (tự quét mỗi 30 phút, 1 lần/agent/ngày). Đang có <b>{data.n_problem}</b> agent cần chú ý.
      </p>
      <table>
        <thead><tr><th>Agent</th><th>Owner</th><th>Status</th><th>Sức khoẻ</th>
          <th className="n">Runs</th><th className="n">Im lặng (h)</th><th>Trace gần nhất</th></tr></thead>
        <tbody>
          {data.agents.length === 0 && <tr><td colSpan={7} className="muted">Chưa có agent.</td></tr>}
          {data.agents.map((a: any) => (
            <tr key={a.agent_id}>
              <td><b>{a.name || a.agent_id}</b><div className="muted">{a.agent_id}</div></td>
              <td>{a.owner || "—"}</td>
              <td><span className={`b b-${a.status === "active" ? "good" : a.status === "deactivated" ? "critical" : "neutral"}`}>{a.status}</span></td>
              <td>{healthBadge(a.health)}</td>
              <td className="n">{a.runs}</td>
              <td className="n">{a.silent_hours ?? "—"}</td>
              <td className="muted">{a.last_trace ? new Date(a.last_trace).toLocaleString("vi-VN") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
