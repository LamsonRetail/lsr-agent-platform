# Minh Anh (AG-MINH-ANH) — **Agent demo của platform**

Agent tham chiếu: đã nối sẵn **mọi tích hợp** của platform. Dùng để (1) thử nhanh cách
agent tương tác qua từng kênh, (2) làm khuôn copy khi tạo agent mới.

| Có sẵn | Cách dùng |
|---|---|
| **Lark** | Admin gán routing (channel `lark`, chat_id nhóm) → nhắn trong nhóm là agent trả lời |
| **Telegram** | Admin gán routing (channel `telegram`, chat_id) → nhắn bot là agent trả lời |
| **Web chat** | Mở `https://app.34-126-154-135.sslip.io/agent/AG-MINH-ANH` → **Chat thử** |
| **Agent gọi agent (A2A)** | Cấp `a2a_grant` rồi agent khác gọi được |
| **Brain / RAG** | `/v1/self/context` tự kèm tri thức đã duyệt + nguồn trích dẫn |
| **Nhớ hội thoại** | Session memory ở platform — restart/đổi máy vẫn liền mạch |
| **Version (no-code)** | Sửa instruction ở Console → Builder, không cần deploy lại |
| **Telemetry / chi phí** | Tự động — xem ở Console → Chi phí / Connectors |

> **Không cần Vercel, Supabase hay DB riêng.** Console của agent nằm luôn trong platform:
> `https://app.34-126-154-135.sslip.io/agent/AG-MINH-ANH`

## Chạy

```bash
# 1) Lấy token agent (1 lần) — hỏi admin enroll-token
python3 scripts/lsr_adopt.py --enroll-token <token> --id AG-MINH-ANH \
  --name "Minh Anh" --owner <email của bạn>

# 2a) Chạy bằng Docker (khuyến nghị — giống môi trường thật)
cd agents/AG-MINH-ANH
cp .env.example .env && vi .env          # điền LSR_AGENT_TOKEN
docker compose up

# 2b) Hoặc chạy trực tiếp
LSR_AGENT_TOKEN=... python3 consumer.py
```

`DRY_RUN=true` (mặc định) = chỉ log, **không gửi tin thật** ra Lark/Telegram.
Đổi `DRY_RUN=false` khi muốn trả lời thật.

## Test

```bash
bash scripts/agent-test.sh AG-MINH-ANH          # chạy tests.jsonl qua Chat API
bash scripts/agent-chat.sh AG-MINH-ANH "xin chào"   # chat tay 1 câu
```

## Cấu trúc (copy khuôn này cho agent mới)

```
agents/AG-MINH-ANH/
├── USECASE.md          ← BẮT BUỘC viết trước khi code (gate của platform)
├── TESTCASES.md        ← BẮT BUỘC — bảng case
├── tests.jsonl         ← case chạy tự động
├── consumer.py         ← chỉ cần sửa hàm answer()
├── Dockerfile          ← container riêng của agent
├── docker-compose.yml  ← docker compose up là chạy
└── .env.example
```

Tạo agent mới theo đúng khuôn: `bash scripts/new-agent.sh AG-TEN-AGENT "Tên"`.

## Ghi chú kiến trúc

- Agent **không cầm secret** của Lark/Telegram — gọi qua connector dùng chung của platform.
- Agent **không cần biết kênh**: mọi tin vào cùng hàng đợi; trả lời bằng
  `POST /v1/self/jobs/{id}/reply`, platform tự gửi đúng Lark / Telegram / web / A2A.
- Chi tiết nghiệp vụ cũ (chia sẻ từ điển meeting-notes, luồng biên bản):
  [WORKFLOW.md](../minh-anh/WORKFLOW.md).
