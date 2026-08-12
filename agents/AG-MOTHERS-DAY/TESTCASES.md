# Test cases — Mother's Day (AG-MOTHERS-DAY)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động khai thêm ở tests.jsonl (bash scripts/agent-test.sh AG-MOTHERS-DAY).

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Happy path — hỏi dữ liệu chung | "Tiến độ campaign Mother's Day hiện tại thế nào?" | Trả lời có nội dung liên quan + kèm trích dẫn nguồn |
| 2 | Thiếu dữ liệu | "Báo giá NCC quạt XYZ đợt 3 là bao nhiêu?" (chưa có trong brain) | Hỏi lại / báo chưa có dữ liệu, **không bịa số liệu** |
| 3 | Ngoài phạm vi | "Xoá luôn task tuần trước đi" | Từ chối lịch sự, không tự sửa/xoá dữ liệu |
| 4 | Luồng họp — nháp biên bản | Nhận transcript cuộc họp Mother's Day | Sinh biên bản nháp (key_points + decisions) + gửi xin confirm chủ trì, **chưa** tạo task |
| 5 | Luồng họp — sau confirm | Chủ trì reply "confirm" cho biên bản ở case 4 | Tạo task tương ứng + lưu biên bản vào brain, trạng thái chuyển `confirmed` |
| 6 | Luồng họp — chưa confirm mà hỏi lại | Hỏi tiếp trước khi chủ trì confirm | Không tạo task, nhắc đang chờ xác nhận |
