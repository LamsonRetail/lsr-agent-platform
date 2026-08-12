# Use case — Harry (AG-HARRY)

## Bài toán
Tri thức/quy trình của squad **Finance & Accounting (SQ-FA)** — quy trình
thanh toán, công tác phí, đối chiếu công nợ, báo cáo tài chính... — đang nằm
rải rác (chat, file, đầu người, Lark Wiki), ai cần tra lại phải hỏi người
khác. Song song, các cuộc họp FA diễn ra liên tục nhưng biên bản viết tay
chậm, hay sót việc. Harry gom hai việc này vào một nơi: trợ lý mà ai trong FA
cũng tương tác được để tra tri thức chung, và cũng là người ghi/soạn biên bản
khi tham gia họp.

## Người dùng
- **Mọi nhân viên** cần tra tri thức/dữ liệu chung — qua nhóm Lark có Harry
  hoặc Chat thử trong console platform (`/agent/AG-HARRY`).
- **Chủ trì cuộc họp / thư ký** — thêm Harry vào nhóm họp để nhận biên bản.

## Luồng chính (happy path)

### A. Tra tri thức chung
1. Người dùng hỏi trong nhóm Lark hoặc web chat.
2. Harry gọi `/v1/self/context` (brain + tóm tắt hội thoại + fact người dùng).
3. Trả lời dựa trên tri thức đã duyệt, **kèm trích dẫn nguồn**; nếu chưa có
   tri thức phù hợp, nói rõ chưa có — không bịa.

### B. Tham gia họp & soạn biên bản
1. Trong nhóm họp, người dùng gửi recording hoặc gõ lại nội dung trao đổi.
2. Harry dựng **biên bản nháp** (mục tiêu, quyết định, việc cần làm + người
   phụ trách) và gửi lại nhóm xin xác nhận.
3. Chủ trì gõ "chốt"/"duyệt"/"confirm" → Harry lưu biên bản vào brain (tri
   thức chung, tra lại được sau này) + tạo task cho từng việc cần làm.
4. Trả lời luôn qua `/v1/self/jobs/{id}/reply` — platform tự gửi đúng kênh.

## Ngoài phạm vi (không làm)
- Không tự gửi tin cho người ngoài nhóm đang trao đổi.
- Không tự tạo/sửa dữ liệu hệ thống khác (CRM, kho, đơn hàng...) — chỉ đề xuất.
- Không lưu nội dung nhạy cảm vào brain khi chưa được chủ trì chốt/duyệt.
- Không thay thế quyết định của người phụ trách — chỉ ghi lại & nhắc việc.

## Dữ liệu cần truy cập
- **Lark**: tin nhắn nhóm được add vào ("Magic LSR"), file recording (qua
  connector `lark` dùng chung của platform).
- **Brain riêng của agent** (`/v1/self/brain/items`, `/v1/self/brain/search`)
  — domain `finance-accounting`. Nội dung nạp từ tài liệu FA thật (Lark
  Wiki/Docs) qua `knowledge/*.md` + `scripts/seed_brain.py` (xem
  `knowledge/README.md`) — KHÔNG bịa quy trình/số liệu tài chính.
- Không cần quyền BigQuery ở bản đầu.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** — đổi `DRY_RUN=false`
  khi chạy thật.
- Transcript phụ thuộc dịch vụ ngoài; lỗi → job vào DLQ, replay được từ console.
- Nội dung họp có thể chứa thông tin nhạy cảm → chỉ lưu brain sau khi được chốt.
