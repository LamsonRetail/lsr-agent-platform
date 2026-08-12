# Skill · Báo cáo tuần & báo cáo tháng (WBR)

**Owner:** PM / TP KD Online — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_report_sources` · `vn_base_targets`
**Tool:** `vn_numbers_read` · `vn_report_draft` · `vn_report_charts` · `vn_report_publish`
**Phase:** 1.
**Nghiệm thu:** MAI đọc đúng DT/LNĐG hôm qua và **nói rõ đang dùng base nào**.

## Trình tự

1. `vn_config_get("vn_report_sources")` → danh sách nguồn cố định: export Ads Manager 3 kênh
   (FB/TikTok/Google) + Shopee + TikTok Shop + Lark Base + chat group.
2. `vn_numbers_read` → DT / LNĐG / %MTD.
3. `vn_report_draft` → dựng `.md` theo template WBR.
4. `vn_report_charts` → chart chuẩn.
5. `vn_report_publish` → **chỉ chạy sau khi được người duyệt.**

## Cấu trúc bắt buộc

Khung **FACT → WHY → SO WHAT → ACTION**, ưu tiên theo **tác động kinh doanh**
(doanh thu → hiệu quả → rủi ro). Báo cáo cho lãnh đạo: **≤1 trang, 3–5 điểm quan trọng nhất**.

Chart chuẩn:
- Doanh thu luỹ kế vs target.
- So chỉ số MKT (CTR / CPA / ROAS / CIR) kỳ này vs kỳ trước.
- Phễu DT theo kênh / theo ngành.

## Hai cái bẫy — MAI phải tránh

1. **Nhiều base target chạy song song** → luôn **in rõ đang dùng base nào** (lấy từ
   `vn_base_targets`, kèm ngày rebase). Không im lặng chọn một base.
2. **% MTD** = actual ÷ target **lũy kế pro-rata theo ngày**, **KHÔNG** phải actual ÷ target
   cả tháng. Ghi rõ công thức đang dùng ngay dưới số.

## Luật bắt buộc

- Mọi số kèm **nguồn + thời điểm + base**. Ước tính ghi rõ *(ước tính)*.
- Toàn bộ số bằng **VND**.
- **Không gộp số 3 ngành.**
- Deck tháng theo format đã chốt của Khối; **ảnh sản phẩm thật bắt buộc** — MAI dựng khung,
  người chèn ảnh.
- **Không tự phát hành.** Draft luôn chờ duyệt.

## TODO cho owner

- [ ] Điền `configs/vn_report_sources.json` — từng nguồn: tên, đường dẫn/cách lấy, ai giữ,
      tần suất cập nhật.
- [ ] Điền `configs/vn_base_targets.json` — base target đang dùng, ngày rebase, base cũ (nếu còn
      ai đang dùng) để MAI in rõ.
- [ ] Dán template WBR đang dùng vào `kb/` để MAI dựng đúng khung.
