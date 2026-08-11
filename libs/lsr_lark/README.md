# lsr_lark — tích hợp Lark dùng chung cho agent LSR

Tạo agent mới **không phải viết lại** phần Lark, và mọi agent tương tác Lark **đồng bộ**
(chung tenant token + chung danh bạ open_id + chung định dạng + audit tập trung).

## Vì sao
Trước đây mỗi agent tự: lấy `tenant_access_token`, resolve `email→open_id` (kèm fallback
`enterprise_email` + duyệt phòng ban), rồi gọi `im/v1/messages`. Logic này từng bị lặp ở
4 nơi. `lsr_lark` gom lại một chỗ.

## Hai chế độ
| Chế độ | Ai dùng | Giữ app_secret? | Cách đồng bộ |
|---|---|---|---|
| **remote** (mặc định cho agent) | mọi agent | ❌ không | gọi broker `platform_api /v1/lark/*`; token + danh bạ cache chung ở Postgres |
| **direct** | dịch vụ lõi / bot long-connection | ✅ có | gọi thẳng Lark; cache qua `PostgresStore` (chung bảng với platform) |

## Dùng nhanh (agent — remote)
Chỉ cần 2 env đã có sẵn khi enroll: `LSR_PLATFORM_URL`, `LSR_AGENT_TOKEN`
(hoặc `LSR_TELEMETRY_API_KEY`).

```python
from lsr_lark import Lark

lark = Lark()                                   # tự chọn remote
lark.send("thint@hapas.vn", "Báo cáo tuần đã xong ✅")
lark.send_markdown("ngadt@hapas.vn", "**KPI hôm nay**\n- Doanh thu: 1.2 tỷ")
lark.send("oc_xxx", "Cập nhật nhóm", to_type="chat_id")
open_id = lark.resolve("anhkt@hapas.vn")        # dùng danh bạ chung
for c in lark.chats():                          # nhóm bot đang tham gia
    print(c["chat_id"], c["name"])
```
Lỗi mạng mặc định **no-op êm** (không làm hỏng agent). Muốn bắt lỗi: `Lark(raise_on_error=True)`.

## Dùng cho dịch vụ lõi (direct)
```python
from lsr_lark import Lark
from lsr_lark.store import PostgresStore
import psycopg

store = PostgresStore(lambda: psycopg.connect(DB_URL))   # cache chung với platform
lark = Lark("direct", store=store)                        # cần LARK_APP_ID/SECRET
lark.send("thint@hapas.vn", "hello")
```

## Broker API (khi không dùng Python)
Gọi trực tiếp bằng agent token:
- `POST /v1/lark/send` — `{to, to_type?: email|open_id|chat_id, text?|markdown?}`
- `POST /v1/lark/resolve` — `{email}` → `{open_id}`
- `GET  /v1/lark/chats` — nhóm bot đang tham gia
