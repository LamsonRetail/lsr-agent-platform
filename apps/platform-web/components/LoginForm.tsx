"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [needChange, setNeedChange] = useState(false);
  const [newPw, setNewPw] = useState("");

  async function login() {
    setBusy(true); setErr("");
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password: pw }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.error === "string" ? d.error : "đăng nhập thất bại");
      if (d.must_change_pw) { setNeedChange(true); return; }
      router.push(next); router.refresh();
    } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(false); }
  }

  async function changePw() {
    setBusy(true); setErr("");
    try {
      const r = await fetch("/api/auth/change-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPw }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.error === "string" ? d.error : "đổi mật khẩu thất bại");
      router.push(next); router.refresh();
    } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(false); }
  }

  if (needChange) {
    return (
      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Đặt mật khẩu mới</h2>
        <p className="muted" style={{ fontSize: 12 }}>Bắt buộc đổi mật khẩu tạm ở lần đăng nhập đầu (tối thiểu 10 ký tự).</p>
        <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)}
               placeholder="Mật khẩu mới" style={{ width: "100%", marginBottom: 8 }}
               onKeyDown={(e) => e.key === "Enter" && changePw()} />
        {err && <p className="err">{err}</p>}
        <button className="btn btn-p" onClick={changePw} disabled={busy || newPw.length < 10}
                style={{ width: "100%" }}>Lưu &amp; vào console</button>
      </div>
    );
  }

  return (
    <div className="card">
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@hapas.vn"
             style={{ width: "100%", marginBottom: 8 }} autoFocus />
      <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Mật khẩu"
             style={{ width: "100%", marginBottom: 8 }}
             onKeyDown={(e) => e.key === "Enter" && login()} />
      {err && <p className="err">{err}</p>}
      <button className="btn btn-p" onClick={login} disabled={busy || !email || !pw}
              style={{ width: "100%" }}>{busy ? "Đang kiểm tra…" : "Đăng nhập"}</button>
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0" }}>
        <hr style={{ flex: 1, border: "none", borderTop: "1px solid #8884" }} />
        <span className="muted" style={{ fontSize: 11 }}>hoặc</span>
        <hr style={{ flex: 1, border: "none", borderTop: "1px solid #8884" }} />
      </div>
      <a className="btn" href="/api/auth/lark/start"
         style={{ width: "100%", display: "block", textAlign: "center", boxSizing: "border-box" }}>
        🔵 Đăng nhập bằng Lark
      </a>
      <p className="muted" style={{ fontSize: 11, marginTop: 8, marginBottom: 0 }}>
        Đăng nhập Lark bằng tài khoản công ty — hệ thống tự tạo tài khoản console
        (quyền user) và kiểm tra đúng tổ chức.
      </p>
    </div>
  );
}
