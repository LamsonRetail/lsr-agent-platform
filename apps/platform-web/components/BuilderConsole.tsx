"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const PUB_COLOR: Record<string, string> = {
  prod: "#2e9e5b", stg: "#4a7edb", dev: "#c98a00", draft: "#8a8f98",
};

export default function BuilderConsole({ agents, agentId, versions }: {
  agents: any[]; agentId: string; versions: any[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [model, setModel] = useState("");
  const [skills, setSkills] = useState("");
  const [note, setNote] = useState("");
  const [gateErr, setGateErr] = useState<any>(null);

  // 1 version có thể sống ở nhiều env cùng lúc → đọc mảng envs.
  const live = (env: string) => versions.find((v: any) => (v.envs || []).includes(env));

  async function call(path: string, payload: any = {}) {
    setBusy(true); setGateErr(null);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, payload }),
      });
      const d = await r.json();
      if (!r.ok) {
        // Gate chặn publish prod → hiện danh sách case fail ngay trên UI
        const err = d?.error;
        if (err?.detail?.failed_cases || err?.detail?.reason || err?.failed_cases || err?.reason) {
          setGateErr(err.detail || err); return;
        }
        throw new Error(typeof err === "string" ? err : JSON.stringify(err));
      }
      router.refresh();
      return d;
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  async function saveDraft() {
    if (!instruction.trim()) { alert("Nhập instruction trước"); return; }
    const payload: any = { instruction_block: instruction, note: note || undefined };
    if (model.trim()) payload.model = model.trim();
    const sk = skills.split(",").map(s => s.trim()).filter(Boolean);
    if (sk.length) payload.skills = sk;
    const d = await call(`/v1/agents/${agentId}/versions`, payload);
    if (d) { setInstruction(""); setNote(""); setSkills(""); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <section className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
          <label>Agent<br />
            <select value={agentId} onChange={e => router.push(`/builder?agent=${e.target.value}`)}>
              {agents.map((a: any) => <option key={a.agent_id} value={a.agent_id}>{a.agent_id} — {a.name}</option>)}
            </select>
          </label>
          {["dev", "stg", "prod"].map(env => {
            const v = live(env);
            return (
              <div key={env} style={{ minWidth: 90 }}>
                <div className="muted" style={{ fontSize: 11, textTransform: "uppercase" }}>{env}</div>
                <div style={{ fontWeight: 700, color: PUB_COLOR[env] }}>{v ? `v${v.version}` : "—"}</div>
              </div>
            );
          })}
          <button className="btn" disabled={busy}
            onClick={() => call(`/v1/agents/${agentId}/rollback`, { env: "prod" })}>
            ↩ Rollback prod
          </button>
        </div>
      </section>

      {gateErr && (
        <section className="card" style={{ borderColor: "#d1495b" }}>
          <h3 style={{ marginTop: 0, color: "#d1495b" }}>⛔ Eval gate chặn publish prod</h3>
          <p style={{ fontSize: 13 }}>{gateErr.reason || gateErr.error}</p>
          {gateErr.failed_cases?.length > 0 && (
            <table>
              <thead><tr><th>Case</th><th>Skill</th><th>Ghi chú</th></tr></thead>
              <tbody>
                {gateErr.failed_cases.map((c: any, i: number) => (
                  <tr key={i}><td className="mono">{c.case_id}</td><td>{c.skill || "—"}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{c.note || c.atype}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          <button className="btn" onClick={() => setGateErr(null)} style={{ marginTop: 8 }}>Đóng</button>
        </section>
      )}

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Tạo version mới (lưu nháp)</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
          Lưu nháp KHÔNG đổi hành vi agent đang chạy — chỉ khi Publish mới áp dụng.
        </p>
        <label style={{ display: "block", marginBottom: 8 }}>Instruction (system prompt)<br />
          <textarea value={instruction} onChange={e => setInstruction(e.target.value)} rows={8}
            style={{ width: "100%", fontFamily: "ui-monospace, monospace", fontSize: 13 }}
            placeholder="Bạn là trợ lý ... Nhiệm vụ: ..." />
        </label>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
          <label>Model<br /><input value={model} onChange={e => setModel(e.target.value)} placeholder="(mặc định)" /></label>
          <label>Skills (phân tách bằng dấu phẩy)<br />
            <input value={skills} onChange={e => setSkills(e.target.value)} placeholder="bigquery, lark_doc" style={{ minWidth: 220 }} /></label>
          <label>Ghi chú<br /><input value={note} onChange={e => setNote(e.target.value)} placeholder="đổi gì ở bản này" style={{ minWidth: 200 }} /></label>
        </div>
        <button className="btn btn-p" disabled={busy || !agentId} onClick={saveDraft}>💾 Lưu nháp</button>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Lịch sử version</h2>
        <table>
          <thead><tr><th>v</th><th>Publication</th><th>Model</th><th>Skills</th><th>Ghi chú</th><th>Tạo bởi</th><th>Publish</th></tr></thead>
          <tbody>
            {versions.length === 0 && <tr><td colSpan={7} className="muted">Chưa có version nào — tạo bản nháp đầu tiên ở trên.</td></tr>}
            {versions.map((v: any) => (
              <tr key={v.version}>
                <td><b>v{v.version}</b></td>
                <td>{(v.envs || []).length
                  ? (v.envs || []).map((e: string) => (
                      <span key={e} style={{ color: PUB_COLOR[e], fontWeight: 600, marginRight: 6 }}>{e}</span>))
                  : <span style={{ color: PUB_COLOR.draft }}>draft</span>}</td>
                <td className="mono" style={{ fontSize: 12 }}>{v.model || "—"}</td>
                <td className="mono" style={{ fontSize: 12 }}>{(v.skills || []).join(", ") || "—"}</td>
                <td className="muted" style={{ fontSize: 12, maxWidth: 200 }}>{v.note || "—"}</td>
                <td className="mono" style={{ fontSize: 12 }}>{v.created_by || "—"}</td>
                <td style={{ display: "flex", gap: 4 }}>
                  {["dev", "stg", "prod"].map(env => (
                    <button key={env} className="btn" disabled={busy || v.publication === env}
                      onClick={() => call(`/v1/agents/${agentId}/versions/${v.version}/publish`, { env })}>
                      {env}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
