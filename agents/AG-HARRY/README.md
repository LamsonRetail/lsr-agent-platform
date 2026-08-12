# Agent · Harry (`AG-HARRY`)
Owner: **hoalt@hapas.vn** · squad: **SQ-FA** · connect: **bot**

Trợ lý Dữ liệu & Họp chung của Lam Sơn Retail — tổng hợp tri thức chung ai
cũng tra được, tham gia cuộc họp và tự soạn biên bản. Xem chi tiết use case ở
[USECASE.md](USECASE.md) và test case ở [TESTCASES.md](TESTCASES.md).

## Chạy nhanh (local, không cần Lark)
```bash
claude setup-token                    # đăng nhập subscription RIÊNG của owner (một lần)
cp .env.example .env && vi .env       # điền LSR_AGENT_TOKEN
docker compose up                     # mount sẵn ~/.claude (đọc), gọi model qua claude_agent_sdk
# terminal khác:
bash ../../scripts/agent-test.sh AG-HARRY
bash ../../scripts/agent-chat.sh AG-HARRY "quy trình đổi trả hàng là gì?"
```

Model được gọi qua **Claude Agent SDK** (`claude_agent_sdk.query`, xem
`consumer.py`) — SDK tự dùng phiên đăng nhập subscription cục bộ, không đọc
API key. Container cần Node.js + CLI `@anthropic-ai/claude-code` (đã cài trong
`Dockerfile`) và mount `~/.claude` từ máy đã đăng nhập.

## Golive (theo chuẩn platform)
1. Owner đăng nhập subscription RIÊNG: `claude setup-token` (không dùng khoá platform).
2. Đăng ký: `lsr-agent register` (hoặc POST Platform API `/v1/agents/register`) → nhận
   `TELEMETRY_API_KEY` riêng agent + tạo schema DB riêng.
3. Kết nối Lark (bot) + bật telemetry (đã cấu hình sẵn trong `lsr-agent.yaml`).
4. Pass bộ test (`pytest tests/test_agent_standards.py` ở gốc repo) → golive.

Chuẩn được kiểm bằng CI (`tests/test_agent_standards.py` + `.github/workflows/agent-gate.yml`).
