# Skill · Bối cảnh ngành Nước hoa

**Owner:** PM Ngành Nước hoa — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_context_nh`
**Phase:** 0 (bối cảnh) → dùng chung với Ads-ops và Báo cáo.
**Nghiệm thu:** MAI trả số ngành NH riêng; biết vùng giá & đối thủ NH.

## Vì sao cần skill riêng

Ngành Nước hoa **mới**, tệp khách và vùng giá khác hẳn Túi xách. RACI đã tách PM ngành NH.
Gộp số NH vào tổng khối sẽ che mất tín hiệu thật của ngành.

## Luật bắt buộc

- **Không gộp số NH với Túi hay TS.**
- Nêu rõ giai đoạn ngành khi so sánh hiệu quả — không so CPA/ROAS như thể cùng vạch xuất phát.
- Số chưa có trong `vn_context_nh` → nói **"chưa có"**, không suy ra từ ngành khác.

## TODO cho owner — điền `configs/vn_context_nh.json`

- [ ] **Tệp khách:** ai mua, mua cho ai, dịp mua (trục quà tặng mạnh với NH).
- [ ] **Vùng giá:** khoảng giá đang bán, giá trung bình đơn, vùng giá thị trường chấp nhận.
- [ ] **Đối thủ:** tên, vùng giá, điểm mạnh, cách họ đang chạy.
- [ ] **Giai đoạn & mục tiêu:** đang học thị trường hay đã tìm được công thức; KPI đang đo.
- [ ] **Danh mục SP chủ lực** + SP đang xả / SP biên lợi nhuận cao.
- [ ] **Đặc thù nghiệp vụ NH** cần MAI biết (mùi/nhóm hương, dung tích, quy định vận chuyển…).
- [ ] **Điều MAI hay trả lời sai về ngành NH** (viết ra để chặn trước).
