"""Sample master data phục vụ prototype dashboard.

Đây là dữ liệu minh hoạ cho phần "hiện vật" chưa nằm trong scorer (link, thành
viên, registry agent, lịch sử test, xu hướng usage). Khi cắm Lark Base thật, thay
các dict này bằng record đọc từ Base.
"""

from __future__ import annotations

# --- Squad: link + nhân sự (bổ sung cho SquadMetrics) ---
SQUAD_MASTER: dict[str, dict] = {
    "SQ-SALES": {
        "lead": "Nguyễn An",
        "members": ["Nguyễn An", "Trần Bình", "Lê Chi", "Phạm Dũng"],
        "description": "Đội bán hàng khu vực Hà Nội",
        "links": {
            "Nhóm chat": "https://lark.example/chat/sales-hn",
            "Tasklist": "https://lark.example/task/sales-hn",
            "Drive báo cáo": "https://lark.example/drive/sales-hn",
            "Dashboard": "https://lark.example/dashboard/sales-hn",
            "Plan": "https://lark.example/doc/plan-sales-hn",
        },
    },
    "SQ-OPS": {
        "lead": "Vũ Minh",
        "members": ["Vũ Minh", "Đỗ Hoa", "Bùi Long"],
        "description": "Đội vận hành kho & giao hàng",
        "links": {
            "Nhóm chat": "https://lark.example/chat/ops",
            "Tasklist": "https://lark.example/task/ops",
            "Drive báo cáo": "https://lark.example/drive/ops",
            "Dashboard": "https://lark.example/dashboard/ops",
            "Plan": "https://lark.example/doc/plan-ops",
        },
    },
}

# --- Agent registry (bảng agents) ---
AGENT_REGISTRY: dict[str, dict] = {
    "AG-ORDER-BOT": {
        "version": "1.4.2",
        "owner": "Team Data",
        "served_squads": ["Sales HN", "Vận hành"],
        "skills": ["Tra cứu đơn", "Tóm tắt"],
        "data_sources": ["lark_chat", "bigquery"],
        "status": "active",
        "registered_at": "2026-05-10",
        "golive_at": "2026-05-18",
        "last_test_status": "pass",
        "last_test_at": "2026-07-28",
    },
    "AG-KPI-BOT": {
        "version": "0.9.0",
        "owner": "Team BI",
        "served_squads": ["Sales HN"],
        "skills": ["Phân tích KPI"],
        "data_sources": ["bigquery"],
        "status": "active",
        "registered_at": "2026-06-20",
        "golive_at": "2026-06-25",
        "last_test_status": "pass",
        "last_test_at": "2026-07-27",
    },
    "AG-CHAT-HELPER": {
        "version": "2.0.1",
        "owner": "Team CS",
        "served_squads": ["Vận hành"],
        "skills": ["Trả lời tự động"],
        "data_sources": ["lark_chat", "lark_doc"],
        "status": "active",  # sẽ bị khuyến nghị deactivate
        "registered_at": "2026-04-01",
        "golive_at": "2026-04-08",
        "last_test_status": "fail",
        "last_test_at": "2026-07-29",
    },
    "AG-DRAFT-BOT": {
        "version": "0.1.0",
        "owner": "Team Data",
        "served_squads": ["Sales HN"],
        "skills": ["Soạn báo giá"],
        "data_sources": ["bigquery"],
        "status": "registered",  # chưa golive — đang chờ pass test
        "registered_at": "2026-07-25",
        "golive_at": "",
        "last_test_status": "-",
        "last_test_at": "",
    },
    "AG-MINH-ANH": {  # Meeting agent nền tảng
        "version": "0.1.0",
        "owner": "Platform",
        "served_squads": ["Toàn bộ"],
        "skills": ["Biên bản họp", "Transcript", "Tạo task"],
        "data_sources": ["lark_minutes", "lark_task", "resource_index"],
        "status": "active",
        "registered_at": "2026-08-05",
        "golive_at": "2026-08-05",
        "last_test_status": "pass",
        "last_test_at": "2026-08-05",
    },
}

# --- Xu hướng usage theo tuần (Agent Detail) ---
USAGE_TREND: dict[str, list[int]] = {
    "AG-ORDER-BOT": [210, 245, 260, 240, 300, 320, 305],
    "AG-KPI-BOT": [40, 55, 60, 48, 62, 70, 65],
    "AG-CHAT-HELPER": [80, 60, 45, 30, 25, 20, 15],
}

# --- Lịch sử test theo thời gian (Agent Detail) ---
# (ngày, pass?) — mới nhất ở cuối
TEST_HISTORY: dict[str, list[tuple[str, bool]]] = {
    "AG-ORDER-BOT": [("07-01", True), ("07-08", True), ("07-15", True),
                     ("07-22", True), ("07-28", True)],
    "AG-KPI-BOT": [("07-01", True), ("07-08", False), ("07-15", True),
                   ("07-22", True), ("07-27", True)],
    "AG-CHAT-HELPER": [("07-08", True), ("07-15", True), ("07-22", False),
                       ("07-29", False)],
}

# --- Lần chạy test gần đây (Agent Test Dashboard) ---
RECENT_TEST_RUNS: list[dict] = [
    {"run_at": "2026-07-29 06:00", "agent": "Chat Helper Bot", "skill": "Trả lời tự động",
     "test": "Phản hồi FAQ #7", "status": "fail", "latency_ms": 3600, "trigger": "scheduled"},
    {"run_at": "2026-07-29 06:00", "agent": "Chat Helper Bot", "skill": "Trả lời tự động",
     "test": "Phản hồi FAQ #3", "status": "fail", "latency_ms": 3400, "trigger": "scheduled"},
    {"run_at": "2026-07-28 06:00", "agent": "Order Lookup Bot", "skill": "Tra cứu đơn",
     "test": "Tra mã đơn hợp lệ", "status": "pass", "latency_ms": 780, "trigger": "scheduled"},
    {"run_at": "2026-07-27 06:00", "agent": "KPI Insight Bot", "skill": "Phân tích KPI",
     "test": "Tổng doanh thu tháng", "status": "pass", "latency_ms": 2100, "trigger": "scheduled"},
    {"run_at": "2026-07-25 09:12", "agent": "Draft Bot", "skill": "Soạn báo giá",
     "test": "Sinh báo giá mẫu", "status": "fail", "latency_ms": 1500, "trigger": "pre_golive"},
]
