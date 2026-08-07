"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

function useApi() {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  async function call(url: string, body: any, key = "x") {
    setBusy(key); setMsg("");
    try {
      const r = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof (j.detail ?? j.error) === "string"
        ? (j.detail ?? j.error) : JSON.stringify(j.detail ?? j.error));
      setMsg("✓ Đã lưu.");
      router.refresh();
      return j;
    } catch (e: any) { setMsg("✗ " + String(e.message || e)); }
    finally { setBusy(""); }
  }
  const admin = (path: string, payload: any, key?: string) =>
    call("/api/admin", { path, payload }, key);
  return { call, admin, busy, msg, setMsg };
}

/* ---------------- Tab 1: Kiến thức chờ duyệt ---------------- */
export function PendingTab({ items }: { items: any[] }) {
  const { call, busy, msg } = useApi();
  const [email, setEmail] = useState("");
  return (
    <>
      <div className="card row">
        <span className="muted">Bạn là</span>
        <input placeholder="email reviewer" value={email}
          onChange={(e) => setEmail(e.target.value)} style={{ width: 300 }} />
        <span className="muted">Quyền duyệt kiểm theo chuyên môn (403 nếu sai domain).</span>
      </div>
      {msg && <p className={msg.startsWith("✗") ? "err" : "muted"}>{msg}</p>}
      <table>
        <thead><tr><th>Tiêu đề</th><th>Chuyên môn</th><th>Từ team</th><th>Hành động</th></tr></thead>
        <tbody>
          {items.length === 0 && <tr><td colSpan={4} className="muted">Không có mục nào chờ duyệt.</td></tr>}
          {items.map((it) => (
            <tr key={it.item_id}>
              <td><b>{it.title}</b><div className="muted">{it.item_id}</div></td>
              <td><span className="b b-series">{it.domain || "—"}</span></td>
              <td>{it.source_team || "—"}</td>
              <td className="row">
                <button className="btn btn-p" disabled={!email || busy === it.item_id}
                  onClick={() => call(`/api/knowledge/${it.item_id}/review`,
                    { reviewer_email: email, decision: "approved" }, it.item_id)}>Duyệt</button>
                <button className="btn" disabled={!email || busy === it.item_id}
                  onClick={() => call(`/api/knowledge/${it.item_id}/review`,
                    { reviewer_email: email, decision: "rejected" }, it.item_id)}>Từ chối</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/* ---------------- Tab 2: Shared beliefs (import + sửa trước khi lưu) ---------------- */
export function BeliefsTab({ beliefs, domains }: { beliefs: any[]; domains: any[] }) {
  const { admin, busy, msg, setMsg } = useApi();
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [domain, setDomain] = useState("");
  const [drafts, setDrafts] = useState<any[]>([]);

  async function readFile(f: File) {
    setFilename(f.name);
    if (/\.(txt|md|markdown|csv)$/i.test(f.name)) setText(await f.text());
    else setMsg("✗ PDF/Word: hãy copy nội dung dán vào ô bên dưới (chưa hỗ trợ parse nhị phân ở trình duyệt).");
  }

  async function suggest() {
    const j = await admin("/v1/shared-beliefs/suggest",
      { text, domain, filename: filename || "paste" }, "suggest");
    if (j?.suggestions) {
      setDrafts(j.suggestions);
      setMsg(j.suggestions.length ? `✓ Trích ${j.suggestions.length} đề xuất — sửa rồi lưu.`
                                  : "Không tìm thấy câu mang tính nguyên tắc.");
    }
  }

  const upd = (i: number, k: string, v: string) =>
    setDrafts((d) => d.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Import từ file → chỉnh sửa → cập nhật</h3>
        <div className="row" style={{ marginBottom: 8 }}>
          <input type="file" accept=".txt,.md,.markdown,.csv,.pdf,.docx"
            onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])} />
          <select value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">— chuyên môn —</option>
            {domains.map((d: any) => <option key={d.domain} value={d.domain}>{d.label || d.domain}</option>)}
          </select>
        </div>
        <textarea rows={4} style={{ width: "100%", marginBottom: 8 }}
          placeholder="Nội dung tài liệu (hoặc dán từ PDF/Word)"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn btn-p" disabled={!text || busy === "suggest"} onClick={suggest}>
          {busy === "suggest" ? "Đang trích..." : "Trích đề xuất"}
        </button>
        {msg && <p className={msg.startsWith("✗") ? "err" : "muted"}>{msg}</p>}
      </div>

      {drafts.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Đề xuất ({drafts.length}) — sửa trước khi lưu</h3>
          {drafts.map((d, i) => (
            <div key={i} className="row" style={{ marginBottom: 8, alignItems: "flex-start" }}>
              <input value={d.title} onChange={(e) => upd(i, "title", e.target.value)}
                style={{ width: 200 }} placeholder="Tiêu đề" />
              <textarea rows={2} style={{ flex: 1, minWidth: 320 }} value={d.statement}
                onChange={(e) => upd(i, "statement", e.target.value)} />
              <button className="btn btn-p" disabled={busy === "s" + i}
                onClick={() => admin("/v1/shared-beliefs",
                  { ...d, domain: d.domain || domain, updated_by: "admin" }, "s" + i)}>Lưu</button>
              <button className="btn" onClick={() => setDrafts((x) => x.filter((_, j) => j !== i))}>Bỏ</button>
            </div>
          ))}
        </div>
      )}

      <h3>Shared beliefs hiện có ({beliefs.length}) — chỉ admin sửa</h3>
      <table>
        <thead><tr><th>Niềm tin</th><th>Chuyên môn</th><th className="n">Ver</th><th>Hành động</th></tr></thead>
        <tbody>
          {beliefs.length === 0 && <tr><td colSpan={4} className="muted">Chưa có belief nào.</td></tr>}
          {beliefs.map((b: any) => (
            <BeliefRow key={b.belief_id} b={b} onSave={(p: any) => admin("/v1/shared-beliefs", p, b.belief_id)}
              onDelete={() => admin(`/v1/shared-beliefs/${b.belief_id}/delete`, {}, b.belief_id)}
              busy={busy === b.belief_id} />
          ))}
        </tbody>
      </table>
    </>
  );
}

function BeliefRow({ b, onSave, onDelete, busy }: any) {
  const [edit, setEdit] = useState(false);
  const [stmt, setStmt] = useState(b.statement || "");
  return (
    <tr>
      <td>
        <b>{b.title || b.belief_id}</b>
        {edit ? <textarea rows={2} style={{ width: "100%" }} value={stmt}
          onChange={(e) => setStmt(e.target.value)} />
              : <div className="muted">{b.statement}</div>}
      </td>
      <td>{b.domain || "—"}</td>
      <td className="n">v{b.version}</td>
      <td className="row">
        {edit
          ? <button className="btn btn-p" disabled={busy}
              onClick={() => { onSave({ ...b, statement: stmt, updated_by: "admin" }); setEdit(false); }}>Lưu</button>
          : <button className="btn" onClick={() => setEdit(true)}>Sửa</button>}
        <button className="btn" disabled={busy} onClick={onDelete}>Xoá</button>
      </td>
    </tr>
  );
}

/* ---------------- Tab 3: Phụ trách chuyên môn ---------------- */
export function ReviewersTab({ reviewers, domains }: { reviewers: any[]; domains: any[] }) {
  const { admin, busy, msg } = useApi();
  const [email, setEmail] = useState("");
  const [domain, setDomain] = useState("");
  const [newDomain, setNewDomain] = useState("");
  const [label, setLabel] = useState("");
  const [keywords, setKeywords] = useState("");

  return (
    <>
      {msg && <p className={msg.startsWith("✗") ? "err" : "muted"}>{msg}</p>}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Chuyên môn (tag/keywords)</h3>
        <div className="row" style={{ marginBottom: 10 }}>
          <input placeholder="mã chuyên môn (vd ops)" value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)} style={{ width: 170 }} />
          <input placeholder="tên hiển thị" value={label}
            onChange={(e) => setLabel(e.target.value)} style={{ width: 190 }} />
          <input placeholder="keywords, phân cách phẩy" value={keywords}
            onChange={(e) => setKeywords(e.target.value)} style={{ width: 280 }} />
          <button className="btn btn-p" disabled={!newDomain || busy === "d"}
            onClick={() => admin("/v1/knowledge/domains",
              { domain: newDomain, label, keywords }, "d")}>+ Thêm chuyên môn</button>
        </div>
        <table>
          <thead><tr><th>Chuyên môn</th><th>Keywords</th><th>Hành động</th></tr></thead>
          <tbody>
            {domains.length === 0 && <tr><td colSpan={3} className="muted">Chưa có chuyên môn nào.</td></tr>}
            {domains.map((d: any) => (
              <tr key={d.domain}>
                <td><b>{d.label || d.domain}</b><div className="muted">{d.domain}</div></td>
                <td>{(d.keywords || []).map((k: string) => (
                  <span key={k} className="b b-series" style={{ marginRight: 4 }}>{k}</span>))}</td>
                <td><button className="btn" disabled={busy === d.domain}
                  onClick={() => admin(`/v1/knowledge/domains/${d.domain}/delete`, {}, d.domain)}>Xoá</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Người phụ trách</h3>
        <div className="row" style={{ marginBottom: 10 }}>
          <input placeholder="email nhân sự" value={email}
            onChange={(e) => setEmail(e.target.value)} style={{ width: 260 }} />
          <select value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">— chọn chuyên môn —</option>
            {domains.map((d: any) => (
              <option key={d.domain} value={d.domain}>
                {(d.label || d.domain)}{(d.keywords || []).length ? ` · ${(d.keywords || []).join(", ")}` : ""}
              </option>
            ))}
            <option value="*">* (mọi chuyên môn)</option>
          </select>
          <button className="btn btn-p" disabled={!email || !domain || busy === "r"}
            onClick={() => admin("/v1/knowledge/reviewers", { email, domain }, "r")}>+ Cấp quyền</button>
        </div>
        <table>
          <thead><tr><th>Email</th><th>Chuyên môn</th><th>Do ai cấp</th><th>Hành động</th></tr></thead>
          <tbody>
            {reviewers.length === 0 && <tr><td colSpan={4} className="muted">Chưa cấp quyền cho ai.</td></tr>}
            {reviewers.map((r: any, i: number) => (
              <tr key={i}>
                <td>{r.email}</td>
                <td><span className="b b-series">{r.domain}</span></td>
                <td className="muted">{r.added_by}</td>
                <td><button className="btn" disabled={busy === r.email + r.domain}
                  onClick={() => admin("/v1/knowledge/reviewers/remove",
                    { email: r.email, domain: r.domain }, r.email + r.domain)}>Gỡ</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ---------------- Khung tab ---------------- */
export function ReviewTabs({ items, beliefs, reviewers, domains }: any) {
  const [tab, setTab] = useState<"pending" | "beliefs" | "reviewers">("pending");
  const T = ({ id, children }: any) => (
    <button className={`navlink${tab === id ? " active" : ""}`} onClick={() => setTab(id)}>{children}</button>
  );
  return (
    <>
      <div className="row" style={{ margin: "6px 0 16px", gap: 6 }}>
        <T id="pending">Kiến thức chờ duyệt ({items.length})</T>
        <T id="beliefs">Shared beliefs ({beliefs.length})</T>
        <T id="reviewers">Phụ trách chuyên môn ({reviewers.length})</T>
      </div>
      {tab === "pending" && <PendingTab items={items} />}
      {tab === "beliefs" && <BeliefsTab beliefs={beliefs} domains={domains} />}
      {tab === "reviewers" && <ReviewersTab reviewers={reviewers} domains={domains} />}
    </>
  );
}
