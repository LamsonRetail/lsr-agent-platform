import { traces, AGENT_ID } from "@/lib/platform";
export const dynamic = "force-dynamic";
export default async function Page(){
  const rows = await traces(40);
  return (<>
    <h1>Chi tiết · {AGENT_ID}</h1>
    <div className="m">Trace gần đây (dữ liệu từ collector).</div>
    <table><thead><tr><th>Thời điểm</th><th>run_id</th><th>Token</th><th>Tool</th><th>ms</th><th>Trạng thái</th><th>PII</th></tr></thead><tbody>
      {(rows||[]).length===0 && <tr><td colSpan={7} className="m">chưa có trace</td></tr>}
      {(rows||[]).map(t=>(<tr key={t.run_id}>
        <td className="m">{new Date(t.received_at).toLocaleString("vi-VN")}</td>
        <td className="m">{t.run_id}</td><td>{(t.total_tokens||0).toLocaleString()}</td>
        <td>{t.tool_calls||0}</td><td>{t.duration_ms??"—"}</td>
        <td><span className="bg">{t.status||"ok"}</span></td><td>{t.pii_flags||0}</td>
      </tr>))}
    </tbody></table>
  </>);
}
