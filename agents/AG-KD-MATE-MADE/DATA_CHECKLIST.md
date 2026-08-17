# Dữ liệu LYLY cần — checklist nạp vào kho tri thức

LYLY **không giữ giá trong prompt**. Mọi con số nằm trong kho tri thức đã duyệt, được
`kd_sync.py` đồng bộ hàng ngày từ Lark và phải qua người duyệt trên console.

Nghĩa là: **đổi giá thì sửa file gốc trên Lark**, hôm sau LYLY biết. Không phải sửa code,
không phải bump version prompt, và mỗi câu trả lời đều dẫn được về đúng dòng dữ liệu gốc.

> Chưa nạp mục nào thì LYLY trả lời _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_
> Đó là hành vi đúng, không phải lỗi. **Đừng điền số giả để test cho xanh** — sale sẽ copy
> nguyên con số đó gửi cho khách.

## Cách nạp

| Loại dữ liệu | Để ở đâu | Vào kho qua |
|---|---|---|
| Bảng giá, tồn kho, pipeline, khách hàng | **Lark Base** | `KD_BASES` trong `.env` |
| Báo cáo doanh số, bảng chính sách dạng tài liệu | **Drive/Sheets** (file docx) | `KD_FOLDERS` trong `.env` |
| Quy trình, FAQ, playbook bán hàng | **Lark Wiki KD** | `KD_SYNC_WIKI` (đọc ghi chú trong `kd_sync.py`) |

Sau khi sync: vào console `/agent/AG-KD-MATE-MADE` → tab **Brain / Duyệt tri thức** →
duyệt. Chưa duyệt thì LYLY chưa dùng được.

## Checklist nội dung

### 1. Bối cảnh thương hiệu — điền vào `system_prompt.md`
Phần này ít đổi nên để trong prompt. Đang là `‹TODO›`:

- [ ] Ngành hàng
- [ ] Khách hàng chính (bán lẻ / sỉ / đại lý / doanh nghiệp)
- [ ] 2–3 điểm khác biệt so với đối thủ (câu sale hay dùng để thuyết phục)
- [ ] Website / fanpage
- [ ] Tên: quản lý kinh doanh · kho/vận hành · kế toán · marketing
- [ ] Hệ thống nhập đơn (bước 3 quy trình chốt đơn)
- [ ] Ai xử lý: lương thưởng/hoa hồng · khiếu nại lớn

### 2. Sản phẩm & giá — vào **Lark Base** (`scope: agent`)
Mỗi sản phẩm một dòng, tối thiểu các cột:

- [ ] Tên sản phẩm · **SKU**
- [ ] Giá lẻ
- [ ] Giá sỉ + **số lượng tối thiểu** áp dụng
- [ ] Mô tả: chất liệu, kích thước, màu có sẵn
- [ ] Điểm bán hàng (lý do khách nên mua)
- [ ] Tồn kho: luôn có / đặt trước bao nhiêu ngày

### 3. Chiết khấu — vào **Lark Base hoặc Sheets**
- [ ] Bậc 1: đơn từ ‹mức› → giảm ‹%›
- [ ] Bậc 2: đơn từ ‹mức› → giảm ‹%›
- [ ] Chính sách riêng cho đại lý / khách sỉ
- [ ] **Mức tối đa sale được tự quyết** + ai duyệt khi vượt

> ⚠️ LYLY **chỉ nhắc lại** các mức này, không bao giờ tự phán "được". Sale hỏi "giảm thêm
> được không" luôn bị đẩy về quản lý kinh doanh — kể cả khi bảng chiết khấu đã có trong kho.

### 4. Giao hàng & thanh toán — vào **Sheets/Docs chính sách**
- [ ] Nội thành ‹tỉnh/thành›: thời gian + phí
- [ ] Tỉnh khác: thời gian + phí
- [ ] Miễn phí ship từ mức đơn nào
- [ ] Hình thức thanh toán (CK / COD / công nợ bao nhiêu ngày)
- [ ] **Thông tin chuyển khoản** gửi khách: số TK — tên — ngân hàng

> Số tài khoản để trong kho tri thức (không phải trong prompt) để đổi tài khoản là sửa một
> chỗ. LYLY không được nhớ số tài khoản từ trí nhớ — luôn lấy từ nguồn.

### 5. Đổi trả & bảo hành — vào **Docs chính sách**
- [ ] Đổi trả trong bao nhiêu ngày + điều kiện
- [ ] Bảo hành bao lâu + phạm vi
- [ ] Các trường hợp **không** áp dụng

### 6. FAQ — vào **Wiki KD**
- [ ] Câu khách hỏi nhiều nhất + câu trả lời chuẩn của team
- [ ] Câu số 2 + đáp
- [ ] Câu số 3 + đáp

### 7. Dữ liệu hạn chế — **bắt buộc** `scope: agent`
Nạp riêng, không để chung với bảng giá công khai:

- [ ] Giá vốn / biên lợi nhuận
- [ ] Chiết khấu riêng theo từng khách
- [ ] Danh sách khách hàng, thông tin liên hệ
- [ ] Công nợ, hạn mức tín dụng

`kd_sync.py` đã set `scope=agent` + `agent_id` cho mọi item từ Lark Base. **Đừng đổi thành
`shared`** — đó là mở giá vốn cho mọi agent trong công ty.

- [ ] Chốt danh sách người được xem → điền `KD_CONFIDENTIAL_VIEWERS` trong `.env`.
      Để rỗng = **không ai** xem được (fail-closed, cố ý).

## Kiểm sau khi nạp

```bash
# 1. Xem thử sẽ nộp gì, KHÔNG ghi lên platform
python3 kd_sync.py --dry-run

# 2. Nộp thật (vào hàng chờ pending)
python3 kd_sync.py --once

# 3. Duyệt trên console, rồi chạy bộ test
bash scripts/agent-test.sh AG-KD-MATE-MADE
```

Chạy `kd_sync.py --once` hai lần liên tiếp: lần hai phải báo `unchanged`, không nộp lại.
Nếu lần hai vẫn `submitted` thì `item_id` đang không ổn định — mỗi ngày team sẽ phải duyệt
lại toàn bộ kho.
