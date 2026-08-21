# AG-LEGAL — hướng dẫn cho Claude Code (project agent)

Trợ lý pháp chế LSR. Branch của project này: **`agent/legal-AG-LEGAL`**.
Kế hoạch đầy đủ: `~/LSR Legal Agent/PLAN-AG-LEGAL.md` (ngoài repo, không commit).

## Ba nguyên tắc — vi phạm là phải sửa lại, đừng tiết kiệm thời gian ở đây

1. **Bộ nhớ ở platform, không ở prompt/tiến trình.** Mỗi lượt gọi
   `GET /v1/self/context` (qua `legalkb/platform.py`) lấy `instruction_block` +
   `rolling_summary` + `recent_turns` + `user_facts` + `knowledge`, rồi dựng prompt
   stateless. Ghi lại bằng `/v1/self/session/turn`; `needs_summary` → nén bằng
   `brain.compress()` rồi `/v1/self/session/summary`. Fact bền → `/v1/self/facts`.
   *Kiểm nhanh:* restart container rồi hỏi tiếp câu phụ thuộc ngữ cảnh — phải vẫn hiểu.
2. **Mọi tương tác Lark qua platform.** Chỉ dùng `legalkb/platform.py`
   (`/v1/lark/send`, `/v1/lark/resolve`, `/v1/lark/chats`, `/v1/lark/resource/...`,
   `/v1/self/jobs/*/reply`). **Không** `im/v1/messages`, **không** cầm `app_secret`.
   Ngoại lệ duy nhất, có ghi chú trong file: `legalkb/lark_kb.py` đọc Wiki/Drive để nạp
   KB — vì broker của core chưa có endpoint đó (yêu cầu **C1**). Đừng mở rộng ngoại lệ này.
3. **Hành vi ở `INSTRUCTION.md`**, publish thành `instruction_block` có version. Không
   hard-code persona/policy vào `consumer.py`. `apply_instruction()` nạp nó vào cả
   NotebookLM.

## Ràng buộc kỹ thuật đã trả giá để biết

- **Một tiến trình = một phiên NotebookLM.** Cookie xoay sau mỗi phiên; hai tiến trình
  dùng chung account sẽ vô hiệu hoá nhau ("Authentication expired"). Vì vậy `sync_loop`
  và (sau này) `news_loop` là **thread trong `consumer.py`**, không phải container riêng.
  `sync_worker.py` chỉ để chạy tay khi consumer đang DỪNG.
- Job nặng có thể vượt hạn khoá 120s của platform → job bị giao lại. Chống trả lời đôi
  bằng `store.get_meta(f"replied:{jid}")`.
- `POST /v1/actions/*/decide` và `POST /v1/extract` của core đòi quyền **admin** → token
  agent dùng không được. Vì vậy phê duyệt nằm ở bảng `legal_gates` của agent, và trích
  text PDF/docx làm trong agent.

## Cấu trúc

```
consumer.py        điều phối: poll job → router → gọi flow → gate; lệnh duyệt trong group
seed_roles.py      nạp legal_roles (2 người duyệt) + resolve open_id
seed_news.py       nạp nguồn luật (S4) + checklist đầu mục hồ sơ (S5)
golden_run.py      golden set — phép kiểm CHỐNG BỊA NGUỒN (--selfcheck chạy offline)
golive.json        checklist golive 28 mục (nộp bằng scripts/submit-golive.sh)
sync_worker.py     chạy sync TAY (chỉ khi consumer đang dừng)
INSTRUCTION.md     nguồn của instruction_block
legalkb/
  platform.py      MỌI lời gọi platform (bộ nhớ, job, Lark broker)
  brain.py         gọi Claude (`claude -p`, subscription) + dựng prompt + nén hội thoại
  gates.py         khung Pháp chế in the loop + parser lệnh `#12 duyệt`
  flows.py         luồng S2–S5 + hệ quả sau khi Pháp chế quyết (dispatch_decision)
  contracts.py     S2: registry mẫu, điền docx, state đa lượt, quy góp ý về field
  review.py        S3: checklist từ KB + đối chiếu + state machine
  news.py          S4 HẰNG TUẦN (thứ 2 07:00): crawl theo NƯỚC (VN, TH…), dedupe theo
                   số hiệu, lưu bản gốc về Drive, digest chờ duyệt
  web.py           lấy trang công khai: header browser + giãn cách theo TỪNG HOST
  chinhphu.py      chinhphu.vn — số hiệu từ cột dữ liệu + PDF KÝ SỐ bản gốc
  tvpl.py          thuvienphapluat.vn — toàn văn qua HTML, không cần đăng nhập
  luatvietnam.py   luatvietnam.vn — TRA CỨU THEO TÊN (cách pháp chế đang làm tay)
  signing.py       S5: logic Bước 3/Bước 5 + form thật của workflow Lark Approval
  approval.py      đọc Lark Approval qua broker C8 (platform giữ user token, agent
                   KHÔNG thấy token). Bảng ĐO THẬT endpoint nào dùng token nào ở đầu file
  extract.py       trích text PDF/DOCX (không dùng /v1/extract vì nó đòi admin)
  addressing.py    gọi tên mới trả lời trong nhóm + khoá phiên theo chat (bộ nhớ nhóm)
  voice.py         nghe tin thoại; chưa có transcriber thì NÓI THẬT, không im lặng
  userchat.py      chat dưới danh tính ACCOUNT của agent bằng POLL (Lark không đẩy event
                   cho account người). Mẫu: jenny-bod-assistant. Token do platform giữ
  engine.py        NotebookLM (AnswerEngine — có thể swap sang Gemini File Search)
  lark_kb.py       đọc/ghi Wiki-Drive (ngoại lệ C1)
  sync.py store.py đồng bộ KB + SQLite (13 bảng)
```

## Luật riêng của từng skill — đừng "tối giản" mấy chỗ này

| Chỗ | Luật | Vì sao |
|---|---|---|
| S2 | Bản thảo **không** gửi thẳng người yêu cầu; luôn qua gate `s2_draft` | Review §A.1 |
| S2 | Field thiếu để nguyên `{{...}}` trong docx | Xoá âm thầm = tạo hợp đồng thiếu điều khoản |
| S2 | Góp ý không quy được về field → **hỏi người**, không đoán giá trị | Đoán giá trị hợp đồng là rủi ro pháp lý |
| S3 | Model lỗi → `clean=False` | Không bao giờ được kết luận "hợp đồng sạch" khi chưa rà được |
| S4 | Mục thiếu link nguồn → **loại** khỏi digest | Review §B, chống bịa nguồn |
| S4 | Chưa duyệt = **không gửi, không nạp KB** | Review §B |
| S4 | **Lưu bản gốc + index TRƯỚC gate**, chỉ digest mới chờ duyệt | Bản gốc là tài liệu nhà nước, không phải nội dung AI — cần tra được ngay khi phát sinh việc |
| S4 | Nguồn chưa kiểm được → **inactive + `note`** | Để active thì mỗi tuần báo lỗi mà không ai biết là do seed sai (3/4 nguồn seed đầu đã chết) |
| S4 | Nguồn `html` **bắt buộc** có `link_pattern` | Parse HTML tuỳ ý sẽ ra rác mà vẫn "thành công" |
| S4 | Văn bản người **bỏ tay** vào kho Drive cũng phải vào index | Nước chưa có nguồn tự động (Thái Lan bỏ khỏi scope 21/08, thêm trên console sau) — kho có văn bản mà agent không biết thì vô ích |
| S4 | Số hiệu đọc lại từ **tên file** khi nạp tay | `_safe_name()` làm phẳng dấu `/` khi upload ⇒ `doc_no` NULL ⇒ dedupe không chạy ⇒ Bộ luật Lao động đã vào kho 2 lần thật |
| S4 | Số hiệu do **nguồn cấp** > regex dò tiêu đề | Trích yếu "Quy định về định danh địa điểm" (326/2026/NĐ-CP) không có chữ số nào ⇒ regex trượt ⇒ dedupe liên nguồn vỡ |
| S4 | Bản gốc **tốt hơn tới sau thì đổi** (`file_urls`) | RSS chạy trước chỉ có link trang tin; chinhphu.vn có PDF ký số |
| S4 | Host nào chưa có bộ trích toàn văn → **báo lỗi**, không lưu HTML cả trang | Lưu 2MB menu/quảng cáo rồi gọi là "văn bản gốc" = báo thành công mà vô dụng |
| Tra cứu | Khớp theo **CỤM TỪ**, không theo tỉ lệ từ trùng | Live: "Luật Lực lượng dự bị động viên 2019" đạt 3/4 từ với "Bộ luật Lao động 2019" và được index như thể đúng |
| Tra cứu | Model trả rác (JSON, quá dài) → **không tra cứu** | Đem rác đi tìm thì nguồn vẫn ra kết quả, và agent trích dẫn 3 văn bản không liên quan |
| Tra cứu | `-d10.html` của luatvietnam là **DỰ THẢO** → loại, hoặc gắn cờ rõ | 72/123 kết quả tìm kiếm là dự thảo; trích dự thảo như đang có hiệu lực là sai nghiêm trọng |
| S5 | Quá SLA 30' hoặc model lỗi → `auto_passed` | Máy không được làm nghẽn quy trình người |
| S5 | Nguồn sự thật là `tasks?topic=1`, **không** phải `instances` | `instances` liệt kê đòi tenant token (đo 20/08); `topic` là tham số BẮT BUỘC, options [1,2,17,18] |
| S5 | Mỗi `task_id` báo **đúng một lần** (khoá ở `meta`) | `topic=1` trả lại đúng việc đó ở mọi lần poll → không khoá là spam group mỗi 5 phút |
| S5 | Chưa đọc được nội dung hồ sơ → **vẫn báo**, nói rõ chưa đọc được | Một hồ sơ đã tới mà không ai biết còn tệ hơn một tin báo thiếu |
| S5 | Form rỗng → **không** rà soát | Không sinh báo cáo từ không có gì |
| Danh tính | `refresh_token` 7 ngày; còn ≤2 ngày thì **nhắc group** | Im lặng hết hạn = S5 chết âm thầm (đã xảy ra 17/07, 19/08 mới phát hiện) |
| userchat | Chat mới thấy → cursor bắt đầu từ **now**, không phải 0 | Lấy từ 0 là lần chạy đầu trả lời lại toàn bộ lịch sử chat của cả công ty |
| userchat | Bỏ tin của **chính mình** (nhớ `message_id` đã gửi) | Không thì agent trả lời câu trả lời của nó, lặp vô hạn |
| userchat | Cursor **luôn tiến** (`max(latest, now)`) | Tin xử lý lỗi cũng không đọc lại mãi |
| userchat | Tin đi qua **đúng `handle()`**, không có nhánh riêng | Nhánh riêng là chỗ tính năng rơi lại mà không ai biết |
| Đo lường | Cùng một API, **tenant token và user token trả khác nhau** | `im/v1/chats`: tenant chỉ trả group, user trả cả chat 1-1. Đo sai loại token là kết luận sai kiến trúc (đã tự vấp 21/08) |
| S5 | Tối đa 2 lần quay lại Bước 4, lần 3 escalate | Chống vòng lặp vô hạn |
| Mọi gate | Quá hạn chỉ **NHẮC**, không tự thông qua (trừ `observe`) | Điểm an toàn cốt lõi |
| Mọi kênh | **Không có bước phê duyệt** khi ai chat lần đầu hay khi bot được add vào nhóm — trả lời luôn, cho tất cả mọi người | Chốt 21/08. Đổi lại: audit event trên job + ghi lượt vào bộ nhớ + một dòng `s1_answer` để `#ds`/`tham gia` gọi tới |
| Mọi kênh | Lượt đầu **không gửi card** vào group, kể cả khi tính là rủi ro cao | "chào bạn" cũng bị tính rủi ro cao (không trích dẫn) ⇒ bắn card đỏ cho một câu chào. Chống bịa nguồn đã có 2 lớp mạnh hơn: lọc citation khỏi câu trả lời + `golden_run.py` FAIL |
| Mọi kênh | Hội thoại **đang chạy mới chuyển** sang rủi ro cao → @ người trực | Báo động an toàn, không chặn ai |
| Nhóm | Chỉ trả lời khi **được gọi tên/@mention**; tin khác vẫn **ghi lượt** | Nhảy vào mọi câu là cách nhanh nhất để bị đá khỏi nhóm; nhưng vẫn cần ngữ cảnh khi được gọi |
| Nhóm | Nhóm **tự phát hiện** qua `/v1/lark/chats` mỗi chu kỳ `gate_loop` | Core nói rõ endpoint này chỉ trả **nhóm** ⇒ add bot vào nhóm mới là dùng được ngay, không phải sửa env rồi deploy lại |
| Phiên | Khoá theo **chat_id**, KHÔNG theo job id | Gateway không set `session_id`; khoá theo job = mỗi tin một phiên = không có bộ nhớ |
| Nhóm/riêng | Phân biệt bằng `chat_type` nếu có, không thì `AGENT_GROUP_CHAT_IDS` | Lark dùng `oc_` cho **cả** p2p lẫn group — đoán theo tiền tố là sai |
| Thoại | Tin thoại có `file_key` nhưng **không** tính là file đính kèm | Nếu tính thì router đẩy sang S3 "rà soát hợp đồng" |

## Pháp chế in the loop

Group **`oc_2c44821d37e5e12a2c1651251cfd4efb`** nhận thông báo *và* nhận lệnh phê duyệt.
Người duyệt gõ trong group:

| Lệnh | Việc |
|---|---|
| `#12 duyệt` | approve |
| `#12 sửa: <góp ý>` | yêu cầu sửa |
| `#12 huỷ: <lý do>` | từ chối |
| `#12 tham gia` / `#12 trả lại` | người thay Agent / trả lại Agent |
| `#12 nhắn: <nội dung>` | chuyển lời tới người hỏi |
| `#ds` | danh sách việc đang chờ |

Chỉ `sender_open_id` có trong `legal_roles` mới có hiệu lực. Tin thường trong group →
**agent im lặng** (đừng làm nó trả lời mọi câu, group đó người ta còn việc khác).
Gate `observe` quá hạn thì tự thông; gate `gate` **không bao giờ tự động thông qua** —
chỉ nhắc.

## Chạy & test

```bash
python3 -m pytest tests/ -q          # offline, không cần secret
python3 seed_roles.py --list         # xem người duyệt
docker compose up                    # chạy thật (cần .env)
bash ../../scripts/agent-test.sh AG-LEGAL
bash ../../scripts/agent-chat.sh AG-LEGAL "câu hỏi thử"
```

Đăng ký/golive theo `PLAN §2.2`: `bash ../../scripts/lsr-login.sh` → enroll →
`claude setup-token` → `POST /v1/self/deploy`. **Kiểm golive bằng
`GET /v1/self/context` → `instruction_block` ≠ null**, đừng tin `status`/`golive_at`.
