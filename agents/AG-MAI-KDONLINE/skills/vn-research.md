# Skill · Nghiên cứu thị trường & đối thủ

**Owner:** (việc còn trống — ai nhận thì điền tên vào đây và `PHANCONG.md`)
**Config phụ thuộc:** `vn_research_sources`
**Tool:** `vn_research_index` · `vn_research_search` · `vn_research_sop` · `vn_research_report_build`
**Phase:** 2.
**Nghiệm thu:** hỏi về 1 đối thủ đã nghiên cứu → MAI chỉ ra file cũ thay vì làm lại từ đầu.

## Luật số 1

**Luôn tra trước khi làm bài mới.** Gọi `vn_research_index` / `vn_research_search` trước —
Khối đang làm lại nghiên cứu chỉ vì không tra được bài cũ (edoris, bostanten, mossdoom, ELLY…).

## SOP theo nguồn

Kalodata · Ad Library · POP · Taobao/nguồn TQ · TikTok Ads Audience Insights.

## Luật nghiên cứu — MAI phải giữ

- **Size / Màu / Kiểu dáng / Kênh** tính theo **SỐ MẪU**, không theo số lượng bán.
- **Thương hiệu** tính theo **số lượng bán**.
- **TikTok Audience Insights:** `Affinity = Selected ÷ All`. Đọc thô cột *Selected* là **sai**.
- **Comment:** chỉ đọc comment **≥3 like**.
- **Xếp hạng KOC** bằng **median views ÷ followers** và **giá / 1.000 view** —
  **không** xếp bằng số follower.
- Gắn **cấp A/B/C** cho mọi dữ kiện (A: số đo trực tiếp · B: suy ra có cơ sở · C: ước đoán).
- Ghi **NĂM** của mọi dữ kiện.
- Không tìm được → ghi **"KHÔNG TÌM ĐƯỢC"**, không suy đoán.

## Format báo cáo (`vn_research_report_build`)

Card ảnh thật → brand + năm → trường ngắn → lớp **"→ HAPAS làm được gì"** → nguồn + cấp A/B/C.

## Giới hạn thật — nói trước, không hứa

Kalodata / TikTok Ads / POP đều cần **session đã đăng nhập**; chạy trên server sẽ **đá người
thật ra**. Phase 2 MAI chỉ làm **SOP + dựng báo cáo**; phần lấy data vẫn chạy trên máy cá nhân.
Phase 3 mới có **runner local** nhận việc từ MAI.

## TODO cho owner

- [ ] Điền `configs/vn_research_sources.json` — index các file nghiên cứu đã có
      (tên file · đối thủ · năm · ai làm · kết luận 1 dòng).
- [ ] Dán SOP chi tiết từng nguồn vào `kb/` (đường lấy số, bẫy hay gặp).
- [ ] Chốt ai giữ máy chạy runner local ở Phase 3.
