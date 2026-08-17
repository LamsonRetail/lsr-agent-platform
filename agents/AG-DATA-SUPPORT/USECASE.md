# Use case — Data Support (AG-DATA-SUPPORT)

> Copy cấu trúc thư mục từ agent mẫu `agents/AG-MINH-ANH` (khuyến nghị của platform),
> không sửa/không import trực tiếp code của agent mẫu.

## Bài toán
Team Data đang có 2 việc tốn thời gian, lặp lại mỗi ngày:
1. **Dữ liệu nằm rải rác** — số liệu BigQuery, bảng Lark Base, tài liệu quy trình —
   mỗi người phải tự nhớ nguồn nào ở đâu, hỏi lại người cũ khi cần. Không có "một nơi"
   để hỏi và luôn ra câu trả lời có trích dẫn nguồn.
2. **Biên bản họp viết tay chậm, hay sót** — họp xong không ai rảnh tổng hợp lại thành
   quyết định + action item + người phụ trách, dẫn tới việc bị quên.

Data Support giải quyết cả hai bằng cách: (a) làm "cửa vào" chung để hỏi dữ liệu đã
được tổng hợp sẵn, và (b) tự dựng biên bản họp từ recording/nội dung trao đổi trong
nhóm Lark của team, rồi lưu lại chính vào (a) để tra cứu về sau.

## Người dùng
- **Mọi thành viên Data squad** — hỏi số liệu/tài liệu qua: nhóm Lark của squad, hoặc
  Chat thử trong Console platform (`/agent/AG-DATA-SUPPORT`) — không cần cài gì thêm.
- **Chủ trì họp / thư ký** của team Data — họp qua Lark Meeting, nhóm có Data Support,
  xác nhận biên bản nháp bằng một câu trả lời trong nhóm.
- **Data lead** — chỉ định nguồn BigQuery/Lark Base nào được đồng bộ vào kho tri thức chung.

## Luồng chính (happy path)

### A. Hỏi dữ liệu chung
1. Người dùng hỏi trong nhóm Lark (hoặc web chat) — mọi kênh vào cùng một hàng đợi.
2. Data Support gọi `/v1/self/context` (đã tự kèm tri thức đã duyệt + nguồn trích dẫn)
   để dựng câu trả lời; nếu không có trong tri thức đã đồng bộ → nói rõ "chưa có dữ liệu
   này", không bịa.
3. Trả lời kèm nguồn (bảng BigQuery/Lark Base nào, cập nhật lúc nào).

### B. Đồng bộ dữ liệu vào kho tri thức chung (nền, không cần người dùng gọi)
1. Job định kỳ (`ingest/bigquery_sync.py`, `ingest/lark_base_sync.py`) đọc danh sách
   nguồn được Data lead khai báo (bảng BigQuery + bảng Lark Base cụ thể).
2. Tóm tắt/chuẩn hoá thành các "tri thức" ngắn có nguồn (`source_url`/tên bảng + thời điểm).
3. Ghi vào Brain **phạm vi riêng của agent này** (không đụng shared brain của agent khác).

### C. Biên bản họp
1. Bot Data Support được add vào nhóm họp Lark của team Data.
2. Nhận recording/nội dung trao đổi → dựng **biên bản nháp**: người tham dự, agenda,
   quyết định, action item (kèm người phụ trách nếu nhắc tên).
3. Gửi biên bản nháp vào nhóm, xin xác nhận.
4. Khi chủ trì gõ "chốt"/"duyệt"/"confirm" → tạo task Lark cho từng action item +
   lưu biên bản đã chốt vào kho tri thức chung (mục A/B) để tra lại bằng chat sau này.
5. Trả lời qua `/v1/self/jobs/{id}/reply` — platform tự gửi đúng nhóm.

## Ngoài phạm vi (không làm ở v1)
- Không tự động tham gia Zoom/Google Meet (cần bot bên thứ ba như Recall.ai — để
  backlog Phase 2 nếu team thực sự cần, hiện công ty họp chủ yếu qua Lark).
- Không tự gửi tin cho người ngoài nhóm đang trao đổi.
- Không tự sửa/xoá dữ liệu gốc ở BigQuery/Lark Base — chỉ đọc, tóm tắt, và ghi vào
  Brain (bản sao tri thức), không viết ngược lại nguồn.
- Không tự đẩy tri thức riêng của agent lên **shared brain** — việc đó do reviewer/
  admin duyệt qua UI có sẵn của platform (đúng chuẩn PII/nhạy cảm).

## Dữ liệu cần truy cập
- **Lark**: tin nhắn/recording trong (các) nhóm Data squad được add bot vào (connector
  `lark` dùng chung của platform).
- **BigQuery**: các bảng cụ thể do Data lead chỉ định (đọc-chỉ; access cấp qua service
  account nội bộ, không đưa key vào repo).
- **Lark Base**: các bảng cụ thể của team Data (đọc-chỉ qua connector Lark có sẵn).
- **Brain** (`/v1/self/brain/*`): đọc để trả lời, ghi ở phạm vi riêng của agent này.

## Rủi ro & giới hạn
- `DRY_RUN=true` mặc định: chỉ log, không gửi tin thật cho tới khi golive.
- Transcript phụ thuộc dịch vụ ngoài (Whisper) — lỗi thì job vào DLQ, replay được từ
  Console (đã có sẵn ở platform).
- Nội dung họp/dữ liệu có thể chứa thông tin nhạy cảm → dựa vào PII guard đã có ở
  collector; không tự ý đồng bộ bảng chứa dữ liệu cá nhân nhạy cảm chưa được duyệt.
- Cần Data lead xác nhận danh sách bảng BigQuery/Lark Base trước khi bật `ingest/` thật.
