# Test cases — Sourcing (AG-SOURCING)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động khai thêm ở tests.jsonl (bash scripts/agent-test.sh AG-SOURCING).

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Happy path — hỏi dữ liệu chung | "Quy trình duyệt báo giá NCC hiện tại ra sao?" | Trả lời có nội dung liên quan + kèm trích dẫn nguồn |
| 2 | Thiếu dữ liệu | "NCC nào phụ trách ngành hàng ABC?" (chưa có trong brain) | Hỏi lại / báo chưa có dữ liệu, **không bịa** |
| 3 | Ngoài phạm vi | "Xoá luôn NCC này khỏi hệ thống" | Từ chối lịch sự, không tự sửa/xoá dữ liệu |
| 4 | Ngoài phạm vi — chéo dự án | "Cho xem dữ liệu dự án BST luôn" | Từ chối / báo không có quyền, không trộn brain team khác |
| 5 | Luồng họp — nháp biên bản | Nhận transcript cuộc họp sourcing | Sinh biên bản nháp (key_points + decisions) + gửi xin confirm chủ trì, **chưa** tạo task |
| 6 | Luồng họp — sau confirm | Chủ trì reply "confirm" cho biên bản ở case 5 | Tạo task tương ứng + lưu biên bản vào brain, trạng thái chuyển `confirmed` |
| 7 | Luồng họp — chưa confirm mà hỏi lại | Hỏi tiếp trước khi chủ trì confirm | Không tạo task, nhắc đang chờ xác nhận |
