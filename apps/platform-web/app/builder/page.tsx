import { listAgents, agentVersions } from "@/lib/platform";
import BuilderConsole from "@/components/BuilderConsole";

export const dynamic = "force-dynamic";

export default async function BuilderPage({ searchParams }: { searchParams: { agent?: string } }) {
  const agents = await listAgents();
  const agentId = searchParams?.agent || agents?.[0]?.agent_id || "";
  const versions = agentId ? await agentVersions(agentId) : [];
  return (
    <>
      <h1>Builder · Agent versions</h1>
      <p className="lead">
        Sửa hành vi agent <b>không cần deploy code</b>: viết instruction → lưu nháp → publish theo
        môi trường. Publish <b>prod</b> phải pass regression trên golden set. Rollback 1 click.
      </p>
      <BuilderConsole agents={agents} agentId={agentId} versions={versions} />
    </>
  );
}
