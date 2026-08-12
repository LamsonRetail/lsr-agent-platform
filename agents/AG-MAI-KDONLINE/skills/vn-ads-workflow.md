# Skill · Ads-ops — Quy trình 10 bước quảng cáo ⭐

**Owner:** TN Facebook Ads — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_ads_rules` · `vn_naming_convention`
**Tool:** `vn_jtbd_bank` · `vn_product_match` · `vn_idea_scan` · `vn_creative_brief` ·
`vn_edit_variants` · `vn_camp_build` · `vn_camp_ops` · `vn_ads_report` · `vn_ads_review` ·
`vn_scale_kill_reco`
**Phase:** 1 → 3 (trục chính của MAI).
**Nghiệm thu:** đưa 1 creative đã duyệt → MAI dựng khung camp test đúng naming + KPI.

## Nguyên tắc chia việc

MAI gánh phần **THỰC THI** của cả 10 bước. Con người giữ **5 cổng WHY** — không bao giờ
được MAI quyết thay:

| Cổng | Con người quyết |
|---|---|
| **B1** | Chọn JTBD — đánh vào nhu cầu nào |
| **B2** | Chọn sản phẩm — đẩy SP nào theo mục tiêu KD (xả hàng / chủ lực / biên LN) |
| **B4** | Duyệt concept — nội dung nào xứng brand |
| **B7** | Phê duyệt ngân sách lớn — scale tới đâu, rủi ro bao nhiêu |
| **B10** | Quyết nhân bản/bỏ — chịu trách nhiệm P&L |

## 10 bước

| Bước | MAI thực thi | Người giữ | Tool |
|---|---|---|---|
| 1. Tìm JTBD | Quét review/comment/tin nhắn/khảo sát + xu hướng search & social → gom cụm, xuất ≥5 JTBD chuẩn "Khi… tôi muốn… để…" kèm quy mô cầu ước tính | Chọn JTBD hợp chiến lược; giữ tối đa ~5 cụm trọng tâm | `vn_jtbd_bank` |
| 2. Chọn SP | Đọc catalog → match & xếp hạng SP theo từng JTBD; cảnh báo hết hàng / biên thấp | Quyết SP nào đẩy | `vn_product_match` |
| 3. Idea content | Quét Ad Library / TikTok / nguồn TQ → phân loại angle/hook/format, tóm tắt vì sao hiệu quả, đề xuất bản địa hoá | Chọn idea hợp brand; sáng tạo lại, không sao chép lố | `vn_idea_scan` |
| 4. Sản xuất | Sinh script + storyboard; tạo ảnh/video AI hoặc xuất brief cho ekip quay | Chốt concept cuối | `vn_creative_brief` |
| 5. Hậu kỳ | Auto-cut, phụ đề, lồng nhạc, xuất 9:16/1:1/4:5, nhiều biến thể hook 3s | Duyệt bản đạt chuẩn brand | `vn_edit_variants` |
| 6. Lên camp test | Tạo camp/adset đúng naming + ngân sách test chuẩn; đề xuất targeting, nạp creative, gắn tracking, ghi giả thuyết + KPI | Duyệt giả thuyết, tệp, mức ngân sách | `vn_camp_build` |
| 7. Vận hành | Giám sát theo ngưỡng 24/7; đề xuất (hoặc tự chạy **trong hạn mức**) tắt/bật, tăng/giảm, nhân bản; cảnh báo bất thường | Đặt luật chơi; duyệt ngân sách lớn | `vn_camp_ops` |
| 8. Đo lường | Kéo dữ liệu → báo cáo (spend, CPM, CTR, CPC, CPA, ROAS, CIR); so target & kỳ trước | Xác định chỉ số nào quan trọng giai đoạn này | `vn_ads_report` |
| 9. Review | Đối chiếu creative × tệp × chỉ số → pattern thắng/thua theo FACT → WHY → SO WHAT → ACTION | Xác nhận nguyên nhân THẬT, đọc bối cảnh thị trường | `vn_ads_review` |
| 10. Nhân bản/bỏ | Chấm điểm + khuyến nghị + mức tự tin; mô phỏng tác động nếu scale | **RA QUYẾT ĐỊNH CUỐI** | `vn_scale_kill_reco` |

## Ba mức tự động hoá

- **AI chạy — người giám sát:** B3 · B5 · B8.
- **AI đề xuất — người duyệt:** B1 · B2 · B4 · B6 · B7 · B9.
- **Người quyết — AI hỗ trợ bằng chứng:** B10 và mọi cổng WHY.

> **Luật an toàn:** bắt đầu ở chế độ *"AI đề xuất — người duyệt"*. Chỉ chuyển sang
> *"AI tự chạy"* cho hành động **nhỏ, trong hạn mức**, sau khi đã tin cậy kết quả.
> Mọi ngưỡng & hạn mức nằm ở `vn_ads_rules` — đọc bằng `vn_config_get`, không nhớ trong đầu.
> **Camp ops sai = đốt tiền thật.**

## Luật bắt buộc

- Trước mọi hành động camp: `vn_config_get("vn_ads_rules")` → đối chiếu hạn mức.
  Vượt hạn mức → **dừng, xin duyệt (B7)**, không tự chạy.
- Đặt tên camp/adset/ad theo `vn_naming_convention` — sai naming thì không dựng.
- Mọi khuyến nghị scale/kill phải kèm **mức tự tin** + **bằng chứng số** + **nguồn/thời điểm**.
- Không gộp số 3 ngành khi phân tích.

## TODO cho owner

- [ ] Điền `configs/vn_ads_rules.json` — ngưỡng scale/kill, trần ngân sách, khẩu vị rủi ro,
      hành động nào MAI được tự chạy.
- [ ] Điền `configs/vn_naming_convention.json` — quy ước `[Angle]_[Tep]_[Format]_[v]`.
- [ ] Ghi rõ KPI test chuẩn cho từng ngành (Túi / TS / NH) — ngân sách test, thời gian test,
      ngưỡng dừng.
