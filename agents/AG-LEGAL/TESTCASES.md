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
| P6 | Thiếu cấu hình thì nói thật | Chưa có kho mẫu → S2 báo rõ chưa cấu hình, **không gọi KB**, không giả vờ soạn được |

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

## S4 — Tổng hợp văn bản luật (Phase 5) — **hằng tuần, thứ 2 07:00**

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 19 | Văn bản mới | Nguồn có nghị định mới | Bản gốc lưu vào Drive **folder con theo nước** (VN/, TH/), **index vào bộ nhớ ngay** (nước + số hiệu + link gốc + link Drive), digest chờ Pháp chế duyệt mới gửi |
| 19a | Nguồn theo nước | Seed | Có cả VN và TH; nguồn **chưa kiểm được để tắt kèm `note`** nói cần gì để bật |
| 19b | Nguồn HTML thiếu `link_pattern` | kind=html, không pattern | Báo lỗi nguồn đó, **không** im lặng trả 0 văn bản |
| 19c | Nguồn HTML có `link_pattern` | trang có link khớp/không khớp | Chỉ lấy link khớp, url tuyệt đối, gán đúng `country` |
| 19d | Lưu Drive chạy lại | Chạy archive 2 lần | Lần 2 không tải/upload lại (đã có `drive_url`) |
| 19e | 1 văn bản tải lỗi | 404 giữa lô | Các văn bản khác vẫn lưu được |
| 19f | Chưa cấu hình folder | thiếu `LEGAL_DRIVE_FOLDER` | Bỏ qua bước lưu, **không** crash |
| 19g | Index chỉ chỗ truy xuất | 1 văn bản đã lưu | Mục index có nước, số hiệu, link gốc **và** link bản lưu nội bộ |
| 19h | Seed không bật lại nguồn admin đã tắt | tắt tay rồi seed lại | Vẫn tắt |
| 19i | Thứ tự | 1 chu kỳ tuần | Lưu bản gốc + index xảy ra **trước** khi mở gate digest |
| 20 | Nguồn lỗi | 1 nguồn đổi layout/chặn bot | Nguồn đó báo lỗi trong console, các nguồn khác vẫn chạy |
| 21 | Trùng lặp | Crawl lại văn bản đã có (cùng số hiệu) | Không tạo bản ghi/file trùng |
| 21a | Số hiệu do nguồn cấp | chinhphu.vn, trích yếu không chứa chữ số | Lấy số hiệu từ **cột dữ liệu**, không phải regex tiêu đề |
| 21b | Trùng liên nguồn | Cùng nghị định từ RSS và chinhphu.vn | Một bản ghi duy nhất |
| 21c | Số hiệu hậu tố lạ | `55/CĐ-TTg`, `45/2019/QH14` | Lấy **đủ** hậu tố (chữ thường/số), không cắt còn `55/CĐ` |
| 21d | Bản gốc tốt hơn tới sau | RSS thấy trước, chinhphu.vn có PDF ký số | Đổi sang PDF ký số (khi **chưa** lưu Drive) |
| 21e | Host chưa có bộ trích | link ở nguồn lạ, không phải file | **Báo lỗi**, không lưu HTML cả trang làm "bản gốc" |
| 21f | File gốc không phải PDF | nguồn trả trang lỗi | Báo lỗi, không upload |

### Tra cứu theo tên (khi có người hỏi — không cần duyệt)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 22a | Hỏi tên văn bản | "Bộ luật Lao động quy định gì về thử việc" | Tra luatvietnam, lưu bản gốc + index, trả link nguồn **và** link bản lưu |
| 22b | Hỏi bằng số hiệu | "Nghị định 98/2020/NĐ-CP…" | Dùng luôn số hiệu, **không** gọi model |
| 22c | Kết quả không khớp tên | nguồn trả văn bản khác | Coi như **không thấy**, không lưu, không trích dẫn |
| 22d | Model trả rác | model trả JSON/chuỗi dài | **Không** tra cứu bằng rác đó |
| 22e | Dự thảo | luatvietnam trả `-d10.html` | Loại khỏi kết quả; nếu hiển thị thì ghi rõ **DỰ THẢO — chưa ban hành** |
| 22f | Nguồn chết | luatvietnam timeout | Trả rỗng, **không** làm vỡ lượt trả lời |
| 22g | Không tìm được | tên không tồn tại | Nói thẳng không thấy, **không đoán** nội dung |

## S5 — Hỗ trợ trình ký (Phase 6) — **hồ sơ đến từ Lark Approval thật** từ 20/08

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 22 | Bước 3 thiếu đầu mục | Hồ sơ thiếu "Báo giá" | Báo cáo chỉ rõ mục thiếu, DM người khởi tạo, **không chặn hồ sơ** |
| 23 | Bước 3 đủ hồ sơ | Hồ sơ đủ danh mục | Báo "đầu mục ✅ đủ" + điểm lưu ý nội dung |
| 24 | Chưa cấu hình checklist | Loại HĐ chưa khai | Báo cáo ghi rõ phần kiểm hồ sơ chỉ là tham khảo |
| 25 | Bước 5 phát hiện mức chặn | Sai pháp nhân bên B | `blocking=true` → đề nghị **quay lại Bước 4**, báo Admin tạm dừng |
| 26 | Bước 5 mức thấp | Góp ý câu chữ | **Cảnh báo tham khảo**, không chặn, Admin vẫn trình ký |
| 27 | Vòng lặp | Đã quay lại Bước 4 2 lần | Lần 3 **escalate trưởng Pháp chế**, Agent chỉ ghi nhận |
| 28 | Agent lỗi/timeout | Model không trả kết quả | Báo "chưa rà soát kịp", hồ sơ **vẫn đi tiếp**; gate observe quá SLA → `auto_passed` |

### Đường vào từ Lark Approval (broker C8 — platform giữ user token)

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 28a | Chưa cấu hình danh tính | thiếu `AGENT_LARK_SUBJECT` | Nói rõ thiếu cấu hình, **không** ném lỗi giữa việc |
| 28b | Đọc việc đang chờ | poll | Gọi `tasks?topic=1&user_id_type=open_id` — `topic` là tham số **bắt buộc** |
| 28c | Đọc instance bị chặn | Lark trả `99991668` | Nói rõ "cần TENANT token (C5)", **không** trả rỗng như thể hồ sơ không có gì |
| 28d | Báo trùng | cùng `task_id` ở 3 lần poll | Báo group **đúng một lần** |
| 28e | Chưa đọc được nội dung | instance không đọc được | **Vẫn báo** hồ sơ đã tới + nhờ Pháp chế mở trực tiếp |
| 28f | Task không có id | payload lạ | Bỏ qua, không báo |
| 28g | Hồ sơ đọc được | form có tên + mô tả | Rà soát bằng **`step3` cũ**, lưu `signing_dossiers`, mở gate observe |
| 28h | Có file đính kèm chưa đọc được | form có `attachments` | Báo cáo ghi rõ "rà soát dựa trên mô tả trong form" |
| 28i | Form rỗng | `form=[]` | **Không gọi model**, không sinh báo cáo từ không có gì |
| 28j | Danh tính sắp hết hạn | `refresh_days_left ≤ 2` | Nhắc vào group **một lần cho mỗi mốc ngày** |

## Phase 7 — Golive & chống bịa nguồn

| # | Kịch bản | Kỳ vọng |
|---|----------|---------|
| 29 | Bịa nguồn | Link trong 📎 không có trong `legal_sources` → golden run **FAIL** với lỗi "BỊA NGUỒN" |
| 30 | Trích dẫn thật | Link tồn tại trong `legal_sources` → pass |
| 31 | Câu từ chối | Case `must_cite=false` không cần trích dẫn, nhưng **không được** viện dẫn điều khoản |
| 32 | KB chưa sync | `legal_sources` trống → bỏ qua phép kiểm, **không** báo sai là bịa |
| 33 | Thiếu CLI `claude` | Consumer **cảnh báo rõ lúc khởi động** (router + S2–S5 sẽ degrade) |
| 34 | Golive checklist | `golive.json` đủ 28 mục; nộp bằng `scripts/submit-golive.sh AG-LEGAL` |

> **Độ phủ tự động**: `python3 -m pytest tests/ -q` → **88 case offline**, không cần secret.
> Ánh xạ: `test_consumer.py` (chuẩn platform + S1 + observe) · `test_gates.py` (lệnh duyệt,
> quyền, SLA) · `test_flows.py` (S2–S5 + hệ quả sau khi duyệt) · `test_golden.py` (chống
> bịa nguồn + trích text) · `test_sync.py` (đồng bộ KB) · `test_approval.py` (S5 qua broker C8).
