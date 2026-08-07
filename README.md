# Rating Agent — LamsonRetail

Hệ thống nội bộ đánh giá **hai đối tượng tách biệt**:

- **Squad** (đội người) — chấm theo **hiệu quả mục tiêu** (Key Result achievement + đúng tiến độ).
- **Agent** (AI/software agent) — chấm theo **skill / mức độ sử dụng / kết quả trả về**, kèm **test tự động** và cổng **auto-deactivate** khi fail.

Dữ liệu lấy từ **Lark** (Base, chat, doc, task) và **BigQuery** data warehouse.

> - **Thành viên muốn tự tạo agent** (plugin hoặc git): [ONBOARDING.md](ONBOARDING.md).
> - Kiến trúc, nguồn dữ liệu, tiêu chí, màn hình, lộ trình: [PLAN.md](PLAN.md).
> - Cấu trúc master data trên Lark Base (đang chờ confirm): [MASTER_DATA.md](MASTER_DATA.md).
> - Tích hợp/giám sát agent VPS↔Lark, token, log, đo 6 chỉ số tool: [AGENT_INTEGRATION.md](AGENT_INTEGRATION.md).

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
# Điền LARK_APP_ID/SECRET, LARK_BASE_APP_TOKEN và thông tin BigQuery.
```

Xem danh sách biến môi trường trong [.env.example](.env.example).

## Chạy demo (dữ liệu mẫu, không cần credential)

```bash
python -m rating_agent.pipeline
```

Kết quả: **Squad Scoreboard** + **Agent Leaderboard**, trong đó có 1 agent mẫu
fail test 2 lần liên tiếp và bị khuyến nghị `deactivate`.

## Sinh prototype dashboard (6 màn hình)

```bash
python -m rating_agent.reporting.dashboard
```

Tạo `output/dashboard.html` — trang HTML self-contained (mở bằng trình duyệt),
gồm: Squad Scoreboard, Squad Detail, Agent Registry, Agent Detail, Agent Test
Dashboard, Agent Leaderboard. Có sidebar điều hướng và nút đổi giao diện
sáng/tối. Dữ liệu điểm lấy từ scorer thật + dữ liệu mẫu.

## Chạy test

```bash
pytest
```

## Cấu trúc thư mục

```
RatingAgent-LamsonRetail/
├── PLAN.md                       # Kiến trúc, nguồn dữ liệu, tiêu chí, màn hình, lộ trình
├── MASTER_DATA.md                # Schema Lark Base (chờ confirm)
├── README.md
├── .env.example
├── config/
│   └── scoring_config.yaml       # Trọng số 2 nhánh + chính sách deactivate
├── src/rating_agent/
│   ├── config.py                 # Nạp env + config chấm điểm
│   ├── pipeline.py               # Điều phối 2 nhánh → báo cáo
│   ├── lark/                     # Client Lark: base, chat, docs, task
│   ├── bq/                       # Client BigQuery + ví dụ query
│   ├── evaluation/               # models, criteria, squad_scorer, agent_scorer
│   ├── agent_testing/            # runner test agent + assertion + gate
│   ├── telemetry/                # trace + đo 6 chỉ số hành vi tool + token + SDK
│   └── reporting/                # sinh prototype dashboard HTML (6 màn hình)
└── tests/                        # test_scorer, test_config, test_agent_testing, test_reporting, test_metrics
```

## Trạng thái (MVP)

- [x] Hai nhánh scorer (squad/agent) chạy với dữ liệu mẫu.
- [x] Module test agent: runner, assertion, chính sách auto-deactivate.
- [x] Khung client Lark (base/chat/doc/task) và BigQuery.
- [x] Prototype 6 màn hình đánh giá (HTML) — `rating_agent.reporting`.
- [ ] Kết nối nguồn thật (`collect_*_from_sources`) — sau khi confirm master data.

## Lưu ý riêng tư & tuân thủ

Agent theo dõi chat/doc/task và dữ liệu vận hành phục vụ đánh giá công việc. Việc
bot tham gia nhóm chat và thu thập dữ liệu cần được thông báo minh bạch tới nhân
viên và tuân thủ chính sách nội bộ của công ty.
