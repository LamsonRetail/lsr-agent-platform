# Use case — HR Agent (AG-HR)

> Trạng thái: DRAFT — chờ owner confirm trước khi code (xem PLAN.md để biết lộ trình chi tiết).

## Bài toán

Team HR LamsonRetail đang tốn thời gian vào các việc lặp lại và phân tán trên nhiều nguồn:

1. **Hỏi đáp chính sách HR** — nhân viên hỏi đi hỏi lại về nội quy, phép, lương thưởng, bảo hiểm; HR trả lời thủ công.
2. **Onboarding nhân viên mới** — hướng dẫn thủ tục, checklist ngày đầu, giải đáp thắc mắc người mới.
3. **Báo cáo nhân sự** — headcount, nghỉ việc, chấm công phải tổng hợp tay từ Sheet/Base.
4. **Tính KPI & thu nhập** — truy vấn số liệu phải **chính xác tuyệt đối**, không chấp nhận model "đoán".
5. **Đánh giá xếp loại nhân sự** — chuẩn hoá theo framework, chuẩn bị calibration.
6. **Train & re-train nhân sự** — soạn nội dung đào tạo, quiz, theo dõi lộ trình học.
7. **Tổng hợp chính sách mới của nhà nước** (luật lao động, BHXH, thuế TNCN…) và **đề xuất điều chỉnh** chính sách nội bộ.
8. **Hỗ trợ tuyển dụng** — JD, câu hỏi phỏng vấn, screening.
9. **Đồng bộ với các agent khác trên platform** (A2A) — chia sẻ tri thức HR về shared brain định kỳ.

## Người dùng & kênh

| Nhóm | Kênh | Phạm vi |
|---|---|---|
| Team HR | Lark nhóm HR | Toàn bộ năng lực (kể cả số liệu nhạy cảm) |
| Toàn bộ nhân viên | Lark (DM bot) | Chỉ hỏi đáp chính sách, onboarding, **dữ liệu của chính mình** |
| Owner/HR admin | Web console (`/agent/AG-HR`) | Cập nhật, điều chỉnh nội dung; test |
| Agent khác | A2A | Đọc tri thức HR đã publish lên shared brain |

## Luồng chính (happy path)

1. Nhân viên gửi câu hỏi qua Lark (hoặc web chat) → platform tạo job.
2. Agent lấy ngữ cảnh (`/v1/self/context`) + tìm tri thức trong brain (`/v1/self/brain/search`).
3. Với câu hỏi **tài liệu/chính sách**: trả lời kèm **trích dẫn nguồn**; không có nguồn → nói rõ không biết, không bịa.
4. Với câu hỏi **số liệu** (KPI, thu nhập, chấm công): code truy vấn trực tiếp Lark Base/Sheet — model chỉ diễn giải kết quả, **không tự sinh số**.
5. Trả lời qua `/v1/self/jobs/{id}/reply` (platform tự chọn kênh) + gửi `usage` để dashboard đo chi phí.

## Kiến trúc tri thức (yêu cầu owner)

- Agent có **bộ nhớ riêng** (brain scope=agent) tách khỏi shared brain.
- Files/link được index và lưu ở **thư mục cố định** (Lark Wiki/Drive folder quy ước — xem PLAN.md §3).
- Thay đổi kiến thức/chính sách được **cập nhật định kỳ về shared brain** của platform để agent khác dùng.
- Console dùng để cập nhật, điều chỉnh nội dung instruction/tri thức.

## Ngoài phạm vi (không làm)

- Không tự quyết định nhân sự (tăng lương, kỷ luật, cho nghỉ việc) — chỉ chuẩn bị số liệu/đề xuất, người duyệt.
- Không trả lời lương/đánh giá của người khác cho nhân viên thường (privacy gate theo `user_ref`).
- Không tư vấn pháp lý sâu — chuyển AG-LEGAL qua A2A.
- Không thao tác ghi vào hệ thống lương/chấm công (chỉ đọc).

## Dữ liệu cần truy cập

| Nguồn | Dùng cho | Quyền |
|---|---|---|
| Lark Wiki/Docs HR (thư mục cố định) | Chính sách, quy trình, tài liệu đào tạo | Cần cấp quyền app Lark đọc folder |
| Lark Base/Sheet nhân sự | Headcount, chấm công, phép, KPI, thu nhập | Cần cấp quyền — dữ liệu nhạy cảm |
| Nguồn pháp luật công khai (VBPL, thuvienphapluat…) | Chính sách nhà nước mới | Public, crawl định kỳ |
| Shared brain platform | Tri thức chung + publish tri thức HR | Đã có qua token agent |

## Rủi ro & giới hạn

- **Sai số liệu lương/KPI** → mất niềm tin ngay: bắt buộc truy vấn bằng code (deterministic), có test case chặn.
- **Lộ dữ liệu nhạy cảm** khi mở cho toàn bộ nhân viên: phân quyền theo `user_ref` trước khi mở rộng kênh.
- **Chính sách nhà nước tổng hợp sai/thiếu**: mọi đề xuất điều chỉnh phải ghi rõ nguồn + con người duyệt.
- Kênh Lark thực chỉ chạy sau khi admin ACTIVATE.
