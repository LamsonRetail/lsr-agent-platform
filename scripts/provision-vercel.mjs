#!/usr/bin/env node
// Tạo + deploy backend agent lên VERCEL bằng TÀI KHOẢN CỦA OWNER (không dùng platform).
// Tạo project (Root Directory = apps/agents/<id>), set env, deploy, rồi ghi backend_url
// về platform qua API agent-scoped (/v1/self/backend).
//
// Yêu cầu env (của OWNER):
//   VERCEL_TOKEN       token Vercel cá nhân của owner (Account Settings → Tokens)
//   VERCEL_TEAM_ID     (tuỳ chọn) nếu deploy vào team
//   LSR_AGENT_TOKEN    telemetry key của agent (từ enroll) — dùng để set env + ghi backend_url
//   LSR_PLATFORM_URL   mặc định https://platform.34-126-154-135.sslip.io
//   LSR_COLLECTOR      mặc định https://collector.34-126-154-135.sslip.io
//   GIT_REPO           mặc định LamsonRetail/lsr-agent-platform
//
// Dùng:  node scripts/provision-vercel.mjs <AGENT_ID>

const AGENT_ID = (process.argv[2] || "").trim();
if (!AGENT_ID) { console.error("Thiếu <AGENT_ID>. Ví dụ: node scripts/provision-vercel.mjs AG-SALESBOT"); process.exit(1); }

const TOKEN = process.env.VERCEL_TOKEN;
if (!TOKEN) { console.error("Thiếu VERCEL_TOKEN (token Vercel của OWNER)."); process.exit(1); }
const TEAM = process.env.VERCEL_TEAM_ID || "";
const AGENT_TOKEN = process.env.LSR_AGENT_TOKEN || "";
const PLATFORM = process.env.LSR_PLATFORM_URL || "https://platform.34-126-154-135.sslip.io";
const COLLECTOR = process.env.LSR_COLLECTOR || "https://collector.34-126-154-135.sslip.io";
const REPO = process.env.GIT_REPO || "LamsonRetail/lsr-agent-platform";
const NAME = ("agent-" + AGENT_ID.toLowerCase()).replace(/[^a-z0-9-]/g, "-");
const q = TEAM ? `?teamId=${TEAM}` : "";

async function v(method, path, body) {
  const r = await fetch(`https://api.vercel.com${path}${q ? (path.includes("?") ? "&" : "?") + q.slice(1) : ""}`, {
    method,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}: ${JSON.stringify(data).slice(0, 300)}`);
  return data;
}

async function main() {
  // 1) Tạo project trỏ vào sub-folder của agent trong repo
  console.log(`→ Tạo project Vercel '${NAME}' (rootDir apps/agents/${AGENT_ID})...`);
  let project;
  try {
    project = await v("POST", "/v11/projects", {
      name: NAME, framework: "nextjs", rootDirectory: `apps/agents/${AGENT_ID}`,
      gitRepository: { type: "github", repo: REPO },
    });
  } catch (e) {
    if (String(e).includes("409") || String(e).toLowerCase().includes("exists")) {
      console.log("  (project đã tồn tại — dùng lại)");
      project = await v("GET", `/v9/projects/${NAME}`);
    } else throw e;
  }
  const pid = project.id;

  // 2) Set env cho project (production+preview+development)
  const envs = {
    AGENT_ID, LSR_PLATFORM_URL: PLATFORM, LSR_COLLECTOR: COLLECTOR, LSR_AGENT_TOKEN: AGENT_TOKEN,
  };
  for (const [key, value] of Object.entries(envs)) {
    if (!value) continue;
    try {
      await v("POST", `/v10/projects/${pid}/env`, {
        key, value, type: "encrypted", target: ["production", "preview", "development"],
      });
      console.log(`  set env ${key}`);
    } catch (e) { console.log(`  env ${key}: ${String(e).slice(0, 80)} (bỏ qua nếu đã có)`); }
  }

  // 3) Trigger deploy production (best-effort; nếu lỗi, push git sẽ tự deploy)
  const url = `https://${NAME}.vercel.app`;
  try {
    const link = await v("GET", `/v9/projects/${pid}`);
    const repoId = link?.link?.repoId;
    if (repoId) {
      await v("POST", "/v13/deployments", {
        name: NAME, project: pid, target: "production",
        gitSource: { type: "github", repoId, ref: "main" },
      });
      console.log("  ✓ đã kích hoạt deploy production");
    } else {
      console.log("  (chưa lấy được repoId — push lên main hoặc bấm Deploy trên Vercel để build)");
    }
  } catch (e) { console.log(`  deploy: ${String(e).slice(0, 120)} — có thể deploy tay trên Vercel`); }

  // 4) Ghi backend_url về platform (agent-scoped, dùng LSR_AGENT_TOKEN)
  if (AGENT_TOKEN) {
    const r = await fetch(`${PLATFORM}/v1/self/backend`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${AGENT_TOKEN}` },
      body: JSON.stringify({ backend_url: url, dashboard_url: url }),
    });
    console.log(`  ghi backend_url về platform: ${r.status === 200 ? "OK" : "lỗi " + r.status}`);
  } else {
    console.log("  (không có LSR_AGENT_TOKEN → chưa ghi backend_url; set thủ công sau)");
  }

  console.log(`\n✅ Xong. Backend: ${url}`);
}

main().catch((e) => { console.error("✗ " + e.message); process.exit(1); });
