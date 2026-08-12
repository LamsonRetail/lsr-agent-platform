"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

type TC = { q: string; expect: string };

const STEPS = ["Thông tin", "Use case", "Test case", "Hành vi", "Kênh & tạo"];

export default function NoCodeWizard({ defaultOwner }: { defaultOwner: string }) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState<any>(null);

  const [name, setName] = useState("");
  const [aid, setAid] = useState("");
  const [owner, setOwner] = useState(defaultOwner);
  const [usecase, setUsecase] = useState("");
  const [tests, setTests] = useState<TC[]>([{ q: "", expect: "" }, { q: "", expect: "" }]);
  const [instruction, setInstruction] = useState("");
  const [model, setModel] = useState("");
  const [skills, setSkills] = useState("");
  const [chChannel, setChChannel] = useState("");
  const [chChatId, setChChatId] = useState("");

  function slug(s: string) {
    return "AG-" + s.normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24);
  }

  const okStep: boolean[] = [
    !!name.trim() && /^AG-[A-Z0-9-]+$/.test(aid),
    usecase.trim().length >= 30,
    tests.filter(t => t.q.trim() && t.expect.trim()).length >= 2,
    instruction.trim().length > 0,
    true,
  ];

  async function create() {
    setBusy(true); setErr("");
    try {
      const payload = {
        agent_id: aid, name, owner,
        usecase_md: usecase,
        testcases: tests.filter(t => t.q.trim() && t.expect.trim())
          .map(t => ({ q: t.q.trim(), expect: t.expect.split(",").map(x => x.trim()).filter(Boolean) })),
        instruction_block: instruction,
        model: model || undefined,
        skills: skills.split(",").map(s => s.trim()).filter(Boolean),
        channels: chChannel && chChatId ? [{ channel: chChannel, chat_id: chChatId }] : [],
      };
      const r = await fetch("/api/admin", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: "/v1/agents/nocode", payload }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.error === "string" ? d.error : JSON.stringify(d.error));
      setDone(d);
    } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="card">
        <h2 style={{ marginTop: 0 }}>✅ Đã tạo {done.agent_id}</h2>
        <p>Agent đã sẵn sàng — platform tự chạy, không cần cài gì thêm.</p>
        <ul style={{ fontSize: 13.5 }}>
          <li>Console riêng: <a href={`/agent/${done.agent_id}`}>/agent/{done.agent_id}</a> — vào đó bấm <b>Chat thử</b></li>
          <li>Sửa hành vi: <a href={`/builder?agent=${done.agent_id}`}>Builder</a> (publish prod cần admin duyệt)</li>
          <li>Gán thêm kênh: <a href="/jobs">Ingress</a></li>
        </ul>
        <p className="muted" style={{ fontSize: 12 }}>
          Khoá telemetry (chỉ hiện một lần, dùng khi bạn muốn tự chạy agent bằng code):
          <br /><span className="mono">{done.telemetry_key}</span>
        </p>
        <button className="btn btn-p" onClick={() => router.push(`/agent/${done.agent_id}`)}>
          Vào console của agent →
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {STEPS.map((s, i) => (
          <span key={s} style={{
            padding: "3px 10px", borderRadius: 999, fontSize: 12,
            background: i === step ? "var(--accent,#b8791f)" : "transparent",
            color: i === step ? "#fff" : i < step ? "#2e9e5b" : "var(--muted,#888)",
            border: "1px solid " + (i <= step ? "transparent" : "var(--border,#ddd)"),
          }}>{i < step ? "✓ " : `${i + 1}. `}{s}</span>
        ))}
      </div>

      <div className="card">
        {step === 0 && (
          <>
            <h2 style={{ marginTop: 0 }}>Thông tin agent</h2>
            <label>Tên agent<br />
              <input value={name} style={{ width: "100%" }} placeholder="vd: Trợ lý kho Hà Nội"
                onChange={e => { setName(e.target.value); if (!aid || aid === slug(name)) setAid(slug(e.target.value)); }} />
            </label>
            <label style={{ display: "block", marginTop: 8 }}>Mã agent<br />
              <input value={aid} onChange={e => setAid(e.target.value.toUpperCase())} className="mono" style={{ width: "100%" }} />
              <span className="muted" style={{ fontSize: 11 }}>Dạng AG-TEN-VIET-HOA, không đổi được sau khi tạo.</span>
            </label>
            <label style={{ display: "block", marginTop: 8 }}>Chủ sở hữu<br />
              <input value={owner} onChange={e => setOwner(e.target.value)} style={{ width: "100%" }} />
            </label>
          </>
        )}

        {step === 1 && (
          <>
            <h2 style={{ marginTop: 0 }}>Use case <span style={{ color: "#d1495b" }}>*bắt buộc</span></h2>
            <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
              Agent giải quyết việc gì? Ai dùng, qua kênh nào? Luồng chính? Cái gì <b>ngoài phạm vi</b>?
              Viết rõ ở đây thì agent mới trả lời đúng việc — đây cũng là điều kiện để sang bước sau.
            </p>
            <textarea value={usecase} onChange={e => setUsecase(e.target.value)} rows={10}
              style={{ width: "100%", fontSize: 13.5 }}
              placeholder={"Bài toán: ...\nNgười dùng: ...\nLuồng chính:\n1. ...\nNgoài phạm vi: ..."} />
            <span className="muted" style={{ fontSize: 11 }}>{usecase.trim().length}/30 ký tự tối thiểu</span>
          </>
        )}

        {step === 2 && (
          <>
            <h2 style={{ marginTop: 0 }}>Test case <span style={{ color: "#d1495b" }}>*tối thiểu 2</span></h2>
            <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
              Mỗi case: câu hỏi thử + từ khoá phải có trong câu trả lời (phân tách bằng dấu phẩy).
              Dùng để chạy kiểm tra tự động về sau.
            </p>
            {tests.map((t, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                <input value={t.q} placeholder={`Câu hỏi ${i + 1}`} style={{ flex: 2 }}
                  onChange={e => setTests(tests.map((x, j) => j === i ? { ...x, q: e.target.value } : x))} />
                <input value={t.expect} placeholder="từ khoá kỳ vọng, cách nhau dấu phẩy" style={{ flex: 2 }}
                  onChange={e => setTests(tests.map((x, j) => j === i ? { ...x, expect: e.target.value } : x))} />
                <button className="btn" onClick={() => setTests(tests.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
            <button className="btn" onClick={() => setTests([...tests, { q: "", expect: "" }])}>+ Thêm case</button>
          </>
        )}

        {step === 3 && (
          <>
            <h2 style={{ marginTop: 0 }}>Hành vi (instruction)</h2>
            <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
              Mô tả agent nên trả lời thế nào: vai trò, giọng điệu, việc được/không được làm.
            </p>
            <textarea value={instruction} onChange={e => setInstruction(e.target.value)} rows={9}
              style={{ width: "100%", fontSize: 13.5 }}
              placeholder="Bạn là trợ lý kho Hà Nội. Trả lời ngắn gọn, dựa trên tri thức đã duyệt. Không đoán số liệu..." />
            <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
              <label>Model<br /><input value={model} onChange={e => setModel(e.target.value)} placeholder="(mặc định)" /></label>
              <label>Kỹ năng<br /><input value={skills} onChange={e => setSkills(e.target.value)} placeholder="vd: tra_kho, bao_cao" /></label>
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <h2 style={{ marginTop: 0 }}>Kênh vào (tuỳ chọn)</h2>
            <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
              Bỏ trống cũng được — <b>Chat thử trong console luôn dùng được</b>. Kênh có thể gán sau ở Ingress.
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap" }}>
              <label>Kênh<br /><select value={chChannel} onChange={e => setChChannel(e.target.value)}>
                <option value="">— không gán —</option>
                <option value="telegram">Telegram</option>
                <option value="lark">Lark</option>
              </select></label>
              <label>chat_id<br /><input value={chChatId} onChange={e => setChChatId(e.target.value)}
                placeholder="Telegram: nhắn bot /id để lấy" style={{ minWidth: 240 }} /></label>
            </div>
            <div className="card" style={{ marginTop: 12, background: "var(--surface-2,#0000000a)" }}>
              <b>Tóm tắt</b>
              <ul style={{ fontSize: 13 }}>
                <li>Agent: <span className="mono">{aid}</span> — {name}</li>
                <li>Use case: {usecase.trim().length} ký tự</li>
                <li>Test case: {tests.filter(t => t.q && t.expect).length}</li>
                <li>Kênh: {chChannel && chChatId ? `${chChannel} · ${chChatId}` : "chỉ web chat"}</li>
              </ul>
            </div>
          </>
        )}

        {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>← Quay lại</button>}
          {step < 4 && (
            <button className="btn btn-p" disabled={!okStep[step]} onClick={() => setStep(step + 1)}>
              Tiếp →
            </button>
          )}
          {step === 4 && (
            <button className="btn btn-p" disabled={busy || !okStep.every(Boolean)} onClick={create}>
              {busy ? "Đang tạo…" : "Tạo agent"}
            </button>
          )}
          {step < 4 && !okStep[step] && (
            <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>
              {step === 1 ? "Cần mô tả use case (≥30 ký tự)"
                : step === 2 ? "Cần ít nhất 2 test case đầy đủ"
                  : step === 3 ? "Cần nhập instruction" : "Điền tên và mã agent hợp lệ"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
