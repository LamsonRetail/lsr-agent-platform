# AG-HR — HR Agent (project Claude Code)

Bạn đang ở project của **HR Agent** trên LSR Agent Platform. Làm việc TRONG thư mục
`agents/AG-HR/` trên branch `agent/hr-AG-HR` — KHÔNG sửa file ngoài thư mục này
(CI scope-guard sẽ chặn PR đụng core platform).

## Quy trình bắt buộc (gate của platform)

1. **Điền `USECASE.md` + `TESTCASES.md` TRƯỚC KHI CODE** — plugin + CI chặn code khi thiếu.
   Use case phải nêu: bài toán HR nào, ai dùng, kênh nào (Lark nhóm HR / web chat), dữ liệu cần.
2. Viết test vào `tests.jsonl` (mỗi dòng: `{"q": "câu hỏi", "expect": ["từ khoá kỳ vọng"]}`).
3. Code `handle()` trong `consumer.py` — chỉ cần sửa hàm này; kết nối platform có sẵn.
4. Chạy local: `docker compose up` (điền `.env` từ `.env.example` trước).
5. Test qua platform: `bash ../../scripts/agent-test.sh AG-HR` (từ gốc repo).

## Kết nối platform (đã đăng ký sẵn)

- Agent id: `AG-HR` — **token đã cấp tự động**, nhờ admin lấy:
  `ssh lsr-gcp "sudo cat /opt/lsr-platform/secrets/agents/AG-HR.env"` → điền vào `.env` (`LSR_AGENT_TOKEN`).
- Trạng thái: `registered` — **test qua web chat console chạy được ngay**
  (https://app.34-126-154-135.sslip.io/agent/AG-HR). Kênh thực (Lark) + A2A chỉ chạy
  sau khi admin ACTIVATE (admin đã nhận thông báo khi agent đăng ký).
- Model auth: dùng **subscription của owner** (`claude setup-token`) — KHÔNG dùng API key chung.
- Context/RAG: gọi `GET /v1/self/context` + `POST /v1/self/brain/search` (xem consumer.py mẫu).
- Trả lời: `POST /v1/self/jobs/{id}/reply` — platform tự chọn kênh (Lark/Telegram/web).
- **Token/Runs trên dashboard**: khi `complete` job, gửi kèm
  `{"usage": {"input_tokens": .., "output_tokens": .., "model": "..."}}` để platform đo chi phí.
  (Run được tự đếm kể cả khi không gửi usage.)

## Master data (bắt buộc trước golive)

Sau khi chốt use case, điền năng lực + hướng dẫn dùng để agent khác/console thấy:
`POST /v1/agents/AG-HR/profile` với `{"capabilities": [...], "usage_guide": "..."}` —
hoặc nhờ admin làm trên console.

## Tham khảo

- Agent demo đầy đủ tích hợp: `agents/AG-MINH-ANH/` (chỉ để tham khảo — không dùng cho việc thực).
- Hướng dẫn onboarding: chạy `bash <(curl -s https://platform.34-126-154-135.sslip.io/bootstrap/onboard.sh)`.
