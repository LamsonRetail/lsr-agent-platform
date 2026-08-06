"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

function usePost() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>("");
  async function post(url: string, body: any) {
    setBusy(true); setErr("");
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.error === "string" ? j.error : JSON.stringify(j.error));
      router.refresh();
      return j;
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }
  return { post, busy, err };
}

export function StatusButton({ agentId, status }: { agentId: string; status: string }) {
  const { post, busy } = usePost();
  const active = status === "active";
  return (
    <button className="btn" disabled={busy}
      onClick={() => post(`/api/agents/${agentId}/status`, { status: active ? "deactivated" : "active" })}>
      {busy ? "..." : active ? "Deactivate" : "Activate"}
    </button>
  );
}

export function ReviewButton({ testId }: { testId: string }) {
  const { post, busy } = usePost();
  return (
    <button className="btn" disabled={busy}
      onClick={() => post(`/api/tests/${testId}/review`, { reviewed_by: "web-admin" })}>
      {busy ? "..." : "Duyệt →"}
    </button>
  );
}

export function AssignForm({ testId }: { testId: string }) {
  const { post, busy, err } = usePost();
  const [id, setId] = useState("AG-ORDER-BOT");
  return (
    <div className="row">
      <input value={id} onChange={(e) => setId(e.target.value)} style={{ width: 140 }} />
      <button className="btn btn-p" disabled={busy}
        onClick={() => post(`/api/tests/${testId}/assign`, { assignees: [{ taker_id: id, taker_type: "agent" }] })}>
        {busy ? "..." : "Giao bài"}
      </button>
      {err && <span className="err">{err}</span>}
    </div>
  );
}

export function GenerateForm() {
  const { post, busy, err } = usePost();
  const [title, setTitle] = useState("Bài test tự động");
  const [materialId, setMaterialId] = useState("");
  const [md, setMd] = useState("");
  const [skill, setSkill] = useState("order");
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Tạo bài test tự động (draft → chờ duyệt)</h3>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="Tiêu đề" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: 220 }} />
        <input placeholder="skill (vd order)" value={skill} onChange={(e) => setSkill(e.target.value)} style={{ width: 140 }} />
        <input placeholder="material_id (tuỳ chọn)" value={materialId} onChange={(e) => setMaterialId(e.target.value)} style={{ width: 200 }} />
      </div>
      <textarea placeholder="Hoặc dán tài liệu (markdown) để sinh câu hỏi" value={md}
        onChange={(e) => setMd(e.target.value)} rows={3} style={{ width: "100%", marginBottom: 8 }} />
      <div className="row">
        <button className="btn btn-p" disabled={busy}
          onClick={() => post(`/api/tests/generate`, { title, skill, material_id: materialId || undefined, material_md: md || undefined, n: 3 })}>
          {busy ? "Đang sinh..." : "Sinh test"}
        </button>
        {err && <span className="err">{err}</span>}
      </div>
    </div>
  );
}

export function TrainingImportForm() {
  const { post, busy, err } = usePost();
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("order");
  const [md, setMd] = useState("");
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Import tài liệu training (HR) → markdown → lưu</h3>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="Tiêu đề" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: 240 }} />
        <input placeholder="tags (phân cách phẩy)" value={tags} onChange={(e) => setTags(e.target.value)} style={{ width: 200 }} />
      </div>
      <textarea placeholder="Nội dung markdown" value={md} onChange={(e) => setMd(e.target.value)} rows={3}
        style={{ width: "100%", marginBottom: 8 }} />
      <div className="row">
        <button className="btn btn-p" disabled={busy || !md}
          onClick={() => post(`/api/training`, {
            material_id: "M-" + Date.now(), title: title || "Tài liệu", md_content: md,
            tags: tags.split(",").map((s) => s.trim()).filter(Boolean), provided_by: "HR",
          })}>
          {busy ? "..." : "Lưu tài liệu"}
        </button>
        {err && <span className="err">{err}</span>}
      </div>
    </div>
  );
}
