# Dữ liệu LYLY cần — checklist nạp vào kho tri thức

LYLY **không giữ số trong prompt**. Mọi con số nằm trong kho tri thức đã duyệt, được
`kd_sync.py` đồng bộ hàng ngày từ **Lark Base** và phải qua người duyệt trên console.

Nghĩa là: **số đổi thì sửa trong Base**, hôm sau LYLY biết. Không phải sửa code, không phải
bump version prompt, và mỗi câu trả lời đều dẫn được về đúng dòng dữ liệu gốc.

> Chưa nạp mục nào thì LYLY trả lời _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_
> Đó là hành vi đúng, không phải lỗi. **Đừng điền số giả để test cho xanh** — người ta sẽ
> quyết ngân sách dựa trên con số đó.

## Thực tế: số của team nằm trong docx/sheet, không nằm trong Base

Tra Lark công ty (17/08/2026) thì số vận hành của team đang nằm trong **báo cáo docx và
sheet viết tay**, không nằm trong Lark Base:

| Tài liệu | Loại | Dùng cho |
|---|---|---|
| MATE MADE - BC DAILY | docx | số hằng ngày, vận hành sàn |
| B2S - SHOPEE | docx | ROAS / GMV Max theo SKU |
| CHECK IN 1-1 - TIKTOK | docx | camp TikTok Ads |
| BÁO CÁO AFF HAPAS | docx | KOC ra đơn, ROAS theo KOC |
| JBP DT/CP 2026 MATE MADE | sheet | Investment · Ad GMV · ROAS · CIR |
| 01_SOP · TIKTOK ADS · [KD MATE MADE] - SCOPE | docx | quy trình, SOP |

Chỉ có 2 Lark Base trong tenant và **cả hai đều không phải dữ liệu của team**: "THEO DÕI
TIẾN ĐỘ DOANH THU" (phòng KHHH) và "CÔNG NỢ KHÁCH HÀNG" (Kế toán) — muốn đọc phải xin quyền
phòng khác.

Nên làm **hai giai đoạn**:

### Giai đoạn 1 — sync đúng thứ team đang dùng (làm ngay)

Khai từng tài liệu trong `.env`, **không quét cả space** (quét cả space kéo về cả file
nháp, file cũ, file người khác → người duyệt phải lọc tay):

```bash
KD_DOCS=[{"token":"Hh7Fwh2VpiNUctkhnTylsoCygGf","label":"MATE MADE - BC DAILY","domain":"kd-ops"}]
```

`token` lấy từ URL — đoạn sau `/wiki/`, `/docx/` hoặc `/sheets/`. Code tự nhận biết docx /
sheet / bitable, và tự giải wiki node token thành token tài liệu thật.

Tài liệu nhạy cảm (P&L, giá vốn, chi phí booking) thêm `"scope":"agent"` → chỉ LYLY tra được.

### Giai đoạn 2 — Base "LSR Control Tower" (đang bị chặn quyền)

Base `Ok4QbTTXiag6iIsW3wylsheqgdh` — **LSR Control Tower** (có trang "doanh thu đơn thành
công") là nguồn số chuẩn nhất: Base thật, có cấu trúc bảng, đúng thứ giai đoạn 2 cần.

**Nhưng đang không đọc được qua API.** Base bật **quyền nâng cao** (`is_advanced: true`) →
`table-list` trả về 0 bảng dù token hợp lệ. Và owner của agent **không phải admin của Base**
(`role-list` trả `not admin, baseID:7603642274441875170`).

**Cách mở khoá — cần admin của Base làm, không tự làm được:**
1. Mở Base → **Quyền nâng cao** (Advanced permissions).
2. Tạo (hoặc chọn) một role **chỉ-đọc** trên các bảng LYLY cần.
3. Thêm **app Lark của agent** vào role đó (và cả `linhtk@hapas.vn` nếu cần chạy tay).
4. Xong thì khai vào `.env`:
   `KD_BASES=[{"app_token":"Ok4QbTTXiag6iIsW3wylsheqgdh","label":"LSR Control Tower"}]`

Xin quyền **chỉ trên các bảng cần**, đừng xin quyền cả Base — Control Tower nhiều khả năng
chứa cả số của thương hiệu và phòng ban khác.

Chưa mở được quyền thì giai đoạn 1 (docx/sheet) vẫn chạy bình thường.

Sau khi sync: vào console `/agent/AG-KD-MATE-MADE` → tab **Brain / Duyệt tri thức** →
duyệt. Chưa duyệt thì LYLY chưa dùng được.

## Checklist nội dung

### 1. Bối cảnh thương hiệu — điền vào `system_prompt.md`
Phần này ít đổi nên để trong prompt. Đang là `‹TODO›`:

- [ ] 2–3 điểm khác biệt của túi MATE MADE so với đối thủ
- [ ] Link gian hàng Shopee + TikTok Shop
- [ ] Tên: quản lý team · phụ trách ADS · phụ trách AFF · phụ trách vận hành sàn · kế toán
- [ ] Ai xử lý lương thưởng / hoa hồng nhân viên

### 2. Số cho nhóm ADS — Lark Base
Mỗi dòng một campaign một ngày (hoặc một tuần), tối thiểu các cột:

- [ ] Ngày / kỳ báo cáo ← **bắt buộc**, LYLY dùng cột này làm "kỳ dữ liệu"
- [ ] Sàn (Shopee / TikTok)
- [ ] Tên campaign · SKU
- [ ] Chi phí · Doanh thu · **ROAS**
- [ ] CPC · CPM · lượt hiển thị · click
- [ ] Ngân sách đặt · ngân sách còn lại

### 3. Số cho nhóm AFF — Lark Base
- [ ] Ngày / kỳ báo cáo
- [ ] Tên KOC/KOL · kênh
- [ ] SKU · số đơn ra · doanh thu
- [ ] **% hoa hồng theo SKU** (mức công khai)
- [ ] Tỷ lệ hoàn đơn từ affiliate

### 4. Số cho nhóm Vận hành sàn — Lark Base
- [ ] Ngày / kỳ báo cáo
- [ ] SKU · tên sản phẩm · **tồn kho**
- [ ] Số đơn · đơn hủy · đơn hoàn · **tỷ lệ hủy / hoàn**
- [ ] Điểm sức khỏe shop từng sàn
- [ ] Giá bán đang niêm yết

### 5. Chính sách & deadline — Drive/Wiki hoặc một bảng trong Base
- [ ] Chính sách đổi trả / hoàn hàng của **Shopee**
- [ ] Chính sách đổi trả / hoàn hàng của **TikTok Shop**
- [ ] Quy định về điểm sức khỏe shop, các mức phạt
- [ ] **Lịch & deadline đăng ký campaign sàn** (9.9, 10.10, 11.11, 12.12…)
- [ ] Quy trình nội bộ: ai duyệt ngân sách, ai duyệt giá, ai duyệt booking

### 6. Dữ liệu hạn chế — **bắt buộc** `scope: agent`
Nên để **Base riêng** hoặc bảng riêng, tách khỏi số vận hành thường:

- [ ] Giá vốn / giá nhập theo SKU
- [ ] Biên lợi nhuận theo SKU / theo campaign
- [ ] Chi phí booking KOC/KOL, hợp đồng affiliate, mức hoa hồng riêng
- [ ] Dữ liệu người mua (SĐT, địa chỉ) — cân nhắc **không nạp** nếu không thật sự cần
- [ ] Công nợ / giá nhà cung cấp

- [ ] Chốt danh sách người được xem → điền `KD_CONFIDENTIAL_VIEWERS` trong `.env`.
      Để rỗng = **không ai** xem được (fail-closed, cố ý).

## Sổ tay công ty (LAMSON RETAIL INFORMATION_2026) — nạp phần nào

Tài liệu `HJCywftE8ikT6DkwQ14lpIWfgbb` chứa cả bối cảnh thương hiệu lẫn nội quy nhân sự.

- **Phần bối cảnh thương hiệu** (lịch sử, định vị MATE MADE, tầm nhìn, giá trị cốt lõi,
  lịch họp) — **đã đưa thẳng vào `system_prompt.md`**, không cần sync.
- **Phần nội quy nhân sự** (phép, lương, phúc lợi, đơn từ) — **không nên nạp**. LYLY khai
  báo rõ là không xử lý lương thưởng/nhân sự; nạp vào chỉ khiến LYLY trả lời những câu
  đáng lẽ phải hỏi phòng Nhân sự, mà lại không chịu trách nhiệm được về câu trả lời đó.

Muốn LYLY trả lời cả câu hỏi nhân sự thì đó là **mở rộng phạm vi** — phải sửa `USECASE.md`,
`system_prompt.md` và bộ test trước, đừng làm bằng cách lặng lẽ nạp thêm tài liệu.

## Chặn secret lọt vào kho

`kd_sync.py` tự **che giá trị** của mọi dòng dạng `password/pass/mật khẩu/secret/api_key/
token: …`, và các chuỗi dạng `sk-ant-…`, `lsr_tel_…`, `cli_…`, trước khi nộp lên kho.

Có thật trong wiki công ty: mục "Văn hóa Học tập" đang để **tài khoản Brandcamp dùng chung
kèm mật khẩu**. Không che thì LYLY sẽ đọc lại mật khẩu đó cho bất kỳ ai hỏi.

> Lớp che này là **lưới an toàn cuối**, không phải giải pháp. Gốc rễ là secret không nên
> nằm trong wiki ai cũng đọc được — báo phòng Nhân sự chuyển sang SSO hoặc tài khoản riêng.
> `kd_sync` in cảnh báo kèm số chuỗi đã che mỗi lần chạy; nếu con số đó lớn dần thì nghĩa là
> đang có thêm secret được viết vào tài liệu.

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

## Cột "ngày / kỳ báo cáo" — đừng bỏ qua

Đây là nguồn lỗi nguy hiểm nhất của agent này. Không có nó, LYLY trả số mà không nói được
của ngày nào; người đọc mặc định là hôm nay rồi quyết ngân sách sai — và **không ai phát
hiện ra ngay**, khác với bịa số vì bịa thì thường nhìn là thấy sai.

**Giai đoạn 1 chỉ giảm thiểu được một phần.** Số nằm trong văn xuôi báo cáo ("set GMV Max
ROAS 7.1 cho Balo Glowy") thì `kd_sync` chỉ suy được kỳ từ **tiêu đề và heading** của tài
liệu — không chắc bằng một cột ngày. Vì vậy ở giai đoạn 1, LYLY trả **nguyên đoạn kèm link**
để người tự đọc con số trong ngữ cảnh của nó, thay vì trích ra một con số trần trụi.

Đây là lý do chính nên làm giai đoạn 2. Nếu team chỉ dựng được **một** thứ, dựng bảng có ba
cột: **ngày · chỉ số · giá trị**. Chừng đó đã đủ để LYLY trả lời chắc chắn.
