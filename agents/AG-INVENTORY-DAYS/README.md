# AG-INVENTORY-DAYS — Giám sát chỉ tiêu ngày tồn kho (DOI) & cảnh báo S&OP

Kiểm tra ngày tồn kho theo 4 nguồn (Hapas VN, MateMade VN, Hapas TL, Nguyên
vật liệu) so với target và ngưỡng an toàn đã chốt trong cuộc họp S&OP, tự tính
số lượng cần đặt thêm khi dưới ngưỡng an toàn.

Manifest: [lsr-agent.yaml](lsr-agent.yaml) · Prompt: [system_prompt.md](system_prompt.md)

**Bot Lark riêng**: `ANN_KHHH` — app_id `cli_aaf6d3a61078ded4` (secret trong
`.env` với tên `LARK_APP_ID_INVENTORY`/`LARK_APP_SECRET_INVENTORY` — không
commit). Đã add vào nhóm test `oc_618134792f49a95d2f455314261c0215`
("test AI") và **đã verify gửi báo cáo thật thành công**.

Quyền đã hoạt động: `im:chat`, `im:message` (gửi), `im:chat.members:bot_access`.
Chưa có: `im:message.group_msg` — chỉ cần nếu muốn agent **đọc** tin nhắn nhóm
để trả lời câu hỏi (thêm scope rồi bấm **Create Version** trên Developer
Console để publish).

## Cách tính

Từ dữ liệu SKU, cộng dồn theo nguồn rồi mới chia (không lấy trung bình NTK
từng SKU — sẽ lệch bởi SKU nhỏ/TĐB=0):

```
ngày_tồn_kho_hiện_tại = SUM(tồn kho + đang trên đường) / SUM(TĐB 30 ngày)
ngày_tồn_kho_tổng     = SUM(tồn kho + đang trên đường + đã xuống đơn NCC) / SUM(TĐB 30 ngày)
```

So với `target_days`, `safety_threshold_days` và `overstock_multiplier` trong
[config/thresholds.yaml](config/thresholds.yaml):
- `days <= safety` → 🔴 dưới ngưỡng an toàn, cần đặt ngay (ngoài kế hoạch)
- `safety < days < target` → 🟡 dưới target nhưng còn an toàn
- `target <= days < target × overstock_multiplier` → 🟢 đạt target
- `days >= target × overstock_multiplier` → 🟣 tồn dư (overstock)

`overstock_multiplier` mặc định 1.5 (đặt ở cấp toàn cục trong config), áp
dụng cho mọi nguồn — có thể khai riêng theo từng nguồn nếu cần khác nhau.

Khi 🔴, script tự tính **số lượng cần đặt thêm** để đưa ngày tồn kho về đúng
target: `(target_days − ngày_tồn_hiện_tại) × TĐB/ngày`.

## Nguồn dữ liệu

- **Hapas VN**: đọc từ file Excel "data gốc" theo dõi tồn kho SKU (MVP hiện
  tại). Cột dùng: `TĐB 30 ngày`, `Slg_TỒN KHO HAPAS`, `Slg_ĐANG TRÊN ĐƯỜNG`,
  `TỔNG_SLG TỒN KHO`. File có vài cột trùng tên (bản "tên cũ"/"tên mới") —
  script tự lấy cột cuối cùng khớp tên (đã hợp nhất).
- **MateMade VN / Hapas TL / Nguyên vật liệu**: **chưa có dữ liệu** — đang
  chờ file/sheet bổ sung. `data_source: null` trong config → script báo
  "chưa có dữ liệu" thay vì lỗi.
- Kế hoạch dài hạn: thay `data_source: excel` bằng `data_source: bigquery`
  cho từng nguồn khi có, không cần đổi phần tính toán/cảnh báo
  (`load_source_aggregate` trong [src/inventory_days.py](src/inventory_days.py)
  là điểm mở rộng nguồn dữ liệu).

## Chạy

```bash
cd src
python inventory_days.py --config ../config/thresholds.yaml --excel "<đường dẫn file excel>"
```

Output: bảng Markdown tổng hợp 4 nguồn, sẵn để dán vào tài liệu/tin nhắn S&OP.

### Chi tiết theo SKU (mã nào tồn cao / tồn thấp)

```bash
python inventory_days.py --config ../config/thresholds.yaml --excel "<file>" --sku-detail --top-n 10
```

Xếp hạng theo **ngày tồn kho hiện tại của từng SKU** = (tồn + đang trên đường) / TĐB 30 ngày:
- **Tồn cao**: ngày tồn lớn nhất → hàng bán chậm, đọng vốn.
- **Tồn thấp**: ngày tồn nhỏ nhất (chỉ xét SKU đang bán, TĐB > 0) → rủi ro hết hàng.
- SKU có **TĐB = 0 mà vẫn còn tồn** được tách riêng: không chia ra ngày tồn được
  (chia cho 0), nhưng đây là nhóm vốn chết đáng lưu ý — dữ liệu Hapas VN hiện có
  **106 mã** như vậy.

Khi kèm `--sku-detail`, tin nhắn Lark cũng gồm bản gọn (top 5 mỗi chiều).

### Gửi thẳng vào nhóm Lark

```bash
python inventory_days.py --config ../config/thresholds.yaml --excel "<đường dẫn file excel>" \
    --lark-chat-id oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Cần `LARK_APP_ID`/`LARK_APP_SECRET` trong file `.env` ở gốc repo (script tự
tìm `.env` từ thư mục hiện tại đi lên). Bot phải đã được **add vào nhóm chat**
đó trước (lấy `chat_id` qua API `GET /open-apis/im/v1/chats`).

## Chưa làm / cần xác nhận thêm

- Đề xuất đặt thêm hiện tính ở **mức tổng công ty**, chưa phân bổ theo
  SKU/BST cụ thể.
- Ngưỡng overstock (×1.5 target) là giá trị đề xuất ban đầu — dữ liệu Hapas
  VN thực tế cho thấy "tổng" đang ~109 ngày (target 60, ngưỡng overstock 90)
  nên đã bị gắn cờ 🟣; chỉnh `overstock_multiplier` trong config nếu muốn
  ngưỡng khác.
- Chưa nối vào Lark để tự gửi thông báo trước cuộc họp S&OP (mới là script
  chạy tay) — sẽ đóng gói thành agent theo chuẩn platform
  ([CREATE_AGENT.md](../../CREATE_AGENT.md)) sau khi chốt logic.
