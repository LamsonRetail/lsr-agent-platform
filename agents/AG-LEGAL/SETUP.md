# SETUP — AG-LEGAL (Phase 0: việc cần người/admin làm)

Mỗi mục dưới đây là một việc **con người phải làm** (agent không tự làm được vì cần
mật khẩu/quyền admin). Làm xong tới đâu điền vào `.env` tới đó (copy từ `.env.example`).

## 1. Cấp quyền bot vào Wiki pháp chế  ✅ ĐÃ XONG 18/08 (đọc được 56 node)

Wiki space pháp chế: `7595876759661186785`
(link: https://o4pvcegwn6b.sg.larksuite.com/wiki/ZK5zwtpbPi5cWFkrlEVleqkigjc)

1. Mở wiki space trên Lark → **Settings → Members → Add member**.
2. Thêm **bot app** sẽ chạy sync (app của platform hoặc app riêng cho AG-LEGAL)
   với quyền **Can view (Read)**.
3. Trên [Lark Developer Console](https://open.larksuite.com/app) của app đó,
   đảm bảo đã bật scopes: `wiki:wiki:readonly`, `drive:drive:readonly`,
   `docx:document:readonly` (sau này thêm `im:resource` cho review hợp đồng)
   → bấm **Create version & publish** để scopes có hiệu lực.
4. Điền `LARK_APP_ID` / `LARK_APP_SECRET` của app đó vào `.env`.

Folder Drive văn bản luật `MIx2fFd8rlzWJBd9bQGlcLQegCd` bot đã đọc được — nếu đổi
app, share folder cho bot mới (Manage collaborators → add bot → Can view).

## 2. NotebookLM — đăng nhập tài khoản Google cá nhân

Trên máy Mac của chủ tài khoản (cần mở browser):

```bash
pip install notebooklm-py
notebooklm login          # mở browser → đăng nhập Google → tự lưu phiên
notebooklm create "LSR Legal KB"
notebooklm list           # lấy notebook id, điền vào .env → NLM_NOTEBOOK_KB_ID
```

Phiên đăng nhập lưu ở `~/.notebooklm/profiles/default/storage_state.json`.
**Copy file này lên VM** vào thư mục secrets của agent (mount read-only):

```bash
gcloud compute scp ~/.notebooklm/profiles/default/storage_state.json \
  digital-transformation-hosting:/opt/lsr-platform/secrets/ag-legal/notebooklm/ \
  --zone asia-southeast1-b --project ganesha-381907
```

⚠️ File này tương đương phiên đăng nhập Google của bạn — chỉ để trong
`/opt/lsr-platform/secrets/` (chmod 600), tuyệt đối không commit.
Khi hết hạn/đổi mật khẩu → login lại và copy đè; agent sẽ cảnh báo khi auth lỗi.

### Phiên NotebookLM hết hạn (gặp 18/08/2026)

Triệu chứng: sync báo `Authentication expired or invalid. Redirected to
accounts.google.com` cho MỌI tài liệu → 0 nạp được.

CLI `notebooklm` nằm trong **venv của dự án**, không phải global (`zsh: command not
found: notebooklm` là vì gọi thiếu đường dẫn):

```bash
"/Users/ntranthi/LSR Legal Agent/.venv/bin/notebooklm" login
```

Nó ghi vào `~/.notebooklm/profiles/default/storage_state.json` — đúng chỗ `NLM_AUTH_PATH`
trỏ tới, không cần copy tay. Trên VM thì copy file này lên
`/opt/lsr-platform/secrets/notebooklm/` (chmod 600).

⚠️ **`.env`: không để comment cuối dòng và không để khoảng trắng quanh dấu `=`.**
Shell (`set -a; . ./.env`) tha, nhưng `docker compose env_file` thì lấy nguyên cả comment
vào giá trị. Đã gặp thật cả hai lỗi: `LARK_APP_SECRET` bị thêm 1 space đầu (len 33/32) và
`NLM_NOTEBOOK_KB_ID` + `NLM_AUTH_PATH` bị lẫn comment.

### Quyền GHI trên folder văn bản luật  ✅ XONG 20/08

| Folder Drive | Đọc | Ghi |
|---|---|---|
| **Kho văn bản luật `GUYFfiGeqlnyiOd8rU9lMLDvgwf`** (folder mới) | ✅ | ✅ |
| Mẫu hợp đồng `T8DzfOysElvbf4dMHB7lomb7grc` | ✅ | ✅ |
| Bản thảo DRAFT `NHe5fRCSclUMvNdDmhul5njvg7c` | ✅ | ✅ |
| ~~Văn bản luật `MIx2fFd8rlzWJBd9bQGlcLQegCd`~~ (folder cũ, chỉ Can view) | ✅ | ❌ 403 |

Agent tự tạo folder con theo nước (`VN/`, `TH/`) trong kho. Đã chạy thật 20/08: lưu được
PDF ký số của chinhphu.vn và toàn văn `.txt` của tvpl/luatvietnam.

Nếu sau này đổi folder: mở folder trên Lark → **Manage collaborators** → thêm bot app
AG-LEGAL với **Can edit** (chỉ Can view thì ghi trả `1061004 forbidden`).

## 3. Group Pháp chế/Admin (thông báo + phê duyệt)

Chốt 17/08/2026: dùng **một group Lark** cho cả thông báo và phê duyệt —
`oc_2c44821d37e5e12a2c1651251cfd4efb`.

1. **Add bot AG-LEGAL vào group đó** (việc của admin Lark).
2. Xác nhận: `GET /v1/lark/chats` bằng token agent phải thấy chat_id này. Consumer cũng
   tự kiểm lúc khởi động và in cảnh báo nếu bot chưa ở trong group.
3. Nạp người duyệt: `python3 seed_roles.py` — hiện có Nguyễn Trần Thi (BOD) và
   Nguyễn Thị Anh (Legal). **Cần email chính xác của chị Anh**; script cố tình báo lỗi
   nếu còn placeholder, để không gửi phê duyệt cho sai người.

> Telegram: **bỏ khỏi scope** (chốt 17/08/2026) — không tạo bot, không cấu hình.

## 3b. Add bot Lark vào group  ⛔ ĐANG CHẶN (đo lại 20/08)

**Đây là việc chặn nhiều nhất còn lại.** Đo bằng token agent, không phải phỏng đoán:

```
GET /v1/lark/chats?app_id=cli_aaff13891ff85ee6  →  {"chats": []}          # 0 chat
POST /v1/lark/send  →  502 "Lark từ chối: Bot/User can NOT be out of the chat."
```

Kiểm cả 4 app Lark có secret trên VM: **không app nào ở trong group
`oc_2c44…4efb`**, cũng không ở trong `oc_7323f980…` (chat của account Ann). Nên việc
"đã add bot" trước đó chưa có hiệu lực — có thể add app khác, hoặc add vào group khác.

Cách làm (người có quyền quản group, trên Lark):

1. Mở group → **Settings → Bots → Add bot** → chọn bot của **app Admin platform**
   `cli_aaff13891ff85ee6`.
2. Kiểm lại bằng chính lệnh trên: `GET /v1/lark/chats` phải thấy `chat_id` của group.
3. Console → **Ingress** → routing binding `channel=lark` → **điền cả `app_id` và
   `chat_id`** (để trống cả hai = binding "bắt tất", AG-OPS sẽ cảnh báo) → AG-LEGAL.

Chưa có bước này thì: **không có thông báo, không duyệt được bằng lệnh `#12 duyệt`,
S4 digest không gửi được, S5 không báo được hồ sơ**. Mọi thứ khác vẫn chạy.

> Muốn bot mang **danh tính riêng** (tên "Ann"/AG-LEGAL thay vì bot dùng chung): core đã
> mở sẵn chỗ `LEGAL_*` trong compose (C9, commit `7f6f7f1`), chỉ còn tạo custom app mới
> trong Lark Developer Console rồi nạp `LEGAL_LARK_APP_ID/SECRET` bằng
> `bash scripts/add-lark-app.sh LEGAL cli_xxx platform_api`. **Không** được trỏ `LEGAL_*`
> vào app đang dùng của agent khác — hai long-connection trên cùng một app làm Lark chỉ
> đẩy event cho một container, tin nhắn rơi rụng ngẫu nhiên (script đã chặn).

## 3c. Danh tính Lark của agent (C8)  ✅ XONG 20/08

Agent đọc Lark Approval dưới account **`ann_legal@hapas.vn`** ("Ann Nguyen") — account
**máy**, không phải người. Platform giữ token (mã hoá, tự refresh); agent gọi
`/v1/lark/user/call` và **không bao giờ thấy token**.

```
GET /v1/lark/user/status?subject=ann_legal@hapas.vn
→ connected: true · scope approval read/write · path /open-apis/approval/v4/ · refresh 7 ngày
```

Hai việc **của người**, chưa xong:

1. **Thông báo minh bạch** cho người trong quy trình trình ký rằng đây là account máy —
   yêu cầu của `docs/LARK_USER_BROKER.md`, đã ghi vào `golive.json`
   (`machine_identity_disclosed`).
2. **`refresh_token` sống 7 ngày** (đo thật trong tenant này). Hết hạn thì phải có người
   authorize lại: Console → trang agent → **Danh tính Lark**. Agent tự nhắc vào group khi
   còn ≤2 ngày, nhưng nhắc chỉ tới được nếu bot đã ở trong group (mục 3b).

## 3d. Publish `INSTRUCTION.md` — chỉ làm được trên Console

Đo 20/08: `POST /v1/agents/AG-LEGAL/versions` → **403** vì Caddy chỉ mở nhóm `@selfserve`
(`/v1/self/*`, `/v1/lark/*`…), route publish nằm sau `guard` (cần `X-Gateway-Token` trên VM).
Không có endpoint `/v1/self/instruction`.

**Và như vậy là đúng**: `instruction_block` là *policy*. Để agent tự publish policy của
chính nó thì mất luôn ý nghĩa kiểm soát. Nên đây là việc của owner/admin, không phải việc
agent tự làm.

Cách làm: Console (**`https://agent.hapas-ai.tech`** — domain mới, commit `53eb2bb`) →
Agent **AG-LEGAL** → Instruction → dán nội dung `INSTRUCTION.md` → **Publish version**.

Kiểm bằng:

```bash
curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
  "$LSR_PLATFORM_URL/v1/self/version"
```

Phải thấy `version` ≠ null. Hiện trả `"note": "chưa publish version nào"`.
Agent nạp lại trong ≤10 phút (`gate_loop`), không cần deploy lại.

## 4. Đăng ký agent với platform

Chuẩn mới (P11) — **không đi xin enroll token của ai**:

```bash
bash ../../scripts/lsr-login.sh
```

Mở link, bấm Duyệt trên console → token cá nhân lưu `~/.lsr/token`. Enroll bằng chính
token đó → nhận `LSR_AGENT_TOKEN`, điền vào `.env`. Người tạo không phải admin platform
thì agent ở `status=registered`: **web chat test được ngay**, kênh Lark thật cần admin duyệt.

Quyền thao tác trên console: đăng nhập console **bằng Lark** → `/request-access` xin
`moderator` trên AG-LEGAL (token agent không dùng được cho việc này; và không ai tự duyệt
được yêu cầu của chính mình).

Chạy runtime:

```bash
claude setup-token     # chủ subscription tạo — KHÔNG dán vào log/PR/chat
```

rồi `POST /v1/self/deploy` (token agent là đủ).

## 5. Chạy thử sync lần đầu (sau khi xong mục 1 + 2)

```bash
cd agents/AG-LEGAL && cp .env.example .env  # điền giá trị
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a; source .env; set +a
.venv/bin/python sync_worker.py --once
```

Kỳ vọng: report JSON `added` = số tài liệu trong wiki + folder, `errors` rỗng;
mở notebook trên notebooklm.google.com thấy đủ sources.

## 6. Deploy lên VM platform (đã làm 12/08/2026)

Agent chạy tại `/opt/ag-legal` trên VM `digital-transformation-hosting`
(project `ganesha-381907`, zone `asia-southeast1-b`), 2 container:
`ag-legal-agent-1` (chat consumer) + `ag-legal-kb-sync-1` (sync KB 3h/lần).

⚠️ **Đường dẫn nguồn deploy đã ĐỔI — kiểm 20/08.** Thư mục cũ
`~/LSR Legal Agent/ag-legal/` là cây code **ngày 12/08** (chỉ có 6 module: engine,
lark_client, store, sync). Toàn bộ việc từ đó tới nay — S2–S5, gates, addressing, voice,
news, 3 adapter nguồn luật, approval — nằm ở `lsr-agent-platform/agents/AG-LEGAL/`.
Lệnh cũ trỏ vào thư mục cũ nên **chạy xong vẫn là bản 12/08 mà tưởng đã cập nhật**. Nên
xoá thư mục cũ đi cho khỏi nhầm lần sau. (Chưa kiểm được VM đang chạy bản nào — việc đó
cần SSH.)

Cập nhật code lên VM (nguồn ĐÚNG là `lsr-agent-platform/agents/AG-LEGAL`):

```bash
cd "$HOME/LSR Legal Agent/lsr-agent-platform/agents/AG-LEGAL" && rm -rf /tmp/ag-legal-deploy \
  && mkdir -p /tmp/ag-legal-deploy && rsync -a --exclude .git --exclude __pycache__ \
     --exclude data --exclude .venv --exclude '*.db' ./ /tmp/ag-legal-deploy/ \
  && mkdir -p /tmp/ag-legal-deploy/secrets/notebooklm \
  && cp ~/.notebooklm/profiles/default/storage_state.json /tmp/ag-legal-deploy/secrets/notebooklm/ \
  && sed -i '' 's|^NLM_AUTH_PATH=.*|NLM_AUTH_PATH=/agent/secrets/notebooklm/storage_state.json|' /tmp/ag-legal-deploy/.env \
  && tar -C /tmp -czf /tmp/ag-legal-deploy.tgz ag-legal-deploy \
  && gcloud compute scp /tmp/ag-legal-deploy.tgz digital-transformation-hosting:/tmp/ --zone asia-southeast1-b --project ganesha-381907 \
  && gcloud compute ssh digital-transformation-hosting --zone asia-southeast1-b --project ganesha-381907 \
     --command 'sudo tar -xzf /tmp/ag-legal-deploy.tgz -C /opt/ag-legal --strip-components=1 && cd /opt/ag-legal && sudo docker compose up -d --build'
```

> **Không dùng `POST /v1/self/deploy` cho agent này.** Đã đọc handler ở core: nó tạo
> container mới chỉ với một bộ env cố định (`CLAUDE_CODE_OAUTH_TOKEN`, `LSR_*`,
> `AGENT_REPO`, `AGENT_START_CMD`) và **không mang theo `.env` của agent** —
> `LARK_APP_SECRET`, `NLM_*`, các token folder Drive, `AGENT_LARK_SUBJECT` sẽ mất, và
> `secrets/notebooklm` không được mount. Agent này cần `.env` đầy đủ nên deploy bằng
> docker compose như trên. `GET /v1/self/deploy/status` trả `not_deployed` là **đúng**,
> không phải lỗi.

Xem log / trạng thái:

```bash
gcloud compute ssh digital-transformation-hosting --zone asia-southeast1-b --project ganesha-381907 --command 'sudo docker logs --tail 30 ag-legal-agent-1'
```

Lưu ý vận hành:
- Container join mạng `lsr-platform_default`, gọi `http://platform_api:8090` —
  edge Caddy **chặn API platform từ ngoài** (poll job qua URL public bị 403).
- Thư mục secrets mount **rw** (notebooklm-py ghi lại cookie xoay vòng; mount `ro`
  làm phiên hết hạn sớm).
- Khi phiên NotebookLM hết hạn: `notebooklm login` trên máy → copy lại
  `storage_state.json` lên `/opt/ag-legal/secrets/notebooklm/` → `docker compose restart`.

## Checklist

- [x] Bot vào được wiki space (mục 1) — ✅ 18/08, đọc được 56 node
- [x] `storage_state.json` (mục 2) — ✅ login lại 19/08, sync **32/32, 0 lỗi**. Phiên xoay cookie nên sẽ hết hạn lại: dấu hiệu là `Authentication expired` cho MỌI tài liệu
- [ ] Bot ở trong group `oc_2c44…4efb` (mục **3b**) — ⛔ **đo lại 20/08: 0 app nào ở trong group**
- [x] **Email của Nguyễn Thị Anh** — ✅ `anhnt1@hapas.vn`, đã nạp `legal_roles`
- [x] Danh tính Lark của agent (C8, mục 3c) — ✅ connected 20/08
- [ ] Thông báo minh bạch "Ann Nguyen là account máy" (mục 3c)
- [x] LSR_AGENT_TOKEN (mục 4) — ✅ agent `status=active` từ 14/08, **29 run** (đo 20/08)
- [ ] `instruction_block` đã publish (mục **3d** — chỉ làm trên Console) — **điều kiện golive thật**
- [x] Sync lần đầu thành công (mục 5) — ✅ 19/08: 32 tài liệu nạp, 18 mục rỗng bị loại đúng
- [ ] (Phase 3) **Nội dung 8 mẫu hợp đồng trong Wiki** — hiện rỗng (12 ký tự/node). Mẫu lấy từ Wiki được (export Lark Doc → docx đã kiểm OK), không cần Drive folder riêng
- [x] (Phase 5) Danh sách nguồn luật — ✅ **3 nguồn VN đang bật** (chinhphu.vn · thuvienphapluat · LuatVietnam RSS), đã lưu thật PDF ký số + toàn văn. **Thái Lan còn 0 nguồn** — 3 nguồn thử đều không lấy được tự động, cần URL trang danh sách thật từ nhóm pháp chế
- [x] (Phase 6) Quy trình trình ký — ✅ `approval_code=0338BCF9…`, 4 node, 4 field form đã ghim vào `signing.py`; checklist đầu mục đã nạp (`seed_news.py`)
- [ ] (Phase 6) **C5 — passthrough tenant token** để đọc form/file hồ sơ + ghi comment vào instance (`requests/C5-lark-tenant-passthrough.md`)
