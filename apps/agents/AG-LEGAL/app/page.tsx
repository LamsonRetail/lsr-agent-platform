import { agent, stats, attempts, conflicts, AGENT_ID } from "@/lib/platform";
import Conflicts from "@/components/Conflicts";
export const dynamic = "force-dynamic";
export default async function Page(){
  const [a, s, at, cf] = await Promise.all([agent(), stats(), attempts(), conflicts()]);
  return (<>
    <h1>Backend · {a.name || AGENT_ID}</h1>
    <div className="m">{AGENT_ID} · squad {a.squad || "—"} · owner {a.owner || "—"} · <span className="bg">{a.status || "?"}</span></div>
    <div className="k">
      <div className="c"><div className="m">Token</div><div className="v">{(s.total_tokens||0).toLocaleString()}</div></div>
      <div className="c"><div className="m">Runs</div><div className="v">{s.runs||0}</div></div>
      <div className="c"><div className="m">Lượt làm bài</div><div className="v">{(at||[]).length}</div></div>
    </div>
    <h3>Kết quả làm bài</h3>
    <table><thead><tr><th>Bài</th><th>Điểm</th><th>Kết quả</th></tr></thead><tbody>
      {(at||[]).length===0 && <tr><td colSpan={3} className="m">chưa có</td></tr>}
      {(at||[]).map(x=>(<tr key={x.attempt_id}><td>{x.test_id}</td><td>{Math.round((x.score||0)*100)}</td><td>{x.passed?"pass":"fail"}</td></tr>))}
    </tbody></table>
    <Conflicts conflicts={cf} ownerHint={a.owner || ""} />
    <p className="m" style={{marginTop:16}}>Backend riêng của agent — deploy chung repo platform. Thêm Config/Schedule tại đây.</p>
  </>);
}
