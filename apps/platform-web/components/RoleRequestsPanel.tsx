"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

// Admin duyệt yêu cầu phân quyền per-agent (P10). Người xin không tự duyệt được (API chặn).
export default function RoleRequestsPanel({ requests }: { requests: any[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(0);
  const [note, setNote] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");

  async function decide(id: number, approve: boolean) {
    setBusy(id); setErr("");
    try {
      const r = await fetch("/api/roles/decide", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, approve, note: note[id] || "" }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "duyệt thất bại");
      router.refresh();
    } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(0); }
  }

  return (
    <section className="card">
      <h2 style={{ marginTop: 0 }}>🔑 Yêu cầu phân quyền {requests.length > 0 && <span style={{ color: "#c98a00" }}>({requests.length} chờ duyệt)</span>}</h2>
      {err && <p className="err">{err}</p>}
      {requests.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>Không có yêu cầu nào đang chờ.</p>
      ) : (
        <table>
          <thead><tr><th>#</th><th>Người xin</th><th>Phạm vi</th><th>Quyền</th><th>Lý do</th><th>Ghi chú duyệt</th><th></th></tr></thead>
          <tbody>
            {requests.map((q) => (
              <tr key={q.id}>
                <td>{q.id}</td>
                <td><span className="mono" style={{ fontSize: 12 }}>{q.email}</span><br />
                  <span className="muted" style={{ fontSize: 11 }}>{q.name || ""}</span></td>
                <td className="mono" style={{ fontSize: 12 }}>{q.scope_type === "platform" ? "PLATFORM" : q.scope_id}</td>
                <td><b>{q.role}</b></td>
                <td className="muted" style={{ fontSize: 12, maxWidth: 220 }}>{q.reason || "—"}</td>
                <td><input value={note[q.id] || ""} onChange={(e) => setNote({ ...note, [q.id]: e.target.value })}
                           placeholder="tuỳ chọn" style={{ width: 130 }} /></td>
                <td style={{ display: "flex", gap: 4 }}>
                  <button className="btn btn-p" disabled={busy === q.id} onClick={() => decide(q.id, true)}>Duyệt</button>
                  <button className="btn" disabled={busy === q.id} onClick={() => decide(q.id, false)}>Từ chối</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
