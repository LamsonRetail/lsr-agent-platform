"""Đồng bộ bảng BigQuery do Data lead chỉ định → tóm tắt → ghi vào Brain RIÊNG của
agent AG-DATA-SUPPORT (không lẫn sang shared brain của agent khác — xem USECASE.md).

Chạy định kỳ (khai báo ở `schedule:` trong ../lsr-agent.yaml), hoặc chạy tay:
    LSR_AGENT_TOKEN=... python3 ingest/bigquery_sync.py

Chỉ ĐỌC BigQuery — không viết ngược lại nguồn (đúng nguyên tắc trong USECASE.md).
Không cấp key BigQuery hộ: đọc từ biến môi trường/Application Default Credentials do
Data lead tự cấu hình (xem .env.example).
"""
import json
import os
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
# Xem chú thích ở ../consumer.py: runtime trên VM tiêm token dưới tên LSR_TELEMETRY_API_KEY,
# nên script chạy theo `schedule:` trong container cũng cần nhận cả hai tên.
TOKEN = os.environ.get("LSR_AGENT_TOKEN") or os.environ.get("LSR_TELEMETRY_API_KEY") or ""
if not TOKEN:
    raise SystemExit("thiếu token agent: đặt LSR_AGENT_TOKEN (chạy tay) "
                     "hoặc LSR_TELEMETRY_API_KEY (runner trên VM tự tiêm)")

# <<< SỬA Ở ĐÂY: danh sách bảng Data lead chỉ định đồng bộ. Mỗi mục = 1 query tóm tắt
# (không kéo raw data đầy đủ vào Brain — chỉ số liệu tổng hợp cần cho câu hỏi thường gặp).
SOURCES = [
    # {
    #     "table": "project.dataset.sales_daily",
    #     "query": "SELECT store, SUM(revenue) AS revenue FROM `project.dataset.sales_daily` "
    #              "WHERE date = CURRENT_DATE() GROUP BY store",
    #     "title": "Doanh số theo kho — hôm nay",
    # },
]


def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        PLATFORM + path, data=data, method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def run_query(sql):
    """<<< SỬA Ở ĐÂY: chạy query BigQuery thật (vd `google-cloud-bigquery` client).

    MVP trả về rows rỗng — chỉ mạch code, không tự ý kết nối BigQuery khi chưa có
    credential/quyền đọc do Data lead cấp.
    """
    return []


def summarize(rows, title):
    if not rows:
        return None
    return "\n".join(f"- {r}" for r in rows)


def main():
    if not SOURCES:
        print("Chưa khai báo nguồn BigQuery nào trong SOURCES — Data lead cần bổ sung trước.")
        return
    n = 0
    for src in SOURCES:
        rows = run_query(src["query"])
        content = summarize(rows, src["title"])
        if not content:
            print(f"⚠ {src['table']}: không có dữ liệu, bỏ qua.")
            continue
        api("POST", "/v1/self/brain/items", {
            "title": src["title"],
            "content": content,
            "source_url": f"bigquery://{src['table']}",
        })
        n += 1
        print(f"✓ đồng bộ {src['table']}")
    print(f"Hoàn tất: {n}/{len(SOURCES)} nguồn.")


if __name__ == "__main__":
    main()
