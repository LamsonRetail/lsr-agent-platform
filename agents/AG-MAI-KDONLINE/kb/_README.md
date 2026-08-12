# Kho tri thức của MAI (`kb/`)

Đây là **nguồn duy nhất** MAI được phép trả lời dựa vào. Không có trong đây → MAI nói
*"chưa có trong kho"*, không đoán.

## Cách nạp

1. Bỏ file `.md` vào thư mục này (chia thư mục con theo chủ đề nếu muốn).
2. Mỗi file: **1 tiêu đề `#` ở đầu**, chia mục bằng `##` / `###` — MAI đọc theo từng mục,
   không nuốt cả file.
3. Khai đường dẫn vào config tương ứng (`vn_kb_files`, `vn_research_sources`…).
4. Kiểm tra MAI thấy file: `python3 ../vn/vietnam_tools.py --call vn_kb_index '{}'`

File bắt đầu bằng `_` (như file này) **không** vào mục lục.

## Nội dung cần nạp cho Phase 0

| Nhóm | Ai nạp | Trạng thái |
|---|---|---|
| JTBD & danh mục SP — Túi xách | TP Digital / PM Túi | ⬜ chưa nạp |
| JTBD & danh mục SP — Trang sức | PM Ngành TS | ⬜ chưa nạp |
| JTBD & danh mục SP — Nước hoa | PM Ngành NH | ⬜ chưa nạp |
| RACI Khối KD Online | HR / People Ops | ⬜ chưa nạp |
| Khung năng lực Junior/Senior + JD | HR / People Ops | ⬜ chưa nạp |
| Chiến lược & kế hoạch quý | TP KD Online | ⬜ chưa nạp |
| Phân tích đối thủ đã có (edoris, bostanten, mossdoom, ELLY…) | (việc còn trống) | ⬜ chưa nạp |
| Template WBR đang dùng | PM / TP KD Online | ⬜ chưa nạp |
| SOP nghiên cứu theo nguồn | (việc còn trống) | ⬜ chưa nạp |

## Luật khi nạp — dữ liệu nhạy cảm

- **Bỏ mọi trường lương và đánh giá cá nhân** trước khi đưa file vào đây.
- Thông tin cá nhân (SĐT, địa chỉ, hợp đồng) không nạp trừ khi thật sự cần cho nghiệp vụ.
- Mỗi dữ kiện nên ghi **năm** và **nguồn** — MAI sẽ trích lại đúng như file ghi.

## Vì sao không nhồi hết vào system prompt

Chuẩn platform: file/link được share thì **index ra ngoài** (resource index), không nhồi
vào memory. MAI tra 2 bước (`vn_kb_index` → `vn_kb_read`) để không đốt token.
