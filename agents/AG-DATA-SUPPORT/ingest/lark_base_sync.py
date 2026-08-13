"""Đồng bộ bảng Lark Base do Data lead chỉ định → tóm tắt → ghi vào Brain RIÊNG của
agent AG-DATA-SUPPORT (không lẫn sang shared brain của agent khác — xem USECASE.md).

Chạy định kỳ (khai báo ở `schedule:` trong ../lsr-agent.yaml), hoặc chạy tay:
    LSR_AGENT_TOKEN=... python3 ingest/lark_base_sync.py

Chỉ ĐỌC Lark Base (qua connector `lark` dùng chung của platform) — không viết ngược
lại bảng nguồn.
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

# <<< SỬA Ở ĐÂY: danh sách bảng Lark Base Data lead chỉ định đồng bộ.
SOURCES = [
    # {"app_token": "...", "table_id": "...", "title": "Quy trình xử lý đơn — Data squad"},
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


def fetch_lark_base_records(app_token, table_id):
    """<<< SỬA Ở ĐÂY: gọi connector Lark Base có sẵn của platform để đọc bảng thật.

    MVP trả rỗng — không tự kết nối khi chưa có quyền do Data lead cấp.
    """
    return []


def summarize(records, title):
    if not records:
        return None
    return "\n".join(f"- {r}" for r in records)


def main():
    if not SOURCES:
        print("Chưa khai báo nguồn Lark Base nào trong SOURCES — Data lead cần bổ sung trước.")
        return
    n = 0
    for src in SOURCES:
        records = fetch_lark_base_records(src["app_token"], src["table_id"])
        content = summarize(records, src["title"])
        if not content:
            print(f"⚠ {src['title']}: không có dữ liệu, bỏ qua.")
            continue
        api("POST", "/v1/self/brain/items", {
            "title": src["title"],
            "content": content,
            "source_url": f"lark-base://{src['app_token']}/{src['table_id']}",
        })
        n += 1
        print(f"✓ đồng bộ {src['title']}")
    print(f"Hoàn tất: {n}/{len(SOURCES)} nguồn.")


if __name__ == "__main__":
    main()
