import { PLATFORM_URL, AGENT_TOKEN } from "@/lib/platform";
// Gửi/resolve Lark qua broker platform — token + danh bạ open_id dùng chung toàn tổ chức.
async function call(path: string, payload: any) {
  const r = await fetch(PLATFORM_URL + path, { method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + AGENT_TOKEN },
    body: JSON.stringify(payload || {}) });
  return r.json().catch(() => ({}));
}
export function larkSend(to: string, text: string, opts: { markdown?: string; to_type?: string } = {}) {
  return call("/v1/lark/send", { to, text, markdown: opts.markdown || "", to_type: opts.to_type || "email" });
}
export function larkResolve(email: string) { return call("/v1/lark/resolve", { email }); }
