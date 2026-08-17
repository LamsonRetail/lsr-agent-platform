# LSR Agent Platform — hướng dẫn cho Claude Code

Repo này chứa **LSR Agent Platform** (LamsonRetail): core platform + các project agent.
Nếu bạn (Claude) vừa clone repo từ link GitHub trong một folder mới, đọc phần
"Bắt đầu một agent" bên dưới TRƯỚC KHI làm gì khác.

## Bắt đầu một agent (khi người dùng đưa link repo)

Mỗi agent là một project Claude Code nằm ở `agents/<AGENT-ID>/` trên **branch riêng
của team** — KHÔNG nằm trên main. Hỏi người dùng họ thuộc team nào rồi checkout:

| Agent | Branch | Thư mục làm việc |
|---|---|---|
| **AG-HR** (HR Agent — mới, chờ điền use case) | `agent/hr-AG-HR` | `agents/AG-HR/` |
| AG-SQ-THAILAND (squad Thái Lan) | `agent/thailand-AG-SQ-THAILAND` | `agents/AG-SQ-THAILAND/` |
| AG-SOURCING (team Sourcing) | `agent/sourcing-AG-SOURCING` | `agents/AG-SOURCING/` |
| AG-MAI-KDONLINE (KD Online VN) | `feature/vn-agent-mai` | `agents/AG-MAI-KDONLINE/` |
| AG-DATA-SUPPORT (team Data) | main | `agents/AG-DATA-SUPPORT/` |

```bash
git checkout <branch> && git pull
bash scripts/lsr-login.sh          # đăng nhập platform 1 lần (không cần xin token của ai)
```

Sau đó **đọc `agents/<ID>/CLAUDE.md`** — đó là hướng dẫn chính của project agent
(quy trình, token, cách test). Agent CHƯA có trong bảng? Scaffold mới:
`bash scripts/new-agent.sh AG-TEN "Tên"` trên branch mới `agent/<team>-AG-TEN`.

## Luật bắt buộc (gate tự động, đừng cố lách)

1. **USE CASE → TEST CASE → code**: `USECASE.md` + `TESTCASES.md` phải được điền
   trước khi viết code agent — plugin PreToolUse + CI `agent-gate` sẽ chặn.
2. **Chỉ sửa trong `agents/<ID>/` của mình** — PR đụng `infra/ src/ scripts/ plugins/
   apps/` sẽ bị CI `scope-guard` chặn (core do maintainer giữ).
3. **Secret không vào git**: token/secret chỉ nằm trong `.env` local (đã gitignore)
   hoặc trên VM `/opt/lsr-platform/`. Không paste token vào code/commit.
4. **Đăng nhập bằng `bash scripts/lsr-login.sh`** — mở link, bấm Duyệt trên console,
   token cá nhân lưu ở `~/.lsr/token`. KHÔNG đi xin `LSR_ENROLL_TOKEN` của ai nữa.
5. Agent mới đăng ký có **token tự động**. Người tạo là **admin platform** → agent
   **ACTIVE luôn**; người khác → `registered`, test web chat được ngay, admin duyệt
   mới chạy kênh thực (Lark/Telegram) + A2A.

## Cấu trúc repo (tham khảo nhanh)

- `agents/` — project của từng agent (mỗi agent 1 docker, tự chạy được)
- `infra/lsr-platform/` — core platform trên VM: platform_api, collector, gateway,
  telegram_bot, nocode_runtime, AG-OPS/AG-EVAL, Caddy, compose (maintainer)
- `apps/platform-web/` — console Next.js (https://app.34-126-154-135.sslip.io)
- `scripts/` — new-agent.sh, agent-test.sh, agent-chat.sh, lsr_adopt.py,
  add-model-credential.sh, add-lark-app.sh
- `libs/lsr_lark/` — thư viện Lark dùng chung (broker qua platform, không cầm secret)
- `docs/` — ARCHITECTURE.md (kiến trúc v3), TESTCASES.md (bộ test toàn platform),
  PLAN.md §0 (lộ trình P1–P10)

## Lệnh hay dùng

```bash
bash scripts/agent-test.sh <AGENT-ID>     # chạy tests.jsonl qua Chat API platform
bash scripts/agent-chat.sh <AGENT-ID>     # chat thử với agent từ terminal
docker compose up                          # chạy agent local (trong agents/<ID>/)
```

Platform API: `https://platform.34-126-154-135.sslip.io` · Console: `https://app.34-126-154-135.sslip.io`
