import "server-only";
// Backend gọi API agent-scoped bằng token của CHÍNH agent (không admin/gateway).
const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const TOK = process.env.LSR_AGENT_TOKEN || "";
export const AGENT_ID = process.env.AGENT_ID || "AG-LEGAL";
function h(){ return TOK ? { "Authorization": "Bearer "+TOK } : {}; }
async function get(u){ const r = await fetch(u, { cache: "no-store", headers: h() }); if(!r.ok) throw new Error(u+" "+r.status); return r.json(); }
async function self(){ return get(P+"/v1/self"); }
export async function agent(){ const d = await self().catch(()=>null); return (d && d.agent) || {agent_id:AGENT_ID}; }
export async function stats(){ const d = await self().catch(()=>null); return (d && d.stats) || {}; }
export async function schema(){ const d = await self().catch(()=>null); return d ? d.db_schema : ""; }
export async function attempts(){ return get(P+"/v1/self/attempts").catch(()=>[]); }
export async function conflicts(){ return get(P+"/v1/self/conflicts").catch(()=>[]); }
export async function traces(n=25){ return get(P+"/v1/self/traces?limit="+n).catch(()=>[]); }
export async function brainItems(){ return get(P+"/v1/self/brain/items").catch(()=>[]); }
export async function brainLinks(){ return get(P+"/v1/self/brain/links").catch(()=>[]); }
export const PLATFORM_URL = P; export const AGENT_TOKEN = TOK;
