# Test cases — Legal Agent (AG-LEGAL)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động khai thêm ở tests.jsonl (bash scripts/agent-test.sh AG-LEGAL).
> Unit test offline (không cần secrets): `python3 -m pytest agents/AG-LEGAL/tests/`.

## S1 — Hỏi đáp pháp chế (Phase 2)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Happy path — chính sách nội bộ | "Quy định về chức năng nhiệm vụ của bộ phận pháp chế?" | Trả lời đúng nội dung tài liệu, có mục 📎 Nguồn với ≥1 link Lark hợp lệ |
| 2 | Câu hỏi có yếu tố rủi ro | "Công ty ký hợp đồng với NCC chưa có giấy phép kinh doanh ngành hàng được không?" | Có mục ⚠️ Rủi ro pháp lý + ✅ Đề xuất hành động cụ thể |
| 3 | KB không có căn cứ | "Chính sách của công ty về đầu tư crypto?" | Nói rõ tài liệu hiện chưa quy định, KHÔNG bịa, đề xuất hỏi legal team |
| 4 | Ngoài phạm vi | "Tư vấn giúp vụ kiện cá nhân của tôi với hàng xóm" | Từ chối lịch sự, chỉ đúng kênh (legal team / luật sư ngoài) |
| 5 | Engine lỗi | NotebookLM không truy cập được | Báo "không truy cập được kho tài liệu", không trả lời bừa; admin được cảnh báo |
| 6 | Trích dẫn phải thật | Bất kỳ câu trả lời nào | Mọi nguồn trong 📎 tồn tại trong bảng legal_sources (regression: golden case) |
| 7 | Memory | Hỏi tiếp "vậy còn với khách lẻ thì sao?" sau case 1 | Hiểu ngữ cảnh câu trước, không hỏi lại từ đầu |

## Chuẩn platform (Phase 2A) — regression guard, chạy offline

| # | Kịch bản | Kỳ vọng |
|---|----------|---------|
| P1 | Bộ nhớ ở platform | Ngữ cảnh (`rolling_summary`, `recent_turns`, `user_facts`) từ `/v1/self/context` đi vào câu hỏi gửi engine; **restart container vẫn hiểu câu hỏi tiếp nối** |
| P2 | Ghi lượt về platform | Mỗi lượt ghi đủ `user` + `assistant` qua `/v1/self/session/turn`; `needs_summary` → nén bằng model rồi POST summary |
| P3 | Không tự tích hợp Lark | Không file nào của agent gọi `open-apis/im/...`; `lark_kb.py` không có hàm gửi tin/thu hồi |
| P4 | Hành vi không hard-code | `consumer.py` không chứa hằng persona; có `INSTRUCTION.md`; không còn `system_prompt.md` |
| P5 | Telegram ngoài scope | Không còn nhánh code nào nhắc telegram |
| P6 | Việc chưa mở nói thật | Intent S2–S5 → trả lời "đang được xây", **không gọi KB**, có báo Pháp chế |

## Pháp chế in the loop (Phase 2B)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| G1 | Thông báo mọi câu trả lời | 1 câu hỏi S1 | Group `oc_2c44…4efb` nhận card; gate `s1_answer` mức `observe` được mở |
| G2 | Gom theo hội thoại | 3 lượt cùng session | Chỉ **1** gate observe, không 3 card |
| G3 | Trả lời không có trích dẫn | KB không có căn cứ | Gate được đánh `risk=high` |
| G4 | Người ngoài gõ lệnh | `#12 duyệt` từ open_id lạ | Từ chối, trạng thái gate **không đổi**, có log |
| G5 | Người duyệt duyệt | `#12 duyệt` từ Thi/Anh | `approved` + ghi `reviewer`, phản hồi xác nhận trong group |
| G6 | Yêu cầu sửa thiếu lý do | `#12 sửa` | Nhắc cú pháp, **không** đổi trạng thái |
| G7 | Duyệt 2 lần | `#12 duyệt` ×2 | Lần 2 báo "đã ở trạng thái approved" |
| G8 | Duyệt card theo dõi | `#12 duyệt` với gate observe | Báo "không cần duyệt", gợi ý `tham gia` |
| G9 | Tham gia hội thoại | `#12 tham gia` | `session_modes=joined`; **người hỏi được thông báo**; agent im ở lượt sau nhưng vẫn ghi lượt |
| G10 | Chuyển lời | `#12 nhắn: …` | Người hỏi nhận tin có prefix `👤 Pháp chế (Tên)` |
| G11 | Trả lại Agent | `#12 trả lại` | `mode=auto`, agent trả lời tiếp bình thường |
| G12 | Tin nhắn thường trong group | "trưa nay ăn gì" | Agent **không trả lời** |
| G13 | Gate quá hạn | SLA hết | **Nhắc một lần**, tuyệt đối **không tự động thông qua** |
| G14 | Observe quá hạn | SLA hết | `auto_passed` — không bao giờ chặn người dùng |
| G15 | Danh sách | `#ds` | Liệt kê việc đang chờ kèm nhãn tiếng Việt |

## Sync KB (Phase 1)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 8 | Sync lần đầu | Wiki space + Drive folder có N tài liệu | legal_sources có N dòng, notebook có N sources, trạng thái synced |
| 9 | Tài liệu sửa | Sửa 1 doc trên Wiki (obj_edit_time đổi) | Chu kỳ sau: source được thay bản mới, hash cập nhật |
| 10 | Tài liệu xoá | Xoá 1 file khỏi Drive folder | Chu kỳ sau: source bị gỡ khỏi notebook, dòng đánh dấu removed |
| 11 | Lỗi 1 tài liệu | 1 file download lỗi | Các tài liệu khác vẫn sync; lỗi được ghi log + báo cáo, không chết cả worker |
| 12 | Không có quyền wiki | Bot chưa được thêm vào space | Worker báo lỗi permission rõ ràng kèm hướng dẫn, không loop vô hạn |

## S2 — Tạo hợp đồng (Phase 3)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 13 | Happy path | "Tạo hợp đồng dịch vụ với công ty ABC" + trả lời đủ field | File docx đủ thông tin, có dấu DRAFT, link Drive |
| 14 | Thiếu field | User bỏ dở giữa chừng, quay lại hôm sau | Agent nhớ state, hỏi tiếp field còn thiếu |
| 15 | Template không có | "Tạo hợp đồng thuê máy bay" | Liệt kê template hiện có, không bịa template |

## S3 — Review hợp đồng (Phase 4)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 16 | HĐ nhiều rủi ro | File hợp đồng thiếu điều khoản phạt, bồi thường | Báo cáo rủi ro theo checklist, mức độ + đề xuất sửa, gửi lại người nộp |
| 17 | HĐ sạch sau 2 vòng | Nộp lại bản đã sửa hết | Chuyển người có thẩm quyền (đúng người theo loại HĐ) kèm tóm tắt; người nộp được báo |
| 18 | Người duyệt từ chối | Approver bấm ❌ kèm lý do | Người nộp nhận lý do; trạng thái rejected trong console |

## S4 — Tổng hợp văn bản luật (Phase 5)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 19 | Văn bản mới | Nguồn có nghị định mới | File lưu về Drive folder văn bản luật, digest gửi Lark group, xuất hiện trong KB sau sync |
| 20 | Nguồn lỗi | 1 nguồn đổi layout/chặn bot | Nguồn đó báo lỗi trong console, các nguồn khác vẫn chạy |
| 21 | Trùng lặp | Crawl lại văn bản đã có (cùng số hiệu) | Không tạo bản ghi/file trùng |
