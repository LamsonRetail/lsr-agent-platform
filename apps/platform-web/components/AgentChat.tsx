"use client";
import { useState } from "react";

type Msg = { role: "user" | "agent" | "sys"; text: string };

export default function AgentChat({ agentId }: { agentId: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [sid, setSid] = useState<string | undefined>();

  async function send() {
    const text = q.trim();
    if (!text || busy) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const r = await fetch("/api/agent-chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, text, session_id: sid }),
      });
      const d = await r.json();
      if (d.session_id) setSid(d.session_id);
      if (d.reply) setMsgs((m) => [...m, { role: "agent", text: d.reply }]);
      else setMsgs((m) => [...m, { role: "sys", text: d.error || `(${d.status})` }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "sys", text: String(e) }]);
    } finally { setBusy(false); }
  }

  const bubble = (m: Msg) => ({
    alignSelf: m.role === "user" ? "flex-end" : "flex-start",
    background: m.role === "user" ? "var(--accent, #b8791f)" : m.role === "sys" ? "transparent" : "var(--surface-2, #0001)",
    color: m.role === "user" ? "#fff" : m.role === "sys" ? "#c98a00" : "inherit",
    border: m.role === "sys" ? "1px dashed #c98a00" : "none",
    padding: m.role === "sys" ? "6px 10px" : "8px 12px",
    borderRadius: 12, maxWidth: "80%", fontSize: 13.5, whiteSpace: "pre-wrap" as const,
  });

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Chat thử</h2>
      <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
        Đi qua đúng đường của kênh thật (Chat API → hàng đợi → agent) nên vẫn có telemetry,
        quota, audit. Cần consumer của agent đang chạy.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minHeight: 120,
                    maxHeight: 340, overflowY: "auto", padding: "8px 0" }}>
        {msgs.length === 0 && <span className="muted" style={{ fontSize: 13 }}>Chưa có tin nhắn.</span>}
        {msgs.map((m, i) => <div key={i} style={bubble(m)}>{m.text}</div>)}
        {busy && <div style={{ ...bubble({ role: "agent", text: "" }), opacity: .6 }}>đang chờ agent…</div>}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && send()}
               placeholder="Nhập câu hỏi thử…" style={{ flex: 1 }} disabled={busy} />
        <button className="btn btn-p" onClick={send} disabled={busy || !q.trim()}>Gửi</button>
      </div>
    </div>
  );
}
