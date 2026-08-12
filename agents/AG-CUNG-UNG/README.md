# Agent · Trợ lý Cung Ứng (`AG-CUNG-UNG`)
Owner: **trinm@hapas.vn** · squad: **SQ-CUNGUNG** · connect: **bot**

Đầu mối tri thức/dữ liệu chung cho team Cung Ứng (ai trong team cũng hỏi được, trả
lời có trích dẫn nguồn) + trợ lý biên bản họp (transcript → draft → xin xác nhận →
tạo task + lưu vào kho tri thức). Xem chi tiết nghiệp vụ ở [USECASE.md](USECASE.md)
và luồng kỹ thuật ở [WORKFLOW.md](WORKFLOW.md).

## Chạy thử nhanh (Docker, giống thật)
```bash
cp .env.example .env && vi .env   # điền LSR_AGENT_TOKEN + CLAUDE_CONFIG_DIR
docker compose up
```
hoặc chạy thẳng (trên máy đã `claude setup-token` sẵn):
`LSR_AGENT_TOKEN=<token> python3 consumer.py`

## Trả lời bằng model thật (Claude Agent SDK)
`consumer.py` ưu tiên gọi **Claude Agent SDK** (auth subscription của OWNER, không API
key) cho câu hỏi tri thức chung — xem hàm `ask_model()`. Cần:
1. Owner đã `claude setup-token` trên máy/VPS chạy agent (token lưu ở `~/.claude`).
2. `pip install -r requirements.txt` (cài `claude-agent-sdk`) — Dockerfile đã tự làm,
   kèm cài Node + `@anthropic-ai/claude-code` (CLI mà SDK gọi xuống).
3. `docker-compose.yml` mount `CLAUDE_CONFIG_DIR` (đường dẫn `~/.claude` của owner) vào
   container.

Nếu SDK chưa cài / chưa đăng nhập / lỗi mạng → `ask_model()` trả `None`, `answer()` tự
**fallback về luật đơn giản** (trích excerpt tri thức hoặc từ chối) — agent không crash,
vẫn test được (`tests.jsonl`) khi chưa nối model thật.

> **Chưa test end-to-end với subscription thật** (môi trường code không có credential/
> Docker) — owner cần tự verify bằng `docker compose up` sau khi có token trước khi
> golive cho người dùng thật.

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
├── requirements.txt       # claude-agent-sdk (tuỳ chọn — cho ask_model() gọi model thật)
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
