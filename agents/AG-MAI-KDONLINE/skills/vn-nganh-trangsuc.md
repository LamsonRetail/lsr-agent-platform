# Skill · Bối cảnh ngành Trang sức

**Owner:** PM Ngành Trang sức — chỉ owner sửa file này.
**Config phụ thuộc:** `vn_context_ts`
**Phase:** 0 (bối cảnh) → dùng chung với Ads-ops và Báo cáo.
**Nghiệm thu:** MAI trả số ngành TS **không gộp với Túi**; biết TS đang "học thị trường".

## Vì sao cần skill riêng

RACI đã tách PM ngành TS & NH. Ngành TS **mới**, đang ở giai đoạn *học thị trường* —
ép chung KPI với Túi xách sẽ ra kết luận sai. Mọi câu trả lời về TS phải tách riêng.

## Luật bắt buộc

- **Không gộp số TS với Túi hay NH** trong bất kỳ báo cáo/phân tích nào.
- Khi so sánh hiệu quả, nêu rõ TS đang ở giai đoạn nào (học thị trường / mở rộng / tối ưu) —
  không so CPA/ROAS của TS với ngành đã chạy lâu như thể cùng vạch xuất phát.
- Số nào chưa có trong `vn_context_ts` thì nói **"chưa có"** — không mượn số ngành khác suy ra.

## TODO cho owner — điền `configs/vn_context_ts.json`

- [ ] **Tệp khách:** ai mua, mua cho ai (tự dùng / tặng), dịp mua.
- [ ] **Vùng giá:** khoảng giá đang bán, giá trung bình đơn, vùng giá thị trường chấp nhận.
- [ ] **Đối thủ:** tên, vùng giá, điểm mạnh, cách họ đang chạy.
- [ ] **Giai đoạn & mục tiêu:** đang học thị trường hay đã tìm được công thức; KPI đang đo là gì.
- [ ] **Danh mục SP chủ lực** + SP đang xả / SP biên lợi nhuận cao.
- [ ] **Điều MAI hay trả lời sai về ngành TS** (viết ra để chặn trước).
