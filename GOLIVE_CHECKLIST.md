# Checklist Golive — bắt buộc cho MỌI agent

Owner của agent phải hoàn tất checklist này **trước khi golive** và **cung cấp đủ
thông tin** để platform vận hành/đánh giá về sau. Platform lưu vào bảng chung
(`agent_golive_checklist`), thiếu mục bắt buộc → **không cho golive**.

Ký hiệu: **(B)** = bắt buộc · (K) = khuyến nghị

---

## A. Định danh & sở hữu
- [ ] **(B)** `agent_id`, tên hiển thị, phiên bản, mô tả mục đích (1–3 câu).
- [ ] **(B)** **Owner** (email) — người chịu trách nhiệm vận hành, nhận cảnh báo.
- [ ] **(B)** **Backup owner** (email) — người thay khi owner vắng.
- [ ] **(B)** Squad/Chapter/Team mà agent phục vụ; có phải **squad agent chính** không.
- [ ] (K) Nhóm Lark để nhận cảnh báo vận hành của agent.

## B. Con người & phối hợp (second brain của team)
- [ ] **(B)** **Danh sách thành viên team**: họ tên, `lark_user_id`, vai trò, chuyên môn.
- [ ] **(B)** Ai là **người ra quyết định** / phê duyệt (approver) cho các việc agent đề xuất.
- [ ] **(B)** **Cách phối hợp**: việc nào agent tự làm, việc nào phải hỏi người, hỏi ai.
- [ ] **(B)** Kênh làm việc chính (chat/nhóm Lark, tasklist, thư mục tài liệu).
- [ ] (K) Giờ làm việc / múi giờ, thời gian phản hồi mong đợi (SLA nội bộ).
- [ ] (K) Người thay thế khi thành viên chính vắng (backup theo vai trò).

## C. Mục tiêu & KPI
- [ ] **(B)** **KPI của team/squad**: tên chỉ số, **đơn vị**, **công thức tính**, **nguồn dữ liệu**
      (BigQuery table/query, Lark Task, nhập tay), **kỳ đo** (ngày/tuần/tháng/quý).
- [ ] **(B)** **Chỉ tiêu (target)** từng KPI cho kỳ hiện tại + trọng số.
- [ ] **(B)** **KPI của chính agent**: agent được coi là "có ích" khi nào (vd giảm thời
      gian xử lý, số việc tự động hoá, tỉ lệ trả lời đúng).
- [ ] **(B)** Ngưỡng cảnh báo (khi nào coi là bất thường: usage tụt, lỗi tăng, chi phí vọt).
- [ ] (K) Baseline trước khi có agent (để đo tác động).

## D. Phạm vi & dữ liệu
- [ ] **(B)** **Nguồn dữ liệu** agent được phép truy cập (BigQuery dataset/table, Lark
      doc/chat/task nào) — nguyên tắc tối thiểu cần thiết.
- [ ] **(B)** **Dữ liệu KHÔNG được đụng** (PII, lương, hợp đồng, dữ liệu khách hàng nhạy cảm).
- [ ] **(B)** Danh sách **skill/MCP** agent dùng + lý do.
- [ ] **(B)** Agent có ghi/sửa dữ liệu ở đâu không (tạo task, gửi tin, ghi bảng nào).
- [ ] (K) Chính sách lưu trữ log/trace và ai được xem.

## E. Kết nối & xác thực
- [ ] **(B)** **Auth = subscription của owner** (`claude setup-token`) — không dùng khoá chung.
- [ ] **(B)** Kết nối Lark: **bot** hay **user account**; đã authorize; đã add vào nhóm cần thiết.
- [ ] **(B)** **Telemetry bật** và đã thấy trace về collector (ít nhất 1 lượt chạy thật).
- [ ] **(B)** Nơi agent chạy: platform-managed (VM/Vercel) hay **external** (dự án khác) —
      nếu external: URL/endpoint, người quản host, cách cập nhật.
- [ ] (K) Hạn mức token/chi phí tối đa mỗi ngày.

## F. Chất lượng & an toàn
- [ ] **(B)** **Bộ test** có nhãn (`needs_tool`, `expected_tool`) đã pass ngưỡng.
- [ ] **(B)** Các trường hợp agent **phải từ chối / chuyển người** (escalation).
- [ ] **(B)** Rủi ro đã lường trước + cách giảm thiểu (vd trả lời sai số liệu → luôn dẫn nguồn).
- [ ] **(B)** Có ai đó **review output** trong tuần đầu golive (tên người + tần suất).
- [ ] (K) Câu trả lời mẫu "đúng chuẩn" để đối chiếu về sau (golden examples).

## G. Vận hành sau golive
- [ ] **(B)** Lịch chạy định kỳ (nếu có): việc gì, cron, gửi kết quả cho ai.
- [ ] **(B)** Quy trình khi agent **fail test định kỳ** → ai training lại, trong bao lâu.
- [ ] **(B)** Cách người dùng **báo lỗi/góp ý** (reaction 👍👎, nhóm chat, form).
- [ ] **(B)** Nhịp review hiệu quả agent (hằng tuần/tháng) + ai tham gia.
- [ ] (K) Kế hoạch nâng cấp/mở rộng 30–90 ngày.

## H. Tuân thủ & minh bạch
- [ ] **(B)** Thành viên team **được thông báo** có agent theo dõi/ghi log công việc.
- [ ] **(B)** Xác nhận không dùng agent để đánh giá cá nhân ngoài phạm vi đã công bố.
- [ ] (K) Đã rà với HR/quản lý nếu agent chạm dữ liệu nhân sự.

---

## Cách nộp checklist
1. Qua **UI platform** (trang Golive của agent) — khuyến nghị.
2. Hoặc gọi API: `POST /v1/agents/{id}/golive-checklist` với JSON theo các mục trên.

Platform **chặn golive** nếu thiếu mục **(B)**; kết quả lưu vào bảng chung và hiển
thị trên Agent Detail để cả team cùng thấy.
