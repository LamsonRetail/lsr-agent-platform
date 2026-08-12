# Kế hoạch P8 + P9 — Tài khoản/Phân quyền & Tạo agent no-code trên console

> Trạng thái: **kế hoạch, chưa build** — chờ duyệt.
> Nối tiếp lộ trình P1–P7 (đã xong, xem [PLAN.md](../PLAN.md) §0).

---

## 0. Hiện trạng & khoảng trống

| Việc | Hiện tại | Vấn đề |
|---|---|---|
| Đăng nhập console | **Chỉ 1 basic-auth dùng chung** (`lamson`) ở Caddy | Không biết ai đang thao tác; ai có mật khẩu đều toàn quyền |
| Danh tính trong audit | `X-Actor` = hằng số `web-admin` | Audit **ghi cùng một tên cho mọi người** → không truy được trách nhiệm |
| Phân quyền | Không có | Không thể cho moderator/user vào console |
| Quyền theo agent | Không có | Không thể "moderator của riêng AG-BI" |
| Tạo agent | Bắt buộc CLI (`new-agent.sh` + enroll) | Người không kỹ thuật không tạo được |
| Agent no-code chạy bằng gì | Chưa có runtime | Tạo xong không có gì chạy nó |

**Nguyên tắc thiết kế bắt buộc:** quyền phải được **kiểm ở platform_api**, không chỉ ẩn/hiện nút trên UI.
Hiện web đang cầm `PLATFORM_ADMIN_TOKEN` và gọi API thay người dùng — nếu chỉ sửa UI thì
moderator/user vẫn có thể gọi thẳng API. P8 phải chuyển sang **API tự nhận diện người gọi**.

---

## 1. Mô hình phân quyền

### 1.1 Vai trò

| Vai trò | Ý nghĩa |
|---|---|
| `admin` | Toàn quyền: duyệt publish, quản tài khoản, credential, connector, kill-switch |
| `moderator` | Tạo agent, sửa config agent mình phụ trách, **publish phải được admin duyệt** |
| `user` | **Chỉ xem**: dashboard, config agent, KPI. Không sửa gì |

### 1.2 Phạm vi (scope)

- **Platform scope** — áp cho mọi agent (vd: `thienlq@` là `moderator` toàn platform).
- **Agent scope** — áp cho đúng 1 agent (vd: `ngadt@` là `moderator` của riêng `AG-BI`).

**Quyền hiệu lực trên một agent = quyền cao hơn giữa (platform role, agent role).**
Ai không có binding nào → không vào được console.

### 1.3 Ma trận quyền (API enforce)

| Hành động | user | moderator | admin |
|---|:--:|:--:|:--:|
| Xem dashboard, KPI, cost, health | ✅ | ✅ | ✅ |
| Xem config/version/brain của agent | ✅ | ✅ | ✅ |
| Chat thử với agent | — | ✅ | ✅ |
| Tạo agent mới (no-code hoặc enroll) | — | ✅ | ✅ |
| Sửa config/instruction → tạo **draft** | — | ✅ (agent trong phạm vi) | ✅ |
| Publish **dev/stg** | — | ✅ (agent trong phạm vi) | ✅ |
| Publish **prod** | — | ⚠️ **tạo yêu cầu chờ admin duyệt** | ✅ (trực tiếp) |
| Rollback prod | — | ⚠️ chờ duyệt | ✅ |
| Gán kênh (routing Lark/Telegram) | — | ✅ (agent trong phạm vi) | ✅ |
| Cấp/thu quyền connector | — | — | ✅ |
| Bật/tắt agent (kill-switch) | — | ⚠️ chờ duyệt | ✅ |
| Duyệt việc (HITL) | — | — | ✅ |
| Quản lý tài khoản & phân quyền | — | — | ✅ |
| Credential model (pool token) | — | — | ✅ |
| Sửa brain **shared** | — | ⚠️ đề xuất | ✅ |
| Sửa brain **riêng của agent** | — | ✅ (agent trong phạm vi) | ✅ |

⚠️ = tạo `pending_actions` (dùng lại HITL của P7) → **AG-OPS báo admin qua Telegram/Lark** → admin duyệt mới chạy.

---

## 2. P8 — Tài khoản, đăng nhập, phân quyền

### 2.1 Schema

```sql
accounts(email PK, name, password_hash, must_change_pw bool, status active|disabled,
         telegram_chat_id, last_login_at, created_by, created_at)

role_bindings(id, email FK, scope_type 'platform'|'agent', scope_id,   -- scope_id='*' khi platform
              role 'admin'|'moderator'|'user', granted_by, granted_at,
              UNIQUE(email, scope_type, scope_id))

web_sessions(token_hash PK, email, created_at, expires_at, ip, user_agent, revoked_at)

login_attempts(email, ip, ok bool, at)      -- chống dò mật khẩu
```

Ghi chú: `platform_admins` (P7, dùng cho kênh Telegram) **giữ nguyên**, sẽ merge dữ liệu sang
`accounts` khi migrate — email trùng thì nối `telegram_chat_id`.

### 2.2 Xác thực

- **Mật khẩu**: `hashlib.pbkdf2_hmac('sha256', pw, salt, 200k)` — dùng stdlib, **không thêm dependency**.
- **Phiên**: token ngẫu nhiên 32 byte → lưu **hash** trong `web_sessions`; cookie
  `httpOnly` + `Secure` + `SameSite=Lax`, hạn 12h, gia hạn khi hoạt động.
- **Chống dò**: khoá 15 phút sau 5 lần sai/email/IP; ghi `login_attempts`; audit mọi lần đăng nhập.
- **Đổi mật khẩu lần đầu**: tài khoản mới do admin tạo có `must_change_pw=true`.
- **(Tuỳ chọn) OTP Telegram**: nếu account đã nối Telegram, bot gửi mã 6 số — tận dụng
  `@LSRAdminBot` sẵn có. Bật/tắt bằng cấu hình; **không bắt buộc ở P8**.

### 2.3 API (platform_api)

```
POST /v1/auth/login              {email, password} → set cookie, trả {name, roles}
POST /v1/auth/logout
GET  /v1/auth/me                 → {email, name, platform_role, agent_roles[], permissions[]}
POST /v1/auth/change-password    {old, new}

GET  /v1/accounts                [admin] danh sách + vai trò + lần đăng nhập cuối
POST /v1/accounts                [admin] tạo (sinh mật khẩu tạm, must_change_pw)
POST /v1/accounts/{email}/status [admin] disable/enable
POST /v1/accounts/{email}/reset-password  [admin] sinh mật khẩu tạm mới
POST /v1/accounts/{email}/roles  [admin] gán/thu {scope_type, scope_id, role, revoke?}
```

**Enforcement**: thêm `_require_perm(authorization, perm, agent_id=None)` trong platform_api.
Mọi endpoint hiện có gắn quyền tương ứng (bảng §1.3). Admin token cũ vẫn dùng được cho
service-to-service (gateway, bot) — nhưng **thao tác từ console phải đi bằng session người dùng**.

### 2.4 Web console

- `/login` — form đăng nhập; middleware Next.js chặn mọi trang khác nếu chưa có phiên.
- Header hiện **tên người đang đăng nhập + vai trò** + nút Đăng xuất.
- `lib/platform.ts`: thay `PLATFORM_ADMIN_TOKEN` bằng **session token của người dùng** cho
  mọi hành động; `X-Actor` lấy từ phiên (bỏ hằng số `web-admin`) → audit ghi đúng người.
- **Tab mới `/accounts`** (chỉ admin): danh sách tài khoản, tạo, disable, reset mật khẩu,
  gán vai trò theo platform **và** theo từng agent, xem lần đăng nhập cuối + audit liên quan.
- UI ẩn nút theo quyền (chỉ là lớp tiện dụng — API vẫn là nơi chặn thật).

### 2.5 Rollout an toàn (không tự khoá mình ra ngoài)

1. Tạo bảng + seed **tài khoản admin đầu tiên** (`thint@hapas.vn`) với mật khẩu tạm in ra **log VM**, `must_change_pw=true`.
2. Bật login nhưng **giữ nguyên basic-auth Caddy** trong 1 tuần (2 lớp).
3. Khi 2 admin + moderator đã đăng nhập được → **gỡ basic-auth** khỏi Caddy.
4. Rút `PLATFORM_ADMIN_TOKEN` khỏi web env sau khi mọi thao tác đã đi qua session.

### 2.6 Test case P8

| ID | Kịch bản | Kỳ vọng |
|---|---|---|
| P8.1.1 | Đăng nhập đúng | Có cookie phiên; `/v1/auth/me` trả đúng vai trò |
| P8.1.2 | Sai mật khẩu 5 lần | Bị khoá 15 phút; ghi `login_attempts`; lần đúng thứ 6 vẫn bị chặn |
| P8.1.3 | Tài khoản `disabled` | Không đăng nhập được, kể cả mật khẩu đúng |
| P8.1.4 | Cookie hết hạn / bị thu hồi | Mọi API trả 401, phải đăng nhập lại |
| P8.1.5 | Tài khoản mới | Bắt buộc đổi mật khẩu trước khi làm việc khác |
| P8.2.1 | `user` gọi API sửa (POST) | **403 từ API** (không chỉ ẩn nút) |
| P8.2.2 | `user` xem dashboard/KPI/config | 200 |
| P8.2.3 | `moderator` sửa agent **trong** phạm vi | 200, tạo draft |
| P8.2.4 | `moderator` sửa agent **ngoài** phạm vi | 403 |
| P8.2.5 | `moderator` publish **dev** | Thành công ngay |
| P8.2.6 | `moderator` publish **prod** | Không publish; tạo `pending_actions`; admin nhận thông báo |
| P8.2.7 | Admin duyệt yêu cầu đó | Version lên prod; audit ghi **cả người đề xuất và người duyệt** |
| P8.2.8 | Admin từ chối | Không đổi gì; moderator thấy trạng thái rejected |
| P8.2.9 | Quyền agent-scope cao hơn platform-scope | Lấy quyền cao hơn (user toàn platform + moderator AG-BI → sửa được AG-BI) |
| P8.3.1 | Thao tác bất kỳ | `audit_log.actor` = **email người thật**, không còn `web-admin` |
| P8.3.2 | Admin thu quyền moderator giữa chừng | Request kế tiếp bị 403 ngay (không cần đăng xuất) |
| P8.3.3 | Gọi API bằng session của người khác (đánh cắp cookie) | Session gắn IP/UA — lệch thì buộc đăng nhập lại (cấu hình được) |
| P8.4.1 | Tab Accounts: tạo tài khoản | Sinh mật khẩu tạm, hiện **một lần**, audit ghi người tạo |
| P8.4.2 | Tab Accounts: gán vai trò theo agent | Người đó chỉ thấy/sửa đúng agent đó |
| P8.4.3 | `moderator` mở tab Accounts | Không thấy tab; gọi API trực tiếp → 403 |
| P8.4.4 | Disable tài khoản đang có phiên | Phiên bị vô hiệu ngay |

---

## 3. P9 — Tạo agent no-code trên console

### 3.1 Trải nghiệm: wizard 5 bước (`/agents/new`)

| Bước | Nội dung | Ràng buộc |
|---|---|---|
| **1. Thông tin** | agent_id (tự sinh từ tên, sửa được), tên, chủ sở hữu, mô tả ngắn | id không trùng |
| **2. Use case** | Bài toán · người dùng · luồng chính · ngoài phạm vi · rủi ro | **BẮT BUỘC** — cùng gate như đường code |
| **3. Test case** | Bảng case (câu hỏi → kỳ vọng), tối thiểu 2 case | **BẮT BUỘC**, lưu thành `tests.jsonl` |
| **4. Hành vi** | Instruction (prompt), model, model dự phòng, skill, connector cần dùng | Connector phải được admin cấp quyền sau |
| **5. Kênh & chạy thử** | Chọn kênh (web/Telegram/Lark) + chat thử ngay | Tạo routing_binding tương ứng |

Kết thúc: agent được tạo ở trạng thái `registered` + **version v1 (draft)** + runtime no-code
sẵn sàng → bấm **Chạy thử** là chat được ngay trong console.

> Use case/test case nhập trên console được **lưu vào DB** và (tuỳ chọn) xuất ra
> `agents/<ID>/USECASE.md` + `TESTCASES.md` qua nút "Xuất repo" để đồng bộ với đường code.

### 3.2 Runtime cho agent no-code

Vấn đề: agent no-code không có code → **ai chạy nó?**

Giải pháp: **một service `nocode_runtime` phục vụ NHIỀU agent** (không phải mỗi agent một container):

```
nocode_runtime (1 container)
  └─ poll job của MỌI agent có runtime='nocode'
       ├─ lấy instruction từ agent_versions (bản đang publish theo env)
       ├─ dựng ngữ cảnh: /v1/self/context (đã có ở P4)
       ├─ lấy quyền model: /v1/self/model-auth/lease (đã có ở P2)
       ├─ gọi model → sinh câu trả lời
       └─ trả lời: /v1/self/jobs/{id}/reply (đã có — tự đúng kênh)
```

Tận dụng gần như toàn bộ P1–P7; phần mới chỉ là **vòng lặp gọi model theo instruction**.
Cần thêm: cột `agents.runtime` (`nocode` | `managed` | `external`) và API cho runtime lấy
job **theo lô nhiều agent** (`GET /v1/runtime/jobs`, xác thực bằng runtime token riêng).

### 3.3 Publish có phê duyệt (moderator → admin)

```
Moderator bấm "Publish prod"
   └─ API tạo pending_actions(action='publish_version', params={agent_id, version, env}, risk=high)
        └─ AG-OPS gửi Telegram/Lark cho admin: nội dung + diff instruction + điểm eval
             ├─ Admin bấm ✅ Duyệt  → executor publish (kèm eval gate P3) → báo lại moderator
             └─ Admin bấm ❌ Từ chối → giữ nguyên; moderator thấy lý do
```

Thêm action `publish_version` vào executor P7. **Eval gate P3 vẫn áp dụng**: dù admin duyệt,
nếu golden set fail thì vẫn bị chặn (trừ khi admin chọn `force` + ghi lý do).

### 3.4 Test case P9

| ID | Kịch bản | Kỳ vọng |
|---|---|---|
| P9.1.1 | Moderator tạo agent qua wizard | Agent + version v1 draft được tạo; audit ghi người tạo |
| P9.1.2 | Bỏ trống Use case hoặc Test case | **Không cho sang bước sau** (gate như đường code) |
| P9.1.3 | agent_id trùng | Báo lỗi rõ, không đè agent cũ |
| P9.1.4 | `user` mở `/agents/new` | Không vào được; API trả 403 |
| P9.2.1 | Tạo xong bấm **Chạy thử** | Runtime no-code trả lời trong console (không cần code, không cần Docker) |
| P9.2.2 | Sửa instruction → chạy thử lại | Trả lời đổi theo instruction mới (bản draft) |
| P9.2.3 | Agent no-code có tri thức khớp trong brain | Trả lời **kèm trích dẫn nguồn** |
| P9.2.4 | Hỏi 2 câu nối nhau | Nhớ ngữ cảnh (session memory dùng chung) |
| P9.2.5 | Pool credential cạn | Báo lỗi rõ ràng, job không mất, admin nhận cảnh báo |
| P9.3.1 | Moderator publish prod | Tạo yêu cầu chờ duyệt; **prod chưa đổi** |
| P9.3.2 | Admin duyệt | Prod đổi sang version mới; cả 2 tên trong audit |
| P9.3.3 | Golden set fail + admin duyệt | **Vẫn bị eval gate chặn**; muốn qua phải `force` + lý do |
| P9.3.4 | Admin từ chối | Prod giữ nguyên; moderator thấy trạng thái + lý do |
| P9.4.1 | Gán kênh Telegram ở bước 5 | Nhắn bot là agent no-code trả lời |
| P9.4.2 | Xuất repo | Sinh `agents/<ID>/USECASE.md` + `TESTCASES.md` + `tests.jsonl` khớp nội dung đã nhập |
| P9.4.3 | Agent no-code trong KPI/mart | Có runs/token/chi phí như agent code |
| P9.4.4 | Deactivate agent no-code | Runtime bỏ qua job của agent đó (kill-switch vẫn hiệu lực) |

---

## 4. Thứ tự thực hiện & rủi ro

**Thứ tự bắt buộc: P8 trước P9** — vì luồng "moderator publish → admin duyệt" cần vai trò có thật.

| Rủi ro | Cách xử lý |
|---|---|
| Tự khoá mình khỏi console | Seed admin trước, giữ basic-auth 2 lớp, chỉ gỡ khi đã đăng nhập được |
| Web còn cầm admin token → RBAC vô nghĩa | Chuyển sang session token; rút admin token khỏi web env ở bước cuối P8 |
| Agent no-code chạy tốn token ngoài dự kiến | Áp quota sẵn có (P7 cost/quota) + cảnh báo AG-OPS |
| Moderator publish nhầm loạt agent | Mọi publish prod đều qua duyệt + audit 2 tên |
| Mật khẩu yếu | Bắt đổi lần đầu, tối thiểu 10 ký tự, khoá sau 5 lần sai |

**Ước lượng đầu ra:** P8 = 4 nhóm việc (schema+auth API, enforcement, web login+middleware, tab Accounts) ·
P9 = 3 nhóm việc (wizard, nocode_runtime, publish-approval). Tổng **~33 test case** mới.
