#!/usr/bin/env node
// Tạo một AGENT mới trong platform, theo đúng tiêu chuẩn.
// Sinh manifest agents/<id>/lsr-agent.yaml + system_prompt + bộ test có nhãn.
// Quan trọng: mỗi agent dùng AUTH CỦA OWNER (Claude subscription riêng), KHÔNG
// dùng auth chung của platform.
//
// Dùng:
//   node scripts/new-agent.mjs <AGENT_ID> "Tên" <owner-email> [squad] [bot|user]
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const [id, name, owner, squad = "", mode = "bot"] = process.argv.slice(2);
if (!id || !name || !owner) {
  console.error('Dùng: node scripts/new-agent.mjs <AGENT_ID> "Tên" <owner-email> [squad] [bot|user]');
  process.exit(1);
}
if (!/^[^@]+@[^@]+\.[^@]+$/.test(owner)) { console.error("owner phải là email của người sở hữu agent."); process.exit(1); }
if (!["bot", "user"].includes(mode)) { console.error("connect_mode phải là bot hoặc user."); process.exit(1); }

const dir = join(root, "agents", id);
if (existsSync(dir)) { console.error(`Đã tồn tại: agents/${id}`); process.exit(1); }
const w = (rel, c) => { const p = join(dir, rel); mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, c); };

w("lsr-agent.yaml",
`apiVersion: lsr/v1
agent:
  id: ${id}
  name: ${name}
  version: 0.1.0
  owner: ${owner}           # OWNER thật của agent — auth dùng subscription của người này
  squad: ${squad || '""'}
  is_squad_agent: false
  connect_mode: ${mode}     # bot | user
  description: >
    (mô tả agent)

lark:
  connect_mode: ${mode}
  bot:
    app: platform-shared
    chat_ids: []
    event_webhook: https://collector.lsr.internal/lark/events

runtime:
  sdk: claude-agent-sdk
  auth: subscription        # BẮT BUỘC: đăng nhập subscription của OWNER (claude login /
                            # setup-token). KHÔNG dùng api key, KHÔNG dùng auth chung platform.
  model: claude-sonnet-5

skills:                     # MCP tự do — chỉ khai báo + log
  - {name: resource-index, type: builtin}

telemetry:
  enabled: true             # BẮT BUỘC (control point) — agent không gửi trace = không golive
  collector: https://collector.lsr.internal

tests:
  suite: tests/agent_tests.yaml
schedule: []
`);

w("system_prompt.md",
`# System prompt — ${name}

Bạn là ${name} của LamsonRetail. (điền vai trò, nguyên tắc)

## Nguyên tắc chung (chuẩn platform)
- File/link được share: index ra ngoài (resource index), KHÔNG nhồi vào memory.
- Telemetry bật: mọi request/tool/token ghi về collector.
- Auth bằng subscription của OWNER (${owner}) — không dùng khoá chung.
`);

w("tests/agent_tests.yaml",
`# Bộ test có nhãn (needs_tool để đo TSR/CTUR/RIR/OFR/UTR/CTRL-Acc).
tests:
  - question_id: q1
    prompt: "(câu hỏi kiểm tra)"
    expected: "(đáp án mong đợi)"
    assertion_type: contains
    needs_tool: false
`);

w("README.md",
`# Agent · ${name} (\`${id}\`)
Owner: **${owner}** · connect: **${mode}**

## Golive (theo chuẩn)
1. Owner đăng nhập subscription RIÊNG:  \`claude setup-token\`  (không dùng khoá platform).
2. Đăng ký: \`lsr-agent register\` (hoặc POST Platform API /v1/agents/register) → nhận
   TELEMETRY_API_KEY (riêng agent) + tạo schema DB riêng trên Supabase.
3. Kết nối Lark (${mode}) + bật telemetry (đã cấu hình).
4. Pass bộ test → golive.
5. (tuỳ chọn) Backend UI riêng: \`node scripts/new-agent-backend.mjs ${id} "${name}"\`.

Chuẩn được kiểm bằng CI (tests/test_agent_standards.py).
`);

console.log(`✓ Tạo agents/${id} (owner ${owner}). Kiểm chuẩn: pytest tests/test_agent_standards.py`);
