"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function BrainMini({ items, links }){
  const router=useRouter(); const [f,setF]=useState({title:"",content:"",domain:"",kind:"knowledge",source_url:""}); const [busy,setBusy]=useState(false);
  const set=k=>e=>setF({...f,[k]:e.target.value});
  async function call(path,payload){ setBusy(true); try{ const r=await fetch("/api/brain",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path,payload})}); if(!r.ok) throw new Error((await r.json()).error||r.status); router.refresh(); }catch(e){ alert(e.message||e); } finally{ setBusy(false);} }
  const lk=id=>links.filter(l=>l.from_id===id||l.to_id===id);
  return (<>
    <div className="c" style={{padding:14,marginBottom:12}}>
      <b>Thêm tri thức</b>
      <div className="row" style={{gap:8,marginTop:8}}>
        <select value={f.kind} onChange={set("kind")}>{["knowledge","process","definition","lesson","faq"].map(k=><option key={k}>{k}</option>)}</select>
        <input placeholder="domain" value={f.domain} onChange={set("domain")} />
      </div>
      <input placeholder="Tiêu đề" value={f.title} onChange={set("title")} style={{width:"100%",marginTop:8}} />
      <textarea placeholder="Nội dung" value={f.content} onChange={set("content")} rows={2} style={{width:"100%",marginTop:8}} />
      <input placeholder="Link Lark nguồn" value={f.source_url} onChange={set("source_url")} style={{width:"100%",marginTop:8}} />
      <button className="btn" disabled={busy||!f.title} onClick={()=>call("/v1/self/brain/items",f)} style={{marginTop:8}}>Lưu</button>
    </div>
    <table><thead><tr><th>Tên</th><th>Loại</th><th>Domain</th><th>Liên kết</th><th>Nguồn</th><th></th></tr></thead><tbody>
      {items.length===0 && <tr><td colSpan={6} className="m">Chưa có tri thức.</td></tr>}
      {items.map(i=>(<tr key={i.item_id}>
        <td><b>{i.title}</b><div className="m" style={{fontSize:11}}>{i.item_id}</div></td>
        <td>{i.kind}</td><td>{i.domain||"—"}</td><td>{lk(i.item_id).length}</td>
        <td>{i.source_url?<a href={i.source_url} target="_blank">Lark</a>:"—"}</td>
        <td><button className="btn" disabled={busy} onClick={()=>{const to=prompt("Nối tới item_id?");const rel=prompt("quan hệ","relates_to");if(to&&rel)call("/v1/self/brain/links",{from_id:i.item_id,to_id:to,rel});}}>+link</button>
            <button className="btn" disabled={busy} onClick={()=>call("/v1/self/brain/items/"+i.item_id+"/delete",{})}>xoá</button></td>
      </tr>))}
    </tbody></table>
  </>);
}
