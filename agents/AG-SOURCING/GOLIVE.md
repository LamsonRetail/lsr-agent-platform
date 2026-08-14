# AG-SOURCING — runbook golive

Trạng thái lúc viết (đã kiểm live, không suy đoán):

| Thứ | Trạng thái |
|---|---|
| Agent enroll | ✅ `GET /v1/self` → `status: registered` |
| Core Lark đa-app | ✅ `/v1/lark/chats?app_id=cli_aaf6ce7c8d38deed` → 200 + 3 nhóm |
| Brain riêng | ✅ 12 item `approved` từ 2 Lark Doc (`brain_seed.py --list`) |
| Golden set | ✅ 4 case active trong `golden-cases.json` (chưa upload lên platform) |
| **Instruction** | ❌ `GET /v1/self/context` → `instruction_block: null`, `version: null` |
| **`golive_at`** | ⚠️ đã set `2026-08-14T07:45:37Z` (trước đó `null`) — xem ghi chú dưới |

→ `routing_binding` đã trỏ TEAM S + SOURCING MM vào AG-SOURCING mà agent **chưa có refusal policy
nào**. Nói cho đúng mức độ: rủi ro này đang **tiềm ẩn, chưa xảy ra** — chưa có runtime nào chạy
(`/v1/self/deploy/status` → `not_deployed`) nên tin nhắn chỉ nằm trong queue, agent chưa trả lời ai.
Nó thành rủi ro thật vào đúng lúc có người bật consumer/deploy trong khi `instruction_block` còn
`null`. Vì vậy thứ tự trong runbook này là bắt buộc, không phải cho đẹp.

⚠️ **`golive_at` đã bị set trong khi `instruction_block` vẫn `null`.** Ngày 14/08 `GET /v1/self` trả
`golive_at: 2026-08-14T07:45:37Z` và `status: active`, trước đó là `null` — không do em làm (token
agent không set được field này), có lẽ là một bước trong Admin App mới (`3370aa4`). Nghĩa là nhìn
từ Console agent này **trông như đã golive** nhưng thực chất chưa có policy nào. Ai đọc dashboard mà
tin `golive_at` sẽ kết luận sai. Cách kiểm đúng vẫn là `GET /v1/self/context` → `instruction_block`.

## Việc CHỈ chủ agent làm được (không nhờ maintainer, không tự động hoá được)

Bốn việc dưới đây không nhờ ai được, làm sớm được thì làm.

- [ ] **0. Đăng nhập Console bằng Lark rồi tự XIN quyền `moderator`** ← làm cái này trước
      Core mới (`5843c9e feat(P10)`, lên `main` ngày 14/08) đã có luồng xin quyền per-agent, nên
      **không cần nhắc ntranthi qua GitHub nữa**:
      1. `https://app.34-126-154-135.sslip.io/login` → đăng nhập **bằng Lark**. Tài khoản Lark thuộc
         org được tự mở với quyền `user`, không cần ai tạo hộ.
      2. `/request-access` → xin `moderator` trên `AG-SOURCING`, ghi lý do.
      3. Admin **tự nhận thông báo qua Lark** (`_notify_admins`, `app.py:1575`), duyệt ở
         Console → Accounts → Yêu cầu phân quyền. Được/không được đều có tin nhắn Lark trả về
         (`app.py:1631`).

      Vì sao phải là anh/chị chứ không phải em: `POST /v1/roles/request` đòi `p["kind"] == "session"`
      (`app.py:1545`) — tức phiên đăng nhập trình duyệt. Token agent vẫn không dùng được, y như
      `/v1/agents/{id}/versions`. Kiểm lại lúc viết: vẫn `403 forbidden`.

      Ràng buộc đáng biết: `app.py:1613` chặn **tự duyệt yêu cầu của chính mình** dù là admin. Nên
      dù sau này anh/chị có admin thì vẫn cần người thứ hai bấm duyệt.

- [ ] **1. Verify tài khoản GitHub cho `linhntt@hapas.vn`.**
      Vercel đỏ ở **cả** PR #18, #20, #22, #23 với đúng một lý do:
      `GitHub couldn't verify an account for the commit`. Không phải lỗi code — `test` và
      `scope-guard` đều xanh. Sửa ở GitHub → Settings → Emails (thêm/verify email đang dùng để
      commit), hoặc đổi `git config user.email` sang email đã verify.
      *Tác dụng:* dọn sạch nhiễu đỏ trên mọi PR sau này, để lần nào đỏ là đỏ thật.

- [ ] **2. `claude setup-token` → deploy runtime.**
      `GET /v1/self/deploy/status` đang `not_deployed`, nên bước 3 của runbook chưa chạy được.
      `POST /v1/self/deploy` dùng `_require_self` (`app.py:1667`) → **token agent là đủ, không cần
      admin**; thứ duy nhất thiếu là `oauth_token`, mà chỉ chủ subscription tạo được:
      ```bash
      claude setup-token          # in ra token — KHÔNG dán vào issue/PR/chat/log
      ```
      Rồi truyền thẳng vào body `/v1/self/deploy` (xem bước 3, đường B).
      *Lưu ý thứ tự:* deploy xong là agent bắt đầu trả lời người thật, và container đặt
      `restart_policy: unless-stopped` nên không tự tắt. **Đừng deploy trước khi publish
      instruction** — làm bước 1→2 trước.

- [ ] **3. Bật Event Subscription trong Lark Developer Console.**
      App **Nihao Sourcing** (`cli_aaf6ce7c8d38deed`): event `im.message.receive_v1` + 4 scope
      `im:message`, `im:message:send_as_bot`, `im:chat:readonly`, `contact:user.id:readonly`.
      *Chưa xác nhận được bật hay chưa* — xem ghi chú ngay dưới.

### Vì sao không tự kiểm hộ được việc 3

Cách hiển nhiên là "gọi `/v1/self/jobs` xem có tin nào từ 2 nhóm chảy vào không". **Không được** —
endpoint đó không phải chỉ đọc, nó **giành job**:

```sql
-- app.py:2645  (GET /v1/self/jobs)
UPDATE jobs SET status='running', locked_by=%s, locked_at=now(),
                attempts=attempts+1, updated_at=now()
WHERE id = (SELECT id FROM jobs WHERE agent_id=%s AND status='queued' ...)
```

Gọi thử một lần là lấy tin nhắn thật của người ta ra khỏi queue, đánh `running` và tăng
`attempts`; không ai `reply/complete` thì nó chờ `_reap_stale` trả về, mỗi lần thử lại tốn một
`attempt` tới `max_attempts` rồi rơi vào `dlq`. Tức "xem thử" = làm mất tin nhắn của đồng nghiệp.

Đường chỉ-đọc thì đóng: `/v1/self/ops/snapshot` (`app.py:4332`) có đếm job theo status nhưng đòi
`is_platform=true`, AG-SOURCING nhận 403.

→ Trạng thái việc 3 chỉ anh/chị xác nhận được bằng mắt trong Lark Developer Console.

## Vì sao token agent không tự chạy được chuỗi này

Có **hai cửa độc lập**, không phải một:

1. **Cửa mạng (Caddy).** `infra/lsr-platform/caddy/Caddyfile:38` chỉ mở không cần gateway token cho
   `/v1/agents/enroll`, `/bootstrap/*`, `/v1/self`, `/v1/self/*`, `/v1/lark/*`, `/v1/chat/*`.
   `/v1/agents/{id}/versions` **không** thuộc danh sách này → thiếu header `X-Gateway-Token` là
   Caddy trả `403 "forbidden"` (chuỗi trần, không phải JSON `{"detail":…}` của FastAPI — đây là
   cách nhận biết mình bị chặn ở cửa nào).
2. **Cửa quyền (app).** `_require_role` (`app.py:227`) đòi `p["kind"] in ("session","admin_token")`.
   Token agent **không thuộc loại nào cả** → dù có gateway token vẫn không qua. Nghĩa là không phải
   "agent chưa đủ cấp moderator" mà là **agent vĩnh viễn không đủ tư cách**; việc này phải do
   **người** làm bằng phiên đăng nhập Console, hoặc bằng admin token.

Đường tự phục vụ còn lại cũng đóng: `POST /v1/self/actions/propose` (`app.py:4215`) đòi
`is_platform=true` (chỉ AG-OPS/AG-EVAL) → AG-SOURCING nhận 403.

Kết luận: **bước 1 và bước 5 buộc phải có người.** Không có mẹo nào lách, và không nên lách.

## Chuỗi golive — ai làm gì

### Bước 0 — Kiểm regex trước khi làm phiền người khác (em làm được, offline)
```bash
cd agents/AG-SOURCING && python3 golden_selfcheck.py    # không token, không model, không gọi API
```
Chấm 4 regex active bằng **đúng** hàm platform dùng (`_assert_answer`, `app.py:5038` →
`re.search`, không IGNORECASE) trên hai bộ câu: câu mà `INSTRUCTION.md` **bắt** agent nói (phải
khớp) và câu trả lời **sai** kiểu điển hình — đã xoá NCC, đọc dữ liệu BST, nêu nguồn rỗng (phải
KHÔNG khớp). Đã chạy: 4/4 case qua cả hai chiều.

Lý do có bước này: `--run` ở bước 4 cần **admin token** nên phải nhờ ntranthi. Regex viết sai thì
lần chạy đó fail vì lỗi mình, tốn một lượt nhờ người và để lại một dòng fail trong
`regression_runs`. Nhưng nó **không** thay được bước 4: ở đây câu trả lời do em viết theo
instruction, chạy thật là model viết.

### Bước 1 — Tạo version (chủ agent, cần `moderator`) — Console
`https://app.34-126-154-135.sslip.io/agent/AG-SOURCING` → **Version** → New version →
dán **toàn bộ** nội dung `INSTRUCTION.md` vào `instruction_block` → Save (version ở `draft`).

Ghi lại số version N. Kiểm: `GET /v1/self/version` phải thấy nó.

### Bước 2 — Publish `dev` (chủ agent, `moderator` là đủ)
Console → Version → Publish → env `dev`. `dev`/`stg` **không** qua eval gate
(`app.py:3272` chỉ gate khi `env == "prod"`), nên bước này chạy được ngay.

### Bước 3 — Hỏi agent bằng instruction MỚI
Cần một chỗ **thật sự gọi được model**. `GET /v1/self/deploy/status` hiện trả `not_deployed`, và
máy đang dùng **không có** `claude` CLI (`which claude` → not found) → nếu chạy ngay thì
`consumer.py > answer()` trả `"(lỗi gọi model: …)"` cho cả 4 câu, `--run` fail sạch. Hai đường:

**(A) Chạy tay ở máy mình** — phải cài `@anthropic-ai/claude-code` và đăng nhập subscription trước.
```bash
cd agents/AG-SOURCING
LSR_ENV=dev DRY_RUN=true python3 consumer.py     # terminal 1
LSR_AGENT_TOKEN=... python3 golden_run.py --ask  # terminal 2
```

**(B) Runtime chính thức trên VM — `POST /v1/self/deploy`.** Endpoint này dùng `_require_self`
(`app.py:1667`) và nằm trong allowlist `/v1/self/*` của Caddy → **token agent là đủ, KHÔNG cần
ntranthi**. Thứ duy nhất thiếu là `oauth_token` = output của `claude setup-token`, chỉ **chủ
subscription** (anh/chị owner) tạo được; đừng dán nó vào issue/PR/log, chỉ truyền thẳng vào body.
```bash
curl -s -X POST -H "Authorization: Bearer $LSR_AGENT_TOKEN" -H "Content-Type: application/json" \
  -d '{"oauth_token":"<claude setup-token>","repo":"<git url>","start_cmd":"LSR_ENV=dev DRY_RUN=true python3 agents/AG-SOURCING/consumer.py"}' \
  "$LSR_PLATFORM_URL/v1/self/deploy"
```
Image `lsr-agent-runner` đã bake sẵn `claude` CLI, và entrypoint còn tự `lease` credential từ pool
chung (`/v1/self/model-auth/lease`) — `oauth_token` chỉ là fallback. Hai chỗ dễ vấp, đã đọc code
chứ không đoán:
- runner tiêm token agent dưới tên **`LSR_TELEMETRY_API_KEY`**, không phải `LSR_AGENT_TOKEN`
  (`app.py:1697`). `consumer.py` đã sửa để nhận cả hai — bản gốc chết `KeyError` ngay khi khởi động.
- `git clone --depth 1 "$AGENT_REPO"` chạy **không có credential** (`entrypoint.sh:54`) và nuốt lỗi;
  repo private thì container vẫn sống nhưng không có code. Đây là phần core, agent không sửa được.

`LSR_ENV=dev` là bắt buộc ở cả hai đường: `/v1/self/context` mặc định `env=prod` (`app.py:3448`),
bỏ nó là đang chấm instruction **cũ** rồi gắn kết quả cho version **mới** — gate xanh mà chưa kiểm gì.

⚠️ **Cảnh báo tác dụng phụ, phải quyết trước khi chạy:** `consumer.py` poll `/v1/self/jobs` —
**một queue dùng chung mọi kênh**. Nó không phân biệt job của `golden_run.py` với tin nhắn thật
trong TEAM S / SOURCING MM, và `/reply` gửi thẳng vào nhóm. Nên bật consumer = agent bắt đầu trả
lời người thật. `DRY_RUN=true` **không** chặn việc này (chỉ chặn ghi brain). Đường (B) còn dai hơn:
container đặt `restart_policy: unless-stopped` (`app.py:1713`) nên tắt terminal không dừng nó —
phải gọi lại `/v1/self/deploy` hoặc nhờ ops stop container `lsr-agent-ag-sourcing`. Hai lựa chọn:
- (an toàn hơn) nhờ ntranthi tạm `pause_routing` 2 chat_id, chạy `--ask`, rồi bật lại;
- (nhanh hơn) chấp nhận: sau bước 2 agent đã có policy nên trả lời có kiểm soát.

Sau đó **đọc `answers.json` bằng mắt** — regex chỉ chứng minh agent CÓ NÓI câu đúng, không chứng
minh nó không bịa thêm số liệu ở câu sau. (`answers.json` bị gitignore: chứa tri thức nội bộ.)

### Bước 4 — Nạp golden case + chấm (ntranthi, cần `admin`)
```bash
cd agents/AG-SOURCING
LSR_ADMIN_TOKEN=... python3 golden_run.py --upload            # POST /v1/golden-cases  (admin)
LSR_ADMIN_TOKEN=... python3 golden_run.py --run --version N   # POST /v1/regression/run (admin)
```
Cả hai endpoint đều `_require_admin` (`app.py:5738`, `app.py:5783`) **và** nằm ngoài allowlist của
Caddy → người chạy cần cả `X-Gateway-Token`. Script chỉ dùng stdlib, luôn truyền
`skill: "AG-SOURCING"`, không ghi gì ngoài phạm vi agent.

`--run` phải đúng `--version N` của bước 1: gate tìm `regression_runs WHERE target_id=AG-SOURCING
AND agent_version=N AND passed=true` (`app.py:3218`).

### Bước 5 — Publish `prod`
Chủ agent bấm publish `prod` → vì chưa phải admin nên vào `pending_actions` chờ duyệt
(`app.py:3243`), ntranthi duyệt. Hoặc ntranthi publish thẳng.

Gate sẽ kiểm: ≥1 golden case `active` (đếm **toàn cục**) + regression run PASS gắn đúng version N.

### Bước 6 — Xác nhận thật
```bash
LSR_AGENT_TOKEN=... curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
  "$LSR_PLATFORM_URL/v1/self/context?session_id=probe&q=test" | python3 -m json.tool | head
# instruction_block PHẢI khác null, version PHẢI = N
bash scripts/agent-test.sh AG-SOURCING
```

## Biết trước hai chỗ sẽ vênh

- **Golden case #1 giờ có cơ sở để pass**: brain đã có tri thức, hỏi "Quy trình duyệt báo giá NCC
  hiện tại ra sao?" thì RAG trả về Bước 6 kèm `source_url` (kiểm bằng `brain_seed.py --check`).
  Trước khi nạp brain thì case này chắc chắn fail.
- **`llm_judge` âm thầm hạ cấp thành `contains`** khi `JUDGE_URL` chưa cấu hình (`app.py:5708`) —
  nên golden set này dùng `regex` toàn bộ, không dùng `llm_judge`.
