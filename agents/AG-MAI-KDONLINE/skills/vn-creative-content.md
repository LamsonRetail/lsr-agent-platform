# Skill · Creative & nội dung

**Owner:** TN Content Performance — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_brand_voice`
**Tool:** `vn_creative_brief` · `vn_edit_variants` · `vn_idea_scan`
**Phase:** 1 (idea) → 2 (brief, hậu kỳ).
**Nghiệm thu:** dán 1 copy thô → MAI trả bản đúng giọng brand + ≥3 angle.

## Khi nào dùng

Sinh **angle / copy / hook / brief**, chuẩn hoá giọng brand, rà chính sách quảng cáo.
Dùng chung với B4 (duyệt concept) và B5 (hậu kỳ) của quy trình 10 bước.

## Trình tự

1. `vn_config_get("vn_brand_voice")` → lấy tone của đúng brand (**HAPAS** hoặc **MATE MADE**).
   Hai brand có giọng khác nhau — hỏi rõ brand nào trước khi viết.
2. Xác định JTBD + tệp khách đang nhắm (lấy từ `vn_jtbd_bank` hoặc người hỏi cung cấp).
3. Sinh **≥3 angle** khác nhau, mỗi angle kèm: hook 3s · thông điệp chính · lý do tin ·
   CTA · format đề xuất (9:16 / 1:1 / 4:5).
4. Rà checklist chính sách quảng cáo trước khi trả bản cuối.

## Luật bắt buộc

- **Không sao chép lố** idea của đối thủ — bản địa hoá và sáng tạo lại.
- Copy phải đúng giọng brand trong config; giọng trong đầu không thắng config.
- Concept cuối luôn do người chốt (**cổng WHY B4**) — MAI đề xuất, không tự duyệt.
- Ảnh sản phẩm thật là bắt buộc cho deck/báo cáo — MAI dựng khung, người chèn ảnh.
- Không hứa hẹn công dụng vượt mô tả sản phẩm thật (rủi ro chính sách + rủi ro CSKH).

## TODO cho owner

- [ ] Điền `configs/vn_brand_voice.json`:
      - HAPAS: tone, từ nên dùng / tránh, ví dụ câu đạt & không đạt.
      - MATE MADE: tương tự, nêu rõ khác HAPAS ở đâu.
      - Checklist chính sách quảng cáo (FB/TikTok) hay bị vi phạm.
- [ ] Bổ sung thư viện hook đã thắng (nếu có) vào `kb/` để MAI học từ dữ liệu thật.
