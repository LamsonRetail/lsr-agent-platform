"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const ST: Record<string, string> = {
  active: "#2e9e5b", cooldown: "#c98a00", disabled: "#d1495b",
};

export default function ModelAuthConsole({ data }: { data: any }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const creds: any[] = data?.credentials || [];
  const agents: any[] = data?.agents || [];
  const subN = data?.pool_subscription_usable ?? 0;
  const apiN = data?.pool_api_usable ?? 0;
  const poolLow = subN <= 1;

  async function setStatus(id: string, status: string) {
    setBusy(true);
    try {
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: `/v1/model-auth/credentials/${id}/status`, payload: { status } }),
      });
      if (!r.ok) throw new Error((await r.json()).error || r.status);
      router.refresh();
    } catch (e: any) { alert(e.message || e); } finally { setBusy(false); }
  }

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div className="card" style={{ margin: 0, flex: 1, minWidth: 160 }}>
          <div className="muted" style={{ fontSize: 12 }}>Subscription khả dụng</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: poolLow ? "#c98a00" : "inherit" }}>{subN}</div>
          {poolLow && <div style={{ fontSize: 12, color: "#c98a00" }}>⚠ pool sắp cạn — nạp thêm account</div>}
        </div>
        <div className="card" style={{ margin: 0, flex: 1, minWidth: 160 }}>
          <div className="muted" style={{ fontSize: 12 }}>API key khả dụng (fallback)</div>
          <div style={{ fontSize: 26, fontWeight: 700 }}>{apiN}</div>
        </div>
      </div>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Credential pool</h2>
        <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
          Thêm credential bằng script trên VM: <code>./scripts/add-model-credential.sh &lt;id&gt; &lt;subscription|api_key&gt;</code>
          — secret ghi vào <code>/opt/lsr-platform/secrets/model/</code>, không qua web.
        </p>
        <table>
          <thead><tr><th>ID</th><th>Loại</th><th>Ưu tiên</th><th>Owner</th><th>Trạng thái</th><th>Cooldown đến</th><th></th></tr></thead>
          <tbody>
            {creds.length === 0 && <tr><td colSpan={7} className="muted">Chưa có credential nào — chạy add-model-credential.sh trên VM.</td></tr>}
            {creds.map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.id}</td><td>{c.kind}</td><td>{c.priority}</td>
                <td className="mono" style={{ fontSize: 12 }}>{c.owner_email || "—"}</td>
                <td><span style={{ color: ST[c.status] || "inherit", fontWeight: 600 }}>{c.status}</span></td>
                <td className="muted" style={{ fontSize: 12 }}>{c.cooldown_until ? new Date(c.cooldown_until).toLocaleString("vi") : "—"}</td>
                <td style={{ display: "flex", gap: 4 }}>
                  {c.status !== "active" && <button className="btn" disabled={busy} onClick={() => setStatus(c.id, "active")}>Bật</button>}
                  {c.status !== "disabled" && <button className="btn" disabled={busy} onClick={() => setStatus(c.id, "disabled")}>Tắt</button>}
                  {c.status !== "cooldown" && <button className="btn" disabled={busy} onClick={() => setStatus(c.id, "cooldown")}>Cooldown</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Agent → chế độ auth</h2>
        <table>
          <thead><tr><th>Agent</th><th>auth_mode</th><th>credential riêng</th><th>model fallback</th></tr></thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.agent_id}>
                <td className="mono">{a.agent_id}</td><td>{a.auth_mode}</td>
                <td className="mono" style={{ fontSize: 12 }}>{a.credential_id || "(pool)"}</td>
                <td className="mono" style={{ fontSize: 12 }}>{a.model_fallback || "(mặc định)"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
