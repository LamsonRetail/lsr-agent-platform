// Phiên đăng nhập console (P8). Token nằm trong cookie httpOnly — không lộ ra client JS.
import "server-only";
import { cookies } from "next/headers";

const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const GATEWAY = process.env.LSR_GATEWAY_TOKEN || "";
export const SESSION_COOKIE = "lsr_session";

export function sessionToken(): string | undefined {
  return cookies().get(SESSION_COOKIE)?.value;
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const t = sessionToken();
  const h: Record<string, string> = { ...extra };
  if (t) h.Authorization = `Bearer ${t}`;
  if (GATEWAY) h["X-Gateway-Token"] = GATEWAY;
  return h;
}

export type Me = {
  email: string; name: string; must_change_pw: boolean;
  platform_role: string | null; agent_roles: Record<string, string>;
  can_manage_accounts: boolean; can_create_agent: boolean;
};

export async function me(): Promise<Me | null> {
  const t = sessionToken();
  if (!t) return null;
  try {
    const r = await fetch(`${P}/v1/auth/me`, { cache: "no-store", headers: authHeaders() });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

/** Quyền hiệu lực trên 1 agent = cao hơn giữa platform role và agent role. */
export function roleOn(m: Me | null, agentId?: string): string | null {
  if (!m) return null;
  const rank: Record<string, number> = { user: 1, moderator: 2, admin: 3 };
  const a = agentId ? m.agent_roles?.[agentId] : undefined;
  const p = m.platform_role || undefined;
  if (!a) return p ?? null;
  if (!p) return a;
  return rank[a] >= rank[p] ? a : p;
}
export function can(m: Me | null, need: "user" | "moderator" | "admin", agentId?: string) {
  const rank: Record<string, number> = { user: 1, moderator: 2, admin: 3 };
  const r = roleOn(m, agentId);
  return !!r && rank[r] >= rank[need];
}
