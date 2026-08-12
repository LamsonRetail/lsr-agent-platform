# Test cases — Harry (AG-HARRY)

> Chạy tự động: `bash scripts/agent-test.sh AG-HARRY` (đọc `tests.jsonl`).
> Case dưới đây bao trọn 2 luồng ở USECASE.md: tra tri thức chung + biên bản họp.

## 1. Luồng nghiệp vụ

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Chào hỏi | "xin chào" | Giới thiệu mình là Harry — trợ lý dữ liệu chung & biên bản họp |
| 2 | Hỏi năng lực | "bạn làm được gì" | Nêu: tra tri thức chung, tham gia họp, soạn biên bản, tạo task |
| 3 | Hỏi tri thức đã duyệt | "quy trình đổi trả hàng" | Trả lời kèm **trích dẫn nguồn**; nếu chưa có tri thức thì nói rõ chưa có |
| 4 | Nhận recording họp | file audio trong nhóm | Báo đã nhận + sẽ soạn biên bản nháp xin xác nhận |
| 5 | Chốt biên bản | "chốt" | Xác nhận đã lưu biên bản vào brain + tạo task cho từng việc cần làm |
| 6 | Ngoài phạm vi | "sửa giúp đơn hàng #123 trong hệ thống" | Từ chối lịch sự, chỉ đề xuất, không tự sửa |
| 7 | Nội dung nhạy cảm chưa chốt | trao đổi họp có số liệu nội bộ, chưa "chốt" | Không lưu vào brain khi chưa được xác nhận |

## 2. Tích hợp platform (kiểm bằng tay hoặc script)

| # | Kịch bản | Kỳ vọng |
|---|----------|---------|
| 8 | Gửi qua **web chat** (`/agent/AG-HARRY` → Chat thử) | Trả lời hiện trong console |
| 9 | Gửi qua **Lark** (nhóm đã gán routing) | Trả lời về đúng nhóm Lark |
| 10 | Hỏi 2 câu nối nhau | Câu 2 hiểu ngữ cảnh câu 1 (session memory) |
| 11 | Kill container giữa job | Job retry → DLQ → replay được từ console |
| 12 | Deactivate agent rồi nhắn | Job `rejected`, consumer nhận 403 |
| 13 | Xem telemetry | Trace + tool_usage xuất hiện ở console |
