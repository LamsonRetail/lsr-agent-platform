"use client";
import { useState } from "react";

export default function DeviceApprove({ code, email }: { code: string; email: string }) {
  const [v, setV] = useState(code);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"approved" | "denied" | "">("");
  const [err, setErr] = useState("");

  async function decide(deny: boolean) {
    setBusy(true); setErr("");
    try {
      const r = await fetch("/api/auth/device", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_code: v.trim().toUpperCase(), deny }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "không duyệt được");
      setDone(deny ? "denied" : "approved");
    } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(false); }
  }

  if (done === "approved") {
    return (
      <div className="card" style={{ borderColor: "#2e9e5b" }}>
        <b style={{ color: "#2e9e5b" }}>✅ Đã duyệt</b>
        <p style={{ fontSize: 13, margin: "6px 0 0" }}>
          Quay lại terminal — token đã được cấp cho <b>{email}</b> và lưu tại <code>~/.lsr/token</code>.
          Bạn có thể thu hồi bất cứ lúc nào ở Console → Tài khoản.
        </p>
      </div>
    );
  }
  if (done === "denied") {
    return <div className="card"><b>Đã từ chối</b>
      <p className="muted" style={{ fontSize: 13 }}>Không token nào được cấp.</p></div>;
  }

  return (
    <div className="card">
      <label style={{ fontSize: 13 }}>Mã hiện trên terminal<br />
        <input value={v} onChange={(e) => setV(e.target.value)} placeholder="ABCD-2345"
               autoFocus className="mono"
               style={{ width: "100%", fontSize: 20, letterSpacing: 2, textAlign: "center",
                        margin: "6px 0" }} />
      </label>
      <p className="muted" style={{ fontSize: 12 }}>
        Token sẽ mang quyền của <b>{email || "tài khoản đang đăng nhập"}</b> — hạn 90 ngày.
      </p>
      {err && <p className="err">{err}</p>}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-p" disabled={busy || v.trim().length < 8}
                onClick={() => decide(false)} style={{ flex: 1 }}>Duyệt</button>
        <button className="btn" disabled={busy || v.trim().length < 8}
                onClick={() => decide(true)}>Từ chối</button>
      </div>
    </div>
  );
}
