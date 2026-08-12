# Test cases — Minh Anh (AG-MINH-ANH)

> Chạy tự động: `bash scripts/agent-test.sh AG-MINH-ANH` (đọc `tests.jsonl`).
> Case dưới đây bao trọn luồng ở USECASE.md + các tích hợp platform.

## 1. Luồng nghiệp vụ

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Chào hỏi | "xin chào" | Giới thiệu mình là trợ lý biên bản họp |
| 2 | Hỏi năng lực | "bạn làm được gì" | Nêu: biên bản họp, chốt task, tra tri thức |
| 3 | Nhận recording | file audio trong nhóm | Báo đã nhận + sẽ dựng biên bản xin xác nhận |
| 4 | Chốt biên bản | "chốt" | Xác nhận đã chốt + tạo task |
| 5 | Ngoài phạm vi | "cho tôi số điện thoại khách hàng X" | Từ chối lịch sự, không bịa |
| 6 | Hỏi tri thức đã duyệt | "quy trình nhập kho" | Trả lời kèm **trích dẫn nguồn**; nếu chưa có tri thức thì nói rõ chưa có |

## 2. Tích hợp platform (kiểm bằng tay hoặc script)

| # | Kịch bản | Kỳ vọng |
|---|----------|---------|
| 7 | Gửi qua **web chat** (`/agent/AG-MINH-ANH` → Chat thử) | Trả lời hiện trong console |
| 8 | Gửi qua **Telegram** (chat đã gán routing) | Trả lời về đúng chat Telegram |
| 9 | Gửi qua **Lark** (nhóm đã gán routing) | Trả lời về đúng nhóm Lark |
| 10 | Hỏi 2 câu nối nhau | Câu 2 hiểu ngữ cảnh câu 1 (session memory) |
| 11 | Kill container giữa job | Job retry → DLQ → replay được từ console |
| 12 | Deactivate agent rồi nhắn | Job `rejected`, consumer nhận 403 |
| 13 | Xem telemetry | Trace + tool_usage xuất hiện ở console |
