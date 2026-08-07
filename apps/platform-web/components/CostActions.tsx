"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

function usePost() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>("");
  const [msg, setMsg] = useState<string>("");
  async function post(url: string, body: any) {
    setBusy(true); setErr(""); setMsg("");
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
  return { post, busy, err, msg, setMsg };
}

// Đặt/sửa hạn mức tháng cho 1 agent (USD ước tính và/hoặc token).
export function QuotaForm({ agentId, usd, tokens, alertPct }:
  { agentId: string; usd?: number | null; tokens?: number | null; alertPct?: number | null }) {
  const { post, busy, err } = usePost();
  const [u, setU] = useState(usd != null ? String(usd) : "");
  const [t, setT] = useState(tokens != null ? String(tokens) : "");
  const [p, setP] = useState(alertPct != null ? String(alertPct) : "80");
  return (
    <div className="row" style={{ gap: 6 }}>
      <input title="Hạn mức USD/tháng" placeholder="$ / th" value={u}
        onChange={(e) => setU(e.target.value)} style={{ width: 70 }} />
      <input title="Hạn mức token/tháng" placeholder="token / th" value={t}
        onChange={(e) => setT(e.target.value)} style={{ width: 100 }} />
      <input title="Ngưỡng cảnh báo %" placeholder="%" value={p}
        onChange={(e) => setP(e.target.value)} style={{ width: 48 }} />
      <button className="btn" disabled={busy}
        onClick={() => post(`/api/quotas`, {
          agent_id: agentId,
          monthly_usd_limit: u === "" ? null : Number(u),
          monthly_token_limit: t === "" ? null : Number(t),
          alert_pct: Number(p) || 80,
        })}>
        {busy ? "..." : "Lưu"}
      </button>
      {err && <span className="err">{err}</span>}
    </div>
  );
}

export function CheckAlertsButton() {
  const { post, busy } = usePost();
  const [out, setOut] = useState<string>("");
  return (
    <div className="row">
      <button className="btn btn-p" disabled={busy}
        onClick={async () => {
          const j = await post(`/api/cost/check-alerts`, {});
          if (j) setOut(`${(j.fired || []).length} cảnh báo gửi đi`);
        }}>
        {busy ? "Đang quét..." : "Quét cảnh báo ngay"}
      </button>
      {out && <span className="muted">{out}</span>}
    </div>
  );
}
