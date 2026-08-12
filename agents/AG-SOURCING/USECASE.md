# Use case — Sourcing (AG-SOURCING)

> ⚠️ BẮT BUỘC điền trước khi code (gate của platform sẽ chặn code nếu thiếu file này).

## Bài toán
Team Sourcing làm việc với nhiều nhà cung cấp, nhiều ngành hàng (mỗi campaign/dự án
là 1 nhánh riêng, ví dụ Mother's Day, BST...) song song. Dữ liệu chung của cả team
(danh sách NCC, quy trình duyệt báo giá, tiến độ theo ngành hàng) và nội dung các
cuộc họp sourcing đang rải rác, người mới hoặc người khác squad khó tra cứu lại,
biên bản họp hay chậm/sót việc.

## Người dùng
- **Toàn bộ thành viên team Sourcing** (không riêng 1 campaign) — qua nhóm Lark
  chung của team Sourcing, hoặc web chat thử trong console platform.
- **Chủ trì cuộc họp sourcing** — khi agent được add vào họp để lấy transcript và
  soạn biên bản.

## Luồng chính (happy path)

**A. Hỏi — đáp dữ liệu chung (data hub toàn team)**
1. Thành viên hỏi trong nhóm Lark/web chat, ví dụ: "quy trình duyệt báo giá NCC
   hiện tại ra sao?", "NCC nào đang phụ trách ngành hàng X?".
2. Agent gọi `/v1/self/context` lấy tri thức đã duyệt liên quan (brain riêng của
   agent, tổng hợp từ nhiều campaign/dự án con của team Sourcing) + lịch sử hội thoại.
3. Agent trả lời kèm **trích dẫn nguồn** (link Lark Doc/Base gốc); nếu không có
   dữ liệu liên quan → hỏi lại, không bịa.

**B. Tham gia họp sourcing → tự soạn biên bản** (theo mẫu đã chạy ở Minh Anh)
1. Agent được add vào nhóm/cuộc họp sourcing → nhận transcript (Whisper).
2. Trích `key_points` + `decisions` → soạn biên bản nháp.
3. Gửi biên bản cho chủ trì **xin xác nhận** qua Lark IM — trạng thái
   `awaiting_confirm`.
4. Sau khi chủ trì confirm → tạo task (Lark Task) tương ứng + lưu biên bản vào
   brain của agent (để dùng lại ở luồng A) — trạng thái `confirmed`.

## Ngoài phạm vi (không làm)
- Không tạo task/gửi kết quả ra ngoài nhóm Sourcing khi chưa được confirm.
- Không tự sửa/xoá dữ liệu trong bảng master data chung của platform.
- Không truy cập hoặc trộn tri thức của agent/squad khác ngoài Sourcing (mỗi
  agent 1 brain riêng, ví dụ không đụng vào brain/dữ liệu của agent dự án BST).

## Dữ liệu cần truy cập
- **Lark**: tin nhắn nhóm Sourcing agent được add vào, file/transcript cuộc họp
  (qua connector `lark` dùng chung của platform).
- **Brain riêng của AG-SOURCING** (`/v1/self/brain/*`): tri thức đã duyệt của
  team Sourcing — chỉ đọc khi trả lời, ghi khi biên bản đã confirm.
- Không cần quyền BigQuery ở giai đoạn đầu.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** — đổi `DRY_RUN=false`
  khi đã test xong và được duyệt golive.
- Transcript phụ thuộc dịch vụ Whisper ngoài; lỗi → job vào DLQ, replay được từ console.
- Nội dung họp có thể chứa thông tin nhạy cảm (giá NCC, ngân sách) → cần review
  trước khi đưa vào brain chung, tránh lộ ra ngoài team Sourcing.
