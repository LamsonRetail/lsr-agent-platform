"""Sample data cho prototype LSR Agent Platform (platform + backend từng agent).

Bổ sung phần config/schedule/logs cho mỗi agent — thứ sẽ nằm trên backend Vercel
riêng của agent. Khi nối thật, thay bằng dữ liệu từ Platform API + collector.
"""

from __future__ import annotations

# Backend riêng của từng agent (chạy trên Vercel, chỉ owner sửa config).
AGENT_BACKEND: dict[str, dict] = {
    "AG-ORDER-BOT": {
        "primary_squad": "SQ-SALES",
        "model": "claude-sonnet-5",
        "system_prompt": (
            "Bạn là trợ lý tra cứu đơn hàng cho đội Sales HN của LamsonRetail.\n"
            "- Luôn tra BigQuery trước khi trả lời số liệu đơn.\n"
            "- Trả lời ngắn gọn, kèm mã đơn và trạng thái.\n"
            "- Không bịa dữ liệu; nếu không có, nói rõ."
        ),
        "skills": ["bigquery", "lark-task", "lark-chat"],
        "schedule": [
            {"name": "Báo cáo doanh thu ngày", "cron": "0 8 * * *",
             "next": "2026-08-06 08:00", "enabled": True},
            {"name": "Nhắc đơn treo > 3 ngày", "cron": "0 9 * * 1-5",
             "next": "2026-08-06 09:00", "enabled": True},
        ],
        "logs": [
            {"time": "08-05 09:12", "user": "Nguyễn An", "action": "tra đơn #A1023",
             "tokens": 820, "status": "ok"},
            {"time": "08-05 08:40", "user": "Trần Bình", "action": "tổng đơn hôm qua",
             "tokens": 1150, "status": "ok"},
            {"time": "08-05 08:05", "user": "cron", "action": "Báo cáo doanh thu ngày",
             "tokens": 2600, "status": "ok"},
        ],
    },
    "AG-KPI-BOT": {
        "primary_squad": "SQ-SALES",
        "model": "claude-sonnet-5",
        "system_prompt": (
            "Bạn là trợ lý phân tích KPI. Tổng hợp số liệu từ BigQuery và giải thích "
            "xu hướng cho quản lý squad. Nêu rõ nguồn và kỳ dữ liệu."
        ),
        "skills": ["bigquery"],
        "schedule": [
            {"name": "Tổng hợp KPI tuần", "cron": "0 7 * * 1",
             "next": "2026-08-10 07:00", "enabled": True},
        ],
        "logs": [
            {"time": "08-05 10:01", "user": "Vũ Minh", "action": "phân tích KPI T7",
             "tokens": 2100, "status": "ok"},
            {"time": "08-04 16:20", "user": "Nguyễn An", "action": "so sánh 2 tháng",
             "tokens": 1800, "status": "warn"},
        ],
    },
    "AG-CHAT-HELPER": {
        "primary_squad": "SQ-OPS",
        "model": "claude-haiku-4-5",
        "system_prompt": (
            "Bạn trả lời tự động câu hỏi vận hành trong nhóm chat. Nếu không chắc, "
            "chuyển cho người phụ trách thay vì đoán."
        ),
        "skills": ["lark-chat", "lark-doc"],
        "schedule": [],
        "logs": [
            {"time": "08-05 07:55", "user": "cron", "action": "test định kỳ",
             "tokens": 300, "status": "fail"},
            {"time": "08-04 14:10", "user": "Đỗ Hoa", "action": "hỏi quy trình đổi trả",
             "tokens": 640, "status": "warn"},
        ],
    },
}
