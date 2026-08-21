# Test cases — Data Support (AG-DATA-SUPPORT)

> Mỗi luồng ở USECASE.md có ít nhất 1 case. Case chạy tự động khai thêm ở `tests.jsonl`
> (`bash scripts/agent-test.sh AG-DATA-SUPPORT`).

| # | Luồng | Kịch bản | Đầu vào | Kỳ vọng |
|---|-------|----------|---------|---------|
| 1 | A. Hỏi dữ liệu | Happy path — có tri thức đã đồng bộ | "Doanh số tuần này của kho HN là bao nhiêu?" (đã có trong Brain từ ingest) | Trả lời có số liệu + trích dẫn nguồn (bảng/thời điểm cập nhật) |
| 2 | A. Hỏi dữ liệu | Chưa có dữ liệu | "Chi phí marketing Q3 năm ngoái?" (chưa được đồng bộ) | Trả lời thẳng "chưa có dữ liệu này", không bịa số |
| 3 | B. Ingest | Đồng bộ BigQuery | Job `bigquery_sync.py` chạy với 1 bảng mẫu | Ghi được ≥1 tri thức mới vào Brain riêng của agent, có `source_url`/tên bảng |
| 4 | B. Ingest | Đồng bộ Lark Base | Job `lark_base_sync.py` chạy với 1 bảng mẫu | Ghi được ≥1 tri thức mới vào Brain riêng của agent, có nguồn |
| 5 | C. Biên bản | Nhận recording → dựng nháp | Gửi 1 đoạn transcript mẫu vào nhóm | Trả lời là bản nháp biên bản có: người tham dự, quyết định, action item |
| 6 | C. Biên bản | Xác nhận → tạo task + lưu Brain | Gửi "chốt" sau bản nháp ở case 5 | Tạo task Lark cho mỗi action item + biên bản chốt xuất hiện lại được khi hỏi ở case 1 |
| 7 | Ngoài phạm vi | Yêu cầu join Zoom | "Vào họp Zoom lúc 3h giúp mình" | Từ chối lịch sự, giải thích v1 chỉ hỗ trợ Lark Meeting |
| 8 | Ngoài phạm vi | Yêu cầu sửa dữ liệu gốc | "Xoá dòng X trong bảng BigQuery Y" | Từ chối, giải thích agent chỉ đọc, không sửa nguồn |
