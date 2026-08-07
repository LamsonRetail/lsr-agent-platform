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

export function HealthCheckButton() {
  const { post, busy } = usePost();
  const [out, setOut] = useState("");
  return (
    <div className="row">
      <button className="btn btn-p" disabled={busy}
        onClick={async () => {
          const j = await post(`/api/health/check-alerts`, {});
          if (j) setOut(`${(j.fired || []).length} cảnh báo gửi đi`);
        }}>
        {busy ? "Đang quét..." : "Quét sức khoẻ ngay"}
      </button>
      {out && <span className="muted">{out}</span>}
    </div>
  );
}

export function GoldenCaseForm() {
  const { post, busy, err } = usePost();
  const [skill, setSkill] = useState("order");
  const [prompt, setPrompt] = useState("");
  const [expected, setExpected] = useState("");
  const [atype, setAtype] = useState("contains");
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Thêm ca golden (bộ chuẩn hồi quy)</h3>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="skill" value={skill} onChange={(e) => setSkill(e.target.value)} style={{ width: 120 }} />
        <select value={atype} onChange={(e) => setAtype(e.target.value)}>
          <option value="contains">contains</option>
          <option value="exact">exact</option>
          <option value="regex">regex</option>
          <option value="numeric_tolerance">numeric_tolerance</option>
          <option value="llm_judge">llm_judge</option>
        </select>
      </div>
      <textarea placeholder="Prompt / yêu cầu" value={prompt} onChange={(e) => setPrompt(e.target.value)}
        rows={2} style={{ width: "100%", marginBottom: 8 }} />
      <textarea placeholder="Đáp án mong đợi / tiêu chí" value={expected} onChange={(e) => setExpected(e.target.value)}
        rows={2} style={{ width: "100%", marginBottom: 8 }} />
      <div className="row">
        <button className="btn btn-p" disabled={busy || !prompt}
          onClick={() => post(`/api/golden`, { skill, prompt, expected, atype })}>
          {busy ? "..." : "Lưu ca golden"}
        </button>
        {err && <span className="err">{err}</span>}
      </div>
    </div>
  );
}
