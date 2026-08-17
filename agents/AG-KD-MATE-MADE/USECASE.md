# Use case — LYLY, trợ lý Kinh doanh MATE MADE (AG-KD-MATE-MADE)

## Bài toán

Sale MATE MADE đang chat với khách thì cần **giá, chính sách chiết khấu, phí ship, thời
gian bảo hành** ngay lập tức. Hiện phải mở Lark Base tra, hoặc nhắn hỏi quản lý rồi chờ —
khách nguội trong lúc chờ. Nhiều sale báo giá theo trí nhớ, và trí nhớ thì lệch khi bảng
giá vừa đổi.

Sale cũng hay bí ở hai chỗ giống nhau mỗi ngày: **soạn tin trả lời khách** cho đúng giọng,
và **xử lý khách chê đắt / lưỡng lự** — mỗi người tự nghĩ một kiểu, chất lượng không đều.

Song song, cuộc họp KD diễn ra liên tục nhưng biên bản viết tay chậm và **hay sót cam kết**:
ai hứa làm gì, hạn nào, với khách nào. Tuần sau không ai nhớ để truy.

**LYLY** làm ba việc:
1. **Tra giá & chính sách** — trả lời trong vài giây, luôn kèm **link nguồn + kỳ dữ liệu**
   để sale đối chiếu trước khi báo khách.
2. **Soạn tin & gợi ý xử lý khách khó** — đoạn tin copy-gửi-luôn, playbook xử lý từ chối
   kèm câu nói mẫu.
3. **Biên bản họp tự động** — dựng từ recording, bóc riêng phần **cam kết ai-làm-gì-khi-nào**,
   xin chủ trì chốt rồi mới publish và tạo task.

> **LYLY nói chuyện với sale nội bộ, KHÔNG với khách hàng cuối.** Mọi câu trả lời là để
> sale đọc, cân nhắc, rồi mới chuyển cho khách — không bao giờ đi thẳng ra khách.

## Người dùng

- **Nhân viên sale MATE MADE** — người dùng chính. Hỏi qua nhóm Lark có LYLY, hoặc DM bot.
- **Quản lý kinh doanh** — người duyệt mọi ngoại lệ (chiết khấu vượt khung, công nợ, giao
  gấp) và chốt danh sách được xem dữ liệu hạn chế.
- **Chủ trì cuộc họp** — người **chốt** biên bản trước khi publish.
- **Người duyệt tri thức** — duyệt dữ liệu vào kho trên console trước khi LYLY được dùng.
- **Người thử nhanh** — Chat thử trong console (`/agent/AG-KD-MATE-MADE`).

## Luồng chính (happy path)

### Luồng A — Tra giá & chính sách

1. Sale hỏi, ví dụ: "giá sỉ sản phẩm A từ bao nhiêu cái?".
2. LYLY gọi `/v1/self/context` → nhận instruction (bản đang publish) + tóm tắt hội thoại
   + fact người dùng + **tri thức liên quan kèm `source_url`**.
3. Có căn cứ đã duyệt → trả lời gọn: **số + trích dẫn nguồn + kỳ dữ liệu**.
4. **Không có căn cứ** → _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_ Không suy
   đoán, không làm tròn, không suy từ sản phẩm tương tự.
5. Câu hỏi chạm **dữ liệu hạn chế** (giá vốn, chiết khấu riêng, danh sách khách) → chỉ trả
   lời cho người trong phạm vi; xem mục Ranh giới dữ liệu.
6. Ghi lượt hội thoại để lượt sau còn ngữ cảnh.

### Luồng B — Soạn tin & xử lý khách khó

1. Sale nhờ "soạn giúp em tin báo giá gửi khách" → LYLY trả **đoạn tin hoàn chỉnh** để
   copy. Thiếu số thì **chừa chỗ trống rõ ràng** (`[giá: hỏi quản lý]`), không tự điền.
2. Sale hỏi "khách chê đắt xử lý sao" → LYLY trả **hướng xử lý + câu nói mẫu**, không nói
   lý thuyết chung chung.
3. Khách so sánh đối thủ → nhấn điểm khác biệt MATE MADE, **tuyệt đối không nói xấu đối thủ**.

### Luồng C — Sale xin ngoại lệ (chặn cứng)

Sale hỏi "giảm thêm 5% được không", "cho nợ 30 ngày được không", "giao gấp trong ngày được
không" → LYLY **không bao giờ phán "được"**, kể cả khi bảng chiết khấu đã có trong kho.
Luôn đẩy về **quản lý kinh doanh** kèm hướng dẫn cần trình bày gì để duyệt nhanh, và nhắc
sale **chưa hứa trước với khách**.

### Luồng B — Biên bản họp

1. Ai đó gửi recording / link Lark Minutes vào nhóm KD.
2. Agent gửi transcript job lên Whisper server, chờ kết quả.
3. Dựng **biên bản nháp** gồm: tóm tắt · quyết định · **cam kết (ai · làm gì · hạn)** ·
   deal/khách hàng được nhắc · next action · rủi ro nêu trong họp.
4. Post nháp vào nhóm và **xin chủ trì xác nhận**. **Không tự publish.**
5. Chủ trì trả lời "chốt/duyệt/confirm" → tạo Lark Docs, tạo task cho từng cam kết, nộp
   biên bản vào hàng chờ tri thức để lần sau tra được.
6. Chủ trì trả lời "sửa ..." → cập nhật nháp, xin chốt lại.

## Ngoài phạm vi (không làm)

- **Không tự duyệt chiết khấu vượt khung, công nợ, hay thời gian giao ngoài chính sách** —
  đẩy về quản lý kinh doanh. Kể cả khi sale nói gấp.
- **Không tự publish biên bản** khi chưa có chủ trì chốt. Không gửi cho người ngoài nhóm.
- **Không nói chuyện trực tiếp với khách hàng cuối** — LYLY chỉ soạn nội dung cho sale gửi.
- Không trả lời bằng suy đoán thị trường/số liệu ngoài kho tri thức đã duyệt. Không làm
  tròn, không nói "khoảng", không suy từ sản phẩm tương tự.
- Không tự điền số vào tin nhắn gửi khách khi chưa có dữ liệu — chừa chỗ trống rõ ràng.
- **Không nói xấu đối thủ**, không bình luận giá/chất lượng của bên khác.
- Không tiết lộ giá vốn, biên lợi nhuận, danh sách khách hàng cho người ngoài phạm vi.
- Không sửa dữ liệu gốc trên Lark Base / Sheets — chỉ đọc và đề xuất.
- Không xử lý lương thưởng, hoa hồng cá nhân, khiếu nại lớn từ khách.
- **Không nhận việc biên bản cho nhóm ngoài KD Mate Made** — xem Ranh giới với AG-MINH-ANH.

## Dữ liệu cần truy cập

| Nguồn | Domain tri thức | Scope | Trạng thái |
|---|---|---|---|
| Lark Wiki **TEAM KINH DOANH MATE MADE** (`7496094770155061279`) | `business-context` | shared | **đã có sẵn** — AG-LEGAL sync hàng ngày, agent này chỉ đọc |
| Lark Base pipeline / đơn hàng / khách hàng | `kd-confidential` | **agent** (chỉ AG-KD) | cần `app_token` |
| Lark Drive / Sheets báo cáo doanh số | `kd-report` | shared | cần `folder_token` |
| Biên bản họp đã chốt | `kd-meeting` | shared | agent tự sinh |
| BigQuery `AI_DB` | — | — | **phase 2** — cần GCP admin cấp dataset + SA riêng |

Đồng bộ bằng job `kd_sync.py` (hàng ngày 6h VN). Mọi tri thức vào hàng chờ `status=pending`,
**người của team KD duyệt** trên console rồi agent mới dùng được.

> **Không sync lại wiki space KD.** `agents/AG-LEGAL/legal_sync.py` đã đồng bộ chính space
> này vào domain `business-context`. Sync lần hai sẽ tạo bản trùng → người duyệt phải duyệt
> hai lần và RAG trả kết quả lặp.

## Ranh giới dữ liệu (ai thấy được gì)

| Nhóm dữ liệu | Ai tra được |
|---|---|
| Quy trình, chính sách bán hàng, FAQ (`business-context`) | mọi người trong công ty |
| Báo cáo doanh số tổng (`kd-report`) | mọi người trong công ty |
| **Giá vốn, biên lợi nhuận, chiết khấu theo khách, danh sách khách hàng** (`kd-confidential`) | **chỉ AG-KD-MATE-MADE** — `scope=agent`, agent khác không tra được |
| Biên bản họp đã chốt (`kd-meeting`) | mọi người trong công ty |

## Ranh giới với AG-MINH-ANH (agent biên bản của platform)

Platform đã có AG-MINH-ANH làm biên bản họp chung. Hai agent **không được cùng vào một
nhóm** — nếu cùng nhóm sẽ ra hai biên bản khác nhau cho cùng cuộc họp và không ai biết bản
nào là bản chính.

Quy ước chốt với admin:
- AG-KD-MATE-MADE: **chỉ** nhóm họp của team KD Mate Made.
- AG-MINH-ANH: mọi nhóm còn lại.
- Admin gán kênh vào ở Console → Ingress; không tự add bot vào nhóm.

## Rủi ro & giới hạn

| Rủi ro | Giảm thiểu |
|---|---|
| **Bịa giá** (nguy hiểm nhất — sale copy nguyên câu trả lời gửi khách, sai giá là mất tiền hoặc mất khách) | Bắt buộc tra tri thức trước khi trả lời; không có hit → câu từ chối cố định _"Cái này em chưa có…"_. Đo bằng **OFR** (bịa) và **CTUR** (dùng tool sạch) |
| **Tự duyệt chiết khấu / công nợ / giao gấp** | Chặn bằng luật trong `consumer.py` (`ASK_APPROVAL`) **trước** mọi nhánh khác — không phụ thuộc prompt. Có 3 test case |
| **Tự điền số vào tin nhắn gửi khách** | Khi chưa có dữ liệu, tin nhắn mẫu chừa `[giá: hỏi quản lý]` thay vì số |
| **Nói xấu đối thủ trong câu mẫu** | Playbook "so sánh" ghi rõ nguyên tắc; có test case kiểm |
| Trả lời bằng **số liệu kỳ cũ** | Mỗi câu trả lời nêu rõ **kỳ dữ liệu** và ngày sync gần nhất; sync hàng ngày |
| **Lộ giá vốn / danh sách khách hàng** | `scope=agent` cho `kd-confidential` — agent khác không tra được; có test case kiểm |
| **Sót cam kết trong biên bản** | Cam kết là mục bắt buộc trong biên bản; thiếu người/hạn thì ghi rõ "chưa rõ", không bỏ trống |
| **Biên bản sai được publish** | Không bao giờ tự publish — bắt buộc chủ trì chốt |
| Transcript sai / server transcript chết | `LSR_TRANSCRIBE_URL` cấu hình được; lỗi → job vào DLQ, replay từ console |
| **Riêng tư khi ghi âm họp** | Thông báo minh bạch cho team trước khi tắt `DRY_RUN`; PII được redact ở collector |
| Trùng biên bản với AG-MINH-ANH | Ranh giới nhóm ở trên, chốt với admin trước golive |

## Phụ thuộc bên ngoài (chặn golive, không chặn code)

- [ ] `app_token` Lark Base pipeline + `folder_token` folder báo cáo Drive.
- [ ] App Lark riêng của agent được cấp scope đọc wiki/docx/bitable/drive + `im:message`.
- [ ] `chat_id` nhóm KD, admin gán ở Console → Ingress.
- [ ] URL transcript server ổn định (hiện là ngrok free, không SLA).
- [ ] Chốt với admin ranh giới nhóm với AG-MINH-ANH.
- [ ] (phase 2) GCP admin cấp dataset + SA riêng cho BigQuery `AI_DB`.
