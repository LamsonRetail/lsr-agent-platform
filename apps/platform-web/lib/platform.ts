// Server-only client tới Platform API + Collector. Admin token KHÔNG bao giờ ra client.
import "server-only";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const C = process.env.LSR_COLLECTOR || "http://localhost:8081";
const ADMIN = process.env.PLATFORM_ADMIN_TOKEN || "";

async function jget(url: string) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

export async function listAgents() { return safe(() => jget(`${P}/v1/agents`), []); }
export async function listTests() { return safe(() => jget(`${P}/v1/tests`), []); }
export async function listAttempts() { return safe(() => jget(`${P}/v1/attempts`), []); }
export async function listTraining() { return safe(() => jget(`${P}/v1/training`), []); }
export async function tokenStats() { return safe(() => jget(`${C}/v1/stats`), []); }

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try { return await fn(); } catch { return fallback; }
}

// Mutations (admin) — dùng trong route handlers.
export async function adminPost(path: string, body: any) {
  const r = await fetch(`${P}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${ADMIN}` },
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
