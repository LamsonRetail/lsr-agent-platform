# Skill · Tri thức nội bộ VN

**Owner:** TP Digital Performance (điều phối) — chỉ owner sửa file này.
**Config phụ thuộc:** `persona` · `vn_context` · `role_permissions` · `vn_squads` · `vn_p2p_partners`
**Tool:** `vn_kb_index` · `vn_kb_read` · `vn_config_get` · `vn_review_report`
**Phase:** 0 — nền của mọi skill khác.
**Nghiệm thu:** hỏi MAI 1 câu về JTBD → trả lời có số + tên file.

## Khi nào dùng

Mọi câu hỏi về **sản phẩm · JTBD · tổ chức · chiến lược 3 ngành** — dựa trên chính các file
đã có trong `kb/`, không suy đoán.

Kho gồm: JTBD & danh mục SP 3 ngành (Túi/TS/NH) · Con người–Tổ chức (RACI, khung năng lực
Junior/Senior, JD) · Chiến lược & kế hoạch quý · phân tích đối thủ đã có · bộ nhớ `.md`.

## Trình tự bắt buộc — tra 2 bước

1. `vn_kb_index(query=…)` → mục lục, chọn đúng mục. **Không đọc cả kho.**
2. `vn_kb_read(file=…, section=…)` → đọc đúng mục đó.
3. Trả lời **kèm `cite_as`** (tên file + mục) mà tool trả về.

Không có trong kho → nói **"chưa có trong kho"**. Không đoán.

## Phân quyền trước khi trả lời

1. `vn_config_get("vn_squads")` → người hỏi thuộc nhóm nào, báo cáo lên ai.
2. `vn_config_get("role_permissions")` → vai trò đó xem được gì, làm được gì.
3. Ngoài quyền → *"phần này em không được chia sẻ"*. Không lách, không trả lời một nửa.

LNĐG / P&L chỉ mở cho cấp quản lý (TP, PM). CV chỉ xem DT & traffic phần mình.
**Không xử lý số lương / đánh giá cá nhân**, không lưu vào bộ nhớ.

## `vn_review_report` — soi báo cáo tuần theo 6 trục

1. Reach vs revenue — có nhầm chỉ số phù phiếm thành kết quả kinh doanh không.
2. Nhìn sau vs nhìn trước — báo cáo chỉ kể chuyện đã qua hay có hành động kỳ tới.
3. Quyết định lớn bị ghi như ghi chú — quyết định đổi hướng nằm lẫn trong bullet phụ.
4. "Done" giả — đánh dấu xong nhưng không có đầu ra chấm được.
5. Ngày tháng lệch giữa các tài liệu.
6. Mảng đang thắng lại viết ít nhất.

## TODO cho owner

- [ ] Điền `configs/persona.json` — tên, giọng, xưng hô, độ dài trả lời.
- [ ] Điền `configs/vn_context.json` — target tháng/quý, 2 brand, 3 ngành, mục tiêu KD hiện tại.
- [ ] Điền `configs/role_permissions.json` — map vai trò RACI → quyền (theo FEATURES §5).
- [ ] Điền `configs/vn_squads.json` — cây tổ chức từ RACI.
- [ ] Điền `configs/vn_p2p_partners.json` — whitelist chat riêng.
- [ ] Nạp file tri thức vào `kb/` (xem `kb/README.md`).
