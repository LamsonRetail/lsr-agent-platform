# MAI · Trợ lý AI Khối KD Online VN (`AG-MAI-KDONLINE`)

Owner: **minhnd@hapas.vn** *(TODO: đổi sang email Head of Online Business nếu owner là người đó)* ·
Squad: `SQ-KD-ONLINE` · connect: **bot** · Branch team: `feature/vn-agent-mai`

2 brand **HAPAS + MATE MADE** · 3 ngành **Túi xách · Trang sức · Nước hoa**.
Mô tả tính năng cho cả team đọc: `FEATURES.md` · Kế hoạch build: `PLAN.md` ·
Phân công + quy trình git: `PHANCONG.md`.

---

## Cấu trúc

```
agents/AG-MAI-KDONLINE/
├── lsr-agent.yaml        # manifest cho platform (CI kiểm chuẩn)
├── system_prompt.md      # persona + 3 nguyên tắc + luật trích nguồn + phân quyền
├── USECASE.md            # bắt buộc trước khi code (gate CI)
├── TESTCASES.md          # bắt buộc trước khi code (gate CI)
├── PHANCONG.md           # ai làm gì · quy trình git · checklist
├── skills/               # 11 skill .md — MỖI FILE 1 OWNER
├── configs/              # 16 config .json — MỖI KEY 1 OWNER
├── kb/                   # kho tri thức (.md) — nguồn DUY NHẤT MAI được trả lời dựa vào
├── vn/vietnam_tools.py   # MCP server "vn": 32 tool (3 thật + 29 stub)
├── tests/agent_tests.yaml
└── tests.jsonl
```

## Chạy thử ngay (không cần đăng ký gì)

```bash
python3 agents/AG-MAI-KDONLINE/vn/vietnam_tools.py --selftest
```

```bash
python3 agents/AG-MAI-KDONLINE/vn/vietnam_tools.py --list
```

```bash
python3 agents/AG-MAI-KDONLINE/vn/vietnam_tools.py --call vn_kb_index '{"query":"jtbd"}'
```

## Đưa MAI lên platform (Phase 0)

```bash
# 1. Owner đăng nhập subscription RIÊNG (không dùng khoá chung)
claude setup-token

# 2. Đăng ký agent → nhận telemetry key (xin LSR_ENROLL_TOKEN từ admin)
curl -s -X POST "https://platform.34-126-154-135.sslip.io/v1/agents/enroll" \
  -H "Authorization: Bearer $LSR_ENROLL_TOKEN" -H "Content-Type: application/json" \
  -d '{"agent_id":"AG-MAI-KDONLINE","name":"MAI","owner":"minhnd@hapas.vn","squad":"SQ-KD-ONLINE"}'

# 3. Cài plugin telemetry (bắt buộc — không gửi trace = không golive)
claude plugin marketplace add LamsonRetail/lsr-agent-platform
claude plugin install lsr-telemetry@lsr

# 4. Chạy thử qua Telegram trước: nhờ admin gán kênh ở Console → Ingress
#    (channel=telegram, chat_id của nhóm), Lark làm sau.
```

Console của agent: **https://app.34-126-154-135.sslip.io/agent/AG-MAI-KDONLINE**

## Nghiệm thu Phase 0

Hỏi 1 câu về JTBD/ngành → MAI trả lời **có số + tên file**.
Điều kiện: `kb/` đã có file (xem `kb/_README.md`) và `configs/vn_context.json` đã điền.

---

## Khác biệt so với PLAN gốc — đọc trước khi thắc mắc

PLAN viết trên giả định repo công ty là codebase **Jenny**. Repo này **không phải Jenny** —
đây là **LSR Agent Platform** (registry agent · telemetry bắt buộc · RBAC · runtime container
· console). Ba điều chỉnh, phần còn lại của PLAN giữ nguyên:

| PLAN gốc | Thực tế repo này | Vì sao |
|---|---|---|
| "Tái dùng xương sống Jenny: gateway Lark OAuth polling, vòng lặp agent, dashboard" | Tái dùng **platform**: event gateway + job queue + Telegram/Lark routing + telemetry + console **đã có sẵn** | Không phải build gateway. Việc còn lại là gán kênh ở Console → Ingress |
| Configs nằm trên **Supabase**, sửa là đổi ngay | Configs là `configs/*.json` **trong git** | Platform dùng **Postgres** (schema/agent), chưa có config store per-agent cho agent dạng code. Đổi config = commit + PR (vài phút) thay vì tức thì |
| `vn/vietnam_tools.py` ở gốc repo · `skills/vn-*.md` ở gốc repo | Tất cả nằm trong `agents/AG-MAI-KDONLINE/` | CI **scope-guard** chặn PR của người không phải maintainer nếu đụng ra ngoài `agents/<id>/` |

Thêm 1 tool ngoài danh sách PLAN §4: **`vn_config_get`** — không có nó thì MAI không đọc được
config (MAI bị cấm `Bash`/`Write`/`Edit` trên VPS), và nguyên tắc "sửa config không cần sửa
code" sẽ không chạy được.

## Trạng thái tool

| Nhóm | Số tool | Trạng thái |
|---|---|---|
| Tri thức | 4 | ✅ `vn_kb_index` · `vn_kb_read` · `vn_config_get` chạy thật · `vn_review_report` stub |
| Ads-ops (10 bước) | 10 | ⬜ stub — Phase 1→3 |
| Báo cáo (WBR) | 4 | ⬜ stub — Phase 1 |
| Mùa vụ & mốc BST | 4 | ⬜ stub — Phase 1 |
| Giao việc RACI | 5 | ⬜ stub — Phase 2 |
| Nghiên cứu | 4 | ⬜ stub — Phase 2 |
| Họp | 1 | ⬜ stub — Phase 3 |

Stub trả về `status: not_implemented` + phase — **không bao giờ trả dữ liệu giả**.

## Đang chặn

| Chặn | Việc | Ai |
|---|---|---|
| Demo Phase 0 | Nạp file tri thức vào `kb/` | Các PM ngành + TP Digital |
| Dòng 9 phân công | Chốt PIC People Ops Khối KD Online | Head of Online Business |
| Manifest | Xác nhận owner email của agent | Head of Online Business |
| Phase 1 (B8) | Chốt Ads Manager / sàn dùng API hay export CSV | TP Digital Perf. |
| Chạy thật | Xin `LSR_ENROLL_TOKEN` + gán kênh Telegram ở Console | Admin platform |
