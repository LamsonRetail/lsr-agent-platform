import { agent, AGENT_ID } from "@/lib/platform";
export const dynamic = "force-dynamic";
export default async function Page(){
  const a = await agent();
  const rows = [
    ["Agent ID", a.agent_id], ["Tên", a.name], ["Owner", a.owner], ["Squad", a.squad],
    ["Deployment", a.deployment], ["Connect mode", a.connect_mode],
    ["Prompt version", (a.prompt_version||"—")+" / "+(a.prompt_ref||"—")],
    ["Backend URL", a.backend_url||"—"], ["Repo", a.repo_url||"—"], ["Status", a.status],
    ["Skills", (a.skills||[]).join(", ")||"—"],
  ];
  return (<>
    <h1>Config · {AGENT_ID}</h1>
    <div className="m">Cấu hình đăng ký trên platform. Sửa qua manifest lsr-agent.yaml + đăng ký lại, hoặc nhờ admin.</div>
    <table><tbody>
      {rows.map(([k,v])=>(<tr key={k}><th style={{width:180}}>{k}</th><td>{String(v)}</td></tr>))}
    </tbody></table>
  </>);
}
