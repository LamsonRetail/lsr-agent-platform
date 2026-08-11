# Gắn telemetry cho bot tự host (custom Python/Node)

Áp dụng cho agent `connect_mode=bot`, team tự chạy trên máy riêng (vd **AG-BI — Nga BI Agent**).
Bot loại này KHÔNG chạy qua Claude Code plugin, nên platform chỉ có số liệu khi bot **tự POST trace**
về collector sau mỗi lần chạy.

## Thông số
- Collector: `https://collector.34-126-154-135.sslip.io`
- Endpoint: `POST /v1/traces`
- Auth: header `Authorization: Bearer <TELEMETRY_KEY>` (key cấp lúc enroll — AG-BI đã có)
- `agent_id` **bắt buộc** = `AG-BI` (đây là thứ gán trace về đúng agent trên dashboard)

## 0. Smoke test (5 giây — xác nhận đường ống thông)
```bash
curl -s https://collector.34-126-154-135.sslip.io/v1/traces \
  -H "Authorization: Bearer <TELEMETRY_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"smoke-1","agent_id":"AG-BI","source":"bi-bot","final_output":"hello"}'
# Kỳ vọng: {"ok":true,...}. Nếu 401 = sai key; 403 = agent bị deactivate.
```
Gửi xong mở `https://app.34-126-154-135.sslip.io/` (hoặc `/cost`) sẽ thấy AG-BI có số liệu.

## 1. Payload schema (các field collector đọc)
| field | kiểu | ý nghĩa |
|---|---|---|
| `run_id` | str | ID mỗi lần chạy (nên unique, vd uuid) |
| `agent_id` | str | **"AG-BI"** — bắt buộc |
| `task_id` | str | (tuỳ chọn) mã tác vụ/câu hỏi BI |
| `source` | str | (tuỳ chọn) vd "bi-bot" |
| `llm_calls` | list | `[{input_tokens, output_tokens}]` → cộng ra token |
| `tool_calls` | list | `[{ok: bool, ...}]` → đếm số tool + suy ra lỗi |
| `final_output` | str | kết quả cuối (tự động che PII trước khi lưu) |
| `status` | str | "ok"/"error" (nếu bỏ trống, tự suy) |
| `error` | str | mô tả lỗi nếu có |
| `started_at`/`finished_at` | ISO8601 | để tính duration (hoặc gửi thẳng `duration_ms`) |

## 2. Python — drop-in
```python
import os, time, uuid, json, urllib.request

COLLECTOR = "https://collector.34-126-154-135.sslip.io"
KEY = os.environ["LSR_TELEMETRY_API_KEY"]  # nạp từ .env.lsr đang có
AGENT_ID = "AG-BI"

def send_trace(*, task_id=None, llm_calls=None, tool_calls=None,
               final_output="", error=None, started_at=None):
    body = {
        "run_id": uuid.uuid4().hex,
        "agent_id": AGENT_ID,
        "task_id": task_id,
        "source": "bi-bot",
        "llm_calls": llm_calls or [],       # [{"input_tokens":123,"output_tokens":45}]
        "tool_calls": tool_calls or [],     # [{"ok":True,"name":"run_sql"}]
        "final_output": final_output,
        "status": "error" if error else "ok",
        "error": error or "",
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    req = urllib.request.Request(
        COLLECTOR + "/v1/traces",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        method="POST",
    )
    try:  # best-effort: đừng để telemetry làm hỏng bot
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        print("trace failed:", e); return None

# Gọi ở cuối mỗi lượt bot xử lý:
# send_trace(task_id="q-lợi-nhuận-t7", final_output=answer,
#            llm_calls=[{"input_tokens":in_tok,"output_tokens":out_tok}],
#            tool_calls=[{"ok":True,"name":"bigquery"}])
```

## 3. Node — drop-in
```js
const COLLECTOR = "https://collector.34-126-154-135.sslip.io";
const KEY = process.env.LSR_TELEMETRY_API_KEY;
const AGENT_ID = "AG-BI";

export async function sendTrace({ taskId, llmCalls = [], toolCalls = [],
                                  finalOutput = "", error = null, startedAt = null } = {}) {
  const body = {
    run_id: crypto.randomUUID(),
    agent_id: AGENT_ID,
    task_id: taskId,
    source: "bi-bot",
    llm_calls: llmCalls,          // [{input_tokens, output_tokens}]
    tool_calls: toolCalls,        // [{ok:true, name:"run_sql"}]
    final_output: finalOutput,
    status: error ? "error" : "ok",
    error: error || "",
    started_at: startedAt,
    finished_at: new Date().toISOString(),
  };
  try {
    const r = await fetch(`${COLLECTOR}/v1/traces`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${KEY}` },
      body: JSON.stringify(body),
    });
    return await r.json();
  } catch (e) { console.error("trace failed", e); return null; } // best-effort
}
```

## Lưu ý
- Gọi `send_trace` **1 lần ở cuối mỗi lượt** bot trả lời (không cần từng bước).
- `final_output` được collector **tự động che PII** (email/thẻ/điện thoại/CCCD) trước khi lưu.
- Muốn platform có cả **policy runtime** (chặn tool nguy hiểm) thì thêm `POST /v1/policy/check`
  trước khi chạy tool — không bắt buộc cho BI bot chỉ đọc dữ liệu.
- Sau khi có trace ổn định, đổi `status` của AG-BI sang `golive` để lên bảng theo dõi chính thức.
