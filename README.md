# Rating Agent — LamsonRetail

Agent nội bộ đánh giá nhân viên/agent của LamsonRetail theo 3 trục:
**Collaboration** (phối hợp), **Grow** (phát triển), **Performance** (hiệu quả).
Dữ liệu lấy từ **Lark** (chat, document, task) và **BigQuery** data warehouse.

> Chi tiết kiến trúc, nguồn dữ liệu, tiêu chí và lộ trình: xem [PLAN.md](PLAN.md).

## Cài đặt

```bash
cd RatingAgent-LamsonRetail
python3 -m venv .venv && source .venv/bin/activate   # macOS thường chỉ có python3
pip install -e ".[dev]"        # hoặc: pip install -r requirements.txt
```

> Sau khi `source .venv/bin/activate`, lệnh `python` và `pytest` mới có trong
> PATH. Nếu chưa activate, gọi trực tiếp: `./.venv/bin/python` và
> `./.venv/bin/python -m pytest`.

## Cấu hình

```bash
cp .env.example .env
# Điền LARK_APP_ID / LARK_APP_SECRET và thông tin BigQuery (service account).
```

Xem danh sách biến môi trường trong [.env.example](.env.example).

## Chạy demo (dữ liệu mẫu, không cần credential)

```bash
python -m rating_agent.pipeline
```

Kết quả: bảng xếp hạng 3 nhân viên mẫu với điểm tổng và xếp loại.

## Chạy test

```bash
pytest
```

## Cấu trúc thư mục

```
RatingAgent-LamsonRetail/
├── PLAN.md                     # Kiến trúc & lộ trình
├── README.md
├── .env.example                # Biến môi trường cần cấu hình
├── pyproject.toml / requirements.txt
├── config/
│   └── scoring_config.yaml     # Trọng số & tiêu chí chấm điểm
├── src/rating_agent/
│   ├── config.py               # Nạp env + config chấm điểm
│   ├── pipeline.py             # Điều phối thu thập → chấm điểm → báo cáo
│   ├── lark/                   # Khung client Lark: chat, docs, task
│   ├── bq/                     # Khung client BigQuery + ví dụ query
│   └── evaluation/             # Data model, tiêu chí, scorer
└── tests/                      # Test scorer & config
```

## Trạng thái (MVP)

- [x] Scaffold, config, data model, scorer chạy được với dữ liệu mẫu.
- [x] Khung client Lark (chat/doc/task) và BigQuery.
- [ ] Kết nối nguồn thật (`collect_from_sources`) — giai đoạn 2, cần credential.

## Lưu ý riêng tư & tuân thủ

Agent theo dõi chat/doc/task phục vụ đánh giá công việc. Việc bot tham gia nhóm
chat và thu thập dữ liệu cần được thông báo minh bạch tới nhân viên và tuân thủ
chính sách nội bộ của công ty.
