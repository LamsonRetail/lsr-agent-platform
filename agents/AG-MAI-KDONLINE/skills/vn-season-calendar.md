# Skill · Lịch mùa vụ VN

**Owner:** MKT / CĐS — chỉ owner sửa file này (cùng owner với `vn-bst-milestones.md`).
**Config phụ thuộc:** `vn_season_calendar`
**Tool:** `vn_season_calendar`
**Phase:** 1.
**Nghiệm thu:** hỏi "T10 làm gì" → MAI nhắc 10/10 · 20/10 kèm kết luận làm / không làm.

## Nguyên tắc

Lịch mùa vụ **không phải danh sách ngày suông**. Mỗi dịp phải kèm **KẾT LUẬN làm / không làm**
và lý do — nếu không, MAI chỉ đang đọc lịch.

## Khung dịp (chi tiết nằm ở config)

| Dịp | Loại | MAI nhắc gì |
|---|---|---|
| Tết Nguyên đán | Peak lớn nhất | Deadline sản xuất trước nghỉ Tết; vùng "chết" cận Tết; combo quà biếu |
| Back-to-school (T7–T9) | LÀM | Tệp **người thân tặng tân sinh viên** (balo/tote) — người mua là phụ huynh/anh chị, không phải sinh viên |
| Sàn double-day 9/9 · 10/10 · 11/11 · 12/12 | Peak sàn | Đăng ký flash deal/voucher; **ngày khoá đăng ký** campaign sàn |
| 20/10 · 8/3 · Valentine | Dịp quà nữ | Trục tặng quà — mạnh cho TS & NH |
| Black Friday · Noel / Năm mới | Peak cuối năm | Nhịp dồn cuối năm; xả tồn trước load hàng mới |

## Luật bắt buộc

- Nhắc dịp phải kèm **hành động cụ thể + hạn**, không chỉ nêu tên dịp.
- Dịp có **ngày khoá đăng ký** (sàn) thì đếm ngược theo ngày khoá, không theo ngày diễn ra.
- Dịp nào Khối đã quyết **KHÔNG làm** thì nói rõ "không làm" + lý do — để năm sau không hỏi lại.
- Không tự thêm dịp ngoài config.

## TODO cho owner — điền `configs/vn_season_calendar.json`

- [ ] Mỗi dịp: tên · ngày (hoặc khoảng) · loại (peak/làm/không làm) · **kết luận & lý do** ·
      hành động cần làm · hạn chuẩn bị (D-x) · ngành nào áp dụng (Túi/TS/NH).
- [ ] Ghi rõ ngày **khoá đăng ký** cho các campaign sàn.
- [ ] Đánh dấu dịp đã thử và **thất bại** — để MAI không đề xuất lại.
