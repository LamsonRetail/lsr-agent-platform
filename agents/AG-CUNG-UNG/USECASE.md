# Use case — Trợ lý Cung Ứng (AG-CUNG-UNG) · **AGENT SQUAD SQ-CUNGUNG**

> Copy cấu trúc thư mục từ agent mẫu `agents/AG-MINH-ANH/` (theo khuyến nghị của
> platform), thu hẹp phạm vi cho squad Cung Ứng: kho tri thức chung + biên bản họp.

## Bài toán
Dữ liệu/tri thức của team Cung Ứng (nhà cung cấp, đơn mua hàng, hợp đồng, tồn kho,
SLA...) đang nằm rải rác, không phải ai cũng tra được. Song song đó, cuộc họp diễn ra
liên tục nhưng biên bản viết tay chậm và hay sót việc. Trợ lý Cung Ứng làm 2 việc:
tổng hợp tri thức về **một nơi** mà mọi thành viên team tương tác được, và tham gia
họp để tự dựng biên bản, xin xác nhận rồi tạo task.

## Người dùng
- **Mọi nhân sự team Cung Ứng** — qua nhóm Lark của team có Trợ lý Cung Ứng.
- **Người chủ trì cuộc họp** — xác nhận biên bản trước khi tạo task.
- **Người thử nhanh** — qua Chat thử trong console platform (`/agent/AG-CUNG-UNG`).

## Luồng chính (happy path)

### A. Tra cứu tri thức Cung Ứng
1. Thành viên gửi câu hỏi (Lark nhóm team, hoặc Chat thử trong console).
2. Agent gọi `/v1/self/context` để lấy tri thức liên quan đã được duyệt trong kho
   `cung-ung-knowledge`.
3. Có tri thức liên quan → trả lời kèm **trích dẫn nguồn**.
4. Không có → nói rõ **chưa có thông tin đã duyệt**, không bịa, gợi ý người hỏi bổ
   sung/nhờ người phụ trách xác nhận thông tin.

### B. Biên bản họp
1. Agent được add vào nhóm/cuộc họp, nhận recording hoặc nội dung trao đổi.
2. Dựng biên bản nháp (key points + decisions) + đề xuất task, gửi lại xin người chủ
   trì **xác nhận**.
3. Người chủ trì trả lời "chốt"/"duyệt"/"confirm" → agent tạo task cho các đầu việc +
   lưu biên bản vào kho tri thức `cung-ung-knowledge`.
4. Câu hỏi tiếp theo về nội dung họp cũ tra được qua luồng A (đã lưu = tri thức đã duyệt).

## Ngoài phạm vi (không làm)
- Không bịa thông tin khi chưa có tri thức đã duyệt tương ứng.
- Không tạo task/lưu biên bản chính thức trước khi có xác nhận của chủ trì.
- Không tự gửi tin cho người ngoài nhóm đang trao đổi.
- Không tự tạo/sửa dữ liệu ở hệ thống khác ngoài Lark (task/docx) — chỉ đề xuất.
- Không trả lời câu hỏi ngoài phạm vi Cung Ứng (dữ liệu khách hàng, phòng ban khác...).

## Dữ liệu cần truy cập
- **Lark**: tin nhắn nhóm team Cung Ứng được add vào, file recording cuộc họp (qua
  connector `lark` dùng chung).
- **Brain**: tri thức đã duyệt trong `cung-ung-knowledge` (`/v1/self/brain/search`) —
  chỉ đọc. Danh sách nguồn dữ liệu thật (supplier/PO/hợp đồng/tồn kho/SLA) — **TBD,
  chờ team Cung Ứng confirm**.
- Không cần quyền BigQuery.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** — đổi `DRY_RUN=false` khi
  chạy thật.
- Transcript phụ thuộc dịch vụ ngoài (Whisper server); lỗi → job vào DLQ, replay được
  từ console.
- Dữ liệu cung ứng (giá, hợp đồng, nhà cung cấp) có thể nhạy cảm → PII/thông tin nhạy
  cảm được che ở collector trước khi lưu; chỉ chia sẻ trong phạm vi team.
