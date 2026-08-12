# Skill · Mốc BST (bộ sưu tập)

**Owner:** MKT / CĐS — chỉ owner sửa file này (cùng owner với `vn-season-calendar.md`).
**Config phụ thuộc:** `vn_bst_milestones`
**Tool:** `vn_milestone_list` · `vn_milestone_check` · `vn_milestone_conflict`
**Phase:** 1.
**Nghiệm thu:** hỏi về 1 BST → MAI đếm ngược đúng mốc và cảnh báo mốc đang trượt.

## Trình tự

1. `vn_milestone_list` → các BST đang theo dõi.
2. `vn_milestone_check` → **đếm ngược tới mốc tuyệt đối** (ngày cụ thể), cảnh báo khi trượt.
   Mốc chuẩn: **chốt mẫu · xuống PO · lên kệ · chốt KOC**.
3. `vn_milestone_conflict` ⭐ → phát hiện **một mốc có nhiều phiên bản ngày** giữa các nguồn.

## Luật bắt buộc

- Đếm ngược theo **ngày tuyệt đối**, không theo "còn mấy tuần nữa" mơ hồ.
- Mốc trượt → cảnh báo ngay + nêu mốc kế tiếp bị ảnh hưởng (dây chuyền), không chỉ báo 1 mốc.
- **Lệch ngày giữa các nguồn** → liệt kê thành **bảng đối chiếu** (nguồn · ngày · cập nhật lúc nào)
  rồi **bắt chốt 1 nguồn chuẩn**. Tuyệt đối không tự chọn ngày nào đúng.
- Không tự đổi ngày launching — đó là quyết định của con người.

## TODO cho owner — điền `configs/vn_bst_milestones.json`

- [ ] Mỗi BST: mã · tên · ngành · ngày launching dự kiến.
- [ ] Mốc tuyệt đối: chốt mẫu · xuống PO · hàng về · lên kệ · chốt KOC · mở bán.
- [ ] Luật **D-x**: mỗi mốc phải xong trước ngày launching bao nhiêu ngày.
- [ ] **Nguồn chuẩn** cho ngày của từng BST (file/Lark Base nào là nguồn duy nhất được tin).
