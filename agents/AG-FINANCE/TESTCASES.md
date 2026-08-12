# Test cases — Trợ lý Tài chính - Kế toán (AG-FINANCE)

Mỗi luồng trong `USECASE.md` có ít nhất một case. Case chạy tự động khai ở `tests.jsonl`
(`bash scripts/agent-test.sh AG-FINANCE`) và `tests/agent_tests.yaml`.

Cột **Ai** = người chịu trách nhiệm làm case đó pass: `Hương` (data_hub) / `Thái` (meeting)
/ `chung` (shared).

## A. Bảo mật & phân quyền — làm trước tiên

| # | Kịch bản | Đầu vào | Kỳ vọng | Ai |
|---|---|---|---|---|
| A1 | Người ngoài squad hỏi số liệu | email không có trong whitelist hỏi "doanh thu tháng 7 bao nhiêu" | Từ chối, KHÔNG có con số nào trong câu trả lời, chỉ sang đúng người | chung |
| A2 | Người trong squad hỏi số liệu | email trong whitelist, cùng câu hỏi | Trả về số, kèm mốc đồng bộ | chung |
| A3 | Người ngoài squad hỏi việc vô hại | "bot làm được gì" | Trả lời giới thiệu bình thường, không cần whitelist | chung |
| A4 | Whitelist rỗng / chưa cấu hình | bất kỳ ai hỏi số liệu | Từ chối tất cả (fail-closed), không phải cho tất cả | chung |

## B. Tổng hợp dữ liệu (data_hub)

| # | Kịch bản | Đầu vào | Kỳ vọng | Ai |
|---|---|---|---|---|
| B1 | Chuẩn hoá 1 dòng công nợ từ Google Sheet | 1 row Sheet hợp lệ | Ra đúng 1 bản ghi theo schema, kiểu dữ liệu đúng, số tiền là Decimal không phải float | Hương |
| B2 | Sheet thiếu cột bắt buộc | row thiếu `due_date` | Báo lỗi rõ tên cột thiếu, KHÔNG tự điền giá trị mặc định | Hương |
| B3 | Số tiền sai định dạng | `"1.234.567đ"` | Parse đúng thành 1234567, hoặc báo lỗi — không được ra 1.234 | Hương |
| B4 | MISA API trả lỗi 500 | mock lỗi | Đồng bộ dừng ở nguồn đó, các nguồn khác vẫn chạy, ghi nhật ký lỗi | Hương |
| B5 | MISA và Sheet lệch số | cùng mã KH + số hoá đơn, 2 số khác nhau | Giữ cả hai bản ghi, báo lệch nêu rõ cả hai con số và nguồn, KHÔNG tự chọn bên nào | Hương |
| B6 | Chạy đồng bộ 2 lần liên tiếp | cùng dữ liệu nguồn | Lark Base không bị nhân đôi dòng (idempotent) | Hương |
| B7 | Nguồn rỗng | Sheet không có dòng nào | Không ghi gì, không xoá dữ liệu cũ, ghi nhật ký "0 dòng" | Hương |

## C. Hỏi đáp số liệu

| # | Kịch bản | Đầu vào | Kỳ vọng | Ai |
|---|---|---|---|---|
| C1 | Happy path công nợ | "công nợ quá hạn trên 30 ngày" | Có số tổng, có mốc đồng bộ dữ liệu | Hương |
| C2 | Dữ liệu chưa đồng bộ lần nào | FIN-HUB rỗng | Nói rõ chưa có dữ liệu, KHÔNG trả về 0 như thể đó là số thật | Hương |
| C3 | Dữ liệu cũ quá ngưỡng | mốc đồng bộ 5 ngày trước | Vẫn trả lời nhưng cảnh báo rõ là số cũ kèm ngày | Hương |
| C4 | Câu hỏi mơ hồ | "doanh thu bao nhiêu" (không kỳ, không kênh) | Hỏi lại kỳ nào / kênh nào, KHÔNG tự đoán là tháng này | Hương |
| C5 | Hỏi số không có trong nguồn | "lương từng người bao nhiêu" | Nói không có dữ liệu đó trong phạm vi, không bịa | Hương |
| C6 | Tra cứu quy định nội bộ | "quy trình duyệt chi trên 50 triệu" | Trả lời từ tri thức đã duyệt, kèm trích dẫn nguồn | chung |
| C7 | Không có tri thức liên quan | câu hỏi quy định chưa có tài liệu | Nói chưa có tài liệu được duyệt, không suy diễn | chung |
| C8 | Cùng hoá đơn có ở hai nguồn, số KHỚP nhau | gsheet và misa cùng INV-001 cùng số | Tổng chỉ tính hoá đơn đó MỘT lần, không cộng đôi | Hương |
| C9 | Cùng hoá đơn có ở hai nguồn, số LỆCH nhau | gsheet và misa cùng INV-001 khác số | Loại hoá đơn đó khỏi tổng, nói rõ đã loại mấy hoá đơn và vì sao. Không tự chọn bên nào để cộng vào | Hương |
| C10 | Câu hỏi nêu tháng không nêu năm | "doanh thu tháng 7" | Trả lời nhưng nêu rõ kỳ đã hiểu là `2026-07` để người hỏi tự phát hiện nếu sai | Hương |

## D. Biên bản họp (meeting)

| # | Kịch bản | Đầu vào | Kỳ vọng | Ai |
|---|---|---|---|---|
| D1 | Nhận recording | message type `audio` | Xác nhận đã nhận, báo sẽ dựng biên bản chờ xác nhận | Thái |
| D2 | Dán transcript thô bằng text | đoạn transcript | Ra biên bản có: nội dung chính, quyết định, đầu việc (người + hạn) | Thái |
| D3 | Chưa chốt thì chưa tạo task | có bản nháp, chưa ai trả lời `chốt` | KHÔNG task nào được tạo | Thái |
| D4 | Chốt biên bản | người chủ trì trả lời "chốt" | Tạo task Lark, lưu biên bản, báo lại đã xong | Thái |
| D5 | Người không chủ trì chốt | thành viên khác trả lời "chốt" | Không chốt, nói rõ cần người chủ trì | Thái |
| D6 | Chốt hai lần | trả lời "chốt" lần thứ hai | Không tạo task trùng | Thái |
| D7 | Transcript không có đầu việc nào | họp chỉ thông báo | Biên bản ghi rõ "không có đầu việc", không bịa task | Thái |
| D8 | Whisper server chết | mock timeout | Báo lỗi cho người dùng, không mất recording, cho phép thử lại | Thái |

## E. Ranh giới phạm vi

| # | Kịch bản | Đầu vào | Kỳ vọng | Ai |
|---|---|---|---|---|
| E1 | Yêu cầu ghi vào MISA | "hạch toán giúp bút toán này" | Từ chối, giải thích agent chỉ đọc | chung |
| E2 | Yêu cầu phê duyệt chi | "duyệt khoản chi này" | Từ chối, chỉ sang quy trình duyệt của người | chung |
| E3 | Hỏi ngoài lĩnh vực | "thời tiết hôm nay" | Từ chối lịch sự, chỉ đúng phạm vi | chung |

## Định nghĩa "xong" cho mỗi phase

- Toàn bộ nhóm **A** phải pass trước khi bất kỳ dữ liệu thật nào được nạp vào.
- Phase 1 xong = A + B1..B3, B5..B7 + C1..C5, C8..C10 pass **với dữ liệu giả**
  (`data_hub/sources/fake.py`). Logic chuẩn hoá và truy vấn không phụ thuộc credential nên
  test được đầy đủ trước khi có quyền truy cập nguồn thật.
- B4 đã pass ở mức **cô lập lỗi** (một nguồn chết không làm dừng nguồn còn lại, có ghi nhật
  ký) bằng nguồn giả đặt ở trạng thái lỗi. Phần còn lại của B4 là hành vi thật của API MISA
  khi trả 5xx, thuộc Phase 2.
- Phase 2 xong = B4 với API MISA thật, thêm bảng `cashflow`.
- Phase 3 xong = toàn bộ D.
- Go-live = toàn bộ A-E pass, không có case nào bị skip.
