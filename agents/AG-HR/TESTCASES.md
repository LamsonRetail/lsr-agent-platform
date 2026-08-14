# Test cases — HR Agent (AG-HR)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động khai thêm ở tests.jsonl (bash scripts/agent-test.sh AG-HR).

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Happy path | "..." | Trả lời chứa ... |
| 2 | Thiếu dữ liệu | "..." | Hỏi lại, không bịa |
| 3 | Ngoài phạm vi | "..." | Từ chối lịch sự + chỉ đúng kênh |
