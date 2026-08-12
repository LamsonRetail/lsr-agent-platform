# Use case — Minh Anh (AG-MINH-ANH) · **AGENT DEMO CỦA PLATFORM**

> Đây là agent **mẫu tham chiếu**: mọi tích hợp của platform đã nối sẵn
> (Lark · Telegram · web chat · brain/RAG · session memory · version · telemetry).
> Team tạo agent mới nên **copy cấu trúc thư mục này**.

## Bài toán
Cuộc họp diễn ra liên tục nhưng biên bản viết tay chậm và hay sót việc. Minh Anh
nhận recording/nội dung trao đổi trong nhóm, dựng biên bản, xin xác nhận của chủ trì
rồi tạo task — để không ai phải ngồi gõ lại.

## Người dùng
- **Chủ trì cuộc họp / thư ký** — qua nhóm Lark có Minh Anh, hoặc chat Telegram.
- **Người thử nhanh** — qua Chat thử trong console platform (`/agent/AG-MINH-ANH`).

## Luồng chính (happy path)
1. Người dùng gửi tin (Lark / Telegram / web chat) — mọi kênh vào **cùng một hàng đợi**.
2. Minh Anh lấy job, gọi `/v1/self/context` để có: instruction (version đang publish)
   + tóm tắt hội thoại + N lượt gần nhất + fact người dùng + tri thức liên quan.
3. Xử lý theo loại nội dung:
   - **Recording (audio/file)** → dựng biên bản nháp, gửi lại xin xác nhận.
   - **"chốt" / "duyệt" / "confirm"** → tạo task + lưu biên bản vào brain.
   - **Câu hỏi thường** → trả lời dựa trên tri thức đã duyệt, có trích dẫn nguồn.
4. Trả lời bằng `/v1/self/jobs/{id}/reply` — platform tự gửi đúng kênh người hỏi.
5. Ghi lượt hội thoại để lượt sau còn ngữ cảnh.

## Ngoài phạm vi (không làm)
- Không tự gửi tin cho người ngoài nhóm đang trao đổi.
- Không tự tạo/sửa dữ liệu hệ thống khác (chỉ đề xuất).
- Không lưu nội dung nhạy cảm vào brain khi chưa được duyệt.

## Dữ liệu cần truy cập
- **Lark**: tin nhắn nhóm được add vào, file recording (qua connector `lark` dùng chung).
- **Brain**: tri thức đã duyệt (`/v1/self/brain/search`) — chỉ đọc.
- Không cần quyền BigQuery.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** — đổi `DRY_RUN=false` khi chạy thật.
- Transcript phụ thuộc dịch vụ ngoài; lỗi → job vào DLQ, replay được từ console.
- Nội dung họp có thể chứa thông tin nhạy cảm → PII được che ở collector trước khi lưu.
