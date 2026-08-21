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

Cây folder Drive pháp chế (đo 21/08) — `MIx2fFd8rlzWJBd9bQGlcLQegCd` là folder **cha**:

```
MIx2fFd8…  (cha, link legal team hay đưa)
├── Hop dong mau/                B9jvfFfYwlMG16d9Pchlm5npgKc  ← mẫu HĐ (trống)
├── Van ban luat/                GUYFfiGeqlnyiOd8rU9lMLDvgwf  ← kho văn bản luật (ghi được)
│   ├── VN/   GFX8fVIORlfHLsdxeRbltMGlgih
│   └── TH/   GaZQfCgZYlpstDdgHKylprbSgqd
└── Legal - standard agreements/  T8DzfOysElvbf4dMHB7lomb7grc  ← mẫu HĐ (trống)
    └── BAN THAO DRAFT (agent xuat)/  NHe5fRCSclUMvNdDmhul5njvg7c
```

`LEGAL_TEMPLATE_FOLDER` khai **cả hai** folder mẫu (cách nhau dấu phẩy) — hai tên đều hợp
lý, đoán sai một cái là S2 không thấy mẫu nào mà vẫn báo thành công. Đổi app thì share lại
folder cho bot mới (Manage collaborators → add bot).

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
3. Nạp người duyệt: `python3 seed_roles.py` — Nguyễn Trần Thi (BOD) và Nguyễn Thị Anh
   (`anhnt1@hapas.vn`). Script cố tình báo lỗi nếu còn placeholder, để không gửi phê
   duyệt cho sai người.

### ⚠️ open_id của Lark thuộc TỪNG APP — cái bẫy im lặng nhất ở đây

Quyền duyệt kiểm bằng `sender_open_id` của tin nhắn. **open_id không phải id toàn cục:
cùng một người, mỗi app Lark thấy một open_id khác nhau.** Nên khi đổi app nhận tin
(21/08 đổi sang `cli_aa0f9ac50cf8dee9`), `legal_roles.open_id` cũ có thể không còn khớp ⇒
**đúng người vẫn bị từ chối lệnh duyệt**, mà thông báo chỉ nói "chưa có quyền".

Bằng chứng đo được 21/08: `POST /v1/lark/resolve` trả `ou_cb1687f6…` cho
`thint@hapas.vn`, còn trong DB là `ou_c4a4e1e0…` — hai giá trị cho cùng một email. Và
`/v1/lark/resolve` của core **không nhận `app_id`** (dùng app mặc định của platform), nên
không resolve được theo app đang nhận tin.

Cách xử lý đã làm — để lỗi tự chỉ đường sửa:

1. Ai gõ lệnh mà không có quyền, agent trả về **chính open_id của người đó** kèm lệnh sửa.
2. Admin chạy: `python3 seed_roles.py --map <open_id> <email>`.

Cách xử lý dứt điểm (cần admin Lark): thêm scope **`contact:user.id:readonly`** cho app
`cli_aa0f9ac50cf8dee9` → **Create version & publish**. Có scope đó thì agent tự resolve
open_id theo đúng app, không cần bước 1–2 nữa.

> Telegram: **bỏ khỏi scope** (chốt 17/08/2026) — không tạo bot, không cấu hình.

## 3b. Add bot Lark vào group  ✅ XONG 21/08 — nhưng đọc kỹ chỗ app_id

Bot **đã ở trong group** `LSR Legal - admin group` (`oc_2c44…4efb`). Đo 21/08:

```
GET  /v1/lark/chats?app_id=cli_aa0f9ac50cf8dee9  →  LSR Legal - admin group
POST /v1/lark/send  (app_id đó)                  →  {"ok": true}
```

⚠️ **Cái bẫy đã mất một ngày để tìm ra**: bot trong group là **app RIÊNG của AG-LEGAL**
`cli_aa0f9ac50cf8dee9`, KHÔNG phải app Admin dùng chung `cli_aaff13891ff85ee6`. Agent để
`LARK_BOT_APP_ID` rỗng thì broker gửi bằng app Admin — app đó **không ở trong group nào**
(`chats: []`) nên mọi lời gọi trả 502 *"Bot/User can NOT be out of the chat"* và **toàn bộ
thông báo mất im lặng**. Đã set `LARK_BOT_APP_ID=cli_aa0f9ac50cf8dee9`.

Cách tự kiểm khi nghi kênh Lark không chạy — chạy 3 lệnh này, đúng thứ tự:

```bash
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
     "$LSR_PLATFORM_URL/v1/lark/chats?app_id=$LARK_BOT_APP_ID"      # phải thấy group
curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
     "$LSR_PLATFORM_URL/v1/lark/chats"                              # app mặc định thấy gì
```

`chats: []` **không** chắc là bot ngoài group (có thể app thiếu scope `im:chat:readonly`) —
phép thử dứt khoát luôn là **gửi thử một tin**.

Còn lại: Console → **Ingress** → routing binding `channel=lark` → điền cả `app_id`
(`cli_aa0f9ac50cf8dee9`) và `chat_id` → AG-LEGAL. Để trống cả hai = binding "bắt tất",
AG-OPS sẽ cảnh báo.

> **Nhóm mới không cần cấu hình gì.** Từ 21/08 agent tự nạp danh sách nhóm qua
> `/v1/lark/chats` mỗi chu kỳ `gate_loop` (core: endpoint này chỉ trả **nhóm**), nên add
> bot vào nhóm nào là nhận ra nhóm đó ngay. `AGENT_GROUP_CHAT_IDS` chỉ còn dùng khi muốn
> coi một chat là nhóm **trước khi** bot join.

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

## 3e. Mẫu hợp đồng — quy ước `[MAU]` và cách agent đọc mẫu

Legal team xếp mẫu theo LOẠI, mỗi loại một folder con trong `Hop dong mau`:

```
Hop dong mau/  (B9jvfFfYwlMG16d9Pchlm5npgKc)
├── BỘ MẪU HỢP ĐỒNG_Mua bán/         2. [MAU]_Hop dong mua ban_Hapas.docx  ← mẫu
│                                     1. Bao gia…  3. ĐNTT…  4. Biên bản nghiệm thu…
├── BỘ MẪU HỢP ĐỒNG_Dịch vụ/         [MAU]_… ×2  (+ Phụ lục, BBNTTL…)
├── BỘ MẪU HỢP ĐỒNG_Dịch vụ IT/ · _Livestream/ · _Thuê nhà/ · _Nguyên tắc_In ấn/
└── MẪU_Header_Footer/               (không phải hợp đồng)
```

Hai quy tắc agent dùng — **theo quy ước của legal team, không tự đoán**:

1. **Chỉ file có `[MAU]` trong tên là mẫu.** Trong cùng folder còn báo giá, đề nghị thanh
   toán, biên bản nghiệm thu thanh lý — tên đều có chữ "hợp đồng". Lấy bừa theo từ khoá là
   agent đem *biên bản nghiệm thu* ra soạn thành hợp đồng. File bị bỏ qua đều được **ghi
   log**, không im lặng.
2. **Quét một tầng folder con**, bỏ `Header_Footer` và folder bản thảo agent tự xuất. Không
   đệ quy sâu: quét vào folder bản thảo là bản thảo của chính mình thành mẫu cho lần sau.

### Chỗ cần điền: mẫu thật dùng `………`, không dùng `{{...}}`

Kiểm mẫu Mua bán 21/08: chỗ điền là **dãy ba chấm chèn giữa câu** —
`"Số: ………/2026/HDMBHH/…….- HTC"`, `"Thời gian giao hàng: …….. giờ ngày …………….;"` — và
trong bảng `nhãn | : | giá trị`. Agent dò 20 chỗ trống ở mẫu này, nhãn lấy từ mảnh câu
quanh chỗ trống (hoặc **ô đầu hàng** nếu ở trong bảng) nên người điền biết đang điền gì.

Ba chốt đã trả giá để biết, đừng bỏ:

| Chốt | Vì sao |
|---|---|
| Ô GỘP chỉ tính **một** chỗ trống | python-docx trả ô gộp nhiều lần ⇒ một chỗ đếm thành ba ⇒ **mọi giá trị phía sau rơi sai ô** |
| Dò và điền đi **cùng một đường** | Lệch thứ tự là giá trị vào sai chỗ — lỗi nguy hiểm nhất có thể có với hợp đồng |
| `"..."` là dấu lược, **không** phải chỗ trống | "hàng mới 100%..." điền vào là hỏng câu. Chỉ nhận `…` hoặc ≥4 dấu chấm |
| Chỗ trống chưa có thông tin **để nguyên `………`** | Xoá âm thầm = hợp đồng thiếu điều khoản mà trông như đã hoàn chỉnh. Card ghi rõ còn mấy chỗ trống |

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

## 6. Deploy lên VM platform  ✅ ĐÃ DEPLOY BẢN MỚI 21/08/2026

Agent chạy tại `/opt/ag-legal` trên VM `digital-transformation-hosting`
(project `ganesha-381907`, zone `asia-southeast1-b`), **một container**
`ag-legal-agent-1` — chat + kb-sync + news-crawl + approval-watch + gate worker cùng
tiến trình (NotebookLM chỉ cho một phiên mỗi tài khoản).

Kết quả deploy 21/08 (kiểm live sau khi lên):

| Thứ | Trạng thái |
|---|---|
| 21 module `legalkb/` | ✅ (trước đó VM chỉ có 5 module bản 12/08) |
| kb-sync | ✅ inventory 62, 0 lỗi |
| nhóm bot tham gia | ✅ 1 (tự phát hiện) |
| approval-watch | ✅ danh tính `ann_legal@hapas.vn`, 5 phút/lần |
| nguồn luật | ✅ 3 nguồn VN bật, chạy thứ 2 07:00 |
| người duyệt | ✅ 2 người, có open_id |
| hỏi đáp S1 end-to-end | ✅ trả lời có trích dẫn từ KB, ghi 2 lượt vào bộ nhớ |
| mẫu hợp đồng | ⚠️ đọc được 2 folder, **0 file .docx** |
| `instruction_block` | ❌ NULL — publish trên Console |
| CLI `claude` trong image | ❌ **thiếu** → S2–S5 degrade (xem cuối mục này) |

Bản đang chạy trước đó được sao lưu ở `/opt/ag-legal.bak-<ngày>-<giờ>` để rollback:
`sudo rm -rf /opt/ag-legal && sudo mv /opt/ag-legal.bak-… /opt/ag-legal && cd /opt/ag-legal && sudo docker compose up -d`.

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
- [x] Bot ở trong group `oc_2c44…4efb` (mục **3b**) — ✅ 21/08, gửi thật OK. Bot là app riêng `cli_aa0f9ac50cf8dee9`, phải set `LARK_BOT_APP_ID`
- [x] **Email của Nguyễn Thị Anh** — ✅ `anhnt1@hapas.vn`, đã nạp `legal_roles`
- [x] Danh tính Lark của agent (C8, mục 3c) — ✅ connected 20/08
- [ ] Thông báo minh bạch "Ann Nguyen là account máy" (mục 3c)
- [x] LSR_AGENT_TOKEN (mục 4) — ✅ agent `status=active` từ 14/08, **29 run** (đo 20/08)
- [x] **Deploy bản mới lên VM** (mục 6) — ✅ 21/08, 21 module, S1 end-to-end OK
- [ ] `instruction_block` đã publish (mục **3d** — chỉ làm trên Console) — **điều kiện golive thật**
- [x] **CLI `claude` trong image** — ✅ 21/08: Node 22 + Claude Code 2.1.238 trong image; token **lease từ platform** (`sub-thi-canhan`), không dán vào `.env`, không vào git
- [ ] **Scope `contact:user.id:readonly`** cho app `cli_aa0f9ac50cf8dee9` — để agent tự resolve open_id theo đúng app (xem mục 3, cái bẫy open_id)
- [x] Sync lần đầu thành công (mục 5) — ✅ 19/08: 32 tài liệu nạp, 18 mục rỗng bị loại đúng
- [x] (Phase 3) **Mẫu hợp đồng .docx trong Drive** — ✅ 21/08: **9 mẫu** đã nạp (Mua bán · Dịch vụ ×2 · Dịch vụ IT · Livestream ×2 · Thuê nhà ×2 · Nguyên tắc/In ấn), 9–34 chỗ trống mỗi mẫu. Đã chạy thử tạo bản thảo Mua bán end-to-end
- [x] (Phase 5) Danh sách nguồn luật — ✅ **3 nguồn VN đang bật** (chinhphu.vn · thuvienphapluat · LuatVietnam RSS), đã lưu thật PDF ký số + toàn văn. Nước khác **thêm trên console agent** (chốt 21/08); văn bản bỏ tay vào folder con theo nước vẫn được index
- [x] (Phase 6) Quy trình trình ký — ✅ `approval_code=0338BCF9…`, 4 node, 4 field form đã ghim vào `signing.py`; checklist đầu mục đã nạp (`seed_news.py`)
- [ ] (Phase 6) **C5 — passthrough tenant token** để đọc form/file hồ sơ + ghi comment vào instance (`requests/C5-lark-tenant-passthrough.md`)
