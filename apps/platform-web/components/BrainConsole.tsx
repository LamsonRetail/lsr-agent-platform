"use client";
import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";

const RELS: Record<string, { label: string; color: string }> = {
  relates_to: { label: "liên quan", color: "#8892a6" }, depends_on: { label: "phụ thuộc", color: "#3b7bc4" },
  derived_from: { label: "dẫn xuất từ", color: "#5b5bd6" }, supersedes: { label: "thay thế", color: "#b7791f" },
  contradicts: { label: "mâu thuẫn", color: "#d1495b" }, refines: { label: "chi tiết hoá", color: "#1f9d57" },
  uses_skill: { label: "dùng kỹ năng", color: "#12a4a4" }, governed_by: { label: "chi phối (policy)", color: "#a4128f" },
};
const LENSES = [
  ["latest", "Mới nhất"], ["agent", "Theo agent"], ["domain", "Theo chuyên môn"], ["type", "Theo loại"],
  ["time", "Theo thời gian"], ["team", "Theo team"], ["status", "Trạng thái"], ["source", "Nguồn"],
  ["tag", "Theo tag"], ["search", "Tìm kiếm"],
];

function chip(s: string) { return <span className={`b b-${s === "approved" || s === "active" || s === "confirmed" ? "good" : s === "pending" || s === "suggested" || s === "proposed" ? "warn" : s === "rejected" ? "critical" : "neutral"}`}>{s}</span>; }

export default function BrainConsole({ scope = "shared", agentId = "", items, skills, policies, links }:
  { scope?: string; agentId?: string; items: any[]; skills: any[]; policies: any[]; links: any[] }) {
  const router = useRouter();
  const [comp, setComp] = useState("kb");
  const [lens, setLens] = useState("latest");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  async function admin(path: string, payload: any) {
    setBusy(path); setMsg("");
    try {
      const r = await fetch("/api/admin", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, payload }) });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.error === "string" ? j.error : JSON.stringify(j.error));
      setMsg("✓ Đã cập nhật."); router.refresh();
      return j;
    } catch (e: any) { setMsg("✗ " + String(e.message || e)); } finally { setBusy(""); }
  }

  const linksOf = (id: string) => links.filter((l) => l.from_id === id || l.to_id === id);
  const rows = useMemo(() => {
    let r = comp === "kb" ? items : comp === "skills" ? skills : policies;
    if (q) r = r.filter((x: any) => JSON.stringify(x).toLowerCase().includes(q.toLowerCase()));
    if (lens === "latest" || lens === "time") r = [...r].sort((a, b) => (b.updated_at || b.created_at || "").localeCompare(a.updated_at || a.created_at || ""));
    if (lens === "status") r = [...r].sort((a, b) => (a.status || "").localeCompare(b.status || ""));
    return r;
  }, [comp, lens, q, items, skills, policies]);

  return (
    <>
      {/* component + scope */}
      <div className="row" style={{ gap: 6 }}>
        <span className="muted" style={{ fontSize: 12 }}>Cấu phần:</span>
        {[["kb", "📚 Tri thức"], ["skills", "🛠️ Kỹ năng"], ["policies", "⚖️ Chính sách"], ["links", "🔗 Liên kết"]].map(([k, l]) => (
          <button key={k} className={`btn ${comp === k ? "btn-p" : ""}`} onClick={() => setComp(k)}>{l}</button>
        ))}
        <div className="spacer" />
        <a href={`/brain-3d${scope === "agent" ? `?scope=agent&agent_id=${agentId}` : ""}`} className="muted" style={{ fontSize: 12 }}>🧊 3D →</a>
      </div>

      {(comp === "kb" || comp === "skills") && (
        <div className="row" style={{ gap: 6, margin: "10px 0" }}>
          {LENSES.map(([k, l]) => <button key={k} className={`tabx ${lens === k ? "on" : ""}`} onClick={() => setLens(k)}>{l}</button>)}
          {lens === "search" && <input placeholder="tìm…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 200 }} />}
        </div>
      )}
      {msg && <p className="muted" style={{ fontSize: 12 }}>{msg}</p>}

      {/* IMPORT (kb only) */}
      {comp === "kb" && <ImportBox scope={scope} agentId={agentId} admin={admin} busy={busy} />}
      {comp === "skills" && <SkillBox admin={admin} busy={busy} />}

      {/* TABLE */}
      <div className="card" style={{ marginTop: 12 }}><div style={{ overflowX: "auto" }}>
        {comp === "links" ? (
          <table><thead><tr><th>Từ</th><th>Quan hệ</th><th>Đến</th><th>Nguồn</th><th>Trạng thái</th><th>Hành động</th></tr></thead>
            <tbody>
              {links.length === 0 && <tr><td colSpan={6} className="muted">Chưa có liên kết.</td></tr>}
              {links.map((l) => (
                <tr key={l.link_id}>
                  <td className="mono">{l.from_id}</td>
                  <td><span className="b" style={{ background: (RELS[l.rel]?.color || "#888") + "22", color: RELS[l.rel]?.color }}>{RELS[l.rel]?.label || l.rel}</span></td>
                  <td className="mono">{l.to_id}</td><td className="muted">{l.created_by}</td>
                  <td>{chip(l.status)}</td>
                  <td><span className="row" style={{ gap: 4 }}>
                    {l.status === "suggested" && <button className="btn btn-p" disabled={!!busy} onClick={() => admin(`/v1/brain/links/${l.link_id}/confirm`, { decision: "confirmed" })}>Xác nhận</button>}
                    <button className="btn" disabled={!!busy} onClick={() => admin(`/v1/brain/links/${l.link_id}/delete`, {})}>Xoá</button>
                  </span></td>
                </tr>
              ))}
            </tbody></table>
        ) : comp === "policies" ? (
          <table><thead><tr><th>Chính sách</th><th>Phase</th><th>Effect</th><th>Domain</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {policies.length === 0 && <tr><td colSpan={5} className="muted">Chưa có policy.</td></tr>}
              {policies.map((p) => (<tr key={p.policy_id}><td><b>{p.title || p.reason || p.policy_id}</b><div className="muted mono" style={{ fontSize: 11 }}>{p.policy_id}</div></td>
                <td>{p.phase}</td><td>{p.effect}</td><td>{p.domain || "—"}</td><td>{chip(p.active ? "active" : "inactive")}</td></tr>))}
            </tbody></table>
        ) : (
          <table><thead><tr><th>Tên</th><th>{colName(lens)}</th><th>Trạng thái</th><th>Nguồn</th><th>Hành động</th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={5} className="muted">Không có mục.</td></tr>}
              {rows.map((r: any) => (
                <tr key={r.item_id || r.skill_id} onClick={() => comp === "kb" && setSel(r)} style={{ cursor: comp === "kb" ? "pointer" : "default" }}>
                  <td><b>{r.title || r.name}</b><div className="muted mono" style={{ fontSize: 11 }}>{r.item_id || r.skill_id}</div></td>
                  <td>{cell(lens, r)}</td>
                  <td>{chip(r.status)}</td>
                  <td>{r.source_url ? <span className="src-ok">● Lark</span> : <span className="src-miss">● thiếu</span>}</td>
                  <td onClick={(e) => e.stopPropagation()}><span className="row" style={{ gap: 4 }}>
                    {comp === "kb" && r.status !== "approved" && <button className="btn btn-p" disabled={!!busy} onClick={() => admin(`/v1/brain/items/${r.item_id}/review`, { decision: "approved" })}>Duyệt</button>}
                    {comp === "kb" && <button className="btn" disabled={!!busy} onClick={() => admin(`/v1/brain/items/${r.item_id}/delete`, {})}>Xoá</button>}
                    {comp === "skills" && <button className="btn" disabled={!!busy} onClick={() => admin(`/v1/brain/skills`, { skill_id: r.skill_id, name: r.name, kind: r.kind, domain: r.domain, status: r.status === "active" ? "deprecated" : "active" })}>{r.status === "active" ? "Ngừng" : "Kích hoạt"}</button>}
                  </span></td>
                </tr>
              ))}
            </tbody></table>
        )}
      </div></div>

      {/* DRAWER */}
      {sel && (
        <div className="drawerX">
          <div className="row" style={{ justifyContent: "space-between" }}><span className="kindx">{sel.kind}</span><button className="btn" onClick={() => setSel(null)}>×</button></div>
          <h3>{sel.title}</h3>
          <div className="muted" style={{ fontSize: 12 }}>{sel.item_id} · {sel.domain || "—"} · {chip(sel.status)} · {sel.source_agent || sel.source_team || ""}</div>
          <p style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{sel.content}</p>
          <div>{(sel.tags || []).map((t: string) => <span key={t} className="tagx">{t}</span>)}</div>
          <div style={{ margin: "8px 0" }}>{sel.source_url ? <a href={sel.source_url} target="_blank" rel="noreferrer">🔗 Mở nguồn Lark ↗</a> : <span className="src-miss">⚠ Thiếu nguồn</span>}</div>
          <Ego id={sel.item_id} links={links} />
          <div style={{ fontSize: 12.5 }}>{linksOf(sel.item_id).map((l) => {
            const other = l.from_id === sel.item_id ? l.to_id : l.from_id;
            return <div key={l.link_id} className="row" style={{ justifyContent: "space-between", padding: "3px 0" }}>
              <span><span style={{ color: RELS[l.rel]?.color }}>━</span> {RELS[l.rel]?.label || l.rel} → <b className="mono">{other}</b> {l.status === "suggested" && chip("suggested")}</span>
            </div>;
          })}</div>
          <div className="row" style={{ marginTop: 12, gap: 6 }}>
            {sel.status !== "approved" && <button className="btn btn-p" disabled={!!busy} onClick={() => admin(`/v1/brain/items/${sel.item_id}/review`, { decision: "approved" }).then(() => setSel(null))}>Duyệt</button>}
            <button className="btn" disabled={!!busy} onClick={() => admin(`/v1/brain/items/${sel.item_id}/review`, { decision: "rejected" }).then(() => setSel(null))}>Từ chối</button>
            <button className="btn" disabled={!!busy} onClick={() => { const to = prompt("Nối tới item_id nào?"); const rel = prompt("Loại quan hệ (" + Object.keys(RELS).join("/") + ")", "relates_to"); if (to && rel) admin(`/v1/brain/links`, { from_id: sel.item_id, to_id: to, from_type: "kb", to_type: "kb", rel }); }}>＋ Liên kết</button>
          </div>
        </div>
      )}
      <style>{`
        .tabx{border:1px solid var(--b,#0002);background:transparent;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer;color:var(--m,#888)}
        .tabx.on{color:inherit;border-color:#5b5bd6;box-shadow:inset 0 -2px 0 #5b5bd6}
        .mono{font-family:ui-monospace,Menlo,monospace}
        .src-ok{color:#1f9d57}.src-miss{color:#d1495b}
        .tagx{display:inline-block;background:#8881;border-radius:6px;padding:1px 7px;font-size:11px;margin:0 3px 3px 0}
        .kindx{background:#5b5bd622;color:#5b5bd6;border-radius:6px;padding:1px 8px;font-size:11px;font-weight:600}
        .drawerX{position:fixed;top:0;right:0;height:100%;width:min(420px,92vw);background:var(--card,#fff);border-left:1px solid #0002;box-shadow:-8px 0 30px #0003;padding:18px;overflow:auto;z-index:50}
      `}</style>
    </>
  );
}
function colName(l: string) { return ({ agent: "Agent", domain: "Chuyên môn", type: "Loại", time: "Cập nhật", team: "Team", status: "Trạng thái", source: "Nguồn", tag: "Tags" } as any)[l] || "Thông tin"; }
function cell(l: string, r: any) {
  if (l === "agent") return <span className="mono">{r.source_agent || "—"}</span>;
  if (l === "domain") return r.domain || "—";
  if (l === "type") return <span className="kindx">{r.kind}</span>;
  if (l === "team") return r.source_team || "—";
  if (l === "tag") return (r.tags || []).map((t: string) => <span key={t} className="tagx">{t}</span>);
  return <span className="mono">{(r.updated_at || r.created_at || "").slice(0, 10)}</span>;
}
function Ego({ id, links }: { id: string; links: any[] }) {
  const ls = links.filter((l) => l.from_id === id || l.to_id === id).slice(0, 6);
  const W = 380, H = 170, cx = W / 2, cy = H / 2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", background: "#8881", borderRadius: 10, margin: "6px 0" }}>
      {ls.map((l, i) => {
        const other = l.from_id === id ? l.to_id : l.from_id; const ang = (2 * Math.PI * i) / Math.max(1, ls.length) - Math.PI / 2;
        const x = cx + Math.cos(ang) * 130, y = cy + Math.sin(ang) * 62, col = RELS[l.rel]?.color || "#888";
        return <g key={l.link_id}><line x1={cx} y1={cy} x2={x} y2={y} stroke={col} strokeWidth={2} strokeDasharray={l.status === "suggested" ? "4 3" : ""} />
          <circle cx={x} cy={y} r={15} fill="var(--card,#fff)" stroke={col} /><text x={x} y={y + 3} textAnchor="middle" fontSize={8} fill="currentColor">{other}</text></g>;
      })}
      <circle cx={cx} cy={cy} r={20} fill="#5b5bd6" /><text x={cx} y={cy + 3} textAnchor="middle" fontSize={9} fill="#fff">{id}</text>
    </svg>
  );
}
function ImportBox({ scope, agentId, admin, busy }: any) {
  const [f, setF] = useState<any>({ kind: "knowledge", title: "", content: "", domain: "", tags: "", source_url: "", source_agent: "", source_team: "" });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <details className="card" style={{ padding: 14 }}>
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>＋ Import tri thức vào {scope === "agent" ? "brain agent" : "shared brain"}</summary>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <select value={f.kind} onChange={set("kind")}>{["knowledge", "process", "definition", "lesson", "belief", "faq"].map((k) => <option key={k}>{k}</option>)}</select>
        <input placeholder="Chuyên môn (domain)" value={f.domain} onChange={set("domain")} />
        <input placeholder="Agent nguồn" value={f.source_agent} onChange={set("source_agent")} />
        <input placeholder="Team nguồn" value={f.source_team} onChange={set("source_team")} />
      </div>
      <input placeholder="Tiêu đề" value={f.title} onChange={set("title")} style={{ width: "100%", marginTop: 8 }} />
      <textarea placeholder="Nội dung (markdown)" value={f.content} onChange={set("content")} rows={3} style={{ width: "100%", marginTop: 8 }} />
      <input placeholder="🔗 Link Lark nguồn (source_url)" value={f.source_url} onChange={set("source_url")} style={{ width: "100%", marginTop: 8 }} />
      <input placeholder="tags (phân cách phẩy)" value={f.tags} onChange={set("tags")} style={{ width: "100%", marginTop: 8 }} />
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn btn-p" disabled={!!busy || !f.title} onClick={() => admin("/v1/brain/items", { ...f, scope, agent_id: scope === "agent" ? agentId : null, tags: f.tags.split(",").map((t: string) => t.trim()).filter(Boolean) })}>Gửi vào hàng chờ duyệt</button>
        <span className="muted" style={{ fontSize: 12 }}>Thiếu source_url → cảnh báo thiếu nguồn.</span>
      </div>
    </details>
  );
}
function SkillBox({ admin, busy }: any) {
  const [f, setF] = useState<any>({ name: "", kind: "mcp", domain: "", status: "proposed" });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <details className="card" style={{ padding: 14 }}>
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>＋ Thêm kỹ năng</summary>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <input placeholder="Tên skill" value={f.name} onChange={set("name")} />
        <select value={f.kind} onChange={set("kind")}>{["mcp", "builtin", "api"].map((k) => <option key={k}>{k}</option>)}</select>
        <input placeholder="Chuyên môn" value={f.domain} onChange={set("domain")} />
        <select value={f.status} onChange={set("status")}>{["proposed", "active", "deprecated"].map((k) => <option key={k}>{k}</option>)}</select>
        <button className="btn btn-p" disabled={!!busy || !f.name} onClick={() => admin("/v1/brain/skills", f)}>Lưu</button>
      </div>
    </details>
  );
}
