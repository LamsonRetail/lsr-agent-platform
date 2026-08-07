import "server-only";
const P = process.env.LSR_PLATFORM_URL || "http://localhost:8090";
const C = process.env.LSR_COLLECTOR || "http://localhost:8081";
const GW = process.env.LSR_GATEWAY_TOKEN || "";
export const AGENT_ID = process.env.AGENT_ID || "AG-ORDER-BOT";
function h(){ return GW ? { "X-Gateway-Token": GW } : {}; }
async function get(u){ const r = await fetch(u, { cache: "no-store", headers: h() }); if(!r.ok) throw new Error(u+" "+r.status); return r.json(); }
export async function agent(){ const all = await get(P+"/v1/agents").catch(()=>[]); return (all||[]).find(a=>a.agent_id===AGENT_ID) || {agent_id:AGENT_ID}; }
export async function stats(){ const all = await get(C+"/v1/stats").catch(()=>[]); return (all||[]).find(s=>s.agent_id===AGENT_ID) || {}; }
export async function attempts(){ return get(P+"/v1/attempts?taker_id="+encodeURIComponent(AGENT_ID)).catch(()=>[]); }
