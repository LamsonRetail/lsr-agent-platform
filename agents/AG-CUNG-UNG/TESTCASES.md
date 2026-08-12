# Test cases — Trợ lý Cung Ứng (AG-CUNG-UNG)

> Chạy tự động: `bash scripts/agent-test.sh AG-CUNG-UNG` (đọc `tests.jsonl`).
> Case dưới đây bao trọn luồng ở USECASE.md + các tích hợp platform.

## 1. Luồng nghiệp vụ

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Chào hỏi | "xin chào" | Giới thiệu mình là trợ lý Cung Ứng (kho tri thức + biên bản họp) |
| 2 | Hỏi năng lực | "bạn làm được gì" | Nêu: tra tri thức Cung Ứng, dựng biên bản họp, chốt task |
| 3 | Nhận recording | file audio trong nhóm | Báo đã nhận + sẽ dựng biên bản xin xác nhận |
| 4 | Chốt biên bản | "chốt" | Xác nhận đã chốt + tạo task |
| 5 | Ngoài phạm vi | "cho tôi số điện thoại khách hàng X" | Từ chối lịch sự, không bịa |
| 6 | Hỏi tri thức đã duyệt | "quy trình đặt hàng nhà cung cấp X" | Trả lời kèm **trích dẫn nguồn**; nếu chưa có tri thức thì nói rõ chưa có |

## 2. Tích hợp platform (kiểm bằng tay hoặc script)

| # | Kịch bản | Kỳ vọng |
|---|----------|---------|
| 7 | Gửi qua **web chat** (`/agent/AG-CUNG-UNG` → Chat thử) | Trả lời hiện trong console |
| 8 | Gửi qua **Lark** (nhóm team Cung Ứng đã gán routing) | Trả lời về đúng nhóm Lark |
| 9 | Hỏi 2 câu nối nhau | Câu 2 hiểu ngữ cảnh câu 1 (session memory) |
| 10 | Kill container giữa job | Job retry → DLQ → replay được từ console |
| 11 | Deactivate agent rồi nhắn | Job `rejected`, consumer nhận 403 |
| 12 | Xem telemetry | Trace + tool_usage xuất hiện ở console |
