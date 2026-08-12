# Kho tri thức nguồn cho não Harry (Finance & Accounting)

Mỗi file `.md` trong thư mục này là **một mục tri thức** sẽ được nạp vào brain
riêng của `AG-HARRY` (qua `scripts/seed_brain.py`, gọi `POST /v1/self/brain/items`).

> ⚠️ Nội dung ở đây phải là **tài liệu/quy trình THẬT** của Lam Sơn Retail (copy
> từ Lark Wiki/Docs/Sheet nội bộ, có `source_url` trỏ về bản gốc). KHÔNG tự bịa
> số liệu/quy định tài chính — vì Harry sẽ dùng đúng nội dung này để trả lời
> thật cho phòng Finance & Accounting.

## Định dạng 1 file
```markdown
---
title: Quy trình đề nghị thanh toán
domain: finance-accounting
tags: [thanh-toan, quy-trinh]
source_url: https://lark.example.com/wiki/xxxx   # link tài liệu gốc trên Lark Wiki
kind: process                                     # knowledge|process|definition|lesson|belief|faq
---

Nội dung tri thức ở đây (có thể nhiều đoạn, markdown thường).
```

`title`/`content` (phần sau `---` thứ 2) là bắt buộc. `source_url` nên có để
Harry trích dẫn nguồn khi trả lời (đúng nguyên tắc "không bịa" trong
`system_prompt.md`).

## Nạp vào brain
```bash
# xem trước, chưa gọi API:
python3 scripts/seed_brain.py --dry-run

# nạp thật (cần LSR_AGENT_TOKEN của AG-HARRY sau khi đã đăng ký với platform):
LSR_AGENT_TOKEN=... python3 scripts/seed_brain.py
```

Xem file mẫu [`_TEMPLATE.md`](_TEMPLATE.md) (script tự bỏ qua file bắt đầu bằng `_`).
