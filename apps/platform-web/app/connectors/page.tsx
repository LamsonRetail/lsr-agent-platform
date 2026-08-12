import { connectorsList, listAgents } from "@/lib/platform";
import ConnectorsConsole from "@/components/ConnectorsConsole";

export const dynamic = "force-dynamic";

export default async function ConnectorsPage() {
  const [data, agents] = await Promise.all([connectorsList(), listAgents()]);
  return (
    <>
      <h1>Connectors · quyền &amp; mức dùng</h1>
      <p className="lead">
        Mỗi connector là một adapter dùng chung (auth · rate-limit · error-map · audit · đo mức dùng).
        Agent chỉ gọi được connector đã được cấp quyền — <b>thu quyền là chặn ngay</b>, không cần restart.
      </p>
      <ConnectorsConsole data={data} agents={agents} />
    </>
  );
}
