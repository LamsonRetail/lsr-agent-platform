# SETUP — AG-LEGAL (Phase 0: việc cần người/admin làm)

Mỗi mục dưới đây là một việc **con người phải làm** (agent không tự làm được vì cần
mật khẩu/quyền admin). Làm xong tới đâu điền vào `.env` tới đó (copy từ `.env.example`).

## 1. Cấp quyền bot vào Wiki pháp chế  ← đang chặn sync

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

Cập nhật code lên VM:

```bash
cd "~/LSR Legal Agent" && rm -rf /tmp/ag-legal-deploy && mkdir -p /tmp/ag-legal-deploy \
  && rsync -a --exclude .git --exclude __pycache__ --exclude data --exclude .venv ag-legal/ /tmp/ag-legal-deploy/ \
  && mkdir -p /tmp/ag-legal-deploy/secrets/notebooklm \
  && cp ~/.notebooklm/profiles/default/storage_state.json /tmp/ag-legal-deploy/secrets/notebooklm/ \
  && sed -i '' 's|^NLM_AUTH_PATH=.*|NLM_AUTH_PATH=/agent/secrets/notebooklm/storage_state.json|' /tmp/ag-legal-deploy/.env \
  && tar -C /tmp -czf /tmp/ag-legal-deploy.tgz ag-legal-deploy \
  && gcloud compute scp /tmp/ag-legal-deploy.tgz digital-transformation-hosting:/tmp/ --zone asia-southeast1-b --project ganesha-381907 \
  && gcloud compute ssh digital-transformation-hosting --zone asia-southeast1-b --project ganesha-381907 \
     --command 'sudo tar -xzf /tmp/ag-legal-deploy.tgz -C /opt/ag-legal --strip-components=1 && cd /opt/ag-legal && sudo docker compose up -d --build'
```

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

- [ ] Bot vào được wiki space (mục 1) — **chặn sync**
- [ ] `storage_state.json` + notebook id (mục 2) — **chặn sync**
- [ ] Bot ở trong group `oc_2c44…4efb` (mục 3) — **chặn thông báo & phê duyệt**
- [ ] **Email của Nguyễn Thị Anh** để `seed_roles.py` chạy được (mục 3)
- [ ] LSR_AGENT_TOKEN (mục 4) — cần từ Phase 2 (chat)
- [ ] `instruction_block` đã publish (`GET /v1/self/context` ≠ null) — **điều kiện golive thật**
- [ ] Sync lần đầu thành công (mục 5)
- [ ] (Phase 3) Drive folder template hợp đồng + file mô tả field
- [ ] (Phase 5) Danh sách nguồn luật uy tín khởi tạo
- [ ] (Phase 6) Tên quy trình trình ký trên Lark Approval + checklist đầu mục hồ sơ
