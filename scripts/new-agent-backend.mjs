#!/usr/bin/env node
// Scaffold backend riêng cho một agent, ngay trong monorepo: apps/agents/<id>/
// Mỗi agent-backend là 1 Next.js app nhỏ (server-side gọi Platform API theo agent_id),
// deploy chung repo với platform (Vercel: Root Directory = apps/agents/<id>).
//
// Dùng:  node scripts/new-agent-backend.mjs <agent-id> [Tên hiển thị]
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const id = (process.argv[2] || "").trim();
const name = (process.argv[3] || id).trim();
if (!id) { console.error("Thiếu <agent-id>. Ví dụ: node scripts/new-agent-backend.mjs AG-ORDER-BOT 'Order Bot'"); process.exit(1); }

const dir = join(root, "apps", "agents", id);
if (existsSync(dir)) { console.error(`Đã tồn tại: apps/agents/${id}`); process.exit(1); }
const w = (rel, content) => { const p = join(dir, rel); mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, content); };

w("package.json", JSON.stringify({
  name: `agent-backend-${id.toLowerCase()}`, private: true, version: "0.1.0",
  scripts: { dev: "next dev", build: "next build", start: "next start" },
  dependencies: { next: "^14.2.35", react: "18.3.1", "react-dom": "18.3.1", "server-only": "0.0.1" },
  devDependencies: { typescript: "5.5.4", "@types/node": "20.14.0", "@types/react": "18.3.3", "@types/react-dom": "18.3.0" },
}, null, 2) + "\n");

w("next.config.mjs", `const nextConfig = { reactStrictMode: true, output: "standalone" };\nexport default nextConfig;\n`);

w("tsconfig.json", JSON.stringify({
  compilerOptions: { target: "ES2021", lib: ["dom", "dom.iterable", "esnext"], allowJs: true,
    skipLibCheck: true, strict: false, noEmit: true, esModuleInterop: true, module: "esnext",
    moduleResolution: "bundler", resolveJsonModule: true, isolatedModules: true, jsx: "preserve",
    incremental: true, plugins: [{ name: "next" }], baseUrl: ".", paths: { "@/*": ["./*"] } },
  include: ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"], exclude: ["node_modules"],
}, null, 2) + "\n");

w(".gitignore", "node_modules/\n.next/\n.env\n.env.local\nnext-env.d.ts\n.vercel\n");
w("public/.gitkeep", "");

w(".env.example",
`# Agent backend — chạy trong monorepo, deploy chung platform.
AGENT_ID=${id}
LSR_PLATFORM_URL=https://platform.34-126-154-135.sslip.io
LSR_COLLECTOR=https://collector.34-126-154-135.sslip.io
PLATFORM_ADMIN_TOKEN=...
LSR_GATEWAY_TOKEN=...
`);

w("Dockerfile",
`FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node","server.js"]
`);

w("lib/platform.ts",
`import "server-only";
const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const C = process.env.LSR_COLLECTOR || "http://localhost:8081";
const GW = process.env.LSR_GATEWAY_TOKEN || "";
export const AGENT_ID = process.env.AGENT_ID || "${id}";
function h(){ return GW ? { "X-Gateway-Token": GW } : {}; }
async function get(u){ const r = await fetch(u, { cache: "no-store", headers: h() }); if(!r.ok) throw new Error(u+" "+r.status); return r.json(); }
export async function agent(){ const all = await get(P+"/v1/agents").catch(()=>[]); return (all||[]).find(a=>a.agent_id===AGENT_ID) || {agent_id:AGENT_ID}; }
export async function stats(){ const all = await get(C+"/v1/stats").catch(()=>[]); return (all||[]).find(s=>s.agent_id===AGENT_ID) || {}; }
export async function attempts(){ return get(P+"/v1/attempts?taker_id="+encodeURIComponent(AGENT_ID)).catch(()=>[]); }
export async function conflicts(){ return get(P+"/v1/knowledge/conflicts?status=open&agent_id="+encodeURIComponent(AGENT_ID)).catch(()=>[]); }
export const PLATFORM_URL = P;
`);

w("app/api/conflicts/[id]/resolve/route.ts",
`import { NextResponse } from "next/server";
import { PLATFORM_URL } from "@/lib/platform";
export async function POST(req, { params }) {
  const body = await req.json().catch(() => ({}));
  const gw = process.env.LSR_GATEWAY_TOKEN;
  const r = await fetch(PLATFORM_URL + "/v1/knowledge/conflicts/" + params.id + "/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(gw ? { "X-Gateway-Token": gw } : {}) },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return NextResponse.json(data, { status: r.status });
}
`);

w("components/Conflicts.tsx",
`"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

/** Mâu thuẫn shared brain vs brain của agent — CHỈ agent owner xác nhận (ở backend agent). */
export default function Conflicts({ conflicts, ownerHint }) {
  const router = useRouter();
  const [email, setEmail] = useState(ownerHint || "");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  async function resolve(id, decision) {
    setBusy(id); setMsg("");
    try {
      const r = await fetch("/api/conflicts/" + id + "/resolve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, owner_email: email }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j));
      setMsg("✓ Đã xác nhận."); router.refresh();
    } catch (e) { setMsg("✗ " + String(e.message || e)); } finally { setBusy(""); }
  }
  return (<>
    <h3>Mâu thuẫn cần xác nhận ({conflicts.length})</h3>
    <div className="row" style={{ marginBottom: 10 }}>
      <span className="m">Owner xác nhận:</span>
      <input value={email} onChange={(e) => setEmail(e.target.value)}
        placeholder="email agent owner" style={{ width: 260 }} />
    </div>
    {msg && <p className="m">{msg}</p>}
    <table><thead><tr><th>Shared brain nói</th><th>Agent brain nói</th><th>Xác nhận</th></tr></thead>
    <tbody>
      {conflicts.length === 0 && <tr><td colSpan={3} className="m">Không có mâu thuẫn nào.</td></tr>}
      {conflicts.map((c) => (
        <tr key={c.conflict_id}>
          <td>{c.shared_claim}</td>
          <td>{c.agent_claim}</td>
          <td>
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_keep_shared")}>Giữ shared</button>{" "}
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "resolved_update_shared")}>Đề xuất cập nhật</button>{" "}
            <button className="btn" disabled={!email || busy === c.conflict_id}
              onClick={() => resolve(c.conflict_id, "dismissed")}>Bỏ qua</button>
          </td>
        </tr>
      ))}
    </tbody></table>
  </>);
}
`);

w("app/globals.css",
`:root{--s:#fcfcfb;--p:#f9f9f7;--t:#0b0b0b;--m:#898781;--b:rgba(11,11,11,.1);--a:#2a78d6;--good:#0ca30c;--crit:#d03b3b}
@media(prefers-color-scheme:dark){:root{--s:#1a1a19;--p:#0d0d0d;--t:#fff;--m:#898781;--b:rgba(255,255,255,.1);--a:#3987e5}}
*{box-sizing:border-box}body{margin:0;background:var(--p);color:var(--t);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
.wrap{max-width:900px;margin:0 auto;padding:26px 22px}h1{font-size:22px;margin:0 0 4px}.m{color:var(--m);font-size:12px}
.k{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0}.c{background:var(--s);border:1px solid var(--b);border-radius:12px;padding:13px 16px;min-width:120px}
.c .v{font-size:24px;font-weight:700}table{width:100%;border-collapse:collapse;background:var(--s);border:1px solid var(--b);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--b)}th{font-size:11px;text-transform:uppercase;color:var(--m)}tr:last-child td{border-bottom:0}
.bg{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;border:1px solid var(--b)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.btn{border:1px solid var(--b);background:var(--s);color:var(--t);padding:5px 10px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:12.5px}
.btn:disabled{opacity:.5;cursor:not-allowed}
input{font-family:inherit;font-size:13px;padding:6px 9px;border-radius:8px;border:1px solid var(--b);background:var(--s);color:var(--t)}
`);

w("app/layout.tsx",
`import "./globals.css";
export const metadata = { title: "Agent Backend · ${name}" };
export default function L({ children }){ return (<html lang="vi"><body><div className="wrap">{children}</div></body></html>); }
`);

w("app/page.tsx",
`import { agent, stats, attempts, conflicts, AGENT_ID } from "@/lib/platform";
import Conflicts from "@/components/Conflicts";
export const dynamic = "force-dynamic";
export default async function Page(){
  const [a, s, at, cf] = await Promise.all([agent(), stats(), attempts(), conflicts()]);
  return (<>
    <h1>Backend · {a.name || AGENT_ID}</h1>
    <div className="m">{AGENT_ID} · squad {a.squad || "—"} · owner {a.owner || "—"} · <span className="bg">{a.status || "?"}</span></div>
    <div className="k">
      <div className="c"><div className="m">Token</div><div className="v">{(s.total_tokens||0).toLocaleString()}</div></div>
      <div className="c"><div className="m">Runs</div><div className="v">{s.runs||0}</div></div>
      <div className="c"><div className="m">Lượt làm bài</div><div className="v">{(at||[]).length}</div></div>
    </div>
    <h3>Kết quả làm bài</h3>
    <table><thead><tr><th>Bài</th><th>Điểm</th><th>Kết quả</th></tr></thead><tbody>
      {(at||[]).length===0 && <tr><td colSpan={3} className="m">chưa có</td></tr>}
      {(at||[]).map(x=>(<tr key={x.attempt_id}><td>{x.test_id}</td><td>{Math.round((x.score||0)*100)}</td><td>{x.passed?"pass":"fail"}</td></tr>))}
    </tbody></table>
    <Conflicts conflicts={cf} ownerHint={a.owner || ""} />
    <p className="m" style={{marginTop:16}}>Backend riêng của agent — deploy chung repo platform. Thêm Config/Schedule tại đây.</p>
  </>);
}
`);

w("README.md",
`# Agent backend · ${name} (\`${id}\`)
Backend riêng của agent, nằm chung monorepo. Deploy:
- **Vercel:** project riêng, Root Directory = \`apps/agents/${id}\`, set env (xem .env.example).
- **Self-host:** thêm service vào infra docker-compose trỏ build tới thư mục này.
Chạy dev: \`cp .env.example .env.local && npm install && npm run dev\`.
`);

console.log(`✓ Tạo apps/agents/${id} (${name}). Tiếp: cd apps/agents/${id} && npm install && npm run build`);
