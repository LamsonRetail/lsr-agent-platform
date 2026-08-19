# Yêu cầu core: User Identity Broker cho Lark (dùng chung toàn platform)

> Người yêu cầu: AG-LEGAL (owner `thint@hapas.vn`) · 19/08/2026
> Mã nội bộ: **C8**. Làm xong C8 thì **C5 (broker Approval) không cần làm nữa** — xem §6.

## 1. Vấn đề

Có những việc Lark **chỉ chấp nhận user token**, tenant/bot token bị API từ chối thẳng.
Đã kiểm live 19/08 với Lark CLI:

| Lệnh | `--as bot` | `--as user` |
|---|---|---|
| `approval approvals search` | ❌ "only supports: user" | ✅ |
| `approval approvals get` | ❌ | ✅ |
| `approval instances get` | ❌ "only supports: user" | ✅ |

Nghĩa là mọi agent muốn tham gia **Lark Approval** (và sau này Task/Docs/Mail ở mức
"làm thay một người") đều cần user token. Nhưng theo chuẩn của platform, **agent không
được tự giữ user token** — nó phải do platform giữ, refresh và audit.

Đây không phải tính năng mới về ý tưởng: `CREATE_AGENT.md` §3.5-B **đã hứa** đúng cơ chế
này ("Callback về platform → đổi authorization code lấy `user_access_token` +
`refresh_token`, **lưu mã hoá ở platform** (không nằm trong repo). Token tự refresh").
Hiện code chưa có. `/v1/auth/lark/start` (`platform_api/app.py:1469`) và
`/v1/auth/lark/callback` (`app.py:1485`) chỉ dùng để **đăng nhập console**: đổi code lấy
`user_access_token` để định danh người rồi **bỏ token đi** (xem chú thích `app.py:1450`,
`app.py:1496`).

## 2. Vì sao phải làm ở platform, không phải từng agent tự làm

1. **Chuẩn**: agent không cầm secret/token của người thật. Đây là mode rủi ro cao nhất
   (hành động dưới danh nghĩa con người) nên phải tập trung để audit được.
2. **Refresh là trạng thái dùng chung**: nhiều agent/tiến trình cùng một account mà tự
   refresh sẽ vô hiệu hoá token của nhau. Platform đã có đúng lớp bug này ở chỗ khác —
   AG-LEGAL từng mất phiên NotebookLM vì hai tiến trình xoay cookie chồng nhau.
3. **Tái dùng**: AG-LEGAL cần Approval ngay; các agent khác sẽ cần Task/Docs/Mail. Làm
   một lần ở platform thì agent sau chỉ cần một dòng grant.
4. **Kill switch**: khi agent bị deactivate phải cắt luôn quyền hành động dưới danh nghĩa
   người — logic đó thuộc platform (đã có pattern ở `_sync_agent_lark`).

## 3. Thiết kế đề xuất

### 3.1 Lưu trữ

```sql
CREATE TABLE lark_user_identities (
  subject_email      text PRIMARY KEY,   -- vd ann_legal@hapas.vn (account của agent)
  open_id            text NOT NULL,
  app_id             text NOT NULL,      -- app OAuth đã dùng để xin quyền
  access_token_enc   bytea NOT NULL,     -- mã hoá at-rest, KHÔNG bao giờ trả ra API
  refresh_token_enc  bytea NOT NULL,
  scope              text NOT NULL,
  expires_at         timestamptz NOT NULL,
  refresh_expires_at timestamptz NOT NULL,
  granted_by         text NOT NULL,      -- admin đã thực hiện authorize
  created_at         timestamptz DEFAULT now(),
  updated_at         timestamptz DEFAULT now()
);

CREATE TABLE agent_user_identity_grants (
  agent_id       text NOT NULL,
  subject_email  text NOT NULL REFERENCES lark_user_identities(subject_email),
  path_prefixes  text[] NOT NULL,   -- vd '{/open-apis/approval/v4/}'
  active         boolean NOT NULL DEFAULT true,
  granted_by     text NOT NULL,
  PRIMARY KEY (agent_id, subject_email)
);
```

Khoá mã hoá lấy từ env trên VM (`LARK_USER_TOKEN_KEY`), cùng cách secret app Lark đang
được quản (`_LARK_APPS`, `app.py:95-105` + `scripts/add-lark-app.sh`).

### 3.2 Luồng authorize (bắt buộc có người, chỉ admin)

- `GET /v1/lark/user/authorize/start?subject=<email>&domains=approval,task`
  → trả URL authorize của Lark (kèm `offline_access`). Admin mở, **đăng nhập bằng đúng
  account đó**, bấm đồng ý.
- `POST /v1/lark/user/authorize/callback` → đổi code, ghi `lark_user_identities`.
- `POST /v1/lark/user/authorize/device` → **biến thể device flow** (trả
  `verification_url` + `user_code`, poll bằng `device_code`). Cần vì account của agent
  thường không có phiên browser sẵn trên máy admin. Lark CLI đã làm đúng kiểu này, có thể
  tham chiếu.

### 3.3 Tự refresh

Job nền refresh trước `expires_at`. Quan trọng: **khi `refresh_expires_at` gần hết mà
chưa ai authorize lại → cảnh báo owner + admin**. Nếu không, token chết âm thầm và agent
degrade không rõ nguyên nhân — AG-LEGAL đã trải qua đúng chuyện này (refresh token hết
hạn 17/07, phát hiện ra ngày 19/08).

### 3.4 Endpoint cho agent — một proxy, không phải N endpoint

```
POST /v1/lark/user/call
  auth: _require_self  +  _require_connector(agent, "lark_user")  +  grant kiểm path
  body: {subject, method, path, query?, body?}
  → gọi Lark bằng user token của subject, trả nguyên response
  → 403 nếu: chưa có grant · path ngoài path_prefixes · identity đã revoke

GET /v1/lark/user/status?subject=<email>
  → {connected, scope, expires_at, refresh_expires_at}   (KHÔNG trả token)
```

**Đây là điểm thiết kế quan trọng nhất**: một proxy có allowlist path thay vì viết riêng
endpoint cho từng nhóm API. Thêm Approval hôm nay, Task/Docs tháng sau → **chỉ thêm một
dòng grant, không sửa core**. Ngược lại nếu làm endpoint riêng cho Approval thì mỗi nhóm
API mới lại là một PR core mới.

`GET /v1/lark/user/status` cần thiết để agent **degrade rõ ràng** thay vì lỗi mù — cùng
lý do AG-LEGAL có `brain.available()` cảnh báo khi thiếu CLI `claude`.

### 3.5 Audit & metering

Mỗi lời gọi proxy: `_audit(agent_id, "lark_user_call", subject, {path, method})` +
`_meter(...)` — giống `/v1/lark/resource` đang làm (`app.py:2979`). Hành động dưới danh
nghĩa một con người thì phải dựng lại được ai-làm-gì-lúc-nào.

### 3.6 Thu hồi

- `POST /v1/lark/user/identities/{subject}/revoke` (admin) → xoá token + tắt grants.
- Agent `status=deactivated` → tự tắt grants của agent đó.

### 3.7 Caddy

Thêm `/v1/lark/user/*` vào `@selfserve` (`caddy/Caddyfile:38`) để agent gọi được từ
ngoài, **trừ** `authorize/*` và `revoke` (admin-only, giữ trong console).

## 4. Tiêu chí nghiệm thu

- [ ] AG-LEGAL có grant `subject=ann_legal@hapas.vn`, `path_prefixes={/open-apis/approval/v4/}`
      → `GET` instance và `POST` comment chạy được, **agent không hề thấy token**.
- [ ] Agent **không** có grant → 403 kèm thông báo rõ lý do.
- [ ] Path ngoài allowlist (vd `/open-apis/im/v1/messages`) → 403.
- [ ] Token hết hạn giữa lúc dùng → tự refresh, lời gọi không gián đoạn.
- [ ] `refresh_expires_at` sắp hết → owner + admin nhận cảnh báo **trước khi** chết.
- [ ] Revoke → lời gọi ngay sau đó 403.
- [ ] Audit log có `agent_id` + `subject` + `path` cho mọi lời gọi.
- [ ] Token **không** xuất hiện trong bất kỳ response, log hay bảng nào ở dạng rõ.

## 5. Chính sách cần chốt trước khi bật

`CREATE_AGENT.md` §3.5-B đã ghi: dùng user account cần **review ToS Lark + chính sách nội
bộ**. Đề nghị chốt hai điều trước khi có grant đầu tiên:

1. Agent hành động dưới danh nghĩa account **riêng cho agent** (vd `ann_legal@hapas.vn`),
   **không dùng account của người thật** — để log Lark phân biệt được người và máy.
2. Người trong nhóm liên quan được **thông báo minh bạch** rằng có một account máy tham
   gia quy trình.

## 6. Vì sao làm C8 thì bỏ được C5

Yêu cầu C5 ban đầu là "broker Lark Approval": gateway chuyển tiếp approval event + hai
endpoint đọc instance/ghi comment. Sau khi kiểm ra API Approval là user-token-based, phần
đọc/ghi của C5 **chính là** `POST /v1/lark/user/call` với path `/open-apis/approval/v4/*`
— không cần code riêng cho Approval.

Còn lại **một phần nhỏ** của C5 vẫn cần, độc lập với C8:

> `event_gateway/gateway.py`, hàm `webhook_lark()` hiện chỉ đọc `event.message` nên
> **approval event bị bỏ im lặng**. Cần đọc `header.event_type`, với `approval_instance`
> thì đẩy sang `/v1/ingest` với `channel="lark_approval"` + payload mang `instance_code`,
> `approval_code`, `status`. Kèm cho `routing_binding` khớp theo `approval_code` (dùng lại
> cột `chat_id` là đủ, không cần cột mới).

Tức thứ tự đúng: **C8 trước** (mở khoá đọc/ghi), rồi **mảnh event nhỏ** ở trên (mở khoá
tự động hoá theo sự kiện). Làm C5 kiểu cũ trước C8 là xây trên nền không có.

## 7. Phía AG-LEGAL đã sẵn sàng

Không cần core làm gì thêm cho phần nghiệp vụ:

- `approval_code = 0338BCF9-2E4C-45E1-9A77-3CAEE6FAE369` ("Review và phê duyệt hợp đồng").
- 4 widget id của form đã ghim + `parse_form()` trong `legalkb/signing.py`.
- Logic Bước 3 / Bước 5, phân mức `high|medium|low`, SLA 30' `auto_passed`, chống vòng
  lặp — đã code xong, có test.
- Có C8 + mảnh event thì AG-LEGAL chỉ đổi phần vào/ra, không viết lại nghiệp vụ.

Lưu ý về workflow thật: nó chỉ có **4 node (Submit → Approval → Approval → End)**, tức 2
bước duyệt, không phải 6 bước như tài liệu nghiệp vụ mô tả; hai node đều tên chung
"Approval" nên **không phân biệt được** Pháp chế với Tài chính/Nhân sự từ định nghĩa. Việc
này thuộc nghiệp vụ (sửa định nghĩa trên Lark), không thuộc core.
