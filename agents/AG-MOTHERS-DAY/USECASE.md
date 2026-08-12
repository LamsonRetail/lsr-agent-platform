# Use case — Mother's Day (AG-MOTHERS-DAY)

> ⚠️ BẮT BUỘC điền trước khi code (gate của platform sẽ chặn code nếu thiếu file này).

## Bài toán
Dự án "Mother's Day" (campaign) có nhiều đầu việc chạy song song (sourcing NCC,
báo giá, tiến độ sản xuất/nhập hàng, kế hoạch truyền thông...) nhưng dữ liệu và
quyết định đang rải rác trong nhiều nhóm chat/file khác nhau. Thành viên mới hoặc
người ngoài squad tốn nhiều thời gian hỏi lại "hiện tới đâu rồi", và biên bản họp
hay bị bỏ sót/ghi chậm nên việc dễ trôi.

## Người dùng
- **Thành viên dự án Mother's Day** (mọi phòng ban tham gia) — qua nhóm Lark của
  dự án, hoặc web chat thử trong console platform.
- **Chủ trì cuộc họp / thư ký dự án** — khi agent được add vào cuộc họp để lấy
  transcript và soạn biên bản.

## Luồng chính (happy path)

**A. Hỏi — đáp dữ liệu chung (data hub)**
1. Thành viên hỏi trong nhóm Lark/web chat, ví dụ: "báo giá NCC quạt đợt này tới
   đâu rồi?", "tiến độ campaign Mother's Day hiện tại thế nào?".
2. Agent gọi `/v1/self/context` lấy tri thức đã duyệt liên quan (đã được đưa vào
   brain riêng của agent) + lịch sử hội thoại.
3. Agent trả lời kèm **trích dẫn nguồn** (link Lark Doc/Base gốc); nếu không có
   dữ liệu liên quan → hỏi lại, không bịa.

**B. Tham gia họp → tự soạn biên bản** (theo mẫu đã chạy ở Minh Anh)
1. Agent được add vào nhóm/cuộc họp Mother's Day → nhận transcript (Whisper).
2. Trích `key_points` + `decisions` → soạn biên bản nháp.
3. Gửi biên bản cho chủ trì **xin xác nhận** qua Lark IM — trạng thái
   `awaiting_confirm`.
4. Sau khi chủ trì confirm → tạo task (Lark Task) tương ứng + lưu biên bản vào
   brain của agent (để dùng lại ở luồng A) — trạng thái `confirmed`.

## Ngoài phạm vi (không làm)
- Không tạo task/gửi kết quả ra ngoài nhóm dự án khi chưa được confirm.
- Không tự sửa/xoá dữ liệu trong bảng master data chung của platform.
- Không truy cập hoặc trộn tri thức của agent/squad khác (mỗi agent 1 brain riêng).

## Dữ liệu cần truy cập
- **Lark**: tin nhắn nhóm dự án Mother's Day agent được add vào, file/transcript
  cuộc họp (qua connector `lark` dùng chung của platform).
- **Brain riêng của AG-MOTHERS-DAY** (`/v1/self/brain/*`): tri thức đã duyệt về
  campaign — chỉ đọc khi trả lời, ghi khi biên bản đã confirm.
- Không cần quyền BigQuery ở giai đoạn đầu.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** — đổi `DRY_RUN=false`
  khi đã test xong và được duyệt golive.
- Transcript phụ thuộc dịch vụ Whisper ngoài; lỗi → job vào DLQ, replay được từ console.
- Nội dung họp có thể chứa thông tin nhạy cảm (giá NCC, ngân sách) → cần review
  trước khi đưa vào brain chung, tránh lộ ra ngoài squad.
