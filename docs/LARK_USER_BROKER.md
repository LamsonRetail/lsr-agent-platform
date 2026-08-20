# C8 — User Identity Broker cho Lark

Một số API Lark **chỉ nhận user token**; gọi bằng tenant/bot token là bị từ chối thẳng
(kiểm live 19/08: `approval approvals search`, `approval approvals get`,
`approval instances get` đều trả *"only supports: user"* khi chạy `--as bot`).

Nhưng theo chuẩn platform, **agent không được cầm token của một người/account thật**.
Broker này là chỗ ở giữa: platform giữ token (mã hoá), tự refresh, kiểm quyền theo
allowlist path, audit từng lời gọi. Agent chỉ gọi một endpoint và **không bao giờ thấy token**.

## Kiến trúc

```
agent ──POST /v1/lark/user/call───▶ platform_api
        {subject, method, path}      │  1. _require_self          (đúng agent nào)
                                     │  2. connector 'lark_user'  (enforce, phải có grant)
                                     │  3. grant còn active?      (kill switch)
                                     │  4. path/method ∈ allowlist?
                                     │  5. token còn hạn? → tự refresh (SELECT FOR UPDATE)
                                     │  6. audit + meter
                                     └──▶ Lark  (Bearer user_access_token)
```

**Một proxy có allowlist, không phải N endpoint.** Thêm Approval hôm nay, Task/Docs
tháng sau = thêm một dòng grant, không phải PR vào core.

## Bảng

| Bảng | Giữ gì |
|---|---|
| `lark_user_identities` | token **mã hoá AES-GCM** (`bytea`), scope, expiry, ai authorize |
| `agent_user_identity_grants` | agent nào được dùng subject nào, giới hạn `path_prefixes` + `methods` |
| `lark_user_authorize_sessions` | phiên đang chờ người bấm đồng ý (TTL 15') |

Khoá mã hoá: `LARK_USER_TOKEN_KEY` trong `.env` **trên VM**. Không có khoá thì broker
**tắt hẳn** (503) — cố ý không fallback sang lưu token dạng rõ.

## Ba chi tiết Lark bắt buộc phải đúng (kiểm live 19/08)

Ba thứ này không suy ra được từ tài liệu, đều phải đo:

| Việc | Sai thì gặp gì | Đúng là |
|---|---|---|
| Endpoint trang đồng ý | `/authen/v2/oauth/authorize` → **404** ở cả `open.*` lẫn `accounts.*` | `/open-apis/authen/v1/authorize` |
| Host | `open.larksuite.com` + v1 → 302 sang `accounts.*`, nhưng v2 thì 404 | `accounts.larksuite.com` |
| `redirect_uri` | URI chưa đăng ký trong console app → `invalid_request` (**không** phải lỗi scope) | dùng lại URI đã đăng ký |
| Tên scope | đoán `approval:instance:readonly` → `invalid_scope` | `approval:instance:read` / `:write` |

Tên scope lấy từ **user token đang chạy thật** trong tenant (`lark-cli auth status`), không
đoán. Thêm domain mới thì đối chiếu lại bằng cách đó.

Vì Lark chỉ nhận `redirect_uri` đã đăng ký, và trong tenant này **chỉ app Admin
`cli_aaff13891ff85ee6`** có sẵn `/api/auth/lark/callback`, C8 **dùng lại đúng route đó**
và phân luồng bằng tiền tố `state`: `u...` = C8, số = đăng nhập console. Hai luồng ký HMAC
khác nhau nên không thể nhận nhầm. Nhờ vậy nối agent mới **không cần vào Lark Console**.

## Cấp quyền (chỉ admin, bắt buộc có người bấm đồng ý)

```bash
# 1) Tạo phiên authorize → lấy URL
curl -sS -X POST "$P/v1/lark/user/authorize/start" \
  -H "X-Gateway-Token: $G" -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"subject":"ann_legal@hapas.vn","domains":"approval"}'
```

Mở `url` trả về trên máy/điện thoại nào cũng được, **đăng nhập bằng CHÍNH account đó**
rồi bấm đồng ý. Platform kiểm lại email của người vừa đồng ý có đúng `subject` không —
sai account thì từ chối, vì nếu không token sẽ hành động dưới danh nghĩa người khác.

```bash
# 2) Chờ (CLI không cần browser tại chỗ)
curl -sS "$P/v1/lark/user/authorize/poll?state=<state>" -H "X-Gateway-Token: $G" -H "Authorization: Bearer $ADMIN"

# 3) Cấp cho agent, path HẸP NHẤT có thể
curl -sS -X POST "$P/v1/lark/user/grants" \
  -H "X-Gateway-Token: $G" -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"agent_id":"AG-LEGAL","subject":"ann_legal@hapas.vn",
       "path_prefixes":["/open-apis/approval/v4/"],"methods":["GET","POST"]}'
```

## Agent dùng thế nào

```python
# Kiểm trước để degrade RÕ RÀNG thay vì lỗi mù giữa việc
st = api("GET", "/v1/lark/user/status?subject=ann_legal@hapas.vn")
if not st["connected"]:
    return f"Chưa nối được danh tính Lark ({st['reason']}) — nhờ admin cấp quyền."

r = api("POST", "/v1/lark/user/call", {
    "subject": "ann_legal@hapas.vn",
    "method": "GET",
    "path": "/open-apis/approval/v4/instances/xxx",
})
data = r["data"]        # nguyên response của Lark
```

Bị 403 thì đọc `detail` — nó nói thẳng lý do: chưa grant / path ngoài phạm vi / method
không được cấp / grant đã thu hồi.

## Vòng đời token

- `access_token` (~2h): tự refresh khi còn <120s. Refresh dùng `SELECT ... FOR UPDATE`
  để hai tiến trình không refresh chồng nhau — platform từng mất phiên NotebookLM đúng
  vì lỗi này.
- `refresh_token` (**7 ngày** — đo thật trong tenant này, không phải 30; mỗi lần refresh
  được gia hạn lại 7 ngày nên chỉ chết nếu agent im hơn một tuần): hết là **bắt buộc có người authorize lại**. AG-OPS cảnh báo
  trước `LARK_USER_REFRESH_WARN_DAYS` (mặc định **2** — đặt 7 thì kêu ngay sau khi vừa cấp), kèm danh sách agent đang dùng.
  Sinh ra cảnh báo này vì AG-LEGAL từng mất refresh token 17/07 mà 19/08 mới phát hiện.

## Thu hồi

```bash
curl -sS -X POST "$P/v1/lark/user/identities/ann_legal@hapas.vn/revoke" \
  -H "X-Gateway-Token: $G" -H "Authorization: Bearer $ADMIN"
```

Xoá token + tắt mọi grant. Agent `deactivated` cũng **tự** mất grant (kill switch trong
`_execute_action`).

## Định tuyến (Caddy)

`/v1/lark/user/call` và `/v1/lark/user/status` đi qua `@selfserve` (agent gọi được từ
ngoài). `authorize/*`, `grants`, `identities*` nằm sau `guard` — **cần `X-Gateway-Token`**,
vì `/v1/lark/*` vốn đã mở cho agent nên phải kéo riêng nhóm admin về sau lớp bảo vệ.

## Chính sách phải chốt TRƯỚC grant đầu tiên

`CREATE_AGENT.md` §3.5-B: dùng user account cần review ToS Lark + chính sách nội bộ.
Hai điều cần chốt:

1. Agent hành động dưới danh nghĩa **account riêng cho agent** (vd `ann_legal@hapas.vn`),
   **không dùng account của người thật** — để log Lark phân biệt được người và máy.
2. Người trong nhóm liên quan **được thông báo minh bạch** rằng có một account máy tham
   gia quy trình.

Code đã sẵn sàng nhưng **chưa có identity nào được authorize** — chờ hai điều trên.
