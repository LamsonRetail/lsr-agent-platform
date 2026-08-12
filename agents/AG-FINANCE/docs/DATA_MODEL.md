# Mô hình dữ liệu FIN-HUB

Định nghĩa dữ liệu chung của dự án. Code trong `data_hub/schema.py` phải khớp với tài liệu
này. Đổi một bên thì đổi cả bên kia.

## Kiến trúc: nguồn → chuẩn hoá → mặt tiền

```
Google Sheet  ─┐
MISA AMIS API ─┼→ data_hub/sources/* → schema chuẩn → Lark Base "FIN-HUB"
Lark Base cũ  ─┘                                            │
                                                            ├→ squad mở Lark ra xem/sửa
                                                            └→ agent đọc lại để trả lời chat
```

**Lark Base FIN-HUB là mặt tiền, không phải nguồn sự thật cho kế toán.** Nguồn sự thật vẫn
là MISA. FIN-HUB là bản sao đã chuẩn hoá, luôn trễ hơn nguồn một khoảng. Vì vậy mọi câu trả
lời phải kèm mốc `synced_at`.

Agent **chỉ đọc** MISA. Không có đường ghi ngược.

## Quy ước chung cho mọi bảng

| Quy ước | Lý do |
|---|---|
| Tiền là `Decimal`, đơn vị VND, không có phần thập phân trong dữ liệu gốc | `float` làm sai số tích luỹ vào báo cáo |
| Ngày là `date`, thời điểm là `datetime` có timezone `Asia/Ho_Chi_Minh` | Tránh lệch ngày khi tính tuổi nợ |
| Mọi bản ghi có `source` và `source_ref` | Truy được số này từ đâu ra, để đối chiếu khi lệch |
| Mọi bản ghi có `synced_at` | Biết dữ liệu cũ đến mức nào |
| Khoá tự nhiên, không dùng số thứ tự dòng | Đồng bộ lại không được nhân đôi dữ liệu |
| Thiếu trường bắt buộc → báo lỗi, không điền mặc định | `0` giả gây hiểu sai nghiêm trọng hơn là lỗi |

## Các bảng

### 1. `receivable` — Công nợ phải thu

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `partner_code` | str | ✔ | Mã khách hàng. Phần khoá tự nhiên |
| `partner_name` | str | ✔ | |
| `invoice_no` | str | ✔ | Số hoá đơn / chứng từ. Phần khoá tự nhiên |
| `invoice_date` | date | ✔ | |
| `due_date` | date | ✔ | Dùng để tính tuổi nợ |
| `amount` | Decimal | ✔ | Giá trị gốc |
| `paid_amount` | Decimal | ✔ | Đã thu |
| `outstanding` | Decimal | ✔ | Còn lại. **Phải bằng** `amount - paid_amount`, kiểm khi nạp |
| `currency` | str | | Mặc định `VND` |
| `source` / `source_ref` / `synced_at` | | ✔ | Quy ước chung |

Khoá tự nhiên: `(source, partner_code, invoice_no)`.
Tuổi nợ tính lúc truy vấn, không lưu sẵn — vì nó đổi mỗi ngày.

### 2. `payable` — Công nợ phải trả

Cùng cấu trúc `receivable`, `partner_code` là mã nhà cung cấp.
Tách bảng riêng để không bao giờ cộng lẫn phải thu với phải trả.

### 3. `revenue` — Doanh thu

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `period` | str | ✔ | `YYYY-MM`. Phần khoá tự nhiên |
| `channel` | str | ✔ | Kênh bán |
| `store_code` | str | | Cửa hàng, rỗng nếu không phân theo cửa hàng |
| `amount` | Decimal | ✔ | Doanh thu thuần |
| `source` / `source_ref` / `synced_at` | | ✔ | |

Khoá tự nhiên: `(source, period, channel, store_code)`.

### 4. `expense` — Chi phí

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `period` | str | ✔ | `YYYY-MM` |
| `account_code` | str | ✔ | Mã khoản mục chi phí |
| `account_name` | str | ✔ | |
| `department` | str | | Phòng ban chịu chi phí |
| `amount` | Decimal | ✔ | Thực tế |
| `budget_amount` | Decimal | | Ngân sách, để so sánh. `None` = không có ngân sách, khác với ngân sách bằng 0 |
| `source` / `source_ref` / `synced_at` | | ✔ | |

Khoá tự nhiên: `(source, period, account_code, department)`.

Lãi lỗ **không lưu thành bảng riêng** — tính từ `revenue` và `expense` lúc truy vấn, để
không có hai con số lãi lỗ lệch nhau trong hệ thống.

### 5. `cashflow` — Dòng tiền

| Trường | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `txn_date` | date | ✔ | |
| `account_code` | str | ✔ | Tài khoản tiền (quỹ / ngân hàng) |
| `direction` | str | ✔ | `in` hoặc `out`. Không dùng số âm để biểu thị chiều |
| `amount` | Decimal | ✔ | Luôn dương |
| `category` | str | | Phân loại dòng tiền |
| `description` | str | | |
| `source` / `source_ref` / `synced_at` | | ✔ | |

Khoá tự nhiên: `(source, source_ref)` — chứng từ gốc.
Số dư tính bằng cách cộng dồn, không lưu sẵn.

### 6. `sync_log` — Nhật ký đồng bộ

Không phải dữ liệu nghiệp vụ, nhưng bắt buộc có: đây là cách trả lời được câu "số này cũ
chưa" và "hôm qua đồng bộ có lỗi gì".

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `run_id` | str | |
| `source` | str | Nguồn nào |
| `table` | str | Bảng nào |
| `started_at` / `finished_at` | datetime | |
| `status` | str | `ok` / `partial` / `failed` |
| `rows_read` / `rows_written` | int | |
| `error` | str | Rỗng nếu `ok` |

## Xử lý lệch số giữa các nguồn

Cùng một khoá tự nhiên nhưng hai nguồn ra hai con số khác nhau: **không tự chọn bên nào**.

1. Giữ cả hai bản ghi, phân biệt bằng trường `source`.
2. Ghi một dòng vào `sync_log` với `status = partial` và mô tả lệch.
3. Báo cho squad. Khi ai đó hỏi số liệu liên quan, agent phải nói rõ đang có lệch và nêu cả
   hai con số kèm nguồn.

Tự động chọn "nguồn đáng tin hơn" là cách nhanh nhất để một con số sai đi vào báo cáo mà
không ai biết.

## Chưa quyết

- Ngưỡng bao lâu thì coi dữ liệu là cũ (đề xuất: 24 giờ cho công nợ, 1 tháng cho doanh thu
  và chi phí) — chốt khi biết tần suất đồng bộ thực tế.
- Mã khoản mục chi phí có dùng chung với hệ thống mã của MISA hay tự định nghĩa lại.
- Lark Base FIN-HUB đặt trong không gian nào, ai được quyền sửa trực tiếp trên đó.
