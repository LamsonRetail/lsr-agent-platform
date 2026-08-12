# Skill · Tri thức con người & tổ chức

**Owner:** HR / People Ops — ⚠ **CHƯA XÁC NHẬN PIC.** Phải chốt ai giữ vai People Ops cho
Khối KD Online trước khi phát bảng phân công (xem `PHANCONG.md` dòng 9).
**Config phụ thuộc:** `vn_kb_files`
**Tool:** `vn_kb_index` · `vn_kb_read`
**Phase:** 0.
**Nghiệm thu:** hỏi "ai là PM ngành TS, báo cáo lên ai" → MAI trả đúng theo RACI.

## Khi nào dùng

Câu hỏi về **tổ chức · RACI · khung năng lực Junior/Senior · JD · tuyển dụng** của Khối
KD Online — đang tuyển CV Ads / AFF / Content cho ngành mới.

## Trình tự

1. `vn_config_get("vn_kb_files")` → biết file tri thức tổ chức nằm ở đâu trong `kb/`.
2. Tra 2 bước: `vn_kb_index` → `vn_kb_read`.
3. Trả lời kèm **tên file + mục**.

## Luật bắt buộc — dữ liệu nhạy cảm

- **KHÔNG xử lý số lương và đánh giá cá nhân.** Không trả lời, không lưu vào bộ nhớ.
- Thông tin cá nhân (số điện thoại, địa chỉ, tình trạng hợp đồng) chỉ trả cho người có quyền
  theo `role_permissions` — mặc định là **không**.
- Câu hỏi về hiệu suất của một cá nhân cụ thể → chuyển về quản lý trực tiếp, MAI không nhận xét.
- Trả lời về JD/khung năng lực thì bám đúng file, không tự chế tiêu chí.

## TODO cho owner

- [ ] **Chốt PIC People Ops của Khối KD Online** (đang là câu hỏi mở của PLAN §7).
- [ ] Điền `configs/vn_kb_files.json` — đường dẫn các file: RACI · khung năng lực Junior/Senior ·
      JD từng vị trí · quy trình tuyển dụng.
- [ ] Nạp các file đó vào `kb/`, **loại bỏ trước** mọi trường lương và đánh giá cá nhân.
