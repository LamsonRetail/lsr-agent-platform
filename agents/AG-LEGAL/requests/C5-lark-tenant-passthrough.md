# C5 — Passthrough Lark bằng **tenant token** (có allowlist), kiểu C8

> Người yêu cầu: AG-LEGAL (owner `thint@hapas.vn`) · 20/08/2026
> Thay thế hoàn toàn mô tả C5 cũ ("broker Approval"). **Lý do thay: kết luận cũ sai** —
> xem phần "Đo lại" dưới.

## Một câu

C8 đã cho agent gọi Lark bằng **user token** qua `/v1/lark/user/call`. Xin thêm **đúng một
endpoint song song** cho **tenant token**: `POST /v1/lark/call` với cùng cơ chế allowlist +
audit. Không cần thêm N endpoint cho từng nhóm API.

## Đo lại (20/08/2026) — sửa một kết luận sai của chính chúng tôi

PLAN AG-LEGAL §11 từng ghi: *"API Approval là user-token-based ⇒ C5 phụ thuộc C8"*. Sai.
Gọi **cùng một endpoint** bằng hai loại token:

| Endpoint | user token (qua C8) | tenant token (app riêng của AG-LEGAL) |
|---|---|---|
| `GET /approval/v4/tasks?topic=1` | ✅ `code:0` | — |
| `GET /approval/v4/approvals/{code}` | ❌ `99991668 user access token not support` | ⚠️ `99991672` **thiếu scope** |
| `GET /approval/v4/instances/{code}` | ❌ `99991668` | ⚠️ `99991672` **thiếu scope** |

`99991672 Access denied. One of the following scopes is required:
[approval:approval:readonly, approval:approval, approval:instance]` là lỗi **cấu hình
scope**, không phải lỗi loại token. Nghĩa là **tenant token đúng loại**.

Chỗ đọc nhầm lần trước: `lark-cli --as bot` dùng **app_access_token**, và Lark trả
"only supports: user" cho loại đó. `app_access_token` ≠ `tenant_access_token`.

⇒ Phần lớn Approval là **tenant**; user token chỉ dùng được cho view "việc đang chờ tôi".

## Xin gì, cụ thể

### 1. `POST /v1/lark/call` — passthrough tenant token

```
POST /v1/lark/call
{ "app_id": "cli_...",              # tuỳ chọn; rỗng = app mặc định của agent
  "method": "GET",
  "path":   "/open-apis/approval/v4/instances/{code}?locale=vi-VN",
  "body":   {...} }                 # tuỳ chọn
→ { "http_status": 200, "data": <nguyên response Lark> }
```

Cùng 6 lớp kiểm như `/v1/lark/user/call` (`_require_self` → connector enforce → grant còn
active → path/method ∈ allowlist → token → audit + meter). Grant khai bằng
`path_prefixes` + `methods`, để mở thêm nhóm API sau này **là thêm một dòng grant, không
phải PR vào core** — đúng tinh thần C8.

Xin cho AG-LEGAL: `path_prefixes: ["/open-apis/approval/v4/"]`, `methods: ["GET","POST"]`.

### 2. Scope `approval:approval` cho app Lark mà AG-LEGAL dùng

Hiện app đang dùng chỉ có scope Wiki/Drive. Cần thêm trên Lark Developer Console:
`approval:approval` (hoặc `approval:approval:readonly` + `approval:instance`), rồi
**Create version & publish**.

Việc này **không phải core làm** — là việc của admin Lark. Ghi ở đây để hai bên không chờ nhau.

## Vì sao không tự làm trong agent

Tự gọi `open.larksuite.com` bằng `app_secret` là vi phạm chuẩn §2.3 ("mọi tương tác Lark
qua platform"). AG-LEGAL đã có **một** ngoại lệ được ghi chú cho Wiki/Drive (C1) vì broker
chưa có; không mở rộng thêm ngoại lệ nữa. `POST /v1/lark/call` **cũng đóng luôn C1** — sau
đó `lark_kb.py` bỏ được `app_secret`.

## Chặn cái gì

| Việc | Trạng thái hôm nay |
|---|---|
| Agent biết có hồ sơ trình ký đang chờ | ✅ chạy được (C8, `tasks?topic=1`) |
| Đọc form + file đính kèm của hồ sơ | ⛔ chặn — cần C5 |
| Ghi báo cáo Bước 3/Bước 5 vào instance | ⛔ chặn — cần C5. Tạm gửi vào group qua bot |
| Bỏ `app_secret` khỏi `lark_kb.py` (đóng C1) | ⛔ chặn — cần C5 |

## Ưu tiên

Trung bình. S5 đã chạy được phần phát hiện + báo cáo vào group, nên **không chặn golive**.
Nhưng C5 là thứ duy nhất còn lại để S5 gắn vào quy trình chính thức, và nó đóng luôn C1 —
tức bỏ được ngoại lệ `app_secret` cuối cùng của AG-LEGAL.
