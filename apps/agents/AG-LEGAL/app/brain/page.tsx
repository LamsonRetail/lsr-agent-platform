import { brainItems, brainLinks, AGENT_ID } from "@/lib/platform";
import BrainMini from "@/components/BrainMini";
export const dynamic = "force-dynamic";
export default async function Page(){
  const [items, links] = await Promise.all([brainItems(), brainLinks()]);
  return (<>
    <h1>Brain của {AGENT_ID}</h1>
    <div className="m">Tri thức RIÊNG của agent (scope=agent). Import, liên kết, xoá — trong phạm vi agent này.</div>
    <BrainMini items={items} links={links} />
  </>);
}
