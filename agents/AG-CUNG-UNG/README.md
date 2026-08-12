# Agent · Trợ lý Cung Ứng (`AG-CUNG-UNG`)
Owner: **trinm@hapas.vn** · squad: **SQ-CUNGUNG** · connect: **bot**

Đầu mối tri thức/dữ liệu chung cho team Cung Ứng (ai trong team cũng hỏi được, trả
lời có trích dẫn nguồn) + trợ lý biên bản họp (transcript → draft → xin xác nhận →
tạo task + lưu vào kho tri thức). Xem chi tiết nghiệp vụ ở [USECASE.md](USECASE.md)
và luồng kỹ thuật ở [WORKFLOW.md](WORKFLOW.md).

## Chạy thử nhanh (Docker, giống thật)
```bash
cp .env.example .env && vi .env   # điền LSR_AGENT_TOKEN
docker compose up
```
hoặc chạy thẳng: `LSR_AGENT_TOKEN=<token> python3 consumer.py`

Test tự động theo `tests.jsonl`:
```bash
bash scripts/agent-test.sh AG-CUNG-UNG
```
hoặc chat tay: `bash scripts/agent-chat.sh AG-CUNG-UNG "câu hỏi thử"`

## Cấu trúc thư mục
```
AG-CUNG-UNG/
├── lsr-agent.yaml       # manifest agent (chuẩn CI test_agent_standards.py)
├── system_prompt.md     # vai trò + nguyên tắc (kho tri thức + biên bản họp)
├── WORKFLOW.md           # luồng kỹ thuật 2 việc (tra tri thức / biên bản họp)
├── USECASE.md            # bài toán, người dùng, luồng chính, ngoài phạm vi
├── TESTCASES.md           # bảng test case nghiệp vụ + tích hợp platform
├── tests.jsonl            # case ngắn cho scripts/agent-test.sh
├── tests/agent_tests.yaml # bộ test có nhãn (needs_tool) cho 6 chỉ số hành vi
├── consumer.py            # logic agent — CHỈ cần sửa answer()
├── Dockerfile / docker-compose.yml
└── .env.example
```

## Golive (theo chuẩn)
1. Owner đăng nhập subscription RIÊNG: `claude setup-token` (không dùng khoá platform).
2. Đăng ký: `lsr-agent register` (hoặc POST Platform API `/v1/agents/register`) → nhận
   `LSR_AGENT_TOKEN`/`TELEMETRY_API_KEY` riêng agent + tạo schema DB riêng.
3. Kết nối Lark (bot) — add bot vào nhóm Lark team Cung Ứng, điền `chat_ids`.
4. Pass bộ test (`pytest tests/test_agent_standards.py`, `bash scripts/agent-test.sh AG-CUNG-UNG`) → golive.
5. (tuỳ chọn) Backend UI riêng: `node scripts/new-agent-backend.mjs AG-CUNG-UNG "Trợ lý Cung Ứng"`
   — thường KHÔNG cần, console platform (`/agent/AG-CUNG-UNG`) đã đủ chat thử/jobs/traces.

Chuẩn được kiểm bằng CI (`tests/test_agent_standards.py` + `.github/workflows/agent-gate.yml`
+ `.github/workflows/scope-guard.yml`).

## Việc còn để trống (TBD)
- Danh sách nguồn dữ liệu Cung Ứng thật cho `resources.managed_folder` (hiện đặt tên
  tạm `cung-ung-knowledge`).
- `chat_ids` thật của nhóm Lark team Cung Ứng.
- Đăng ký squad `SQ-CUNGUNG` trên Lark Base (admin thực hiện, ngoài repo này).
