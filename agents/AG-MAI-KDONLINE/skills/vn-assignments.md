# Skill · Giao việc & đôn đốc theo RACI

**Owner:** TN Affiliate / TP TMĐT — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_squads` (của TP Digital — **không sửa file config đó**, cần đổi thì nhắn owner)
**Tool:** `vn_assignment_create` · `_list` · `_update` · `_remind` · `_escalate`
**Phase:** 2.
**Nghiệm thu:** giao 1 việc test → MAI nhắn đủ 4 yếu tố cho PIC.

## Bốn yếu tố bắt buộc

Mọi assignment phải đủ **4 yếu tố**. **Thiếu 1 yếu tố → MAI TỪ CHỐI TẠO** và hỏi bổ sung:

1. **Việc gì** — mô tả hành động cụ thể.
2. **Bối cảnh** — vì sao cần, gắn với mục tiêu nào.
3. **Đầu ra cụ thể để chấm được** — nộp cái gì, đo bằng gì. ("Làm tốt hơn" không phải đầu ra.)
4. **PIC** — một người chịu trách nhiệm, không phải một nhóm.

## Ai được giao việc

Bám cột **A (Accountable)** trong RACI: TP KD Online · TP Digital Performance ·
PM ngành TS/NH · TP TMĐT · và các **Trưởng nhóm trong phạm vi nhóm mình**.

Người ngoài danh sách gọi giao việc → MAI **nói rõ ai được giao** trong phạm vi đó,
không tạo assignment.

## Luồng

1. `vn_config_get("vn_squads")` → xác định người giao có quyền không, PIC thuộc nhóm nào.
2. `vn_assignment_create` → tạo record + Lark task + **tự nhắn PIC đầy đủ thông tin**.
3. `vn_assignment_remind` → nhắc trước hạn.
4. `vn_assignment_escalate` → **luật 24h**: PIC im 24h → escalate theo cây RACI
   (CV → TN → TP/PM). Escalate là thông báo, không phải phán xét.

## Luật bắt buộc

- Không tạo assignment thiếu 4 yếu tố — kể cả khi người giao là TP.
- Không giao việc vượt phạm vi nhóm của người giao.
- Escalate theo đúng cây RACI, không nhảy cấp.
- Không lưu đánh giá cá nhân vào bộ nhớ.

## TODO cho owner

- [ ] Chốt với TP Digital: cây RACI trong `vn_squads` đã đủ để xác định ai giao được việc chưa.
- [ ] Chốt mẫu tin nhắn giao việc gửi PIC (4 yếu tố + hạn + link).
- [ ] Chốt thời hạn escalate cho từng cấp (mặc định 24h) và ai nhận escalate cuối.
