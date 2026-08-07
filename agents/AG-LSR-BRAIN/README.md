# Agent · LSR Brain (`AG-LSR-BRAIN`)
Owner: **platform@lamsonretail.vn** · connect: **bot**

## Golive (theo chuẩn)
1. Owner đăng nhập subscription RIÊNG:  `claude setup-token`  (không dùng khoá platform).
2. Đăng ký: `lsr-agent register` (hoặc POST Platform API /v1/agents/register) → nhận
   TELEMETRY_API_KEY (riêng agent) + tạo schema DB riêng trên Supabase.
3. Kết nối Lark (bot) + bật telemetry (đã cấu hình).
4. Pass bộ test → golive.
5. (tuỳ chọn) Backend UI riêng: `node scripts/new-agent-backend.mjs AG-LSR-BRAIN "LSR Brain"`.

Chuẩn được kiểm bằng CI (tests/test_agent_standards.py).
