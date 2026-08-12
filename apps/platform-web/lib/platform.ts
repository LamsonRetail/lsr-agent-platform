// Server-only client tới Platform API + Collector. Admin token KHÔNG bao giờ ra client.
import "server-only";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const C = process.env.LSR_COLLECTOR || "http://localhost:8081";
const ADMIN = process.env.PLATFORM_ADMIN_TOKEN || "";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";
// Item 2: danh tính người thao tác, do LỚP WEB (server-side) đóng dấu — không tin body.
// Tạm dùng env; khi có SSO/RBAC sẽ set từ session của user đăng nhập.
const ACTOR = process.env.PLATFORM_ACTOR || "web-admin";

// Header gateway (Caddy) — bắt buộc khi gọi qua public HTTPS; rỗng khi dev qua tunnel.
function gwHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return GATEWAY ? { "X-Gateway-Token": GATEWAY, ...extra } : extra;
}

async function jget(url: string) {
  const r = await fetch(url, { cache: "no-store", headers: gwHeaders() });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

export async function listAgents() { return safe(() => jget(`${P}/v1/agents`), []); }
export async function listTests() { return safe(() => jget(`${P}/v1/tests`), []); }
export async function listAttempts() { return safe(() => jget(`${P}/v1/attempts`), []); }
export async function listTraining() { return safe(() => jget(`${P}/v1/training`), []); }
export async function tokenStats() { return safe(() => jget(`${C}/v1/stats`), []); }

// --- Cost & Quota ---
export async function costSummary(period?: string) {
  const q = period ? `?period=${period}` : "";
  return safe(() => jget(`${P}/v1/cost/summary${q}`), { period: "", total_usd: 0, total_tokens: 0, total_runs: 0, agents: [] });
}
export async function costTimeseries(period?: string) {
  const q = period ? `?period=${period}` : "";
  return safe(() => jget(`${P}/v1/cost/timeseries${q}`), { period: "", series: [] });
}
export async function quotas() { return safe(() => jget(`${P}/v1/quotas`), []); }

// --- A1 audit / A3 health / A4 golden+regression ---
export async function auditLog(params = "") { return safe(() => jget(`${P}/v1/audit${params}`), []); }
export async function healthAgents() { return safe(() => jget(`${P}/v1/health/agents`), { threshold_hours: 24, agents: [], n_problem: 0 }); }
export async function goldenCases() { return safe(() => jget(`${P}/v1/golden-cases`), []); }
export async function regressionRuns() { return safe(() => jget(`${P}/v1/regression/runs`), []); }

// --- Per-agent dashboard/backend ---
export async function agentDetail(id: string) { return safe(() => jget(`${P}/v1/agents/${id}`), null); }
export async function agentTraces(id: string, limit = 20) { return safe(() => jget(`${C}/v1/traces?agent_id=${id}&limit=${limit}`), []); }
export async function conflictsForAgent(id: string) { return safe(() => jget(`${P}/v1/knowledge/conflicts?status=open&agent_id=${id}`), []); }
export async function auditForTarget(id: string) { return safe(() => jget(`${P}/v1/audit?target_id=${id}&limit=30`), []); }
export async function brainGraph(qs = "") { return safe(() => jget(`${P}/v1/brain/graph${qs}`), { nodes: [], links: [], counts: {} }); }
export async function brainItems(qs = "?scope=shared") { return safe(() => jget(`${P}/v1/brain/items${qs}`), []); }
export async function brainSkills(qs = "?scope=shared") { return safe(() => jget(`${P}/v1/brain/skills${qs}`), []); }
export async function brainPolicies() { return safe(() => jget(`${P}/v1/brain/policies`), []); }
export async function brainLinks(qs = "") { return safe(() => jget(`${P}/v1/brain/links${qs}`), []); }

// --- P1: Ingress (routing + jobs/DLQ) — cần admin token ---
async function jgetAdmin(url: string) {
  const r = await fetch(url, { cache: "no-store", headers: gwHeaders({ Authorization: `Bearer ${ADMIN}` }) });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
export async function routingList() { return safe(() => jgetAdmin(`${P}/v1/routing`), []); }
export async function jobsList(qs = "") { return safe(() => jgetAdmin(`${P}/v1/jobs${qs}`), []); }
// P3: Agent versions (Builder)
export async function agentVersions(id: string) { return safe(() => jgetAdmin(`${P}/v1/agents/${id}/versions`), []); }
export async function versionResolve(id: string, env = "prod") {
  return safe(() => jgetAdmin(`${P}/v1/agents/${id}/versions/resolve?env=${env}`),
    { agent_id: id, env, version: null, config: null });
}
// P2: Model Auth pool
export async function modelCredentials() {
  return safe(() => jgetAdmin(`${P}/v1/model-auth/credentials`),
    { credentials: [], agents: [], pool_subscription_usable: 0, pool_api_usable: 0 });
}

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try { return await fn(); } catch { return fallback; }
}

// Mutations (admin) — dùng trong route handlers.
export async function adminPost(path: string, body: any) {
  const r = await fetch(`${P}${path}`, {
    method: "POST",
    headers: gwHeaders({ "Content-Type": "application/json", Authorization: `Bearer ${ADMIN}`, "X-Actor": ACTOR }),
    body: JSON.stringify(body ?? {}),
  });
  const text = await r.text();
  let data: any;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!r.ok) {
    const err: any = new Error("platform api error");
    err.status = r.status; err.data = data;
    throw err;
  }
  return data;
}

export const PLATFORM_URL = P;

// Upload multipart (admin) — dùng cho /v1/extract (parse PDF/Word server-side).
export async function adminForm(path: string, form: FormData) {
  const r = await fetch(`${P}${path}`, {
    method: "POST",
    headers: gwHeaders({ Authorization: `Bearer ${ADMIN}`, "X-Actor": ACTOR }),
    body: form,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err: any = new Error("platform api error");
    err.status = r.status; err.data = data;
    throw err;
  }
  return data;
}

// --- LSR Brain: shared brain + hàng chờ duyệt ---
export async function pendingKnowledge() { return safe(() => jget(`${P}/v1/knowledge/items?status=pending`), []); }
export async function approvedKnowledge() { return safe(() => jget(`${P}/v1/knowledge/items?status=approved`), []); }
export async function openConflicts() { return safe(() => jget(`${P}/v1/knowledge/conflicts?status=open`), []); }
export async function sharedBrain() { return safe(() => jget(`${P}/v1/shared-brain`), { beliefs: [], knowledge: [] }); }
export async function reviewers() { return safe(() => jget(`${P}/v1/knowledge/reviewers`), []); }
export async function knowledgeDomains() { return safe(() => jget(`${P}/v1/knowledge/domains`), []); }
