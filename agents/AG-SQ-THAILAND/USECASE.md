# Use case — Trợ lý Squad Thái Lan (AG-SQ-THAILAND)

> Squad agent chính của **SQ-THAILAND**. Theo chuẩn platform: squad phải có ≥1 agent
> mới đủ điều kiện đánh giá, và squad agent là **kênh dữ liệu** của squad đó.

## Bài toán

Squad Thái Lan làm việc rải rác: tài liệu nằm trong Lark Doc/Drive của từng người, số
liệu nằm trong file gửi qua chat, quyết định nằm trong cuộc họp mà không ai kịp ghi.
Hệ quả:

1. **Hỏi lại nhau những thứ đã có** — không biết dữ liệu nằm ở đâu, ai đang giữ.
2. **Người mới / người nghỉ phép mất mạch** — không có nơi tra "squad đã chốt gì".
3. **Họp xong không có biên bản** — đầu việc rơi, quyết định không ai nhớ chính xác.

## Người dùng

| Ai | Kênh | Việc chính |
|---|---|---|
| Thành viên squad Thái Lan | Nhóm Lark của squad | Hỏi dữ liệu chung, gửi tài liệu vào kho, đọc biên bản |
| Chủ trì cuộc họp | Nhóm Lark / Telegram | Gửi recording, duyệt biên bản nháp, chốt đầu việc |
| Quản lý squad / BOD | Web chat console `/agent/AG-SQ-THAILAND` | Tra quyết định cũ, xem squad đang vướng gì |
| Người thử / QA | Chat thử trong console | Chạy `tests.jsonl` trước golive |

Mọi kênh vào **cùng một hàng đợi** của platform — agent không cần biết tin đến từ đâu.

## Luồng chính (happy path)

### Luồng 1 — Kho dữ liệu chung ("tổng hợp ở một nơi")

1. Thành viên gửi tài liệu / link Lark / số liệu vào nhóm, kèm ý định (vd: "lưu cái này").
2. Agent **index ra resource index + đề xuất vào brain của squad** (`/v1/self/brain/items`),
   luôn kèm `source_url` (link Lark đối chứng) — **không nhồi nội dung vào memory**.
3. Tri thức ở trạng thái **chờ duyệt**; reviewer theo chuyên môn duyệt trên console.
4. Ai hỏi gì thì agent trả lời **dựa trên tri thức đã duyệt** (`/v1/self/context`,
   `/v1/self/brain/search`) và **luôn trích dẫn nguồn**. Không có nguồn → nói không biết.

### Luồng 2 — Ai cũng tương tác được

1. Hỏi trong nhóm Lark / Telegram / web chat → cùng một hàng đợi.
2. Agent lấy ngữ cảnh từ platform: instruction đang publish + tóm tắt hội thoại +
   N lượt gần nhất + fact người dùng + tri thức liên quan.
3. Trả lời bằng `POST /v1/self/jobs/{id}/reply` — platform tự gửi đúng kênh người hỏi.
4. Ghi lượt hội thoại lại để lượt sau còn mạch (`/v1/self/session/turn`).

### Luồng 3 — Tham gia họp & tự làm biên bản

```
1. Bot được add vào nhóm/cuộc họp của squad         → nhận event
2. Nhận recording (audio/video/file) hoặc nội dung trao đổi
3. Transcript                                        (Whisper server: POST /transcribe → poll /result)
4. Dựng BIÊN BẢN NHÁP: bối cảnh · key points · quyết định · đầu việc (ai/làm gì/hạn)
5. Gửi lại nhóm XIN XÁC NHẬN chủ trì                 ── status: awaiting_confirm
       │ chủ trì trả lời "chốt" / "duyệt" / "confirm"
       ▼
6. Lưu biên bản vào kho tri thức squad + đề xuất tạo task  ── status: confirmed
```

**Bắt buộc:** không tạo task, không lưu biên bản chính thức khi **chưa** có confirm của
chủ trì. Biên bản nháp chỉ tồn tại trong session cho tới khi được chốt.

### Luồng 5 — Bối cảnh thị trường Thái từ config (mở rộng Ploy, 12/08)

Trả lời trực tiếp từ `configs/*.json` qua `thailand_tools.py` (không cần model, không
cần mạng): lịch mùa vụ kèm kết luận làm/không làm · đếm ngược mốc BST theo ngày tuyệt
đối · ⭐ cảnh báo 1 mốc có nhiều phiên bản ngày giữa các nguồn · 2 base target song song
· mục lục kho tri thức. Sửa config là đổi câu trả lời — không deploy. Toàn bộ kế hoạch
6 tính năng Ploy và mapping vào platform: [PLOY.md](PLOY.md).

## Ngoài phạm vi (không làm)

- Không tự gửi tin cho người **ngoài** nhóm đang trao đổi.
- Không tự tạo/sửa dữ liệu hệ thống khác — chỉ **đề xuất** qua `/v1/self/actions/propose`.
- Không lưu nội dung nhạy cảm (giá vốn, lương, thông tin cá nhân khách) vào brain khi
  chưa duyệt.
- Không trả lời câu hỏi ngoài phạm vi squad Thái Lan → chỉ đúng kênh/agent phụ trách.
- Không đụng dữ liệu/cấu hình của agent khác hay của platform core.

## Dữ liệu cần truy cập

| Nguồn | Quyền | Trạng thái |
|---|---|---|
| Nhóm Lark của squad Thái Lan (tin nhắn, file recording) | qua app riêng **Sawadee HAPAS** (`cli_aaf6d2b3a5b8ded3`) nối vào event gateway | ⬜ cần admin chạy long-connection + gán ingress (PLOY.md §6) |
| Brain của agent (`/v1/self/brain/*`) | đọc + đề xuất | ✅ có sẵn khi register |
| Resource index `meeting-notes` (Minh Anh tự share khi register) | đọc/ghi | ✅ tự động |
| Whisper transcript server (`LSR_TRANSCRIBE_URL`) | POST /transcribe | ✅ server sống (large-v3/CUDA) |
| BigQuery `AI_DB` | **chưa cần** ở Phase 1 | ⬜ |

Agent **không cầm secret** của Lark/Telegram — mọi thứ đi qua connector của platform.

## Rủi ro & giới hạn

- `DRY_RUN=true` mặc định: chỉ log, **không gửi tin thật** ra Lark/Telegram. Đổi
  `DRY_RUN=false` khi đã duyệt chạy thật.
- Transcript phụ thuộc dịch vụ ngoài (Whisper server ngrok) → lỗi thì job vào DLQ,
  replay được từ console. Nội dung tiếng Thái/tiếng Anh có thể sai nhiều hơn tiếng Việt.
- Nội dung họp có thể chứa thông tin nhạy cảm → PII được redact ở collector trước khi lưu.
- Biên bản do model dựng **có thể sai** → bắt buộc gate confirm của chủ trì trước khi
  thành biên bản chính thức.
- Việc bot tham gia nhóm chat và thu thập dữ liệu phải được **thông báo minh bạch** tới
  thành viên squad, theo chính sách nội bộ.
